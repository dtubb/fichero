"""Bibliographic metadata API (#908)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from fichero.actions.registry import ActionContext, registry
from fichero.api.auth import action_context
from fichero.api.library_header import require_library_path
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.models import Document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bibliography")


class MetadataResponse(BaseModel):
    document_id: str
    metadata: dict[str, Any]


def _resolve_action_ctx(
    ctx: ActionContext | object,
    *,
    library_path: str | object | None = None,
) -> ActionContext:
    if isinstance(ctx, ActionContext):
        return ctx
    return ActionContext(
        library_path=library_path if isinstance(library_path, str) else None
    )


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


class AttachRequest(ImportRequest):
    """Attach one bibliography record to a document."""


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
    db: Database = Depends(get_library_database_for_write),
) -> ImportResponse:
    entries = _parse_bibliography(request.text, request.format)
    return ImportResponse(count=len(entries), entries=entries)


@router.post(
    "/document/{document_id}/attach",
    response_model=MetadataResponse,
    summary="Attach a BibTeX / RIS / CSL-JSON record to a document",
    description=(
        "Parses a single bibliographic record and writes it into "
        "document.source_metadata, including canonical bibtex."
    ),
)
async def attach_record(
    document_id: str,
    request: AttachRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    ctx: ActionContext | object = Depends(action_context),
) -> MetadataResponse:
    ctx = _resolve_action_ctx(ctx, library_path=x_fichero_library_path)
    result = registry.invoke(
        db,
        "bibliography.attach",
        {
            "document_id": document_id,
            "text": request.text,
            "format": request.format,
        },
        ctx,
    )
    return MetadataResponse.model_validate(result.result)


def _parse_bibliography(text: str, fmt: str | None) -> list[dict[str, Any]]:
    """Parse BibTeX / RIS / CSL-JSON content into entry dicts (format auto-
    detected when ``fmt`` is None). Shared by the import + attach paths."""
    from fichero.bibliography.importers import (
        detect_format,
        read_bibtex,
        read_csl_json,
        read_ris,
    )

    resolved = fmt or detect_format(text)
    if resolved == "bibtex":
        return read_bibtex(text)
    if resolved == "ris":
        return read_ris(text)
    if resolved == "csl_json":
        return read_csl_json(text)
    raise HTTPException(400, "Format not recognised — try 'bibtex', 'ris', or 'csl_json'")


def _attach_record_impl(
    db: Database, document_id: str, text: str, fmt: str | None
) -> tuple[Document, dict[str, Any] | None]:
    """Parse a single bibliographic record and write it into a document's
    ``source_metadata`` — the proven body of ``POST .../attach``, extracted so
    BOTH the route and the ``bibliography.attach`` action drive the same code.
    Returns ``(document, previous_source_metadata)`` (the previous value is the
    undo payload). Raises ``HTTPException`` on unknown id / unparsable input."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, f"Document not found: {document_id}")

    entries = _parse_bibliography(text, fmt)
    if not entries:
        raise HTTPException(400, "No parsable bibliography record found")

    before = doc.source_metadata
    doc.source_metadata = entries[0]
    doc.updated_at = datetime.now()
    db.save(doc)
    return doc, before


