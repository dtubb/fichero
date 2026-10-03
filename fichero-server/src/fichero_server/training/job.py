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

from pydantic import BaseModel, Field

from fichero_server.execution import jobs

KIND = "train-a-model"
TARGET = "huggingface-jobs"
#: How often a running Job is looked at (`compute.job.poll-is-gentle`).
POLL_SECONDS = 60.0
NOT_FOR_RELEASE_NOTE = "No release was recorded for the pages it was trained on; it is not released."


class _TrainRequest(BaseModel):
    """What every training card asks: which pages teach, which teacher, which test."""

    scope_ids: list[str] = Field(description="Folders or pages whose teacher-read lines are the lessons.")
    teacher: str = Field(description="The model whose line readings are the lessons, e.g. google/gemini-3-flash-preview.")
    held_out_ids: list[str] = Field(default_factory=list, description="Pages kept home as the test; never sent.")
    display_name: str | None = None
    pages_may_leave: bool = Field(False, description="The person's yes for these pages to go to Hugging Face.")
    not_for_release: bool = Field(True, description="The trained model may not be released.")
    release_note: str | None = None


class TrainKrakenRequest(_TrainRequest):
    """The Kraken card: a recognition model fine-tuned with `ketos train`."""

    base: str | None = Field(None, description="The Kraken reader to start from (a model id); none trains from nothing.")
    name: str = Field("reader", description="A short name for the trained reader's file.")
    flavor: str = Field("t4-small", description="Hugging Face hardware.")
    timeout: str = Field("4h", description="The Job's time limit; always sent (the service's default is 30 minutes).")


class TrainVisionLoraRequest(_TrainRequest):
    """The vision-model card: a LoRA on a vision-language model, landed on this Mac as MLX 4-bit."""

    base_repo: str = Field("Qwen/Qwen2.5-VL-7B-Instruct", description="The bf16 base on the Hub (the setup card's "
                           "model before MLX quantisation).")
    base_licence: str = Field("Apache-2.0", description="The base's licence, carried on the card.")
    language: str | None = Field(None, description="The pages' language, given to the student as the line reader gives it.")
    name: str = Field("student", description="A short name: the model lands as fichero-trained/<name>.")
    flavor: str | None = Field(None, description="Hugging Face hardware; none chooses the cheapest that fits a 7B LoRA.")
    timeout: str = Field("8h", description="The Job's time limit; always sent.")
    epochs: int = Field(2, ge=1, le=20)
    rank: int = Field(16, ge=2, le=256)


#: The cards a training job can be, by the name its row records.
CARDS: dict[str, type[_TrainRequest]] = {"kraken": TrainKrakenRequest, "vision-lora": TrainVisionLoraRequest}


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
    row = db.execute_fetchone("SELECT state, detail FROM jobs WHERE id = ?", [job_id])
    if row is None:
        raise LookupError(f"no training job {job_id}")
    return row[0], json.loads(row[1] or "{}")


def _save(db: Any, job_id: str, detail: dict[str, Any], *, phase: str | None = None, reason: str | None = None) -> None:
    if phase and detail.get("phase") != phase:
        detail["phase"] = phase
        detail.setdefault("history", []).append({"phase": phase, "at": _now()})
    db.execute("UPDATE jobs SET detail = ?, reason = COALESCE(?, reason) WHERE id = ?",
               [json.dumps(detail), reason, job_id])


