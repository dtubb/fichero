"""Comments on claims, entities, sources and segments (`kg.interact.comment`, #4643).

Writes are audited, undoable actions (`kg.comment.add`, `kg.comment.withdraw`), so the app, the command
line and MCP do the same thing. A comment is its own threaded record; it is never stored as a claim.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action
from fichero_server.api.auth import action_context  # noqa: F401  (kept with the other action routes' imports)
from fichero_server.api.main import get_library_database
from fichero_server.api.routes.document.segments import provenance_kind_from_ctx
from fichero_server.core.off_loop import off_loop
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.models import Document, Segment
from fichero_server.models.kg_comments import CommentAnchorKind, KgComment
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

router = APIRouter(prefix="/kg/comments")

_ANCHOR_MODEL = {
    CommentAnchorKind.claim: KnowledgeClaim,
    CommentAnchorKind.entity: KnowledgeEntity,
    CommentAnchorKind.source: Document,
    CommentAnchorKind.segment: Segment,
}


class CommentAddParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_kind: CommentAnchorKind
    anchor_id: str
    body: str = Field(min_length=1, max_length=4000)
    parent_id: Optional[str] = None


class CommentIdParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment_id: str


def _spec(comment: KgComment, *, before: Any, after: Any, emit: str) -> ChangeSpec:
    return ChangeSpec(domains=["kg"], target_ids=[comment.id, comment.anchor_id], before=before, after=after, emit_type=emit)


def _invert_add(before, after, ctx: ActionContext):
    comment_id = (after or {}).get("comment_id")
    return ("kg.comment.withdraw", {"comment_id": comment_id}) if comment_id else None


@action("kg.comment.add", CommentAddParams, domains=["kg"], undoable=True, invert=_invert_add)
def _action_add(db: Database, params: CommentAddParams, ctx: ActionContext):
    """Comment on a node; a reply names a comment on the same node."""
    if db.get(_ANCHOR_MODEL[params.anchor_kind], params.anchor_id) is None:
        raise HTTPException(status_code=404, detail=f"{params.anchor_kind.value} not found: {params.anchor_id}")
    if params.parent_id is not None:
        parent = db.get(KgComment, params.parent_id)
        if parent is None or parent.anchor_id != params.anchor_id:
            raise HTTPException(status_code=422, detail="a reply names a comment on the same node")
    comment = KgComment(**params.model_dump(), created_by=ctx.actor or None, provenance_kind=provenance_kind_from_ctx(ctx))
    db.save(comment)
    return {"comment_id": comment.id}, _spec(comment, before=None, after={"comment_id": comment.id}, emit="kg.comment.added")


def _invert_withdraw(before, after, ctx: ActionContext):
    comment_id = (after or {}).get("comment_id")
    return ("kg.comment.restore", {"comment_id": comment_id}) if comment_id and (after or {}).get("changed", True) else None


@action("kg.comment.withdraw", CommentIdParams, domains=["kg"], undoable=True, invert=_invert_withdraw)
def _action_withdraw(db: Database, params: CommentIdParams, ctx: ActionContext):
    comment = db.get(KgComment, params.comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail=f"Comment not found: {params.comment_id}")
    changed = comment.withdrawn_at is None
    if changed:
        comment.withdrawn_at = utc_now()
        db.save(comment)
    return {"comment_id": comment.id, "withdrawn": True}, _spec(
        comment, before={"comment_id": comment.id, "withdrawn": not changed},
        after={"comment_id": comment.id, "withdrawn": True, "changed": changed}, emit="kg.comment.withdrawn")


@action("kg.comment.restore", CommentIdParams, domains=["kg"], undoable=False)
def _action_restore(db: Database, params: CommentIdParams, ctx: ActionContext):
    comment = db.get(KgComment, params.comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail=f"Comment not found: {params.comment_id}")
    comment.withdrawn_at = None
    db.save(comment)
    return {"comment_id": comment.id, "withdrawn": False}, _spec(
        comment, before={"comment_id": comment.id, "withdrawn": True},
        after={"comment_id": comment.id, "withdrawn": False}, emit="kg.comment.added")


class CommentListResponse(BaseModel):
    items: list[KgComment]


@router.get("", response_model=CommentListResponse)
@off_loop
def list_comments(anchor_id: str, db: Database = Depends(get_library_database)) -> CommentListResponse:
    """The live comments on one node, oldest first; a reply carries its `parent_id`."""
    live = [c for c in db.query(KgComment, anchor_id=anchor_id) if c.withdrawn_at is None]
    return CommentListResponse(items=sorted(live, key=lambda c: c.created_at))
