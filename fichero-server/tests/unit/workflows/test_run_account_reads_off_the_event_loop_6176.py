"""`engine.polls-read-off-the-loop` (#6176, #6178): a run's account reads the project's rows on a worker thread, never on the
event loop. Opus review 2026-10-26: `waiting_reason` and `_title_failed_pages` were synchronous reads inside `async run_account`;
a writer holding the transaction gate stalled the whole loop for up to 17 s, `/api/health` answered late, and the app restarted
the engine.
WHY: the loop must answer health while the project's database is busy."""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

from fichero_server.workflows import run_account as ra


def test_the_accounts_database_reads_are_off_the_event_loop(monkeypatch):
    seen: dict[str, bool] = {}
    loop_thread = threading.get_ident()

    def waiting_reason(_db, _thread):
        seen["waiting_reason"] = threading.get_ident() != loop_thread
        return None

    def title_failed_pages(_db, _failures):
        seen["titles"] = threading.get_ident() != loop_thread

    monkeypatch.setattr(ra, "waiting_reason", waiting_reason)
    monkeypatch.setattr(ra, "_title_failed_pages", title_failed_pages)
    monkeypatch.setattr(ra, "_FINISHED", {})
    run = SimpleNamespace(status="running", error=None, started_at=None, run_usage=None, resolved_scope=None)
    account = asyncio.run(ra.run_account(object(), "thread-1", run=run, state={}, pending_writes=()))
    assert account is not None
    assert seen == {"waiting_reason": True, "titles": True}
