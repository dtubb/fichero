"""Claim Links API - Canonical FastAPI routes for knowledge claim links.

This module implements dedicated routes for claim-to-claim relationship operations,
providing a clean separation from the broader knowledge graph functionality.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    ClaimRelationType,
    KnowledgeClaim,
    KnowledgeClaimLink,
)

router = APIRouter(tags=["claim-links"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ClaimLinkCreateRequest(BaseModel):
    """Request to create a link between claims."""

    related_claim_id: str
    relation_type: ClaimRelationType
    link_quality: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimLinkUpdateRequest(BaseModel):
    """Request to update a claim link."""

    relation_type: ClaimRelationType | None = None
    link_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: str | None = None
    metadata: dict[str, Any] | None = None


class ClaimLinkResponse(BaseModel):
    """Response model for claim link operations."""

    id: str
    claim_id: str
    related_claim_id: str
    relation_type: str
    link_quality: float
    evidence: str | None = None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime | None = None


# =============================================================================
# Claim Link CRUD Endpoints
# =============================================================================


@router.post("/claims/{claim_id}/links", response_model=KnowledgeClaimLink)
async def create_claim_link(
    claim_id: str,
    request: ClaimLinkCreateRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaimLink:
    """Create a link between two claims."""
    # Validate source claim exists
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    # Validate related claim exists
    related_claim = db.get(KnowledgeClaim, request.related_claim_id)
    if related_claim is None:
        raise HTTPException(
            status_code=404,
            detail=f"Related claim not found: {request.related_claim_id}",
        )

    # Create the link
    link = KnowledgeClaimLink(
        claim_id=claim_id,
        related_claim_id=request.related_claim_id,
        relation_type=request.relation_type,
        link_quality=request.link_quality,
        evidence=request.evidence,
        metadata=request.metadata,
        created_at=datetime.now(),
    )
    db.save(link)
    return link


@router.get("/claims/{claim_id}/links", response_model=list[KnowledgeClaimLink])
async def list_claim_links(
    claim_id: str,
    db: Database = Depends(get_library_database),
) -> list[KnowledgeClaimLink]:
    """List all links for a given claim (both outgoing and incoming)."""
    # Validate claim exists
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    # Get outgoing links (claim_id -> related_claim_id)
    outgoing = db.query(KnowledgeClaimLink, claim_id=claim_id)
    # Get incoming links (related_claim_id <- claim_id)
    incoming = db.query(KnowledgeClaimLink, related_claim_id=claim_id)

    # Merge and deduplicate by ID
    merged = {link.id: link for link in [*outgoing, *incoming]}
    return sorted(merged.values(), key=lambda link: link.created_at, reverse=True)


@router.get("/claim-links/{link_id}", response_model=KnowledgeClaimLink)
async def get_claim_link(
    link_id: str,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaimLink:
    """Get a specific claim link by ID."""
    link = db.get(KnowledgeClaimLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail=f"Claim link not found: {link_id}")
    return link


@router.patch("/claim-links/{link_id}", response_model=KnowledgeClaimLink)
async def update_claim_link(
    link_id: str,
    request: ClaimLinkUpdateRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaimLink:
    """Update an existing claim link."""
    link = db.get(KnowledgeClaimLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail=f"Claim link not found: {link_id}")

    # Update fields
    data = request.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(link, key, value)
    db.save(link)
    return link


@router.delete("/claim-links/{link_id}")
async def delete_claim_link(
    link_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    """Delete a claim link (hard delete)."""
    link = db.get(KnowledgeClaimLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail=f"Claim link not found: {link_id}")

    # Delete from database
    db.delete(link)
    return {"success": True, "link_id": link_id, "operation": "deleted"}


# =============================================================================
# Claim Link Utility Endpoints
# =============================================================================


@router.get("/claims/{claim_id}/related", response_model=list[KnowledgeClaim])
async def get_related_claims(
    claim_id: str,
    relation_type: ClaimRelationType | None = None,
    db: Database = Depends(get_library_database),
) -> list[KnowledgeClaim]:
    """Get all claims related to a given claim."""
    # Validate source claim exists
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    # Get all links for this claim
    outgoing = db.query(KnowledgeClaimLink, claim_id=claim_id)
    incoming = db.query(KnowledgeClaimLink, related_claim_id=claim_id)

    # Collect related claim IDs
    related_ids: set[str] = set()
    for link in outgoing:
        if relation_type is None or link.relation_type == relation_type:
            related_ids.add(link.related_claim_id)
    for link in incoming:
        if relation_type is None or link.relation_type == relation_type:
            related_ids.add(link.claim_id)

    # Fetch related claims
    related_claims = [db.get(KnowledgeClaim, rid) for rid in related_ids]
    return [c for c in related_claims if c is not None]