def _patch_metadata_impl(
    db: Database, document_id: str, metadata: dict[str, Any]
) -> tuple[Document, dict[str, Any] | None]:
    """Replace a document's ``source_metadata`` — the proven body of the
    ``PATCH /bibliography/document/{id}`` route, extracted so BOTH the route and
    the ``bibliography.patch_metadata`` action drive the same code (iterate-not-
    replace). Returns ``(document, previous_source_metadata)``; the previous
    value is the undo payload. Raises ``HTTPException(404)`` on unknown id."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, f"Document not found: {document_id}")
    before = doc.source_metadata
    doc.source_metadata = metadata
    doc.updated_at = datetime.now()
    db.save(doc)
    return doc, before


class ExportRequest(BaseModel):
    document_ids: list[str]


@router.post(
    "/export.bib",
    response_class=PlainTextResponse,
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
    db: Database = Depends(get_library_database_for_write),
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
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    ctx: ActionContext | object = Depends(action_context),
) -> MetadataResponse:
    ctx = _resolve_action_ctx(ctx, library_path=x_fichero_library_path)
    result = registry.invoke(
        db,
        "bibliography.patch_metadata",
        {
            "document_id": document_id,
            "metadata": request.metadata,
        },
        ctx,
    )
    return MetadataResponse.model_validate(result.result)


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
    db: Database = Depends(get_library_database_for_write),
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


# ---------------------------------------------------------------------------
# Action layer registration (EPIC #1848 sweep #2014) — bibliography mutations
# ---------------------------------------------------------------------------
#
# Each action WRAPS the proven `_impl` above (iterate-not-replace) and routes
# through `registry.invoke`, which writes the generic ActionAudit + emits one
# typed change event. Bibliographic metadata lives on `Document.source_metadata`,
# so the touched ids are document_ids. Both mutations are undoable: their inverse
# restores the prior `source_metadata` via `bibliography.patch_metadata` itself —
# the before/after snapshots in the ChangeSpec ARE the undo payload.
#
# NOT wrapped (noted for the manager): `import_bibliography` parses only and
# persists nothing (pure transform — no audit needed); `resolve` and
# `run_extractor` perform async network / LLM I/O, which the sync `execute(db,
# params, ctx)` contract can't host — they need an async-action variant (future).

from fichero.actions.registry import action, ChangeSpec  # noqa: E402


class BibliographyPatchMetadataParams(BaseModel):
    """Params for bibliography.patch_metadata — replace a document's metadata."""

    document_id: str = Field(description="Target document id")
    metadata: dict[str, Any] = Field(description="New source_metadata dict (replaces)")


class BibliographyAttachParams(BaseModel):
    """Params for bibliography.attach — parse one record into a document."""

    document_id: str = Field(description="Target document id")
    text: str = Field(description="BibTeX / RIS / CSL-JSON record content")
    format: str | None = Field(default=None, description="Format hint; auto-detected when None")


def _invert_to_patch_metadata(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Inverse of any source_metadata mutation: restore the prior dict. The
    PATCH params require a dict, so a previously-absent (None) metadata round-
    trips to ``{}`` — semantically equivalent to "no metadata"."""
    if not before:
        return None
    document_id = before.get("document_id")
    if not document_id:
        return None
    prior = before.get("source_metadata") or {}
    return ("bibliography.patch_metadata", {"document_id": document_id, "metadata": prior})


@action(
    "bibliography.patch_metadata",
    BibliographyPatchMetadataParams,
    domains=["bibliography", "document"],
    undoable=True,
    invert=_invert_to_patch_metadata,
)
def _action_patch_metadata(
    db: Database, params: BibliographyPatchMetadataParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    doc, before_meta = _patch_metadata_impl(db, params.document_id, params.metadata)
    spec = ChangeSpec(
        domains=["bibliography", "document"],
        target_ids=[doc.id],
        before={"document_id": doc.id, "source_metadata": before_meta},
        after={"document_id": doc.id, "source_metadata": doc.source_metadata},
        emit_type="bibliography.updated",
        document_ids=[doc.id],
    )
    return {"document_id": doc.id, "metadata": doc.source_metadata or {}}, spec


@action(
    "bibliography.attach",
    BibliographyAttachParams,
    domains=["bibliography", "document"],
    undoable=True,
    invert=_invert_to_patch_metadata,
)
def _action_attach_record(
    db: Database, params: BibliographyAttachParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    doc, before_meta = _attach_record_impl(db, params.document_id, params.text, params.format)
    spec = ChangeSpec(
        domains=["bibliography", "document"],
        target_ids=[doc.id],
        before={"document_id": doc.id, "source_metadata": before_meta},
        after={"document_id": doc.id, "source_metadata": doc.source_metadata},
        emit_type="bibliography.updated",
        document_ids=[doc.id],
    )
    return {"document_id": doc.id, "metadata": doc.source_metadata or {}}, spec
