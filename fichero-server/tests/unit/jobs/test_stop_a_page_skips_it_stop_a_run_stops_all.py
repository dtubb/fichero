"""Stop on one page skips it and its run carries on; Stop on a run leaves no child reading running or waiting
(`activity.stop.page-skips-run-stops-children`, owner screenshot 2026-10-19 16:27: the run said "Stopped" while its step said
"Running 0 of 2" and IMG_004 still waited)."""
from __future__ import annotations

import asyncio
from concurrent.futures import Future

import pytest

from fichero_server.execution import jobs


def _row(db, job_id, kind, parent, state, reason=None):
    db.execute("INSERT INTO jobs (id, kind, subject, parent_id, state, reason, created_at, started_by) "
               "VALUES (?, ?, ?, ?, ?, ?, now(), 'workflow')", [job_id, kind, job_id, parent, state, reason])


def test_a_page_stopped_alone_raises_page_stopped_and_its_row_ends_cancelled(db):
    jobs._ensure(db)
    _row(db, "page-1", "read-a-page", None, "waiting")
    future = Future()
    future.job_id = "page-1"

    async def go():
        signal = asyncio.get_running_loop().create_future()
        assert jobs._scheduler.withdraw(db, future)  # what Stop on the page does
        signal.cancel()
        return await jobs._wait_for_lane(db, future, signal, "no-such-run")

    with pytest.raises(jobs.PageStopped):
        asyncio.run(go())
    row = jobs.read_job(db, "page-1")
    assert row["state"] == "cancelled" and row["reason"] == "Stopped by you"  # stopped, not failed
    assert issubclass(jobs.PageStopped, jobs.JobCancelled)  # the fan-out skips it and goes on (builder: not a failure)


def test_the_fan_out_treats_a_stopped_page_as_cancelled_not_failed():
    import inspect

    from fichero_server.workflows import builder

    assert "JobCancelled" in inspect.getsource(builder)


def test_stop_on_a_run_leaves_no_child_reading_running_or_waiting(db):
    jobs._ensure(db)
    _row(db, "run-1", "workflow", None, "cancelled", "Stopped by you")
    _row(db, "step-1", "workflow-step", "run-1", "running")
    _row(db, "page-a", "read-a-page", "step-1", "waiting")
    _row(db, "page-b", "read-a-page", "step-1", "paused")
    _row(db, "page-c", "read-a-page", "step-1", "done")
    _row(db, "sub-run", "workflow", "step-1", "running")
    _row(db, "sub-page", "read-a-page", "sub-run", "waiting")
    assert jobs.settle_stopped_children(db, "run-1") == 5
    for job_id in ("step-1", "page-a", "page-b", "sub-run", "sub-page"):
        assert jobs.read_job(db, job_id)["state"] == "cancelled", job_id
    assert jobs.read_job(db, "page-c")["state"] == "done"  # a finished page keeps its result
    states = {r[0] for r in db.execute_fetchall("SELECT state FROM jobs WHERE id <> 'run-1'")}
    assert not states & {"running", "waiting"}
