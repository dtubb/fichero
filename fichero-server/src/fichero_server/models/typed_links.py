"""Source-model slice 10 (#4931) — one typed link record, and one vocabulary.

Spec: ``build-notes-readings-cascade-orders.md``, "Slice 10 → One typed-link
record".

WHAT THIS IS FOR. Four records already hold "this thing relates to that thing":
``NoteLink`` (notes), ``SpatialConnection`` and ``CanvasItem`` of kind link (the
canvas), and ``PredictionLink`` (a value inside a prediction's metadata). Each
carries its own word list. **This slice makes the ONE record and puts SEGMENTS on
it; it does not move the other four** -- each convergence is its own later slice
with its own tests and owner.

THE VOCABULARY IS SEEDED FROM EVERY SET THAT ALREADY HOLDS THE IDEA, with the
overlap collapsed to one key each (ruled 2026-09-26). Not a second list beside
the existing ones: a record built to remove four vocabularies must not ship a
fifth that disagrees with the one two records already share. Two consequences
that are easy to get wrong and are therefore pinned by tests:

* the four words that exist in both take ``ClaimRelationType``'s spelling --
  where a plan and stored data disagree about a spelling, **the stored data
  wins**, because changing stored data means a migration and changing a plan
  means editing a line;
* ``derives_from``, never ``derived_from``. Two keys one letter apart are worse
  than two unrelated keys: a query for one silently misses the other and looks
  like an answer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now
from fichero_server.models.knowledge import ClaimRelationType, ProvenanceKind


def _new_id() -> str:
    return uuid.uuid4().hex


class LinkEndKind(str, Enum):
    """What a link's end IS. `segment` is the only one this slice writes; the
    others are listed because the record is the one record and a reader needs to
    know what it will eventually hold."""

    segment = "segment"
    note = "note"
    document = "document"
    claim = "claim"
    canvas_item = "canvas_item"


#: The words the KG already stores, reused rather than re-spelled. Read from the
#: enum at import so the two can never drift: adding a relation to
#: `ClaimRelationType` adds it here, which is the point of sharing one ontology.
KG_LINK_TYPES: tuple[str, ...] = tuple(value.value for value in ClaimRelationType)

#: The manuscript-facing relations the KG has no equivalent for. These are the
#: reason this vocabulary is larger than the KG's and not merely a copy: a gloss
#: is not a citation, and a catchword continuing onto the next page is neither.
#:
#: `inverse_label` matters because a link is reachable from both ends and the
#: sentence reads differently from each: A *glosses* B, B *is glossed by* A.
SOURCE_LINK_TYPES: tuple[tuple[str, str, str], ...] = (
    ("glosses", "Glosses", "Is glossed by"),
    ("comments_on", "Comments on", "Is commented on by"),
    ("answers", "Answers", "Is answered by"),
    ("quotes", "Quotes", "Is quoted by"),
    ("expands", "Expands", "Is expanded by"),
    ("reorders", "Reorders", "Is reordered by"),
    ("marks", "Marks", "Is marked by"),
    ("captions", "Captions", "Is captioned by"),
    ("labels", "Labels", "Is labelled by"),
    ("continues", "Continues", "Is continued by"),
    ("translates", "Translates", "Is translated by"),
    ("same_as", "Same as", "Same as"),
    ("names", "Names", "Is named by"),
    ("interprets", "Interprets", "Is interpreted by"),
)

#: The words the four existing records use that the KG does NOT have. `follows`,
#: `refines`, `supports` and `contradicts` are deliberately absent: they are in
#: `ClaimRelationType` already, and listing them here would be the duplication
#: this seeding exists to avoid.
#:
#: `next_logical` is `PredictionLink`'s word for what `follows` means, and `free`
#: is `NoteLink`'s "no particular relation" default -- both kept so no stored row
#: loses its word when those records converge.
LEGACY_LINK_TYPES: tuple[tuple[str, str, str], ...] = (
    ("next_logical", "Next", "Previous"),
    ("free", "Related", "Related"),
)

#: Words a reader may type or a legacy row may hold that mean a key already in
#: the vocabulary. **A DISPLAY ALIAS, not a key** (ruled 2026-09-26): `references`
#: became `cites` because nothing in the engine or the app ever treated the two
#: differently as link types -- and because `references` already means two other
#: things here, the `references` table and the `Reference` model, so keeping it as
#: a third would put three unrelated ideas behind one word.
#:
#: A historian may well distinguish a work referred to in passing from one
#: formally cited. If that distinction is wanted, it is a DISPLAY distinction over
#: this one relation -- a second label, not a second key -- and nothing here
#: forecloses it.
LINK_TYPE_ALIASES: dict[str, str] = {
    "references": "cites",
    "derived_from": "derives_from",
}


def builtin_link_types() -> tuple[tuple[str, str, str], ...]:
    """Every key this library ships, from every set that already holds the idea.

    ONE list, assembled once, with the overlap collapsed: a key present in the
    KG's vocabulary is not repeated by the source or legacy lists. The KG's own
    labels are derived from its keys rather than restated, because the KG is where
    that word's meaning already lives.
    """
    seen: set[str] = set()
    rows: list[tuple[str, str, str]] = []
    for key in KG_LINK_TYPES:
        if key in seen:
            continue
        seen.add(key)
        label = key.replace("_", " ").capitalize()
        rows.append((key, label, f"Is {key.replace('_', ' ')} of"))
    for key, label, inverse in SOURCE_LINK_TYPES + LEGACY_LINK_TYPES:
        if key in seen:
            continue
        seen.add(key)
        rows.append((key, label, inverse))
    return tuple(rows)


class LibraryLinkType(BaseModel):
    """One link type this library allows. Table ``librarylinktypes``.

    The same shape as ``LibraryReadingKind``: seeded idempotently on open,
    additive only, never deleted -- a link stored under a type later withdrawn
    must still read back.
    """

    model_config = {"from_attributes": True}

    id: str = Field(default_factory=_new_id)
    key: str
    label: str
    #: How the relation reads from the OTHER end. A link is reachable from both
    #: ends, and "A glosses B" read backwards is "B is glossed by A", not
    #: "B glosses A".
    inverse_label: str
    builtin: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class TypedLink(BaseModel):
    """One typed relation between two things. Table ``typedlinks``."""

    id: str = Field(default_factory=_new_id)
    from_kind: str = LinkEndKind.segment.value
    from_id: str
    to_kind: str = LinkEndKind.segment.value
    to_id: str
    #: A key from this library's `librarylinktypes`.
    link_type: str
    #: False for a symmetric relation (`same_as`), where "from" and "to" carry no
    #: meaning and a reader must not be shown a direction that says nothing.
    directed: bool = True
    #: Engine-set from `ctx` (#4868/#4869).
    provenance_kind: ProvenanceKind
    created_by: str | None = None
    certainty: float | None = None
    #: A SHORT reason, never source text: this lands in the tamper-evident audit
    #: chain, which nothing can purge.
    note: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    #: Soft delete, so a withdrawn link is still auditable.
    deleted_at: datetime | None = None


# ---------------------------------------------------------------------------
# Typed refusals
# ---------------------------------------------------------------------------


class UnknownLinkType(ValueError):
    """Raised when a write names a link type this library does not have.

    Resolves an alias in the message when the caller sent one, because
    "`references` is not a link type" is unhelpful when the answer is "it is
    called `cites` here".
    """

    def __init__(self, link_type: str, allowed: list[str]) -> None:
        self.link_type = link_type
        self.allowed = allowed
        alias = LINK_TYPE_ALIASES.get(link_type)
        hint = f"; {link_type!r} is a display alias for {alias!r}" if alias else ""
        super().__init__(
            f"unknown link type {link_type!r}{hint}. This library allows: "
            + ", ".join(sorted(allowed))
        )


class LinkNeedsTwoEnds(ValueError):
    """Raised when a link points at itself.

    A segment related to itself is either a mistake or a statement about the
    record rather than the source; either way it is not a link, and storing one
    would make "everything related to this" include the thing itself forever.
    """

    def __init__(self, end_id: str) -> None:
        self.end_id = end_id
        super().__init__(f"a link needs two different ends; both are {end_id}")


def resolve_link_type(link_type: str) -> str:
    """The key a caller's word means, resolving a display alias.

    One place, so the alias cannot be honoured by some writers and refused by
    others -- which is how an alias becomes a second key.
    """
    return LINK_TYPE_ALIASES.get(link_type, link_type)
