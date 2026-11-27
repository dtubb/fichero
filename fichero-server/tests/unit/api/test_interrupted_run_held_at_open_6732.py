"""A run the engine's stop cut off is HELD at the next open, not failed (#6732; owner 2026-11-21: interrupted runs resume
from the launch alert). With a checkpoint its record reads `paused` with the held words and the alert's list names it once;
without one it is still marked interrupted, failed."""
from __future__ import annotations

import asyncio
import time

from fichero_server.workflows import run_account
from tests.unit.api.test_routes_workflow_execution import _seed_run
from tests.unit.workflows.test_recovered_run_settles_documents import _write_checkpoint


def test_a_run_with_a_checkpoint_is_held_paused_and_listed_once(db, client):
    from fichero_server.workflows.activity import get_activity_tracker

    get_activity_tracker(str(db.path))  # its own open's sweep passes before the run exists
    time.sleep(0.5)
    tracker = _seed_run(db, "thread-held", status="running")
    asyncio.run(_write_checkpoint(str(db.path), "thread-held", []))

    assert run_account.mark_interrupted_runs(db) == [], "a held run has no documents to settle"

    run = asyncio.run(tracker.store.get_workflow_run("thread-held"))
    assert run.status == "paused"
    assert run_account.held_at_open(run.error), run.error
    listed = client.get("/api/activity/stopped-at-quit").json()
    assert [i["id"] for i in listed["items"]].count("thread-held") == 1


def test_a_run_without_a_checkpoint_is_still_failed(db):
    from fichero_server.workflows.activity import get_activity_tracker

    get_activity_tracker(str(db.path))
    time.sleep(0.5)
    tracker = _seed_run(db, "thread-nothing-saved", status="running")

    assert run_account.mark_interrupted_runs(db) == ["thread-nothing-saved"]
    assert asyncio.run(tracker.store.get_workflow_run("thread-nothing-saved")).status == "failed"
