"""Knowledge graph mutation log routes (undo/redo, audit log)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    MutationLog,
    MutationOperationType,
)

router = APIRouter()


class MutationLogResponse(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    operation: MutationOperationType
    before_state: dict | None
    after_state: dict | None
    changed_fields: list[str] | None
    run_id: str | None
    agent_id: str | None
    created_by: str
    reversal_id: str | None
    created_at: datetime


class UndoRequest(BaseModel):
    run_id: str | None = Field(
        default=None, description="Rollback all mutations in this AI run"
    )
    mutation_id: str | None = Field(
        default=None, description="Undo a specific mutation"
    )


def _entity_type_to_model(entity_type: str):
    """Map entity_type string to the Pydantic model class."""
    mapping = {
        "KnowledgeEntity": KnowledgeEntity,
        "KnowledgeClaim": KnowledgeClaim,
        "KnowledgeClaimLink": KnowledgeClaimLink,
    }
    return mapping.get(entity_type)


@router.post("/knowledge-mutations/undo", response_model=list[MutationLogResponse])
async def undo_mutations(
    request: UndoRequest,
    db: Database = Depends(get_library_database),
) -> list[MutationLogResponse]:
    """Undo specific mutation(s) by replaying before_state.

    Accepts either run_id (rollback all mutations in that AI run) or
    mutation_id (undo a single mutation).
    """
    if not request.run_id and not request.mutation_id:
        raise HTTPException(
            status_code=400, detail="Provide run_id or mutation_id"
        )

    if request.mutation_id:
        mutations_to_undo = [db.get(MutationLog, request.mutation_id)]
        mutations_to_undo = [m for m in mutations_to_undo if m is not None]
    else:
        mutations_to_undo = db.query(MutationLog, run_id=request.run_id)
        mutations_to_undo.sort(key=lambda m: m.created_at, reverse=True)

    if not mutations_to_undo:
        raise HTTPException(
            status_code=404, detail="No mutations found to undo"
        )

    undone: list[MutationLogResponse] = []
    for mutation in mutations_to_undo:
        if mutation.before_state is None and mutation.operation != MutationOperationType.create:
            continue

        model_class = _entity_type_to_model(mutation.entity_type)
        if model_class is None:
            continue

        if mutation.operation == MutationOperationType.create:
            # Undo create: delete the entity
            obj = db.get(model_class, mutation.entity_id)
            if obj:
                db.delete(obj)
        elif mutation.operation in (
            MutationOperationType.update,
            MutationOperationType.delete,
        ):
            # Undo update/delete: restore before_state
            if mutation.before_state:
                try:
                    restored = model_class(**mutation.before_state)
                    db.save(restored)
                except Exception:
                    continue

        undo_log = MutationLog(
            entity_type=mutation.entity_type,
            entity_id=mutation.entity_id,
            operation=MutationOperationType.delete
            if mutation.operation == MutationOperationType.create
            else MutationOperationType.update,
            before_state=mutation.after_state,
            after_state=mutation.before_state,
            changed_fields=mutation.changed_fields,
            run_id=mutation.run_id,
            agent_id=mutation.agent_id,
            created_by="undo",
            created_at=datetime.now(),
        )
        db.save(undo_log)

        undone.append(
            MutationLogResponse(
                id=undo_log.id,
                entity_type=undo_log.entity_type,
                entity_id=undo_log.entity_id,
                operation=undo_log.operation,
                before_state=undo_log.before_state,
                after_state=undo_log.after_state,
                changed_fields=undo_log.changed_fields,
                run_id=undo_log.run_id,
                agent_id=undo_log.agent_id,
                created_by=undo_log.created_by,
                reversal_id=undo_log.reversal_id,
                created_at=undo_log.created_at,
            )
        )

    return undone


@router.get("/knowledge-mutations", response_model=list[MutationLogResponse])
async def list_mutations(
    run_id: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Database = Depends(get_library_database),
) -> list[MutationLogResponse]:
    """List mutation log entries, optionally filtered."""
    mutations = db.all(MutationLog)
    if run_id:
        mutations = [m for m in mutations if m.run_id == run_id]
    if entity_id:
        mutations = [m for m in mutations if m.entity_id == entity_id]
    if entity_type:
        mutations = [m for m in mutations if m.entity_type == entity_type]
    mutations.sort(key=lambda m: m.created_at, reverse=True)
    return [
        MutationLogResponse(
            id=m.id,
            entity_type=m.entity_type,
            entity_id=m.entity_id,
            operation=m.operation,
            before_state=m.before_state,
            after_state=m.after_state,
            changed_fields=m.changed_fields,
            run_id=m.run_id,
            agent_id=m.agent_id,
            created_by=m.created_by,
            reversal_id=m.reversal_id,
            created_at=m.created_at,
        )
        for m in mutations[:limit]
    ]
