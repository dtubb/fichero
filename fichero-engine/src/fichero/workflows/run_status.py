"""Canonical workflow-run lifecycle status vocabulary (#2624).

The run-status strings were an uncontracted vocabulary duplicated inline across
the codebase — and the duplicates had drifted (the delete guard counted
``"deleted"`` as terminal; the cancel/pause guards did not). A run that ends in
``"failed"`` vs ``"error"``, or ``"stopped"`` vs ``"cancelled"``, must be treated
identically by every "is this run still active?" check, or the UI shows a
terminated run as still running (an EPIC #2624 symptom).

This module is the single source of truth for that membership test. It does NOT
yet rename/collapse the synonyms (``failed``≈``error``, ``stopped``≈``cancelled``)
— that's a vocabulary decision for Daniel — it just guarantees every check
covers the same set.
"""

from __future__ import annotations

# Every terminal status currently written by the runner / persistence layer.
# Kept as a SUPERSET (both ``error``/``failed`` and ``cancelled``/``stopped``)
# so no in-flight check can miss a terminated run while the synonyms coexist.
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "error", "failed", "cancelled", "stopped"}
)

# A soft-deleted run is also terminal for delete/cleanup purposes.
DELETED_STATUS = "deleted"
DELETABLE_TERMINAL_STATUSES: frozenset[str] = TERMINAL_STATUSES | {DELETED_STATUS}


def is_terminal(status: str | None) -> bool:
    """True if ``status`` is a terminal run state (nothing left to run)."""
    return status in TERMINAL_STATUSES
