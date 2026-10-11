"""Knowledge resting on trashed pages is out of view, not deleted (`safety.trash.dependants-go-with-their-source`).

Worked out when reading, from the documents' own trash mark: nothing is stored, so trashing is
instant, Put Back brings every statement and entity back exactly, and only Empty Trash removes
them (through `_cascade_delete_kg_rows`).

* A **statement** is out of view when it names at least one source and every source is in the
  Trash. One that rests on a live source too stays.
* An **entity** is out of view when it rests on sources (its own pages, or statements that
  mention it) and none of them is live, unless a person verified it.

The one seam for knowledge reads: the claims list, the entities list, the graph's
neighbourhood and the knowledge search call it.
"""

from __future__ import annotations

from typing import Any, Iterable

from fichero_server.models import Document


def trashed_document_ids(db: Any) -> set[str]:
    rows = db.execute_fetchall(
        f"SELECT id FROM {db._sql_table_name(Document)} WHERE deleted_at IS NOT NULL"
    )
    return {row[0] for row in rows or []}


def claim_sources(claim: Any) -> set[str]:
    sources = set(getattr(claim, "source_ids", None) or [])
    if getattr(claim, "source_document_id", None):
        sources.add(claim.source_document_id)
    return sources


def claim_is_hidden(claim: Any, trashed: set[str]) -> bool:
    sources = claim_sources(claim)
    return bool(sources) and sources <= trashed


def visible_claims(db: Any, claims: Iterable[Any], trashed: set[str] | None = None) -> list[Any]:
    claims = list(claims)
    trashed = trashed_document_ids(db) if trashed is None else trashed
    if not trashed:
        return claims
    return [claim for claim in claims if not claim_is_hidden(claim, trashed)]


def hidden_entity_ids(
    db: Any,
    entities: Iterable[Any],
    trashed: set[str] | None = None,
    claims: Iterable[Any] | None = None,
) -> set[str]:
    from fichero_server.models.knowledge import EntityCurationState, KnowledgeClaim

    trashed = trashed_document_ids(db) if trashed is None else trashed
    if not trashed:
        return set()
    entities = list(entities)
    if not entities:
        return set()
    claims = db.query(KnowledgeClaim) if claims is None else claims
    live_mentioned: set[str] = set()
    trash_mentioned: set[str] = set()
    for claim in claims:
        target = trash_mentioned if claim_is_hidden(claim, trashed) else live_mentioned
        target.update(claim.entity_ids or [])
    hidden = set()
    for entity in entities:
        if entity.curation_state == EntityCurationState.verified or entity.id in live_mentioned:
            continue
        pages = set(entity.source_document_ids or [])
        if pages - trashed:
            continue
        if pages or entity.id in trash_mentioned:
            hidden.add(entity.id)
    return hidden


def visible_entities(db: Any, entities: Iterable[Any], trashed: set[str] | None = None) -> list[Any]:
    entities = list(entities)
    hidden = hidden_entity_ids(db, entities, trashed)
    return [entity for entity in entities if entity.id not in hidden] if hidden else entities


def claims_resting_on(db: Any, doc_ids: set[str]) -> list[Any]:
    """The statements Empty Trash removes with ``doc_ids``: the same rule as the purge's cascade
    (`_cascade_delete_kg_rows`), so the preview's count is what is then removed."""
    from fichero_server.models.knowledge import KnowledgeClaim

    if not doc_ids:
        return []
    return [claim for claim in db.query(KnowledgeClaim) if claim_sources(claim) & doc_ids]
