"""Bibliographic metadata API (#908)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import Document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bibliography", tags=["knowledge-graph"])


class MetadataResponse(BaseModel):
    document_id: str
    metadata: dict[str, Any]


@router.get(
    "/document/{document_id}",
    response_model=MetadataResponse,
    summary="Get a document's bibliographic metadata",
)
async def get_metadata(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> MetadataResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, f"Document not found: {document_id}")
    return MetadataResponse(
        document_id=document_id, metadata=doc.source_metadata or {}
    )


class ImportRequest(BaseModel):
    """Inline import — the file content as a string."""
    text: str
    format: str | None = None  # auto-detected when None


class ImportResponse(BaseModel):
    count: int
    entries: list[dict[str, Any]]


@router.post(
    "/import",
    response_model=ImportResponse,
    summary="Parse BibTeX / RIS / CSL JSON into SourceMetadata dicts (#909)",
    description=(
        "Parses bibliography file content posted as the request body's "
        "``text`` field. Returns the parsed entries WITHOUT writing "
        "them to any document — the caller decides how to associate "
        "each entry with an in-library document (auto-match by title "
        "or manual pick)."
    ),
)
async def import_bibliography(
    request: ImportRequest,
    db: Database = Depends(get_library_database),
) -> ImportResponse:
    from fichero.bibliography.importers import (
        detect_format,
        read_bibtex,
        read_csl_json,
        read_ris,
    )

    fmt = request.format or detect_format(request.text)
    if fmt == "bibtex":
        entries = read_bibtex(request.text)
    elif fmt == "ris":
        entries = read_ris(request.text)
    elif fmt == "csl_json":
        entries = read_csl_json(request.text)
    else:
        raise HTTPException(
            400,
            "Format not recognised — try 'bibtex', 'ris', or 'csl_json'",
        )
    return ImportResponse(count=len(entries), entries=entries)


class ExportRequest(BaseModel):
    document_ids: list[str]


@router.post(
    "/export.bib",
    summary="Bulk export multiple documents as BibTeX",
    description=(
        "Returns a multi-entry .bib file built from each document's "
        "source_metadata. Documents without metadata are skipped."
    ),
)
async def export_bibtex(
    request: ExportRequest,
    db: Database = Depends(get_library_database),
):
    from fastapi.responses import PlainTextResponse

    from fichero.bibliography.importers import write_bibtex

    entries: list[dict[str, Any]] = []
    for doc_id in request.document_ids:
        doc = db.get(Document, doc_id)
        if doc is None or not doc.source_metadata:
            continue
        entries.append(doc.source_metadata)
    return PlainTextResponse(write_bibtex(entries))


class ResolveRequest(BaseModel):
    doi: str | None = None
    isbn: str | None = None


@router.post(
    "/resolve",
    response_model=MetadataResponse,
    summary="Resolve a DOI or ISBN via Crossref / Open Library (#910)",
    description=(
        "Online lookup — Crossref for DOIs, Open Library for ISBNs. "
        "Free, no API key needed. Returns the resolved metadata "
        "merged with whatever's already on the document. NOT "
        "associated with a document by default; set document_id "
        "to merge the result into a document's source_metadata."
    ),
)
async def resolve(
    request: ResolveRequest,
    document_id: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> MetadataResponse:
    from fichero.bibliography.doi_lookup import resolve_doi, resolve_isbn

    resolved: dict[str, Any] = {}
    if request.doi:
        resolved = await resolve_doi(request.doi)
    if not resolved and request.isbn:
        resolved = await resolve_isbn(request.isbn)
    if not resolved:
        raise HTTPException(404, "DOI / ISBN did not resolve to any metadata")

    if document_id is not None:
        doc = db.get(Document, document_id)
        if doc is None:
            raise HTTPException(404, f"Document not found: {document_id}")
        # Merge: existing curated values win over resolved.
        existing = doc.source_metadata or {}
        merged = dict(existing)
        for key, value in resolved.items():
            if not value:
                continue
            if key in merged and merged[key]:
                continue
            merged[key] = value
        doc.source_metadata = merged
        doc.updated_at = datetime.now()
        db.save(doc)
        return MetadataResponse(document_id=document_id, metadata=merged)

    return MetadataResponse(document_id="", metadata=resolved)


class MetadataPatchRequest(BaseModel):
    metadata: dict[str, Any]


@router.patch(
    "/document/{document_id}",
    response_model=MetadataResponse,
    summary="Set or update a document's bibliographic metadata",
    description=(
        "Replaces the document's source_metadata dict. To merge "
        "rather than replace, GET first and pass the merged dict."
    ),
)
async def patch_metadata(
    document_id: str,
    request: MetadataPatchRequest,
    db: Database = Depends(get_library_database),
) -> MetadataResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, f"Document not found: {document_id}")
    doc.source_metadata = request.metadata
    doc.updated_at = datetime.now()
    db.save(doc)
    return MetadataResponse(document_id=document_id, metadata=doc.source_metadata)


@router.post(
    "/document/{document_id}/extract",
    response_model=MetadataResponse,
    summary="Run the bibliographic extractor on a document",
    description=(
        "Pulls PDF metadata via PyMuPDF + optionally LLM-extracts "
        "from the first page text. Merges with existing curated "
        "metadata — user values are preserved. Returns the new "
        "merged dict and writes it back to the document."
    ),
)
async def run_extractor(
    document_id: str,
    use_llm: bool = Query(
        default=False,
        description=(
            "When true, in addition to PDF metadata run an Apple "
            "Intelligence first-page extractor. Requires a configured "
            "LLM."
        ),
    ),
    db: Database = Depends(get_library_database),
) -> MetadataResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, f"Document not found: {document_id}")

    from fichero.bibliography.extractor import extract_full

    llm_config = None
    if use_llm:
        # Resolve the user's default LLM the same way other workflows do.
        from fichero.llm import LLMConfig
        from fichero.settings import settings

        llm_config = LLMConfig(
            provider=settings.default_llm_provider or "apple",
            model=settings.default_llm_model or "apple-intelligence",
        )

    merged = await extract_full(doc, llm_config=llm_config)
    doc.source_metadata = merged
    doc.updated_at = datetime.now()
    db.save(doc)
    return MetadataResponse(document_id=document_id, metadata=merged)
