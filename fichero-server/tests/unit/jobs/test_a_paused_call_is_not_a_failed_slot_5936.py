"""A body that raises the run's Pause (or Stop) inside a lane slot ends the slot's row `cancelled`, in the pause's words,
never `failed` (#5936, `activity.durable.paused-stays-paused`; Fable runner review 2 MED 5)."""
from __future__ import annotations

import asyncio
import time

import pytest

from fichero_server.execution import jobs
from fichero_server.execution.cancellation import WorkflowCancelled, WorkflowPaused


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")


def _settled(db, subject):
    for _ in range(60):
        state, reason = db.execute_fetchone("SELECT state, reason FROM jobs WHERE subject = ?", [subject])
        if state not in ("running", "waiting"):
            break
        time.sleep(0.1)
    return state, reason


async def _raise_in_slot(test_package, subject, exc):
    with pytest.raises(type(exc)):
        async with jobs.lane_slot(str(test_package), "ask-a-model", subject, model="omlx:reader", run_id="run-5936", lane="local-ml"):
            raise exc


def test_a_pause_raised_in_the_body_ends_the_row_cancelled_paused_with_its_run(db, test_package):
    asyncio.run(_raise_in_slot(test_package, "paused page", WorkflowPaused("run-5936")))
    assert _settled(db, "paused page") == ("cancelled", "Paused with its run")


def test_a_stop_raised_in_the_body_ends_the_row_cancelled_stopped_by_you(db, test_package):
    asyncio.run(_raise_in_slot(test_package, "stopped page", WorkflowCancelled("run-5936")))
    assert _settled(db, "stopped page") == ("cancelled", "Stopped by you")
