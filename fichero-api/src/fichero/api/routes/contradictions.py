"""Contradiction Triage API Routes

Evidence API for managing claim contradictions:
- Side-by-side evidence display
- Evidence chain traversal (claim → sources → claims)
- Contradiction relationship management
- Visualization data preparation
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
from fichero.knowledge_models import (
    ClaimRelationType,
    KnowledgeClaim,
    KnowledgeClaimLink,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/claims", tags=["contradiction-triage"])


# =============================================================================
# Enums and Types
# =============================================================================


class ContradictionSeverity(str, Enum):
    """Severity level of a contradiction."""

    MINOR = "minor"  # Minor discrepancy in details
    MODERATE = "moderate"  # Significant disagreement
    SEVERE = "severe"  # Fundamental conflict
    CRITICAL = "critical"  # Core thesis contradiction


class EvidenceType(str, Enum):
    """Type of evidence in contradiction analysis."""

    PRIMARY_SOURCE = "primary_source"
    SECONDARY_SOURCE = "secondary_source"
    EXPERT_TESTIMONY = "expert_testimony"
    STATISTICAL = "statistical"
    LOGICAL_INFERENCE = "logical_inference"


class ResolutionStatus(str, Enum):
    """Status of contradiction resolution."""

    UNRESOLVED = "unresolved"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    REFUTED = "refuted"
    SUPERSEDED = "superseded"


# =============================================================================
# Request/Response Models
# =============================================================================


class EvidenceItem(BaseModel):
    """Single piece of evidence for or against a claim."""

    evidence_type: EvidenceType
    source_id: str | None = None
    claim_id: str | None = None
    description: str
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    citation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContradictionEvidence(BaseModel):
    """Evidence bundle for a contradiction relationship."""

    relation_id: str
    source_claim_id: str
    target_claim_id: str
    severity: ContradictionSeverity
    evidence_items: list[EvidenceItem]
    explanation: str | None = None
    detected_at: str
    resolved_at: str | None = None
    resolution_status: ResolutionStatus
    resolution_notes: str | None = None


class SideBySideComparison(BaseModel):
    """Side-by-side view of contradicting claims."""

    claim_a: dict[str, Any]
    claim_b: dict[str, Any]
    points_of_agreement: list[str]
    points_of_conflict: list[str]
    semantic_similarity: float
    confidence_a: float
    confidence_b: float
    source_quality_a: float
    source_quality_b: float


class EvidenceChainNode(BaseModel):
    """Node in an evidence chain."""

    node_type: str  # "claim", "source", "entity"
    node_id: str
    node_label: str
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceChain(BaseModel):
    """Chain of evidence from claim back to sources."""

    start_claim_id: str
    end_claim_id: str
    chain_type: str  # "supporting", "contradicting", "neutral"
    nodes: list[EvidenceChainNode]
    edges: list[dict[str, Any]]
    total_length: int
    strength_score: float


class ContradictingClaimSummary(BaseModel):
    """Summary of a claim that contradicts another."""

    claim_id: str
    claim_text: str
    confidence: float
    epistemic_status: str
    source_count: int
    relation_quality: float
    severity: ContradictionSeverity
    detected_at: str
    evidence_summary: str | None = None


class ContradictionListResponse(BaseModel):
    """Response for listing contradictions."""

    claim_id: str
    contradictions: list[ContradictingClaimSummary]
    total: int
    unresolved_count: int
    by_severity: dict[str, int]


class ContradictionVisualizationData(BaseModel):
    """Data formatted for contradiction visualization."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    claim_id: str
    focus_claim: dict[str, Any]
    contradictions: list[dict[str, Any]]
    supports: list[dict[str, Any]]
    severity_distribution: dict[str, int]


class UpdateContradictionRequest(BaseModel):
    """Request to update contradiction metadata."""

    severity: ContradictionSeverity | None = None
    resolution_status: ResolutionStatus | None = None
    resolution_notes: str | None = None
    evidence_items: list[EvidenceItem] | None = None
    explanation: str | None = None


class CreateContradictionRequest(BaseModel):
    """Request to create a contradiction relationship."""

    target_claim_id: str
    severity: ContradictionSeverity = ContradictionSeverity.MODERATE
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    explanation: str | None = None


# =============================================================================
# Helper Functions
# =============================================================================


def _get_claim_summary(claim: KnowledgeClaim) -> dict[str, Any]:
    """Get summary dict for a claim."""
    return {
        "id": claim.id,
        "text": claim.text[:200] + "..." if len(claim.text) > 200 else claim.text,
        "confidence": claim.confidence,
        "epistemic_status": claim.epistemic_status.value if claim.epistemic_status else "unknown",
        "source_document_id": claim.source_document_id,
        "created_at": claim.created_at.isoformat() if hasattr(claim.created_at, "isoformat") else str(claim.created_at),
    }


