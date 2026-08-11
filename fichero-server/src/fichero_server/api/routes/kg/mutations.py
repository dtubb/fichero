"""KG mutation log + undo (#901)."""

from __future__ import annotations

import logging
from datetime import datetime
from fichero_server.core.timeutil import utc_now
from typing import Any

from fichero_server.api.auth import request_actor
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models.knowledge import (
    KnowledgeClaim,
    KnowledgeEntity,
    MutationLog,
    MutationOperationType,
)
from fichero_server.models import MutationListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kg/mutations")


class MutationRow(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    operation: str
    changed_fields: list[str] | None
    created_by: str
    created_at: datetime
    reversal_id: str | None


@router.get(
    "",
    response_model=MutationListResponse,
    summary="List recent KG mutations (newest first)",
    description="Recent entity/claim edits + deletes for undo. (#901)",
)
async def list_mutations(
    limit: int = Query(default=50, ge=1, le=500),
    db: Database = Depends(get_library_database),
) -> MutationListResponse:
    rows = db.query(MutationLog)
    rows.sort(key=lambda m: m.created_at, reverse=True)
    rows = rows[:limit]
    items = [
        MutationRow(
            id=m.id,
            entity_type=m.entity_type,
            entity_id=m.entity_id,
            operation=m.operation.value if hasattr(m.operation, "value") else str(m.operation),
            changed_fields=m.changed_fields,
            created_by=m.created_by,
            created_at=m.created_at,
            reversal_id=m.reversal_id,
        )
        for m in rows
    ]

    return MutationListResponse(items=items, count=len(items))


class UndoResponse(BaseModel):
    mutation_id: str
    reversal_mutation_id: str
    restored_entity_id: str | None


@router.post(
    "/{mutation_id}/undo",
    response_model=UndoResponse,
    summary="Reverse a previous KG mutation",
    description=(
        "Restores the before-state of a previously-logged mutation. "
        "Writes a new ``restore``-type MutationLog row pointing back "
        "at the original via reversal_id, so the undo itself is "
        "auditable. (#901)"
    ),
)
async def undo_mutation(
    mutation_id: str,
    db: Database = Depends(get_library_database_for_write),
    actor: str = Depends(request_actor),
) -> UndoResponse:
    log = db.get(MutationLog, mutation_id)
    if log is None:
        raise HTTPException(status_code=404, detail=f"Mutation not found: {mutation_id}")
    if log.reversal_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Mutation already reversed by {log.reversal_id}",
        )
    if log.before_state is None:
        # Create operations have no before-state to restore. (They
        # could be inverted by deleting the entity, but that's the
        # caller's responsibility — explicit DELETE goes through the
        # entity router.)
        raise HTTPException(
            status_code=400,
            detail="Cannot undo a create — call DELETE instead",
        )

    # Materialise the before-state as the appropriate model and save.
    model_cls = _model_for(log.entity_type)
    if model_cls is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported entity_type for undo: {log.entity_type}",
        )

    restored: Any = model_cls.model_validate(log.before_state)
    restored.updated_at = utc_now()
    db.save(restored)

    # Refresh the LanceDB vector for restored entities.
    if log.entity_type == "KnowledgeEntity":
        try:
            from fichero_server.knowledge import entity_vectors
            entity_vectors.index_entity(
                db=db,
                entity_id=restored.id,
                entity_type=restored.entity_type,
                canonical_name=restored.canonical_name,
                description=restored.description,
            )
        except Exception as exc:
            logger.warning("undo_mutation: vector refresh failed: %s", exc)

    # Write the reversal entry and link it back.
    reversal = MutationLog(
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        operation=MutationOperationType.restore,
        before_state=log.after_state,
        after_state=log.before_state,
        reversal_id=log.id,
        # #4415: an undo is itself an edit, and whoever performed it must be
        # named — a reversal recorded as an anonymous 'human' is exactly the
        # attribution hole this closes.
        created_by=actor,
    )
    db.save(reversal)

    # Mark the original as reversed.
    log.reversal_id = reversal.id
    db.save(log)

    return UndoResponse(
        mutation_id=log.id,
        reversal_mutation_id=reversal.id,
        restored_entity_id=restored.id,
    )


def _model_for(entity_type: str):
    """Map MutationLog.entity_type to its concrete Pydantic class."""
    return {
        "KnowledgeEntity": KnowledgeEntity,
        "KnowledgeClaim": KnowledgeClaim,
    }.get(entity_type)
