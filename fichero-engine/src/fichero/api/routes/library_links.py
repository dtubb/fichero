"""Library Links API — generic node-to-node links between library items.

Backend slice of #2590. Reuses the typed relation vocabulary from
:class:`fichero.knowledge_models.ClaimRelationType` and mirrors the shape of
:class:`fichero.knowledge_models.KnowledgeClaimLink`, but connects any two
library items (document, note, entity, claim) via source_id/target_id.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.library_header import require_library_path
from fichero.api.auth import request_actor
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.knowledge_models import (
    ClaimRelationType,
    KnowledgeClaim,
    KnowledgeEntity,
    LibraryItemLink,
    LibraryItemType,
)
from fichero.models import Document, LibraryItemLinkListResponse, Note

router = APIRouter(tags=["library-links"])


# Map typed item kinds to the Pydantic model used to validate existence.
_MODEL_FOR_TYPE: dict[str, type[Any]] = {
    LibraryItemType.document.value: Document,
    LibraryItemType.note.value: Note,
    LibraryItemType.entity.value: KnowledgeEntity,
    LibraryItemType.claim.value: KnowledgeClaim,
}


# =============================================================================
# Request/Response Models
# =============================================================================


class LibraryLinkCreateRequest(BaseModel):
    """Request to create a generic link between two library items."""

    source_id: str
    source_type: LibraryItemType
    target_id: str
    target_type: LibraryItemType
    relation_type: ClaimRelationType
    link_quality: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LibraryLinkUpdateRequest(BaseModel):
    """Request to update a generic library link."""

    relation_type: ClaimRelationType | None = None
    link_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: str | None = None
    metadata: dict[str, Any] | None = None


class LibraryLinkDeletedResponse(BaseModel):
    success: bool
    link_id: str
    operation: str


# =============================================================================
# Helpers
# =============================================================================


def _resolve_item(db: Database, item_id: str, item_type: LibraryItemType) -> Any:
    """Validate that a library item of the given type exists."""
    model = _MODEL_FOR_TYPE.get(item_type.value)
    if model is None:
        raise HTTPException(
            status_code=400, detail=f"Unsupported item type: {item_type.value}"
        )
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(
            status_code=404, detail=f"{item_type.value} not found: {item_id}"
        )
    return item


def _list_links(
    db: Database,
    *,
    source_id: str | None = None,
    target_id: str | None = None,
    relation_type: ClaimRelationType | None = None,
) -> list[LibraryItemLink]:
    """Load links matching the provided equality filters."""
    filters: dict[str, Any] = {}
    if source_id is not None:
        filters["source_id"] = source_id
    if target_id is not None:
        filters["target_id"] = target_id
    if relation_type is not None:
        filters["relation_type"] = relation_type

    if filters:
        return db.query(LibraryItemLink, **filters)
    return db.all(LibraryItemLink)


# =============================================================================
# CRUD Endpoints
# =============================================================================


@router.post("/links", response_model=LibraryItemLink)
async def create_library_link(
    request: LibraryLinkCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    actor: str = Depends(request_actor),
) -> LibraryItemLink:
    """Create a typed link between any two library items."""
    _resolve_item(db, request.source_id, request.source_type)
    _resolve_item(db, request.target_id, request.target_type)

    link = LibraryItemLink(
        source_id=request.source_id,
        source_type=request.source_type,
        target_id=request.target_id,
        target_type=request.target_type,
        relation_type=request.relation_type,
        link_quality=request.link_quality,
        evidence=request.evidence,
        metadata=request.metadata,
        created_at=datetime.now(),
    )
    db.save(link)
    return link


@router.get("/links", response_model=LibraryItemLinkListResponse)
async def list_library_links(
    source_id: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    relation_type: ClaimRelationType | None = Query(default=None),
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Depends(require_library_path),
    actor: str = Depends(request_actor),
) -> LibraryItemLinkListResponse:
    """List generic library links, filtered by endpoint and/or relation."""
    items = _list_links(
        db, source_id=source_id, target_id=target_id, relation_type=relation_type
    )
    return LibraryItemLinkListResponse(items=items, count=len(items))


@router.get("/links/{link_id}", response_model=LibraryItemLink)
async def get_library_link(
    link_id: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Depends(require_library_path),
    actor: str = Depends(request_actor),
) -> LibraryItemLink:
    """Get a single generic library link by id."""
    link = db.get(LibraryItemLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail=f"Link not found: {link_id}")
    return link


@router.patch("/links/{link_id}", response_model=LibraryItemLink)
async def update_library_link(
    link_id: str,
    request: LibraryLinkUpdateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    actor: str = Depends(request_actor),
) -> LibraryItemLink:
    """Update an existing generic library link."""
    link = db.get(LibraryItemLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail=f"Link not found: {link_id}")

    data = request.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in data.items():
        setattr(link, key, value)
    link.updated_at = datetime.now()
    db.save(link)
    return link


@router.delete("/links/{link_id}")
async def delete_library_link(
    link_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    actor: str = Depends(request_actor),
) -> LibraryLinkDeletedResponse:
    """Delete a generic library link (hard delete)."""
    link = db.get(LibraryItemLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail=f"Link not found: {link_id}")
    db.delete(link)
    return LibraryLinkDeletedResponse(success=True, link_id=link_id, operation="deleted")


@router.get("/library-items/{item_id}/links", response_model=LibraryItemLinkListResponse)
async def list_links_for_item(
    item_id: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Depends(require_library_path),
    actor: str = Depends(request_actor),
) -> LibraryItemLinkListResponse:
    """All links touching a given library item id (outgoing + incoming)."""
    outgoing = db.query(LibraryItemLink, source_id=item_id)
    incoming = db.query(LibraryItemLink, target_id=item_id)
    merged = {link.id: link for link in [*outgoing, *incoming]}
    items = sorted(merged.values(), key=lambda link: link.created_at, reverse=True)
    return LibraryItemLinkListResponse(items=items, count=len(items))
