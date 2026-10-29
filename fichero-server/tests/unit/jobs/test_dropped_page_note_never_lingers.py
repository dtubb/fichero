"""Review (reviewer-lane-b-4): a page Stop dropped is noted so its row ends cancelled (`jobs._DROPPED_PAGES`). A page
that ended between the withdraw and the note, or one deferred back to waiting, must not leave its note behind (the
next run of that job would end "cancelled")."""
from __future__ import annotations

from concurrent.futures import Future

from fichero_server.execution import jobs


def test_a_note_for_a_page_that_already_ended_is_pruned_by_the_next(monkeypatch):
    monkeypatch.setattr(jobs, "_DROPPED_PAGES", {})
    ended: Future = Future()
    jobs._note_dropped("late", "Stopped by you", ended)
    ended.set_result(None)  # the page ended (its row written) without seeing the note
    running: Future = Future()
    jobs._note_dropped("p2", "Stopped by you", running)
    assert list(jobs._DROPPED_PAGES) == ["p2"], "a page still running keeps its note; the ended one's is gone"
