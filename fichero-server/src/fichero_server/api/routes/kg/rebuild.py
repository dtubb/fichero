"""Knowledge graph rebuild routes.

Exposes the ``fichero_server.kg.rebuild`` helper as an HTTP endpoint so a
caller can backfill entity vectors / refresh the RDF triple file
without re-running Catalogue. Useful after pulling a new engine
version that changed how vectors are computed.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from fichero_server.api.main import get_library_database_for_write
from fichero_server.db import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kg")


class KGResetResponse(BaseModel):
    """Counts of rows deleted by a KG reset."""
    entities_deleted: int
    claims_deleted: int
    links_deleted: int


@router.post(
    "/reset",
    response_model=KGResetResponse,
    summary="Wipe all KG rows so extraction can run fresh",
    description=(
        "Deletes every KnowledgeEntity, KnowledgeClaim, and KnowledgeClaimLink "
        "row in the library. Documents and Artifacts are not touched. "
        "Use before re-running Catalogue/Extract workflows to get a clean slate."
    ),
)
async def reset_kg(
    db: Database = Depends(get_library_database_for_write),
) -> KGResetResponse:
    """Delete all KG rows (entities, claims, links)."""
    from fichero_server.models.knowledge import KnowledgeEntity, KnowledgeClaim, KnowledgeClaimLink

    entities = db.query(KnowledgeEntity)
    claims = db.query(KnowledgeClaim)
    links = db.query(KnowledgeClaimLink)

    for e in entities:
        db.delete(KnowledgeEntity, e.id)
    for c in claims:
        db.delete(KnowledgeClaim, c.id)
    for lnk in links:
        db.delete(KnowledgeClaimLink, lnk.id)

    logger.info(
        "KG reset: %d entities, %d claims, %d links deleted",
        len(entities), len(claims), len(links),
    )
    return KGResetResponse(
        entities_deleted=len(entities),
        claims_deleted=len(claims),
        links_deleted=len(links),
    )


class RebuildRequest(BaseModel):
    """Toggle which derived stores get refreshed."""
    vectors: bool = True
    triples: bool = True


class RebuildResponse(BaseModel):
    """Stats describing what got refreshed."""
    entities: int
    claims: int
    entity_vectors_indexed: int
    claim_vectors_indexed: int
    triples_written: int


@router.post(
    "/rebuild",
    response_model=RebuildResponse,
    summary="Backfill KG derived stores",
    description=(
        "Rebuild the entity vector store (LanceDB) and/or the RDF "
        "triple file (kg.nt next to the DuckDB file) from the "
        "canonical KnowledgeEntity + KnowledgeClaim tables. "
        "Idempotent — safe to call repeatedly. Both stages run "
        "synchronously and the response carries counts. (#899)"
    ),
)
async def rebuild_kg(
    request: RebuildRequest | None = None,
    db: Database = Depends(get_library_database_for_write),
) -> RebuildResponse:
    """Backfill the KG derived stores from canonical DuckDB rows."""
    from fichero_server.kg.rebuild import rebuild_kg as do_rebuild

    req = request or RebuildRequest()
    stats = do_rebuild(db, vectors=req.vectors, triples=req.triples)
    return RebuildResponse(**stats)
