"""Recovery of runs a dead process left unfinished, on the library's managed connection (#1362, #4316, #5645).

#1362: `workflow_runs` sat on hand-made connections, and a stale index after a crashed session's WAL replay made the
recovery UPDATE raise a FATAL "Failed to delete all rows from index", poisoning the database; a hand-rolled rebuild of
the whole table was the workaround. Since #5644 `connect_utc` rebuilds every secondary index right after a replay,
before anything can checkpoint, and since #5645 the runs are `WorkflowRunRecord` rows on the managed connection, which
recovers its own connection. The rebuild is gone; what recovery still promises is pinned here:

- constructing the store never flips a run (F5: reopening a library mid-run failed LIVE runs, #4316);
- the sweep flips only unfinished runs older than its cutoff, never one this process is tracking;
- a failure in the sweep is logged and flips nothing; it never takes the library down.
The crash itself (a process killed mid-write, then reopened) is `tests/unit/db/test_saved_is_found_after_a_crash.py`.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fichero_server.db import Database
from fichero_server.workflows.activity_store import ActivityStore


def _library(tmp_path: Path) -> tuple[Database, ActivityStore]:
    package = tmp_path / "Runs.fichero"
    package.mkdir()
    db = Database(package / "fichero.duckdb")
    return db, ActivityStore(str(db.path))


def _seed(store: ActivityStore, thread_id: str, *, hours_ago: float, status: str = "running") -> None:
    asyncio.run(store.save_workflow_run(thread_id, "wf", "Read", status=status,
                                        started_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago)))


def _status(store: ActivityStore, thread_id: str) -> str:
    return asyncio.run(store.get_workflow_run(thread_id)).status


def test_constructing_the_store_flips_nothing_and_the_sweep_recovers(tmp_path):
    db, store = _library(tmp_path)
    try:
        for n in range(4):
            _seed(store, f"zombie-{n}", hours_ago=5)
        ActivityStore(str(db.path))  # reopened mid-run: F5
        assert {_status(store, f"zombie-{n}") for n in range(4)} == {"running"}
        recovered = asyncio.run(store.recover_stale_runs(max_age_hours=0))
        assert sorted(recovered) == [f"zombie-{n}" for n in range(4)]
        assert {_status(store, f"zombie-{n}") for n in range(4)} == {"failed"}
        assert asyncio.run(store.get_workflow_run("zombie-0")).error.startswith("Run interrupted")
    finally:
        db.close()


def test_the_sweep_keeps_to_its_cutoff_and_never_flips_a_tracked_run(tmp_path):
    db, store = _library(tmp_path)
    try:
        _seed(store, "old", hours_ago=5)
        _seed(store, "young", hours_ago=0.1)
        _seed(store, "tracked", hours_ago=5)
        _seed(store, "paused", hours_ago=5, status="paused")  # #5357: a paused run needs no process
        _seed(store, "accepted", hours_ago=5, status="accepted")
        recovered = asyncio.run(store.recover_stale_runs(max_age_hours=2, exclude_thread_ids=("tracked",)))
        assert sorted(recovered) == ["accepted", "old"]
        assert _status(store, "young") == "running" and _status(store, "tracked") == "running"
        assert _status(store, "paused") == "paused"
    finally:
        db.close()


def test_a_failing_sweep_flips_nothing_and_the_library_stays_usable(tmp_path, monkeypatch):
    from fichero_server.db import activity_records

    db, store = _library(tmp_path)
    try:
        _seed(store, "zombie", hours_ago=5)

        def broken(*args, **kwargs):
            raise RuntimeError("as a FATAL from a stale index would")

        monkeypatch.setattr(activity_records, "recover_stale", broken)
        assert asyncio.run(store.recover_stale_runs(max_age_hours=0)) == []
        assert _status(store, "zombie") == "running", "nothing flipped"
        assert len(asyncio.run(store.list_workflow_runs())) == 1, "the library still answers"
    finally:
        db.close()
