"""Knowledge graph triangulation routes (#900).

Surfaces the cross-source support counts computed by
``fichero_server.knowledge.triangulation`` so the inspector UI can display
"triangulated (6 sources)" badges next to claims.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models import MutationListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kg/triangulation")


class TripleSupportResponse(BaseModel):
    """One triangulated triple — the SVO + the supporting source list."""
    subject_id: str
    predicate: str
    object_text: str
    support_count: int
    weighted_support: float  # #903 — scaled by SourceAuthority
    corroboration: str  # "single-source" | "corroborated" | "triangulated"
    source_document_ids: list[str]
    claim_ids: list[str]


@router.get(
    "/entity/{entity_id}",
    response_model=MutationListResponse,
    summary="Triangulated triples for one entity",
    description=(
        "Return every (subject, predicate, object) triple where the "
        "entity appears as subject, with a support_count of how many "
        "distinct source documents assert the same fact. Sorted by "
        "descending support_count. (#900)"
    ),
)
async def entity_triangulation(
    entity_id: str,
    db: Database = Depends(get_library_database),
) -> MutationListResponse:
    """Triples for a single entity, sorted by corroboration strength."""
    from fichero_server.knowledge.triangulation import triples_for_entity

    items = [
        TripleSupportResponse(
            subject_id=t.key.subject_id,
            predicate=t.key.predicate,
            object_text=t.key.object_text,
            support_count=t.support_count,
            weighted_support=t.weighted_support,
            corroboration=t.corroboration,
            source_document_ids=list(t.source_document_ids),
            claim_ids=list(t.claim_ids),
        )
        for t in triples_for_entity(db, entity_id)
    ]


    return MutationListResponse(items=items, count=len(items))


@router.get(
    "",
    response_model=MutationListResponse,
    summary="Triangulated facts across the library",
    description=(
        "Return triples whose weighted support meets the threshold "
        "(default 3.0 = triangulated). Use this to surface the most "
        "strongly-attested facts in the corpus."
    ),
)
async def library_triangulation(
    threshold: float = Query(
        default=3.0,
        ge=1,
        description="Minimum weighted support required.",
    ),
    db: Database = Depends(get_library_database),
) -> MutationListResponse:
    """Corpus-wide triangulated facts."""
    from fichero_server.knowledge.triangulation import triangulated_facts

    items = [
        TripleSupportResponse(
            subject_id=t.key.subject_id,
            predicate=t.key.predicate,
            object_text=t.key.object_text,
            support_count=t.support_count,
            weighted_support=t.weighted_support,
            corroboration=t.corroboration,
            source_document_ids=list(t.source_document_ids),
            claim_ids=list(t.claim_ids),
        )
        for t in triangulated_facts(db, threshold=threshold)
    ]


    return MutationListResponse(items=items, count=len(items))


class RecomputeResponse(BaseModel):
    """Result of a triangulation recompute run."""
    claims_updated: int
    message: str


@router.post(
    "/recompute",
    response_model=RecomputeResponse,
    summary="Persist global support counts onto claims",
    description=(
        "Re-run cross-source triangulation across all KG claims and "
        "write the computed support_count back onto each KnowledgeClaim "
        "row (corroboration_count + corroborating_source_ids). "
        "Idempotent — safe to call repeatedly. (#900)"
    ),
)
async def recompute_triangulation(
    db: Database = Depends(get_library_database_for_write),
) -> RecomputeResponse:
    """Persist corpus-wide support counts back onto claim rows."""
    from fichero_server.knowledge.triangulation import persist_support_counts

    updated = persist_support_counts(db)
    return RecomputeResponse(
        claims_updated=updated,
        message=(
            f"Triangulation recomputed: {updated} claim(s) updated."
        ),
    )
