"""#2624/#4316: canonical run-status vocabulary contract.

One vocabulary — ``accepted|running|paused|completed|failed|cancelled`` (+ the
soft-delete marker) — used by every writer and every "is this run still
active?" check. #4316 dropped the never-written ``error``/``stopped`` synonyms
from the canonical set (readers normalize them defensively) and made
``paused``/``accepted`` deletable instead of dead ends.
"""

from __future__ import annotations

import pytest

from fichero_server.workflows.run_status import (
    DELETABLE_STATUSES,
    DELETABLE_TERMINAL_STATUSES,
    LEGACY_STATUS_ALIASES,
    NON_TERMINAL_STATUSES,
    RunStatus,
    TERMINAL_STATUSES,
    is_terminal,
    normalize_status,
)


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
def test_terminal_statuses_are_terminal(status):
    assert is_terminal(status)
    assert status in TERMINAL_STATUSES


@pytest.mark.parametrize("status", ["running", "paused", "accepted", "queued", "", None])
def test_non_terminal_statuses_are_not_terminal(status):
    assert not is_terminal(status)


def test_legacy_synonyms_normalize_and_stay_terminal():
    # No code path ever wrote 'error'/'stopped', but a legacy row must still
    # read as terminal via normalization — never as a live run.
    assert normalize_status("error") == "failed"
    assert normalize_status("stopped") == "cancelled"
    assert is_terminal("error") and is_terminal("stopped")
    assert LEGACY_STATUS_ALIASES == {"error": "failed", "stopped": "cancelled"}


def test_canonical_enum_matches_sets():
    values = {s.value for s in RunStatus}
    assert values == {
        "accepted",
        "running",
        "paused",
        "completed",
        "failed",
        "cancelled",
        "deleted",
    }
    assert TERMINAL_STATUSES | NON_TERMINAL_STATUSES | {"deleted"} == values
    assert TERMINAL_STATUSES.isdisjoint(NON_TERMINAL_STATUSES)


def test_paused_and_accepted_are_deletable_but_not_terminal():
    # #4316: a run paused (or stuck accepted) before its first checkpoint must
    # be deletable — previously DELETE 409'd forever.
    assert "paused" in DELETABLE_STATUSES
    assert "accepted" in DELETABLE_STATUSES
    assert not is_terminal("paused")
    assert not is_terminal("accepted")
    assert TERMINAL_STATUSES <= DELETABLE_STATUSES


def test_deleted_is_deletable_but_not_a_run_terminal():
    # 'deleted' is terminal for delete/cleanup, but is_terminal() (used by
    # cancel/pause) intentionally excludes it — it's a soft-delete marker.
    assert "deleted" in DELETABLE_STATUSES
    assert "deleted" not in TERMINAL_STATUSES
    assert not is_terminal("deleted")
    # Back-compat alias kept for pre-#4316 importers.
    assert DELETABLE_TERMINAL_STATUSES == DELETABLE_STATUSES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
