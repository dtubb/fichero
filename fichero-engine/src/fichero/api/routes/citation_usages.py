"""Citation usage exploration API (dev tier, #1277)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import DocumentCitation, KnowledgeClaim

router = APIRouter(prefix="/citation-usages")


class CitationUsageItem(BaseModel):
    citation: DocumentCitation
    claim: KnowledgeClaim | None = None
    reference_id: str | None = None
    stance: str | None = None
    metadata: dict[str, Any] = {}


class CitationUsageListResponse(BaseModel):
    items: list[CitationUsageItem]
    count: int


@router.get("", response_model=CitationUsageListResponse)
async def list_citation_usages(
    source_document_id: str | None = Query(default=None),
    target_document_id: str | None = Query(default=None),
    reference_id: str | None = Query(default=None),
    stance: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> CitationUsageListResponse:
    """List body-pass citation usages extracted by ``citation_usage_extract``."""
    rows = [
        citation
        for citation in db.query(DocumentCitation)
        if citation.detector == "llm-usage"
    ]
    if source_document_id is not None:
        rows = [c for c in rows if c.source_document_id == source_document_id]
    if target_document_id is not None:
        rows = [c for c in rows if c.target_document_id == target_document_id]

    items: list[CitationUsageItem] = []
    for citation in rows:
        metadata = citation.metadata if isinstance(citation.metadata, dict) else {}
        if reference_id is not None and metadata.get("matched_reference_id") != reference_id:
            continue
        if stance is not None and metadata.get("stance") != stance:
            continue
        claim_id = metadata.get("claim_id")
        claim = db.get(KnowledgeClaim, claim_id) if isinstance(claim_id, str) else None
        items.append(
            CitationUsageItem(
                citation=citation,
                claim=claim,
                reference_id=metadata.get("matched_reference_id"),
                stance=metadata.get("stance"),
                metadata=metadata,
            )
        )

    items.sort(key=lambda item: item.citation.created_at, reverse=True)
    return CitationUsageListResponse(items=items, count=len(items))
