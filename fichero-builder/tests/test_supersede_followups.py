"""dev-workflows.run.supersede follow-ups (manager 2026-11-02): cancel markers are cleaned up, a no-jail ladder leaves a neighbour's
jail alone, and each ladder thread reads its own key."""
from __future__ import annotations

import os
import threading
import time

import pytest

from fichero_builder import check_tool, journal


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "s").mkdir()
    return tmp_path / "s"


def test_old_cancel_markers_are_swept_and_a_fresh_one_stays(state):
    old, fresh = state / "cancel-aaaaaaaaa", state / "cancel-bbbbbbbbb"
    old.write_text("x"), fresh.write_text("y")
    t = time.time() - 3 * 86400
    os.utime(old, (t, t))
    check_tool.sweep_cancels()
    assert not old.exists() and fresh.exists(), "a day-old marker (its ladder ended before `done` wrote it) goes; a live one stays"


def test_a_no_jail_ladder_entering_leaves_a_neighbours_jail_in_force(monkeypatch):
    monkeypatch.setattr(check_tool, "_JAIL", None)
    monkeypatch.setattr(check_tool, "_JAIL_USERS", [0])
    j = object()
    check_tool._jail_enter(j)
    check_tool._jail_enter(None)
    assert check_tool._JAIL is j, "the no-jail ladder did not clear the jail the first one is using"
    check_tool._jail_exit(), check_tool._jail_exit()
    assert check_tool._JAIL is None, "and the last to leave unjails"


def test_cancel_requested_reads_the_calling_ladders_own_key(state):
    seen = {}

    def ladder(name, key):
        check_tool._KEY[0] = key
        barrier.wait(5)
        seen[name] = check_tool.cancel_requested()
    barrier = threading.Barrier(2)
    check_tool.cancel_file("hhhhhhhhh").write_text("new")
    ts = [threading.Thread(target=ladder, args=("a", "check s..hhhhhhhhh")), threading.Thread(target=ladder, args=("b", "check s..kkkkkkkkk"))]
    [t.start() for t in ts], [t.join(5) for t in ts]
    assert seen == {"a": True, "b": False}, "the cancel for one ladder's head never stops the other"


def test_a_ladder_that_ends_removes_its_own_cancel_marker(state, monkeypatch):
    monkeypatch.setattr(check_tool, "_run_ladder", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(check_tool, "load", lambda p: check_tool.Config())
    check_tool.cancel_file("abcdef012").write_text("newer")
    check_tool.run_ladder("/nonexistent", "s" * 9, "abcdef0123456", "/nonexistent", jail_required=False)
    assert not check_tool.cancel_file("abcdef012").exists()
