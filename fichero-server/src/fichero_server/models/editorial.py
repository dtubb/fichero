"""Editorial facts: what the editor knows about the text on the page, recorded as FACTS (slice 14, #4935).

Spec: `readings-and-apparatus.md`, "Three different kinds of 'sure'" (`source.sure.*`).

A reading says what the text IS. An editorial fact says something ABOUT a stretch of it: that it is
*unclear*; *lost* (with how much, and why -- water, a hole, trimming); *restored* by the editor;
*supplied* (left out by the scribe); *superfluous*; *deleted* by the scribe; *added* by the scribe
(and where: above the line, in the margin). Each is its own record, with an extent, a reason and an
author (`source.sure.editorial-facts`).

The editor's brackets and dots (Leiden) are DRAWN from these facts when a reading is shown or
exported -- `editorial/leiden.py` -- and never typed into the reading's text
(`source.sure.brackets-are-drawn`). And the three kinds of "sure" stay apart
(`source.sure.three-kinds`): a machine's confidence lives on the reading, a scholar's certainty on
the judgement it qualifies (here `certainty`, as on a hand attribution), and the state of the page is
these facts. Never one number.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now
from fichero_server.models.knowledge import ProvenanceKind


def _new_id() -> str:
    return uuid.uuid4().hex


class EditorialFactKind(str, Enum):
    """What an editor can say about a stretch of text. An open list is a question for the maintainer;
    these are the spec's seven."""

    unclear = "unclear"
    lost = "lost"
    restored = "restored"
    supplied = "supplied"
    superfluous = "superfluous"
    deleted = "deleted"
    added = "added"


class EditorialFact(BaseModel):
    """One fact about one stretch of one segment's text (`source.sure.editorial-facts`)."""

    id: str = Field(default_factory=_new_id)
    segment_id: str
    kind: EditorialFactKind
    #: The reading the character span indexes into (a reading's text can change; the fact names the
    #: one it was measured on, like a mark). None with no span: the fact is about the whole segment.
    representation_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    #: How much, as words and as a count when there is one: "3 letters", "about 2 lines" -- a lost
    #: stretch has no text to span, so its extent is how the editor says how much is missing.
    extent: str | None = None
    extent_quantity: float | None = None
    extent_unit: str | None = None
    #: Why: water, a hole, trimming, erasure, faded -- or for supplied, "omitted by the scribe".
    reason: str | None = None
    #: Where an ADDED stretch was written: above the line, below it, in the margin, inline.
    place: str | None = None
    #: The scholar's certainty in THIS judgement, 0-1, or None when they did not say. Never a
    #: machine's confidence (`source.sure.three-kinds`).
    certainty: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance_kind: ProvenanceKind = ProvenanceKind.unknown
    created_by: str | None = None
    #: "file: <name>" when an import's file said so (a TEI <unclear>, a PAGE `unclear {}`), else None.
    source: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    #: Withdrawn, never deleted: the record of what an editor once said is kept.
    withdrawn_at: datetime | None = None
