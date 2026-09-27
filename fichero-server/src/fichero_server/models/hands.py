"""Hands: who put the ink on the page, as project records (slice 14, #4935).

Spec: `readings-and-apparatus.md`, "Hands" (`source.hand.*`).

A **hand** is a named scribe, or "hand B", with a date or period, a place, a script style and
notes. It is a record in the PROJECT, shared across sources, so "everything in hand B" can be
asked (`source.hand.record`).

A segment names its hand through an **attribution**: which hand, how sure, and who judged it.
Several can stand on one segment at once, because scholars disagree and the model must not make
them agree (`source.hand.attributed`: rival attributions coexist).

**A hand is not provenance** (`source.hand.not-provenance`). Provenance says who made the RECORD
-- a model, a person, a workflow run -- and lives in `provenance_kind` / `created_by` on the
attribution like on every record. The hand says who wrote the INK. Both are kept, separately.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now
from fichero_server.models.knowledge import ProvenanceKind


def _new_id() -> str:
    return uuid.uuid4().hex


class Hand(BaseModel):
    """One hand in a project's list of hands (`source.hand.record`)."""

    id: str = Field(default_factory=_new_id)
    #: What people call it: "hand B", "m2", "the rubricator", or a scribe's name.
    label: str
    #: A named scribe, when one is known.
    scribe: str | None = None
    #: The date or period, as words ("s. III a.C.", "c. 1150") -- a date on the common count is
    #: slice 15's `source.date.*`, not this field.
    date: str | None = None
    place: str | None = None
    #: A script style ("Caroline minuscule", "documentary cursive").
    style: str | None = None
    notes: str | None = None
    provenance_kind: ProvenanceKind = ProvenanceKind.unknown
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    #: Withdrawn, not deleted: attributions that name it must stay resolvable.
    deleted_at: datetime | None = None


class HandAttribution(BaseModel):
    """One judgement that one segment was written by one hand (`source.hand.attributed`)."""

    id: str = Field(default_factory=_new_id)
    hand_id: str
    segment_id: str
    #: How sure the judge is, 0-1, or None when they did not say. Scholarly CERTAINTY, never a
    #: machine's confidence (`source.sure.three-kinds`).
    certainty: float | None = Field(default=None, ge=0.0, le=1.0)
    #: Who made the judgement is `created_by` + `provenance_kind`, as on every record: a person,
    #: or an import saying the FILE said so (an EpiDoc `<handShift>`).
    provenance_kind: ProvenanceKind = ProvenanceKind.unknown
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    withdrawn_at: datetime | None = None
