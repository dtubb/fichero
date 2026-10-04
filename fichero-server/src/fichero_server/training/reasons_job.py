"""Gathering a palaeographer's reasons as a job (#4642): one row, its counts in words.

`training.reasons.gather_reasons` over a scope, run by the scheduler. A teacher on a hosted provider is
refused by the egress gate inside `llm.vision` like any other call. The job waits on a model server and
holds no model in this process, so it runs on the `remote` lane, off the local ML lane, as the line
reader's own vision calls do. Stopping it asks no further lines; what was gathered stays in the ledger.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from fichero_server.execution import jobs

KIND = "gather-reasons"


class GatherReasonsRequest(BaseModel):
    scope_ids: list[str] = Field(description="Folders or pages whose checked lines are asked about.")
    checked: str = Field(description="The model id of the CHECKED pass (its lines and their right readings).")
    mode: Literal["read", "review"] = Field("read", description="`read`: the palaeographer's reasons and "
                                            "transcription; `review`: its review of the `draft` pass's readings.")
    provider: str = Field(description="The teacher's provider, e.g. openrouter, gemini, omlx.")
    model: str = Field(description="The teacher: a reasoning vision model, e.g. Qwen3-VL-8B-Thinking.")
    draft: str | None = Field(None, description="review: the model id of the pass whose readings are reviewed.")
    held_out_ids: list[str] = Field(default_factory=list, description="Pages kept as the test: never asked about.")
    language: str | None = None
    prompt_file: str | None = Field(None, description="The recipe's prompt file; none uses Fichero's own.")


def _row(db: Any, job_id: str) -> tuple[str, dict[str, Any]]:
    row = db.execute_fetchone("SELECT state, detail FROM jobs WHERE id = ? AND kind = ?", [job_id, KIND])
    if row is None:
        raise LookupError(f"no reasons job {job_id}")
    return row[0], json.loads(row[1] or "{}")


def start(db: Any, request: GatherReasonsRequest, *, started_by: str) -> dict[str, str]:
    if not request.scope_ids:
        raise ValueError("name the folders or pages whose checked lines to ask about")
    if request.mode == "review" and not request.draft:
        raise ValueError("a review needs the pass whose readings it reviews (draft)")
    detail = {"request": request.model_dump()}
    job_id = jobs.enqueue_remote(db, KIND, f"reasons:{uuid.uuid4()}", target=request.provider,
                                 detail=json.dumps(detail), reason=f"Waiting to ask {request.model}",
                                 started_by=started_by)
    return {"job_id": job_id}


def run(db: Any, subject: str) -> dict[str, Any]:
    from fichero_server.llm import LLMConfig
    from fichero_server.training.reasons import gather_reasons

    job_id = db.execute_fetchone("SELECT id FROM jobs WHERE kind = ? AND subject = ?", [KIND, subject])[0]
    _state, detail = _row(db, job_id)
    request = GatherReasonsRequest(**detail["request"])
    db.execute("UPDATE jobs SET reason = ? WHERE id = ?", [f"Asking {request.model} about each checked line", job_id])
    done = asyncio.run(gather_reasons(
        db, scope_ids=request.scope_ids, checked=request.checked, mode=request.mode,
        config=LLMConfig(provider=request.provider, model=request.model), draft=request.draft,
        held_out_ids=request.held_out_ids, language=request.language, prompt_file=request.prompt_file,
        should_stop=lambda: bool(_row(db, job_id)[1].get("cancel"))))
    detail["result"] = {k: v for k, v in vars(done).items()}
    words = (f"{done.reasoned} of {done.lines} lines have reasons, {done.with_thinking} with thinking; "
             f"{done.unparsed} unanswered; {len(done.missing)} pages missing")
    db.execute("UPDATE jobs SET detail = ?, reason = ? WHERE id = ?", [json.dumps(detail), words, job_id])
    if done.stopped:
        raise jobs.JobCancelled(f"Stopped by you; {words}")
    return detail["result"]


def request_cancel(db: Any, job_id: str) -> str:
    state, detail = _row(db, job_id)
    if state == "waiting":
        db.execute("UPDATE jobs SET state = 'cancelled', reason = 'Stopped by you', finished_at = ? "
                   "WHERE id = ? AND state = 'waiting'", [datetime.now(timezone.utc), job_id])
        return "cancelled"
    if state == "running":
        detail["cancel"] = True
        db.execute("UPDATE jobs SET detail = ? WHERE id = ?", [json.dumps(detail), job_id])
    return state


def status(db: Any, job_id: str) -> dict[str, Any]:
    state, detail = _row(db, job_id)
    reason = db.execute_fetchone("SELECT reason FROM jobs WHERE id = ?", [job_id])[0]
    return {"job_id": job_id, "state": state, "reason": reason, **detail}


def register_job_kinds() -> None:
    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="remote",
                           name="Gather a palaeographer's reasons")
