"""`activity.persists-from-any-thread`: an Activity written from a worker thread with no event loop is kept.

Seen 2026-10-11 in a dev engine's log: "Activity could not be persisted: no running event loop (Processing imported
pages started)", and the same for "stalled at 27 of 184". The import's queue says so from its own threads (a
timer, a job thread), and the tracker, made on such a thread, had no loop to save on, so the row was lost.
"""

from __future__ import annotations

import asyncio
import threading

from fichero_server.workflows.activity import ActivityFilter, ActivityTracker
from fichero_server.workflows.activity_types import ActivityType


def _in_a_thread(fn) -> None:
    errors: list[BaseException] = []

    def body() -> None:
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 -- re-raised below, on the test's thread
            errors.append(exc)

    worker = threading.Thread(target=body)
    worker.start()
    worker.join(30)
    assert not errors, errors


def _messages(tracker: ActivityTracker) -> list[str]:
    return [a.message for a in asyncio.run(tracker.store.query(ActivityFilter(types=[ActivityType.SYSTEM_INFO])))]


def test_a_tracker_made_and_written_on_a_worker_thread_keeps_the_row(tmp_path):
    path = str(tmp_path / "activity.duckdb")
    made: dict[str, ActivityTracker] = {}

    def write() -> None:
        made["tracker"] = ActivityTracker(path)
        made["tracker"].log(ActivityType.SYSTEM_INFO, "Processing imported pages started")

    _in_a_thread(write)
    assert "Processing imported pages started" in _messages(made["tracker"])


def test_a_tracker_whose_loop_has_closed_still_keeps_a_row_written_from_a_thread(tmp_path):
    path = str(tmp_path / "activity.duckdb")

    async def make() -> ActivityTracker:
        return ActivityTracker(path)

    tracker = asyncio.run(make())  # its loop is closed once this returns
    _in_a_thread(lambda: tracker.log(ActivityType.SYSTEM_INFO, "Processing imported pages stalled at 27 of 184"))
    assert "Processing imported pages stalled at 27 of 184" in _messages(tracker)
