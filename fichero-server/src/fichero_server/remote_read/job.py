"""Reading at scale off the Mac: one job row, many shards on Hugging Face Jobs (#5398 slice 2).

`compute.job.one-state-machine`, `.array-by-shard`, `.sparse-resubmit`, `.poll-is-gentle`,
`compute.land.*`. A run over 100k pages is ONE row in the jobs table (kind `read-at-scale`, lane
`remote`); its detail holds every shard's state:

    pending -> submitted (the Job's id) -> landed | failed (with the reason and the Job's last lines)

The package is made and sent once. At most `max_in_flight` shards run at a time; all of them are
looked at with ONE call per round (`HfJobsTarget.statuses`). A finished shard's results come home and
land at once, through Fichero's own PAGE import, as a new pass on each page: never over an existing
one, and a page whose results already landed is not landed again (`compute.land.idempotent`). The run is
done only when every shard has landed or failed (`compute.land.completed-means-landed`); failed shards
are re-sent only when a person asks (`resend_failed`), and only those.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


from fichero_server.execution import jobs
from fichero_server.models.compute_requests import ReadAtScaleRequest  # noqa: F401  (re-exported)

KIND = "read-at-scale"
TARGET = "huggingface-jobs"
POLL_SECONDS = 60.0
#: The jobs a remote run may hang under: a recipe run, a workflow run or a step of one (`activity.jobs-are-a-tree`).
STEP_KINDS = ("run-a-recipe", "workflow", "workflow-step", "batch", "recipe")
#: A vision-model reader needs these where the Job runs (the runner's own header has Kraken).
VLM_DEPENDENCIES = ["torch>=2.5", "transformers>=4.57,<5", "accelerate>=1.3"]
#: Added for a step that puts a PEFT adapter on its base model (#5977); other steps do not install it.
ADAPTER_DEPENDENCIES = ["peft>=0.14"]


def dependencies_for(step: dict[str, Any]) -> list[str] | None:
    """What the Job installs for this step: nothing for Kraken (the image has it), the vision-model set for a vlm,
    and `peft` besides for one with an adapter."""
    if step["reader"] != "vlm":
        return None
    return [*VLM_DEPENDENCIES, *(ADAPTER_DEPENDENCIES if step.get("adapter") else [])]


class PagesMayNotLeave(PermissionError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _work_dir(job_id: str) -> Path:
    from fichero_server.db.paths import server_state_dir

    return server_state_dir() / "remote-read" / job_id


def _row(db: Any, job_id: str) -> tuple[str, dict[str, Any]]:
    from fichero_server.execution import jobs

    row = jobs.read_job(db, job_id)
    if row is None:
        raise LookupError(f"no reading job {job_id}")
    return row["state"], json.loads(row["detail"] or "{}")


def _save(db: Any, job_id: str, detail: dict[str, Any], reason: str | None = None, *, keep_cancel: bool = True,
          keep_catch_up: bool = True) -> None:
    """Write the run's detail. A stop (or a catch-up) the person asked for meanwhile is kept, not saved over."""
    latest = _row(db, job_id)[1]
    if keep_cancel and latest.get("cancel"):
        detail["cancel"] = True
    if keep_catch_up and latest.get("catch_up"):
        detail["catch_up"] = True
    from fichero_server.execution import jobs

    jobs.save_detail(db, job_id, json.dumps(detail), reason=reason)


def resolve_step(request: ReadAtScaleRequest, *, bucket: str | None) -> dict[str, Any]:
    """The reading step, from the card: a Kraken reader's file here, or where the Job finds a vision
    model's Hugging Face weights. Refused by name when the card cannot be read off this Mac."""
    from fichero_server.llm.line_reader import prompt_for
    from fichero_server.remote_read.package import NotSendable, ReadStep

    if request.reader == "kraken":
        from fichero_server.llm.kraken_runtime import resolve_recognition_model

        path, _ = resolve_recognition_model(request.card)
        return {"reader": "kraken", "card": request.card, "model_file": path}
    if request.reader != "vlm":
        raise NotSendable(f"no reader {request.reader!r}: kraken or vlm")
    model = request.card
    if request.card.startswith("fichero-trained/"):
        from fichero_server.llm.mlx_model_store import get_mlx_model_store
        from fichero_server.training.hf_jobs import MOUNT

        hf = ((get_mlx_model_store().trained_card(request.card) or {}).get("builds") or {}).get("hf") or {}
        if not hf.get("merged") or hf.get("bucket") != bucket:
            raise NotSendable(f"{request.card} has no Hugging Face build in your bucket to read with off this Mac")
        model = f"{MOUNT}/{hf['merged']}"
    adapter = None
    if request.base_model:  # the card is a PEFT adapter: the base is the model, the adapter goes on it (#5977)
        adapter, model = request.card, request.base_model
    ReadStep(reader="vlm", card=request.card, model=model, adapter=adapter)  # the same refusals as the package
    return {"reader": "vlm", "card": request.card, "model": model, "prompt": prompt_for(1, request.language),
            "lines_per_call": 1, "language": request.language, **({"adapter": adapter} if adapter else {})}


