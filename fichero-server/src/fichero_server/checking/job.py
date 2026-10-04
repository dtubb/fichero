"""The `check` job: a checker model checks a layer's proposals over a scope (`source.check.run-is-a-job`).

One row in Activity (kind `check`, the recipe job's own id), on the `remote` lane: it waits on a model
server and holds no model here. One proposal per call, one at a time (a hosted checker is a paid call;
a local one shares the Mac). Each call is an episode (`source.check.traces-in-the-ledger`); each answer is
recorded through `check.verdict` under the run, so it is the model's (`source.check.model-never-a-person`);
a corrected reading is first written as a new reading naming the one checked
(`source.check.correction-names-the-first`). A stop is honoured before the next proposal; what was checked
stays.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from fichero_server.execution import jobs

KIND = "check"
COUNTS = ("confirm", "correct", "reject", "unanswered")


class CheckRunRequest(BaseModel):
    layer: Literal["readings", "claims", "entities"] = Field(description="Which layer's proposals to check.")
    scope_ids: list[str] = Field(description="Folders, pages or documents: their lines, or their statements and entities.")
    provider: str = Field(description="The checker's provider, e.g. openrouter, omlx.")
    model: str = Field(description="The checker model, e.g. a palaeographer such as Fable.")
    prompt_file: str | None = Field(None, description="The recipe's prompt for this card; none uses Fichero's own.")
    language: str | None = None
    kind: str = Field("transcription", description="readings: the kind of reading checked.")
    pass_model: str | None = Field(None, description="readings: check the lines of this model's pass, not the "
                                   "page's newest.")


def _row(db: Any, job_id: str) -> tuple[str, dict[str, Any]]:
    row = db.execute_fetchone("SELECT state, detail FROM jobs WHERE id = ? AND kind = ?", [job_id, KIND])
    if row is None:
        raise LookupError(f"no check run {job_id}")
    return row[0], json.loads(row[1] or "{}")


def start(db: Any, request: CheckRunRequest, *, started_by: str) -> dict[str, str]:
    if not request.scope_ids:
        raise ValueError("name the folders or documents whose proposals to check")
    job_id = jobs.enqueue_remote(db, KIND, f"check:{uuid.uuid4()}", target=request.provider,
                                 detail=json.dumps({"request": request.model_dump()}),
                                 reason=f"Waiting to check {request.layer} with {request.model}", started_by=started_by)
    return {"job_id": job_id}


def _words(counts: dict[str, int]) -> str:
    return (f"{counts['confirm']} confirmed, {counts['correct']} corrected, {counts['reject']} rejected, "
            f"{counts['unanswered']} unanswered")


async def _check(db: Any, job_id: str, request: CheckRunRequest, started_by: str) -> dict[str, Any]:
    import fichero_server.api.routes.document.content_representations  # noqa: F401  (representation.create)
    import fichero_server.checking.verdicts  # noqa: F401  (check.verdict)
    from fichero_server import llm
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.checking import cards
    from fichero_server.observability import episodes
    from fichero_server.training.reasons import split_thinking

    library = str(Path(db.path).parent)
    missing: list[dict[str, str]] = []
    if request.layer == "readings":
        proposals, missing = cards.reading_proposals(db, request.scope_ids, kind=request.kind,
                                                     pass_model=request.pass_model)
    elif request.layer == "claims":
        proposals = cards.claim_proposals(db, request.scope_ids)
    else:
        proposals = cards.entity_proposals(db, request.scope_ids, language=request.language)
    template = Path(request.prompt_file).read_text(encoding="utf-8") if request.prompt_file else None
    config = llm.LLMConfig(provider=request.provider, model=request.model)
    ctx = ActionContext(actor=started_by, run_id=job_id, library_path=library)
    counts = dict.fromkeys(COUNTS, 0)
    token = episodes.set_library(library)
    stopped = False
    try:
        for proposal in proposals:
            if _row(db, job_id)[1].get("cancel"):
                stopped = True
                break
            prompt = cards.prompt_for(proposal, template=template, language=request.language)
            started = time.monotonic()
            if proposal.image:
                raw = await llm.vision(images=[proposal.image], prompt=prompt, config=config)
            else:
                raw = await llm.chat(prompt, config=config)
            _answer, thinking = split_thinking(raw)
            found = cards.parse_verdict(raw, request.layer)
            line = None
            if proposal.layer == "readings":  # the review arm's lesson (`training.reasons.traces_by_line`)
                text = None if not found or found["verdict"] == "reject" else (
                    found["correction"]["text"] if found["verdict"] == "correct" else proposal.shown)
                line = [{"line_id": proposal.line_id, "document_id": proposal.document_id, "draft": proposal.shown,
                         "text": text, "why": found and found["why"], "verdict": found and found["verdict"],
                         **({"thinking": thinking} if thinking else {})}]
            episode_id = episodes.record(
                subject={"layer": proposal.layer, "target_id": proposal.target_id, "document_id": proposal.document_id},
                model={"provider": request.provider, "model": request.model, "use_case": cards.USE_CASE[proposal.layer],
                       "prompt_file": Path(request.prompt_file).name if request.prompt_file else None},
                exchange={"prompt": prompt, "output": raw, "thinking": thinking, "images": 1 if proposal.image else 0},
                timing={"seconds": round(time.monotonic() - started, 2)},
                extra={"lines": line} if line else None)
            if found is None:
                counts["unanswered"] += 1
                continue
            replacement = None
            if proposal.layer == "readings" and found["verdict"] == "correct":
                made = registry.invoke(db, "representation.create", {
                    "document_id": proposal.document_id, "segment_id": proposal.segment_id,
                    "kind": proposal.extra["kind"], "content": found["correction"]["text"],
                    **({"derived_from_artifact_id": proposal.extra["derived_from_artifact_id"]}
                       if proposal.extra["provisional"] else {"corrects_representation_id": proposal.target_id}),
                }, ctx).result
                replacement = made["id"]
            registry.invoke(db, "check.verdict", {
                "layer": proposal.layer, "target_id": proposal.target_id, "verdict": found["verdict"],
                "reasons": found["why"], "checker_model": request.model, "episode_id": episode_id,
                "correction": found["correction"] if proposal.layer != "readings" else None,
                "replacement_id": replacement, "segment_id": proposal.segment_id}, ctx)
            counts[found["verdict"]] += 1
    finally:
        episodes._episode_library_path.reset(token)
    return {"counts": counts, "proposals": len(proposals), "missing": missing, "stopped": stopped}


def run(db: Any, subject: str) -> dict[str, Any]:
    job_id = db.execute_fetchone("SELECT id FROM jobs WHERE kind = ? AND subject = ?", [KIND, subject])[0]
    _state, detail = _row(db, job_id)
    request = CheckRunRequest(**detail["request"])
    started_by = db.execute_fetchone("SELECT started_by FROM jobs WHERE id = ?", [job_id])[0] or "owner"
    db.execute("UPDATE jobs SET reason = ? WHERE id = ?", [f"Checking {request.layer} with {request.model}", job_id])
    result = asyncio.run(_check(db, job_id, request, started_by))
    _state, detail = _row(db, job_id)
    detail["result"] = result
    words = _words(result["counts"])
    db.execute("UPDATE jobs SET detail = ?, reason = ? WHERE id = ?", [json.dumps(detail), words, job_id])
    if result["stopped"]:
        raise jobs.JobCancelled(f"Stopped by you; {words}")
    return result


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
    result = detail.get("result") or {}
    return {"job_id": job_id, "state": state, "reason": reason, "request": detail.get("request"),
            "counts": result.get("counts", dict.fromkeys(COUNTS, 0)), "proposals": result.get("proposals"),
            "missing": result.get("missing", [])}


def register_job_kinds() -> None:
    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="remote", name="Check")
