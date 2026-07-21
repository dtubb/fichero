"""Claim Links API - Canonical FastAPI routes for knowledge claim links.

This module implements dedicated routes for claim-to-claim relationship operations,
providing a clean separation from the broader knowledge graph functionality.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.api.auth import action_context
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.actions.registry import registry
from fichero.db import Database
from fichero.knowledge_models import (
    ClaimRelationType,
    KnowledgeClaim,
    KnowledgeClaimLink,
)
from fichero.models import ClaimLinkListResponse, ClaimListResponse

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


class ClaimLinkDeletedResponse(BaseModel):
    success: bool
    link_id: str
    operation: str


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
# Claim-link mutation impls — the proven business logic, extracted so BOTH the
# route handler and the audited action (EPIC #1848 / #2014) drive the SAME code
# (iterate-not-replace). Emission stays with the caller; each raises
# HTTPException on bad input exactly as the route did.
# =============================================================================


def create_claim_link_impl(
    db: Database, claim_id: str, request: ClaimLinkCreateRequest
) -> KnowledgeClaimLink:
    """Create + persist a link between two existing claims."""
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


def update_claim_link_impl(
    db: Database, link_id: str, request: "ClaimLinkUpdateRequest"
) -> tuple[KnowledgeClaimLink, dict[str, Any]]:
    """Apply a partial update to a claim link. Returns (link, before_snapshot)."""
    link = db.get(KnowledgeClaimLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail=f"Claim link not found: {link_id}")

    before = link.model_dump(mode="json")
    data = request.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in data.items():
        setattr(link, key, value)
    db.save(link)
    return link, before


def delete_claim_link_impl(
    db: Database, link_id: str
) -> tuple[dict[str, Any], list[str]]:
    """Hard-delete a claim link. Returns (before_snapshot, affected_claim_ids)."""
    link = db.get(KnowledgeClaimLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail=f"Claim link not found: {link_id}")

    before = link.model_dump(mode="json")
    affected_claim_ids = [link.claim_id, link.related_claim_id]
    db.delete(link)
    return before, affected_claim_ids


def restore_claim_link_impl(
    db: Database, snapshot: dict[str, Any]
) -> KnowledgeClaimLink:
    """Re-create a claim link from a JSON snapshot (inverse of update/delete)."""
    link = KnowledgeClaimLink.model_validate(snapshot)
    db.save(link)
    return link


# =============================================================================
# Claim Link CRUD Endpoints
# =============================================================================


@router.post("/claims/{claim_id}/links", response_model=KnowledgeClaimLink)
async def create_claim_link(
    claim_id: str,
    request: ClaimLinkCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> KnowledgeClaimLink:
    """Create a link between two claims."""
    if not isinstance(ctx, ActionContext):
        ctx = ActionContext(actor="system")
    result = registry.invoke(
        db,
        "claim.create_link",
        {"claim_id": claim_id, "link": request.model_dump(mode="json")},
        ctx,
    )
    return KnowledgeClaimLink.model_validate(result.result)


@router.get("/claims/{claim_id}/links", response_model=ClaimLinkListResponse)
async def list_claim_links(
    claim_id: str,
    db: Database = Depends(get_library_database),
) -> ClaimLinkListResponse:
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
    items = sorted(merged.values(), key=lambda link: link.created_at, reverse=True)
    return ClaimLinkListResponse(items=items, count=len(items))


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
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> KnowledgeClaimLink:
    """Update an existing claim link."""
    if not isinstance(ctx, ActionContext):
        ctx = ActionContext(actor="system")
    result = registry.invoke(
        db,
        "claim.update_link",
        {"link_id": link_id, "patch": request.model_dump(mode="json", exclude_unset=True)},
        ctx,
    )
    return KnowledgeClaimLink.model_validate(result.result)


@router.delete("/claim-links/{link_id}")
async def delete_claim_link(
    link_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ClaimLinkDeletedResponse:
    """Delete a claim link (hard delete)."""
    if not isinstance(ctx, ActionContext):
        ctx = ActionContext(actor="system")
    registry.invoke(
        db,
        "claim.delete_link",
        {"link_id": link_id},
        ctx,
    )
    return ClaimLinkDeletedResponse(success=True, link_id=link_id, operation="deleted")


# =============================================================================
# Claim Link Utility Endpoints
# =============================================================================


@router.get("/claims/{claim_id}/related", response_model=ClaimListResponse)
async def get_related_claims(
    claim_id: str,
    relation_type: ClaimRelationType | None = None,
    db: Database = Depends(get_library_database),
) -> ClaimListResponse:
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
    items = [c for c in related_claims if c is not None]
    return ClaimListResponse(items=items, count=len(items))


# =============================================================================
# Action layer registration (EPIC #1848 / #2014) — claim-link CRUD.
# =============================================================================
#
# Each action WRAPS the proven ``*_impl`` above (iterate-not-replace) and routes
# through ``registry.invoke`` so chat tools / App Intents / tests / the audit
# log share ONE path with the typed routes (which stay untouched). Reversible
# pairs:
#   * claim.create_link -> claim.delete_link
#   * claim.update_link -> claim.restore_link  (restore the before-snapshot)
#   * claim.delete_link -> claim.restore_link

from fichero.actions.registry import action, ActionContext, ChangeSpec  # noqa: E402


class ClaimCreateLinkParams(BaseModel):
    """Params for claim.create_link — the owning claim_id + the link body."""

    claim_id: str = Field(description="Claim the link originates from")
    link: ClaimLinkCreateRequest = Field(description="Link to create")


class ClaimUpdateLinkParams(BaseModel):
    """Params for claim.update_link — the link id + a partial patch.

    ``patch`` is a nested :class:`ClaimLinkUpdateRequest` so the registry's
    ``model_validate`` preserves exclude-unset/none semantics.
    """

    link_id: str = Field(description="Claim link id to update")
    patch: ClaimLinkUpdateRequest = Field(description="Partial link update")


class ClaimDeleteLinkParams(BaseModel):
    """Params for claim.delete_link — also the inverse of claim.create_link."""

    link_id: str = Field(description="Claim link id to delete")


class ClaimRestoreLinkParams(BaseModel):
    """Params for claim.restore_link — re-create a link from a JSON snapshot."""

    snapshot: dict[str, Any] = Field(
        description="KnowledgeClaimLink.model_dump snapshot"
    )


def _invert_create_link(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not after:
        return None
    link_id = after.get("link_id")
    if not link_id:
        return None
    return ("claim.delete_link", {"link_id": link_id})


def _invert_restore_from_before(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return ("claim.restore_link", {"snapshot": before})


@action(
    "claim.create_link",
    ClaimCreateLinkParams,
    domains=["claim"],
    undoable=True,
    invert=_invert_create_link,
)
def _action_create_link(
    db: Database, params: ClaimCreateLinkParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    link = create_claim_link_impl(db, params.claim_id, params.link)
    claim_ids = [link.claim_id, link.related_claim_id]
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=[link.id],
        after={"link_id": link.id},
        emit_type="claim.linked",
        claim_ids=claim_ids,
    )
    return link.model_dump(mode="json"), spec


@action(
    "claim.update_link",
    ClaimUpdateLinkParams,
    domains=["claim"],
    undoable=True,
    invert=_invert_restore_from_before,
)
def _action_update_link(
    db: Database, params: ClaimUpdateLinkParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    link, before = update_claim_link_impl(db, params.link_id, params.patch)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=[link.id],
        before=before,
        after=link.model_dump(mode="json"),
        emit_type="claim.linked",
        claim_ids=[link.claim_id, link.related_claim_id],
    )
    return link.model_dump(mode="json"), spec


@action(
    "claim.delete_link",
    ClaimDeleteLinkParams,
    domains=["claim"],
    undoable=True,
    invert=_invert_restore_from_before,
)
def _action_delete_link(
    db: Database, params: ClaimDeleteLinkParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before, affected_claim_ids = delete_claim_link_impl(db, params.link_id)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=[params.link_id],
        before=before,
        after=None,
        emit_type="claim.linked",
        claim_ids=affected_claim_ids,
    )
    return {"deleted_link_id": params.link_id}, spec


@action(
    "claim.restore_link",
    ClaimRestoreLinkParams,
    domains=["claim"],
    undoable=False,
)
def _action_restore_link(
    db: Database, params: ClaimRestoreLinkParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    link = restore_claim_link_impl(db, params.snapshot)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=[link.id],
        after=link.model_dump(mode="json"),
        emit_type="claim.linked",
        claim_ids=[link.claim_id, link.related_claim_id],
    )
    return link.model_dump(mode="json"), spec
