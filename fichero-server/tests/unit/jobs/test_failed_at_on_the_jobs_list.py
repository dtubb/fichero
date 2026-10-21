"""`activity.jobs.failed-at`: a failed job says when it failed, and a retry clears it.

WHY (2026-10-11): the Activity popover lists recent errors only, and had to guess each failure's time. Every job in
`GET /api/activity/jobs` carries `failed_at`, an ISO time for a failed job (when it failed), null for any other, and
null again once it is retried. Through the routes and the real jobs table.
"""
from __future__ import annotations

from datetime import datetime, timezone

from tests.unit.jobs.test_clear_failed_5634 import KIND, _failed, held  # noqa: F401 (fixture)


def _job(client, job_id):
    return next(j for j in client.get("/api/activity/jobs").json()["jobs"] if j["id"] == job_id)


def test_a_failed_job_says_when_it_failed_and_a_retry_clears_it(held, client):
    before = datetime.now(timezone.utc)
    job_id = _failed(held, KIND, "failed-at:1")

    row = _job(client, job_id)
    assert row["state"] == "failed" and row["failed_at"], row
    when = datetime.fromisoformat(row["failed_at"])
    assert when.tzinfo is not None, "an ISO time with its zone"
    assert abs((when - before).total_seconds()) < 120, (when, before)

    assert client.post(f"/api/activity/jobs/{job_id}/retry").status_code == 200
    listed = client.get("/api/activity/jobs").json()["jobs"]
    assert all(j.get("failed_at") is None for j in listed if j["state"] != "failed"), listed


def test_a_job_that_has_not_failed_has_no_failed_at(held, client):
    from fichero_server.execution import jobs

    jobs.enqueue(held, KIND, "failed-at:waits")
    listed = client.get("/api/activity/jobs").json()["jobs"]
    assert listed and all(j["failed_at"] is None for j in listed if j["state"] != "failed"), listed


def test_an_ended_job_says_when_it_ended_and_a_live_one_does_not(held, client):
    """`activity.window.done-today` (#5960): DONE TODAY goes by when a job ENDED, so the list carries `finished_at`."""
    from fichero_server.execution import jobs

    failed = _failed(held, KIND, "finished-at:1")
    jobs.enqueue(held, KIND, "finished-at:waits")
    listed = client.get("/api/activity/jobs").json()["jobs"]
    row = next(j for j in listed if j["id"] == failed)
    assert row["finished_at"] and row["finished_at"] == row["failed_at"], row
    assert all(j["finished_at"] is None for j in listed if j["state"] in ("waiting", "running", "paused")), listed


import pytest  # noqa: E402


@pytest.mark.parametrize("status", ["completed", "done", "failed", "cancelled", "stopped", "not run"])
def test_a_run_that_ended_in_any_status_reports_when(status):
    """## 748: the workflow half set `finished_at` only for failed runs; every ended status reads its `completed_at`."""
    from fichero_server.api.routes.system.activity import _run_finished_at

    when = datetime(2026, 10, 20, 14, 5, tzinfo=timezone.utc)
    assert _run_finished_at(status, when) == when


@pytest.mark.parametrize("status", ["running", "paused", "waiting"])
def test_a_run_that_has_not_ended_has_no_finished_at(status):
    from fichero_server.api.routes.system.activity import _run_finished_at

    assert _run_finished_at(status, datetime(2026, 10, 20, 14, 5, tzinfo=timezone.utc)) is None
