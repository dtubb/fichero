"""Durable work: a paused run is still paused after a relaunch, and resumes without doing a page twice (#5357).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md -- `activity.durable.paused-stays-paused`,
`activity.durable.nothing-twice`, `activity.stale-runs-settle-across-restarts`. Found by reading the open-time
sweep: every running, accepted *and paused* run was turned into a failed one on reopen, although a paused run
resumes from its checkpoint on disk. Driven through the public surface: a real run started with
`POST /api/workflow-execution/execute`, paused with the job control, the project closed and opened again
through the database manager (what a relaunch does), and resumed with the run's Resume. Only the model call
is a stub (a cloud model answering from memory).
"""
# ruff: noqa: F811 -- pytest fixtures imported from test_runs_are_jobs are named as test arguments
from __future__ import annotations

import threading
import time

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    _execute,
    _status,
    _tree,
    _wait_for,
    cloud,
    no_embedding_model,
    pages,
    workflow,
)


def test_activity_durable_paused_stays_paused__a_paused_run_survives_a_relaunch_and_resumes_once(
        client, test_package, workflow, pages, cloud, monkeypatch):
    """Behaviour `activity.durable.paused-stays-paused`: a run paused by a person is still paused after the
    project is opened again, its row in Activity says paused, and its Resume carries on from its checkpoint;
    `activity.durable.nothing-twice`: the page read before the pause is not read again."""
    monkeypatch.setitem(jobs.LANES, "network", 1)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    cloud.gate = threading.Event()
    run = _execute(client, workflow, pages)
    assert cloud.first_call.wait(30)
    assert client.put(f"/api/activity/jobs/{run}/paused", json={"paused": True}).status_code == 200
    cloud.gate.set()
    assert _wait_for(lambda: _status(client, run) == "paused")
    time.sleep(0.5)
    assert cloud.calls == 1

    db_manager.close_database(test_package)  # quit
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())  # a new engine process
    db_manager.get_database(test_package)  # relaunch: the project opens again

    assert _status(client, run) == "paused"
    tree = _tree(client, run)
    assert tree["state"] == "paused", tree
    listed = {j["id"]: j for j in client.get("/api/activity/jobs").json()["jobs"]}
    assert listed[run]["state"] == "paused"

    r = client.post(f"/api/workflow-execution/threads/{run}/resume")
    assert r.status_code in (200, 202), r.text
    assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    assert _status(client, run) == "completed"
    assert cloud.calls == 3  # the page read before the pause is not read again
