"""Pause reaches a recipe run and its step, and a paused step is waited for, not failed (#5933,
`activity.recipe-run.pause-reaches-its-step`; Fable runner review 2 HIGH 2, ## 652 LOW 1).

Before: `run-a-recipe` had no pause, so Pause on a running recipe row answered `running` and did nothing; and a step whose run
was paused read as FAILED ("the engine stopped while this was running; try it again"), so the recipe moved on with the pages
unread.
"""
# ruff: noqa: F811 -- fixtures
from __future__ import annotations

import asyncio

import pytest

from fichero_server.execution import jobs
from fichero_server.execution.cancellation import clear_pause, pause_requested
from fichero_server.recipes import runner


def _running_recipe_with_a_step_run(db):
    runner.register_job_kinds()
    recipe = jobs.enqueue(db, runner.KIND, "pause-test")
    child = jobs.enqueue(db, "workflow", "thread-step-1")
    jobs.set_parent(db, child, recipe)
    db.execute("UPDATE jobs SET state = 'running' WHERE id IN (?, ?)", [recipe, child])
    return recipe, child


def test_pause_on_a_running_recipe_row_pauses_the_recipe_and_its_step_run_and_says_so(db):
    recipe, child = _running_recipe_with_a_step_run(db)
    try:
        state = jobs.pause_job(db, recipe, True)
        assert state == "running"  # it pauses at its next step: the row says so, not silence
        assert pause_requested(recipe) and pause_requested(child), "the recipe and the step's run are both asked to pause"
        assert jobs.read_job(db, recipe)["reason"] == jobs.PAUSING
    finally:
        clear_pause(recipe)
        clear_pause(child)


def test_resume_on_the_recipe_row_lets_it_go_on_and_resumes_the_step_run(db, monkeypatch):
    recipe, child = _running_recipe_with_a_step_run(db)
    resumed: list[str] = []
    monkeypatch.setattr(runner, "_resume_step_run", lambda database, thread: resumed.append(thread))
    jobs.pause_job(db, recipe, True)
    db.execute("UPDATE jobs SET state = 'paused' WHERE id = ?", [child])  # the step's run has reached its pause
    state = jobs.pause_job(db, recipe, False)
    assert state == "running"
    assert not pause_requested(recipe), "the recipe's pause is cleared"
    assert resumed == [child], "the step's paused run is resumed from its checkpoint"
    clear_pause(child)


def test_a_paused_step_run_is_waited_for_never_failed(monkeypatch):
    from fichero_server.api.routes.workflow import chains

    answers = iter([("paused", None), ("paused", None), ("completed", None)])
    monkeypatch.setattr(chains, "_step_run_outcome", lambda thread: next(answers))
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(runner, "_stop_asked", lambda job: False)
    assert runner._settled_outcome("thread-1", "recipe-1") == ("completed", None)


def test_a_stop_on_the_recipe_ends_the_wait_for_a_paused_step(monkeypatch):
    from fichero_server.api.routes.workflow import chains

    monkeypatch.setattr(chains, "_step_run_outcome", lambda thread: ("paused", None))
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(runner, "_stop_asked", lambda job: True)
    assert runner._settled_outcome("thread-1", "recipe-1")[0] == "paused"  # the caller's Stop turns it into "Stopped by you"


def test_a_joined_run_that_pauses_is_waited_for_too(monkeypatch):
    from fichero_server.api.routes.workflow import chains
    from fichero_server.execution import runner as engine_runner

    answers = iter([("running", None), ("paused", None), ("running", None), ("completed", None), ("completed", None)])
    monkeypatch.setattr(chains, "_step_run_outcome", lambda thread: next(answers))
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(runner, "_stop_asked", lambda job: False)
    monkeypatch.setattr(engine_runner, "_get_workflow_state", lambda thread: {"workflow_name": "Read"})
    assert runner._join_live_run("live-1", "recipe-1")[1] == "done"


@pytest.mark.asyncio
async def test_pages_of_a_child_run_count_under_the_top_run(tmp_path):
    """## 652 LOW 1: a sub-workflow's fan-out keys its pages by the child's task_id; the runner asks by the run's own id."""
    from fichero_server.workflows import builder

    token = builder.TOP_RUN.set("parent-run")
    try:
        builder._count_page_reading("child-run", +1)
        assert builder.pages_reading("parent-run") == 1
        assert builder.pages_reading("child-run") == 0
        builder._count_page_reading("child-run", -1)
        assert builder.pages_reading("parent-run") == 0
    finally:
        builder.TOP_RUN.reset(token)
