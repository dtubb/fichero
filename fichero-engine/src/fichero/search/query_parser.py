"""
Query parser for /api/search.

Produces a structured plan from a user-typed query string so the route
can apply different retrieval strategies for different parts. Supports:

- Quoted phrases: `"el escribano"` → exact substring of the whole phrase
- Field scopes:    `people:Asprilla`  → match only the people artifact table
                   `places:Quibdó`    → only places
                   `organizations:`, `dates:`, `events:`, `keywords:`
- NOT exclusions:  `gold -mining`     → matches "gold" but excludes docs
                                        containing "mining"
- Plain terms:     anything else      → standard substring + semantic

Returns a SearchPlan dataclass that the route hands to db.search and the
entity-bridge helper. Scope-only queries (e.g. `people:Asprilla` with no
free-text term) skip semantic + fulltext entirely and resolve through
the entity bridge.

Kept deliberately small — no boolean precedence, no nested groups. The
syntax is "what users type instinctively" not "boolean algebra".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# All entity types the catalogue/extract_all workflow emits. Adding a
# new type to extract_all means adding it here AND to _entity_match_results
# in routes/search.py.
ENTITY_TYPES = frozenset(
    {"people", "places", "organizations", "dates", "events", "keywords"}
)


@dataclass
class SearchPlan:
    """Structured query plan derived from raw user input.

    Attributes:
        free_text: Concatenated unquoted, unscoped terms — fed to
            semantic + fulltext retrievers.
        phrases: Quoted exact-substring phrases (each must match).
        excludes: NOT-prefixed terms — docs containing any are dropped.
        scopes: Mapping entity_type -> list of values to match in that
            artifact table. e.g. {'people': ['Asprilla'], 'places': ['Quibdó']}.
        original: The raw query string for logging / round-trip tags.
    """

    free_text: str = ""
    phrases: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    scopes: dict[str, list[str]] = field(default_factory=dict)
    original: str = ""

    @property
    def has_freetext_intent(self) -> bool:
        """Whether semantic + fulltext should run.

        True when the user typed any plain term or quoted phrase. False
        for pure scope queries like `people:Asprilla` (those resolve via
        the entity bridge alone — no point hammering the embeddings).
        """
        return bool(self.free_text.strip()) or bool(self.phrases)

    @property
    def has_entity_scope(self) -> bool:
        """Whether the entity bridge should run with explicit scope."""
        return bool(self.scopes)


_QUOTED_RE = re.compile(r'"([^"]+)"')
_SCOPE_RE = re.compile(rf'(?P<field>{"|".join(ENTITY_TYPES)}):(?P<value>\S+)')
_EXCLUDE_RE = re.compile(r"(?:^|\s)-(\S+)")


def parse_query(raw: str) -> SearchPlan:
    """Parse a user-typed query string into a SearchPlan.

    Order of operations:
        1. Pull out quoted phrases first (so quotes inside scope values
           survive — e.g. `people:"José Antonio"` becomes a scoped phrase).
        2. Pull out field scopes.
        3. Pull out NOT-prefixed exclusions.
        4. Whatever remains is free-text.

    Robust to extra whitespace and missing close-quotes (we treat an
    un-closed `"foo` as plain text).
    """
    if not raw or not raw.strip():
        return SearchPlan(original=raw)

    plan = SearchPlan(original=raw)
    remaining = raw

    # 1. Scoped phrases like `people:"José Antonio"` first — they have a
    # field followed by a quoted value.
    scoped_phrase_re = re.compile(
        rf'(?P<field>{"|".join(ENTITY_TYPES)}):"(?P<value>[^"]+)"'
    )
    for match in scoped_phrase_re.finditer(remaining):
        plan.scopes.setdefault(match.group("field"), []).append(match.group("value"))
    remaining = scoped_phrase_re.sub(" ", remaining)

    # 2. Plain quoted phrases.
    for match in _QUOTED_RE.finditer(remaining):
        plan.phrases.append(match.group(1))
    remaining = _QUOTED_RE.sub(" ", remaining)

    # 3. Field scopes with single-word values.
    for match in _SCOPE_RE.finditer(remaining):
        plan.scopes.setdefault(match.group("field"), []).append(match.group("value"))
    remaining = _SCOPE_RE.sub(" ", remaining)

    # 4. Exclusions.
    for match in _EXCLUDE_RE.finditer(remaining):
        plan.excludes.append(match.group(1))
    remaining = _EXCLUDE_RE.sub(" ", remaining)

    # 5. Free text — everything left, collapse whitespace.
    plan.free_text = " ".join(remaining.split())
    return plan
