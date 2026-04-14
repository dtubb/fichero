"""Knowledge graph prediction routes (PyKEEN training + heuristic embedding similarity)."""

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pykeen
import pykeen.models
import torch
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pykeen.pipeline import pipeline
from pykeen.predict import predict_target
from pykeen.triples import TriplesFactory

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    ClaimRelationType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    KnowledgePredictionRun,
    PredictionModelType,
)
from fichero.api.routes.knowledge_graph._shared import KG_CLAIM_EMBEDDINGS_TABLE

# PyKEEN compat shim for older versions without Model.load_directory
if not hasattr(pykeen.models.Model, "load_directory"):

    @classmethod  # type: ignore[misc]
    def _load_directory_compat(cls, directory: str):
        """Compatibility shim for PyKEEN versions without Model.load_directory."""
        model_file = Path(directory) / "trained_model.pkl"
        if not model_file.exists():
            raise FileNotFoundError(f"trained_model.pkl not found in {directory}")
        return torch.load(model_file, map_location="cpu")

    pykeen.models.Model.load_directory = _load_directory_compat

router = APIRouter()


class HeuristicPredictionItem(BaseModel):
    source_claim_id: str
    target_claim_id: str
    similarity_score: float
    method: str


class HeuristicPredictionsResponse(BaseModel):
    predictions: list[HeuristicPredictionItem]
    method: str
    claims_embedded: int


class ApplyPredictionsResponse(BaseModel):
    applied: int
    total_predictions_evaluated: int
    min_confidence_threshold: float
    relation_types: list[str]


class PredictionGenerateHeuristicRequest(BaseModel):
    """Generate heuristic link predictions based on embedding similarity."""

    top_k: int = Field(default=10, ge=1, le=100)
    entity_id: str | None = None


class PredictionGeneratePyKEENRequest(BaseModel):
    """Train a PyKEEN model and generate predictions."""

    model_type: PredictionModelType = PredictionModelType.transe
    training_epochs: int = Field(default=100, ge=1, le=1000)
    learning_rate: float = Field(default=0.001, ge=0.0001, le=1.0)
    batch_size: int = Field(default=256, ge=8, le=1024)


def _build_minimal_pykeen_triples(
    claims: list[KnowledgeClaim],
    claim_links: list[KnowledgeClaimLink],
) -> list[tuple[str, str, str]]:
    """Build a compact training graph from existing claim/entity/link data."""
    triples: list[tuple[str, str, str]] = []

    for claim in claims:
        sensitivity = str((claim.metadata or {}).get("sensitivity", "confidential")).lower()
        if sensitivity in {"confidential", "private", "secret"}:
            continue

        entity_ids = sorted(set(claim.entity_ids))
        for entity_id in entity_ids:
            triples.append((claim.id, "mentions", entity_id))

        for index, left_entity_id in enumerate(entity_ids):
            for right_entity_id in entity_ids[index + 1 :]:
                triples.append((left_entity_id, "co_occurs_with", right_entity_id))
                triples.append((right_entity_id, "co_occurs_with", left_entity_id))

    for claim_link in claim_links:
        triples.append(
            (
                claim_link.claim_id,
                f"claim_{claim_link.relation_type.value}",
                claim_link.related_claim_id,
            )
        )

    return list(dict.fromkeys(triples))


def _extract_pykeen_metrics(result: Any) -> dict[str, float | None]:
    """Extract realistic ranking metrics from a PyKEEN pipeline result."""
    metrics = result.metric_results.to_dict()
    realistic = metrics.get("both", {}).get("realistic", {})
    return {
        "mrr": realistic.get("inverse_harmonic_mean_rank"),
        "hits_at_10": realistic.get("hits_at_10"),
        "hits_at_5": realistic.get("hits_at_5"),
        "hits_at_1": realistic.get("hits_at_1"),
    }


def _prediction_artifacts_dir(db: Database) -> Path:
    """Return the directory used to persist PyKEEN run artifacts."""
    artifacts_dir = Path(db.path).parent / "knowledge-predictions"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir


