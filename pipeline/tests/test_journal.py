"""pipeline.resume-from-journal, journal-lock."""
from __future__ import annotations

import pytest

from pipeline import journal


def test_replay_gives_the_same_state(scratch):
    from pipeline import core
    journal.append("item", issue=5, key="5", task="t", title="x", window="w", worktree="/wt", ids=[])
    journal.append("transition", issue=5, to="coding", why="a")
    journal.append("check", issue=5, ok=False, sha="abc", results=[{"name": "ready", "ok": False, "text": "no", "seconds": 1}])
    journal.append("transition", issue=5, to="coding", why="retry")
    journal.append("queue", id="q1", kind="ask", text="?", options=["y"], task="t", window="w")
    journal.append("point", milestone="m")
    first = core.state()
    assert first["items"]["5"]["state"] == "coding" and first["items"]["5"]["attempts"] == 1
    assert first["point"] == "m" and list(first["queue"]) == ["q1"]
    lines = journal.path().read_text()
    journal.path().write_text(lines)
    assert core.state() == first
    journal.append("answer", id="q1", text="y")
    assert core.state()["queue"] == {}


def test_open_intents_are_those_without_a_done(scratch):
    journal.append("intent", task="t", what="worktree")
    journal.append("intent", task="t", what="tell")
    journal.append("done", task="t", what="tell")
    assert [i["what"] for i in journal.open_intents()] == ["worktree"]


def test_second_dispatcher_waits_on_the_journal_lock(scratch):
    with journal.Lock("dispatch"):
        with pytest.raises(BlockingIOError):
            with journal.Lock("dispatch", wait=False):
                pass
    with journal.Lock("dispatch", wait=False):
        pass  # free again
