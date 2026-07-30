"""MCP Tools Routes

Dedicated REST API endpoints for MCP tool adapters.
These endpoints provide thin wrappers around canonical Knowledge API operations,
ensuring no business-logic divergence between MCP and HTTP paths.
"""

from __future__ import annotations

import logging
import uuid
from fichero_server.core.timeutil import utc_now
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.routes.auth.accounts import _require_authenticated_or_bootstrap
from fichero_server.db import Database
from fichero_server.models.knowledge import (
    ClaimType,
    ClaimCurationState,
    EpistemicStatus,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    SourceType,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["mcp-tools"],
    dependencies=[Depends(_require_authenticated_or_bootstrap)],
)


# =============================================================================
# Request/Response Models
# =============================================================================


class KnowledgeEntityUpsertRequest(BaseModel):
    """Request to upsert a knowledge entity via MCP.

    Maps 1:1 to the canonical Knowledge API entity upsert operation.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"canonical_name": "Tokyo", "entity_type": "place", "language": "en"}]},
    )

    id: str | None = Field(None, description="Entity ID for updates", max_length=255)
    canonical_name: str = Field(..., description="Canonical entity name", min_length=1, max_length=512)
    entity_type: str = Field(default="other", description="Entity type", min_length=1, max_length=64)
    aliases: list[str] = Field(default_factory=list, description="Alternative names", max_length=200)
    description: str | None = Field(None, description="Entity description", max_length=4000)
    language: str | None = Field(None, description="ISO 639-1 language code", min_length=2, max_length=16)
    metadata: dict[str, Any] = Field(default_factory=dict, description="Custom metadata")


class KnowledgeEntityUpsertResponse(BaseModel):
    """Response from entity upsert operation."""

    success: bool
    entity_id: str
    operation: str = Field(..., description="'created' or 'updated'")
    entity: dict[str, Any] | None = None


class KnowledgeClaimCreateRequest(BaseModel):
    """Request to create a knowledge claim via MCP.

    Maps 1:1 to the canonical Knowledge API claim creation operation.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"text": "Paris is the capital of France", "source_document_id": "doc-123", "claim_type": "fact"}]},
    )

    text: str = Field(..., description="Claim text content", min_length=1, max_length=10000)
    source_document_id: str | None = Field(None, description="Primary source document ID", max_length=255)
    source_ids: list[str] = Field(default_factory=list, description="Multiple source document IDs", max_length=200)
    source_page_labels: list[str] = Field(default_factory=list, max_length=200)
    source_languages: list[str] = Field(default_factory=list, description="ISO 639-1 codes per source", max_length=200)
    source_type: str = Field(default="document", description="Source type: document, claim, multiple, synthesis", min_length=1, max_length=64)
    entity_ids: list[str] = Field(default_factory=list, description="Linked entity IDs", max_length=200)
    claim_type: str = Field(default="fact", description="Type: fact, analysis, interpretation, argument, historiography, theory", min_length=1, max_length=64)
    epistemic_status: str = Field(default="tentative", description="Status: tentative, confirmed, rejected", min_length=1, max_length=64)
    curation_state: str = Field(default="unreviewed", description="State: unreviewed, shortlisted, curated, rejected", min_length=1, max_length=64)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    language: str | None = Field(None, description="ISO 639-1 language code", min_length=2, max_length=16)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str = Field(default="mcp", min_length=1, max_length=128)


class KnowledgeClaimCreateResponse(BaseModel):
    """Response from claim creation operation."""

    success: bool
    claim_id: str
    claim: dict[str, Any] | None = None


class MCPErrorResponse(BaseModel):
    """Standard MCP error response."""

    error: str
    detail: str | None = None


class MCPEntityDeletedResponse(BaseModel):
    success: bool
    entity_id: str
    operation: str


class MCPClaimDeletedResponse(BaseModel):
    success: bool
    claim_id: str
    operation: str


class MCPEntitiesListResponse(BaseModel):
    entities: list
    total: int
    limit: int
    offset: int


class MCPClaimsListResponse(BaseModel):
    claims: list
    total: int
    limit: int
    offset: int


# =============================================================================
# Helper Functions
# =============================================================================


def _validate_entity_type(entity_type: str) -> EntityType:
    """Validate and convert string entity type to enum."""
    try:
        return EntityType(entity_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type: {entity_type}. Must be one of: {[t.value for t in EntityType]}"
        )


