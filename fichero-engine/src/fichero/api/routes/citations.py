"""Document-to-document citation graph (#906).

CRUD for DocumentCitation rows + inbound/outbound query endpoints
that surface "what cites this document?" and "what does this document
cite?" — the citation network alongside the entity network.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import DocumentCitation
from fichero.models import Document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/citations/graph", tags=["knowledge-graph"])


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
    db: Database = Depends(get_library_database),
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


@router.get(
    "",
    response_model=list[DocumentCitation],
    summary="List citations (filter by source/target/detector)",
)
async def list_citations(
    source_document_id: str | None = Query(default=None),
    target_document_id: str | None = Query(default=None),
    detector: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    db: Database = Depends(get_library_database),
) -> list[DocumentCitation]:
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
    return rows


@router.get(
    "/document/{document_id}/outbound",
    response_model=list[DocumentCitation],
    summary="Citations FROM this document — what it cites",
)
async def outbound(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> list[DocumentCitation]:
    return [
        c for c in db.query(DocumentCitation)
        if c.source_document_id == document_id
    ]


@router.get(
    "/document/{document_id}/inbound",
    response_model=list[DocumentCitation],
    summary="Citations TO this document — what cites it",
)
async def inbound(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> list[DocumentCitation]:
    return [
        c for c in db.query(DocumentCitation)
        if c.target_document_id == document_id
    ]


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
    db: Database = Depends(get_library_database),
) -> DocumentCitation:
    citation = db.get(DocumentCitation, citation_id)
    if citation is None:
        raise HTTPException(404, f"Citation not found: {citation_id}")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(citation, field, value)
    db.save(citation)
    return citation


@router.delete("/{citation_id}", status_code=204)
async def delete_citation(
    citation_id: str,
    db: Database = Depends(get_library_database),
) -> None:
    citation = db.get(DocumentCitation, citation_id)
    if citation is None:
        raise HTTPException(404, f"Citation not found: {citation_id}")
    db.delete(citation)
