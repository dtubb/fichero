"""Claim contradiction + evidence-chain analysis.

Ported from the deprecated ``/api/knowledge-graph/claims/{id}/contradictions``
and ``/evidence-chain`` endpoints. Lives under ``/api/kg/claim-analysis``.
"""

from __future__ import annotations

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
from fichero.models import ContradictionEvidence, ContradictionListResponse, Document

router = APIRouter(prefix="/kg/claim-analysis")


class EvidenceChainItem(BaseModel):
    step_type: str  # "claim", "source", "link"
    claim_id: str | None = None
    document_id: str | None = None
    text: str | None = None
    relation_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceChain(BaseModel):
    claim_id: str
    chain: list[EvidenceChainItem]
    sources: list[dict[str, Any]]
    related_claims: list[str]


def _source_docs(db: Database, claim: KnowledgeClaim) -> list[dict[str, Any]]:
    ids = claim.source_ids or [claim.source_document_id]
    out: list[dict[str, Any]] = []
    for sid in ids:
        if not sid:
            continue
        doc = db.get(Document, sid)
        if doc:
            out.append({"id": doc.id, "name": doc.name, "metadata": doc.metadata or {}})
    return out


@router.get("/{claim_id}/contradictions", response_model=ContradictionListResponse)
async def contradictions(
    claim_id: str,
    min_link_quality: float = Query(default=0.0, ge=0.0, le=1.0),
    db: Database = Depends(get_library_database),
) -> ContradictionListResponse:
    """Return all contradicting claims with evidence."""
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    out: list[ContradictionEvidence] = []
    for link in db.query(KnowledgeClaimLink, claim_id=claim_id):
        if link.relation_type != ClaimRelationType.contradicts:
            continue
        if (link.link_quality or 0) < min_link_quality:
            continue
        other = db.get(KnowledgeClaim, link.related_claim_id)
        if not other:
            continue
        out.append(ContradictionEvidence(
            claim_id=claim_id,
            contradicting_claim_id=other.id,
            relation_type="outgoing",
            evidence=link.evidence,
            link_quality=link.link_quality or 0.5,
            source_documents=_source_docs(db, other),
            claim_text=claim.text[:200],
            contradicting_text=other.text[:200],
        ))
    for link in db.query(KnowledgeClaimLink, related_claim_id=claim_id):
        if link.relation_type != ClaimRelationType.contradicts:
            continue
        if (link.link_quality or 0) < min_link_quality:
            continue
        other = db.get(KnowledgeClaim, link.claim_id)
        if not other:
            continue
        out.append(ContradictionEvidence(
            claim_id=claim_id,
            contradicting_claim_id=other.id,
            relation_type="incoming",
            evidence=link.evidence,
            link_quality=link.link_quality or 0.5,
            source_documents=_source_docs(db, other),
            claim_text=claim.text[:200],
            contradicting_text=other.text[:200],
        ))
    out.sort(key=lambda x: x.link_quality, reverse=True)
    return ContradictionListResponse(items=out, count=len(out))


@router.get("/{claim_id}/evidence-chain", response_model=EvidenceChain)
async def evidence_chain(
    claim_id: str,
    max_depth: int = Query(default=2, ge=1, le=5),
    db: Database = Depends(get_library_database),
) -> EvidenceChain:
    """Traverse the evidence chain from claim → sources → linked claims."""
    claim = db.get(KnowledgeClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    chain: list[EvidenceChainItem] = [EvidenceChainItem(
        step_type="claim",
        claim_id=claim.id,
        text=claim.text[:200],
        metadata={
            "confidence": claim.confidence,
            "epistemic_status": claim.epistemic_status.value if claim.epistemic_status else None,
        },
    )]
    sources: list[dict[str, Any]] = []
    for sid in (claim.source_ids or [claim.source_document_id]):
        if not sid:
            continue
        doc = db.get(Document, sid)
        if not doc:
            continue
        sources.append({
            "id": doc.id, "name": doc.name,
            "path": str(doc.path) if doc.path else None,
            "metadata": doc.metadata or {},
        })
        chain.append(EvidenceChainItem(
            step_type="source", document_id=doc.id,
            text=f"Source: {doc.name}", metadata=doc.metadata or {},
        ))

    related: set[str] = set()
    if max_depth > 1:
        for link in db.query(KnowledgeClaimLink, claim_id=claim_id):
            other = db.get(KnowledgeClaim, link.related_claim_id)
            if not other:
                continue
            related.add(other.id)
            chain.append(EvidenceChainItem(
                step_type="link", claim_id=other.id, text=other.text[:150],
                relation_type=link.relation_type.value if link.relation_type else None,
                metadata={"link_quality": link.link_quality, "evidence": link.evidence},
            ))
        for link in db.query(KnowledgeClaimLink, related_claim_id=claim_id):
            other = db.get(KnowledgeClaim, link.claim_id)
            if not other:
                continue
            related.add(other.id)
            chain.append(EvidenceChainItem(
                step_type="link", claim_id=other.id, text=other.text[:150],
                relation_type=f"reverse:{link.relation_type.value if link.relation_type else None}",
                metadata={"link_quality": link.link_quality, "evidence": link.evidence},
            ))

    return EvidenceChain(
        claim_id=claim_id, chain=chain, sources=sources,
        related_claims=list(related),
    )
