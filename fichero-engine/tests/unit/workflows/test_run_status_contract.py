"""#2624: canonical run-status vocabulary contract.

Every "is this run still active?" check must agree on the terminal set, or a
finished/cancelled run shows as still running. These pin the canonical set and
the is_terminal() helper that the thread cancel/pause/delete guards now share.
"""

from __future__ import annotations

import pytest

from fichero.workflows.run_status import (
    DELETABLE_TERMINAL_STATUSES,
    TERMINAL_STATUSES,
    is_terminal,
)


@pytest.mark.parametrize(
    "status", ["completed", "error", "failed", "cancelled", "stopped"]
)
def test_terminal_statuses_are_terminal(status):
    assert is_terminal(status)
    assert status in TERMINAL_STATUSES


@pytest.mark.parametrize("status", ["running", "paused", "queued", "", None])
def test_non_terminal_statuses_are_not_terminal(status):
    assert not is_terminal(status)


def test_error_and_failed_both_terminal():
    # The synonyms coexist today; both MUST count as terminal so a finished run
    # never reads as still-running regardless of which the writer used.
    assert is_terminal("error") and is_terminal("failed")


def test_cancelled_and_stopped_both_terminal():
    assert is_terminal("cancelled") and is_terminal("stopped")


def test_deleted_is_deletable_terminal_but_not_a_run_terminal():
    # 'deleted' is terminal for delete/cleanup, but is_terminal() (used by
    # cancel/pause) intentionally excludes it — it's a soft-delete marker.
    assert "deleted" in DELETABLE_TERMINAL_STATUSES
    assert "deleted" not in TERMINAL_STATUSES
    assert not is_terminal("deleted")
    assert TERMINAL_STATUSES <= DELETABLE_TERMINAL_STATUSES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
