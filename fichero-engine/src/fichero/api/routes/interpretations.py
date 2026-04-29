"""Interpretations API Routes (dev tier, backend-first 0.0.2 slice).

Dedicated router for /api/interpretations endpoints — separate from
/api/hermeneutics to provide focused interpretation workspace API.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.hermeneutics_models import (
    Interpretation,
    InterpretiveActType,
    InterpretiveFramework,
)
from fichero.knowledge_models import KnowledgeClaim
from fichero.models import Document

router = APIRouter(prefix="/interpretations", tags=["interpretations"])


# =============================================================================
# Response Models
# =============================================================================


class CitationLineage(BaseModel):
    """Citation lineage for an interpretation."""

    claim_id: str | None
    claim_text: str | None
    document_id: str | None
    document_name: str | None
    source_metadata: dict[str, Any] | None
    framework_id: str
    framework_name: str
    framework_type: str


class InterpretationListItem(BaseModel):
    """Interpretation list item with summary."""

    id: str
    framework_id: str
    framework_name: str
    claim_id: str | None
    document_id: str | None
    interpretation_text: str
    act: str
    confidence: float
    created_by: str
    created_at: datetime
    updated_at: datetime


class InterpretationDetailResponse(BaseModel):
    """Detailed interpretation with citation lineage."""

    id: str
    framework_id: str
    framework_name: str
    framework_type: str
    claim_id: str | None
    document_id: str | None
    passage_text: str | None
    interpretation_text: str
    act: str
    confidence: float
    key_insights: list[str]
    tensions: list[str]
    connections: list[str]
    citation_lineage: CitationLineage
    metadata: dict[str, Any]
    created_by: str
    created_at: datetime
    updated_at: datetime


class InterpretationDeletedResponse(BaseModel):
    deleted: bool
    id: str


class MethodTaxonomyResponse(BaseModel):
    """Method taxonomy for interpretations."""

    acts: list[dict[str, Any]]
    frameworks: list[dict[str, Any]]


class InterpretationCreateRequest(BaseModel):
    """Create a new interpretation."""

    framework_id: str
    claim_id: str | None = None
    document_id: str | None = None
    passage_text: str | None = None
    interpretation_text: str = Field(..., min_length=1)
    act: InterpretiveActType
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    key_insights: list[str] = Field(default_factory=list)
    tensions: list[str] = Field(default_factory=list)
    connections: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InterpretationUpdateRequest(BaseModel):
    """Update an interpretation."""

    interpretation_text: str | None = None
    act: InterpretiveActType | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    key_insights: list[str] | None = None
    tensions: list[str] | None = None
    connections: list[str] | None = None
    metadata: dict[str, Any] | None = None


# =============================================================================
# Helper Functions
# =============================================================================


def _build_citation_lineage(
    interpretation: Interpretation,
    db: Database,
) -> CitationLineage:
    """Build citation lineage for an interpretation."""
    claim_text = None
    source_metadata = None
    document_name = None

    # Get claim text if linked
    if interpretation.claim_id:
        claim = db.get(KnowledgeClaim, interpretation.claim_id)
        if claim:
            claim_text = claim.text[:500]  # Truncated for response
            if claim.source_metadata:
                source_metadata = (
                    claim.source_metadata.model_dump()
                    if hasattr(claim.source_metadata, "model_dump")
                    else dict(claim.source_metadata)
                )

    # Get document name if linked
    if interpretation.document_id:
        doc = db.get(Document, interpretation.document_id)
        if doc:
            document_name = doc.name

    # Get framework info
    framework_name = "Unknown"
    framework_type = "unknown"
    framework = db.get(InterpretiveFramework, interpretation.framework_id)
    if framework:
        framework_name = framework.name
        framework_type = framework.framework_type.value

    return CitationLineage(
        claim_id=interpretation.claim_id,
        claim_text=claim_text,
        document_id=interpretation.document_id,
        document_name=document_name,
        source_metadata=source_metadata,
        framework_id=interpretation.framework_id,
        framework_name=framework_name,
        framework_type=framework_type,
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("", response_model=list[InterpretationListItem])
async def list_interpretations(
    framework_id: str | None = Query(default=None),
    claim_id: str | None = Query(default=None),
    document_id: str | None = Query(default=None),
    act: InterpretiveActType | None = Query(default=None),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Database = Depends(get_library_database),
) -> list[InterpretationListItem]:
    """List interpretations with optional filtering.

    Returns interpretations sorted by creation date (newest first).
    """
    # Build query filters
    query_kwargs: dict[str, Any] = {}
    if framework_id:
        query_kwargs["framework_id"] = framework_id
    if claim_id:
        query_kwargs["claim_id"] = claim_id
    if document_id:
        query_kwargs["document_id"] = document_id
    if act:
        query_kwargs["act"] = act

    interpretations = db.query(Interpretation, **query_kwargs)

    # Filter by confidence
    if min_confidence > 0:
        interpretations = [i for i in interpretations if i.confidence >= min_confidence]

    # Sort by created_at descending
    interpretations.sort(key=lambda i: i.created_at, reverse=True)

    # Apply pagination
    interpretations = interpretations[offset:offset + limit]

    # Build response with framework names
    results: list[InterpretationListItem] = []
    for interp in interpretations:
        framework_name = "Unknown"
        framework = db.get(InterpretiveFramework, interp.framework_id)
        if framework:
            framework_name = framework.name

        results.append(
            InterpretationListItem(
                id=interp.id,
                framework_id=interp.framework_id,
                framework_name=framework_name,
                claim_id=interp.claim_id,
                document_id=interp.document_id,
                interpretation_text=interp.interpretation_text[:200],
                act=interp.act.value,
                confidence=interp.confidence,
                created_by=interp.created_by,
                created_at=interp.created_at,
                updated_at=interp.updated_at,
            )
        )

    return results


@router.post("", response_model=InterpretationDetailResponse)
async def create_interpretation(
    request: InterpretationCreateRequest,
    db: Database = Depends(get_library_database),
) -> InterpretationDetailResponse:
    """Create a new interpretation.

    Requires at least one of: claim_id, document_id, or passage_text.
    """
    # Validate framework exists
    framework = db.get(InterpretiveFramework, request.framework_id)
    if not framework:
        raise HTTPException(
            status_code=404,
            detail=f"Framework not found: {request.framework_id}",
        )

    # Validate claim exists if provided
    if request.claim_id:
        claim = db.get(KnowledgeClaim, request.claim_id)
        if not claim:
            raise HTTPException(
                status_code=404,
                detail=f"Claim not found: {request.claim_id}",
            )

    # Validate document exists if provided
    if request.document_id:
        doc = db.get(Document, request.document_id)
        if not doc:
            raise HTTPException(
                status_code=404,
                detail=f"Document not found: {request.document_id}",
            )

    # Require at least one target
    if not request.claim_id and not request.document_id and not request.passage_text:
        raise HTTPException(
            status_code=400,
            detail="At least one of claim_id, document_id, or passage_text is required",
        )

    now = datetime.now()
    interpretation = Interpretation(
        framework_id=request.framework_id,
        claim_id=request.claim_id,
        document_id=request.document_id,
        passage_text=request.passage_text,
        interpretation_text=request.interpretation_text.strip(),
        act=request.act,
        confidence=request.confidence,
        key_insights=list(request.key_insights),
        tensions=list(request.tensions),
        connections=list(request.connections),
        metadata=dict(request.metadata),
        created_by="human",
        created_at=now,
        updated_at=now,
    )

    db.save(interpretation)

    # Build response with citation lineage
    citation_lineage = _build_citation_lineage(interpretation, db)

    return InterpretationDetailResponse(
        id=interpretation.id,
        framework_id=interpretation.framework_id,
        framework_name=citation_lineage.framework_name,
        framework_type=citation_lineage.framework_type,
        claim_id=interpretation.claim_id,
        document_id=interpretation.document_id,
        passage_text=interpretation.passage_text,
        interpretation_text=interpretation.interpretation_text,
        act=interpretation.act.value,
        confidence=interpretation.confidence,
        key_insights=interpretation.key_insights,
        tensions=interpretation.tensions,
        connections=interpretation.connections,
        citation_lineage=citation_lineage,
        metadata=interpretation.metadata,
        created_by=interpretation.created_by,
        created_at=interpretation.created_at,
        updated_at=interpretation.updated_at,
    )


@router.get("/{interpretation_id}", response_model=InterpretationDetailResponse)
async def get_interpretation(
    interpretation_id: str,
    db: Database = Depends(get_library_database),
) -> InterpretationDetailResponse:
    """Get interpretation detail with citation lineage."""
    interpretation = db.get(Interpretation, interpretation_id)
    if not interpretation:
        raise HTTPException(
            status_code=404,
            detail=f"Interpretation not found: {interpretation_id}",
        )

    citation_lineage = _build_citation_lineage(interpretation, db)

    return InterpretationDetailResponse(
        id=interpretation.id,
        framework_id=interpretation.framework_id,
        framework_name=citation_lineage.framework_name,
        framework_type=citation_lineage.framework_type,
        claim_id=interpretation.claim_id,
        document_id=interpretation.document_id,
        passage_text=interpretation.passage_text,
        interpretation_text=interpretation.interpretation_text,
        act=interpretation.act.value,
        confidence=interpretation.confidence,
        key_insights=interpretation.key_insights,
        tensions=interpretation.tensions,
        connections=interpretation.connections,
        citation_lineage=citation_lineage,
        metadata=interpretation.metadata,
        created_by=interpretation.created_by,
        created_at=interpretation.created_at,
        updated_at=interpretation.updated_at,
    )


@router.patch("/{interpretation_id}", response_model=InterpretationDetailResponse)
async def update_interpretation(
    interpretation_id: str,
    request: InterpretationUpdateRequest,
    db: Database = Depends(get_library_database),
) -> InterpretationDetailResponse:
    """Update an interpretation."""
    interpretation = db.get(Interpretation, interpretation_id)
    if not interpretation:
        raise HTTPException(
            status_code=404,
            detail=f"Interpretation not found: {interpretation_id}",
        )

    if request.interpretation_text is not None:
        interpretation.interpretation_text = request.interpretation_text.strip()
    if request.act is not None:
        interpretation.act = request.act
    if request.confidence is not None:
        interpretation.confidence = request.confidence
    if request.key_insights is not None:
        interpretation.key_insights = list(request.key_insights)
    if request.tensions is not None:
        interpretation.tensions = list(request.tensions)
    if request.connections is not None:
        interpretation.connections = list(request.connections)
    if request.metadata is not None:
        interpretation.metadata.update(request.metadata)

    interpretation.updated_at = datetime.now()
    db.save(interpretation)

    citation_lineage = _build_citation_lineage(interpretation, db)

    return InterpretationDetailResponse(
        id=interpretation.id,
        framework_id=interpretation.framework_id,
        framework_name=citation_lineage.framework_name,
        framework_type=citation_lineage.framework_type,
        claim_id=interpretation.claim_id,
        document_id=interpretation.document_id,
        passage_text=interpretation.passage_text,
        interpretation_text=interpretation.interpretation_text,
        act=interpretation.act.value,
        confidence=interpretation.confidence,
        key_insights=interpretation.key_insights,
        tensions=interpretation.tensions,
        connections=interpretation.connections,
        citation_lineage=citation_lineage,
        metadata=interpretation.metadata,
        created_by=interpretation.created_by,
        created_at=interpretation.created_at,
        updated_at=interpretation.updated_at,
    )


@router.delete("/{interpretation_id}")
async def delete_interpretation(
    interpretation_id: str,
    db: Database = Depends(get_library_database),
) -> InterpretationDeletedResponse:
    """Delete an interpretation."""
    interpretation = db.get(Interpretation, interpretation_id)
    if not interpretation:
        raise HTTPException(
            status_code=404,
            detail=f"Interpretation not found: {interpretation_id}",
        )

    db.delete(interpretation)

    return InterpretationDeletedResponse(deleted=True, id=interpretation_id)


@router.get("/taxonomy/methods", response_model=MethodTaxonomyResponse)
async def get_method_taxonomy() -> MethodTaxonomyResponse:
    """Get method taxonomy for interpretations (taggable in API).

    Returns available interpretive acts and framework types.
    """
    acts = [
        {"value": act.value, "label": act.name.replace("_", " ").title()}
        for act in InterpretiveActType
    ]

    # Framework types from hermeneutics_models
    from fichero.hermeneutics_models import FrameworkType

    frameworks = [
        {"value": ft.value, "label": ft.name.replace("_", " ").title()}
        for ft in FrameworkType
    ]

    return MethodTaxonomyResponse(acts=acts, frameworks=frameworks)
