"""A checker's verdict on one proposal (`source.check.verdict-recorded`, specs/source/checking.md).

Beside the proposal, never in it: a check does not edit what it checks. The trust level is set by the
server from who is writing (`source.check.model-never-a-person`), never accepted from a caller.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


class CheckRunRequest(BaseModel):
    layer: Literal["readings", "claims", "entities"] = Field(description="Which layer's proposals to check.")
    scope_ids: list[str] = Field(description="Folders, pages or documents: their lines, or their statements and entities.")
    provider: str = Field(description="The checker's provider, e.g. openrouter, omlx.")
    model: str = Field(description="The checker model, e.g. a palaeographer such as Fable.")
    prompt_file: str | None = Field(None, description="The recipe's prompt for this card; none uses Fichero's own.")
    language: str | None = None
    kind: str = Field("transcription", description="readings: the kind of reading checked.")
    pass_model: str | None = Field(None, description="readings: check the lines of this model's pass, not the "
                                   "page's newest.")
    check: Literal["model", "line-against-page"] = Field(
        "model", description="model: the checker model reads each proposal. line-against-page (readings only, "
        "provider kraken, model a Kraken reader): each line's reading is scored against Kraken's rough read of "
        "that line and of its neighbours; a reading closer to a neighbour's line, or below the threshold, is "
        "rejected (#5446).")


class CheckVerdictParams(BaseModel):
    model_config = ConfigDict(extra="forbid")  # no `trust`, no `checker`: the server's to set

    layer: Literal["readings", "claims", "entities"]
    target_id: str
    verdict: Literal["confirm", "correct", "reject"]
    reasons: str
    correction: dict[str, Any] | None = None
    replacement_id: str | None = None
    #: The model whose verdict this is, written by a check run; a person's own verdict names none.
    checker_model: str | None = None
    episode_id: str | None = None
    #: A reading not yet stored (it still lives in a run's output) is found through its line.
    segment_id: str | None = None
