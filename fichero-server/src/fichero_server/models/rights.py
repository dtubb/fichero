"""Rights and consent records, and what they add up to (slice 14, #4953).

Spec: `rights-and-access.md` (`source.rights.*`). Approved 2026-09-27.

A **rights record** hangs on a project (the library), a source (a document, or a folder of
them), or a segment. It says who holds rights; what was consented to, by whom, when; any
conditions; LABELS from an open list (Traditional Knowledge and Biocultural labels belong to the
communities that apply them -- Fichero carries them, never invents them); whether the material
is RESTRICTED and, if so, the people who may see it; and whether it may go to a cloud model, a
local model only, or none.

**It passes downward and only tightens** (`source.rights.tighten-only`): `effective_rights`
combines every live record from the library down to the target so that a lower record can add
a restriction, never remove one -- restricted if ANY record restricts; the people who may see it
are the INTERSECTION of each restricting record's names; model use is the STRICTEST stated.
Enforcement (who is refused what) is a separate question, `source.rights.one-check`, and is not
decided in this module.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now
from fichero_server.models.knowledge import ProvenanceKind


def _new_id() -> str:
    return uuid.uuid4().hex


class RightsTarget(str, Enum):
    library = "library"
    document = "document"
    segment = "segment"


class ModelUse(str, Enum):
    """Where a segment may be sent (`source.rights.model-use`), strictest first."""

    none = "none"
    local = "local"
    cloud = "cloud"


#: Strictness order: a lower number is tighter.
MODEL_USE_RANK = {ModelUse.none.value: 0, ModelUse.local.value: 1, ModelUse.cloud.value: 2}


class RightsRecord(BaseModel):
    id: str = Field(default_factory=_new_id)
    target_kind: str
    #: The document or segment id; for the library, the literal "library".
    target_id: str
    holders: list[str] = Field(default_factory=list)
    #: `{"what", "by", "when"}` -- what was consented to, by whom, when.
    consent: dict[str, Any] | None = None
    conditions: str | None = None
    #: Open list: a community's TK/BC label, or a project's own.
    labels: list[str] = Field(default_factory=list)
    restricted: bool = False
    #: When restricted: the ACCOUNTS (user ids) that may see it. Ruled 2026-09-20: being an editor
    #: or the owner is not enough -- only the people a record names.
    readers: list[str] = Field(default_factory=list)
    model_use: str | None = None
    provenance_kind: ProvenanceKind = ProvenanceKind.unknown
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    withdrawn_at: datetime | None = None


@dataclass
class EffectiveRights:
    """What the records from the library down to one target add up to."""

    restricted: bool = False
    #: None = everyone the permission layer allows; otherwise only these accounts.
    readers: set[str] | None = None
    #: The strictest model use any record states, or None when none says.
    model_use: str | None = None
    labels: list[str] = field(default_factory=list)
    #: The records that contributed, library first.
    record_ids: list[str] = field(default_factory=list)


def combine(records: list[RightsRecord]) -> EffectiveRights:
    """Tighten-only: `records` ordered from the library down; only restrictions accumulate."""
    effective = EffectiveRights()
    for record in records:
        if record.withdrawn_at is not None:
            continue
        effective.record_ids.append(record.id)
        for label in record.labels:
            if label not in effective.labels:
                effective.labels.append(label)
        if record.restricted:
            named = set(record.readers)
            effective.readers = named if effective.readers is None else effective.readers & named
            effective.restricted = True
        if record.model_use is not None and (
            effective.model_use is None
            or MODEL_USE_RANK[record.model_use] < MODEL_USE_RANK[effective.model_use]
        ):
            effective.model_use = record.model_use
    return effective
