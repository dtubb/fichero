"""Knowledge graph analysis routes — contradiction evidence and evidence chains."""

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
from fichero.models import Document

router = APIRouter()


class ContradictionEvidenceResponse(BaseModel):
    """Response for contradiction evidence between two claims."""

    claim_id: str
    contradicting_claim_id: str
    relation_type: str
    evidence: str | None
    link_quality: float
    source_documents: list[dict[str, Any]]
    claim_text: str
    contradicting_text: str


class ContradictingClaimItem(BaseModel):
    """A claim that contradicts the target claim."""

    claim_id: str
    text: str
    epistemic_status: str | None
    confidence: float
    source_document_id: str | None
    source_metadata: dict[str, Any] | None
    link_quality: float
    evidence: str | None


class EvidenceChainItem(BaseModel):
    """Single item in an evidence chain."""

    step_type: str  # "claim", "source", "link"
    claim_id: str | None = None
    document_id: str | None = None
    text: str | None = None
    relation_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceChainResponse(BaseModel):
    """Response for evidence chain traversal."""

    claim_id: str
    chain: list[EvidenceChainItem]
    sources: list[dict[str, Any]]
    related_claims: list[str]


@router.get(
    "/claims/{claim_id}/contradictions",
    response_model=list[ContradictionEvidenceResponse],
    summary="Get contradiction evidence",
    description="Returns all contradicting claims with detailed evidence for analysis.",
)
async def get_contradiction_evidence(
    claim_id: str,
    db: Database = Depends(get_library_database),
) -> list[ContradictionEvidenceResponse]:
    """Get contradiction evidence for a claim."""
    claim = db.get(KnowledgeClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    links = db.query(KnowledgeClaimLink, claim_id=claim_id)
    reverse_links = db.query(KnowledgeClaimLink, related_claim_id=claim_id)

    contradictions: list[ContradictionEvidenceResponse] = []

    for link in links:
        if link.relation_type == ClaimRelationType.contradicts:
            other = db.get(KnowledgeClaim, link.related_claim_id)
            if other:
                source_docs = []
                for sid in other.source_ids or [other.source_document_id]:
                    if sid:
                        doc = db.get(Document, sid)
                        if doc:
                            source_docs.append({
                                "id": doc.id,
                                "name": doc.name,
                                "metadata": doc.metadata or {},
                            })

                contradictions.append(
                    ContradictionEvidenceResponse(
                        claim_id=claim_id,
                        contradicting_claim_id=other.id,
                        relation_type="outgoing",
                        evidence=link.evidence,
                        link_quality=link.link_quality or 0.5,
                        source_documents=source_docs,
                        claim_text=claim.text[:200],
                        contradicting_text=other.text[:200],
                    )
                )

    for link in reverse_links:
        if link.relation_type == ClaimRelationType.contradicts:
            other = db.get(KnowledgeClaim, link.claim_id)
            if other:
                source_docs = []
                for sid in other.source_ids or [other.source_document_id]:
                    if sid:
                        doc = db.get(Document, sid)
                        if doc:
                            source_docs.append({
                                "id": doc.id,
                                "name": doc.name,
                                "metadata": doc.metadata or {},
                            })

                contradictions.append(
                    ContradictionEvidenceResponse(
                        claim_id=claim_id,
                        contradicting_claim_id=other.id,
                        relation_type="incoming",
                        evidence=link.evidence,
                        link_quality=link.link_quality or 0.5,
                        source_documents=source_docs,
                        claim_text=claim.text[:200],
                        contradicting_text=other.text[:200],
                    )
                )

    return contradictions


@router.get(
    "/claims/related/{claim_id}/contradicting",
    response_model=list[ContradictingClaimItem],
    summary="Get contradicting claims",
    description="Returns claims that directly contradict the specified claim.",
)
async def get_contradicting_claims(
    claim_id: str,
    min_link_quality: float = Query(default=0.0, ge=0.0, le=1.0),
    db: Database = Depends(get_library_database),
) -> list[ContradictingClaimItem]:
    """Get claims that contradict the specified claim."""
    claim = db.get(KnowledgeClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    links = db.query(KnowledgeClaimLink, claim_id=claim_id)
    reverse_links = db.query(KnowledgeClaimLink, related_claim_id=claim_id)

    contradicting: list[ContradictingClaimItem] = []

    for link in links:
        if link.relation_type == ClaimRelationType.contradicts:
            if (link.link_quality or 0) >= min_link_quality:
                other = db.get(KnowledgeClaim, link.related_claim_id)
                if other:
                    source_meta = None
                    if other.source_metadata:
                        source_meta = (
                            other.source_metadata.model_dump()
                            if hasattr(other.source_metadata, "model_dump")
                            else dict(other.source_metadata)
                        )
                    contradicting.append(
                        ContradictingClaimItem(
                            claim_id=other.id,
                            text=other.text[:500],
                            epistemic_status=other.epistemic_status.value
                            if other.epistemic_status
                            else None,
                            confidence=other.confidence,
                            source_document_id=other.source_document_id,
                            source_metadata=source_meta,
                            link_quality=link.link_quality or 0.5,
                            evidence=link.evidence,
                        )
                    )

    for link in reverse_links:
        if link.relation_type == ClaimRelationType.contradicts:
            if (link.link_quality or 0) >= min_link_quality:
                other = db.get(KnowledgeClaim, link.claim_id)
                if other:
                    source_meta = None
                    if other.source_metadata:
                        source_meta = (
                            other.source_metadata.model_dump()
                            if hasattr(other.source_metadata, "model_dump")
                            else dict(other.source_metadata)
                        )
                    contradicting.append(
                        ContradictingClaimItem(
                            claim_id=other.id,
                            text=other.text[:500],
                            epistemic_status=other.epistemic_status.value
                            if other.epistemic_status
                            else None,
                            confidence=other.confidence,
                            source_document_id=other.source_document_id,
                            source_metadata=source_meta,
                            link_quality=link.link_quality or 0.5,
                            evidence=link.evidence,
                        )
                    )

    contradicting.sort(key=lambda x: x.link_quality, reverse=True)
    return contradicting


@router.get(
    "/claims/{claim_id}/evidence-chain",
    response_model=EvidenceChainResponse,
    summary="Get evidence chain",
    description="Traverse the evidence chain from claim to sources to related claims.",
)
async def get_evidence_chain(
    claim_id: str,
    max_depth: int = Query(default=2, ge=1, le=5),
    db: Database = Depends(get_library_database),
) -> EvidenceChainResponse:
    """Get evidence chain for a claim."""
    claim = db.get(KnowledgeClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    chain: list[EvidenceChainItem] = []
    sources: list[dict[str, Any]] = []
    related_claim_ids: set[str] = set()

    chain.append(
        EvidenceChainItem(
            step_type="claim",
            claim_id=claim.id,
            text=claim.text[:200],
            metadata={
                "confidence": claim.confidence,
                "epistemic_status": claim.epistemic_status.value
                if claim.epistemic_status
                else None,
            },
        )
    )

    source_ids = claim.source_ids or [claim.source_document_id]
    for sid in source_ids:
        if not sid:
            continue
        doc = db.get(Document, sid)
        if doc:
            sources.append({
                "id": doc.id,
                "name": doc.name,
                "path": str(doc.path) if doc.path else None,
                "metadata": doc.metadata or {},
            })
            chain.append(
                EvidenceChainItem(
                    step_type="source",
                    document_id=doc.id,
                    text=f"Source: {doc.name}",
                    metadata=doc.metadata or {},
                )
            )

    if max_depth > 1:
        links = db.query(KnowledgeClaimLink, claim_id=claim_id)
        for link in links:
            other = db.get(KnowledgeClaim, link.related_claim_id)
            if other:
                related_claim_ids.add(other.id)
                chain.append(
                    EvidenceChainItem(
                        step_type="link",
                        claim_id=other.id,
                        text=other.text[:150],
                        relation_type=link.relation_type.value
                        if link.relation_type
                        else None,
                        metadata={
                            "link_quality": link.link_quality,
                            "evidence": link.evidence,
                        },
                    )
                )

        reverse_links = db.query(KnowledgeClaimLink, related_claim_id=claim_id)
        for link in reverse_links:
            other = db.get(KnowledgeClaim, link.claim_id)
            if other:
                related_claim_ids.add(other.id)
                chain.append(
                    EvidenceChainItem(
                        step_type="link",
                        claim_id=other.id,
                        text=other.text[:150],
                        relation_type=f"reverse:{link.relation_type.value if link.relation_type else None}",
                        metadata={
                            "link_quality": link.link_quality,
                            "evidence": link.evidence,
                        },
                    )
                )

    return EvidenceChainResponse(
        claim_id=claim_id,
        chain=chain,
        sources=sources,
        related_claims=list(related_claim_ids),
    )
