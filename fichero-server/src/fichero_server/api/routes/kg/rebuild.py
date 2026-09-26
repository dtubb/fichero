"""Knowledge graph rebuild routes.

Exposes the ``fichero_server.knowledge.rebuild`` helper as an HTTP endpoint so a
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

# #4982: `POST /kg/reset` (a bulk, unaudited, unfiltered, unconfirmed delete
# of every KnowledgeEntity/KnowledgeClaim/KnowledgeClaimLink row, curated or
# not) lived here and is DELETED, not repaired. It could never actually run
# — it called `db.delete(Model, id)` with two arguments against a
# one-argument method, and its only test passed by faking that wrong
# signature. Per the safety-net spec (`docs/contributor_manual/specs/safety/
# safety-net.md` §E, `safety.net.reset-never-touches-curated-work`): a real
# reset, when it exists, is an audited `kg.reset` action that touches only
# machine-made/uncurated rows by default, snapshots first, is confirmable
# and undoable as one step, and is owner-only in a shared library.


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
    from fichero_server.knowledge.rebuild import rebuild_kg as do_rebuild

    req = request or RebuildRequest()
    stats = do_rebuild(db, vectors=req.vectors, triples=req.triples)
    return RebuildResponse(**stats)
