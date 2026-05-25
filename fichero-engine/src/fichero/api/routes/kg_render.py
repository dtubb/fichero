"""Knowledge-graph rendering routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import KnowledgeClaim
from fichero.kg.paragraph import (
    ParagraphRenderRequest,
    ParagraphRenderResponse,
    render_paragraph_claims,
)

router = APIRouter(prefix="/kg/render", tags=["knowledge-graph"])


@router.post(
    "/paragraph",
    response_model=ParagraphRenderResponse,
    summary="Render a deterministic KG paragraph",
    description=(
        "Compose KnowledgeClaim rows into deterministic prose with "
        "bidirectional citation metadata. Consecutive claims sharing the "
        "same subject and verb are folded into one sentence, while the "
        "response preserves marker offsets and source provenance for each "
        "citation."
    ),
)
async def render_paragraph(
    request: ParagraphRenderRequest,
    db: Database = Depends(get_library_database),
) -> ParagraphRenderResponse:
    """Render the supplied claims as a paragraph with citation metadata."""

    claims: list[KnowledgeClaim] = []
    for claim_id in request.claim_ids:
        claim = db.get(KnowledgeClaim, claim_id)
        if claim is None:
            raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")
        claims.append(claim)

    return render_paragraph_claims(claims, style=request.style)
