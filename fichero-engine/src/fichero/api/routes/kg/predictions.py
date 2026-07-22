"""Heuristic prediction generator + run listing + application.

Companion to ``kg_pykeen.py`` (which handles PyKEEN training/predict).
The heuristic endpoint here is the cheap embedding-similarity fallback
when no trained PyKEEN model is available — same surface, different
backend, so the curation loop has something to show on day one.

Ported from the deprecated ``/api/knowledge-graph/predictions/*``
endpoints. Lives under ``/api/kg/predictions``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.models.knowledge import (
    ClaimRelationType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgePredictionRun,
)
from fichero.models import KGPredictionListResponse

router = APIRouter(prefix="/kg/predictions")
logger = logging.getLogger(__name__)

KG_CLAIM_EMBEDDINGS_TABLE = "kg_claim_embeddings"


def _ensure_pykeen_compat() -> None:
    """Install the load_directory compat shim if this PyKEEN version lacks it.

    Older PyKEEN distributions write trained_model.pkl directly without a
    directory-loader class method. This shim is installed lazily (on first
    route use) so the heavy torch/pykeen deps don't load at server start.
    """
    import pykeen.models  # noqa: PLC0415
    import torch  # noqa: PLC0415

    if not hasattr(pykeen.models.Model, "load_directory"):

        @classmethod  # type: ignore[misc]
        def _load_directory_compat(cls, directory: str):
            model_file = Path(directory) / "trained_model.pkl"
            if not model_file.exists():
                raise FileNotFoundError(f"trained_model.pkl not found in {directory}")
            return torch.load(model_file, map_location="cpu", weights_only=True)

        pykeen.models.Model.load_directory = _load_directory_compat


def _prediction_artifacts_dir(db: Database) -> Path:
    """Directory used to persist PyKEEN run artifacts for this library."""
    artifacts_dir = Path(db.path).parent / "knowledge-predictions"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir


def _build_minimal_pykeen_triples(
    claims: list[KnowledgeClaim],
    claim_links: list[KnowledgeClaimLink],
) -> list[tuple[str, str, str]]:
    """Build a compact training graph from claim/entity/link data.

    Claims whose metadata flags them as confidential/private/secret are
    excluded — ML training never sees them. See
    ``test_knowledge_graph_security::TestTripleBuildingSecurity``.
    """
    triples: list[tuple[str, str, str]] = []
    for claim in claims:
        sensitivity = str((claim.metadata or {}).get("sensitivity", "confidential")).lower()
        if sensitivity in {"confidential", "private", "secret"}:
            continue
        entity_ids = sorted(set(claim.entity_ids))
        for eid in entity_ids:
            triples.append((claim.id, "mentions", eid))
        for i, left in enumerate(entity_ids):
            for right in entity_ids[i + 1:]:
                triples.append((left, "co_occurs_with", right))
                triples.append((right, "co_occurs_with", left))
    for link in claim_links:
        triples.append((
            link.claim_id,
            f"claim_{link.relation_type.value}",
            link.related_claim_id,
        ))
    return list(dict.fromkeys(triples))


class HeuristicPredictionItem(BaseModel):
    source_claim_id: str
    target_claim_id: str
    similarity_score: float
    method: str


class HeuristicPredictionsResponse(BaseModel):
    predictions: list[HeuristicPredictionItem]
    method: str
    claims_embedded: int


class HeuristicRequest(BaseModel):
    top_k: int = Field(default=10, ge=1, le=100)
    entity_id: str | None = None


class ApplyPredictionsResponse(BaseModel):
    applied: int
    total_predictions_evaluated: int
    min_confidence_threshold: float
    relation_types: list[str]


@router.post("/heuristic", response_model=HeuristicPredictionsResponse)
async def generate_heuristic_predictions(
    request: HeuristicRequest,
    db: Database = Depends(get_library_database),
) -> HeuristicPredictionsResponse:
    """Generate cheap candidate links via embedding similarity.

    Requires claims to be embedded first via
    ``POST /kg/claim-search/embed``.
    """
    if KG_CLAIM_EMBEDDINGS_TABLE not in db._lance_tables():
        raise HTTPException(
            status_code=503,
            detail="Claims not embedded. POST /kg/claim-search/embed first.",
        )

    all_claims = db.all(KnowledgeClaim)
    existing_links = db.all(KnowledgeClaimLink)
    linked_pairs: set[tuple[str, str]] = set()
    for link in existing_links:
        linked_pairs.add((link.claim_id, link.related_claim_id))
        linked_pairs.add((link.related_claim_id, link.claim_id))

    out: list[dict[str, Any]] = []
    for claim in all_claims:
        try:
            qv = await db._embed_text_async(claim.text, role="passage")  # type: ignore[attr-defined]
        except Exception as exc:
            logger.exception("Failed to embed claim %s for heuristic predictions", claim.id)
            raise HTTPException(
                status_code=503,
                detail=f"Failed to embed claim {claim.id} for heuristic predictions",
            ) from exc
        similar = db.search_vectors(
            KG_CLAIM_EMBEDDINGS_TABLE, qv, limit=request.top_k + 1
        )
        for r in similar:
            other_id = r["id"]
            if other_id == claim.id:
                continue
            if (claim.id, other_id) in linked_pairs:
                continue
            if request.entity_id:
                other = db.get(KnowledgeClaim, other_id)
                if not other or request.entity_id not in other.entity_ids:
                    continue
            out.append({
                "source_claim_id": claim.id,
                "target_claim_id": other_id,
                "similarity_score": r.get("_score", 0.0),
                "method": "heuristic",
            })

    out.sort(key=lambda p: p["similarity_score"], reverse=True)
    return HeuristicPredictionsResponse(
        predictions=[HeuristicPredictionItem(**p) for p in out[: request.top_k * 5]],
        method="heuristic",
        claims_embedded=len(all_claims),
    )


@router.get("", response_model=KGPredictionListResponse)
async def list_prediction_runs(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_library_database),
) -> list[KnowledgePredictionRun]:
    """List PyKEEN prediction runs (newest first)."""
    runs = db.all(KnowledgePredictionRun)
    if status:
        runs = [r for r in runs if r.status == status]
    runs.sort(key=lambda r: r.trained_at, reverse=True)
    return KGPredictionListResponse(items=runs[:limit], count=len(runs[:limit]))


@router.post("/{run_id}/apply", response_model=ApplyPredictionsResponse)
async def apply_prediction_run(
    run_id: str,
    min_confidence: float = Query(default=0.7, ge=0.0, le=1.0),
    max_links: int = Query(default=100, ge=1, le=1000),
    db: Database = Depends(get_library_database_for_write),
) -> ApplyPredictionsResponse:
    """Apply a prediction run's top-scoring predictions as claim links."""
    try:
        import pykeen.models  # noqa: PLC0415
        from pykeen.predict import predict_target  # noqa: PLC0415
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="PyKEEN link prediction is not installed in this backend.",
        ) from exc

    _ensure_pykeen_compat()

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
        raise HTTPException(status_code=500, detail=f"Failed to load PyKEEN model: {exc}") from exc

    all_claims = db.all(KnowledgeClaim)
    claim_ids = [c.id for c in all_claims]
    existing_links = db.all(KnowledgeClaimLink)
    linked_pairs: set[tuple[str, str]] = {
        tuple(sorted((link.claim_id, link.related_claim_id))) for link in existing_links
    }

    candidate_relations = [
        rel for rel in ("claim_supports", "claim_refines", "claim_contradicts", "mentions")
        if rel in trained_model.triples_factory.relation_to_id
    ]
    if not candidate_relations:
        raise HTTPException(status_code=400, detail="No valid relations found in trained model.")

    relation_map = {
        "claim_supports": ClaimRelationType.supports,
        "claim_refines": ClaimRelationType.refines,
        "claim_contradicts": ClaimRelationType.contradicts,
        "mentions": ClaimRelationType.supports,
    }

    new_links: list[KnowledgeClaimLink] = []
    seen: set[tuple[str, str]] = set()
    for claim in all_claims:
        if len(new_links) >= max_links:
            break
        for relation in candidate_relations:
            if len(new_links) >= max_links:
                break
            try:
                preds = predict_target(
                    trained_model,
                    head=claim.id,
                    relation=relation,
                    targets=claim_ids,
                    triples_factory=trained_model.triples_factory,
                )
            except Exception:
                continue
            for row in preds.df.itertuples(index=False):
                target_id = row.tail_label
                if target_id == claim.id:
                    continue
                pair = tuple(sorted((claim.id, target_id)))
                if pair in seen or pair in linked_pairs:
                    continue
                score = float(row.score)
                if score < min_confidence:
                    continue
                seen.add(pair)
                new_links.append(KnowledgeClaimLink(
                    claim_id=claim.id,
                    related_claim_id=target_id,
                    relation_type=relation_map.get(relation, ClaimRelationType.related_to),
                    link_quality=round(score, 4),
                    metadata={
                        "source": "pykeen_prediction",
                        "run_id": run_id,
                        "predicted_relation": relation,
                        "pykeen_score": score,
                    },
                ))

    for link in new_links:
        db.save(link)

    return ApplyPredictionsResponse(
        applied=len(new_links),
        total_predictions_evaluated=len(all_claims) * len(candidate_relations),
        min_confidence_threshold=min_confidence,
        relation_types=candidate_relations,
    )
