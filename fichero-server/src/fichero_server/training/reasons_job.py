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
from typing import Any


from fichero_server.execution import jobs
from fichero_server.models.compute_requests import (  # noqa: F401  (re-exported)
    ContenderSpec,
    GatherReasonsRequest,
    ReasonsABRequest,
)

KIND = "gather-reasons"
KIND_AB = "reasons-ab"


def _job(db: Any, job_id: str, kind: str = KIND) -> dict[str, Any]:
    row = jobs.read_job(db, job_id)
    if row is None or row["kind"] != kind:
        raise LookupError(f"no {kind} job {job_id}")
    return row


def _row(db: Any, job_id: str, kind: str = KIND) -> tuple[str, dict[str, Any]]:
    row = _job(db, job_id, kind)
    return row["state"], json.loads(row["detail"] or "{}")


def start(db: Any, request: GatherReasonsRequest, *, started_by: str) -> dict[str, str]:
    if not request.scope_ids:
        raise ValueError("name the folders or pages whose checked lines to ask about")
    detail = {"request": request.model_dump()}
    job_id = jobs.enqueue_remote(db, KIND, f"reasons:{uuid.uuid4()}", target=request.provider,
                                 detail=json.dumps(detail), reason=f"Waiting to ask {request.model}",
                                 started_by=started_by)
    return {"job_id": job_id}


def run(db: Any, subject: str) -> dict[str, Any]:
    from fichero_server.llm import LLMConfig
    from fichero_server.training.reasons import gather_reasons

    job_id = jobs.job_id_for(db, KIND, subject)
    _state, detail = _row(db, job_id)
    request = GatherReasonsRequest(**detail["request"])
    jobs.save_detail(db, job_id, json.dumps(detail), reason=f"Asking {request.model} about each checked line")
    done = asyncio.run(gather_reasons(
        db, scope_ids=request.scope_ids, checked=request.checked,
        config=LLMConfig(provider=request.provider, model=request.model),
        held_out_ids=request.held_out_ids, language=request.language, prompt_file=request.prompt_file,
        should_stop=lambda: bool(_row(db, job_id)[1].get("cancel"))))
    detail["result"] = {k: v for k, v in vars(done).items()}
    words = (f"{done.reasoned} of {done.lines} lines have reasons, {done.with_thinking} with thinking; "
             f"{done.unparsed} unanswered; {len(done.missing)} pages missing")
    jobs.save_detail(db, job_id, json.dumps(detail), reason=words)
    if done.stopped:
        raise jobs.JobCancelled(f"Stopped by you; {words}")
    return detail["result"]


def request_cancel(db: Any, job_id: str) -> str:
    state, detail = _row(db, job_id)
    if state == "waiting":
        jobs.cancel_waiting(db, job_id)
        return "cancelled"
    if state == "running":
        detail["cancel"] = True
        jobs.save_detail(db, job_id, json.dumps(detail))
    return state


def status(db: Any, job_id: str, kind: str = KIND) -> dict[str, Any]:
    row = _job(db, job_id, kind)
    return {"job_id": job_id, "state": row["state"], "reason": row["reason"], **json.loads(row["detail"] or "{}")}


def start_ab(db: Any, request: ReasonsABRequest, *, started_by: str) -> dict[str, str]:
    if not request.held_out_ids:
        raise ValueError("name the held-out checked pages: the A/B is measured only on pages no arm trained on")
    job_id = jobs.enqueue_remote(db, KIND_AB, f"reasons-ab:{uuid.uuid4()}", target="models",
                                 detail=json.dumps({"request": request.model_dump()}),
                                 reason="Waiting to measure the students", started_by=started_by)
    return {"job_id": job_id}


def run_ab(db: Any, subject: str) -> dict[str, Any]:
    from fichero_server.training.reasons_ab import Contender, run_ab as measure_ab

    job_id = jobs.job_id_for(db, KIND_AB, subject)
    _state, detail = _row(db, job_id, KIND_AB)
    request = ReasonsABRequest(**detail["request"])
    jobs.save_detail(db, job_id, json.dumps(detail), reason="Each contender reading the held-out lines")
    result = asyncio.run(measure_ab(db, checked=request.checked, held_out_ids=request.held_out_ids,
                                    contenders=[Contender(**c.model_dump()) for c in request.contenders],
                                    language=request.language, noise_band=request.noise_band))
    detail["result"] = result
    adopted = [label for label, v in result["verdicts"].items() if v["adopted"]]
    words = (f"Adopted: {', '.join(adopted)}" if adopted else "No reasoning student beat the answer-only one "
             "beyond the noise band") + f"; written on {len(result['cards'])} cards"
    jobs.save_detail(db, job_id, json.dumps(detail), reason=words)
    return result


def register_job_kinds() -> None:
    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="remote",
                           name="Gather a palaeographer's reasons", cancel=request_cancel)  # Stop on its row (#5356)
    if KIND_AB not in jobs.KINDS or jobs.KINDS[KIND_AB].run is None:
        jobs.register_kind(KIND_AB, lambda db, subject: run_ab(db, subject), model=None, lane="remote",
                           name="Measure the reasons A/B")