def _claim_to_side_by_side(claim: KnowledgeClaim) -> dict[str, Any]:
    """Convert claim to side-by-side format."""
    return {
        "id": claim.id,
        "full_text": claim.text,
        "summary": claim.text[:300] + "..." if len(claim.text) > 300 else claim.text,
        "confidence": claim.confidence,
        "epistemic_status": claim.epistemic_status.value if claim.epistemic_status else "unknown",
        "source_type": claim.source_type.value if claim.source_type else "unknown",
        "source_document_id": claim.source_document_id,
        "key_entities": claim.entity_ids[:5] if claim.entity_ids else [],
    }


def _calculate_semantic_similarity(text_a: str, text_b: str) -> float:
    """Calculate simple semantic similarity between two texts."""
    # Simple word overlap similarity (could be enhanced with embeddings)
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())

    if not words_a or not words_b:
        return 0.0

    intersection = words_a.intersection(words_b)
    union = words_a.union(words_b)
    return len(intersection) / len(union) if union else 0.0


def _find_points_of_conflict(claim_a: KnowledgeClaim, claim_b: KnowledgeClaim) -> list[str]:
    """Identify points of conflict between two claims."""
    conflicts = []

    # Check confidence disagreement
    if abs(claim_a.confidence - claim_b.confidence) > 0.3:
        conflicts.append(f"Confidence disagreement: {claim_a.confidence:.2f} vs {claim_b.confidence:.2f}")

    # Check epistemic status conflict
    if claim_a.epistemic_status and claim_b.epistemic_status:
        if claim_a.epistemic_status != claim_b.epistemic_status:
            conflicts.append(f"Status conflict: {claim_a.epistemic_status.value} vs {claim_b.epistemic_status.value}")

    return conflicts


def _find_points_of_agreement(claim_a: KnowledgeClaim, claim_b: KnowledgeClaim) -> list[str]:
    """Identify points of agreement between two claims."""
    agreements = []

    # Shared entities
    if claim_a.entity_ids and claim_b.entity_ids:
        shared = set(claim_a.entity_ids).intersection(set(claim_b.entity_ids))
        if shared:
            agreements.append(f"Shared entities: {', '.join(list(shared)[:3])}")

    # Similar confidence
    if abs(claim_a.confidence - claim_b.confidence) < 0.2:
        agreements.append("Similar confidence levels")

    # Same source document
    if claim_a.source_document_id and claim_a.source_document_id == claim_b.source_document_id:
        agreements.append("Same source document")

    return agreements


# =============================================================================
# API Endpoints
# =============================================================================