def _validate_claim_type(claim_type: str) -> ClaimType:
    """Validate and convert string claim type to enum."""
    try:
        return ClaimType(claim_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid claim_type: {claim_type}. Must be one of: {[t.value for t in ClaimType]}"
        )


def _validate_curation_state(state: str) -> ClaimCurationState:
    """Validate and convert string curation state to enum."""
    try:
        return ClaimCurationState(state)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid curation_state: {state}. Must be one of: {[s.value for s in ClaimCurationState]}"
        )


def _validate_epistemic_status(status: str) -> EpistemicStatus:
    """Validate and convert string epistemic status to enum."""
    try:
        return EpistemicStatus(status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid epistemic_status: {status}. Must be one of: {[s.value for s in EpistemicStatus]}"
        )


def _validate_source_type(source_type: str) -> SourceType:
    """Validate and convert string source type to enum."""
    try:
        return SourceType(source_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_type: {source_type}. Must be one of: {[t.value for t in SourceType]}"
        )


# =============================================================================
# MCP Tools Endpoints
# =============================================================================


@router.post(
    "/knowledge/entities/upsert",
    response_model=KnowledgeEntityUpsertResponse,
    responses={400: {"model": MCPErrorResponse}, 500: {"model": MCPErrorResponse}},
    summary="Upsert knowledge entity",
    description="Create or update a knowledge entity. Maps 1:1 to canonical Knowledge API.",
)
async def mcp_knowledge_entity_upsert(
    request: KnowledgeEntityUpsertRequest,
    db: Database = Depends(get_library_database_for_write),
) -> KnowledgeEntityUpsertResponse:
    """MCP tool endpoint: Upsert knowledge entity.

    This endpoint provides a thin adapter to the canonical Knowledge API,
    ensuring no business-logic divergence between MCP and HTTP paths.
    """
    entity_type = _validate_entity_type(request.entity_type)

    # Check if entity exists (update) or create new
    if request.id:
        existing = db.get(KnowledgeEntity, request.id)
        if existing:
            existing.canonical_name = request.canonical_name
            existing.entity_type = entity_type
            existing.aliases = request.aliases
            existing.description = request.description
            if request.language:
                existing.language = request.language
            if request.metadata:
                existing.metadata = request.metadata

            db.save(existing)
            logger.info("MCP: Updated entity %s", request.id)
            return KnowledgeEntityUpsertResponse(
                success=True,
                entity_id=existing.id,
                operation="updated",
                entity=existing.model_dump(mode="json"),
            )

    entity = KnowledgeEntity(
        id=request.id or str(uuid.uuid4()),
        canonical_name=request.canonical_name,
        entity_type=entity_type,
        aliases=request.aliases,
        description=request.description,
        language=request.language,
        metadata=request.metadata,
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    db.save(entity)
    logger.info("MCP: Created entity %s", entity.id)
    return KnowledgeEntityUpsertResponse(
        success=True,
        entity_id=entity.id,
        operation="created",
        entity=entity.model_dump(mode="json"),
    )


@router.post(
    "/knowledge/claims/create",
    response_model=KnowledgeClaimCreateResponse,
    responses={400: {"model": MCPErrorResponse}, 500: {"model": MCPErrorResponse}},
    summary="Create knowledge claim",
    description="Create a new knowledge claim. Maps 1:1 to canonical Knowledge API.",
)
async def mcp_knowledge_claim_create(
    request: KnowledgeClaimCreateRequest,
    db: Database = Depends(get_library_database_for_write),
) -> KnowledgeClaimCreateResponse:
    """MCP tool endpoint: Create knowledge claim.

    This endpoint provides a thin adapter to the canonical Knowledge API,
    ensuring no business-logic divergence between MCP and MCP and HTTP paths.
    """
    claim_type = _validate_claim_type(request.claim_type)
    curation_state = _validate_curation_state(request.curation_state)
    epistemic_status = _validate_epistemic_status(request.epistemic_status)
    source_type = _validate_source_type(request.source_type)

    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Claim text is required")

    if request.source_document_id:
        source_docs = [request.source_document_id] + request.source_ids
    elif request.source_ids:
        source_docs = request.source_ids
    else:
        raise HTTPException(status_code=400, detail="At least one source document ID is required")

    for entity_id in request.entity_ids:
        entity = db.get(KnowledgeEntity, entity_id)
        if not entity:
            raise HTTPException(status_code=400, detail=f"Linked entity not found: {entity_id}")

    claim = KnowledgeClaim(
        id=str(uuid.uuid4()),
        text=request.text.strip(),
        source_document_id=request.source_document_id or (request.source_ids[0] if request.source_ids else ""),
        source_ids=source_docs,
        source_page_labels=request.source_page_labels,
        source_languages=request.source_languages,
        source_type=source_type,
        entity_ids=request.entity_ids,
        claim_type=claim_type,
        epistemic_status=epistemic_status,
        curation_state=curation_state,
        confidence=request.confidence,
        language=request.language,
        metadata=request.metadata,
        created_by=request.created_by,
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    db.save(claim)
    logger.info("MCP: Created claim %s", claim.id)
    return KnowledgeClaimCreateResponse(
        success=True,
        claim_id=claim.id,
        claim=claim.model_dump(mode="json"),
    )


@router.get(
    "/knowledge/entities/{entity_id}",
    summary="Get knowledge entity",
    description="Retrieve a knowledge entity by ID.",
)
async def mcp_knowledge_entity_get(
    entity_id: str,
    db: Database = Depends(get_library_database),
) -> KnowledgeEntity:
    """MCP tool endpoint: Get knowledge entity by ID."""
    entity = db.get(KnowledgeEntity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")
    return entity


@router.get(
    "/knowledge/claims/{claim_id}",
    summary="Get knowledge claim",
    description="Retrieve a knowledge claim by ID.",
)
async def mcp_knowledge_claim_get(
    claim_id: str,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaim:
    """MCP tool endpoint: Get knowledge claim by ID."""
    claim = db.get(KnowledgeClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")
    return claim


@router.delete(
    "/knowledge/entities/{entity_id}",
    summary="Delete knowledge entity",
    description="Soft-delete a knowledge entity.",
)
async def mcp_knowledge_entity_delete(
    entity_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> MCPEntityDeletedResponse:
    """MCP tool endpoint: Soft-delete knowledge entity."""
    entity = db.get(KnowledgeEntity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    db.delete(entity)
    logger.info(f"MCP: Deleted entity {entity_id}")
    return MCPEntityDeletedResponse(success=True, entity_id=entity_id, operation="deleted")


@router.delete(
    "/knowledge/claims/{claim_id}",
    summary="Delete knowledge claim",
    description="Soft-delete a knowledge claim.",
)
async def mcp_knowledge_claim_delete(
    claim_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> MCPClaimDeletedResponse:
    """MCP tool endpoint: Soft-delete knowledge claim."""
    claim = db.get(KnowledgeClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    db.delete(claim)
    logger.info(f"MCP: Deleted claim {claim_id}")
    return MCPClaimDeletedResponse(success=True, claim_id=claim_id, operation="deleted")


@router.get(
    "/knowledge/entities",
    summary="List knowledge entities",
    description="List knowledge entities with optional filtering.",
)
async def mcp_knowledge_entities_list(
    q: str | None = Query(default=None, max_length=512),
    entity_type: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Database = Depends(get_library_database),
) -> MCPEntitiesListResponse:
    """MCP tool endpoint: List knowledge entities."""
    entities = db.all(KnowledgeEntity)
    total = len(entities)

    # Apply filters
    if q:
        entities = [e for e in entities if q.lower() in e.canonical_name.lower()]
    if entity_type:
        entities = [e for e in entities if e.entity_type.value == entity_type]

    # Apply pagination
    paginated = entities[offset:offset + limit]

    return MCPEntitiesListResponse(
        entities=[e.model_dump(mode="json") for e in paginated],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/knowledge/claims",
    summary="List knowledge claims",
    description="List knowledge claims with optional filtering.",
)
async def mcp_knowledge_claims_list(
    q: str | None = Query(default=None, max_length=512),
    claim_type: str | None = Query(default=None, max_length=64),
    entity_id: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Database = Depends(get_library_database),
) -> MCPClaimsListResponse:
    """MCP tool endpoint: List knowledge claims."""
    claims = db.all(KnowledgeClaim)
    total = len(claims)

    # Apply filters
    if q:
        claims = [c for c in claims if q.lower() in c.text.lower()]
    if claim_type:
        claims = [c for c in claims if c.claim_type.value == claim_type]
    if entity_id:
        claims = [c for c in claims if entity_id in c.entity_ids]

    # Apply pagination
    paginated = claims[offset:offset + limit]

    return MCPClaimsListResponse(
        claims=[c.model_dump(mode="json") for c in paginated],
        total=total,
        limit=limit,
        offset=offset,
    )
