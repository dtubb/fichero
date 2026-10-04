"""activity.window.absolute-times (#5432): every run time the engine returns
carries its zone.

WHY: a run time with no zone is a time the client has to guess at. The app
read the run list's `started_at` with a parser that refused it and put "now"
in its place, so every Activity row said "just now", even a run a day old.
The engine half of the rule is that a stored (naive, by the #4347 contract
UTC) DuckDB TIMESTAMP leaves the engine as an aware UTC string; if this test
goes red, the app is being handed times it can only read by assuming a zone.

Through the real routes and the real ActivityStore: the store's row mapper
is the one place a run's times become aware, so a test against a mock
would pin nothing.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from fichero_server.workflows.activity import get_activity_tracker


def _assert_has_zone(field: str, value: str | None) -> None:
    assert value is not None, f"{field} is missing"
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, f"{field}={value!r} has no zone"
    assert parsed.utcoffset() == timedelta(0), f"{field}={value!r} is not UTC"


def test_activity_window_absolute_times__every_run_time_carries_its_zone(client, db):
    tracker = get_activity_tracker(str(db.path))
    # Naive, with microseconds: exactly what a DuckDB TIMESTAMP column hands back.
    started = datetime(2026, 10, 3, 9, 10, 11, 123456)
    asyncio.run(
        tracker.store.save_workflow_run(
            thread_id="thread-times",
            workflow_id="wf-times",
            workflow_name="Workflow times",
            status="running",
            started_at=started,
        )
    )
    asyncio.run(
        tracker.store.update_workflow_run(
            "thread-times",
            status="completed",
            completed_at=started + timedelta(minutes=5, microseconds=654321),
        )
    )

    listed = client.get("/api/workflow-execution/runs")
    assert listed.status_code == 200, listed.text
    items = [i for i in listed.json()["items"] if i["thread_id"] == "thread-times"]
    assert len(items) == 1, listed.json()
    _assert_has_zone("runs[].started_at", items[0]["started_at"])
    _assert_has_zone("runs[].completed_at", items[0]["completed_at"])
    # The instant is the stored one, not a shifted or substituted one.
    assert datetime.fromisoformat(items[0]["started_at"]).replace(tzinfo=None) == started

    detail = client.get("/api/workflow-execution/threads/thread-times/run")
    assert detail.status_code == 200, detail.text
    _assert_has_zone("run.started_at", detail.json()["started_at"])
    _assert_has_zone("run.completed_at", detail.json()["completed_at"])