@router.get(
    "/{claim_id}/contradictions",
    response_model=ContradictionListResponse,
    summary="Get claim contradictions",
    description="Get all claims that contradict the specified claim with evidence summaries.",
)
async def get_claim_contradictions(
    claim_id: str,
    severity: ContradictionSeverity | None = Query(None, description="Filter by severity"),
    resolution_status: ResolutionStatus | None = Query(None, description="Filter by resolution status"),
    limit: int = Query(50, ge=1, le=500),
    db: Database = Depends(get_library_database),
) -> ContradictionListResponse:
    """Get all contradictions for a claim."""
    # Verify claim exists
    claim = db.get(KnowledgeClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    # Get all claim links where this claim is the source and relation is contradicts
    all_links = db.all(KnowledgeClaimLink)
    contradiction_links = [
        link for link in all_links
        if link.claim_id == claim_id and link.relation_type == ClaimRelationType.contradicts
    ]

    # Also get links where this claim is the target
    contradiction_links.extend([
        link for link in all_links
        if link.related_claim_id == claim_id and link.relation_type == ClaimRelationType.contradicts
    ])

    # Deduplicate by relation pair
    seen_pairs = set()
    unique_links = []
    for link in contradiction_links:
        pair = tuple(sorted([link.claim_id, link.related_claim_id]))
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            unique_links.append(link)

    # Build response items
    contradictions = []
    by_severity: dict[str, int] = {}
    unresolved_count = 0

    for link in unique_links:
        # Get the other claim
        other_claim_id = link.related_claim_id if link.claim_id == claim_id else link.claim_id
        other_claim = db.get(KnowledgeClaim, other_claim_id)
        if not other_claim:
            continue

        # Parse metadata
        metadata = link.metadata or {}
        link_severity = metadata.get("severity", "moderate")
        link_status = metadata.get("resolution_status", "unresolved")

        # Apply filters
        if severity and link_severity != severity.value:
            continue
        if resolution_status and link_status != resolution_status.value:
            continue

        # Track counts
        by_severity[link_severity] = by_severity.get(link_severity, 0) + 1
        if link_status == "unresolved":
            unresolved_count += 1

        contradictions.append(
            ContradictingClaimSummary(
                claim_id=other_claim_id,
                claim_text=other_claim.text[:200] + "..." if len(other_claim.text) > 200 else other_claim.text,
                confidence=other_claim.confidence,
                epistemic_status=other_claim.epistemic_status.value if other_claim.epistemic_status else "unknown",
                source_count=len(other_claim.source_ids) if hasattr(other_claim, "source_ids") and other_claim.source_ids else 1,
                relation_quality=link.link_quality,
                severity=ContradictionSeverity(link_severity),
                detected_at=link.created_at.isoformat() if hasattr(link.created_at, "isoformat") else str(link.created_at),
                evidence_summary=link.evidence,
            )
        )

    # Sort by severity (critical first) then by relation quality
    severity_order = {"critical": 0, "severe": 1, "moderate": 2, "minor": 3}
    contradictions.sort(key=lambda c: (severity_order.get(c.severity.value, 4), -c.relation_quality))

    return ContradictionListResponse(
        claim_id=claim_id,
        contradictions=contradictions[:limit],
        total=len(contradictions),
        unresolved_count=unresolved_count,
        by_severity=by_severity,
    )


@router.get(
    "/related/{claim_id}/contradicting",
    response_model=list[ContradictingClaimSummary],
    summary="Get contradicting claims",
    description="Get claims that have a contradicts relationship with the specified claim.",
)
async def get_contradicting_claims(
    claim_id: str,
    min_quality: float = Query(0.0, ge=0.0, le=1.0, description="Minimum relation quality"),
    db: Database = Depends(get_library_database),
) -> list[ContradictingClaimSummary]:
    """Get claims that directly contradict the specified claim."""
    # Verify claim exists
    claim = db.get(KnowledgeClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    # Get contradiction links
    all_links = db.all(KnowledgeClaimLink)
    contradicting_links = [
        link for link in all_links
        if (link.claim_id == claim_id or link.related_claim_id == claim_id)
        and link.relation_type == ClaimRelationType.contradicts
        and link.link_quality >= min_quality
    ]

    results = []
    for link in contradicting_links:
        other_id = link.related_claim_id if link.claim_id == claim_id else link.claim_id
        other_claim = db.get(KnowledgeClaim, other_id)
        if not other_claim:
            continue

        metadata = link.metadata or {}
        results.append(
            ContradictingClaimSummary(
                claim_id=other_id,
                claim_text=other_claim.text[:200] + "..." if len(other_claim.text) > 200 else other_claim.text,
                confidence=other_claim.confidence,
                epistemic_status=other_claim.epistemic_status.value if other_claim.epistemic_status else "unknown",
                source_count=1,
                relation_quality=link.link_quality,
                severity=ContradictionSeverity(metadata.get("severity", "moderate")),
                detected_at=link.created_at.isoformat() if hasattr(link.created_at, "isoformat") else str(link.created_at),
                evidence_summary=link.evidence,
            )
        )

    return results


@router.get(
    "/{claim_id_a}/compare/{claim_id_b}",
    response_model=SideBySideComparison,
    summary="Compare two claims",
    description="Side-by-side comparison of two potentially contradicting claims.",
)
async def compare_claims(
    claim_id_a: str,
    claim_id_b: str,
    db: Database = Depends(get_library_database),
) -> SideBySideComparison:
    """Side-by-side comparison of two claims."""
    claim_a = db.get(KnowledgeClaim, claim_id_a)
    claim_b = db.get(KnowledgeClaim, claim_id_b)

    if not claim_a:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id_a}")
    if not claim_b:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id_b}")

    # Calculate analysis
    semantic_similarity = _calculate_semantic_similarity(claim_a.text, claim_b.text)
    points_of_conflict = _find_points_of_conflict(claim_a, claim_b)
    points_of_agreement = _find_points_of_agreement(claim_a, claim_b)

    return SideBySideComparison(
        claim_a=_claim_to_side_by_side(claim_a),
        claim_b=_claim_to_side_by_side(claim_b),
        points_of_agreement=points_of_agreement,
        points_of_conflict=points_of_conflict,
        semantic_similarity=semantic_similarity,
        confidence_a=claim_a.confidence,
        confidence_b=claim_b.confidence,
        source_quality_a=claim_a.confidence * 0.8,  # Placeholder calculation
        source_quality_b=claim_b.confidence * 0.8,
    )


