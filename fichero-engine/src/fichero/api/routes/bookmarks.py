"""Bookmark routes — node-model fold F4 (#2591).

Bookmarks are additive node types, not a separate subsystem: each bookmark is a
Document alias with ``prototype_key="bookmark"`` pointing at its target via
``alias_target_id``. The P2 alias machinery remains the source of truth for
resolution, so dangling targets raise loudly instead of silently degrading.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.models import Document, DocumentListResponse
from fichero.node_aliases import (
    ALIAS_NODE_KIND,
    DanglingAliasError,
    make_alias,
    resolve_alias,
)

router = APIRouter()

BOOKMARK_PROTOTYPE_KEY = "bookmark"


class BookmarkCreate(BaseModel):
    target_id: str
    parent_id: str | None = None
    name: str | None = None


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
) -> Document:
    """Create a bookmark node that references another document."""
    return create_bookmark_impl(db, request)


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
