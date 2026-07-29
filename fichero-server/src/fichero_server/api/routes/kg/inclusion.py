"""Knowledge-graph inclusion scoping (library / folder / document).

Ported from the deprecated ``/api/knowledge-graph/inclusion``
endpoints. Declarative scope rules for which sources count when KG
queries roll up entities/claims. Lives under ``/api/kg/inclusion``.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models.knowledge import (
    InclusionScopeType,
    KnowledgeGraphInclusion,
)
from fichero_server.models import KGInclusionListResponse

router = APIRouter(prefix="/kg/inclusion")


class InclusionUpsertRequest(BaseModel):
    scope_type: InclusionScopeType
    target_id: str
    included: bool
    reason: str | None = None
    updated_by: str = "human"


@router.post("", response_model=KnowledgeGraphInclusion)
async def upsert_inclusion(
    request: InclusionUpsertRequest,
    db: Database = Depends(get_library_database_for_write),
) -> KnowledgeGraphInclusion:
    """Upsert an inclusion rule. Most-recent row wins per (scope, target)."""
    existing = db.query(
        KnowledgeGraphInclusion,
        scope_type=request.scope_type,
        target_id=request.target_id,
    )
    now = datetime.now()
    if existing:
        record = max(existing, key=lambda row: row.updated_at)
        record.included = request.included
        record.reason = request.reason
        record.updated_by = request.updated_by
        record.updated_at = now
    else:
        record = KnowledgeGraphInclusion(
            scope_type=request.scope_type,
            target_id=request.target_id,
            included=request.included,
            reason=request.reason,
            updated_by=request.updated_by,
            updated_at=now,
        )
    db.save(record)
    return record


@router.get("", response_model=KGInclusionListResponse)
async def list_inclusion(
    scope_type: InclusionScopeType | None = Query(default=None),
    target_id: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> list[KnowledgeGraphInclusion]:
    """List inclusion rules, optionally filtered by scope + target."""
    if scope_type and target_id:
        rows = db.query(KnowledgeGraphInclusion, scope_type=scope_type, target_id=target_id)
    elif scope_type:
        rows = db.query(KnowledgeGraphInclusion, scope_type=scope_type)
    elif target_id:
        rows = db.query(KnowledgeGraphInclusion, target_id=target_id)
    else:
        rows = db.all(KnowledgeGraphInclusion)
    rows.sort(key=lambda row: row.updated_at, reverse=True)
    return KGInclusionListResponse(items=rows, count=len(rows))
