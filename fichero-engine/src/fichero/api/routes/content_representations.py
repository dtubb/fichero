"""Audited content-representation revision actions (#3443)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException

from fichero.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero.api.auth import action_context
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.models import ContentRepresentation, ContentRepresentationRevision

router = APIRouter(prefix="/content-representations")


class RepresentationRevisionParams(BaseModel):
    representation_id: str
    content: str = Field(min_length=1)
    decision: str | None = None


@action(
    "representation.revise",
    RepresentationRevisionParams,
    domains=["representation"],
    undoable=False,
)
def revise_representation(
    db: Database,
    params: RepresentationRevisionParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    """Create a user revision without changing the source representation."""
    representation = db.get(ContentRepresentation, params.representation_id)
    if representation is None:
        raise LookupError(f"Content representation not found: {params.representation_id}")
    revision = ContentRepresentationRevision(
        representation_id=representation.id,
        content=params.content,
        reviewer=ctx.actor,
        decision=params.decision,
    )
    db.save(revision)
    snapshot = revision.model_dump(mode="json")
    return snapshot, ChangeSpec(
        domains=["representation"],
        target_ids=[representation.id, revision.id],
        before=None,
        after=snapshot,
        emit_type="representation.revised",
        document_ids=[representation.document_id],
    )


@router.get("/document/{document_id}", response_model=list[ContentRepresentation])
async def list_representations(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> list[ContentRepresentation]:
    return db.query(ContentRepresentation, document_id=document_id)


@router.get("/{representation_id}/revisions", response_model=list[ContentRepresentationRevision])
async def list_revisions(
    representation_id: str,
    db: Database = Depends(get_library_database),
) -> list[ContentRepresentationRevision]:
    if db.get(ContentRepresentation, representation_id) is None:
        raise HTTPException(404, f"Content representation not found: {representation_id}")
    return db.query(ContentRepresentationRevision, representation_id=representation_id)


@router.post("/{representation_id}/revisions", response_model=ContentRepresentationRevision)
async def create_revision(
    representation_id: str,
    payload: RepresentationRevisionParams,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ContentRepresentationRevision:
    result = registry.invoke(
        db,
        "representation.revise",
        {**payload.model_dump(), "representation_id": representation_id},
        ctx,
    )
    return ContentRepresentationRevision.model_validate(result.result)