def start(db: Any, request: _TrainRequest, *, started_by: str,
          target_factory: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Queue a training job; refuses before anything is queued when it could not run."""
    from fichero_server.llm.kraken_runtime import resolve_recognition_model
    from fichero_server.training.hf_jobs import LORA_FLAVORS, HfJobsTarget

    if not request.pages_may_leave:
        raise PagesMayNotLeave("Training on Hugging Face sends this project's pages there. "
                               "Say yes for this project first (pages_may_leave).")
    if not request.scope_ids:
        raise ValueError("name the folders or pages to train on")
    if isinstance(request, TrainKrakenRequest) and request.base:
        resolve_recognition_model(request.base)  # not installed: refused here, by name
    target = (target_factory or HfJobsTarget)()  # no token: refused here, by name
    flavor = request.flavor or target.cheapest(LORA_FLAVORS)
    price = target.price_per_hour(flavor)
    detail = {"card": _card_of(request), "request": request.model_dump(), "flavor": flavor,
              "price_per_hour_usd": price, "yes": {"by": started_by, "at": _now(), "to": TARGET},
              "phase": "waiting", "history": [{"phase": "waiting", "at": _now()}]}
    job_id = jobs.enqueue_remote(db, KIND, f"training:{uuid.uuid4()}", target=TARGET, detail=json.dumps(detail),
                                 reason="Waiting to send to Hugging Face", started_by=started_by)
    return {"job_id": job_id, "flavor": flavor, "timeout": request.timeout, "price_per_hour_usd": price}


def request_cancel(db: Any, job_id: str) -> str:
    """Stop a training job: one not started yet ends now; a running one is cancelled on Hugging Face
    at its next look. Returns the row's state after the request."""
    state, detail = _row(db, job_id)
    if state == "waiting":
        db.execute("UPDATE jobs SET state = 'cancelled', reason = 'Stopped by you', finished_at = ? "
                   "WHERE id = ? AND state = 'waiting'", [datetime.now(timezone.utc), job_id])
        return "cancelled"
    if state == "running":
        detail["cancel"] = True
        _save(db, job_id, detail, reason="Stopping: cancelling the Job on Hugging Face")
    return state


def status(db: Any, job_id: str) -> dict[str, Any]:
    state, detail = _row(db, job_id)
    reason = db.execute_fetchone("SELECT reason FROM jobs WHERE id = ?", [job_id])[0]
    return {"job_id": job_id, "state": state, "reason": reason, **detail}


def _job_id_for(db: Any, subject: str) -> str:
    return db.execute_fetchone("SELECT id FROM jobs WHERE kind = ? AND subject = ?", [KIND, subject])[0]


def run(db: Any, subject: str, *, target: Any | None = None, sleep: Callable[[float], None] = time.sleep,
        poll_seconds: float | None = None) -> str:
    """Carry a training job through its phases; returns the landed model's id."""
    from fichero_server.llm.kraken_runtime import resolve_recognition_model
    from fichero_server.training.hf_jobs import LORA_TRAINER, TRAINER, HfJobsTarget, kraken_args, lora_args
    from fichero_server.training.kraken_set import export_training_set
    from fichero_server.training.line_pairs import write_line_pairs

    job_id = _job_id_for(db, subject)
    _state, detail = _row(db, job_id)
    card_name = detail.get("card", "kraken")
    request = CARDS[card_name](**detail["request"])
    vision = isinstance(request, TrainVisionLoraRequest)
    flavor = detail.get("flavor") or request.flavor
    target = target or HfJobsTarget()
    work = _work_dir(job_id)
    poll = POLL_SECONDS if poll_seconds is None else poll_seconds

    if not detail.get("far_id"):
        _save(db, job_id, detail, phase="preparing", reason="Preparing the training set")
        data = work / "data"
        if data.exists():
            shutil.rmtree(data)
        made = export_training_set(db, scope_ids=request.scope_ids, teacher=request.teacher,
                                   held_out_ids=request.held_out_ids, out_dir=data)
        detail["training_set"] = {k: v for k, v in made.manifest().items() if k != "pages"} | {"pages": len(made.pages)}
        if vision:
            detail["training_set"]["line_pairs"] = write_line_pairs(data, language=request.language)
            script, args = LORA_TRAINER, lora_args(job_id, base_repo=request.base_repo, epochs=request.epochs,
                                                   rank=request.rank)
        else:
            base_file = None
            if request.base:
                base_path = Path(resolve_recognition_model(request.base)[0])
                (data / "base").mkdir()
                shutil.copy2(base_path, data / "base" / base_path.name)
                base_file = base_path.name
            script, args = TRAINER, kraken_args(job_id, base_file=base_file, model_name=request.name)
        _save(db, job_id, detail, phase="sending",
              reason=f"Sending {len(made.pages)} pages ({made.lines} lines) to Hugging Face")
        target.send(data, job_id)
        far_id = target.submit(job_id, script=script, script_args=args, flavor=flavor, timeout=request.timeout)
        detail["far_id"] = far_id
        _save(db, job_id, detail, phase="submitted", reason=f"Sent to Hugging Face ({flavor})")

    far_id = detail["far_id"]
    while True:
        _state, latest = _row(db, job_id)
        if latest.get("cancel"):
            target.cancel(far_id)
            detail["cancel"] = True
            _save(db, job_id, detail, phase="cancelled")
            raise jobs.JobCancelled("Stopped by you; the Job on Hugging Face was cancelled")
        far = target.status(far_id)
        if far.state in ("waiting", "running"):
            words = "Queued on" if far.state == "waiting" else "Training on"
            _save(db, job_id, detail, phase="queued" if far.state == "waiting" else "running",
                  reason=f"{words} Hugging Face ({flavor})")
            sleep(poll)
            continue
        detail["last_lines"] = target.last_lines(far_id)
        if far.state == "cancelled":
            _save(db, job_id, detail, phase="cancelled")
            raise jobs.JobCancelled("The Job was cancelled on Hugging Face")
        if far.state == "failed":
            _save(db, job_id, detail, phase="failed")
            tail = " | ".join(detail["last_lines"][-3:])
            raise RuntimeError(f"Hugging Face: {far.message or far.stage}" + (f"; last lines: {tail}" if tail else ""))
        break

    _save(db, job_id, detail, phase="fetching", reason="Bringing the trained model home")
    out = target.fetch(job_id, work / "out")
    ts = detail["training_set"]
    card = {
        "display_name": request.display_name or f"{request.name} (taught by {request.teacher})",
        "summary": (f"Taught by {request.teacher} on {ts['pages']} pages ({ts['lines']} lines, none checked "
                    f"by a person); {len(request.held_out_ids)} pages held out as the test."),
        "teacher": request.teacher, "training_set": ts, "held_out": ts.get("held_out", []),
        "target": TARGET, "far_id": far_id, "flavor": flavor,
        "not_for_release": request.not_for_release,
        "release_note": request.release_note or (NOT_FOR_RELEASE_NOTE if request.not_for_release else None),
    }
    if vision:
        _save(db, job_id, detail, phase="landing", reason="Converting the model for MLX on this Mac")
        model_id = _land_vision(db, job_id, out, request, card)
        detail["model_id"] = model_id
    else:
        from fichero_server.training.landing import land_trained_reader

        _save(db, job_id, detail, phase="landing", reason="Adding the reader to this Mac's Kraken readers")
        model_id = land_trained_reader(out, job_id=job_id, model_name=request.name, card={**card, "base": request.base})
        detail["reader_id"] = model_id
    _save(db, job_id, detail, phase="done", reason=f"Done: {model_id} is ready to read with")
    return model_id


def _land_vision(db: Any, job_id: str, out: Path, request: TrainVisionLoraRequest, card: dict[str, Any]) -> str:
    """The conversion is heavy local work: it runs on the local ML lane as one job, never beside a
    Kraken page or another model, while this remote job waits for it."""
    from fichero_server.training.mlx_landing import CONVERT_KIND, CONVERT_MODEL, land_vision_student

    student = {**card, "base": request.base_repo, "base_licence": request.base_licence,
               "language": request.language, "epochs": request.epochs, "rank": request.rank}
    return jobs.run_on_lane_blocking(
        str(Path(db.path).parent), CONVERT_KIND, job_id, model=CONVERT_MODEL,
        fn=lambda: land_vision_student(out, job_id=job_id, name=request.name, card=student))


def register_job_kinds() -> None:
    """Called by the scheduler before its first scan (`execution.jobs._KIND_MODULES`)."""
    from fichero_server.core.background_compute import set_utility_qos
    from fichero_server.training.mlx_landing import CONVERT_KIND

    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="remote",
                           name="Train a model")
    if CONVERT_KIND not in jobs.KINDS:
        jobs.register_kind(CONVERT_KIND, None, model=None, qos=set_utility_qos, name="Convert a model for MLX")
