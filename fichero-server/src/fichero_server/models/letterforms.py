"""Letterforms, described the way palaeographers describe them (slice 14, #4935).

Spec: `readings-and-apparatus.md`, "Letterforms" (`source.letterform.*`); the model is Archetype's
(DigiPal), `source-survey.md`: character > allograph > a scribe's own form > the mark on the page,
described by component and feature ("ascender: wedged").

- An **allograph** is a recognised form of a character ("uncial a", "insular a"): a project record,
  like a hand, shared across sources.
- A **letterform description** hangs on ONE character segment -- this very mark -- and names its
  chain (`source.letterform.chain`): the abstract character (text, or a declared sign), the allograph,
  and the hand whose way of making it this is (the scribe's own form is that allograph as that hand
  writes it). It carries components and features from OPEN lists (`source.letterform.features`): any
  words a project uses; the lists are what the project has used.
- Marks of the same character, allograph or hand are then gathered across hands and sources
  (`source.letterform.compare`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now
from fichero_server.models.knowledge import ProvenanceKind


def _new_id() -> str:
    return uuid.uuid4().hex


class Allograph(BaseModel):
    """A recognised form of a character, in the project's list."""

    id: str = Field(default_factory=_new_id)
    #: The abstract character it is a form of: its text ("a", "ܐ") or a declared sign's id.
    character: str
    #: What the field calls it: "uncial a", "insular a", "Estrangela alaph".
    name: str
    notes: str | None = None
    provenance_kind: ProvenanceKind = ProvenanceKind.unknown
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    withdrawn_at: datetime | None = None


class LetterFeature(BaseModel):
    """One component and what it is like: "ascender" -> "wedged". Both open words."""

    component: str = Field(min_length=1, max_length=80)
    feature: str = Field(min_length=1, max_length=80)


class LetterformDescription(BaseModel):
    """This very mark, described: its chain and its features (`source.letterform.chain`, `.features`)."""

    id: str = Field(default_factory=_new_id)
    #: The character segment it describes.
    segment_id: str
    #: The abstract character: text, or a declared sign's id.
    character: str
    allograph_id: str | None = None
    #: The hand whose way of making it this is -- with the allograph, the scribe's own form.
    hand_id: str | None = None
    features: list[LetterFeature] = Field(default_factory=list)
    provenance_kind: ProvenanceKind = ProvenanceKind.unknown
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    #: Withdrawn, never deleted; a new description of the same mark supersedes by withdrawing the old.
    withdrawn_at: datetime | None = None
