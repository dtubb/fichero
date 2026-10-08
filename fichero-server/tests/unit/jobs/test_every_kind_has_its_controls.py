"""Pause, resume, cancel and retry on every kind of job, through the one job API (#5356).

WHY (`activity.pause.per-job`, `activity.pause.one-start-stop`): the window, MCP and the command line
offer the same four controls on every row. Kinds grew their own stop routes and some could not be
stopped from their row at all once running, and nothing could be retried. Each registered kind is
pinned here, so a new kind that cannot take the four controls fails this test rather than a person.
"""
from __future__ import annotations

import importlib

import pytest

from fichero_server.execution import jobs

for _module in (*jobs._KIND_MODULES, "fichero_server.llm.local_models"):
    getattr(importlib.import_module(_module), "register_job_kinds", lambda: None)()

QUEUED = sorted(k for k, v in jobs.KINDS.items() if v.run is not None)
HANDED_IN = sorted(k for k, v in jobs.KINDS.items() if v.run is None and v.pause is None)
#: Work that runs a long time on its own row, stopped while it runs by a flag its loop reads.
STOPPED_WHILE_RUNNING = ("check", "check-lines", "tie-text-to-lines", "read-at-scale", "gather-reasons",
                         "train-on-this-mac", "evaluate-models")


@pytest.fixture
def held(db):
    jobs.set_paused(True)  # nothing runs: the controls are what is tested, not the work
    yield db
    jobs.set_paused(False)


def _control(client, job_id, verb, **body):
    if verb == "paused":
        return client.put(f"/api/activity/jobs/{job_id}/paused", json=body)
    return client.post(f"/api/activity/jobs/{job_id}/{verb}")


@pytest.mark.parametrize("kind", QUEUED)
def test_a_queued_kind_pauses_resumes_cancels_and_retries(kind, held, client):
    job_id = jobs.enqueue(held, kind, f"controls:{kind}")

    assert _control(client, job_id, "paused", paused=True).json()["state"] == "paused"
    assert _control(client, job_id, "paused", paused=False).json()["state"] == "waiting"
    assert _control(client, job_id, "cancel").json()["state"] == "cancelled"

    retried = _control(client, job_id, "retry")
    if jobs.KINDS[kind].no_retry:
        assert retried.status_code == 409 and retried.json()["detail"] == jobs.KINDS[kind].no_retry
        return
    assert retried.status_code == 200 and retried.json()["state"] == "waiting"
    assert held.execute_fetchone("SELECT reason, attempts FROM jobs WHERE id = ?", [job_id]) == ("Retried by you", 0)
    assert _control(client, job_id, "retry").json()["state"] == "waiting"  # not finished: unchanged


@pytest.mark.parametrize("kind", HANDED_IN)
def test_handed_in_work_is_retried_through_what_waits_for_it(kind, held, client):
    job_id = jobs.enqueue(held, kind, f"controls:{kind}")
    held.execute("UPDATE jobs SET state = 'failed' WHERE id = ?", [job_id])
    r = _control(client, job_id, "retry")
    assert r.status_code == 409 and "retry that instead" in r.json()["detail"]


@pytest.mark.parametrize("kind", STOPPED_WHILE_RUNNING)
def test_a_running_long_job_is_stopped_from_its_row(kind, held, client):
    """WHY: Stop on a running check, reading at scale or gathering reasons did nothing from its
    row (only from its own route); the row's Stop must reach the flag the running loop reads."""
    assert jobs.KINDS[kind].cancel is not None
    job_id = jobs.enqueue(held, kind, f"controls:{kind}", detail='{"request": {}}')
    held.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [job_id])
    assert _control(client, job_id, "cancel").json()["state"] == "running"
    assert jobs.read_job(held, job_id)["detail"].count('"cancel": true') == 1

    held.execute("UPDATE jobs SET state = 'cancelled' WHERE id = ?", [job_id])
    if jobs.KINDS[kind].no_retry is None:
        _control(client, job_id, "retry")
        assert '"cancel"' not in (jobs.read_job(held, job_id)["detail"] or "")  # a retry is not stopped at once


def test_retry_refuses_when_the_same_work_already_waits(held, client):
    first = jobs.enqueue(held, "metrics", "same")
    held.execute("UPDATE jobs SET state = 'failed' WHERE id = ?", [first])
    jobs.enqueue(held, "metrics", "same")
    r = _control(client, first, "retry")
    assert r.status_code == 409 and r.json()["detail"] == "The same work is already waiting to run"
