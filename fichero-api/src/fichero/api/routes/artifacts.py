"""
Artifact Routes

API endpoints for accessing processing artifacts (transcriptions, summaries, entities, etc.)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import Artifact, Document

logger = logging.getLogger(__name__)
router = APIRouter()


# Response models
class ArtifactResponse(BaseModel):
    """Artifact response with formatted data."""

    id: str
    document_id: str
    artifact_type: str
    content: Optional[str] = None
    data: Optional[dict] = None
    version: int
    provider: Optional[str] = None
    model: Optional[str] = None
    confidence: Optional[float] = None
    reviewed: bool
    created_at: str


class ArtifactListResponse(BaseModel):
    """Response for listing artifacts."""

    artifacts: list[ArtifactResponse]
    total: int


# Routes


@router.get("/")
async def list_all_artifacts(
    artifact_type: Optional[str] = Query(None, description="Filter by artifact type"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Database = Depends(get_library_database),
) -> ArtifactListResponse:
    """List all artifacts in the library.

    Returns artifacts sorted by creation date (newest first).
    """
    query_kwargs = {}
    if artifact_type:
        query_kwargs["artifact_type"] = artifact_type

    artifacts = (
        db.query(Artifact, **query_kwargs) if query_kwargs else db.query(Artifact)
    )
    artifacts.sort(key=lambda a: a.created_at, reverse=True)

    total = len(artifacts)
    artifacts = artifacts[offset : offset + limit]

    response_artifacts = [
        ArtifactResponse(
            id=a.id,
            document_id=a.document_id,
            artifact_type=a.artifact_type,
            content=a.content,
            data=a.data,
            version=a.version,
            provider=a.provider,
            model=a.model,
            confidence=a.confidence,
            reviewed=a.reviewed,
            created_at=a.created_at.isoformat() if a.created_at else "",
        )
        for a in artifacts
    ]
    return ArtifactListResponse(artifacts=response_artifacts, total=total)


@router.get("/types")
async def list_artifact_types(
    db: Database = Depends(get_library_database),
) -> list[str]:
    """List all artifact types in the library.

    Useful for filtering UI.
    """
    artifacts = db.query(Artifact)
    types = set(a.artifact_type for a in artifacts if a.artifact_type)
    return sorted(types)


@router.get("/document/{doc_id}")
async def list_document_artifacts(
    doc_id: str,
    artifact_type: Optional[str] = Query(None, description="Filter by artifact type"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Database = Depends(get_library_database),
) -> ArtifactListResponse:
    """List all artifacts for a document.

    Returns artifacts sorted by creation date (newest first).
    """
    # Verify document exists
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    # Collect document IDs to query: the doc itself plus its direct children (pages).
    # Also include the parent when the queried doc is a page — transcription workflows
    # run against the parent PDF and save artifacts there, not per page.
    child_ids = [d.id for d in db.query(Document, parent_id=doc_id)]
    all_doc_ids = [doc_id] + child_ids
    if doc.parent_id:
        all_doc_ids.append(doc.parent_id)

    # Query artifacts across the doc and its children
    all_artifacts = []
    for did in all_doc_ids:
        query_kwargs: dict = {"document_id": did}
        if artifact_type:
            query_kwargs["artifact_type"] = artifact_type
        all_artifacts.extend(db.query(Artifact, **query_kwargs))

    artifacts = all_artifacts

    # Sort by created_at descending
    artifacts.sort(key=lambda a: a.created_at, reverse=True)

    # Apply pagination
    total = len(artifacts)
    artifacts = artifacts[offset : offset + limit]

    # Convert to response format
    response_artifacts = [
        ArtifactResponse(
            id=a.id,
            document_id=a.document_id,
            artifact_type=a.artifact_type,
            content=a.content,
            data=a.data,
            version=a.version,
            provider=a.provider,
            model=a.model,
            confidence=a.confidence,
            reviewed=a.reviewed,
            created_at=a.created_at.isoformat() if a.created_at else "",
        )
        for a in artifacts
    ]

    return ArtifactListResponse(artifacts=response_artifacts, total=total)


@router.get("/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    db: Database = Depends(get_library_database),
) -> ArtifactResponse:
    """Get a specific artifact by ID."""
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=404, detail=f"Artifact not found: {artifact_id}"
        )

    return ArtifactResponse(
        id=artifact.id,
        document_id=artifact.document_id,
        artifact_type=artifact.artifact_type,
        content=artifact.content,
        data=artifact.data,
        version=artifact.version,
        provider=artifact.provider,
        model=artifact.model,
        confidence=artifact.confidence,
        reviewed=artifact.reviewed,
        created_at=artifact.created_at.isoformat() if artifact.created_at else "",
    )


class ArtifactUpdate(BaseModel):
    """Request to update an artifact's editable fields. Used by the V2
    inspector's per-panel edit. Only `content` is editable today; provider,
    model, version etc. are immutable provenance and stay set by the tool
    that produced them.
    """

    content: Optional[str] = None
    reviewed: Optional[bool] = None


@router.put("/{artifact_id}")
async def update_artifact(
    artifact_id: str,
    update: ArtifactUpdate,
    db: Database = Depends(get_library_database),
) -> ArtifactResponse:
    """Update an artifact's editable fields (content, reviewed flag).

    Used by the V2 inspector to let users correct workflow output (e.g. fix
    OCR mistakes in a transcription) without re-running the whole tool. The
    artifact stays attached to its original document and keeps its provider/
    model provenance — we just update the text.
    """
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=404, detail=f"Artifact not found: {artifact_id}"
        )

    if update.content is not None:
        artifact.content = update.content
    if update.reviewed is not None:
        artifact.reviewed = update.reviewed

    db.save(artifact)

    return ArtifactResponse(
        id=artifact.id,
        document_id=artifact.document_id,
        artifact_type=artifact.artifact_type,
        content=artifact.content,
        data=artifact.data,
        version=artifact.version,
        provider=artifact.provider,
        model=artifact.model,
        confidence=artifact.confidence,
        reviewed=artifact.reviewed,
        created_at=artifact.created_at.isoformat() if artifact.created_at else "",
    )


@router.delete("/{artifact_id}", status_code=204)
async def delete_artifact(
    artifact_id: str,
    db: Database = Depends(get_library_database),
) -> None:
    """Delete an artifact."""
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=404, detail=f"Artifact not found: {artifact_id}"
        )

    db.delete(artifact)
    logger.info(f"Deleted artifact {artifact_id}")
