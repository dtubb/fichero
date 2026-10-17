"""The project's confirmed names and places, as the word list a review is given
(`source.job.review-uses-the-projects-names-and-places`, #5725).

An entity a person verified in the knowledge graph is spelled one way throughout; its other names (variants, other
scripts, older spellings) are listed beside it so a reading of any of them is put to the confirmed one. Nothing here
names a language or script: the variants are whatever the entity carries.
"""
from __future__ import annotations

from typing import Any

from fichero_server.models.knowledge import (
    EntityCurationState,
    EntityType,
    KnowledgeEntity,
)

#: A name or a place, not an event or a concept.
_NAMED = frozenset({EntityType.person, EntityType.location, EntityType.organization})
#: shortcut: the most corroborated entities only, so a large graph cannot swamp the prompt; the rest are said to be left out.
LIMIT = 300


def known_names(db: Any) -> tuple[list[tuple[str, list[str]]], int]:
    """([(the confirmed spelling, its other names)], how many confirmed entities were left out by LIMIT)."""
    rows = [e for e in db.query(KnowledgeEntity)
            if e.curation_state == EntityCurationState.verified and e.entity_type in _NAMED and not e.merged_into_id]
    rows.sort(key=lambda e: (-e.corroboration_count, e.canonical_name))
    return [(e.canonical_name, [a for a in e.aliases if a != e.canonical_name]) for e in rows[:LIMIT]], max(0, len(rows) - LIMIT)


def instruction(db: Any) -> str:
    """The sentence and list to add to a review's prompt; '' when the project has confirmed none."""
    names, left_out = known_names(db)
    if not names:
        return ""
    lines = [f"- {name}" + (f" (also written: {'; '.join(variants)})" if variants else "") for name, variants in names]
    more = f"\n({left_out} more confirmed names are not listed.)" if left_out else ""
    return ("The project's confirmed names and places. When a line shows one of them, or a variant listed beside it, "
            "write it exactly as the confirmed spelling, so a name is spelled one way throughout; a name not on this "
            "list stays as the page shows it:\n" + "\n".join(lines) + more)
