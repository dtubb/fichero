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

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import KGGraphListResponse
from fichero.knowledge_models import (
    ClaimCurationState,
    ClaimType,
    KnowledgeClaim,
)

router = APIRouter(prefix="/kg/claim-search")

KG_CLAIM_EMBEDDINGS_TABLE = "kg_claim_embeddings"


class EmbedClaimsResponse(BaseModel):
    embedded: int
    table: str


class _EmbedClaimRequest(BaseModel):
    claim_ids: list[str] | None = None


def _embed_claims_sync(db: Database, claims: list[KnowledgeClaim]) -> int:
    """CPU-bound work for embed_claims. Runs off the event loop."""
    texts = [c.text for c in claims]
    vectors = db._embed_texts(texts)  # type: ignore[attr-defined]
    records = [
        {
            "id": c.id,
            "text": c.text,
            "vector": v,
            "claim_type": c.claim_type.value if c.claim_type else None,
        }
        for c, v in zip(claims, vectors)
    ]
    db.save_vectors(KG_CLAIM_EMBEDDINGS_TABLE, records)
    return len(records)


@router.post("/embed", response_model=EmbedClaimsResponse)
async def embed_claims(
    request: _EmbedClaimRequest | None = None,
    db: Database = Depends(get_library_database),
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
    score_map = {r["id"]: r.get("_score", 0.0) for r in results}
    items = [
        {**claims[cid].model_dump(), "similarity_score": score_map.get(cid, 0.0)}
        for cid in claim_ids
        if cid in claims
        and (claim_type is None or claims[cid].claim_type == claim_type)
        and (curation_state is None or claims[cid].curation_state == curation_state)
    ]
    return KGGraphListResponse(items=items, count=len(items))


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
        query_vector = db._embed_text(claim.text)  # type: ignore[attr-defined]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Embedding failed: {exc}") from exc

    results = db.search_vectors(KG_CLAIM_EMBEDDINGS_TABLE, query_vector, limit=limit + 1)
    results = [r for r in results if r["id"] != claim_id]
    ids = [r["id"] for r in results]
    claim_map = {c.id: c for c in db.all(KnowledgeClaim) if c.id in ids}
    score_map = {r["id"]: r.get("_score", 0.0) for r in results}
    items = [
        {**claim_map[rid].model_dump(), "similarity_score": score_map.get(rid, 0.0)}
        for rid in ids
        if rid in claim_map
    ][:limit]
    return KGGraphListResponse(items=items, count=len(items))
