"""A checker's verdict on one proposal (`source.check.verdict-recorded`, specs/source/checking.md).

Beside the proposal, never in it: a check does not edit what it checks. The trust level is set by the
server from who is writing (`source.check.model-never-a-person`), never accepted from a caller.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now

LAYERS = ("readings", "claims", "entities")
VERDICTS = ("confirm", "correct", "reject")


class CheckVerdict(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    layer: Literal["readings", "claims", "entities"]
    #: The proposal checked: a reading's id, a statement's id or an entity's id.
    target_id: str
    document_id: str | None = None
    verdict: Literal["confirm", "correct", "reject"]
    reasons: str
    #: A statement's or entity's corrected values, held here for a person to take (never applied).
    correction: dict[str, Any] | None = None
    #: A reading's correction: the new reading, which names the one checked.
    replacement_id: str | None = None
    #: A person's name, or the checker model's id.
    checker: str
    trust: Literal["person", "model"]
    run_id: str | None = None
    episode_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
