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


def _step(done: int, total: int):
    return {"account": SimpleNamespace(pages_done=done, pages_total=total)}


def test_pages_done_sum_across_stages_and_do_not_reset_when_the_next_stage_starts():
    read = {"steps": [_step(92, 92)]}
    assert activity._recipe_pages_done(read) == 92
    names = {"steps": [_step(92, 92), _step(0, 92)]}  # Names has just started: nothing resets
    assert activity._recipe_pages_done(names) == 92 and activity._recipe_pages_in_all(names, 92) == 184


def test_a_stage_with_no_account_counts_nothing_and_the_runs_own_pages_stand():
    status = {"steps": [{"account": None}, {}, _step(3, 10)]}
    assert activity._recipe_pages_done(status) == 3
    assert activity._recipe_pages_in_all(status, 92) == 92
