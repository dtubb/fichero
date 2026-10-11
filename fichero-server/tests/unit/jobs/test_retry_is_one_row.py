"""`activity.retry.one-row`: Retry on a failed row runs it again and Activity still shows one row.

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. WHY (2026-10-11, the hardening pass): on a
scratch engine killed mid-run, Retry on the interrupted workflow run's row was refused with "This is work a workflow
run (or a training) handed in and waits for: retry that instead", though the row WAS the run. A queued job's retry
already puts the same row back (one row, `failed_at` cleared: `test_a_job_that_dies_with_the_engine.py`). A failed
workflow run is now run again over the pages it did not do, with the same workflow and model, as a new run that takes
the old one's place in the list. Through the activity route, with the real lanes.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.db.manager import db_manager
from tests.unit.jobs.test_closed_mid_run_5608 import _close_and_open, _waiting_pages, lane_held  # noqa: F401
from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    _execute,
    _status,
    _wait_for,
    cloud,
    no_embedding_model,
    pages,
    workflow,
)


def _listed(client) -> dict[str, dict]:
    return {j["id"]: j for j in client.get("/api/activity/jobs").json()["jobs"]}


def test_retry_on_an_interrupted_workflow_run_reads_its_pages_again_in_one_row(
        client, test_package, workflow, pages, cloud, lane_held):
    db = db_manager.get_database(test_package)
    run = _execute(client, workflow, pages)
    assert _wait_for(lambda: _waiting_pages(db, run) == 3, 60)
    _close_and_open(test_package)  # the run stops with its project, as it does when the engine goes away
    assert _status(client, run) == "failed" and _listed(client)[run]["failed_at"]

    r = client.post(f"/api/activity/jobs/{run}/retry")

    assert r.status_code == 200, r.text
    again = r.json()
    assert again["replaces"] == run and again["id"] != run and again["state"] == "running"
    listed = _listed(client)
    assert run not in listed, "the run read again is the new run's row now, not a second one"
    assert again["id"] in listed and listed[again["id"]]["failed_at"] is None
    lane_held.set()


def test_the_retry_action_on_a_workflow_run_says_how_it_is_run_again(client, db, test_package):
    from fichero_server.execution import jobs

    jobs.enqueue(db, "workflow", "thread-x", started_by="owner")
    row = db.execute_fetchone("SELECT id FROM jobs WHERE subject = 'thread-x'")[0]
    db.execute("UPDATE jobs SET state = 'failed' WHERE id = ?", [row])
    try:
        registry.invoke(db, "job.retry", {"job_id": row}, ActionContext(actor="owner", is_bootstrap=True))
    except ValueError as exc:
        said = str(exc)
    else:
        raise AssertionError("the action does not run a workflow run again by itself")
    assert "handed in" not in said and "pages it did not do" in said, said