@router.get(
    "/{claim_id}/evidence-chain",
    response_model=list[EvidenceChain],
    summary="Get evidence chains",
    description="Trace evidence chains from claim back to supporting/contradicting sources.",
)
async def get_evidence_chains(
    claim_id: str,
    chain_type: str = Query("all", description="Type of chain: supporting, contradicting, all"),
    max_depth: int = Query(3, ge=1, le=5, description="Maximum chain depth"),
    db: Database = Depends(get_library_database),
) -> list[EvidenceChain]:
    """Get evidence chains for a claim."""
    claim = db.get(KnowledgeClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    # Get all claim links
    all_links = db.all(KnowledgeClaimLink)

    chains = []

    # Build chains based on relation type filter
    for link in all_links:
        if link.claim_id != claim_id and link.related_claim_id != claim_id:
            continue

        # Determine chain type
        current_chain_type = "neutral"
        if link.relation_type == ClaimRelationType.supports:
            current_chain_type = "supporting"
        elif link.relation_type == ClaimRelationType.contradicts:
            current_chain_type = "contradicting"

        # Apply filter
        if chain_type != "all" and current_chain_type != chain_type:
            continue

        other_id = link.related_claim_id if link.claim_id == claim_id else link.claim_id
        other_claim = db.get(KnowledgeClaim, other_id)
        if not other_claim:
            continue

        # Build chain nodes
        nodes = [
            EvidenceChainNode(
                node_type="claim",
                node_id=claim_id,
                node_label=claim.text[:50] + "..." if len(claim.text) > 50 else claim.text,
                confidence=claim.confidence,
            ),
            EvidenceChainNode(
                node_type="claim",
                node_id=other_id,
                node_label=other_claim.text[:50] + "..." if len(other_claim.text) > 50 else other_claim.text,
                confidence=other_claim.confidence,
                metadata={"relation_type": link.relation_type.value},
            ),
        ]

        edges = [
            {
                "source": claim_id,
                "target": other_id,
                "type": link.relation_type.value,
                "quality": link.link_quality,
            }
        ]

        chains.append(
            EvidenceChain(
                start_claim_id=claim_id,
                end_claim_id=other_id,
                chain_type=current_chain_type,
                nodes=nodes,
                edges=edges,
                total_length=len(nodes),
                strength_score=link.link_quality,
            )
        )

    # Sort by strength score descending
    chains.sort(key=lambda c: c.strength_score, reverse=True)

    return chains[:20]  # Limit to top 20 chains


@router.get(
    "/{claim_id}/visualization",
    response_model=ContradictionVisualizationData,
    summary="Get visualization data",
    description="Get claim and contradiction data formatted for visualization.",
)
async def get_contradiction_visualization(
    claim_id: str,
    include_supports: bool = Query(True, description="Include supporting claims"),
    max_nodes: int = Query(50, ge=10, le=200),
    db: Database = Depends(get_library_database),
) -> ContradictionVisualizationData:
    """Get visualization-ready contradiction data."""
    claim = db.get(KnowledgeClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    # Build nodes list
    nodes = []
    edges = []
    contradictions = []
    supports = []
    severity_distribution: dict[str, int] = {}

    # Add focus claim as center node
    nodes.append({
        "id": claim_id,
        "type": "focus",
        "label": claim.text[:50] + "..." if len(claim.text) > 50 else claim.text,
        "confidence": claim.confidence,
        "epistemic_status": claim.epistemic_status.value if claim.epistemic_status else "unknown",
    })

    # Get related claims
    all_links = db.all(KnowledgeClaimLink)
    related_count = 0

    for link in all_links:
        if related_count >= max_nodes - 1:
            break

        if link.claim_id != claim_id and link.related_claim_id != claim_id:
            continue

        other_id = link.related_claim_id if link.claim_id == claim_id else link.claim_id
        other_claim = db.get(KnowledgeClaim, other_id)
        if not other_claim:
            continue

        # Determine node type
        node_type = "related"
        if link.relation_type == ClaimRelationType.contradicts:
            node_type = "contradiction"
            metadata = link.metadata or {}
            severity = metadata.get("severity", "moderate")
            severity_distribution[severity] = severity_distribution.get(severity, 0) + 1
            contradictions.append({
                "id": other_id,
                "text": other_claim.text[:100] + "..." if len(other_claim.text) > 100 else other_claim.text,
                "severity": severity,
                "quality": link.link_quality,
            })
        elif link.relation_type == ClaimRelationType.supports and include_supports:
            node_type = "support"
            supports.append({
                "id": other_id,
                "text": other_claim.text[:100] + "..." if len(other_claim.text) > 100 else other_claim.text,
                "quality": link.link_quality,
            })

        nodes.append({
            "id": other_id,
            "type": node_type,
            "label": other_claim.text[:50] + "..." if len(other_claim.text) > 50 else other_claim.text,
            "confidence": other_claim.confidence,
            "relation_type": link.relation_type.value,
            "relation_quality": link.link_quality,
        })

        edges.append({
            "source": claim_id,
            "target": other_id,
            "type": link.relation_type.value,
            "quality": link.link_quality,
        })

        related_count += 1

    return ContradictionVisualizationData(
        nodes=nodes,
        edges=edges,
        claim_id=claim_id,
        focus_claim=_get_claim_summary(claim),
        contradictions=contradictions,
        supports=supports,
        severity_distribution=severity_distribution,
    )


@router.post(
    "/{claim_id}/contradictions",
    response_model=ContradictionEvidence,
    summary="Create contradiction",
    description="Create a new contradiction relationship between claims.",
)
async def create_contradiction(
    claim_id: str,
    request: CreateContradictionRequest,
    db: Database = Depends(get_library_database),
) -> ContradictionEvidence:
    """Create a contradiction relationship."""
    # Verify both claims exist
    source_claim = db.get(KnowledgeClaim, claim_id)
    if not source_claim:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    target_claim = db.get(KnowledgeClaim, request.target_claim_id)
    if not target_claim:
        raise HTTPException(status_code=404, detail=f"Target claim not found: {request.target_claim_id}")

    # Create the link
    now = datetime.now()
    link = KnowledgeClaimLink(
        claim_id=claim_id,
        related_claim_id=request.target_claim_id,
        relation_type=ClaimRelationType.contradicts,
        link_quality=0.5,
        evidence=request.explanation,
        metadata={
            "severity": request.severity.value,
            "resolution_status": "unresolved",
            "evidence_items": [e.model_dump() for e in request.evidence_items],
        },
        created_at=now,
    )

    db.save(link)
    logger.info(f"Created contradiction between {claim_id} and {request.target_claim_id}")

    return ContradictionEvidence(
        relation_id=link.id,
        source_claim_id=claim_id,
        target_claim_id=request.target_claim_id,
        severity=request.severity,
        evidence_items=request.evidence_items,
        explanation=request.explanation,
        detected_at=now.isoformat(),
        resolved_at=None,
        resolution_status=ResolutionStatus.UNRESOLVED,
        resolution_notes=None,
    )


@router.patch(
    "/contradictions/{relation_id}",
    response_model=ContradictionEvidence,
    summary="Update contradiction",
    description="Update contradiction metadata (severity, resolution status, etc.).",
)
async def update_contradiction(
    relation_id: str,
    request: UpdateContradictionRequest,
    db: Database = Depends(get_library_database),
) -> ContradictionEvidence:
    """Update contradiction metadata."""
    # Find the link
    all_links = db.all(KnowledgeClaimLink)
    link = next((lnk for lnk in all_links if lnk.id == relation_id), None)

    if not link:
        raise HTTPException(status_code=404, detail=f"Contradiction relation not found: {relation_id}")

    metadata = link.metadata or {}

    # Update fields
    if request.severity:
        metadata["severity"] = request.severity.value

    if request.resolution_status:
        metadata["resolution_status"] = request.resolution_status.value
        if request.resolution_status in [ResolutionStatus.RESOLVED, ResolutionStatus.REFUTED]:
            metadata["resolved_at"] = datetime.now().isoformat()

    if request.resolution_notes:
        metadata["resolution_notes"] = request.resolution_notes

    if request.evidence_items:
        metadata["evidence_items"] = [e.model_dump() for e in request.evidence_items]

    if request.explanation:
        link.evidence = request.explanation

    link.metadata = metadata
    db.save(link)

    return ContradictionEvidence(
        relation_id=link.id,
        source_claim_id=link.claim_id,
        target_claim_id=link.related_claim_id,
        severity=ContradictionSeverity(metadata.get("severity", "moderate")),
        evidence_items=[EvidenceItem(**e) for e in metadata.get("evidence_items", [])],
        explanation=link.evidence,
        detected_at=link.created_at.isoformat() if hasattr(link.created_at, "isoformat") else str(link.created_at),
        resolved_at=metadata.get("resolved_at"),
        resolution_status=ResolutionStatus(metadata.get("resolution_status", "unresolved")),
        resolution_notes=metadata.get("resolution_notes"),
    )
