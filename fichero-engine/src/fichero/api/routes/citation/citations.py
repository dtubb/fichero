"""Document-to-document citation graph (#906).

CRUD for DocumentCitation rows + inbound/outbound query endpoints
that surface "what cites this document?" and "what does this document
cite?" — the citation network alongside the entity network.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero.api.auth import action_context, request_actor
from fichero.api.library_header import require_library_path
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.models.knowledge import DocumentCitation
from fichero.models import CitationListResponse, Document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/citations/graph")


class CitationCreateRequest(BaseModel):
    source_document_id: str
    target_document_id: str | None = None
    target_citation_text: str
    page_label: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = 1.0
    detector: str = "manual"
    metadata: dict[str, Any] = {}


def _resolve_action_ctx(
    ctx: ActionContext | object,
    *,
    actor: str | object = "system",
    library_path: str | object | None = None,
    origin_window: str | object | None = None,
) -> ActionContext:
    if isinstance(ctx, ActionContext):
        return ctx
    return ActionContext(
        actor=actor if isinstance(actor, str) else "system",
        library_path=library_path if isinstance(library_path, str) else None,
        origin_window=origin_window if isinstance(origin_window, str) else None,
    )


def _create_citation_impl(
    db: Database, request: CitationCreateRequest
) -> DocumentCitation:
    if db.get(Document, request.source_document_id) is None:
        raise HTTPException(
            404, f"Source document not found: {request.source_document_id}"
        )
    if (
        request.target_document_id is not None
        and db.get(Document, request.target_document_id) is None
    ):
        raise HTTPException(
            404, f"Target document not found: {request.target_document_id}"
        )
    citation = DocumentCitation(**request.model_dump())
    db.save(citation)
    return citation


def _patch_citation_impl(
    db: Database, citation_id: str, request: CitationPatchRequest
) -> tuple[DocumentCitation, dict[str, Any]]:
    citation = db.get(DocumentCitation, citation_id)
    if citation is None:
        raise HTTPException(404, f"Citation not found: {citation_id}")
    before = citation.model_dump(mode="json")
    updates = request.model_dump(exclude_unset=True)
    if "target_document_id" in updates:
        target_document_id = updates["target_document_id"]
        if target_document_id is not None and db.get(Document, target_document_id) is None:
            raise HTTPException(404, f"Target document not found: {target_document_id}")
    for field, value in updates.items():
        setattr(citation, field, value)
    db.save(citation)
    return citation, before


def _delete_citation_impl(db: Database, citation_id: str) -> dict[str, Any]:
    citation = db.get(DocumentCitation, citation_id)
    if citation is None:
        raise HTTPException(404, f"Citation not found: {citation_id}")
    before = citation.model_dump(mode="json")
    db.delete(citation)
    return before


def _restore_citation_impl(db: Database, payload: dict[str, Any]) -> DocumentCitation:
    citation = DocumentCitation(**payload)
    db.save(citation)
    return citation


def _invert_citation_to_restore(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return ("citation.restore", {"payload": before})


def _invert_citation_create(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not after:
        return None
    citation_id = after.get("citation_id")
    if not citation_id:
        return None
    return ("citation.delete", {"citation_id": citation_id})


@router.post(
    "",
    response_model=DocumentCitation,
    summary="Record a citation from one document to another",
)
async def create_citation(
    request: CitationCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None,
        alias="X-Fichero-Origin-Window",
    ),
    actor: str | object = Depends(request_actor),
    ctx: ActionContext | object = Depends(action_context),
) -> DocumentCitation:
    ctx = _resolve_action_ctx(
        ctx,
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
    )
    result = registry.invoke(
        db,
        "citation.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return DocumentCitation.model_validate(result.result)


@router.get(
    "",
    response_model=CitationListResponse,
    summary="List citations (filter by source/target/detector)",
)
async def list_citations(
    source_document_id: str | None = Query(default=None),
    target_document_id: str | None = Query(default=None),
    detector: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    db: Database = Depends(get_library_database),
) -> CitationListResponse:
    # Push equality filters into the DB query; confidence filter is a
    # range predicate so stays in Python (but on a much smaller result set).
    filters: dict[str, Any] = {}
    if source_document_id is not None:
        filters["source_document_id"] = source_document_id
    if target_document_id is not None:
        filters["target_document_id"] = target_document_id
    if detector is not None:
        filters["detector"] = detector
    rows = db.query(DocumentCitation, **filters) if filters else db.query(DocumentCitation)
    if min_confidence is not None:
        rows = [r for r in rows if r.confidence >= min_confidence]
    rows.sort(key=lambda r: r.created_at, reverse=True)
    return CitationListResponse(items=rows, count=len(rows))


@router.get(
    "/document/{document_id}/outbound",
    response_model=CitationListResponse,
    summary="Citations FROM this document — what it cites",
)
async def outbound(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> CitationListResponse:
    items = db.query(DocumentCitation, source_document_id=document_id)

    return CitationListResponse(items=items, count=len(items))


@router.get(
    "/document/{document_id}/inbound",
    response_model=CitationListResponse,
    summary="Citations TO this document — what cites it",
)
async def inbound(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> CitationListResponse:
    items = db.query(DocumentCitation, target_document_id=document_id)

    return CitationListResponse(items=items, count=len(items))


class CitationPatchRequest(BaseModel):
    target_document_id: str | None = None
    target_citation_text: str | None = None
    page_label: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    confidence: float | None = None


class CitationPatchActionParams(BaseModel):
    citation_id: str = Field(description="Citation id to update")
    patch: CitationPatchRequest = Field(description="Fields to update")


class CitationDeleteActionParams(BaseModel):
    citation_id: str = Field(description="Citation id to delete")


class CitationRestoreActionParams(BaseModel):
    payload: dict[str, Any] = Field(description="Full citation snapshot to restore")


@router.patch("/{citation_id}", response_model=DocumentCitation)
async def patch_citation(
    citation_id: str,
    request: CitationPatchRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None,
        alias="X-Fichero-Origin-Window",
    ),
    actor: str | object = Depends(request_actor),
    ctx: ActionContext | object = Depends(action_context),
) -> DocumentCitation:
    ctx = _resolve_action_ctx(
        ctx,
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
    )
    result = registry.invoke(
        db,
        "citation.patch",
        {
            "citation_id": citation_id,
            "patch": request.model_dump(mode="json", exclude_unset=True),
        },
        ctx,
    )
    return DocumentCitation.model_validate(result.result)


@router.delete("/{citation_id}", status_code=204)
async def delete_citation(
    citation_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None,
        alias="X-Fichero-Origin-Window",
    ),
    actor: str | object = Depends(request_actor),
    ctx: ActionContext | object = Depends(action_context),
) -> None:
    ctx = _resolve_action_ctx(
        ctx,
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
    )
    registry.invoke(
        db,
        "citation.delete",
        {"citation_id": citation_id},
        ctx,
    )


@action(
    "citation.create",
    CitationCreateRequest,
    domains=["citation", "document"],
    undoable=True,
    invert=_invert_citation_create,
)
def _action_create_citation(
    db: Database, params: CitationCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    citation = _create_citation_impl(db, params)
    spec = ChangeSpec(
        domains=["citation", "document"],
        target_ids=[citation.id],
        before=None,
        after={"citation_id": citation.id},
        emit_type="citation.created",
        citation_ids=[citation.id],
        document_ids=[citation.source_document_id],
    )
    return citation.model_dump(mode="json"), spec


@action(
    "citation.patch",
    CitationPatchActionParams,
    domains=["citation", "document"],
    undoable=True,
    invert=_invert_citation_to_restore,
)
def _action_patch_citation(
    db: Database, params: CitationPatchActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    citation, before = _patch_citation_impl(db, params.citation_id, params.patch)
    spec = ChangeSpec(
        domains=["citation", "document"],
        target_ids=[citation.id],
        before=before,
        after=citation.model_dump(mode="json"),
        emit_type="citation.updated",
        citation_ids=[citation.id],
        document_ids=[citation.source_document_id],
    )
    return citation.model_dump(mode="json"), spec


@action(
    "citation.delete",
    CitationDeleteActionParams,
    domains=["citation", "document"],
    undoable=True,
    invert=_invert_citation_to_restore,
)
def _action_delete_citation(
    db: Database, params: CitationDeleteActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before = _delete_citation_impl(db, params.citation_id)
    spec = ChangeSpec(
        domains=["citation", "document"],
        target_ids=[params.citation_id],
        before=before,
        after=None,
        emit_type="citation.deleted",
        citation_ids=[params.citation_id],
        document_ids=[before["source_document_id"]],
    )
    return None, spec


@action(
    "citation.restore",
    CitationRestoreActionParams,
    domains=["citation", "document"],
    undoable=False,
)
def _action_restore_citation(
    db: Database, params: CitationRestoreActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    citation = _restore_citation_impl(db, params.payload)
    spec = ChangeSpec(
        domains=["citation", "document"],
        target_ids=[citation.id],
        before=None,
        after=citation.model_dump(mode="json"),
        emit_type="citation.created",
        citation_ids=[citation.id],
        document_ids=[citation.source_document_id],
    )
    return citation.model_dump(mode="json"), spec
