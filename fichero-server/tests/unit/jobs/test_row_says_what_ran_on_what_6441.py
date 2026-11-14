"""Every row of the jobs list says what ran on what (#6441, `activity.pane.row-says-what-ran-on-what`).

Spec: docs/contributor_manual/specs/ui/activity-pane.md. WHY (owner 2026-11-13): Activity did not tell which files were
being worked on, at which step, by which model. The engine supplies the trail on the list row: the stages with each one's
state and counts, the pages the row runs over, the stage's model; the app adds nothing.
"""
from __future__ import annotations

import json

import pytest

from fichero_server.execution import jobs
from fichero_server.recipes import runner

THUMB = "t-ran-on-thumb"


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setitem(jobs.KINDS, THUMB, jobs.Kind(run=lambda db, subject: None, model=None, name="Make thumbnails"))
    jobs.load_kinds()
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(True)
    yield db
    jobs.set_paused(False)


def test_a_recipe_runs_row_carries_its_stages_and_the_pages_it_ran_over(held, client):
    detail = {"title": "Letters", "pages": 120,
              "runs": [{"steps": ["read-a-page"], "card": "workflow", "job": "read-a-page", "model": "qwen2-vl"},
                       {"steps": ["find-names-tag-words"], "card": "names", "job": "find-names-tag-words"}],
              "steps": [{"steps": ["read-a-page"], "card": "workflow", "state": "done", "child_id": None},
                        {"steps": ["find-names-tag-words"], "card": "names", "state": "failed", "child_id": None,
                         "why": "no model"}]}
    run = jobs.enqueue(held, runner.KIND, "project", started_by="owner", detail=json.dumps(detail))
    held.execute("UPDATE jobs SET state = 'failed', reason = 'no model', finished_at = now() WHERE id = ?", [run])

    row = {j["id"]: j for j in client.get("/api/activity/jobs").json()["jobs"]}[run]

    assert row["name"] == "Run the recipe: Letters"
    assert row["ran_on"] == {"kind": "pages", "count": 120, "name": None}
    stages = row["stages"]
    assert [(s["title"], s["state"]) for s in stages] == [("Read", "done"), ("Names", "failed")], stages
    # Cost (`activity.pane.cost-per-row-and-totals`): the keys are on every row; nothing priced here reads null, never "$0".
    assert row["cost_usd"] is None and row["cost_estimate_usd"] is None


def test_the_estimate_is_the_running_stages_pace_over_its_pages_left():
    from fichero_server.api.routes.system.activity import StageCount, _cost_estimate

    running = [StageCount(stage="read", title="Read", state="running", done=20, total=120, failed=0)]
    assert _cost_estimate(0.40, running, "running") == 2.0, "20 pages cost $0.40: 100 more cost about $2.00"
    assert _cost_estimate(0.40, running, "failed") is None, "an ended run has no estimate"
    assert _cost_estimate(None, running, "running") is None, "nothing priced yet: no estimate"
    assert _cost_estimate(0.40, [StageCount(stage="read", title="Read", state="done", done=120, total=120, failed=0)],
                          "running") is None, "no stage running: nothing to estimate"


def test_a_group_row_says_how_many_pages_it_stands_for(held, client):
    for i in range(12):
        jobs.enqueue(held, THUMB, f"page-{i}")

    rows = client.get("/api/activity/jobs").json()["jobs"]
    group = next(j for j in rows if j["id"] == f"waiting:{THUMB}")

    assert group["ran_on"]["kind"] == "pages" and group["ran_on"]["count"] == 12
    assert group["stages"] is None, "a kind's group has no recipe stages"