def cluster_target(cluster_id: str) -> Callable[[], Any]:
    """The target for a Slurm cluster. ponytail: the Keychain key and the MFA prompt passed through the app
    (#5238) are not built, so a cluster is refused by name here; tests and the live run inject the target."""
    from fichero_server.remote_read.slurm_target import NoKey

    def refuse() -> Any:
        raise NoKey(f"cluster {cluster_id}: the app's key and sign-in step are not built yet (#5238)")

    return refuse


def start(db: Any, request: ReadAtScaleRequest, *, started_by: str,
          target_factory: Callable[[], Any] | None = None) -> dict[str, Any]:
    from fichero_server.training.hf_jobs import HfJobsTarget

    if not request.pages_may_leave:
        where = "Hugging Face" if request.target == TARGET else f"the cluster {request.target}"
        raise PagesMayNotLeave(f"Reading on {where} sends these pages (or their IIIF addresses) there. "
                               "Say yes for this project first (pages_may_leave).")
    from fichero_server.recipes import places

    if (no := places.refusal("huggingface" if request.target == TARGET else "acenet")):
        raise PagesMayNotLeave(no)  # the app's places cap the request's yes (#5831)
    if not request.scope_ids:
        raise ValueError("name the folders or pages to read")
    if request.parent_job_id:
        parent = jobs.read_job(db, request.parent_job_id)
        if parent is None or parent["kind"] not in STEP_KINDS:
            raise ValueError(f"parent_job_id {request.parent_job_id!r} is not a step job of this library")
    target = (target_factory or (HfJobsTarget if request.target == TARGET else cluster_target(request.target)))()
    # no token (or key): refused here, by name
    step = resolve_step(request, bucket=getattr(target, "bucket", None))
    detail = {"request": request.model_dump(), "step": step, "flavor": request.flavor,
              "price_per_hour_usd": target.price_per_hour(request.flavor),
              "yes": {"by": started_by, "at": _now(), "to": request.target}, "phase": "waiting"}
    job_id = jobs.enqueue_remote(db, KIND, f"read:{uuid.uuid4()}", target=request.target, detail=json.dumps(detail),
                                 reason="Waiting to send to Hugging Face" if request.target == TARGET else "Waiting to send to the cluster",
                                 started_by=started_by)
    if request.parent_job_id:
        jobs.set_parent(db, job_id, request.parent_job_id)  # under the step that sent it
    return {"job_id": job_id, "flavor": request.flavor, "price_per_hour_usd": detail["price_per_hour_usd"]}


def _counts(shards: dict[str, dict[str, Any]]) -> dict[str, int]:
    out = {"pending": 0, "submitted": 0, "landed": 0, "failed": 0}
    for shard in shards.values():
        out[shard["state"]] = out.get(shard["state"], 0) + 1
    return out


def _words(counts: dict[str, int], total: int) -> str:
    return (f"Reading on Hugging Face: {counts['landed']} of {total} shards landed, "
            f"{counts['submitted']} running, {counts['failed']} failed")


