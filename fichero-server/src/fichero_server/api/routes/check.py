"""Checking a layer's proposals, from the API (`source.check.*`, specs/source/checking.md).

Start, follow and stop a check run (`check.run`, `check.cancel`); record a verdict yourself
(`check.verdict`, recorded at `person`); list the verdicts on a proposal or of a run.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import (
    get_library_database,
    get_library_database_for_write,
    optional_library_path,
    readable_documents,
)
from fichero_server.db import Database
from fichero_server.models.checking import CheckRunRequest, CheckVerdict, CheckVerdictParams

router = APIRouter(prefix="/check")


class CheckRunParams(BaseModel):
    job_id: str


@action("check.run", CheckRunRequest, domains=["job"], undoable=False)
def _action_run(db: Database, params: CheckRunRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.checking import job as check_job

    if not ctx.is_bootstrap:
        # The action layer checked the ids named; a check reads every document UNDER them (each check
        # kind walks the same descendants). One the caller may not read refuses the run (fail closed).
        from fichero_server.checking.cards import _descendants
        from fichero_server.security import authz

        authz.assert_can_read_every(ctx.actor, ctx.library_path, [d.id for d in _descendants(db, params.scope_ids)],
                                    bootstrap=False)
    started = check_job.start(db, params, started_by=ctx.actor or "owner")
    return started, ChangeSpec(domains=["job"], target_ids=[started["job_id"]],
                               after={"job_id": started["job_id"], "kind": check_job.KIND}, emit_type="job.created")


@action("check.cancel", CheckRunParams, domains=["job"], undoable=False)
def _action_cancel(db: Database, params: CheckRunParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.checking import job as check_job

    state = check_job.request_cancel(db, params.job_id)
    return {"job_id": params.job_id, "state": state}, ChangeSpec(
        domains=["job"], target_ids=[params.job_id], after={"job_id": params.job_id, "state": state},
        emit_type="job.updated")


@action("check.verdict", CheckVerdictParams, domains=["check"], undoable=False)
def _action_verdict(db: Database, params: CheckVerdictParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    """Registered here, at app start, so every surface finds it; the work is `checking.verdicts`."""
    from fichero_server.checking.verdicts import record_verdict

    return record_verdict(db, params, ctx)


@router.post("/runs", summary="Check a layer's proposals with a checker model, as one job")
async def start_check_run(
    request: CheckRunRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict[str, str]:
    """Queue a `check` job: the checker model is shown each proposal of `layer` in scope (a line's picture
    and its counting reading; a statement with its subject, relation, object and passage; an entity with
    its names and passages) and answers confirm, correct or reject with its reasons. Each answer is a
    verdict at the trust level `model`; a corrected reading is a new reading naming the first; a model
    never curates a statement or verifies an entity. Through `check.run`."""
    try:
        return registry.invoke(db, "check.run", request.model_dump(), ctx).result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs/{job_id}", summary="A check run's counts in words and numbers")
async def check_run_status(job_id: str, db: Database = Depends(get_library_database)) -> dict[str, Any]:
    from fichero_server.checking import job as check_job

    try:
        return check_job.status(db, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{job_id}/cancel", summary="Stop a check run before its next proposal")
async def cancel_check_run(
    job_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict[str, str]:
    try:
        return registry.invoke(db, "check.cancel", {"job_id": job_id}, ctx).result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/verdicts", summary="Record your verdict on a proposal")
async def record_verdict(
    params: CheckVerdictParams,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict[str, Any]:
    """Confirm, correct or reject one proposal, with your reasons, through `check.verdict`. Its trust level
    is the server's: `person` for you, `model` for a run or an agent. A reject records your verdict; a
    statement's curation is still its own action."""
    try:
        return registry.invoke(db, "check.verdict", params.model_dump(), ctx).result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/verdicts", summary="Verdicts on a proposal, or of a run")
async def list_verdicts(
    request: Request,
    target_id: str | None = Query(None), run_id: str | None = Query(None), layer: str | None = Query(None),
    document_id: str | None = Query(None, description="one page's verdicts (a page view never reads the library's)"),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    filters = {
        k: v for k, v in {"target_id": target_id, "run_id": run_id, "layer": layer, "document_id": document_id}.items()
        if v
    }
    rows = sorted(db.query(CheckVerdict, **filters), key=lambda v: (v.created_at, v.id))
    # ACCESS CONTROL (#5180): a run's or a layer's verdicts span pages. A verdict on a page this caller
    # may not read is left out and counted (`withheld`, #5135); one on no page (a claim, an entity) is
    # library-level like the knowledge graph. The owner's list is unchanged.
    readable = set(readable_documents(request, x_fichero_library_path,
                                      sorted({v.document_id for v in rows if v.document_id})))
    kept = [v for v in rows if not v.document_id or v.document_id in readable]
    if len(kept) != len(rows):
        return {"items": [v.model_dump(mode="json") for v in kept], "count": len(kept),
                "withheld": len(rows) - len(kept)}
    return {"items": [v.model_dump(mode="json") for v in rows], "count": len(rows)}
