"""A recipe run's row (#5870, #5871).

`source.recipe.status-names-its-own-child`: a running step that makes no job shows its own state, never another row's.
`source.recipe.row-progress-across-stages`: the row's pages count across every stage and reset at none."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fichero_server.api.routes.system import activity
from fichero_server.execution import jobs
from fichero_server.recipes import runner


def _run_row(steps: list[dict]) -> dict:
    return {"id": "run1", "kind": runner.KIND, "state": "running", "reason": None, "started_by": None,
            "detail": json.dumps({"runs": [{"card": s["card"], "steps": [], "job": None} for s in steps], "steps": steps})}


def _status(monkeypatch, steps: list[dict]) -> dict:
    row = _run_row(steps)
    monkeypatch.setattr(jobs, "read_job", lambda _db, jid: row if jid == "run1" else {"state": "running", "reason": None})
    monkeypatch.setattr(jobs, "running_child", lambda _db, _jid: "someone-elses-row")
    monkeypatch.setattr(jobs, "find_jobs", lambda *a, **k: [])
    return runner.status(None, "run1")


@pytest.mark.parametrize("card", ["regions", "prepare", "embed", "table", "publish"])
def test_a_running_step_that_makes_no_job_does_not_borrow_the_runs_newest_row(monkeypatch, card):
    got = _status(monkeypatch, [{"card": card, "steps": [], "state": "running", "child_id": None}])
    step = got["steps"][0]
    assert step["child_id"] is None and step["state"] == "running"


@pytest.mark.parametrize("card", ["workflow", "check", "find-documents", "entries"])
def test_a_step_that_makes_a_job_points_at_it_while_it_runs(monkeypatch, card):
    got = _status(monkeypatch, [{"card": card, "steps": [], "state": "running", "child_id": None}])
    assert got["steps"][0]["child_id"] == "someone-elses-row"  # its newest unfinished job is its own (#5654)


def _step(done: int, total: int, card: str = "workflow"):
    return {"card": card, "account": SimpleNamespace(pages_done=done, pages_total=total)}


def test_a_page_counts_once_across_stages_never_the_stages_added_up():
    names = {"steps": [_step(92, 92), _step(0, 92)]}  # Reading done, Names just started: 0 of 92, not 92 of 184
    assert activity._recipe_pages_done(names) == 0 and activity._recipe_pages_in_all(names, 92) == 92
    three = {"steps": [_step(92, 92), _step(46, 92), _step(36, 92)]}
    assert activity._recipe_pages_done(three) == 36 and activity._recipe_pages_in_all(three, 92) == 92  # "36 of 92"


def test_a_stage_not_started_holds_the_row_at_zero_and_a_finished_run_reads_all():
    waiting = {"steps": [_step(92, 92), {"card": "workflow", "account": None}]}
    assert activity._recipe_pages_done(waiting) == 0
    assert activity._recipe_pages_done({"steps": [_step(92, 92), _step(92, 92)]}) == 92
    assert activity._recipe_pages_done({"steps": []}) == 0


def test_a_step_with_no_workflow_account_does_not_hold_the_row_back():
    status = {"steps": [_step(10, 92), {"card": "embed", "account": None}]}
    assert activity._recipe_pages_done(status) == 10 and activity._recipe_pages_in_all(status, 0) == 92