def land_shard(db: Any, job_id: str, folder: Path, *, pass_name: str, actor: str) -> dict[str, int]:
    """Land one shard's PAGE files as new passes through `format.import`. A page whose file already
    landed is counted, not landed again; a page that no longer exists is set aside, not an error."""
    from fastapi import HTTPException

    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.api.routes.document.format_import import existing_import, file_checksum
    import fichero_server.api.routes.document.format_import  # noqa: F401  (registers format.import)

    outcome = json.loads((folder / "_outcome.json").read_text(encoding="utf-8"))
    ctx = ActionContext(actor=actor, library_path=str(Path(db.path).parent), run_id=job_id)
    counts = {"landed": 0, "already": 0, "unread": 0, "set_aside": 0}
    for source_id, result in sorted(outcome.get("sources", {}).items()):
        if not result.get("ok"):
            counts["unread"] += 1
            continue
        xml = folder / f"{source_id}.xml"
        if existing_import(db, source_id, file_checksum(xml.read_bytes())) is not None:
            counts["already"] += 1
            continue
        try:
            registry.invoke(db, "format.import", {"document_id": source_id, "path": str(xml), "name": pass_name}, ctx)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            counts["set_aside"] += 1  # its page was deleted while the job ran (`compute.land.orphans-set-aside`)
            continue
        counts["landed"] += 1
    return counts


def run(db: Any, subject: str, *, target: Any | None = None, sleep: Callable[[float], None] = time.sleep,
        poll_seconds: float | None = None, land: Callable[..., dict[str, int]] = land_shard,
        build: Callable[..., Any] | None = None) -> dict[str, int]:
    from fichero_server.remote_read.package import RUNNER, ReadStep, build_read_package
    from fichero_server.training.hf_jobs import HfJobsTarget, job_root

    from fichero_server.execution import jobs

    job_id = jobs.job_id_for(db, KIND, subject)
    _state, detail = _row(db, job_id)
    request = ReadAtScaleRequest(**detail["request"])
    if target is None:
        try:
            target = HfJobsTarget() if request.target == TARGET else cluster_target(request.target)()
        except Exception as exc:
            _out_of_reach_if_running_there(db, job_id, detail, exc)
            raise
    work = _work_dir(job_id)
    poll = POLL_SECONDS if poll_seconds is None else poll_seconds
    started_by = (jobs.read_job(db, job_id) or {}).get("started_by") or "owner"
    pass_name = request.pass_name or f"Read at scale ({request.card})"

    if "shards" not in detail:
        step = detail["step"]
        made = (build or build_read_package)(
            db, job_id=job_id, scope_ids=request.scope_ids, out_dir=work / "pkg", shard_size=request.shard_size,
            longest=request.longest, library_root=Path(db.path).parent,
            step=ReadStep(**{k: v for k, v in step.items() if k in ReadStep.__dataclass_fields__}))
        detail["package"] = {"sources": len(made.sources), "shards": len(made.shards), "skipped": made.skipped}
        detail["estimate"] = {"pages": len(made.sources), "shards": len(made.shards),
                              "gpu_hours": (len(made.sources) / request.expected_pages_per_second / 3600
                                            if request.expected_pages_per_second else None)}
        _save(db, job_id, detail, reason=f"Sending {len(made.sources)} pages in {len(made.shards)} shards")
        target.send(work / "pkg", job_id)
        detail["shards"] = {str(i): {"state": "pending", "tries": 0} for i in range(len(made.shards))}
        detail["landing"] = {"landed": 0, "already": 0, "unread": 0, "set_aside": 0}
        _save(db, job_id, detail)

    shards: dict[str, dict[str, Any]] = detail["shards"]
    root = job_root(job_id)
    total = len(shards)
    while True:
        _state, latest = _row(db, job_id)
        if latest.get("cancel"):
            for shard in shards.values():
                if shard["state"] == "submitted":
                    target.cancel(shard["far_id"])
                    shard.update(state="failed", why="Stopped by you")
            _save(db, job_id, detail)
            raise jobs.JobCancelled("Stopped by you; the running shards were cancelled on Hugging Face")
        running = sum(1 for s in shards.values() if s["state"] == "submitted")
        for key in sorted((k for k, s in shards.items() if s["state"] == "pending"), key=int):
            if running >= request.max_in_flight:
                break
            far_id = target.submit(
                job_id, script=RUNNER, flavor=request.flavor, timeout=request.timeout,
                script_args=["--package", f"{root}/data", "--shard", key, "--out", f"{root}/out"],
                dependencies=dependencies_for(detail["step"]),
                labels={"fichero-shard": key})
            shards[key].update(state="submitted", far_id=far_id, tries=shards[key]["tries"] + 1)
            running += 1
        _save(db, job_id, detail, reason=_words(_counts(shards), total))
        try:
            seen = target.statuses(job_id)  # ONE call for every shard
        except Exception as exc:
            _out_of_reach_if_running_there(db, job_id, detail, exc)
            raise
        detail.pop("out_of_reach", None)
        for key, shard in shards.items():
            if shard["state"] != "submitted":
                continue
            far = seen.get(shard["far_id"]) or target.status(shard["far_id"])  # not listed: asked by id
            if far.state in ("waiting", "running"):
                continue
            if far.state == "done":
                part = f"shard-{int(key):05d}"
                folder = target.fetch_part(job_id, part, work / "out" / part)
                result = land(db, job_id, folder, pass_name=pass_name, actor=started_by)
                for name, value in result.items():
                    detail["landing"][name] = detail["landing"].get(name, 0) + value
                shard.update(state="landed", landed=result, seconds=_shard_seconds(folder))
            else:
                shard.update(state="failed", why=f"Hugging Face: {far.message or far.stage}",
                             last_lines=target.last_lines(shard["far_id"])[-5:])
        counts = _counts(shards)
        _save(db, job_id, detail, reason=_words(counts, total))
        if counts["pending"] == 0 and counts["submitted"] == 0:
            break
        if _row(db, job_id)[1].get("catch_up"):  # asked to look now (after the Mac slept): skip this wait, once
            detail.pop("catch_up", None)
            _save(db, job_id, detail, keep_catch_up=False)
            continue
        sleep(poll)
    counts = _counts(shards)
    words = f"Done: {counts['landed']} of {total} shards landed, {detail['landing']['landed']} pages read"
    if counts["failed"]:
        words += f"; {counts['failed']} shards failed (re-send them)"
    elif hasattr(target, "remove"):  # a cluster; Hugging Face keeps nothing of a finished Job
        words += copies_left(db, target, job_id)
    detail.pop("catch_up", None)  # a request made as the run ended has nothing left to hurry
    _save(db, job_id, detail, reason=words, keep_catch_up=False)
    return counts


