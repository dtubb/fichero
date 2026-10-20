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


def test_a_regions_step_does_not_take_a_downloads_state_and_reason(db):
    step = runner.status(db, _run_with(db, "regions"))["steps"][0]
    assert step["state"] == "running" and not step.get("child_id")
    assert "network" not in (step.get("why") or "")


def test_a_workflow_step_still_points_at_its_running_job(db):
    run = _run_with(db, "workflow")
    child = jobs._insert(db, "workflow-step", "w", None, "owner")
    db.execute("UPDATE jobs SET state = 'running', parent_id = ? WHERE id = ?", [run, child])
    assert runner.status(db, run)["steps"][0]["child_id"] == child
