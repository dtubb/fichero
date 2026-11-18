"""Closing a project PAUSES the work running in it (#6596, #6588, `activity.engine.close-pauses-running-work`).

Spec: docs/contributor_manual/specs/ui/activity-pane.md. Seen in the Dev Local build: a deliberate Close of a project with a
workflow run in flight ended the run failed with a bare red X (the close asked the run to cancel, and the next open marked
it interrupted), while the quit path paused the same run. Now the close pauses it ("Paused: the project closed", never a
failure, never the library's path), and the row's Continue resumes it from its checkpoint.

Through the public surface with the real lanes: the run started with `POST /api/workflow-execution/execute`, the network
lane held by a real handed-in page, the project closed and opened through the database manager, read back through the
run's status, `GET /api/activity/jobs` and the tree, and continued with the row's verb (`PUT /api/activity/jobs/{id}/paused`).
Only the model is a stub (a cloud vision model answering from memory).
"""
# ruff: noqa: F811 -- pytest fixtures imported from test_runs_are_jobs are named as test arguments
from __future__ import annotations

import time

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from tests.unit.jobs.test_closed_mid_run_5608 import _close_and_open, _listed, _waiting_pages, lane_held  # noqa: F401
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


@pytest.fixture(autouse=True)
def fresh_scheduler(monkeypatch, app_db):
    """The reset tests/unit/jobs/conftest.py gave these tests before they moved: a new scheduler and the mode
    "automatic" per test, since the scheduler, its foreground streak and the pause are process-wide."""
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_mode("automatic")
    yield
    jobs.set_mode("automatic")


@pytest.mark.parametrize("every", [False, True], ids=["this-project-closed", "every-project-closed"])
def test_activity_engine_close_pauses_running_work__a_run_in_flight_is_paused_and_continues(
        client, test_package, workflow, pages, cloud, lane_held, every):
    """WHY (#6596): the close failed a run in flight; it is paused, says so in plain words, and Continue finishes it."""
    from fichero_server.execution.runner import _running_workflows

    db = db_manager.get_database(test_package)
    run = _execute(client, workflow, pages)
    assert _wait_for(lambda: _waiting_pages(db, run) == 3, 60)

    db = _close_and_open(test_package, every)

    assert run not in _running_workflows, "a run its project's close paused is not live"
    assert _status(client, run) == "paused"
    tree = _tree(client, run)
    assert (tree["state"], tree["reason"]) == ("paused", jobs.PAUSED_PROJECT_CLOSED)
    listed = _listed(client, run)
    assert (listed["state"], listed["reason"]) == ("paused", jobs.PAUSED_PROJECT_CLOSED)
    assert str(test_package) not in (listed["reason"] or ""), "never the library's path in its words"
    assert _waiting_pages(db, run) == 0, "no page of it waits for a lane any more"

    # The runner's own end after the close (its pages stopped) does not end the run otherwise.
    lane_held.set()
    time.sleep(1.0)
    assert _status(client, run) == "paused"
    assert _tree(client, run)["reason"] == jobs.PAUSED_PROJECT_CLOSED

    # The row's Continue resumes it from its checkpoint, and it ends done.
    r = client.put(f"/api/activity/jobs/{run}/paused", json={"paused": False})
    assert r.status_code == 200, r.text
    assert _wait_for(lambda: _status(client, run) == "completed", 120), _status(client, run)