def copies_left(db: Any, target: Any, job_id: str) -> str:
    """`source.onboard.copies-may-stay-on-cluster`: the run's working copies stay for re-runs only when the project
    said so; otherwise they leave once every shard has landed (with failed shards they wait for the re-send)."""
    from fichero_server.recipes.answers import copies_may_stay
    from fichero_server.recipes.project import read_project_setup

    if copies_may_stay(read_project_setup(Path(db.path).parent)["answers"]):
        return "; the working copies stay on the cluster for re-runs"
    try:
        target.remove(job_id)
    except Exception as exc:  # the pages are read and home; a folder left behind is said, not a failed run
        return f"; the working copies could not be removed from the cluster ({exc})"
    return "; the working copies were removed from the cluster"


def _out_of_reach_if_running_there(db: Any, job_id: str, detail: dict[str, Any], exc: Exception) -> None:
    """This engine cannot reach Hugging Face for shards that may still run there: the row stays
    running with the reason, never failed (#5449). Anything else is for the caller to raise."""
    from fichero_server.training.hf_jobs import cannot_reach, out_of_reach_reason

    submitted = [s for s in (detail.get("shards") or {}).values() if s.get("state") == "submitted"]
    if not (submitted and cannot_reach(exc)):
        return
    reason = out_of_reach_reason(f"its {len(submitted)} shards sent there")
    detail["out_of_reach"] = {"at": datetime.now(timezone.utc).isoformat(), "why": str(exc)}
    _save(db, job_id, detail, reason=reason)
    raise jobs.JobOutOfReach(reason) from exc


def resend_failed(db: Any, job_id: str) -> int:
    """Send the failed shards again, and only those (`compute.job.sparse-resubmit`); returns how many."""
    state, detail = _row(db, job_id)
    if state in ("waiting", "running"):
        raise ValueError("the job is still running; its failed shards are re-sent when it ends")
    failed = [k for k, s in (detail.get("shards") or {}).items() if s["state"] == "failed"]
    for key in failed:
        detail["shards"][key].update(state="pending", why=None)
    detail.pop("cancel", None)
    _save(db, job_id, detail, keep_cancel=False)
    if failed:
        jobs.requeue(db, job_id, reason=f"Re-sending {len(failed)} failed shards")
    return len(failed)


def request_cancel(db: Any, job_id: str) -> str:
    state, detail = _row(db, job_id)
    if state == "waiting":
        from fichero_server.execution import jobs

        jobs.cancel_waiting(db, job_id)
        return "cancelled"
    if state == "running":
        detail["cancel"] = True
        _save(db, job_id, detail, reason="Stopping: cancelling the running shards on Hugging Face")
    return state


