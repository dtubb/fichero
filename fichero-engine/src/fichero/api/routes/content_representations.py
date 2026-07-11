"""Audited content-representation revision actions (#3443)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from fichero.actions.registry import ActionContext, ChangeSpec, action
from fichero.db import Database
from fichero.models import ContentRepresentation, ContentRepresentationRevision


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