def _build_claim_link_prediction_preview(
    result: Any,
    triples_factory: TriplesFactory,
    claims: list[KnowledgeClaim],
    claim_links: list[KnowledgeClaimLink],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Create lightweight candidate links from real PyKEEN scores."""
    linked_pairs: set[tuple[str, str]] = set()
    for claim_link in claim_links:
        linked_pairs.add((claim_link.claim_id, claim_link.related_claim_id))
        linked_pairs.add((claim_link.related_claim_id, claim_link.claim_id))

    claim_ids = [claim.id for claim in claims]
    candidate_relations = [
        relation
        for relation in (
            "claim_supports",
            "claim_refines",
            "claim_contradicts",
            "mentions",
        )
        if relation in triples_factory.relation_to_id
    ]
    if not candidate_relations:
        return []

    candidates: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for claim in claims:
        predictions = predict_target(
            result.model,
            head=claim.id,
            relation=candidate_relations[0],
            triples_factory=triples_factory,
            targets=claim_ids,
        )
        for row in predictions.df.itertuples(index=False):
            target_claim_id = row.tail_label
            if target_claim_id == claim.id:
                continue
            pair = tuple(sorted((claim.id, target_claim_id)))
            if pair in seen_pairs or (claim.id, target_claim_id) in linked_pairs:
                continue
            seen_pairs.add(pair)
            candidates.append(
                {
                    "source_claim_id": claim.id,
                    "target_claim_id": target_claim_id,
                    "predicted_relation": "supports",
                    "score": round(float(row.score), 6),
                }
            )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:top_k]


@router.post("/predictions/generate/pykeen", response_model=KnowledgePredictionRun)
async def generate_pykeen_predictions(
    request: PredictionGeneratePyKEENRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgePredictionRun:
    """Train a minimal PyKEEN pipeline and persist run metadata."""
    claims = db.all(KnowledgeClaim)
    if not claims:
        raise HTTPException(
            status_code=400,
            detail="Cannot train predictions: no knowledge claims found.",
        )

    entities = db.all(KnowledgeEntity)
    if not entities:
        raise HTTPException(
            status_code=400,
            detail="Cannot train predictions: no knowledge entities found.",
        )

    claim_links = db.all(KnowledgeClaimLink)
    triples = _build_minimal_pykeen_triples(claims, claim_links)
    if not triples:
        raise HTTPException(
            status_code=400,
            detail="Cannot train predictions: no graph triples derived from claims/entities.",
        )

    relation_types = sorted({relation for _, relation, _ in triples})
    triples_array = np.array(triples, dtype=str)
    triples_factory = TriplesFactory.from_labeled_triples(triples_array)
    model_name = {
        PredictionModelType.transe: "TransE",
        PredictionModelType.rotate: "RotatE",
        PredictionModelType.complex: "ComplEx",
        PredictionModelType.hermite: "HolE",
    }[request.model_type]

    try:
        result = pipeline(
            training=triples_factory,
            testing=triples_factory,
            validation=triples_factory,
            model=model_name,
            epochs=request.training_epochs,
            training_kwargs={"batch_size": request.batch_size},
            optimizer_kwargs={"lr": request.learning_rate},
            random_seed=42,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"PyKEEN training failed: {exc}"
        ) from exc

    metrics = _extract_pykeen_metrics(result)
    prediction_preview = _build_claim_link_prediction_preview(
        result, triples_factory, claims, claim_links
    )

    artifact_dir = (
        _prediction_artifacts_dir(db)
        / f"pykeen-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )
    result.save_to_directory(str(artifact_dir))

    run = KnowledgePredictionRun(
        model_type=request.model_type,
        pykeen_config={
            "model_type": request.model_type.value,
            "pykeen_model": model_name,
            "training_epochs": request.training_epochs,
            "learning_rate": request.learning_rate,
            "batch_size": request.batch_size,
            "pipeline_mode": "pykeen",
        },
        trained_at=datetime.now(),
        num_entities=len(entities),
        num_claims=len(claims),
        num_relation_types=len(relation_types),
        mrr=metrics["mrr"],
        hits_at_10=metrics["hits_at_10"],
        hits_at_5=metrics["hits_at_5"],
        hits_at_1=metrics["hits_at_1"],
        model_path=str(artifact_dir),
        status="trained",
        metadata={
            "training_triples": len(triples),
            "relation_types": relation_types,
            "prediction_preview": prediction_preview,
            "prediction_preview_count": len(prediction_preview),
        },
    )
    db.save(run)
    return run


@router.post("/predictions/generate/heuristic")
async def generate_heuristic_predictions(
    request: PredictionGenerateHeuristicRequest,
    db: Database = Depends(get_library_database),
) -> HeuristicPredictionsResponse:
    """Generate heuristic predictions using embedding similarity."""
    if KG_CLAIM_EMBEDDINGS_TABLE not in db._lance_tables():
        raise HTTPException(
            status_code=503,
            detail="Claims not embedded. POST /claims/semantic/embed first.",
        )

    all_claims = db.all(KnowledgeClaim)
    existing_links = db.all(KnowledgeClaimLink)
    linked_pairs: set[tuple[str, str]] = set()
    for link in existing_links:
        linked_pairs.add((link.claim_id, link.related_claim_id))
        linked_pairs.add((link.related_claim_id, link.claim_id))

    predictions: list[dict[str, Any]] = []
    for claim in all_claims:
        try:
            query_vector = db._embed_text(claim.text)  # type: ignore[attr-defined]
        except Exception:
            continue

        similar = db.search_vectors(
            KG_CLAIM_EMBEDDINGS_TABLE, query_vector, limit=request.top_k + 1
        )
        for result in similar:
            other_id = result["id"]
            if other_id == claim.id:
                continue
            if (claim.id, other_id) in linked_pairs:
                continue
            if request.entity_id:
                other = db.get(KnowledgeClaim, other_id)
                if not other or request.entity_id not in other.entity_ids:
                    continue
            predictions.append(
                {
                    "source_claim_id": claim.id,
                    "target_claim_id": other_id,
                    "similarity_score": result.get("_score", 0.0),
                    "method": "heuristic",
                }
            )

    predictions.sort(key=lambda p: p["similarity_score"], reverse=True)
    return HeuristicPredictionsResponse(
        predictions=[
            HeuristicPredictionItem(**p) for p in predictions[: request.top_k * 5]
        ],
        method="heuristic",
        claims_embedded=len(all_claims),
    )


@router.get("/predictions", response_model=list[KnowledgePredictionRun])
async def list_predictions(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_library_database),
) -> list[KnowledgePredictionRun]:
    """List PyKEEN prediction runs."""
    runs = db.all(KnowledgePredictionRun)
    if status:
        runs = [r for r in runs if r.status == status]
    runs.sort(key=lambda r: r.trained_at, reverse=True)
    return runs[:limit]


@router.post("/predictions/{run_id}/apply")
async def apply_prediction(
    run_id: str,
    min_confidence: float = Query(default=0.7, ge=0.0, le=1.0),
    max_links: int = Query(default=100, ge=1, le=1000),
    db: Database = Depends(get_library_database),
) -> ApplyPredictionsResponse:
    """Apply a prediction run's top-scoring predictions as claim links."""
    run = db.get(KnowledgePredictionRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Prediction run not found: {run_id}")

    if run.status != "trained" or not run.model_path:
        raise HTTPException(
            status_code=400,
            detail=f"Run {run_id} is not ready for application (status: {run.status})",
        )

    model_path = Path(run.model_path)
    if not model_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Model artifact not found at {run.model_path}. Retrain the model.",
        )

    try:
        trained_model = pykeen.models.Model.load_directory(str(model_path))
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to load PyKEEN model: {exc}"
        ) from exc

    all_claims = db.all(KnowledgeClaim)
    claim_ids = [c.id for c in all_claims]
    existing_links = db.all(KnowledgeClaimLink)
    linked_pairs: set[tuple[str, str]] = {
        tuple(sorted((link.claim_id, link.related_claim_id))) for link in existing_links
    }

    candidate_relations = [
        rel
        for rel in ("claim_supports", "claim_refines", "claim_contradicts", "mentions")
        if rel in trained_model.triples_factory.relation_to_id
    ]
    if not candidate_relations:
        raise HTTPException(
            status_code=400,
            detail="No valid relations found in trained model.",
        )

    new_links: list[KnowledgeClaimLink] = []
    seen_pairs: set[tuple[str, str]] = set()

    for claim in all_claims:
        if len(new_links) >= max_links:
            break

        for relation in candidate_relations:
            if len(new_links) >= max_links:
                break

            try:
                predictions = predict_target(
                    trained_model,
                    head=claim.id,
                    relation=relation,
                    targets=claim_ids,
                    triples_factory=trained_model.triples_factory,
                )
            except Exception:
                continue

            for row in predictions.df.itertuples(index=False):
                target_id = row.tail_label
                if target_id == claim.id:
                    continue
                pair = tuple(sorted((claim.id, target_id)))
                if pair in seen_pairs or pair in linked_pairs:
                    continue
                score = float(row.score)
                if score < min_confidence:
                    continue

                seen_pairs.add(pair)
                relation_type_map = {
                    "claim_supports": ClaimRelationType.supports,
                    "claim_refines": ClaimRelationType.refines,
                    "claim_contradicts": ClaimRelationType.contradicts,
                    "mentions": ClaimRelationType.related_to,
                }
                new_links.append(
                    KnowledgeClaimLink(
                        claim_id=claim.id,
                        related_claim_id=target_id,
                        relation_type=relation_type_map.get(
                            relation, ClaimRelationType.related_to
                        ),
                        link_quality=round(score, 4),
                        metadata={
                            "source": "pykeen_prediction",
                            "run_id": run_id,
                            "predicted_relation": relation,
                            "pykeen_score": score,
                        },
                    )
                )

    for link in new_links:
        db.save(link)

    return ApplyPredictionsResponse(
        applied=len(new_links),
        total_predictions_evaluated=len(all_claims) * len(candidate_relations),
        min_confidence_threshold=min_confidence,
        relation_types=candidate_relations,
    )
