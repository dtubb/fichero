"""Claim semantic search — embed + query + similar.

Ported from the deprecated ``/api/knowledge-graph/claims/semantic*`` and
``/api/knowledge-graph/claims/{id}/similar`` endpoints. Lives under
``/api/kg/claim-search`` so it groups with the rest of the KG surface
in OpenAPI codegen.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.db.embeddings import KG_CLAIM_EMBEDDINGS_TABLE
from fichero.models import KGGraphListResponse
from fichero.models.knowledge import (
    ClaimCurationState,
    ClaimType,
    KnowledgeClaim,
)

router = APIRouter(prefix="/kg/claim-search")

class EmbedClaimsResponse(BaseModel):
    embedded: int
    table: str


class _EmbedClaimRequest(BaseModel):
    claim_ids: list[str] | None = None


def _vector_similarity(row: dict) -> float:
    """Return a stable similarity score from LanceDB row metadata."""
    if row.get("_score") is not None:
        return float(row["_score"])
    distance = row.get("_distance")
    if distance is None:
        return 0.0
    value = 1.0 - (float(distance) ** 2) / 2.0
    return max(-1.0, min(1.0, value))


def _embed_claims_sync(db: Database, claims: list[KnowledgeClaim]) -> int:
    """CPU-bound work for embed_claims. Runs off the event loop."""
    return db.embed_claims(claims)


def search_claims_semantic_impl(
    *,
    db: Database,
    q: str,
    claim_type: ClaimType | None = None,
    curation_state: ClaimCurationState | None = None,
    limit: int = 20,
) -> KGGraphListResponse:
    """Shared semantic claim retrieval for the route and /api/search."""
    if KG_CLAIM_EMBEDDINGS_TABLE not in db._lance_tables():
        raise HTTPException(
            status_code=503,
            detail="Claim embeddings not yet indexed. POST /kg/claim-search/embed first.",
        )

    try:
        query_vector = db._embed_text(q)  # type: ignore[attr-defined]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Embedding generation failed: {exc}") from exc

    results = db.search_vectors(KG_CLAIM_EMBEDDINGS_TABLE, query_vector, limit=limit)
    claim_ids = [r["id"] for r in results]
    if not claim_ids:
        return KGGraphListResponse(items=[], count=0)

    claims = {c.id: c for c in db.all(KnowledgeClaim) if c.id in claim_ids}
    score_map = {r["id"]: _vector_similarity(r) for r in results}
    items = [
        {**claims[cid].model_dump(), "similarity_score": score_map.get(cid, 0.0)}
        for cid in claim_ids
        if cid in claims
        and (claim_type is None or claims[cid].claim_type == claim_type)
        and (curation_state is None or claims[cid].curation_state == curation_state)
    ]
    return KGGraphListResponse(items=items, count=len(items))


@router.post("/embed", response_model=EmbedClaimsResponse)
async def embed_claims(
    request: _EmbedClaimRequest | None = None,
    db: Database = Depends(get_library_database_for_write),
) -> EmbedClaimsResponse:
    """Embed claims into LanceDB for semantic search.

    Runs the synchronous FastEmbed batch in a worker thread so the FastAPI
    event loop stays responsive — same fix as the entity-curation peer (#1004).
    """
    if request and request.claim_ids:
        claims = [db.get(KnowledgeClaim, cid) for cid in request.claim_ids]
        claims = [c for c in claims if c is not None]
    else:
        claims = db.all(KnowledgeClaim)

    if not claims:
        return EmbedClaimsResponse(embedded=0, table=KG_CLAIM_EMBEDDINGS_TABLE)

    embedded = await asyncio.to_thread(_embed_claims_sync, db, claims)
    return EmbedClaimsResponse(embedded=embedded, table=KG_CLAIM_EMBEDDINGS_TABLE)


@router.get("", response_model=KGGraphListResponse)
async def search_claims_semantic(
    q: str = Query(..., description="Natural language query"),
    claim_type: ClaimType | None = Query(default=None),
    curation_state: ClaimCurationState | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_library_database),
) -> KGGraphListResponse:
    """Semantic claim search via LanceDB cosine similarity."""
    return search_claims_semantic_impl(
        db=db,
        q=q,
        claim_type=claim_type,
        curation_state=curation_state,
        limit=limit,
    )


@router.get("/{claim_id}/similar", response_model=KGGraphListResponse)
async def find_similar_claims(
    claim_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    db: Database = Depends(get_library_database),
) -> KGGraphListResponse:
    """Find claims similar to a given claim (excludes the claim itself)."""
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")
    if KG_CLAIM_EMBEDDINGS_TABLE not in db._lance_tables():
        raise HTTPException(status_code=503, detail="Claims not embedded yet.")

    try:
        query_vector = await db._embed_text_async(claim.text, role="passage")  # type: ignore[attr-defined]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Embedding failed: {exc}") from exc

    results = db.search_vectors(KG_CLAIM_EMBEDDINGS_TABLE, query_vector, limit=limit + 1)
    results = [r for r in results if r["id"] != claim_id]
    ids = [r["id"] for r in results]
    claim_map = {c.id: c for c in db.all(KnowledgeClaim) if c.id in ids}
    score_map = {r["id"]: _vector_similarity(r) for r in results}
    items = [
        {**claim_map[rid].model_dump(), "similarity_score": score_map.get(rid, 0.0)}
        for rid in ids
        if rid in claim_map
    ][:limit]
    return KGGraphListResponse(items=items, count=len(items))
