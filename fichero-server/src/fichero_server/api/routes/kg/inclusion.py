"""Knowledge-graph inclusion scoping (library / folder / document).

Ported from the deprecated ``/api/knowledge-graph/inclusion``
endpoints. Declarative scope rules for which sources count when KG
queries roll up entities/claims. Lives under ``/api/kg/inclusion``.
"""

from __future__ import annotations

from pathlib import Path

from fichero_server.core.timeutil import utc_now

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import request_actor
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
    # #4831/#4843: kept on the wire for backwards compatibility with any
    # existing caller that still sends it, but its VALUE is never trusted --
    # `inclusion.upsert` (below) always records `ctx.actor` instead. A
    # forged value here must never reach the stored row; see
    # `test_routes_kg_inclusion.py::test_forged_updated_by_is_ignored`.
    updated_by: str = "human"


def upsert_inclusion_impl(
    db: Database, request: InclusionUpsertRequest, actor: str
) -> KnowledgeGraphInclusion:
    """Upsert an inclusion rule. Most-recent row wins per (scope, target).

    Extracted verbatim from the former bare route body (#4831, iterate-not-
    replace) so both the route and the `inclusion.upsert` action drive the
    SAME code. `actor` is the REAL actor (`ctx.actor`) -- `request.updated_by`
    is read nowhere here; see that field's own docstring.
    """
    existing = db.query(
        KnowledgeGraphInclusion,
        scope_type=request.scope_type,
        target_id=request.target_id,
    )
    now = utc_now()
    if existing:
        record = max(existing, key=lambda row: row.updated_at)
        record.included = request.included
        record.reason = request.reason
        record.updated_by = actor
        record.updated_at = now
    else:
        record = KnowledgeGraphInclusion(
            scope_type=request.scope_type,
            target_id=request.target_id,
            included=request.included,
            reason=request.reason,
            updated_by=actor,
            updated_at=now,
        )
    db.save(record)
    return record


def _invert_inclusion_upsert(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Replays the OLD field values through `inclusion.upsert` itself --
    there is no dedicated inclusion-delete/restore action, so a fresh INSERT
    (no `before` row) has nothing to revert to and stays non-invertible for
    that one call, the same idiom `_invert_merge`/`_invert_update_entity`
    (entity_curation.py / entities.py) use when their own before/after has
    nothing to restore."""
    if not before:
        return None
    return (
        "inclusion.upsert",
        {
            "scope_type": before["scope_type"],
            "target_id": before["target_id"],
            "included": before["included"],
            "reason": before.get("reason"),
        },
    )


@action(
    "inclusion.upsert",
    InclusionUpsertRequest,
    domains=["kg"],
    undoable=True,
    invert=_invert_inclusion_upsert,
)
def _action_upsert_inclusion(
    db: Database, params: InclusionUpsertRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    existing = db.query(
        KnowledgeGraphInclusion, scope_type=params.scope_type, target_id=params.target_id,
    )
    before = (
        max(existing, key=lambda row: row.updated_at).model_dump(mode="json")
        if existing
        else None
    )
    record = upsert_inclusion_impl(db, params, ctx.actor)
    spec = ChangeSpec(
        domains=["kg"],
        target_ids=[record.id],
        before=before,
        after=record.model_dump(mode="json"),
    )
    return record.model_dump(mode="json"), spec


@router.post("", response_model=KnowledgeGraphInclusion)
async def upsert_inclusion(
    request: InclusionUpsertRequest,
    db: Database = Depends(get_library_database_for_write),
    actor: str = Depends(request_actor),
) -> KnowledgeGraphInclusion:
    """Upsert an inclusion rule. Most-recent row wins per (scope, target)."""
    ctx = ActionContext(actor=actor, library_path=str(Path(db.path).parent))
    result = registry.invoke(
        db, "inclusion.upsert", request.model_dump(mode="json"), ctx
    )
    return KnowledgeGraphInclusion.model_validate(result.result)


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
