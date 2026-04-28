"""Entity writer helpers for catalogue extractors.

Centralizes the upsert + claim save pattern so each extractor in
`extractors.py` doesn't reimplement it. Bridges structured-extraction
outputs (people, places, organizations, events, concepts) into the
existing knowledge-graph layer (`KnowledgeEntity`, `KnowledgeClaim`).

See `docs/architecture/typed_entity_storage.md` §0 for the design and
`docs/superpowers/plans/2026-04-28-typed-entity-storage.md` for the
implementation plan (#728).
"""

from __future__ import annotations

import logging
from typing import Optional

from fichero.db import Database
from fichero.knowledge_models import (
    ClaimType,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)

logger = logging.getLogger(__name__)


def upsert_entity(
    db: Database,
    canonical_name: str,
    entity_type: EntityType,
    aliases: Optional[list[str]] = None,
    description: Optional[str] = None,
) -> str:
    """Look up entity by ``(canonical_name, entity_type)``; create if missing.

    Returns the entity ID. Idempotent — calling twice with the same args
    reuses the existing row, so re-running an extractor on the same document
    doesn't accumulate duplicate entities.
    """
    existing = db.query(
        KnowledgeEntity,
        canonical_name=canonical_name,
        entity_type=entity_type,
    )
    if existing:
        return existing[0].id

    entity = KnowledgeEntity(
        canonical_name=canonical_name,
        entity_type=entity_type,
        aliases=aliases or [],
        description=description,
    )
    db.save(entity)
    return entity.id


def save_claim(
    db: Database,
    text: str,
    source_document_id: str,
    entity_ids: Optional[list[str]] = None,
    source_excerpt: Optional[str] = None,
    claim_type: ClaimType = ClaimType.fact,
    confidence: float = 0.5,
    metadata: Optional[dict] = None,
) -> str:
    """Save a `KnowledgeClaim` row. Returns the claim ID.

    Claims are document-scoped textual assertions linked to entities via
    ``entity_ids``. Date-style claims (no canonical entity to dedup) pass
    an empty list for ``entity_ids``; the normalized date lives in
    ``metadata['date_normalized']``.
    """
    claim = KnowledgeClaim(
        text=text,
        source_document_id=source_document_id,
        entity_ids=entity_ids or [],
        source_excerpt=source_excerpt,
        claim_type=claim_type,
        confidence=confidence,
        metadata=metadata or {},
    )
    db.save(claim)
    return claim.id