def _shard_seconds(folder: Path) -> float | None:
    """How long the shard took where it ran: the runner's own record, kept for the estimate against the actual."""
    try:
        return float(json.loads((Path(folder) / "_outcome.json").read_text(encoding="utf-8")).get("seconds"))
    except (OSError, ValueError, TypeError):
        return None


def far_state(status: dict[str, Any]) -> str:
    """Where the run is, in words, on the far side (`activity.remote-under-its-step`): queued, running, done, failed."""
    counts = status["counts"]
    if counts.get("submitted"):
        return "running"
    if counts.get("pending"):
        return "queued"
    if counts.get("failed"):
        return "failed"
    return "done" if counts.get("landed") else "queued"


def remote_row(status: dict[str, Any]) -> dict[str, Any]:
    """What Activity's row shows for a remote run, and what it offers (Cancel, Retry failed shards, Catch up)."""
    state = far_state(status)
    done, total = status.get("shards_done", status["counts"].get("landed", 0)), status.get("shards_total") or sum(
        status["counts"].values())
    offers = {"queued": ["Cancel", "Catch up"], "running": ["Cancel", "Catch up"], "failed": ["Retry failed shards"]}
    return {"target": status.get("target"), "far_state": state, "shards": f"{done} of {total} shards",
            "pages_landed": status.get("pages_landed", 0), "offers": offers.get(state, [])}


def catch_up(db: Any, job_id: str) -> str:
    """After the Mac slept: look at the far side now. A live run skips its next wait; a run the scheduler dropped
    (paused, failed with shards still out) is queued again and carries on from its recorded shards."""
    state, detail = _row(db, job_id)
    if state in ("running", "waiting"):
        detail["catch_up"] = True
        _save(db, job_id, detail)
        return state
    out = any(sh.get("state") == "submitted" for sh in (detail.get("shards") or {}).values())
    if not (state == "paused" or (state == "failed" and out)):
        # a finished run is never brought back: resending it would be billed again
        raise ValueError(f"nothing to catch up with: the run is {state} and has no shard still out")
    jobs.requeue(db, job_id, reason="Catching up with the far side")
    return "waiting"


def status(db: Any, job_id: str) -> dict[str, Any]:
    state, detail = _row(db, job_id)
    from fichero_server.execution import jobs

    reason = (jobs.read_job(db, job_id) or {}).get("reason")
    shards = detail.pop("shards", {}) or {}
    counts = _counts(shards)
    failed = {k: {"why": s.get("why"), "last_lines": s.get("last_lines")} for k, s in shards.items() if s["state"] == "failed"}
    seconds = [s["seconds"] for s in shards.values() if s.get("seconds") is not None]
    out = {"job_id": job_id, "state": state, "reason": reason, "counts": counts, "failed_shards": failed,
           "target": (detail.get("request") or {}).get("target", TARGET),
           "shards_done": counts["landed"], "shards_total": sum(counts.values()),
           "pages_landed": (detail.get("landing") or {}).get("landed", 0),
           "shards": [{"shard": int(k), "state": s["state"], "far_id": s.get("far_id"), "tries": s.get("tries", 0),
                       "why": s.get("why"), "last_lines": s.get("last_lines"), "seconds": s.get("seconds")}
                      for k, s in sorted(shards.items(), key=lambda kv: int(kv[0]))],
           "estimate": detail.get("estimate"),
           "actual": {"seconds_per_shard": sum(seconds) / len(seconds) if seconds else None,
                      "gpu_hours": sum(seconds) / 3600 if seconds else None},
           **{k: v for k, v in detail.items() if k in ("package", "landing", "flavor", "price_per_hour_usd", "step")}}
    out["far_state"] = far_state(out)
    out["hf_spend"] = _hf_spend(db) if out["target"] == TARGET else None
    return out


def _hf_spend(db: Any) -> dict[str, Any]:
    """This month's Hugging Face spend against the project's cap, for the run's Inspector (`source.onboard.spend-cap`)."""
    from fichero_server.recipes.answers import spend_cap
    from fichero_server.recipes.project import read_project_setup
    from fichero_server.recipes.train_offers import spend_this_month

    return spend_this_month(db, cap=spend_cap(read_project_setup(Path(db.path).parent)["answers"]))


def register_job_kinds() -> None:
    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="remote", name="Read at scale",
                           cancel=request_cancel)  # Stop on its row cancels the running shards (#5356)
