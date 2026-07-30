"""Canonical workflow-run lifecycle status vocabulary (#2624, #4316).

One vocabulary, used by every writer and every "is this run still active?"
check: ``accepted → running → paused → completed | failed | cancelled``
(plus the soft-delete marker ``deleted``). #4316 collapsed the historical
synonyms — nothing ever wrote ``error`` or ``stopped``; readers that meet a
legacy row normalize via :func:`normalize_status` — and made ``paused`` /
``accepted`` first-class lifecycle states: cancellable, deletable, and swept
by recovery past an age cutoff instead of being dead ends.

The :class:`RunStatus` enum is exported through the OpenAPI schema
(``ExecutionStatusResponse.status`` / ``WorkflowRunResponse.status``) so the
app can replace its hand-rolled status enums with the generated one.
"""

from __future__ import annotations

from enum import Enum


class RunStatus(str, Enum):
    """Canonical lifecycle states of a workflow run (#4316)."""

    accepted = "accepted"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    # Soft-delete marker — a storage state, not a lifecycle outcome; kept in
    # the enum so persisted rows always round-trip through typed responses.
    deleted = "deleted"


# Legacy synonyms that pre-#4316 docs claimed but no code path ever wrote.
# Readers normalize them defensively so an old row can never dodge a
# terminal check.
LEGACY_STATUS_ALIASES: dict[str, str] = {"error": "failed", "stopped": "cancelled"}


def normalize_status(status: str | None) -> str | None:
    """Collapse legacy synonyms onto the canonical vocabulary."""
    if status is None:
        return None
    return LEGACY_STATUS_ALIASES.get(status, status)


# Terminal: nothing left to run.
TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})

# Non-terminal lifecycle states — everything recovery must sweep past an age
# cutoff, and everything cancel must be able to reach (#4316).
NON_TERMINAL_STATUSES: frozenset[str] = frozenset({"accepted", "running", "paused"})

# A soft-deleted run is also terminal for delete/cleanup purposes.
DELETED_STATUS = "deleted"

# Deletable: every terminal state, the soft-delete marker, and the two states
# that used to be dead ends — a run paused (or stuck accepted) before its
# first checkpoint must be deletable, not 409 forever (#4316).
DELETABLE_STATUSES: frozenset[str] = TERMINAL_STATUSES | {
    DELETED_STATUS,
    "paused",
    "accepted",
}

# Backwards-compatible alias for pre-#4316 importers.
DELETABLE_TERMINAL_STATUSES: frozenset[str] = DELETABLE_STATUSES


def is_terminal(status: str | None) -> bool:
    """True if ``status`` is a terminal run state (nothing left to run)."""
    return normalize_status(status) in TERMINAL_STATUSES
