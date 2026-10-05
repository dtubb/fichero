"""The evaluation job, from the API (#5441, `distill.eval.*`): start one, follow it, read a model's scores.

Thin over `fichero_server.training.evaluation`. Starting is an audited action (`evaluation.run`), so the
app, the CLI, MCP and an agent do it the one way. It cannot be undone: a score is a result, not an edit;
it is appended to the model's card and a later evaluation adds to it. Stopping is Activity's stop
(`POST /api/activity/jobs/{id}/cancel`), which reaches the kind's own cancel.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models.compute_requests import EvaluationRunRequest

router = APIRouter(prefix="/evaluation")


def _evaluation() -> Any:
    from fichero_server.training import evaluation  # loaded on first use (#3950)

    return evaluation


class EvaluationStarted(BaseModel):
    job_id: str


class ModelScores(BaseModel):
    """Every evaluation written on one model's card, oldest first."""

    model: str
    reader: str
    evaluations: list[dict[str, Any]]


@action("evaluation.run", EvaluationRunRequest, domains=["job"], undoable=False)
def _action_run(db: Database, params: EvaluationRunRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    # The pages scored may come from a model's card, not the request; the action layer checked only the ids
    # named. A held-out page this caller may not read refuses the run (fail closed); the owner is unchecked.
    from fichero_server.security import authz

    started = _evaluation().start(db, params, started_by=ctx.actor or "owner",
                                  check_pages=lambda pages: authz.assert_can_read_every(
                                      ctx.actor, ctx.library_path, pages, bootstrap=ctx.is_bootstrap))
    return started, ChangeSpec(domains=["job"], target_ids=[started["job_id"]],
                               after={"job_id": started["job_id"], "kind": _evaluation().KIND},
                               emit_type="job.created")


@router.post("/runs", response_model=EvaluationStarted,
             summary="Score trained and out-of-the-box models on the held-out checked pages, as one job")
async def start_evaluation(
    request: EvaluationRunRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> EvaluationStarted:
    """Queue an `evaluate-models` job on the local model lane: each candidate (and, unless asked not to, the
    out-of-the-box readers of the same kind on this Mac) reads the checked pass's lines on the held-out
    pages, and is scored with Fichero's one CER under every normalisation policy; the scores are appended
    to each model's card. Refused (422) in words when a trained model's card names no held-out page, a
    named page is not held out from a trained candidate, no page has a checked reading, a model is not
    on this Mac, or the model is remote (not built yet). Through `evaluation.run`."""
    try:
        return EvaluationStarted(**registry.invoke(db, "evaluation.run", request.model_dump(), ctx).result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs/{job_id}", summary="An evaluation's plan, progress and scores")
async def evaluation_status(job_id: str, db: Database = Depends(get_library_database)) -> dict[str, Any]:
    try:
        return _evaluation().status(db, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/scores", response_model=ModelScores, summary="A model's held-out scores, as its card keeps them")
async def model_scores(
    model: str = Query(..., description="The model id: a Kraken reader, or a vision model."),
    reader: Literal["kraken", "vision"] = Query("kraken"),
) -> ModelScores:
    """Every evaluation on the model's card (`distill.eval.stored-on-the-model-node`): per policy, the CER
    over the held-out pages and per page, who checked the reference, and the models it was compared with."""
    return ModelScores(model=model, reader=reader, evaluations=_evaluation().model_evaluations(model, reader))
