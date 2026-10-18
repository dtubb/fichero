"""Training a Kraken reader on Hugging Face Jobs, as one job row (#5398).

`compute.job.one-state-machine`: the job is a row in the one `jobs` table (`execution/jobs.py`), kind
`train-a-model`, lane `remote` (it waits on the network and never holds the local ML lane), target
`huggingface-jobs`. Its phases are the row's `reason` in words and its `detail` (JSON): the request,
the training set's counts, the Job's id on Hugging Face, the phase history, the last lines of the
Job's log, the price per hour, and, when done, the reader it landed.

    preparing -> sending -> submitted -> queued -> running -> fetching -> landing -> done

A restart while it runs resumes it: the Job's id is stored as soon as Hugging Face gives it, and a
resumed job watches that Job rather than sending a second. The global pause stops new jobs from
starting and never cancels one already running there (that would waste paid time). Cancelling
cancels the Job on Hugging Face and ends the row `cancelled`.

Before anything leaves this Mac the request must carry the person's yes for this project's pages to
go to Hugging Face (`pages_may_leave`), which is recorded on the row. A fuller, once-per-project
record (`compute.leave.*`, #5239) is not built yet.
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


from fichero_server.execution import jobs
from fichero_server.training.model_nodes import project_of
from fichero_server.models.compute_requests import (  # noqa: F401  (re-exported)
    TrainKrakenHereRequest,
    TrainKrakenRequest,
    TrainVisionLoraRequest,
    _TrainRequest,
)

KIND = "train-a-model"
TARGET = "huggingface-jobs"
#: How often a running Job is looked at (`compute.job.poll-is-gentle`).
POLL_SECONDS = 60.0
NOT_FOR_RELEASE_NOTE = "No release was recorded for the pages it was trained on; it is not released."


#: The cards a training job can be, by the name its row records.
CARDS: dict[str, type[_TrainRequest]] = {"kraken": TrainKrakenRequest, "vision-lora": TrainVisionLoraRequest}


def counted(n: int, word: str) -> str:
    """A count in words that agree with it: "1 page", "3 pages" (#5617, `source.find.note-counts-agree`)."""
    return f"{n} {word}{'' if n == 1 else 's'}"


def taught_by(teacher: str) -> str:
    """Who taught a reader, in the card's words: a model by its name, the person as their corrections (#5700)."""
    from fichero_server.training.kraken_set import PERSON

    return "your corrections" if teacher == PERSON else teacher


def lessons(teacher: str, ts: dict[str, Any]) -> str:
    """What a reader learned from: the person's corrected lines, or a model's lines no person checked (#5700)."""
    from fichero_server.training.kraken_set import PERSON

    pages, lines = counted(ts["pages"], "page"), counted(ts["lines"], "line")
    if teacher == PERSON:
        return f"Trained on {pages} ({lines} you corrected)"
    return f"Taught by {teacher} on {pages} ({lines}, none checked by a person)"


def _card_of(request: _TrainRequest) -> str:
    return next(name for name, model in CARDS.items() if type(request) is model)


class PagesMayNotLeave(PermissionError):
    """No yes was given for the pages to leave this Mac."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _work_dir(job_id: str) -> Path:
    from fichero_server.db.paths import server_state_dir

    return server_state_dir() / "training" / job_id


def _row(db: Any, job_id: str) -> tuple[str, dict[str, Any]]:
    row = jobs.read_job(db, job_id)
    if row is None:
        raise LookupError(f"no training job {job_id}")
    return row["state"], json.loads(row["detail"] or "{}")


def _save(db: Any, job_id: str, detail: dict[str, Any], *, phase: str | None = None, reason: str | None = None) -> None:
    if phase and detail.get("phase") != phase:
        detail["phase"] = phase
        detail.setdefault("history", []).append({"phase": phase, "at": _now()})
    jobs.save_detail(db, job_id, json.dumps(detail), reason=reason)


def _place_of(request: _TrainRequest) -> str:
    """Where the training runs: Hugging Face Jobs, or a cluster set up here by its id (#5769)."""
    return getattr(request, "target", TARGET) or TARGET


def _target_for(place: str) -> Callable[[], Any]:
    from fichero_server.training.hf_jobs import HfJobsTarget

    if place == TARGET:
        return HfJobsTarget
    from fichero_server.remote_read.job import cluster_target

    return cluster_target(place)  # no key yet: refused by name (#5238); tests and the live run inject the target


def _place_words(target: Any, place: str) -> str:
    return "Hugging Face" if place == TARGET else getattr(getattr(target, "cluster", None), "name", None) or place


def start(db: Any, request: _TrainRequest, *, started_by: str,
          target_factory: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Queue a training job; refuses before anything is queued when it could not run."""
    from fichero_server.llm.kraken_runtime import resolve_recognition_model
    from fichero_server.training.hf_jobs import LORA_FLAVORS, kraken_batch

    place = _place_of(request)
    if not request.pages_may_leave:
        where = "Hugging Face" if place == TARGET else f"the cluster {place}"
        raise PagesMayNotLeave(f"Training on {where} sends this project's pages there. "
                               "Say yes for this project first (pages_may_leave).")
    if not request.scope_ids:
        raise ValueError("name the folders or pages to train on")
    if isinstance(request, TrainKrakenRequest) and request.base:
        resolve_recognition_model(request.base)  # not installed: refused here, by name
    target = (target_factory or _target_for(place))()  # no token (or key): refused here, by name
    target.check_token()  # a token that can't run Jobs: refused here, in words (#5526)
    from fichero_server.training.kraken_set import refuse_an_empty_set

    refuse_an_empty_set(db, request)  # nothing to train on: refused here, with the preview's reason (#5699)
    flavor = (request.flavor or target.cheapest(LORA_FLAVORS)) if place == TARGET else ""  # a cluster: one GPU a job
    price = target.price_per_hour(flavor)
    batch = kraken_batch(flavor, request.batch_size) if isinstance(request, TrainKrakenRequest) else None
    detail = {"card": _card_of(request), "request": request.model_dump(), "flavor": flavor,
              "price_per_hour_usd": price, "yes": {"by": started_by, "at": _now(), "to": place},
              "phase": "waiting", "history": [{"phase": "waiting", "at": _now()}],
              **({"batch_size": batch} if batch else {})}
    job_id = jobs.enqueue_remote(db, KIND, f"training:{uuid.uuid4()}", target=place, detail=json.dumps(detail),
                                 reason=f"Waiting to send to {_place_words(target, place)}", started_by=started_by)
    return {"job_id": job_id, "flavor": flavor, "timeout": request.timeout, "price_per_hour_usd": price,
            "batch_size": batch}


#: Phases after which the Job on Hugging Face is known to have ended (or never to have started).
_FAR_ENDED = ("failed", "cancelled", "fetching", "landing", "done")
CANCELLED_THERE = "Stopped by you; the Job on Hugging Face was cancelled"


def _may_run_there(detail: dict[str, Any]) -> bool:
    return bool(detail.get("far_id")) and detail.get("phase") not in _FAR_ENDED


def request_cancel(db: Any, job_id: str, *, target_factory: Callable[[], Any] | None = None) -> str:
    """Stop a training job: one not started yet ends now; a running one is cancelled on Hugging Face
    at its next look. A row whose Job may still run there while nothing here follows it (waiting to
    be taken up again, out of this engine's reach, or failed by an engine that could not reach it)
    is cancelled on Hugging Face now (#5449, `compute.job.another-engine-never-fails-what-it-cannot-reach`).
    Returns the row's state after the request."""
    from fichero_server.training.hf_jobs import cannot_reach

    state, detail = _row(db, job_id)
    followed_here = state == "running" and not detail.get("out_of_reach")
    if _may_run_there(detail) and state in ("waiting", "paused", "running", "failed") and not followed_here:
        try:
            (target_factory or _target_for(_place_of(CARDS[detail.get("card", "kraken")](**detail["request"]))))(
            ).cancel(detail["far_id"])
        except Exception as exc:
            if not cannot_reach(exc):
                raise
            # Not reached from here: the next engine that can reach it cancels it at its first look.
            detail["cancel"] = True
            _save(db, job_id, detail, reason="Stopping: this engine can't read the Hugging Face token, so the "
                                              "Job is cancelled by the next Fichero that has it")
            return state
        detail.update(cancel=True, cancel_sent=True)
        _save(db, job_id, detail, phase="cancelled")
        jobs.end_cancelled(db, job_id, CANCELLED_THERE)
        return "cancelled"
    if state == "waiting":
        jobs.cancel_waiting(db, job_id)
        return "cancelled"
    if state == "running":
        detail["cancel"] = True
        _save(db, job_id, detail, reason="Stopping: cancelling the Job on Hugging Face")
    return state


def status(db: Any, job_id: str) -> dict[str, Any]:
    state, detail = _row(db, job_id)
    reason = jobs.read_job(db, job_id)["reason"]
    return {"job_id": job_id, "state": state, "reason": reason, **detail}


def _job_id_for(db: Any, subject: str) -> str:
    return jobs.job_id_for(db, KIND, subject)


def run(db: Any, subject: str, *, target: Any | None = None, sleep: Callable[[float], None] = time.sleep,
        poll_seconds: float | None = None) -> str:
    """Carry a training job through its phases; returns the landed model's id."""
    from fichero_server.llm.kraken_runtime import resolve_recognition_model
    from fichero_server.training.hf_jobs import (
        LORA_TRAINER, TRAINER, cannot_reach, kraken_args, kraken_batch, lora_args, ran_out_of_gpu_memory,
    )
    from fichero_server.training.kraken_set import EmptyTrainingSet, export_training_set
    from fichero_server.training.line_pairs import write_line_pairs

    job_id = _job_id_for(db, subject)
    _state, detail = _row(db, job_id)
    card_name = detail.get("card", "kraken")
    request = CARDS[card_name](**detail["request"])
    vision = isinstance(request, TrainVisionLoraRequest)
    flavor = detail.get("flavor", request.flavor)
    place = _place_of(request)
    if target is None:
        try:
            target = _target_for(place)()
        except Exception as exc:
            _out_of_reach_if_running_there(db, job_id, detail, exc)
            raise
    there = _place_words(target, place)
    work = _work_dir(job_id)
    poll = POLL_SECONDS if poll_seconds is None else poll_seconds

    batch = None if vision else (detail.get("batch_size") or kraken_batch(flavor, request.batch_size))
    if not detail.get("far_id"):
        # Minutes of preparing are never spent on a token Hugging Face will refuse at sending (#5526).
        target.check_token()
        _save(db, job_id, detail, phase="preparing", reason="Preparing the training set")
        data = work / "data"
        if data.exists():
            shutil.rmtree(data)
        made = export_training_set(db, scope_ids=request.scope_ids, teacher=request.teacher,
                                   held_out_ids=request.held_out_ids, out_dir=data)
        detail["training_set"] = made.summary()
        if vision:
            # Every arm's set is built with the reasons there are, the answer-only one too: `in_every_arm`
            # then keeps both students to the same lines (`distill.reasoning.two-arms`).
            from fichero_server.training.reasons import READ, REVIEW, traces_by_line

            library = str(Path(db.path).parent)
            traces, reviews = traces_by_line(library, READ), traces_by_line(library, REVIEW)
            detail["training_set"]["line_pairs"] = write_line_pairs(
                data, language=request.language, traces=traces, reviews=reviews, max_trace_cer=request.max_trace_cer)
            arms = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
            detail["training_set"].update({k: arms[k] for k in ("arms", "arms_dropped_outside_cer",
                                                                 "max_trace_cer", "lines_in_every_arm")})
            if not arms["arms"].get(request.arm):
                raise EmptyTrainingSet(f"no line in scope has the {request.arm} arm: gather the palaeographer's "
                                       "reasons for the checked lines first (or check its readings, for review)")
            script, args = LORA_TRAINER, lora_args(job_id, base_repo=request.base_repo, epochs=request.epochs,
                                                   rank=request.rank, arm=request.arm, all_lines=request.all_lines)
        else:
            base_file = None
            if request.base:
                base_path = Path(resolve_recognition_model(request.base)[0])
                (data / "base").mkdir()
                shutil.copy2(base_path, data / "base" / base_path.name)
                base_file = base_path.name
            detail["batch_size"] = batch
            script, args = TRAINER, kraken_args(job_id, base_file=base_file, model_name=request.name, batch_size=batch)
        _save(db, job_id, detail, phase="sending",
              reason=f"Sending {counted(len(made.pages), 'page')} ({counted(made.lines, 'line')}) to {there}")
        try:
            target.send(data, job_id)
            far_id = target.submit(job_id, script=script, script_args=args, flavor=flavor, timeout=request.timeout)
        except Exception as exc:
            if cannot_reach(exc):
                raise target.rejected(exc) from exc  # the token, in words, not a failed Job (#5526)
            raise
        detail["far_id"] = far_id
        _save(db, job_id, detail, phase="submitted", reason=f"Sent to {there}" + (f" ({flavor})" if flavor else ""))

    far_id = detail["far_id"]
    while True:
        _state, latest = _row(db, job_id)
        try:
            if latest.get("cancel"):
                if not latest.get("cancel_sent"):
                    target.cancel(far_id)
                detail.update(cancel=True, cancel_sent=True)
                _save(db, job_id, detail, phase="cancelled")
                raise jobs.JobCancelled(CANCELLED_THERE)
            far = target.status(far_id)
        except jobs.JobCancelled:
            raise
        except Exception as exc:
            _out_of_reach_if_running_there(db, job_id, detail, exc)
            raise
        if detail.pop("out_of_reach", None):
            _save(db, job_id, detail)
        if far.state in ("waiting", "running"):
            words = "Queued on" if far.state == "waiting" else "Training on"
            _save(db, job_id, detail, phase="queued" if far.state == "waiting" else "running",
                  reason=f"{words} {there}" + (f" ({flavor})" if flavor else ""))
            sleep(poll)
            continue
        detail["last_lines"] = target.last_lines(far_id)
        if far.state == "cancelled":
            _save(db, job_id, detail, phase="cancelled")
            raise jobs.JobCancelled(f"The Job was cancelled on {there}")
        if far.state == "failed":
            _save(db, job_id, detail, phase="failed")
            tail = " | ".join(detail["last_lines"][-3:])
            why = f"{there}: {far.message or far.stage}" + (f"; last lines: {tail}" if tail else "")
            if batch and ran_out_of_gpu_memory(detail["last_lines"]):  # #5527
                gpu = f"this GPU ({flavor})" if flavor else "this GPU"
                why = f"Too big for {gpu} at batch {batch}: try a smaller batch or a larger GPU. " + why
            raise RuntimeError(why)
        break

    _save(db, job_id, detail, phase="fetching", reason="Bringing the trained model home")
    out = target.fetch(job_id, work / "out")
    ts = detail["training_set"]
    card = {
        "display_name": request.display_name or f"{request.name} (taught by {taught_by(request.teacher)})",
        "summary": (f"{lessons(request.teacher, ts)}; {counted(len(request.held_out_ids), 'page')} held out as the test; "
                    f"{counted(ts.get('lines_left_out', 0), 'flagged line')} left out."),
        "teacher": request.teacher, "training_set": ts, "held_out": ts.get("held_out", []),
        "target": place, "far_id": far_id, "flavor": flavor,
        "not_for_release": request.not_for_release,
        "release_note": request.release_note or (NOT_FOR_RELEASE_NOTE if request.not_for_release else None),
        "project": project_of(db),  # the model shows only in this project's training node (#5483)
    }
    if vision:
        _save(db, job_id, detail, phase="landing", reason="Converting the model for MLX on this Mac")
        hf_build = {"bucket": getattr(target, "bucket", None), "merged": f"{job_id}/out/merged",
                    "adapter": f"{job_id}/out/adapter"}
        model_id = _land_vision(db, job_id, out, request, card, hf_build)
        detail["model_id"] = model_id
    else:
        from fichero_server.training.landing import land_trained_reader

        _save(db, job_id, detail, phase="landing", reason="Adding the reader to this project's models")
        model_id = land_trained_reader(out, job_id=job_id, model_name=request.name, card={**card, "base": request.base},
                                        project=Path(db.path).parent)  # lands inside the project (#5539)
        detail["reader_id"] = model_id
    done = f"Done: {model_id} is ready to read with"
    if hasattr(target, "remove"):  # a cluster: the set's copies stay only where the project said so (#5769)
        from fichero_server.remote_read.job import copies_left

        done += copies_left(db, target, job_id)
    _save(db, job_id, detail, phase="done", reason=done)
    return model_id


def _out_of_reach_if_running_there(db: Any, job_id: str, detail: dict[str, Any], exc: Exception) -> None:
    """This engine cannot reach Hugging Face (no token it can read, or one refused) for a Job that may
    still run there: leave the row running with the reason, never failed (#5449). Anything else is
    for the caller to raise."""
    from fichero_server.training.hf_jobs import cannot_reach, out_of_reach_reason

    if not (_may_run_there(detail) and cannot_reach(exc)):
        return
    reason = out_of_reach_reason(f"its Job ({detail['far_id']})")
    if _row(db, job_id)[1].get("cancel"):  # a stop asked for meanwhile is kept for the engine that can reach it
        detail["cancel"] = True
    detail["out_of_reach"] = {"at": _now(), "why": str(exc)}
    _save(db, job_id, detail, reason=reason)
    raise jobs.JobOutOfReach(reason) from exc


def _land_vision(db: Any, job_id: str, out: Path, request: TrainVisionLoraRequest, card: dict[str, Any],
                 hf_build: dict[str, Any]) -> str:
    """The conversion is heavy local work: it runs on the local ML lane as one job, never beside a
    Kraken page or another model, while this remote job waits for it."""
    from fichero_server.training.mlx_landing import CONVERT_KIND, CONVERT_MODEL, land_vision_student
    from fichero_server.training.vision_bases import licence_of

    licence, licence_note = licence_of(request.base_repo)
    student = {**card, "base": request.base_repo, "base_licence": request.base_licence or licence,
               "base_licence_note": licence_note, "language": request.language, "epochs": request.epochs,
               "rank": request.rank, "arm": request.arm}
    return jobs.run_on_lane_blocking(
        str(Path(db.path).parent), CONVERT_KIND, job_id, model=CONVERT_MODEL,
        fn=lambda: land_vision_student(out, job_id=job_id, name=request.name, card=student, hf_build=hf_build,
                                       keep_merged=request.keep_merged_here, project=Path(db.path).parent))


def register_job_kinds() -> None:
    """Called by the scheduler before its first scan (`execution.jobs._KIND_MODULES`)."""
    from fichero_server.core.background_compute import set_utility_qos
    from fichero_server.training.mlx_landing import CONVERT_KIND

    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="remote",
                           name="Train a model", cancel=request_cancel,
                           # Its row follows one Job on Hugging Face; run again, it would follow that
                           # same ended Job. A new training is started instead (#5356).
                           no_retry="A training on Hugging Face is not retried in place: start a new training")
    if CONVERT_KIND not in jobs.KINDS:
        jobs.register_kind(CONVERT_KIND, None, model=None, qos=set_utility_qos, name="Convert a model for MLX")
