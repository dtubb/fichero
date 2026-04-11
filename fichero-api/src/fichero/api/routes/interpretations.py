"""Interpretations Workspace API Routes

Workspace backend for managing interpretations with:
- Method taxonomy tagging
- Citation lineage tracking
- Claim linking and provenance
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import KnowledgeClaim
from fichero.hermeneutics_models import (
    Interpretation,
    InterpretiveFramework,
    InterpretiveActType,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/interpretations", tags=["interpretations-workspace"])


# =============================================================================
# Enums
# =============================================================================


class MethodCategory(str, Enum):
    """High-level method categories for taxonomy."""

    HISTORICAL = "historical"
    TEXTUAL = "textual"
    ANALYTICAL = "analytical"
    SYNTHETIC = "synthetic"
    CRITICAL = "critical"
    COMPARATIVE = "comparative"
    EMPIRICAL = "empirical"
    CONCEPTUAL = "conceptual"


class MethodTechnique(str, Enum):
    """Specific techniques within methods."""

    CLOSE_READING = "close_reading"
    DISCOURSE_ANALYSIS = "discourse_analysis"
    GENRE_ANALYSIS = "genre_analysis"
    NARRATIVE_ANALYSIS = "narrative_analysis"
    SOURCE_CRITICISM = "source_criticism"
    COMPARATIVE_ANALYSIS = "comparative_analysis"
    STATISTICAL = "statistical"
    THEMATIC_CODING = "thematic_coding"
    GROUNDED_THEORY = "grounded_theory"
    HERMENEUTIC_CIRCLE = "hermeneutic_circle"
    DIALECTICAL = "dialectical"


class CitationType(str, Enum):
    """Type of citation link."""

    PRIMARY = "primary"  # Direct source
    SECONDARY = "secondary"  # Scholarly interpretation
    SUPPORTING = "supporting"  # Evidence supports claim
    CONTRADICTING = "contradicting"  # Evidence contradicts claim
    CONTEXTUAL = "contextual"  # Provides background


# =============================================================================
# Request/Response Models
# =============================================================================


class MethodTag(BaseModel):
    """A method taxonomy tag."""

    category: MethodCategory
    technique: MethodTechnique
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    rationale: str | None = None


class CitationLineage(BaseModel):
    """Citation lineage entry for an interpretation."""

    claim_id: str  # The claim this cites
    citation_type: CitationType
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)
    excerpt: str | None = None  # Key excerpt supporting the citation
    notes: str | None = None


class InterpretationCreateRequest(BaseModel):
    """Request to create an interpretation."""

    framework_id: str
    claim_ids: list[str] = Field(default_factory=list, description="Claims being interpreted")
    document_id: str | None = None
    passage_text: str | None = None
    interpretation_text: str = Field(..., min_length=1)
    act: InterpretiveActType
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    key_insights: list[str] = Field(default_factory=list)
    tensions: list[str] = Field(default_factory=list)
    connections: list[str] = Field(default_factory=list)
    method_tags: list[MethodTag] = Field(default_factory=list)
    citation_lineage: list[CitationLineage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "human"


class InterpretationUpdateRequest(BaseModel):
    """Request to update an interpretation."""

    interpretation_text: str | None = None
    framework_id: str | None = None
    claim_ids: list[str] | None = None
    act: InterpretiveActType | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    key_insights: list[str] | None = None
    tensions: list[str] | None = None
    connections: list[str] | None = None
    method_tags: list[MethodTag] | None = None
    citation_lineage: list[CitationLineage] | None = None
    metadata: dict[str, Any] | None = None


class InterpretationDetailResponse(BaseModel):
    """Full interpretation with enriched details."""

    id: str
    framework_id: str
    framework_name: str
    claim_ids: list[str]
    claims_summary: list[dict[str, Any]]  # Enriched claim info
    document_id: str | None
    passage_text: str | None
    interpretation_text: str
    act: str
    confidence: float
    key_insights: list[str]
    tensions: list[str]
    connections: list[str]
    method_tags: list[MethodTag]
    citation_lineage: list[CitationLineage]
    source_provenance: list[dict[str, Any]]  # Traced back to documents
    created_by: str
    created_at: str
    updated_at: str


class InterpretationListItem(BaseModel):
    """Summary item for interpretation list."""

    id: str
    framework_name: str
    interpretation_preview: str  # First 200 chars
    act: str
    confidence: float
    num_claims: int
    method_categories: list[str]  # Unique categories
    created_at: str


class InterpretationListResponse(BaseModel):
    """Response for listing interpretations."""

    interpretations: list[InterpretationListItem]
    total: int
    limit: int
    offset: int


class MethodTaxonomyResponse(BaseModel):
    """Available method taxonomy."""

    categories: list[dict[str, str]]
    techniques: list[dict[str, str]]


# =============================================================================
# Helper Functions
# =============================================================================


def _get_framework_name(framework_id: str, db: Database) -> str:
    """Get framework name or return ID if not found."""
    framework = db.get(InterpretiveFramework, framework_id)
    return framework.name if framework else f"[Framework: {framework_id[:8]}...]"


def _get_claims_summary(claim_ids: list[str], db: Database) -> list[dict[str, Any]]:
    """Get enriched claim summaries."""
    summaries = []
    for claim_id in claim_ids:
        claim = db.get(KnowledgeClaim, claim_id)
        if claim:
            summaries.append({
                "id": claim_id,
                "text": claim.text[:200] + "..." if len(claim.text) > 200 else claim.text,
                "epistemic_status": claim.epistemic_status.value if claim.epistemic_status else None,
                "confidence": claim.confidence,
            })
        else:
            summaries.append({
                "id": claim_id,
                "text": "[Claim not found]",
                "epistemic_status": None,
                "confidence": 0.0,
            })
    return summaries


def _trace_provenance(claim_ids: list[str], db: Database) -> list[dict[str, Any]]:
    """Trace claims back to their source documents."""
    provenance = []
    seen_docs = set()

    for claim_id in claim_ids:
        claim = db.get(KnowledgeClaim, claim_id)
        if claim and claim.source_document_id:
            doc_id = claim.source_document_id
            if doc_id not in seen_docs:
                seen_docs.add(doc_id)
                provenance.append({
                    "document_id": doc_id,
                    "claim_id": claim_id,
                    "source_type": claim.source_type.value if claim.source_type else "unknown",
                })

    return provenance


def _to_iso(dt: datetime) -> str:
    """Convert datetime to ISO string."""
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


def _interpretation_to_detail(
    interpretation: Interpretation, db: Database
) -> InterpretationDetailResponse:
    """Convert Interpretation to detailed response."""
    # Get claim IDs from citation lineage if not in claim_ids
    claim_ids = list(getattr(interpretation, "claim_ids", []))
    if not claim_ids and interpretation.claim_id:
        claim_ids = [interpretation.claim_id]

    # Extract method tags from metadata if present
    method_tags = []
    method_data = interpretation.metadata.get("method_tags", [])
    if method_data:
        for tag in method_data:
            if isinstance(tag, dict):
                method_tags.append(MethodTag(**tag))

    # Extract citation lineage from metadata
    lineage = []
    lineage_data = interpretation.metadata.get("citation_lineage", [])
    if lineage_data:
        for cit in lineage_data:
            if isinstance(cit, dict):
                lineage.append(CitationLineage(**cit))

    return InterpretationDetailResponse(
        id=interpretation.id,
        framework_id=interpretation.framework_id,
        framework_name=_get_framework_name(interpretation.framework_id, db),
        claim_ids=claim_ids,
        claims_summary=_get_claims_summary(claim_ids, db),
        document_id=interpretation.document_id,
        passage_text=interpretation.passage_text,
        interpretation_text=interpretation.interpretation_text,
        act=interpretation.act.value if interpretation.act else "unknown",
        confidence=interpretation.confidence,
        key_insights=interpretation.key_insights,
        tensions=interpretation.tensions,
        connections=interpretation.connections,
        method_tags=method_tags,
        citation_lineage=lineage,
        source_provenance=_trace_provenance(claim_ids, db),
        created_by=interpretation.created_by,
        created_at=_to_iso(interpretation.created_at),
        updated_at=_to_iso(interpretation.updated_at),
    )


def _interpretation_to_list_item(
    interpretation: Interpretation, db: Database
) -> InterpretationListItem:
    """Convert Interpretation to list item."""
    text = interpretation.interpretation_text or ""
    preview = text[:200] + "..." if len(text) > 200 else text

    # Get unique method categories
    method_data = interpretation.metadata.get("method_tags", [])
    categories = list(set(m.get("category", "unknown") for m in method_data if isinstance(m, dict)))

    # Count linked claims
    claim_count = len(getattr(interpretation, "claim_ids", []))
    if claim_count == 0 and interpretation.claim_id:
        claim_count = 1

    return InterpretationListItem(
        id=interpretation.id,
        framework_name=_get_framework_name(interpretation.framework_id, db),
        interpretation_preview=preview,
        act=interpretation.act.value if interpretation.act else "unknown",
        confidence=interpretation.confidence,
        num_claims=claim_count,
        method_categories=categories,
        created_at=_to_iso(interpretation.created_at),
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.post(
    "",
    response_model=InterpretationDetailResponse,
    summary="Create interpretation",
    description="Create a new interpretation with method tags and citation lineage.",
)
async def create_interpretation(
    request: InterpretationCreateRequest,
    db: Database = Depends(get_library_database),
) -> InterpretationDetailResponse:
    """Create a new interpretation."""
    # Validate framework exists
    framework = db.get(InterpretiveFramework, request.framework_id)
    if not framework:
        raise HTTPException(
            status_code=404, detail=f"Framework not found: {request.framework_id}"
        )

    # Validate claims exist (must have at least one claim)
    if not request.claim_ids:
        raise HTTPException(status_code=400, detail="At least one claim_id is required")

    for claim_id in request.claim_ids:
        claim = db.get(KnowledgeClaim, claim_id)
        if not claim:
            raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    # Create interpretation
    now = datetime.now()

    # Build metadata with method tags and citation lineage
    metadata = dict(request.metadata)
    if request.method_tags:
        metadata["method_tags"] = [tag.model_dump() for tag in request.method_tags]
    if request.citation_lineage:
        metadata["citation_lineage"] = [cit.model_dump() for cit in request.citation_lineage]

    # Use first claim_id as primary claim for backward compatibility
    primary_claim_id = request.claim_ids[0] if request.claim_ids else None

    interpretation = Interpretation(
        framework_id=request.framework_id,
        claim_id=primary_claim_id,
        document_id=request.document_id,
        passage_text=request.passage_text,
        interpretation_text=request.interpretation_text.strip(),
        act=request.act,
        confidence=request.confidence,
        key_insights=request.key_insights,
        tensions=request.tensions,
        connections=request.connections,
        metadata=metadata,
        created_by=request.created_by,
        created_at=now,
        updated_at=now,
    )

    # Store claim_ids list in metadata for multi-claim support
    if request.claim_ids:
        interpretation.metadata["claim_ids"] = request.claim_ids

    db.save(interpretation)
    logger.info(f"Created interpretation {interpretation.id} for framework {request.framework_id}")

    return _interpretation_to_detail(interpretation, db)


@router.get(
    "",
    response_model=InterpretationListResponse,
    summary="List interpretations",
    description="List interpretations with filtering by framework, method, etc.",
)
async def list_interpretations(
    framework_id: str | None = Query(None, description="Filter by framework"),
    act: InterpretiveActType | None = Query(None, description="Filter by interpretive act"),
    method_category: MethodCategory | None = Query(None, description="Filter by method category"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_library_database),
) -> InterpretationListResponse:
    """List interpretations with optional filtering."""
    interpretations = db.all(Interpretation)

    # Apply filters
    filtered = []
    for interp in interpretations:
        # Framework filter
        if framework_id and interp.framework_id != framework_id:
            continue

        # Act filter
        if act and interp.act != act:
            continue

        # Confidence filter
        if interp.confidence < min_confidence:
            continue

        # Method category filter
        if method_category:
            method_data = interp.metadata.get("method_tags", [])
            has_category = any(
                m.get("category") == method_category.value
                for m in method_data
                if isinstance(m, dict)
            )
            if not has_category:
                continue

        filtered.append(interp)

    total = len(filtered)
    paginated = filtered[offset:offset + limit]

    return InterpretationListResponse(
        interpretations=[_interpretation_to_list_item(i, db) for i in paginated],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{interpretation_id}",
    response_model=InterpretationDetailResponse,
    summary="Get interpretation details",
    description="Get full interpretation with claims summary and citation lineage.",
)
async def get_interpretation(
    interpretation_id: str,
    db: Database = Depends(get_library_database),
) -> InterpretationDetailResponse:
    """Get interpretation by ID with enriched details."""
    interpretation = db.get(Interpretation, interpretation_id)
    if not interpretation:
        raise HTTPException(
            status_code=404, detail=f"Interpretation not found: {interpretation_id}"
        )

    return _interpretation_to_detail(interpretation, db)


@router.patch(
    "/{interpretation_id}",
    response_model=InterpretationDetailResponse,
    summary="Update interpretation",
    description="Update interpretation fields including method tags and citation lineage.",
)
async def update_interpretation(
    interpretation_id: str,
    request: InterpretationUpdateRequest,
    db: Database = Depends(get_library_database),
) -> InterpretationDetailResponse:
    """Update an interpretation."""
    interpretation = db.get(Interpretation, interpretation_id)
    if not interpretation:
        raise HTTPException(
            status_code=404, detail=f"Interpretation not found: {interpretation_id}"
        )

    # Update fields
    if request.interpretation_text is not None:
        interpretation.interpretation_text = request.interpretation_text.strip()
    if request.framework_id is not None:
        interpretation.framework_id = request.framework_id
    if request.act is not None:
        interpretation.act = request.act
    if request.confidence is not None:
        interpretation.confidence = request.confidence
    if request.key_insights is not None:
        interpretation.key_insights = request.key_insights
    if request.tensions is not None:
        interpretation.tensions = request.tensions
    if request.connections is not None:
        interpretation.connections = request.connections

    # Update claim_ids
    if request.claim_ids is not None:
        interpretation.metadata["claim_ids"] = request.claim_ids
        # Update primary claim_id
        if request.claim_ids:
            interpretation.claim_id = request.claim_ids[0]

    # Update method tags
    if request.method_tags is not None:
        interpretation.metadata["method_tags"] = [t.model_dump() for t in request.method_tags]

    # Update citation lineage
    if request.citation_lineage is not None:
        interpretation.metadata["citation_lineage"] = [c.model_dump() for c in request.citation_lineage]

    if request.metadata is not None:
        for key, value in request.metadata.items():
            interpretation.metadata[key] = value

    interpretation.updated_at = datetime.now()
    db.save(interpretation)

    return _interpretation_to_detail(interpretation, db)


@router.delete(
    "/{interpretation_id}",
    summary="Delete interpretation",
    description="Soft-delete an interpretation.",
)
async def delete_interpretation(
    interpretation_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    """Soft-delete an interpretation."""
    interpretation = db.get(Interpretation, interpretation_id)
    if not interpretation:
        raise HTTPException(
            status_code=404, detail=f"Interpretation not found: {interpretation_id}"
        )

    interpretation.is_active = False
    interpretation.updated_at = datetime.now()
    db.save(interpretation)

    return {
        "success": True,
        "interpretation_id": interpretation_id,
        "operation": "deleted",
    }


@router.get(
    "/{interpretation_id}/lineage",
    response_model=list[dict[str, Any]],
    summary="Get citation lineage",
    description="Get traced provenance back to source documents.",
)
async def get_interpretation_lineage(
    interpretation_id: str,
    db: Database = Depends(get_library_database),
) -> list[dict[str, Any]]:
    """Get citation lineage for an interpretation."""
    interpretation = db.get(Interpretation, interpretation_id)
    if not interpretation:
        raise HTTPException(
            status_code=404, detail=f"Interpretation not found: {interpretation_id}"
        )

    claim_ids = interpretation.metadata.get("claim_ids", [])
    if not claim_ids and interpretation.claim_id:
        claim_ids = [interpretation.claim_id]

    return _trace_provenance(claim_ids, db)


@router.post(
    "/{interpretation_id}/tags",
    response_model=InterpretationDetailResponse,
    summary="Add method tags",
    description="Add method taxonomy tags to an interpretation.",
)
async def add_method_tags(
    interpretation_id: str,
    tags: list[MethodTag],
    db: Database = Depends(get_library_database),
) -> InterpretationDetailResponse:
    """Add method tags to an interpretation."""
    interpretation = db.get(Interpretation, interpretation_id)
    if not interpretation:
        raise HTTPException(
            status_code=404, detail=f"Interpretation not found: {interpretation_id}"
        )

    existing = interpretation.metadata.get("method_tags", [])
    existing.extend([t.model_dump() for t in tags])
    interpretation.metadata["method_tags"] = existing
    interpretation.updated_at = datetime.now()
    db.save(interpretation)

    return _interpretation_to_detail(interpretation, db)


@router.get(
    "/taxonomy/methods",
    response_model=MethodTaxonomyResponse,
    summary="Get method taxonomy",
    description="Get available method categories and techniques.",
)
async def get_method_taxonomy() -> MethodTaxonomyResponse:
    """Get method taxonomy categories and techniques."""
    categories = [
        {"value": c.value, "label": c.value.replace("_", " ").title()}
        for c in MethodCategory
    ]
    techniques = [
        {"value": t.value, "label": t.value.replace("_", " ").title()}
        for t in MethodTechnique
    ]

    return MethodTaxonomyResponse(categories=categories, techniques=techniques)
