"""PyKEEN latent inference for knowledge graph link prediction.

Trains knowledge graph embedding models and generates link predictions
using PyKEEN.
"""

from __future__ import annotations

import logging
import math
import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from fichero.knowledge_models import (
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
)

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    """PyKEEN model types for knowledge graph embeddings."""

    trans_e = "TransE"  # Translation-based
    rotat_e = "RotatE"  # Rotation-based
    distmult = "DistMult"  # Bilinear
    compl_ex = "ComplEx"  # Complex embeddings
    conve = "ConvE"  # Convolutional


class TrainingStatus(str, Enum):
    """Training job status."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class PredictionType(str, Enum):
    """Type of prediction to generate."""

    head_prediction = "head_prediction"  # Predict source entity
    tail_prediction = "tail_prediction"  # Predict target entity
    relation_prediction = "relation_prediction"  # Predict relation type


class TrainingConfig(BaseModel):
    """Configuration for PyKEEN model training."""

    model_type: ModelType = Field(default=ModelType.distmult)
    embedding_dim: int = Field(default=50, ge=16, le=512)
    epochs: int = Field(default=100, ge=10, le=1000)
    batch_size: int = Field(default=32, ge=8, le=512)
    learning_rate: float = Field(default=0.001, ge=0.0001, le=0.1)
    patience: int = Field(default=10, ge=3, le=50)
    minimum_improvement: float = Field(default=0.01, ge=0.001, le=0.1)
    use_gpu: bool = Field(default=False)


class TrainingResult(BaseModel):
    """Training job result."""

    model_id: str
    status: TrainingStatus
    model_type: str
    epochs_completed: int
    final_loss: float | None = None
    hits_at_10: float | None = None
    mean_rank: float | None = None
    training_time_ms: float
    entity_count: int
    relation_count: int
    triple_count: int
    error_message: str | None = None


class PredictionResult(BaseModel):
    """Single link prediction result."""

    rank: int
    score: float
    entity_id: str
    entity_name: str
    confidence: float  # Normalized 0-1


class PredictionResponse(BaseModel):
    """Link prediction response."""

    model_id: str
    prediction_type: PredictionType
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    relation: str | None = None
    top_k: list[PredictionResult]
    execution_time_ms: float


class StoredPrediction(BaseModel):
    """Stored prediction with metadata."""

    prediction_id: str
    model_id: str
    created_at: str
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    relation: str | None = None
    prediction_type: PredictionType
    predictions: list[PredictionResult]
    verified: bool | None = None  # User verification status
    notes: str | None = None


class PyKEENInference:
    """PyKEEN-based link prediction for knowledge graphs."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._models: dict[str, Any] = {}  # model_id -> trained model
        self._training_jobs: dict[str, TrainingResult] = {}
        self._predictions: dict[str, StoredPrediction] = {}

    def get_status(self) -> dict[str, Any]:
        """Get inference engine status."""
        return {
            "enabled": self.enabled,
            "models_trained": len(self._models),
            "training_jobs": len(self._training_jobs),
            "stored_predictions": len(self._predictions),
        }

    def _build_triples(
        self,
        entities: list[KnowledgeEntity],
        claims: list[KnowledgeClaim],
        links: list[KnowledgeClaimLink],
    ) -> list[tuple[str, str, str]]:
        """Build triples from knowledge graph for PyKEEN.

        Triples: (head, relation, tail)
        - Entity -> mentions -> Claim
        - Claim -> related_to -> Claim
        - Entity -> related_to -> Entity (via shared claims)
        """
        triples: list[tuple[str, str, str]] = []
        entity_ids = {e.id for e in entities}

        # Entity -> mentions -> Claim
        for claim in claims:
            for entity_id in claim.entity_ids:
                if entity_id in entity_ids:
                    triples.append((entity_id, "mentions", claim.id))

        # Claim -> related_to -> Claim
        for link in links:
            relation = link.relation_type.value if link.relation_type else "related_to"
            triples.append((link.claim_id, relation, link.related_claim_id))

        # Entity -> related_to -> Entity (co-occurrence)
        claim_entities: dict[str, list[str]] = {}
        for claim in claims:
            claim_entities[claim.id] = [
                eid for eid in claim.entity_ids if eid in entity_ids
            ]

        for entity_ids_list in claim_entities.values():
            if len(entity_ids_list) > 1:
                for i, e1 in enumerate(entity_ids_list):
                    for e2 in entity_ids_list[i + 1 :]:
                        triples.append((e1, "co_mentioned_with", e2))
                        triples.append((e2, "co_mentioned_with", e1))

        return triples

    def train_model(
        self,
        model_id: str,
        entities: list[KnowledgeEntity],
        claims: list[KnowledgeClaim],
        links: list[KnowledgeClaimLink],
        config: TrainingConfig,
    ) -> TrainingResult:
        """Train a PyKEEN model on the knowledge graph."""
        import pykeen.models  # noqa: PLC0415
        import pykeen.optimizers  # noqa: PLC0415
        from pykeen.evaluation import RankBasedEvaluator  # noqa: PLC0415
        from pykeen.stoppers import EarlyStopper  # noqa: PLC0415
        from pykeen.training import SLCWATrainingLoop  # noqa: PLC0415
        from pykeen.triples import TriplesFactory  # noqa: PLC0415

        start_time = time.time()

        try:
            # Build triples
            triples = self._build_triples(entities, claims, links)

            if len(triples) < 10:
                return TrainingResult(
                    model_id=model_id,
                    status=TrainingStatus.failed,
                    model_type=config.model_type.value,
                    epochs_completed=0,
                    training_time_ms=(time.time() - start_time) * 1000,
                    entity_count=len(entities),
                    relation_count=0,
                    triple_count=len(triples),
                    error_message="Insufficient training data (need at least 10 triples)",
                )

            # Create triples factory
            triples_factory = TriplesFactory.from_labeled_triples(triples)

            # Split data
            training, testing, validation = triples_factory.split(
                ratios=[0.8, 0.1, 0.1],
            )

            # Get model class
            model_class = getattr(pykeen.models, config.model_type.value)

            # Create model
            model = model_class(
                triples_factory=training,
                embedding_dim=config.embedding_dim,
            )

            # Training loop
            optimizer = pykeen.optimizers.Adam(
                params=model.get_grad_params(),
                lr=config.learning_rate,
            )

            training_loop = SLCWATrainingLoop(
                model=model,
                triples_factory=training,
                optimizer=optimizer,
            )

            # Early stopper
            stopper = EarlyStopper(
                model=model,
                evaluation_triples_factory=validation,
                frequency=1,
                patience=config.patience,
                relative_delta=config.minimum_improvement,
                larger_is_better=False,
                metric="mean_reciprocal_rank",
            )

            # Train
            training_loop.train(
                triples_factory=training,
                num_epochs=config.epochs,
                batch_size=config.batch_size,
                stopper=stopper,
                use_tqdm=False,
            )

            # Evaluate
            evaluator = RankBasedEvaluator()
            results = evaluator.evaluate(
                model=model,
                mapped_triples=testing.mapped_triples,
                batch_size=config.batch_size,
                additional_filter_triples=[
                    training.mapped_triples,
                    validation.mapped_triples,
                ],
            )

            # Store model
            self._models[model_id] = {
                "model": model,
                "triples_factory": triples_factory,
                "entity_id_to_index": triples_factory.entity_to_id,
                "relation_id_to_index": triples_factory.relation_to_id,
            }

            hits_at_10 = results.get_metric("hits_at_10")
            mean_rank = results.get_metric("mean_rank")
            training_time = (time.time() - start_time) * 1000

            result = TrainingResult(
                model_id=model_id,
                status=TrainingStatus.completed,
                model_type=config.model_type.value,
                epochs_completed=stopper.number_of_epochs,
                final_loss=None,  # PyKEEN doesn't expose this easily
                hits_at_10=hits_at_10,
                mean_rank=mean_rank,
                training_time_ms=training_time,
                entity_count=len(entities),
                relation_count=len(triples_factory.relation_to_id),
                triple_count=len(triples),
            )

            self._training_jobs[model_id] = result
            return result

        except Exception as e:
            logger.error(f"PyKEEN training failed: {e}")
            training_time = (time.time() - start_time) * 1000

            result = TrainingResult(
                model_id=model_id,
                status=TrainingStatus.failed,
                model_type=config.model_type.value,
                epochs_completed=0,
                training_time_ms=training_time,
                entity_count=len(entities),
                relation_count=0,
                triple_count=0,
                error_message=str(e),
            )
            self._training_jobs[model_id] = result
            return result

    def predict_links(
        self,
        model_id: str,
        prediction_type: PredictionType,
        source_entity_id: str | None = None,
        target_entity_id: str | None = None,
        relation: str | None = None,
        top_k: int = 10,
        entity_map: dict[str, str] | None = None,  # id -> name
    ) -> PredictionResponse | None:
        """Generate link predictions using trained model."""
        if model_id not in self._models:
            return None

        start_time = time.time()

        try:
            model_data = self._models[model_id]
            model = model_data["model"]
            triples_factory = model_data["triples_factory"]
            entity_to_id = model_data["entity_id_to_index"]
            relation_to_id = model_data["relation_id_to_index"]

            h_idx = entity_to_id.get(source_entity_id) if source_entity_id else None
            t_idx = entity_to_id.get(target_entity_id) if target_entity_id else None
            r_idx = relation_to_id.get(relation) if relation else None

            if prediction_type == PredictionType.tail_prediction:
                if h_idx is None or r_idx is None:
                    return None
                scores = model.predict_t(h_idx, r_idx)
                predictions = self._rank_predictions(
                    scores, entity_to_id, triples_factory, top_k, entity_map
                )

            elif prediction_type == PredictionType.head_prediction:
                if t_idx is None or r_idx is None:
                    return None
                scores = model.predict_h(r_idx, t_idx)
                predictions = self._rank_predictions(
                    scores, entity_to_id, triples_factory, top_k, entity_map
                )

            elif prediction_type == PredictionType.relation_prediction:
                if h_idx is None or t_idx is None:
                    return None
                scores = model.predict_r(h_idx, t_idx)
                predictions = self._rank_relation_predictions(
                    scores, relation_to_id, triples_factory, top_k
                )
            else:
                return None

            execution_time = (time.time() - start_time) * 1000

            return PredictionResponse(
                model_id=model_id,
                prediction_type=prediction_type,
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relation=relation,
                top_k=predictions,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            logger.error(f"PyKEEN prediction failed: {e}")
            return None

    def _rank_predictions(
        self,
        scores,
        entity_to_id: dict,
        triples_factory,
        top_k: int,
        entity_map: dict[str, str] | None,
    ) -> list[PredictionResult]:
        """Rank entity predictions from scores."""
        import torch  # noqa: PLC0415
        if isinstance(scores, torch.Tensor):
            scores = scores.cpu().numpy()

        top_indices = scores.argsort()[-top_k:][::-1]
        id_to_entity = {v: k for k, v in entity_to_id.items()}

        results = []
        for rank, idx in enumerate(top_indices, 1):
            entity_id = id_to_entity.get(int(idx), f"unknown_{idx}")
            score = float(scores[idx])
            confidence = 1 / (1 + math.exp(-score))
            entity_name = entity_map.get(entity_id, entity_id) if entity_map else entity_id

            results.append(
                PredictionResult(
                    rank=rank,
                    score=score,
                    entity_id=entity_id,
                    entity_name=entity_name,
                    confidence=confidence,
                )
            )

        return results

    def _rank_relation_predictions(
        self,
        scores,
        relation_to_id: dict,
        triples_factory,
        top_k: int,
    ) -> list[PredictionResult]:
        """Rank relation predictions from scores."""
        import torch  # noqa: PLC0415
        if isinstance(scores, torch.Tensor):
            scores = scores.cpu().numpy()

        top_indices = scores.argsort()[-top_k:][::-1]
        id_to_relation = {v: k for k, v in relation_to_id.items()}

        results = []
        for rank, idx in enumerate(top_indices, 1):
            relation_id = id_to_relation.get(int(idx), f"unknown_{idx}")
            score = float(scores[idx])
            confidence = 1 / (1 + math.exp(-score))

            results.append(
                PredictionResult(
                    rank=rank,
                    score=score,
                    entity_id=relation_id,
                    entity_name=relation_id,
                    confidence=confidence,
                )
            )

        return results

    def get_training_jobs(self) -> list[TrainingResult]:
        """Get all training job results."""
        return list(self._training_jobs.values())

    def get_training_job(self, model_id: str) -> TrainingResult | None:
        """Get specific training job result."""
        return self._training_jobs.get(model_id)

    def delete_model(self, model_id: str) -> bool:
        """Delete a trained model."""
        if model_id in self._models:
            del self._models[model_id]
            return True
        return False

    def store_prediction(self, prediction: StoredPrediction) -> None:
        """Store a prediction for later verification."""
        self._predictions[prediction.prediction_id] = prediction

    def get_prediction(self, prediction_id: str) -> StoredPrediction | None:
        """Get stored prediction by ID."""
        return self._predictions.get(prediction_id)

    def list_predictions(
        self,
        model_id: str | None = None,
        verified: bool | None = None,
    ) -> list[StoredPrediction]:
        """List stored predictions with optional filtering."""
        predictions = list(self._predictions.values())

        if model_id:
            predictions = [p for p in predictions if p.model_id == model_id]

        if verified is not None:
            predictions = [p for p in predictions if p.verified == verified]

        return sorted(predictions, key=lambda p: p.created_at, reverse=True)


# Singleton instance
_inference: PyKEENInference | None = None


def get_inference(enabled: bool = True) -> PyKEENInference:
    """Get singleton PyKEEN inference instance."""
    global _inference
    if _inference is None:
        _inference = PyKEENInference(enabled=enabled)
    return _inference


def set_inference_enabled(enabled: bool) -> None:
    """Enable or disable PyKEEN inference globally."""
    global _inference
    if _inference is None:
        _inference = PyKEENInference(enabled=enabled)
    else:
        _inference.enabled = enabled
