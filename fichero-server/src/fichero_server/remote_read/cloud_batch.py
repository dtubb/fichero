"""A recipe step sent as a provider batch: ONE `cloud-batch` row under the step (#5940, spec compute/recipe-steps-at-scale.md).

`compute.recipe.cloud-batch-*`. The step's own vision calls are captured (`provider_batch.capturing`, nothing is called
or kept), the ones not answered before (the run's `answers.jsonl`, #6127) are cut to the provider's cap and submitted;
each batch's ids are on the row the moment the provider acknowledges them, so a restart adopts them and never submits
again. The row polls gently (a minute, backing off to five), keeps every answered line as it lands, and ends when every
batch has; the recipe then runs the step once more under `provider_batch.answering`, so each page lands through the
step's own path, and a line that failed goes as a plain call there. Stop cancels at the provider, polls each batch to
its end and keeps what was answered (it was billed) before the row reads Stopped (`ai.where.batch-stop-reaches-the-provider`).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from fichero_server.execution import jobs
from fichero_server.llm import provider_batch as pb

KIND = "cloud-batch"
POLL_FIRST, POLL_MOST = 60.0, 300.0


def _work_dir(job_id: str) -> Path:
    from fichero_server.db.paths import server_state_dir

    return server_state_dir() / "cloud-batch" / job_id


def _detail(db: Any, job_id: str) -> dict[str, Any]:
    row = jobs.read_job(db, job_id)
    if row is None:
        raise LookupError(f"no batch run {job_id}")
    return json.loads(row["detail"] or "{}")


def _save(db: Any, job_id: str, detail: dict[str, Any], reason: str | None = None) -> None:
    if _detail(db, job_id).get("cancel"):  # a Stop asked meanwhile is kept, never saved over
        detail["cancel"] = True
    jobs.save_detail(db, job_id, json.dumps(detail), reason=reason)


def book_for(job_id: str) -> pb.AnswerBook:
    return pb.AnswerBook(_work_dir(job_id) / "answers.jsonl")


def run(db: Any, subject: str, *, client: Any, capture: Callable[[Any, dict[str, Any]], list[pb.BatchRequest]],
        sleep: Callable[[float], None] = time.sleep) -> dict[str, int]:
    """Submit what is still to answer (or adopt what is out), poll to the end, keep the answers. {answered, failed}."""
    job_id = jobs.job_id_for(db, KIND, subject)
    detail = _detail(db, job_id)
    book = book_for(job_id)
    who = client.name
    if not detail.get("batches"):
        to_send = book.still_to_send(capture(db, detail))
        detail["batches"] = []
        for chunk in pb.cut_to_cap(to_send, cap_bytes=client.cap_bytes):
            ids = client.submit(detail["model"], chunk, max_tokens=detail["max_tokens"])
            detail["batches"].append({"ids": ids, "state": "open", "requests": len(chunk)})
            _save(db, job_id, detail, reason=f"Sent as a batch to {who}: {sum(b['requests'] for b in detail['batches'])} "
                                              "requests, answered within a day")  # on the row before anything else
    counts = {"answered": 0, "failed": 0}
    wait, stopping = POLL_FIRST, False
    while any(b["state"] == "open" for b in detail["batches"]):
        if not stopping and _detail(db, job_id).get("cancel"):
            stopping = True
            for batch in detail["batches"]:
                if batch["state"] == "open":
                    client.cancel(batch["ids"])
        for batch in detail["batches"]:
            if batch["state"] != "open":
                continue
            seen = client.poll(batch["ids"])
            if seen["state"] == "open":
                continue
            if seen["state"] == "gone":  # past the provider's retention: its unanswered pages are asked again
                batch["state"] = "gone"
                continue
            lines = client.lines(batch["ids"])
            book.keep(lines)
            batch.update(state="ended", answered=sum(line.ok for line in lines),
                         failed=sum(not line.ok for line in lines), why=seen.get("why"))
        counts = {"answered": sum(b.get("answered", 0) for b in detail["batches"]),
                  "failed": sum(b.get("failed", 0) for b in detail["batches"])}
        open_ = sum(b["state"] == "open" for b in detail["batches"])
        _save(db, job_id, detail, reason=(f"{'Stopping' if stopping else 'Sent as a batch'} to {who}: "
                                          f"{counts['answered']} answered, {counts['failed']} failed, {open_} batches out"))
        if open_:
            sleep(wait)
            wait = min(wait * 2, POLL_MOST)
    words = f"{who} answered {counts['answered']}, {counts['failed']} failed (asked again as plain calls)"
    if stopping:
        _save(db, job_id, detail, reason=f"Stopped: {words}; nothing answered is lost")
        raise jobs.JobCancelled(f"Stopped: {words}; nothing answered is lost")
    _save(db, job_id, detail, reason=f"Done: {words}")
    return counts


def request_cancel(db: Any, job_id: str) -> str:
    row = jobs.read_job(db, job_id)
    if row["state"] == "waiting":
        jobs.cancel_waiting(db, job_id)
        return "cancelled"
    detail = json.loads(row["detail"] or "{}")
    detail["cancel"] = True
    jobs.save_detail(db, job_id, json.dumps(detail), reason="Stopping: cancelling the batch at the provider")
    return row["state"]
