"""Sources API - Canonical FastAPI routes for knowledge sources.

This module implements the "sources" route surface requested in issue #364:
"Canonical FastAPI knowledge write path and route surface".

The sources route provides CRUD operations for Documents that serve as sources
for claims. This ensures no direct client datastore writes for knowledge operations.

Design Decisions:
1. Reuses the Document model (sources = Documents marked as document_type="source")
2. Enforces referential integrity with claims via source_document_id
3. Provides dedicated /sources routes for clarity and API consistency
4. Follows the same pattern as /entities, /claims, /claims/{id}/links
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import Document

router = APIRouter(tags=["sources"])


class SourceUpsertRequest(BaseModel):
    """Request to create or update a source (Document)."""

    id: str | None = None
    title: str
    file_path: str
    document_type: str = "source"
    metadata: dict = {}


class SourceUpsertResponse(BaseModel):
    """Response after upserting a source."""

    id: str
    title: str
    file_path: str
    document_type: str
    metadata: dict


@router.post("", response_model=SourceUpsertResponse)
async def upsert_source(
    request: SourceUpsertRequest,
    db: Database = Depends(get_library_database),
) -> SourceUpsertResponse:
    """Create or update a source (Document)."""
    document = db.get(Document, request.id) if request.id else None
    if document is None:
        document = Document(
            id=request.id,
            title=request.title.strip(),
            file_path=request.file_path.strip(),
            document_type="source",
            metadata=request.metadata,
        )
    else:
        document.title = request.title.strip()
        document.file_path = request.file_path.strip()
        document.document_type = "source"
        document.metadata = request.metadata
    db.save(document)
    db.commit()
    return SourceUpsertResponse(
        id=document.id,
        title=document.title,
        file_path=document.file_path,
        document_type=document.document_type,
        metadata=document.metadata,
    )


@router.get("", response_model=list[SourceUpsertResponse])
async def list_sources(
    db: Database = Depends(get_library_database),
) -> list[SourceUpsertResponse]:
    """List all sources (Documents with document_type='source')."""
    documents = db.all(Document)
    return [
        SourceUpsertResponse(
            id=d.id,
            title=d.title,
            file_path=d.file_path,
            document_type=d.document_type,
            metadata=d.metadata,
        )
        for d in documents
        if d.document_type == "source"
    ]


@router.get("/{source_id}", response_model=SourceUpsertResponse)
async def get_source(
    source_id: str,
    db: Database = Depends(get_library_database),
) -> SourceUpsertResponse:
    """Get a specific source."""
    document = db.get(Document, source_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
    if document.document_type != "source":
        raise HTTPException(
            status_code=400, detail=f"Document is not a source: {source_id}"
        )
    return SourceUpsertResponse(
        id=document.id,
        title=document.title,
        file_path=document.file_path,
        document_type=document.document_type,
        metadata=document.metadata,
    )


@router.put("/{source_id}", response_model=SourceUpsertResponse)
async def update_source(
    source_id: str,
    request: SourceUpsertRequest,
    db: Database = Depends(get_library_database),
) -> SourceUpsertResponse:
    """Update an existing source."""
    document = db.get(Document, source_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
    if document.document_type != "source":
        raise HTTPException(
            status_code=400, detail=f"Document is not a source: {source_id}"
        )
    document.title = request.title.strip()
    document.file_path = request.file_path.strip()
    document.metadata = request.metadata
    db.save(document)
    db.commit()
    return SourceUpsertResponse(
        id=document.id,
        title=document.title,
        file_path=document.file_path,
        document_type=document.document_type,
        metadata=document.metadata,
    )


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: str,
    db: Database = Depends(get_library_database),
) -> None:
    """Delete a source."""
    document = db.get(Document, source_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
    if document.document_type != "source":
        raise HTTPException(
            status_code=400, detail=f"Document is not a source: {source_id}"
        )
    db.delete(document)
    db.commit()
