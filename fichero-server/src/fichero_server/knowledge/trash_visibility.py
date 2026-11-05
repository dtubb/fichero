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



def trashed_document_ids(db: Any) -> set[str]:
    from fichero_server.db.document_tree import trashed_ids

    return trashed_ids(db)


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


def _rests_only_on_trash(anchors: Iterable[str | None], trashed: set[str]) -> bool:
    """True when something names at least one document and every one it names is in the Trash."""
    named = {anchor for anchor in anchors if anchor}
    return bool(named) and named <= trashed


def visible_annotations(db: Any, rows: Iterable[Any], trashed: set[str] | None = None) -> list[Any]:
    """Annotations anchored only to trashed documents are out of view with them (`safety.trash.dependants-go-with-their-source`)."""
    rows = list(rows)
    trashed = trashed_document_ids(db) if trashed is None else trashed
    if not trashed:
        return rows
    return [r for r in rows if not _rests_only_on_trash((r.document_id, r.page_id, r.folder_id), trashed)]


def visible_notes(db: Any, rows: Iterable[Any], trashed: set[str] | None = None) -> list[Any]:
    """Notes whose every linked document is trashed are out of view with them; a note that also links a live
    document, or links none, stays."""
    rows = list(rows)
    trashed = trashed_document_ids(db) if trashed is None else trashed
    if not trashed:
        return rows
    return [
        r for r in rows
        if not _rests_only_on_trash((*(r.linked_document_ids or []), r.page_id, r.folder_id), trashed)
    ]


def visible_document_ids(db: Any, document_ids: Iterable[str], trashed: set[str] | None = None) -> list[str]:
    """A scope of documents without the trashed ones, in the order given."""
    document_ids = list(document_ids)
    trashed = trashed_document_ids(db) if trashed is None else trashed
    return [i for i in document_ids if i not in trashed] if trashed else document_ids


def hidden_note_ids(db: Any, notes: Iterable[Any], trashed: set[str] | None = None) -> set[str]:
    """The ids of the notes `visible_notes` leaves out: every document they link is in the Trash."""
    notes = list(notes)
    shown = {n.id for n in visible_notes(db, notes, trashed)}
    return {n.id for n in notes if n.id not in shown}


def sources_in_trash(db: Any, claims: Iterable[Any], trashed: set[str] | None = None) -> dict[str, list[str]]:
    """For each listed statement with a source in the Trash (and, being listed, one still live): claim id -> those sources."""
    trashed = trashed_document_ids(db) if trashed is None else trashed
    if not trashed:
        return {}
    marked = {}
    for claim in claims:
        gone = sorted(claim_sources(claim) & trashed)
        if gone:
            marked[claim.id] = gone
    return marked
