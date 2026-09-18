"""PyKEEN link-prediction routes (#377, #899 Phase E)."""

from __future__ import annotations

import logging
from pathlib import Path
from fichero_server.core.timeutil import utc_now

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import request_actor
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.knowledge.pykeen_inference import (
    StoredPrediction,
    TrainingResult,
    get_inference,
)
from fichero_server.models.knowledge import KnowledgePredictionReview, PredictionReviewState
from fichero_server.models import PykeenListResponse, KGGraphListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kg/pykeen")


def _pykeen_unavailable(exc: ImportError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="PyKEEN link prediction is not installed in this backend.",
    )


class TrainResponse(BaseModel):
    triples: int
    entities: int
    relations: int
    model: str
    path: str
    trained: bool
    reason: str | None = None


@router.post(
    "/train",
    response_model=TrainResponse,
    summary="Train a PyKEEN link-prediction model on the library's claims",
)
async def train(
    model: str = Query(default="TransE"),
    embedding_dim: int = Query(default=64, ge=8, le=512),
    num_epochs: int = Query(default=50, ge=1, le=1000),
    db: Database = Depends(get_library_database_for_write),
) -> TrainResponse:
    """Train + persist a KGE model. Synchronous (can take 30s+ on a
    small library; minutes on larger). Use the response to learn
    whether the corpus had enough triples."""
    try:
        from fichero_server.knowledge.pykeen_predictor import train_model
    except ImportError as exc:
        raise _pykeen_unavailable(exc) from exc

    try:
        stats = train_model(
            db, model_name=model, embedding_dim=embedding_dim, num_epochs=num_epochs
        )
    except ImportError as exc:
        raise _pykeen_unavailable(exc) from exc
    return TrainResponse(**{**stats, "reason": stats.get("reason")})


class LinkPredictionRow(BaseModel):
    subject_id: str
    predicate: str
    object_id: str
    score: float


@router.get(
    "/predict/{entity_id}",
    response_model=KGGraphListResponse,
    summary="Top-k predicted facts for one entity",
    description=(
        "Surfaces the curation queue: ranked candidate (predicate, "
        "object) pairs the model thinks are plausibly true for this "
        "entity. A reviewer accepts (creates a KnowledgeClaim), "
        "rejects (logs a negative example), or skips. Requires a "
        "model trained via POST /api/kg/pykeen/train. (#377)"
    ),
)
async def predict(
    entity_id: str,
    top_k: int = Query(default=10, ge=1, le=100),
    db: Database = Depends(get_library_database),
) -> KGGraphListResponse:
    try:
        from fichero_server.knowledge.pykeen_predictor import predict_for_subject
    except ImportError as exc:
        raise _pykeen_unavailable(exc) from exc

    try:
        predictions = predict_for_subject(db, entity_id, top_k=top_k)
    except ImportError as exc:
        raise _pykeen_unavailable(exc) from exc
    if not predictions:
        # 200 with empty envelope — caller distinguishes "no model" from
        # "model has no predictions" via the explicit empty items list.
        return KGGraphListResponse(items=[], count=0)
    rows = [
        LinkPredictionRow(
            subject_id=p.subject_id,
            predicate=p.predicate,
            object_id=p.object_id,
            score=p.score,
        )
        for p in predictions
    ]
    return KGGraphListResponse(items=rows, count=len(rows))


# ---------------------------------------------------------------------------
# Training-job + stored-prediction management.
#
# Ported from the deprecated /api/predictions/* surface (predictions.py)
# during the 2026-05-15 module-org cleanup. The /api/predictions namespace
# was the pre-/kg-consolidation home for PyKEEN; these endpoints are the
# unique features that did not already exist on /kg/pykeen. URL paths are
# /api/kg/pykeen/training-jobs[/...], /api/kg/pykeen/models/{id} (DELETE),
# /api/kg/pykeen/stored[/...].
# ---------------------------------------------------------------------------


class DeleteModelResponse(BaseModel):
    deleted: bool
    model_id: str


class VerifyPredictionRequest(BaseModel):
    verified: bool
    notes: str | None = None


class PredictionReviewDecision(BaseModel):
    state: PredictionReviewState
    note: str | None = None
    resulting_claim_id: str | None = None


