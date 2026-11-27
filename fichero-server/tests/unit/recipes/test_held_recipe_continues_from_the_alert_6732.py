"""A recipe run whose step run the engine's stop cut off is held at the next open, and the launch alert's Continue on the
recipe's row resumes that step run from its checkpoint and lets the recipe go on (#6732; owner 2026-11-21: interrupted
runs resume from the launch alert). Before, the Continue resumed the step run but left the recipe's own row paused, so it
never adopted the step's outcome."""
# ruff: noqa: F811 -- fixtures
from __future__ import annotations

import asyncio
import json
import time

import pytest

from fichero_server.execution import jobs
from fichero_server.recipes import runner
from fichero_server.workflows import run_account
from tests.unit.api.test_routes_workflow_execution import _seed_run
from tests.unit.workflows.test_recovered_run_settles_documents import _write_checkpoint


@pytest.fixture(autouse=True)
def _lane_stays_asleep(monkeypatch):
    """The rows are set by hand; a woken lane would take the recipe row up, and the state asserted would be the lane's."""
    monkeypatch.setattr(jobs, "wake_lane", lambda db: None)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)


def _recipe_with_a_running_step_run(db, thread_id):
    from fichero_server.workflows.activity import get_activity_tracker

    get_activity_tracker(str(db.path))  # its own open's sweep passes before the run exists
    time.sleep(0.5)
    runner.register_job_kinds()
    recipe = jobs.enqueue(db, runner.KIND, "held-recipe")
    jobs.save_detail(db, recipe, json.dumps({"steps": [{"state": "running"}], "runs": [{"id": "read"}]}))
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [recipe])
    jobs._record(db, thread_id, kind="workflow", subject=thread_id, parent_id=recipe, state="running", reason=None, name=None)
    _seed_run(db, thread_id, status="running")
    asyncio.run(_write_checkpoint(str(db.path), thread_id, []))
    return recipe


def _open_again(db):
    run_account.mark_interrupted_runs(db)
    jobs.resume(db)


def test_continue_on_a_held_recipe_resumes_its_step_run_and_the_recipe_goes_to_waiting(db, monkeypatch):
    from fichero_server.api.routes.workflow_execution import core

    recipe = _recipe_with_a_running_step_run(db, "thread-held-step")
    _open_again(db)
    assert [row["id"] for row in jobs.stopped_at_quit(db)] == [recipe], "the alert names the recipe once, not its step run"

    resumed: list[str] = []

    async def resume_workflow(thread_id, *args, **kwargs):
        resumed.append(thread_id)

    monkeypatch.setattr(core, "resume_workflow", resume_workflow)
    assert jobs.continue_after_quit(db, [recipe]) == [recipe]
    deadline = time.monotonic() + 5
    while not resumed and time.monotonic() < deadline:
        time.sleep(0.05)
    assert resumed == ["thread-held-step"], "the held step run is resumed from its checkpoint, no new run started"
    assert jobs.read_job(db, recipe)["state"] == "waiting", "the recipe is let go to adopt its step run's outcome"


def test_a_step_run_that_cannot_resume_is_failed_so_the_recipe_does_not_park_for_ever(db, monkeypatch):
    from fichero_server.api.routes.workflow_execution import core
    from fichero_server.workflows.activity import get_activity_tracker

    recipe = _recipe_with_a_running_step_run(db, "thread-held-broken")
    _open_again(db)

    async def resume_workflow(thread_id, *args, **kwargs):
        raise RuntimeError("its checkpoint cannot be read")

    monkeypatch.setattr(core, "resume_workflow", resume_workflow)
    jobs.continue_after_quit(db, [recipe])
    tracker_store = get_activity_tracker(str(db.path)).store
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and asyncio.run(tracker_store.get_workflow_run("thread-held-broken")).status != "failed":
        time.sleep(0.05)
    run = asyncio.run(tracker_store.get_workflow_run("thread-held-broken"))
    assert run.status == "failed", run.status
    assert "its checkpoint cannot be read" in (run.error or "")
    assert jobs.read_job(db, "thread-held-broken")["state"] == "failed"
