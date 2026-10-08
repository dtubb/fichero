"""A project closed while a run's pages wait for a lane: the run ends interrupted, and a recipe run never waits on a
dead child (#5608, `compute.run.interrupted-on-close`).

Spec: docs/contributor_manual/specs/compute/jobs-and-fine-tuning.md. Seen on the demo engine (2026-10-08): the app
relaunched and the engine closed the project while a recipe run's reading step had 49 pages waiting for the lane.
The pages failed "The engine closed every project before this work ran" and their rows were cancelled, but the
run's own record and account said running for good (the open took it for a run still going) and the recipe run
waited on it for an hour after the project was open again.

Through the public surface with the real lanes: runs started with `POST /api/workflow-execution/execute` or by a
real `run-a-recipe` job on the recipes lane, the model lane held by a real handed-in page, the project closed and
opened through the database manager, read back through the run's status, `GET /api/activity/jobs` and the tree.
Only the model is a stub (a cloud vision model answering from memory).
"""
# ruff: noqa: F811 -- pytest fixtures imported from test_runs_are_jobs are named as test arguments
from __future__ import annotations

import json
import threading
import time

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from fichero_server.recipes import runner as recipes
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

CLOSED = "Interrupted: the project was closed at "


@pytest.fixture
def lane_held(monkeypatch, db):
    """The network lane (one slot here) held by a page of another run, as a long reading holds it; released by
    the test or at its end."""
    monkeypatch.setitem(jobs.LANES, "network", 1)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    release = threading.Event()
    held = jobs.submit(db, "read-a-page", "held", model="openai:gpt-5", fn=lambda: release.wait(60),
                       lane="network")
    assert _wait_for(lambda: jobs.read_job(db, held.job_id)["state"] == "running", 30)
    yield release
    release.set()


def _waiting_pages(db, under: str) -> int:
    return db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = 'read-a-page' AND state = 'waiting' "
                               "AND parent_id LIKE ?", [f"{under}%"])[0]


def _account(client, thread_id):
    r = client.get(f"/api/workflow-execution/threads/{thread_id}/status", params={"view": "summary"})
    assert r.status_code == 200, r.text
    return r.json()["account"]


def _listed(client, job_id):
    return {j["id"]: j for j in client.get("/api/activity/jobs").json()["jobs"]}[job_id]


def _close_and_open(test_package, every=False):
    if every:  # the engine closes every project (the app relaunched), and goes on
        db_manager.close_all()
    else:
        db_manager.close_database(test_package)
    return db_manager.get_database(test_package)


@pytest.mark.parametrize("every", [False, True], ids=["this-project-closed", "every-project-closed"])
def test_compute_run_interrupted_on_close__a_run_whose_pages_wait_for_a_lane_ends_interrupted(
        client, test_package, workflow, pages, cloud, lane_held, every):
    """WHY (#5608): closed while its pages waited for the lane, the run's record stayed running for good; on the
    next open it was taken for a run still going and never marked. It reads interrupted, with when the project was
    closed, in its status, its account, the list and the tree, and offers its pages not done."""
    from fichero_server.execution.runner import _running_workflows

    db = db_manager.get_database(test_package)
    run = _execute(client, workflow, pages)
    assert _wait_for(lambda: _waiting_pages(db, run) == 3, 60)

    db = _close_and_open(test_package, every)

    assert run not in _running_workflows, "a run its project's close stopped is not live"
    assert _status(client, run) == "failed"
    account = _account(client, run)
    assert account["state"] == "interrupted" and account["interrupted"] is True
    assert account["reason"].startswith(CLOSED) and account["reason"].endswith(", before this run finished")
    assert account["offer"]["label"] == "Read the 3 pages not done"
    tree = _tree(client, run)
    assert (tree["state"], tree["reason"]) == ("failed", account["reason"])
    listed = _listed(client, run)
    assert (listed["state"], listed["reason"]) == ("failed", account["reason"])
    assert listed["account"]["interrupted"] is True
    assert _waiting_pages(db, run) == 0, "no page of it waits for a lane any more"

    # The runner's own end after the close (its pages stopped) does not end the run otherwise.
    lane_held.set()
    time.sleep(1.0)
    assert _account(client, run)["reason"] == account["reason"]
    assert _tree(client, run)["state"] == "failed"


