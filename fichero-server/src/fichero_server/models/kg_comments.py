"""A human comment on a node of the knowledge graph (`kg.interact.comment`, #4643).

A comment is its own record, anchored to a claim, an entity, a source or a segment, and threaded by
`parent_id`. It is never stored as a claim: nothing reads it as something the sources say.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now
from fichero_server.models.knowledge import ProvenanceKind


class CommentAnchorKind(str, Enum):
    claim = "claim"
    entity = "entity"
    source = "source"
    segment = "segment"


class KgComment(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    anchor_kind: CommentAnchorKind
    anchor_id: str
    parent_id: str | None = None
    body: str
    created_by: str | None = None
    provenance_kind: ProvenanceKind = ProvenanceKind.unknown
    created_at: datetime = Field(default_factory=utc_now)
    #: Kept in the record, no longer listed (what undo does).
    withdrawn_at: datetime | None = None
