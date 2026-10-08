"""Stop on a recipe run's row stops the run (#5609, `activity.jobs-are-a-tree`: Stop on the run's row reaches the run
and its waiting pages).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. Seen on the demo engine (2026-10-08):
`POST /api/activity/jobs/{id}/cancel` on a `run-a-recipe` job answered {state: running} and a minute later the run
was running its next step; only cancelling its child workflow run stopped the child.

Through the public surface with the real lanes: a real `run-a-recipe` job on the recipes lane whose step is a real
workflow run, the network lane held by a real handed-in page so the step's pages wait for it, Stop through the
activity route, read back through the run's status, `GET /api/activity/jobs` and the tree. Only the model is a stub.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

import time

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from fichero_server.recipes import runner as recipes
from tests.unit.jobs.test_closed_mid_run_5608 import (  # noqa: F401
    _close_and_open,
    _first_child,
    _listed,
    _recipe,
    _recipe_steps,
    _waiting_pages,
    lane_held,
)
from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    _status,
    _tree,
    _wait_for,
    cloud,
    no_embedding_model,
    pages,
    workflow,
)

ENDED = ("done", "failed", "cancelled")


def _cancel(client, job_id) -> str:
    r = client.post(f"/api/activity/jobs/{job_id}/cancel")
    assert r.status_code == 200, r.text
    return r.json()["state"]


def _listed_ids(client) -> set[str]:
    return {j["id"] for j in client.get("/api/activity/jobs").json()["jobs"]}


def _children(db, recipe_job) -> list[str]:
    return [r[0] for r in db.execute_fetchall("SELECT id FROM jobs WHERE kind = 'workflow' AND parent_id = ?",
                                              [recipe_job])]


def test_activity_stop_reaches_the_run__stop_on_a_recipe_run_stops_its_step_and_every_step_after(
        client, test_package, workflow, pages, cloud, lane_held):
    """WHY (#5609): Stop on a running recipe run answered running and the run went on to its next step. Stop
    answers stopping (or cancelled), stops the step it is running through that step's own Stop (its pages waiting
    for the lane are withdrawn), runs no step after it, and the row ends cancelled saying who stopped it; the list
    and the tree agree."""
    db = db_manager.get_database(test_package)
    recipe = _recipe(db, workflow, pages, steps=("read", "names"))
    assert _wait_for(lambda: _first_child(db, recipe) is not None, 60)
    child = _first_child(db, recipe)
    assert _wait_for(lambda: _waiting_pages(db, child) == 3, 60)

    assert _cancel(client, recipe) in ("stopping", "cancelled")

    assert _wait_for(lambda: jobs.read_job(db, recipe)["state"] in ENDED, 30), jobs.read_job(db, recipe)
    row = jobs.read_job(db, recipe)
    assert row["state"] == "cancelled", row
    assert row["reason"].startswith("Stopped by you; 0 of 2 steps done"), row
    assert jobs.read_job(db, child)["state"] == "cancelled", "the running step's run was stopped"
    assert _status(client, child) == "cancelled"
    assert _waiting_pages(db, child) == 0, "its pages no longer wait for the lane"
    read, names = _recipe_steps(db, recipe)
    assert (read["state"], read["child_id"], read["why"]) == ("cancelled", child, "Stopped by you")
    assert (names["state"], names["why"]) == ("not run", recipes.STOPPED_BEFORE)
    assert [s["state"] for s in recipes.status(db, recipe)["steps"]] == ["cancelled", "not run"]

    # The list shows work going on and failures; a stopped run leaves it, and its tree says how it ended.
    assert recipe not in _listed_ids(client), "a stopped run is not listed as going on"
    tree = _tree(client, recipe)
    assert (tree["state"], tree["reason"]) == ("cancelled", row["reason"])

    lane_held.set()  # the lane frees: nothing of the stopped run runs
    time.sleep(1.5)
    assert _children(db, recipe) == [child], "no step after the stopped one ran"
    assert jobs.read_job(db, recipe)["state"] == "cancelled"
    assert _cancel(client, recipe) == "cancelled", "Stop again on a stopped run says so"


def test_activity_stop_reaches_the_run__a_waiting_recipe_run_is_cancelled_at_once(
        client, test_package, workflow, pages, cloud, lane_held):
    """WHY (#5609): a recipe run waiting its turn (recipe runs go one at a time) ends cancelled when stopped, and
    never starts."""
    db = db_manager.get_database(test_package)
    first = _recipe(db, workflow, pages)
    assert _wait_for(lambda: _first_child(db, first) is not None, 60)
    second = _recipe(db, workflow, pages)
    assert jobs.read_job(db, second)["state"] == "waiting"

    assert _cancel(client, second) == "cancelled"
    row = jobs.read_job(db, second)
    assert (row["state"], row["reason"]) == ("cancelled", "Stopped by you")

    assert _cancel(client, first) in ("stopping", "cancelled")
    assert _wait_for(lambda: jobs.read_job(db, first)["state"] in ENDED, 30)
    lane_held.set()
    time.sleep(1.0)
    assert _children(db, second) == [], "the stopped waiting run never started"


def test_activity_stop_reaches_the_run__an_engine_resumed_mid_stop_does_not_take_the_recipe_run_up_again(
        client, test_package, workflow, pages, cloud, lane_held, monkeypatch):
    """WHY (#5609): a run left running when the engine went away is taken up again on the next open ("Interrupted;
    carries on"). One stopped while its step wound down is not: it ends cancelled, stopped by you, and runs nothing
    more."""
    db = db_manager.get_database(test_package)
    recipe = _recipe(db, workflow, pages, steps=("read", "names"))
    assert _wait_for(lambda: _first_child(db, recipe) is not None, 60)
    child = _first_child(db, recipe)
    assert _wait_for(lambda: _waiting_pages(db, child) == 3, 60)
    # The recipe run looks at its Stop only after a long while: the project closes before the run winds down.
    monkeypatch.setattr(recipes, "_CHECK_POLL_SECONDS", 60.0)
    time.sleep(0.6)  # the run's current look (0.5 s) ends; its next one is the long one

    assert _cancel(client, recipe) == "stopping"
    row = jobs.read_job(db, recipe)
    assert (row["state"], row["reason"]) == ("running", jobs.STOPPING), row
    listed, tree = _listed(client, recipe), _tree(client, recipe)
    assert (listed["state"], listed["reason"]) == (tree["state"], tree["reason"]) == ("running", jobs.STOPPING)

    db = _close_and_open(test_package)

    row = jobs.read_job(db, recipe)
    assert row["state"] == "cancelled" and row["reason"].startswith("Stopped by you"), row
    lane_held.set()
    time.sleep(1.5)
    assert _children(db, recipe) == [child], "the stopped run was not taken up again"
    assert jobs.read_job(db, recipe)["state"] == "cancelled"
    assert recipe not in _listed_ids(client) and _tree(client, recipe)["state"] == "cancelled"


def test_activity_stop_reaches_the_run__a_run_left_stopping_when_the_engine_went_away_is_not_resumed(
        client, test_package, monkeypatch):
    """WHY (#5609): an engine that went away (quit, crash) while a stopped recipe run wound down left its row
    running, saying it is stopping; the next open took every running row up again ("Interrupted; carries on"). It
    ends stopped instead; a running row not stopped still carries on."""
    recipes.register_job_kinds()
    db = db_manager.get_database(test_package)
    stopped = jobs._insert(db, recipes.KIND, "recipe:stopped", None, "owner")
    going = jobs._insert(db, recipes.KIND, "recipe:going", None, "owner")
    db.execute("UPDATE jobs SET state = 'running', reason = ? WHERE id = ?", [jobs.STOPPING, stopped])
    db.execute("UPDATE jobs SET state = 'running', reason = 'Running step read' WHERE id = ?", [going])
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)  # nothing is taken up while the open is read

    jobs.resume(db)

    assert (jobs.read_job(db, stopped)["state"], jobs.read_job(db, stopped)["reason"]) == \
        ("cancelled", "Stopped by you")
    assert (jobs.read_job(db, going)["state"], jobs.read_job(db, going)["reason"]) == \
        ("waiting", "Interrupted; carries on")
    jobs.cancel_waiting(db, going)
