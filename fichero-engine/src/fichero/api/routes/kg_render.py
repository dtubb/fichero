"""Knowledge-graph rendering routes."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.api.auth import action_context
from fichero.actions.registry import ActionContext, registry
from fichero.db import Database
from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity
# NOTE: fichero.llm is imported inside the one handler that uses it (#3950).
# It pulls langchain_core (~600 modules) onto the engine startup path.
from fichero.kg.paragraph import (
    ParagraphRenderRequest,
    ParagraphRenderResponse,
    render_paragraph_claims,
)

logger = logging.getLogger(__name__)

# Passthrough wrappers, NOT deferred imports at the call sites (#3950).
#
# These names are part of this module's TEST SURFACE — tests patch
# `fichero.api.routes.kg_render.<name>`. Two things must both hold:
#   1. the name exists as a module attribute, or mock.patch raises
#      AttributeError ("module has no attribute ...");
#   2. the call site resolves it as a module GLOBAL, so the patch takes effect.
# A function-local import at the call site satisfies NEITHER: it removes the
# attribute AND binds a local that shadows any patch — letting a test pass
# while silently exercising the real implementation. A module-level __getattr__
# (PEP 562) fixes (1) but not (2), because LOAD_GLOBAL inside this module never
# consults it. The wrapper satisfies both and still keeps fichero.llm
# (langchain_core) off the engine startup path.


def chat(*args, **kwargs):
    """Passthrough to fichero.llm.chat; imports it on first call (#3950)."""
    from fichero.llm import chat as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


router = APIRouter(prefix="/kg/render", tags=["knowledge-graph"])

# Second router: LLM-driven entity operations under /kg/entities
bio_router = APIRouter(prefix="/kg/entities", tags=["knowledge-graph"])


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


# =============================================================================
# POST /api/kg/entities/{entity_id}/bio — LLM biography generation (#1361)
# =============================================================================


class EntityBioResponse(BaseModel):
    entity_id: str
    biography: str


def _build_bio_prompt(entity: KnowledgeEntity, claims: list[KnowledgeClaim]) -> str:
    """Build the LLM prompt for biography generation."""
    lines: list[str] = [
        f"Write a concise biography paragraph (3–5 sentences) for the entity "
        f'"{entity.canonical_name}"',
    ]
    if entity.entity_type:
        lines.append(f"Entity type: {entity.entity_type.value}")
    if entity.aliases:
        lines.append(f"Also known as: {', '.join(entity.aliases)}")

    if claims:
        lines.append("\nKnown facts (SVO claims from source documents):")
        for c in claims[:40]:
            lines.append(f"  - {c.text}")
    else:
        lines.append("\nNo specific claims are available in the knowledge graph yet.")

    lines.append(
        "\nWrite in third-person prose. Be factual and concise. "
        "Do not invent facts not supported by the claims above."
    )
    return "\n".join(lines)


@bio_router.post(
    "/{entity_id}/bio",
    response_model=EntityBioResponse,
    summary="Generate LLM biography for a knowledge entity",
    description=(
        "Runs an LLM over the entity's SVO claims and writes the resulting "
        "prose back as entity.description. Re-generation is always allowed."
    ),
)
async def generate_entity_bio(
    entity_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> EntityBioResponse:
    """Generate a prose biography from SVO claims and persist as entity.description."""
    entity = db.get(KnowledgeEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    from fichero.api.routes.entities import _claims_referencing_entity_ids

    entity_claims = _claims_referencing_entity_ids(db, [entity_id])
    entity_claims.sort(key=lambda c: c.created_at)

    prompt = _build_bio_prompt(entity, entity_claims)

    from fichero.app_db import get_app_db  # noqa: PLC0415

    defaults = get_app_db().get_ai_defaults()
    # LLMConfig only — `chat` resolves to the module-level passthrough above,
    # which tests patch. A local import of it here would shadow that patch.
    from fichero.llm import LLMConfig  # noqa: PLC0415

    llm_config = LLMConfig(
        provider=defaults.get("default_text_provider") or "apple",
        model=defaults.get("default_text_model") or "apple-intelligence",
    )

    try:
        biography = await chat(prompt, llm_config, permissive_guardrails=True)
    except Exception as exc:
        logger.error("Biography LLM call failed for entity %s: %s", entity_id, exc)
        raise HTTPException(status_code=500, detail=f"LLM generation failed: {exc}") from exc

    if not isinstance(biography, str):
        biography = str(biography)

    metadata = dict(entity.metadata or {})
    ai_owned = bool(metadata.get("biography_provenance"))
    metadata["biography_provenance"] = {
        "provider": llm_config.provider,
        "model": llm_config.model,
        "generated_at": datetime.now().isoformat(),
        "claim_ids": [claim.id for claim in entity_claims],
    }
    description = biography if entity.description is None or ai_owned else entity.description
    if description != biography:
        metadata["ai_biography"] = biography
    registry.invoke(
        db,
        "entity.update",
        {
            "entity_id": entity.id,
            "canonical_name": entity.canonical_name,
            "entity_type": entity.entity_type,
            "aliases": entity.aliases,
            "description": description,
            "language": entity.language,
            "metadata": metadata,
            "source_document_ids": entity.source_document_ids,
        },
        ctx,
    )

    return EntityBioResponse(entity_id=entity_id, biography=biography)
