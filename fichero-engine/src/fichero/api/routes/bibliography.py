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
