"""Citation rendering API (#912)."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/citations")


CitationStyle = Literal["bibtex", "chicago", "apa", "mla"]


def _render(style: CitationStyle, metadata) -> str:
    from fichero.citations import (
        render_apa,
        render_bibtex,
        render_chicago,
        render_mla,
    )

    fn = {
        "bibtex": render_bibtex,
        "chicago": render_chicago,
        "apa": render_apa,
        "mla": render_mla,
    }[style]
    return fn(metadata)


class CitationResponse(BaseModel):
    style: str
    text: str
    document_id: str | None = None
    claim_id: str | None = None


def _metadata_for_document(db: Database, document_id: str):
    """Pull SourceMetadata for a document.

    SourceMetadata now lives on the top-level Document.source_metadata
    field (added #908). Older libraries may still have it nested inside
    Document.metadata['source_metadata'], so we check the primary field
    first and fall back to the legacy dict location. If neither works,
    fall back to the most-recent claim from that document.
    """
    from fichero.models.knowledge import KnowledgeClaim, SourceMetadata
    from fichero.models import Document

    doc = db.get(Document, document_id)
    if doc is not None:
        # Primary: top-level source_metadata field (#908)
        if doc.source_metadata is not None:
            if isinstance(doc.source_metadata, SourceMetadata):
                return doc.source_metadata
            # Stored as a dict — construct from it
            try:
                return SourceMetadata(**doc.source_metadata)
            except Exception:
                pass
        # Legacy fallback: nested inside metadata dict
        meta_dict = (doc.metadata or {}).get("source_metadata")
        if meta_dict:
            try:
                return SourceMetadata(**meta_dict)
            except Exception:
                pass

    # Fall back to a claim from this document.
    claims = db.query(KnowledgeClaim, source_document_id=document_id)
    for c in claims:
        if c.source_metadata is not None:
            return c.source_metadata
    return None


@router.get(
    "/document/{document_id}",
    response_model=CitationResponse,
    summary="Render a document's citation in one of the supported styles",
)
async def cite_document(
    document_id: str,
    style: CitationStyle = Query(
        default="bibtex",
        description="Citation style: bibtex | chicago | apa | mla",
    ),
    db: Database = Depends(get_library_database),
) -> CitationResponse:
    meta = _metadata_for_document(db, document_id)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail=f"No SourceMetadata found for document {document_id}",
        )
    return CitationResponse(
        style=style,
        text=_render(style, meta),
        document_id=document_id,
    )


@router.get(
    "/document/{document_id}.bib",
    response_class=PlainTextResponse,
    summary="Download a single document's BibTeX entry as text",
)
async def cite_document_bibtex(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> str:
    meta = _metadata_for_document(db, document_id)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail=f"No SourceMetadata found for document {document_id}",
        )
    return _render("bibtex", meta)


@router.get(
    "/export",
    response_class=PlainTextResponse,
    summary="Bulk export — BibTeX for a list of documents",
    description=(
        "Returns a multi-entry BibTeX file. Pass document_ids "
        "as repeated query parameters: "
        "/api/citations/export?document_ids=A&document_ids=B"
    ),
)
async def export_bibtex(
    document_ids: list[str] = Query(default=[]),
    db: Database = Depends(get_library_database),
) -> str:
    entries = []
    for doc_id in document_ids:
        meta = _metadata_for_document(db, doc_id)
        if meta is not None:
            entries.append(_render("bibtex", meta))
    return "\n\n".join(entries)
