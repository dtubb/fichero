"""dev-workflows.run.records-are-truth: the journal is append-only JSON lines, intents without a done are open, one flock."""
from __future__ import annotations

import fcntl

import pytest

from fichero_builder import journal


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path)


def test_lines_are_appended_and_read_back_in_order():
    journal.append("worker", task="t", window="w")
    journal.append("transition", issue=5, to="coding", why="a")
    assert [e["event"] for e in journal.read()] == ["worker", "transition"]
    assert journal.read()[1]["ts"]


def test_an_incomplete_item_line_is_refused():
    with pytest.raises(ValueError, match="lacks"):
        journal.append("item", issue=5)


def test_open_intents_are_those_without_a_done():
    journal.append("intent", task="t", what="worktree")
    journal.append("intent", task="t", what="tell")
    journal.append("done", task="t", what="tell")
    assert [i["what"] for i in journal.open_intents()] == ["worktree"]


def test_second_holder_waits_on_the_lock_and_it_is_a_real_flock():
    with journal.Lock("test-run") as lk, open(lk.p) as other:
        with pytest.raises(BlockingIOError):
            with journal.Lock("test-run", wait=False):
                pass
        with pytest.raises(BlockingIOError):
            fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    with journal.Lock("test-run", wait=False):
        pass  # free again
