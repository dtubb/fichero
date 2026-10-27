"""While a run goes, the run's status and Activity's recipe-run node never hold the event loop: every database read of a
poll runs on a worker thread (`recipes-run.engine.answers-while-a-run-goes`, #6178)."""
from __future__ import annotations

import asyncio
import time

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime
from fichero_server.recipes import run_view, runner


def _status(job_id="r1"):
    return {"job_id": job_id, "state": "running", "reason": None, "steps": [], "skipped": [], "started_by": "owner"}


def _slow(value):
    def call(*_a, **_k):
        time.sleep(1.5)  # waiting on the transaction gate behind a run's write
        return value

    return call


def _loop_turn_during(blocking_call) -> float:
    """How long a 0.2 s sleep beside `blocking_call` takes (a poll beside it): over 1 s, the call held the loop."""
    async def go() -> float:
        work = asyncio.ensure_future(blocking_call())
        started = time.monotonic()
        await asyncio.sleep(0.2)
        took = time.monotonic() - started
        await work
        return took

    return asyncio.run(go())


def test_the_run_status_reads_the_run_off_the_loop(monkeypatch):
    from fichero_server.api.routes.system import recipes

    monkeypatch.setattr(runner, "status", _slow(_status()))
    monkeypatch.setattr(kraken_runtime, "pages_at_once_and_why", lambda person: (1, None))

    assert _loop_turn_during(lambda: recipes.recipe_run_status("r1", db=None)) < 1.0


def test_the_list_of_runs_reads_off_the_loop(monkeypatch):
    from fichero_server.api.routes.system import recipes

    monkeypatch.setattr(runner, "runs", _slow([_status()]))
    monkeypatch.setattr(kraken_runtime, "pages_at_once_and_why", lambda person: (1, None))

    assert _loop_turn_during(lambda: recipes.recipe_runs(db=None)) < 1.0


def test_the_gate_reading_of_a_running_run_is_off_the_loop(monkeypatch):
    monkeypatch.setattr(kraken_runtime, "pages_at_once_and_why", _slow((2, None)))  # the memory and paging probes

    assert _loop_turn_during(lambda: run_view.with_accounts(None, _status())) < 1.0


def test_activitys_recipe_run_node_reads_its_row_off_the_loop(monkeypatch):
    from fichero_server.api.routes.system import activity

    monkeypatch.setattr(runner, "status", lambda db, job_id: _status(job_id))
    monkeypatch.setattr(kraken_runtime, "pages_at_once_and_why", lambda person: (1, None))
    monkeypatch.setattr(jobs, "state_and_reason", _slow(("running", None)))

    assert _loop_turn_during(lambda: activity._recipe_state(None, "r1")) < 1.0


def test_the_project_setup_plans_its_redo_steps_off_the_loop(monkeypatch, tmp_path):
    """GET /api/recipes/project plans the started recipe's runs for the folder menu (#6170): off the loop too."""
    from fichero_server.api.routes.system import recipes
    from fichero_server.recipes import project, start

    recipe = {"id": "t/run", "steps": [], "gaps": [], "problems": []}
    monkeypatch.setattr(recipes, "_library", lambda db: tmp_path)
    monkeypatch.setattr(recipes, "read_project_setup", lambda library: {"answers": {}, "recipe": recipe})
    monkeypatch.setattr(project, "read_start", lambda library: {"started_at": "now"})
    monkeypatch.setattr(start, "plan_start", _slow({"workflows": []}))

    assert _loop_turn_during(lambda: recipes.get_project_setup(db=None)) < 1.0


def _a_run(db, state):
    """A recipe run, queued, or running a workflow step whose run has a page waiting (the poll reads the step's child,
    its account and what its page waits for: b20)."""
    import json

    run_id = jobs.enqueue(db, runner.KIND, "project", started_by="owner")
    if state == "running":
        card = {"steps": [], "card": "workflow"}
        db.execute("UPDATE jobs SET state = 'running', detail = ? WHERE id = ?",
                   [json.dumps({"runs": [card], "steps": [{**card, "state": "running", "child_id": None}]}), run_id])
        step = jobs._insert(db, "workflow", "project", None, "owner")
        page = jobs._insert(db, "read-a-page", "page-1", None, "owner")
        db.execute("UPDATE jobs SET state = 'running', parent_id = ? WHERE id = ?", [run_id, step])
        db.execute("UPDATE jobs SET parent_id = ? WHERE id = ?", [step, page])
    return run_id


def _under_a_held_writer(db, run_id, read):
    """`read()` while another thread's transaction holds a write to the run's row for 3 s: (its answer, seconds)."""
    import threading

    writing, done = threading.Event(), threading.Event()

    def hold_the_writer():
        with db.transaction():
            db.execute("UPDATE jobs SET reason = 'writing' WHERE id = ?", [run_id])
            writing.set()
            done.wait(3)

    writer = threading.Thread(target=hold_the_writer)
    writer.start()
    try:
        assert writing.wait(5)
        started = time.monotonic()
        answer = read()
        return answer, time.monotonic() - started
    finally:
        done.set()
        writer.join()


@pytest.mark.parametrize("state", ["waiting", "running"])
def test_the_run_status_answers_under_a_held_writer(db, state):
    """A poll under a held writer answers with what was committed rather than waiting for the writer (#6178): a run's
    write holds the transaction for 3 s, and the run's status beside it answers within 1 s."""
    run_id = _a_run(db, state)
    status, took = _under_a_held_writer(db, run_id, lambda: runner.status(db, run_id))
    assert took < 1.0, took
    assert status["reason"] != "writing", status  # what was committed, not the held write


@pytest.mark.parametrize("state", ["waiting", "running"])
def test_activitys_job_tree_answers_under_a_held_writer(db, state):
    from fichero_server.api.routes.system import activity

    run_id = _a_run(db, state)
    tree, took = _under_a_held_writer(db, run_id, lambda: asyncio.run(activity.get_job_tree(run_id, depth=1, db=db)))
    assert took < 1.0, took
    assert tree.reason != "writing", tree



@pytest.mark.parametrize("sql", [
    "UPDATE jobs SET reason = 'recovered' WHERE id = ? RETURNING id",
    "WITH stale AS (SELECT id FROM jobs WHERE id = ?) UPDATE jobs SET reason = 'recovered' "
    "WHERE id IN (SELECT id FROM stale) RETURNING id",
])
def test_a_write_that_returns_rows_still_waits_for_the_writer(db, sql):
    """Committed reads are opted into by a known read, never guessed from a statement's first word: a write that
    returns rows (stale-run recovery's UPDATE ... RETURNING, a WITH ... UPDATE) inside a poll's committed reads keeps
    the transaction gate, never the READ cursor beside a held writer (#6178, review b19)."""
    from fichero_server.db import committed

    run_id = jobs.enqueue(db, runner.KIND, "project", started_by="owner")

    def write():
        with committed(db):
            return db.execute_fetchall(sql, [run_id])

    _rows, took = _under_a_held_writer(db, run_id, write)
    assert took > 2.0, took


@pytest.mark.parametrize("state", ["waiting", "running"])
def test_activitys_list_answers_under_a_held_writer(db, state):
    from fichero_server.api.routes.system import activity

    run_id = _a_run(db, state)
    _listed, took = _under_a_held_writer(db, run_id, lambda: asyncio.run(activity.list_background_jobs(db=db)))
    assert took < 1.0, took
