"""Fable runner review #12: a running `regions` (or prepare, embed, table) step has no job of its own, so the status
pointed it at the run's newest unfinished row (a model download hung under the run) and copied that row's state and
reason onto the step (`source.recipe.run-status-is-activity`)."""
from __future__ import annotations

import json

from fichero_server.execution import jobs
from fichero_server.recipes import runner


def _run_with(db, card):
    jobs._ensure(db)
    run = jobs._insert(db, runner.KIND, "run", None, "owner")
    db.execute("UPDATE jobs SET state = 'running', detail = ? WHERE id = ?", [json.dumps({
        "runs": [{"steps": ["s"], "card": card, "job": "x"}],
        "steps": [{"steps": ["s"], "card": card, "state": "running", "child_id": None}]}), run])
    download = jobs._insert(db, "download-a-model", "m", None, "owner")
    db.execute("UPDATE jobs SET state = 'waiting', reason = 'Waiting for the network', parent_id = ? WHERE id = ?", [run, download])
    return run


import pytest


@pytest.mark.parametrize("card", ["regions", "prepare", "embed", "table"])  # the four cards that make no job of their own
def test_a_step_with_no_job_does_not_take_a_downloads_state_and_reason(db, card):
    step = runner.status(db, _run_with(db, card))["steps"][0]
    assert step["state"] == "running" and not step.get("child_id")
    assert "network" not in (step.get("why") or "")


def test_a_run_still_waiting_says_what_it_waits_for(db):
    """`source.recipe.run-status-is-activity`: "a run still waiting says what it waits for (recipe runs go one at a time)"."""
    jobs._ensure(db)
    ahead = jobs._insert(db, runner.KIND, "first", None, "owner")
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [ahead])
    waiting = jobs._insert(db, runner.KIND, "second", None, "owner")
    db.execute("UPDATE jobs SET state = 'waiting' WHERE id = ?", [waiting])
    reason = runner.status(db, waiting)["reason"]
    assert ahead in reason and "recipe runs go one at a time" in reason


def test_a_workflow_step_still_points_at_its_running_job(db):
    run = _run_with(db, "workflow")
    child = jobs._insert(db, "workflow-step", "w", None, "owner")
    db.execute("UPDATE jobs SET state = 'running', parent_id = ? WHERE id = ?", [run, child])
    assert runner.status(db, run)["steps"][0]["child_id"] == child