def _recipe(db, workflow, pages, steps=("read",)) -> str:
    """A real `run-a-recipe` job whose cards are the test's workflow, one card per step."""
    recipes.register_job_kinds()
    cards = [{"steps": [step], "card": "workflow", "workflow_id": workflow.id, "workflow": workflow.name,
              "provider_override": None, "model_override": None} for step in steps]
    return recipes.enqueue(db, {"runs": cards, "skipped": []}, documents=[p.id for p in pages], started_by="owner")


def _recipe_steps(db, job_id):
    return json.loads(jobs.read_job(db, job_id)["detail"] or "{}").get("steps") or []


def _first_child(db, recipe_job):
    row = db.execute_fetchone("SELECT id FROM jobs WHERE kind = 'workflow' AND parent_id = ?", [recipe_job])
    return row[0] if row else None


def test_compute_run_interrupted_on_close__the_recipe_run_carries_on_when_the_project_opens(
        client, test_package, workflow, pages, cloud, lane_held):
    """WHY (#5608): the recipe run waited on its closed step's run for an hour after the project was open again.
    Closed while its step's pages wait for the lane, the step's run ends interrupted; the recipe run is not failed
    by the close, and on the next open it carries on, its step reads the pages again in a new run, and it ends."""
    db = db_manager.get_database(test_package)
    recipe = _recipe(db, workflow, pages)
    assert _wait_for(lambda: _first_child(db, recipe) is not None, 60)
    child = _first_child(db, recipe)
    assert _wait_for(lambda: _waiting_pages(db, child) == 3, 60)

    db = _close_and_open(test_package)

    account = _account(client, child)
    assert account["state"] == "interrupted" and account["reason"].startswith(CLOSED)
    assert jobs.read_job(db, recipe)["state"] in ("waiting", "running"), jobs.read_job(db, recipe)

    lane_held.set()  # the lane frees: the recipe run carries on
    assert _wait_for(lambda: jobs.read_job(db, recipe)["state"] in ("done", "failed", "cancelled"), 120), \
        jobs.read_job(db, recipe)
    row = jobs.read_job(db, recipe)
    assert row["state"] == "done", row
    [step] = _recipe_steps(db, recipe)
    assert step["state"] == "done" and step["child_id"] != child
    assert _status(client, step["child_id"]) == "completed"
    assert _account(client, step["child_id"])["pages_done"] == 3
    assert _account(client, child)["state"] == "interrupted", "the closed run stays as it ended"


def test_a_recipe_run_never_waits_on_a_step_run_whose_row_has_ended(
        client, test_package, workflow, pages, cloud, lane_held, monkeypatch):
    """WHY (#5608): a recipe run waited on its step's run for good. Whatever ends a step's run (here its row is
    cancelled while its pages still wait for the lane), the recipe run stops waiting on it, says why, and does
    not run the steps after it on nothing."""
    monkeypatch.setattr(recipes, "_DEAD_CHILD_GRACE_SECONDS", 0.5)
    db = db_manager.get_database(test_package)
    recipe = _recipe(db, workflow, pages, steps=("read", "names"))
    assert _wait_for(lambda: _first_child(db, recipe) is not None, 60)
    child = _first_child(db, recipe)
    assert _wait_for(lambda: _waiting_pages(db, child) == 3, 60)

    db.execute("UPDATE jobs SET state = 'cancelled', reason = 'Ended elsewhere' WHERE id = ?", [child])

    assert _wait_for(lambda: jobs.read_job(db, recipe)["state"] in ("done", "failed", "cancelled"), 30), \
        jobs.read_job(db, recipe)
    row = jobs.read_job(db, recipe)
    assert row["state"] == "failed" and "Ended elsewhere" in row["reason"], row
    read, names = _recipe_steps(db, recipe)
    assert (read["state"], read["child_id"], read["why"]) == ("failed", child, "Ended elsewhere")
    assert names["state"] == "not run"
