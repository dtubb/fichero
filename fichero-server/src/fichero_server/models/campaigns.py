"""Campaigns of writing: what lies over what on one patch of page (slice 14, #4935).

Spec: `readings-and-apparatus.md`, "Campaigns" (`source.campaign.*`). The main ink, the rubric, vowel
marks added a century later, stylus reading-marks, a palimpsest's under-text, a librarian's pencil:
each is a campaign with a name, an ORDER (what lies over what), and optionally a hand and a date
(`source.campaign.ordered`). Each segment belongs to one campaign; two campaigns can share the same
characters (the consonants in one, their later vowels in another), and a reading says which
campaigns it takes in (`source.campaign.reading-says-which`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now
from fichero_server.models.knowledge import ProvenanceKind


def _new_id() -> str:
    return uuid.uuid4().hex


class Campaign(BaseModel):
    """One campaign of writing on a source."""

    id: str = Field(default_factory=_new_id)
    #: The source (or page) the campaigns are of.
    document_id: str
    name: str
    #: What lies over what: 1 is the first campaign, laid down first; higher lies over it. (Not
    #: `order`: a column is not quoted, and ORDER is SQL's own word.)
    sequence: int = 1
    hand_id: str | None = None
    #: A date or period, as words ("s. XII"); a date on the common count is slice 15's.
    date: str | None = None
    notes: str | None = None
    provenance_kind: ProvenanceKind = ProvenanceKind.unknown
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    withdrawn_at: datetime | None = None


class CampaignMembership(BaseModel):
    """A segment belongs to ONE campaign: one live row per segment."""

    id: str = Field(default_factory=_new_id)
    segment_id: str
    campaign_id: str
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    #: Superseded when the segment is assigned elsewhere; never deleted.
    superseded_at: datetime | None = None


class ReadingCampaigns(BaseModel):
    """Which campaigns one reading takes in: the consonants and their later vowels, or only one."""

    id: str = Field(default_factory=_new_id)
    representation_id: str
    campaign_ids: list[str] = Field(default_factory=list)
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    superseded_at: datetime | None = None
