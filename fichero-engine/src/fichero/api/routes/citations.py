"""Document-to-document citation graph (#906).

CRUD for DocumentCitation rows + inbound/outbound query endpoints
that surface "what cites this document?" and "what does this document
cite?" — the citation network alongside the entity network.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.api.auth import request_actor
from fichero.api.change_stream import emit_change
from fichero.db import Database
from fichero.knowledge_models import DocumentCitation
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


@router.post(
    "",
    response_model=DocumentCitation,
    summary="Record a citation from one document to another",
)
async def create_citation(
    request: CitationCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Header(
        default=None,
        alias="X-Fichero-Library-Path",
    ),
    x_fichero_origin_window: str | None = Header(
        default=None,
        alias="X-Fichero-Origin-Window",
    ),
    actor: str = Depends(request_actor),
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
    emit_change(
        x_fichero_library_path or str(db.path.parent),
        type="citation.created",
        citation_ids=[citation.id],
        document_ids=[citation.source_document_id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return citation


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
    rows = db.query(DocumentCitation)
    if source_document_id is not None:
        rows = [r for r in rows if r.source_document_id == source_document_id]
    if target_document_id is not None:
        rows = [r for r in rows if r.target_document_id == target_document_id]
    if detector is not None:
        rows = [r for r in rows if r.detector == detector]
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
    items = [
        c for c in db.query(DocumentCitation) if c.source_document_id == document_id
    ]

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
    items = [
        c for c in db.query(DocumentCitation) if c.target_document_id == document_id
    ]

    return CitationListResponse(items=items, count=len(items))


class CitationPatchRequest(BaseModel):
    target_document_id: str | None = None
    target_citation_text: str | None = None
    page_label: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    confidence: float | None = None


@router.patch("/{citation_id}", response_model=DocumentCitation)
async def patch_citation(
    citation_id: str,
    request: CitationPatchRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Header(
        default=None,
        alias="X-Fichero-Library-Path",
    ),
    x_fichero_origin_window: str | None = Header(
        default=None,
        alias="X-Fichero-Origin-Window",
    ),
    actor: str = Depends(request_actor),
) -> DocumentCitation:
    citation = db.get(DocumentCitation, citation_id)
    if citation is None:
        raise HTTPException(404, f"Citation not found: {citation_id}")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(citation, field, value)
    db.save(citation)
    emit_change(
        x_fichero_library_path or str(db.path.parent),
        type="citation.updated",
        citation_ids=[citation.id],
        document_ids=[citation.source_document_id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return citation


@router.delete("/{citation_id}", status_code=204)
async def delete_citation(
    citation_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Header(
        default=None,
        alias="X-Fichero-Library-Path",
    ),
    x_fichero_origin_window: str | None = Header(
        default=None,
        alias="X-Fichero-Origin-Window",
    ),
    actor: str = Depends(request_actor),
) -> None:
    citation = db.get(DocumentCitation, citation_id)
    if citation is None:
        raise HTTPException(404, f"Citation not found: {citation_id}")
    library_path = x_fichero_library_path or str(db.path.parent)
    document_id = citation.source_document_id
    db.delete(citation)
    emit_change(
        library_path,
        type="citation.deleted",
        citation_ids=[citation_id],
        document_ids=[document_id] if document_id else [],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
