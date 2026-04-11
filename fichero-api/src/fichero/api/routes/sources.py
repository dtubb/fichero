"""Sources API - Canonical FastAPI routes for knowledge sources.

This module implements the "sources" route surface requested in issue #364.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import Document

router = APIRouter(tags=["sources"])

_SOURCE_METADATA_FLAG = "_fichero_source"


class SourceUpsertRequest(BaseModel):
    """Request to create or update a source document."""

    id: str | None = None
    title: str
    file_path: str
    document_type: str = "source"
    metadata: dict = Field(default_factory=dict)


class SourceUpsertResponse(BaseModel):
    """Response after upserting or reading a source document."""

    id: str
    title: str
    file_path: str
    document_type: str
    metadata: dict


def _is_source_document(document: Document) -> bool:
    return bool(document.metadata.get(_SOURCE_METADATA_FLAG))


def _to_response(document: Document) -> SourceUpsertResponse:
    metadata = dict(document.metadata)
    metadata.pop(_SOURCE_METADATA_FLAG, None)
    return SourceUpsertResponse(
        id=document.id,
        title=document.name,
        file_path=document.path or "",
        document_type="source",
        metadata=metadata,
    )


def _build_source_metadata(metadata: dict) -> dict:
    source_metadata = dict(metadata)
    source_metadata[_SOURCE_METADATA_FLAG] = True
    return source_metadata


@router.post("", response_model=SourceUpsertResponse)
async def upsert_source(
    request: SourceUpsertRequest,
    db: Database = Depends(get_library_database),
) -> SourceUpsertResponse:
    """Create or update a source (stored as a Document)."""
    if request.document_type != "source":
        raise HTTPException(status_code=400, detail="document_type must be 'source'")

    document = db.get(Document, request.id) if request.id else None
    if document is None:
        kwargs = {
            "name": request.title.strip(),
            "path": request.file_path.strip(),
            "metadata": _build_source_metadata(request.metadata),
        }
        if request.id:
            kwargs["id"] = request.id
        document = Document(**kwargs)
    else:
        document.name = request.title.strip()
        document.path = request.file_path.strip()
        document.metadata = _build_source_metadata(request.metadata)

    db.save(document)
    return _to_response(document)


@router.get("", response_model=list[SourceUpsertResponse])
async def list_sources(
    db: Database = Depends(get_library_database),
) -> list[SourceUpsertResponse]:
    """List all source documents."""
    return [_to_response(d) for d in db.all(Document) if _is_source_document(d)]


@router.get("/{source_id}", response_model=SourceUpsertResponse)
async def get_source(
    source_id: str,
    db: Database = Depends(get_library_database),
) -> SourceUpsertResponse:
    """Get a specific source."""
    document = db.get(Document, source_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
    if not _is_source_document(document):
        raise HTTPException(status_code=400, detail=f"Document is not a source: {source_id}")
    return _to_response(document)


@router.put("/{source_id}", response_model=SourceUpsertResponse)
async def update_source(
    source_id: str,
    request: SourceUpsertRequest,
    db: Database = Depends(get_library_database),
) -> SourceUpsertResponse:
    """Update an existing source."""
    if request.document_type != "source":
        raise HTTPException(status_code=400, detail="document_type must be 'source'")

    document = db.get(Document, source_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
    if not _is_source_document(document):
        raise HTTPException(status_code=400, detail=f"Document is not a source: {source_id}")

    document.name = request.title.strip()
    document.path = request.file_path.strip()
    document.metadata = _build_source_metadata(request.metadata)
    db.save(document)
    return _to_response(document)


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: str,
    db: Database = Depends(get_library_database),
) -> None:
    """Delete a source."""
    document = db.get(Document, source_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
    if not _is_source_document(document):
        raise HTTPException(status_code=400, detail=f"Document is not a source: {source_id}")
    db.delete(document)
