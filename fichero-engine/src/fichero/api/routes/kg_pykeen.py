"""PyKEEN link-prediction routes (#377, #899 Phase E)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kg/pykeen")


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
    db: Database = Depends(get_library_database),
) -> TrainResponse:
    """Train + persist a KGE model. Synchronous (can take 30s+ on a
    small library; minutes on larger). Use the response to learn
    whether the corpus had enough triples."""
    from fichero.kg.pykeen_predictor import train_model

    stats = train_model(
        db, model_name=model, embedding_dim=embedding_dim, num_epochs=num_epochs
    )
    return TrainResponse(**{**stats, "reason": stats.get("reason")})


class LinkPredictionRow(BaseModel):
    subject_id: str
    predicate: str
    object_id: str
    score: float


@router.get(
    "/predict/{entity_id}",
    response_model=list[LinkPredictionRow],
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
) -> list[LinkPredictionRow]:
    from fichero.kg.pykeen_predictor import predict_for_subject

    predictions = predict_for_subject(db, entity_id, top_k=top_k)
    if not predictions:
        # 200 with empty body — caller distinguishes "no model" from
        # "model has no predictions" via the explicit empty array.
        return []
    return [
        LinkPredictionRow(
            subject_id=p.subject_id,
            predicate=p.predicate,
            object_id=p.object_id,
            score=p.score,
        )
        for p in predictions
    ]
