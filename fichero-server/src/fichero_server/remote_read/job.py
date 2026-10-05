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
#: A vision-model reader needs these where the Job runs (the runner's own header has Kraken).
VLM_DEPENDENCIES = ["torch>=2.5", "transformers>=4.57,<5", "accelerate>=1.3"]


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


def _save(db: Any, job_id: str, detail: dict[str, Any], reason: str | None = None, *, keep_cancel: bool = True) -> None:
    """Write the run's detail. A stop the person asked for meanwhile is kept, not saved over."""
    if keep_cancel and _row(db, job_id)[1].get("cancel"):
        detail["cancel"] = True
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
    ReadStep(reader="vlm", card=request.card, model=model)  # the same refusals as the package
    return {"reader": "vlm", "card": request.card, "model": model, "prompt": prompt_for(1, request.language),
            "lines_per_call": 1, "language": request.language}


def start(db: Any, request: ReadAtScaleRequest, *, started_by: str,
          target_factory: Callable[[], Any] | None = None) -> dict[str, Any]:
    from fichero_server.training.hf_jobs import HfJobsTarget

    if not request.pages_may_leave:
        raise PagesMayNotLeave("Reading on Hugging Face sends these pages (or their IIIF addresses) there. "
                               "Say yes for this project first (pages_may_leave).")
    if not request.scope_ids:
        raise ValueError("name the folders or pages to read")
    target = (target_factory or HfJobsTarget)()  # no token: refused here, by name
    step = resolve_step(request, bucket=getattr(target, "bucket", None))
    detail = {"request": request.model_dump(), "step": step, "flavor": request.flavor,
              "price_per_hour_usd": target.price_per_hour(request.flavor),
              "yes": {"by": started_by, "at": _now(), "to": TARGET}, "phase": "waiting"}
    job_id = jobs.enqueue_remote(db, KIND, f"read:{uuid.uuid4()}", target=TARGET, detail=json.dumps(detail),
                                 reason="Waiting to send to Hugging Face", started_by=started_by)
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
            target = HfJobsTarget()
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
                dependencies=VLM_DEPENDENCIES if detail["step"]["reader"] == "vlm" else None,
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
                shard.update(state="landed", landed=result)
            else:
                shard.update(state="failed", why=f"Hugging Face: {far.message or far.stage}",
                             last_lines=target.last_lines(shard["far_id"])[-5:])
        counts = _counts(shards)
        _save(db, job_id, detail, reason=_words(counts, total))
        if counts["pending"] == 0 and counts["submitted"] == 0:
            break
        sleep(poll)
    counts = _counts(shards)
    words = f"Done: {counts['landed']} of {total} shards landed, {detail['landing']['landed']} pages read"
    if counts["failed"]:
        words += f"; {counts['failed']} shards failed (re-send them)"
    _save(db, job_id, detail, reason=words)
    return counts


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


def status(db: Any, job_id: str) -> dict[str, Any]:
    state, detail = _row(db, job_id)
    from fichero_server.execution import jobs

    reason = (jobs.read_job(db, job_id) or {}).get("reason")
    shards = detail.pop("shards", {}) or {}
    failed = {k: {"why": s.get("why"), "last_lines": s.get("last_lines")} for k, s in shards.items() if s["state"] == "failed"}
    return {"job_id": job_id, "state": state, "reason": reason, "counts": _counts(shards), "failed_shards": failed,
            **{k: v for k, v in detail.items() if k in ("package", "landing", "flavor", "price_per_hour_usd", "step")}}


def register_job_kinds() -> None:
    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="remote", name="Read at scale")