@action(
    "pykeen.create_review",
    KnowledgePredictionReview,
    domains=["claim"],
    # No delete/restore action exists for this row kind yet -- a fresh
    # create has nothing to invert to. Add one if this needs undo.
    undoable=False,
)
def _action_create_prediction_review(
    db: Database, params: KnowledgePredictionReview, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    db.save(params)
    after = params.model_dump(mode="json")
    spec = ChangeSpec(domains=["claim"], target_ids=[params.id], before=None, after=after)
    return after, spec


@router.post("/reviews", response_model=KnowledgePredictionReview)
async def create_prediction_review(
    review: KnowledgePredictionReview,
    db: Database = Depends(get_library_database_for_write),
    actor: str = Depends(request_actor),
) -> KnowledgePredictionReview:
    ctx = ActionContext(actor=actor, library_path=str(Path(db.path).parent))
    result = registry.invoke(
        db, "pykeen.create_review", review.model_dump(mode="json"), ctx
    )
    return KnowledgePredictionReview.model_validate(result.result)


@router.get("/reviews", response_model=PykeenListResponse)
async def list_prediction_reviews(
    state: PredictionReviewState | None = None,
    db: Database = Depends(get_library_database),
) -> PykeenListResponse:
    rows = db.all(KnowledgePredictionReview)
    if state is not None:
        rows = [row for row in rows if row.state == state]
    rows.sort(key=lambda row: row.created_at, reverse=True)
    return PykeenListResponse(items=rows, count=len(rows))


class RestoreReviewParams(BaseModel):
    """Params for `pykeen.restore_review` -- a full-row snapshot round-trip,
    the SAME idiom `claim.restore`/`review.restore_pair` use for their own
    update-action undo."""

    snapshot: dict


@action("pykeen.restore_review", RestoreReviewParams, domains=["claim"], undoable=False)
def _action_restore_review(
    db: Database, params: RestoreReviewParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    restored = KnowledgePredictionReview.model_validate(params.snapshot)
    db.save(restored)
    spec = ChangeSpec(
        domains=["claim"], target_ids=[restored.id], after={"id": restored.id}
    )
    return {"id": restored.id}, spec


class DecidePredictionReviewParams(BaseModel):
    review_id: str
    state: PredictionReviewState
    note: str | None = None
    resulting_claim_id: str | None = None


def _invert_decide_review(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return ("pykeen.restore_review", {"snapshot": before})


@action(
    "pykeen.decide_review",
    DecidePredictionReviewParams,
    domains=["claim"],
    undoable=True,
    invert=_invert_decide_review,
)
def _action_decide_prediction_review(
    db: Database, params: DecidePredictionReviewParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    review = db.get(KnowledgePredictionReview, params.review_id)
    if review is None:
        raise HTTPException(status_code=404, detail=f"Prediction review {params.review_id} not found")
    before = review.model_dump(mode="json")
    review.state = params.state
    review.decision_note = params.note
    review.resulting_claim_id = params.resulting_claim_id
    review.reviewed_at = utc_now()
    db.save(review)
    after = review.model_dump(mode="json")
    spec = ChangeSpec(domains=["claim"], target_ids=[review.id], before=before, after=after)
    return after, spec


@router.patch("/reviews/{review_id}", response_model=KnowledgePredictionReview)
async def decide_prediction_review(
    review_id: str,
    decision: PredictionReviewDecision,
    db: Database = Depends(get_library_database_for_write),
    actor: str = Depends(request_actor),
) -> KnowledgePredictionReview:
    ctx = ActionContext(actor=actor, library_path=str(Path(db.path).parent))
    result = registry.invoke(
        db,
        "pykeen.decide_review",
        {
            "review_id": review_id,
            "state": decision.state.value,
            "note": decision.note,
            "resulting_claim_id": decision.resulting_claim_id,
        },
        ctx,
    )
    return KnowledgePredictionReview.model_validate(result.result)


@router.get(
    "/training-jobs",
    response_model=PykeenListResponse,
    summary="List all PyKEEN training jobs",
)
async def list_training_jobs() -> PykeenListResponse:
    inference = get_inference()
    jobs = inference.get_training_jobs()
    return PykeenListResponse(items=jobs, count=len(jobs))


@router.get(
    "/training-jobs/{model_id}",
    response_model=TrainingResult,
    summary="Get a specific PyKEEN training job",
)
async def get_training_job(model_id: str) -> TrainingResult:
    inference = get_inference()
    job = inference.get_training_job(model_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Training job {model_id} not found")
    return job


@router.delete(
    "/models/{model_id}",
    response_model=DeleteModelResponse,
    summary="Delete a trained PyKEEN model",
)
async def delete_trained_model(model_id: str) -> DeleteModelResponse:
    inference = get_inference()
    deleted = inference.delete_model(model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return DeleteModelResponse(deleted=True, model_id=model_id)


@router.get(
    "/stored",
    response_model=PykeenListResponse,
    summary="List stored predictions",
)
async def list_stored_predictions(
    model_id: str | None = None,
    verified: bool | None = None,
) -> PykeenListResponse:
    inference = get_inference()
    predictions = inference.list_predictions(model_id=model_id, verified=verified)
    return PykeenListResponse(items=predictions, count=len(predictions))


@router.get(
    "/stored/{prediction_id}",
    response_model=StoredPrediction,
    summary="Get a specific stored prediction",
)
async def get_stored_prediction(prediction_id: str) -> StoredPrediction:
    inference = get_inference()
    prediction = inference.get_prediction(prediction_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail=f"Prediction {prediction_id} not found")
    return prediction


@router.patch(
    "/stored/{prediction_id}/verify",
    response_model=StoredPrediction,
    summary="Verify or refute a stored prediction",
)
async def verify_prediction(
    prediction_id: str,
    request: VerifyPredictionRequest,
) -> StoredPrediction:
    inference = get_inference()
    prediction = inference.get_prediction(prediction_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail=f"Prediction {prediction_id} not found")
    prediction.verified = request.verified
    if request.notes:
        prediction.notes = request.notes
    inference.store_prediction(prediction)
    return prediction
