"""An interrupted run ends when it stopped, not when the engine noticed (#6588, `activity.pane.row-and-inspector-agree`).

Seen in the Dev Local build, 2026-11-14 night: a Kraken run that worked three minutes before its project was closed read
"1 h" in Time, its end stamped when the next open marked it interrupted. Its end is now the time its words name: the
close's, else the last work it recorded.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

from fichero_server.core.timeutil import ensure_utc, utc_now
from fichero_server.workflows import run_account
from tests.unit.api.test_routes_workflow_execution import _seed_run


def test_a_run_closed_mid_run_ends_at_the_close(db):
    import time

    from fichero_server.workflows.activity import get_activity_tracker

    get_activity_tracker(str(db.path))  # made first: its open's sweep of stale runs passes before the run exists
    time.sleep(0.5)
    started = utc_now() - timedelta(hours=1)
    tracker = _seed_run(db, "thread-closed-early", status="running", started_at=started)
    closed = started + timedelta(minutes=3)
    run_account._CLOSED_MID_RUN["thread-closed-early"] = closed
    try:
        assert "thread-closed-early" in run_account.mark_interrupted_runs(db)
    finally:
        run_account._CLOSED_MID_RUN.pop("thread-closed-early", None)
    run = asyncio.run(tracker.store.get_workflow_run("thread-closed-early"))
    assert run.status == "failed"
    assert abs((ensure_utc(run.completed_at) - closed).total_seconds()) < 2, "it ended at the close, not now"
