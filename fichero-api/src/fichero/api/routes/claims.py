"""Claims API - Canonical FastAPI routes for knowledge claims.

This module implements dedicated routes for knowledge claim operations,
providing a clean separation from the broader knowledge graph functionality.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    ClaimCurationState,
    ClaimType,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
    PredictionMetadata,
    SourceType,
)
from fichero.models import Document

router = APIRouter(prefix="/claims", tags=["claims"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ClaimCreateRequest(BaseModel):
    """Request to create a knowledge claim."""

    text: str
    source_document_id: str
    source_segment_id: str | None = None
    source_page_label: str | None = None
    source_excerpt: str | None = None
    source_ref: str | None = None
    entity_ids: list[str] = Field(default_factory=list)
    curation_state: ClaimCurationState = ClaimCurationState.unreviewed
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    predicted_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    predicted_by: list[str] = Field(default_factory=list)
    prediction: PredictionMetadata | None = None
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "human"
    # Multi-source support
    source_type: SourceType = SourceType.document
    source_ids: list[str] = Field(default_factory=list)
    source_page_labels: list[str] = Field(default_factory=list)
    source_languages: list[str] = Field(default_factory=list)
    # Claim classification
    claim_type: ClaimType | None = None
    epistemic_status: EpistemicStatus | None = None


class ClaimPatchRequest(BaseModel):
    """Request to patch/update a knowledge claim."""

    text: str | None = None
    source_segment_id: str | None = None
    source_page_label: str | None = None
    source_excerpt: str | None = None
    source_ref: str | None = None
    entity_ids: list[str] | None = None
    curation_state: ClaimCurationState | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    predicted_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    predicted_by: list[str] | None = None
    prediction: PredictionMetadata | None = None
    language: str | None = None
    metadata: dict[str, Any] | None = None
    source_type: SourceType | None = None
    source_ids: list[str] | None = None
    source_page_labels: list[str] | None = None
    source_languages: list[str] | None = None
    claim_type: ClaimType | None = None
    epistemic_status: EpistemicStatus | None = None


# =============================================================================
# Claim CRUD Endpoints
# =============================================================================


@router.post("", response_model=KnowledgeClaim)
async def create_claim(
    request: ClaimCreateRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaim:
    """Create a new knowledge claim."""
    # Validate source document exists
    source_doc = db.get(Document, request.source_document_id)
    if source_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source document not found: {request.source_document_id}",
        )

    # Validate entity IDs exist
    missing_entities = [
        entity_id
        for entity_id in request.entity_ids
        if db.get(KnowledgeEntity, entity_id) is None
    ]
    if missing_entities:
        raise HTTPException(
            status_code=404, detail=f"Unknown entities: {missing_entities}"
        )

    now = datetime.now()
    claim = KnowledgeClaim(
        text=request.text.strip(),
        source_document_id=request.source_document_id,
        source_segment_id=request.source_segment_id,
        source_page_label=request.source_page_label,
        source_excerpt=request.source_excerpt,
        source_ref=request.source_ref,
        entity_ids=request.entity_ids,
        curation_state=request.curation_state,
        confidence=request.confidence,
        predicted_confidence=request.predicted_confidence,
        predicted_by=request.predicted_by,
        prediction=request.prediction,
        language=request.language,
        metadata=request.metadata,
        created_by=request.created_by,
        created_at=now,
        updated_at=now,
        source_type=request.source_type,
        source_ids=request.source_ids,
        source_page_labels=request.source_page_labels,
        source_languages=request.source_languages,
        claim_type=request.claim_type,
        epistemic_status=request.epistemic_status,
    )
    db.save(claim)
    return claim


@router.patch("/{claim_id}", response_model=KnowledgeClaim)
async def patch_claim(
    claim_id: str,
    request: ClaimPatchRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaim:
    """Update an existing knowledge claim."""
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    data = request.model_dump(exclude_unset=True)

    # Validate entity IDs if provided
    if "entity_ids" in data and data["entity_ids"] is not None:
        missing_entities = [
            entity_id
            for entity_id in data["entity_ids"]
            if db.get(KnowledgeEntity, entity_id) is None
        ]
        if missing_entities:
            raise HTTPException(
                status_code=404, detail=f"Unknown entities: {missing_entities}"
            )

    # Update claim fields
    for key, value in data.items():
        setattr(claim, key, value)
    claim.updated_at = datetime.now()
    db.save(claim)
    return claim


@router.get("/{claim_id}", response_model=KnowledgeClaim)
async def get_claim(
    claim_id: str,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaim:
    """Get a knowledge claim by ID."""
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")
    return claim


# =============================================================================
# Claim Listing and Filtering
# =============================================================================


def _normalize_text(value: str | None) -> str:
    """Normalize text for comparison."""
    return (value or "").strip().lower()


@router.get("", response_model=list[KnowledgeClaim])
async def list_claims(
    q: Annotated[str | None, Query()] = None,
    entity_id: Annotated[str | None, Query()] = None,
    curated_only: Annotated[bool, Query()] = False,
    curation_state: Annotated[ClaimCurationState | None, Query()] = None,
    claim_type: Annotated[ClaimType | None, Query()] = None,
    epistemic_status: Annotated[EpistemicStatus | None, Query()] = None,
    source_document_id: Annotated[str | None, Query()] = None,
    source_language: Annotated[str | None, Query()] = None,
    source_type: Annotated[SourceType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Database = Depends(get_library_database),
) -> list[KnowledgeClaim]:
    """List knowledge claims with optional filtering."""
    claims = db.all(KnowledgeClaim)

    # Apply filters
    if q:
        needle = _normalize_text(q)
        claims = [c for c in claims if needle in _normalize_text(c.text)]
    if entity_id:
        claims = [c for c in claims if entity_id in c.entity_ids]
    if curated_only:
        claims = [c for c in claims if c.curation_state == ClaimCurationState.curated]
    if curation_state:
        claims = [c for c in claims if c.curation_state == curation_state]
    if claim_type:
        claims = [c for c in claims if c.claim_type == claim_type]
    if epistemic_status:
        claims = [c for c in claims if c.epistemic_status == epistemic_status]
    if source_document_id:
        claims = [c for c in claims if c.source_document_id == source_document_id]
    if source_language:
        claims = [c for c in claims if source_language in c.source_languages]
    if source_type:
        claims = [c for c in claims if c.source_type == source_type]

    return claims[offset : offset + limit]
