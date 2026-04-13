"""PyKEEN prediction API routes.

Provides endpoints for training knowledge graph embedding models
and generating link predictions using PyKEEN.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import KnowledgeClaim, KnowledgeClaimLink, KnowledgeEntity
from fichero.pykeen_inference import (
    ModelType,
    PredictionResponse,
    PredictionType,
    StoredPrediction,
    TrainingConfig,
    TrainingResult,
    get_inference,
    set_inference_enabled,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["predictions"])


class TrainRequest(BaseModel):
    """Request to train a PyKEEN model."""

    model_type: ModelType = Field(default=ModelType.distmult)
    embedding_dim: int = Field(default=50, ge=16, le=512)
    epochs: int = Field(default=100, ge=10, le=1000)
    batch_size: int = Field(default=32, ge=8, le=512)
    learning_rate: float = Field(default=0.001, ge=0.0001, le=0.1)
    patience: int = Field(default=10, ge=3, le=50)
    minimum_improvement: float = Field(default=0.01, ge=0.001, le=0.1)
    use_gpu: bool = Field(default=False)


class EnableRequest(BaseModel):
    """Request to enable/disable PyKEEN inference."""

    enabled: bool


class PredictionRequest(BaseModel):
    """Request to generate predictions."""

    prediction_type: PredictionType
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    relation: str | None = None
    top_k: int = Field(default=10, ge=1, le=100)


class StorePredictionRequest(BaseModel):
    """Request to store a prediction."""

    prediction_id: str | None = None
    prediction_type: PredictionType
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    relation: str | None = None
    predictions: list[dict[str, Any]]
    notes: str | None = None


class VerifyPredictionRequest(BaseModel):
    """Request to verify a prediction."""

    verified: bool
    notes: str | None = None


@router.get("/api/predictions/status")
async def get_prediction_status() -> dict:
    """Get PyKEEN prediction engine status."""
    inference = get_inference()
    return inference.get_status()


@router.post("/api/predictions/enable")
async def set_prediction_enabled(request: EnableRequest) -> dict:
    """Enable or disable PyKEEN inference."""
    set_inference_enabled(request.enabled)
    return {"enabled": request.enabled}


@router.get("/api/predictions/models")
async def list_available_models() -> list[str]:
    """List available PyKEEN model types."""
    return [m.value for m in ModelType]


@router.post("/api/predictions/train")
async def train_prediction_model(
    request: TrainRequest,
    db: Database = Depends(get_library_database),
) -> TrainingResult:
    """Train a PyKEEN model on the current knowledge graph.

    Requires sufficient knowledge graph data (at least 10 triples).
    Training is asynchronous in memory; job status tracks completion.
    """
    inference = get_inference()

    # Load knowledge data
    entities = db.load_all(KnowledgeEntity)
    claims = db.load_all(KnowledgeClaim)
    links = db.load_all(KnowledgeClaimLink)

    if len(entities) < 2 or len(claims) < 2:
        raise HTTPException(
            status_code=400,
            detail="Insufficient data for training. Need at least 2 entities and 2 claims.",
        )

    # Generate model ID
    model_id = f"model_{uuid.uuid4().hex[:8]}"

    # Convert request to config
    config = TrainingConfig(
        model_type=request.model_type,
        embedding_dim=request.embedding_dim,
        epochs=request.epochs,
        batch_size=request.batch_size,
        learning_rate=request.learning_rate,
        patience=request.patience,
        minimum_improvement=request.minimum_improvement,
        use_gpu=request.use_gpu,
    )

    # Train model
    result = inference.train_model(
        model_id=model_id,
        entities=entities,
        claims=claims,
        links=links,
        config=config,
    )

    return result


@router.get("/api/predictions/training-jobs")
async def list_training_jobs() -> list[TrainingResult]:
    """List all training jobs."""
    inference = get_inference()
    return inference.get_training_jobs()


@router.get("/api/predictions/training-jobs/{model_id}")
async def get_training_job(model_id: str) -> TrainingResult:
    """Get specific training job details."""
    inference = get_inference()
    job = inference.get_training_job(model_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Training job {model_id} not found")

    return job


@router.delete("/api/predictions/models/{model_id}")
async def delete_trained_model(model_id: str) -> dict:
    """Delete a trained model."""
    inference = get_inference()
    deleted = inference.delete_model(model_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    return {"deleted": True, "model_id": model_id}


@router.post("/api/predictions/generate/{model_id}")
async def generate_predictions(
    model_id: str,
    request: PredictionRequest,
    db: Database = Depends(get_library_database),
) -> PredictionResponse:
    """Generate link predictions using a trained model."""
    inference = get_inference()

    # Build entity name map for readable results
    entities = db.load_all(KnowledgeEntity)
    entity_map = {e.id: e.canonical_name for e in entities}

    response = inference.predict_links(
        model_id=model_id,
        prediction_type=request.prediction_type,
        source_entity_id=request.source_entity_id,
        target_entity_id=request.target_entity_id,
        relation=request.relation,
        top_k=request.top_k,
        entity_map=entity_map,
    )

    if response is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model {model_id} not found or prediction failed",
        )

    return response


@router.post("/api/predictions/heuristic")
async def generate_heuristic_predictions(
    request: PredictionRequest,
    db: Database = Depends(get_library_database),
) -> PredictionResponse:
    """Generate heuristic predictions without PyKEEN.

    Uses co-occurrence and simple graph patterns.
    Available regardless of PyKEEN installation.
    """
    # Load data
    entities = db.load_all(KnowledgeEntity)
    claims = db.load_all(KnowledgeClaim)
    links = db.load_all(KnowledgeClaimLink)

    start_time = __import__("time").time()

    # Build co-occurrence graph
    co_occurrence: dict[str, dict[str, int]] = {}

    for claim in claims:
        entity_ids = claim.entity_ids
        for i, e1 in enumerate(entity_ids):
            if e1 not in co_occurrence:
                co_occurrence[e1] = {}
            for e2 in entity_ids[i + 1 :]:
                co_occurrence[e1][e2] = co_occurrence[e1].get(e2, 0) + 1
                if e2 not in co_occurrence:
                    co_occurrence[e2] = {}
                co_occurrence[e2][e1] = co_occurrence[e2].get(e1, 0) + 1

    # Build entity name map
    entity_map = {e.id: e.canonical_name for e in entities}

    # Generate predictions based on type
    predictions = []

    if request.prediction_type == PredictionType.tail_prediction:
        # Find entities commonly co-mentioned with source
        source = request.source_entity_id
        if source and source in co_occurrence:
            candidates = co_occurrence[source]
            sorted_candidates = sorted(
                candidates.items(),
                key=lambda x: x[1],
                reverse=True,
            )[: request.top_k]

            for rank, (entity_id, count) in enumerate(sorted_candidates, 1):
                predictions.append({
                    "rank": rank,
                    "score": float(count),
                    "entity_id": entity_id,
                    "entity_name": entity_map.get(entity_id, entity_id),
                    "confidence": min(1.0, count / 10.0),  # Normalize
                })

    elif request.prediction_type == PredictionType.head_prediction:
        # Find entities that commonly co-mention with target
        target = request.target_entity_id
        for source, targets in co_occurrence.items():
            if target in targets:
                predictions.append({
                    "rank": len(predictions) + 1,
                    "score": float(targets[target]),
                    "entity_id": source,
                    "entity_name": entity_map.get(source, source),
                    "confidence": min(1.0, targets[target] / 10.0),
                })

        predictions = sorted(predictions, key=lambda x: x["score"], reverse=True)[
            : request.top_k
        ]

    elif request.prediction_type == PredictionType.relation_prediction:
        # Return common relations from links
        relation_counts: dict[str, int] = {}
        for link in links:
            rel = link.relation_type.value if link.relation_type else "related_to"
            relation_counts[rel] = relation_counts.get(rel, 0) + 1

        sorted_relations = sorted(
            relation_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[: request.top_k]

        for rank, (rel, count) in enumerate(sorted_relations, 1):
            predictions.append({
                "rank": rank,
                "score": float(count),
                "entity_id": rel,
                "entity_name": rel,
                "confidence": min(1.0, count / 10.0),
            })

    execution_time = (__import__("time").time() - start_time) * 1000

    return PredictionResponse(
        model_id="heuristic",
        prediction_type=request.prediction_type,
        source_entity_id=request.source_entity_id,
        target_entity_id=request.target_entity_id,
        relation=request.relation,
        top_k=predictions,
        execution_time_ms=execution_time,
    )


@router.post("/api/predictions/store")
async def store_prediction(
    model_id: str,
    request: StorePredictionRequest,
) -> StoredPrediction:
    """Store a prediction for later verification."""
    inference = get_inference()


    prediction = StoredPrediction(
        prediction_id=request.prediction_id or f"pred_{uuid.uuid4().hex[:12]}",
        model_id=model_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        source_entity_id=request.source_entity_id,
        target_entity_id=request.target_entity_id,
        relation=request.relation,
        prediction_type=request.prediction_type,
        predictions=request.predictions,
        verified=None,
        notes=request.notes,
    )

    inference.store_prediction(prediction)
    return prediction


@router.get("/api/predictions/stored")
async def list_stored_predictions(
    model_id: str | None = None,
    verified: bool | None = None,
) -> list[StoredPrediction]:
    """List stored predictions."""
    inference = get_inference()
    return inference.list_predictions(model_id=model_id, verified=verified)


@router.get("/api/predictions/stored/{prediction_id}")
async def get_stored_prediction(prediction_id: str) -> StoredPrediction:
    """Get a specific stored prediction."""
    inference = get_inference()
    prediction = inference.get_prediction(prediction_id)

    if prediction is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prediction {prediction_id} not found",
        )

    return prediction


@router.patch("/api/predictions/stored/{prediction_id}/verify")
async def verify_prediction(
    prediction_id: str,
    request: VerifyPredictionRequest,
) -> StoredPrediction:
    """Verify or refute a stored prediction."""
    inference = get_inference()
    prediction = inference.get_prediction(prediction_id)

    if prediction is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prediction {prediction_id} not found",
        )

    # Update prediction
    prediction.verified = request.verified
    if request.notes:
        prediction.notes = request.notes

    inference.store_prediction(prediction)
    return prediction
