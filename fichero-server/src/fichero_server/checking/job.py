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
from pathlib import Path
from typing import Any


from fichero_server.execution import jobs
from fichero_server.models.checking import CheckRunRequest  # noqa: F401  (re-exported)

KIND = "check"
COUNTS = ("confirm", "correct", "reject", "unanswered")


def _job(db: Any, job_id: str) -> dict[str, Any]:
    from fichero_server.checking import line_check, tie_text

    row = jobs.read_job(db, job_id)
    if row is None or row["kind"] not in (KIND, line_check.KIND, tie_text.KIND):
        raise LookupError(f"no check run {job_id}")
    return row


def _row(db: Any, job_id: str) -> tuple[str, dict[str, Any]]:
    row = _job(db, job_id)
    return row["state"], json.loads(row["detail"] or "{}")


def start(db: Any, request: CheckRunRequest, *, started_by: str) -> dict[str, str]:
    if not request.scope_ids:
        raise ValueError("name the folders or documents whose proposals to check")
    if request.check == "line-against-page":
        from fichero_server.checking import line_check

        return line_check.start(db, request, started_by=started_by)
    if request.check == "tie-text-to-lines":
        from fichero_server.checking import tie_text

        return tie_text.start(db, request, started_by=started_by)
    job_id = jobs.enqueue_remote(db, KIND, f"check:{uuid.uuid4()}", target=request.provider,
                                 detail=json.dumps({"request": request.model_dump()}),
                                 reason=f"Waiting to check {request.layer} with {request.model}", started_by=started_by)
    return {"job_id": job_id}


def _words(counts: dict[str, int]) -> str:
    return (f"{counts['confirm']} confirmed, {counts['correct']} corrected, {counts['reject']} rejected, "
            f"{counts['unanswered']} unanswered")


async def _check(db: Any, job_id: str, request: CheckRunRequest, started_by: str) -> dict[str, Any]:
    import fichero_server.api.routes.document.content_representations  # noqa: F401  (representation.create)
    import fichero_server.api.routes.check  # noqa: F401  (registers check.verdict)
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
    job_id = jobs.job_id_for(db, KIND, subject)
    row = _job(db, job_id)
    detail = json.loads(row["detail"] or "{}")
    request = CheckRunRequest(**detail["request"])
    started_by = row["started_by"] or "owner"
    jobs.save_detail(db, job_id, json.dumps(detail), reason=f"Checking {request.layer} with {request.model}")
    result = asyncio.run(_check(db, job_id, request, started_by))
    _state, detail = _row(db, job_id)
    detail["result"] = result
    words = _words(result["counts"])
    jobs.save_detail(db, job_id, json.dumps(detail), reason=words)
    if result["stopped"]:
        raise jobs.JobCancelled(f"Stopped by you; {words}")
    return result


def request_cancel(db: Any, job_id: str) -> str:
    state, detail = _row(db, job_id)
    if state == "waiting":
        jobs.cancel_waiting(db, job_id)
        return "cancelled"
    if state == "running":
        detail["cancel"] = True
        jobs.save_detail(db, job_id, json.dumps(detail))
    return state


def status(db: Any, job_id: str) -> dict[str, Any]:
    from fichero_server.checking import line_check, tie_text

    row = _job(db, job_id)
    detail = json.loads(row["detail"] or "{}")
    result = detail.get("result") or {}
    if row["kind"] == tie_text.KIND:  # the page text tied to its lines: the counts and each doubtful line
        return {"job_id": job_id, "state": row["state"], "reason": row["reason"], "request": detail.get("request"),
                "counts": result.get("counts", dict.fromkeys(tie_text.COUNTS, 0)),
                "flagged": result.get("flagged", []), "thresholds": result.get("thresholds"),
                "missing": result.get("missing", [])}
    if row["kind"] == line_check.KIND:  # the teacher-line check: its flags, by line, with the scores
        return {"job_id": job_id, "state": row["state"], "reason": row["reason"], "request": detail.get("request"),
                "counts": result.get("counts", dict.fromkeys(line_check.COUNTS, 0)),
                "flagged": result.get("flagged", []), "thresholds": result.get("thresholds"),
                "missing": result.get("missing", [])}
    return {"job_id": job_id, "state": row["state"], "reason": row["reason"], "request": detail.get("request"),
            "counts": result.get("counts", dict.fromkeys(COUNTS, 0)), "proposals": result.get("proposals"),
            "missing": result.get("missing", [])}


def register_job_kinds() -> None:
    from fichero_server.checking import line_check, tie_text

    line_check.register_job_kinds()
    tie_text.register_job_kinds()
    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="remote", name="Check",
                           cancel=request_cancel)  # Stop on its row, or on a recipe run it is a step of (#5609)
