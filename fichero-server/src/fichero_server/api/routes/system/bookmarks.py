"""Bookmark routes — node-model fold F4 (#2591).

Bookmarks are additive node types, not a separate subsystem: each bookmark is a
Document alias with ``prototype_key="bookmark"`` pointing at its target via
``alias_target_id``. The P2 alias machinery remains the source of truth for
resolution, so dangling targets raise loudly instead of silently degrading.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models.knowledge import Milestone
from fichero_server.models import DocType, Document, DocumentListResponse
from fichero_server.models.node_aliases import (
    ALIAS_NODE_KIND,
    DanglingAliasError,
    make_alias,
    resolve_alias,
)

router = APIRouter()

BOOKMARK_PROTOTYPE_KEY = "bookmark"


class BookmarkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str
    parent_id: str | None = None
    name: str | None = None


class MilestoneCreateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    parent_id: str
    status: str = "planned"
    description: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    created_by: str = "human"


def _bookmark_or_404(db: Database, bookmark_id: str) -> Document:
    bookmark = db.get(Document, bookmark_id)
    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    if bookmark.prototype_key != BOOKMARK_PROTOTYPE_KEY:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    if bookmark.node_kind != ALIAS_NODE_KIND:
        raise HTTPException(
            status_code=409,
            detail=f"Bookmark {bookmark.id} is not an alias node",
        )
    return bookmark


def create_bookmark_impl(db: Database, request: BookmarkCreate) -> Document:
    target = db.get(Document, request.target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Bookmark target not found")
    if request.parent_id is not None and db.get(Document, request.parent_id) is None:
        raise HTTPException(status_code=400, detail="Bookmark parent not found")

    bookmark = make_alias(target, parent_id=request.parent_id, name=request.name)
    bookmark.prototype_key = BOOKMARK_PROTOTYPE_KEY
    db.save(bookmark)
    return bookmark


def create_milestone_impl(
    db: Database, params: MilestoneCreateParams | Milestone
) -> Milestone:
    milestone = (
        params
        if isinstance(params, Milestone)
        else Milestone(**params.model_dump(mode="json"))
    )
    parent = db.get(Document, milestone.parent_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Milestone parent not found")
    if parent.doc_type != DocType.folder:
        raise HTTPException(status_code=400, detail="Milestone parent must be a folder")
    db.save(milestone)
    return milestone


def list_bookmarks_impl(
    db: Database, *, parent_id: str | None = None
) -> list[Document]:
    filters = {
        "prototype_key": BOOKMARK_PROTOTYPE_KEY,
        "node_kind": ALIAS_NODE_KIND,
    }
    if parent_id is not None:
        filters["parent_id"] = parent_id
    bookmarks = db.query(Document, **filters)
    return sorted(bookmarks, key=lambda doc: (doc.sort_order, (doc.name or "").lower()))


def resolve_bookmark_impl(db: Database, bookmark_id: str) -> Document:
    bookmark = _bookmark_or_404(db, bookmark_id)
    try:
        return resolve_alias(db, bookmark)
    except DanglingAliasError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=Document, status_code=201)
async def create_bookmark(
    request: BookmarkCreate,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> Document:
    """Create a bookmark node that references another document."""
    result = registry.invoke(
        db,
        "bookmark.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return Document.model_validate(result.result)


@router.get("", response_model=DocumentListResponse)
async def list_bookmarks(
    parent_id: str | None = Query(None, description="Filter by parent bookmark container"),
    db: Database = Depends(get_library_database),
) -> DocumentListResponse:
    """List bookmark nodes."""
    items = list_bookmarks_impl(db, parent_id=parent_id)
    return DocumentListResponse(items=items, count=len(items))


@router.get("/{bookmark_id}/resolve", response_model=Document)
async def resolve_bookmark(
    bookmark_id: str,
    db: Database = Depends(get_library_database),
) -> Document:
    """Resolve a bookmark node to its live target document."""
    return resolve_bookmark_impl(db, bookmark_id)


def _bookmark_snapshot(bookmark: Document) -> dict:
    return bookmark.model_dump(mode="json")


def _invert_bookmark_create(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not after:
        return None
    bookmark_id = after.get("id")
    if not bookmark_id:
        return None
    return ("document.delete", {"doc_id": bookmark_id})


@action(
    "bookmark.create",
    BookmarkCreate,
    domains=["bookmark", "document"],
    undoable=True,
    invert=_invert_bookmark_create,
)
def _action_create_bookmark(
    db: Database, params: BookmarkCreate, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    bookmark = create_bookmark_impl(db, params)
    after = _bookmark_snapshot(bookmark)
    spec = ChangeSpec(
        domains=["bookmark", "document"],
        target_ids=[bookmark.id],
        before=None,
        after=after,
        emit_type="document.created",
        document_ids=[bookmark.id],
    )
    return after, spec


@action(
    "milestone.create",
    MilestoneCreateParams,
    domains=["milestone", "document"],
)
def _action_create_milestone(
    db: Database, params: MilestoneCreateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    milestone = create_milestone_impl(db, params)
    after = milestone.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["milestone", "document"],
        target_ids=[milestone.id],
        before=None,
        after=after,
        emit_type="document.created",
        document_ids=[milestone.id],
    )
    return after, spec
