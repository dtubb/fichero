"""Typed human-in-the-loop contract for workflows (#2529).

A workflow node can pause and ask the user a question (disambiguate a reading,
confirm an entity, choose a branch). LangGraph's ``interrupt()`` is the pause
primitive — the checkpointer persists state and the run suspends until it is
resumed with the user's answer.

The *payload* that crosses that boundary needs to be a single typed shape, not
an ad-hoc dict per call site: the SSE/Activity surface and the eventual resume
endpoint both have to render and round-trip it without data loss. This module
owns that contract + a thin ``ask_human()`` wrapper so every node (the catalogue
grouping confirmation today; a general "Ask / Human Review" node next) speaks
the same language.

Resume wiring (a /threads/{id}/resume endpoint that feeds the answer back via
``Command(resume=...)``) is intentionally NOT here yet — see the design notes on
issue #2529. This is the typed foundation it will build on.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HumanReviewRequest(BaseModel):
    """The question a paused workflow surfaces to the user.

    Serialized into the LangGraph interrupt value, so it must be plain-JSON
    safe (no engine objects) — that is what the frontend receives and what the
    resume endpoint will echo back alongside the answer.
    """

    # Stable discriminator so the UI can pick a renderer (free-text vs.
    # the catalogue grouping editor vs. a bbox HTR confirmation, etc.).
    kind: str = "human_review"
    # The human-readable question the AI is asking.
    question: str
    # Optional context to help the human answer: an image region (bbox),
    # a draft transcription, the proposed groupings, etc. Free-form but typed
    # as a dict so it round-trips as JSON.
    context: dict[str, Any] = Field(default_factory=dict)
    # Optional discrete choices — when present, the UI can render buttons.
    options: list[str] | None = None
    # The node that asked, for attribution in Activity (filled by callers
    # that know their node id).
    node_id: str | None = None


def ask_human(
    question: str,
    *,
    kind: str = "human_review",
    context: dict[str, Any] | None = None,
    options: list[str] | None = None,
    node_id: str | None = None,
) -> Any:
    """Suspend the workflow and ask the user ``question``; return their answer.

    Thin wrapper over LangGraph ``interrupt()`` that enforces the typed
    :class:`HumanReviewRequest` payload. The return value is whatever the
    resume call feeds back (``Command(resume=<answer>)``) — typically the
    user's typed answer or a structured edit.

    Imported lazily so this module stays importable without langgraph (e.g.
    for contract tests / schema export).
    """
    from langgraph.types import interrupt

    payload = HumanReviewRequest(
        kind=kind,
        question=question,
        context=context or {},
        options=options,
        node_id=node_id,
    )
    return interrupt(payload.model_dump())
