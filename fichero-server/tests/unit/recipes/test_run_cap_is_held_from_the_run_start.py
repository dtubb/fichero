"""`designer.budget.run-cap` (#6295): a run's own cap is held from the moment the run starts, not while it waits in the queue, and it goes
when the run ends; a run that is deferred (paused, parked) keeps it. A queued run cancelled before it starts leaves none behind."""
# ruff: noqa: F811 -- fixtures
from __future__ import annotations

import json

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import spend
from fichero_server.recipes import runner


@pytest.fixture(autouse=True)
def _lane_stays_asleep(monkeypatch):
    monkeypatch.setattr(jobs, "wake_lane", lambda db: None)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)


def _queued(db, cap=2.0):
    runner.register_job_kinds()
    return runner.enqueue(db, {"runs": [], "skipped": []}, documents=[], started_by="owner", run_cap_usd=cap)


def test_a_queued_run_holds_no_cap_until_it_starts(db):
    job = _queued(db)
    library = str(runner._library(db))
    assert json.loads(jobs.read_job(db, job)["detail"])["run_cap_usd"] == 2.0, "the cap is kept on the run's row"
    assert spend.run_cap(library) is None, "a run that never starts leaves no cap holding later calls"


def test_the_run_holds_its_cap_while_it_runs_and_clears_it_at_the_end(db, monkeypatch):
    job = _queued(db)
    library = str(runner._library(db))
    seen = []
    monkeypatch.setattr(runner, "_run_the_plan", lambda database, job_id: seen.append(spend.run_cap(library)) or {})
    runner._run(db, job)
    assert [(c["job_id"], c["cap_usd"]) for c in seen] == [(job, 2.0)]
    assert spend.run_cap(library) is None


def test_a_run_with_no_run_cap_holds_none(db, monkeypatch):
    runner.register_job_kinds()
    job = runner.enqueue(db, {"runs": [], "skipped": []}, documents=[], started_by="owner")
    library = str(runner._library(db))
    seen = []
    monkeypatch.setattr(runner, "_run_the_plan", lambda database, job_id: seen.append(spend.run_cap(library)) or {})
    runner._run(db, job)
    assert seen == [None]


def test_a_deferred_run_keeps_its_cap_as_changed_and_its_baseline_when_it_comes_back(db, monkeypatch):
    job = _queued(db)
    library = str(runner._library(db))
    calls = []

    def plan(database, job_id):
        calls.append(spend.run_cap(library))
        if len(calls) == 1:
            spend.change_run_cap(library, 5.0)  # raised while it was paused
            raise jobs.JobDeferred("paused at the cap")
        return {}

    monkeypatch.setattr(runner, "_run_the_plan", plan)
    with pytest.raises(jobs.JobDeferred):
        runner._run(db, job)
    assert spend.run_cap(library)["cap_usd"] == 5.0, "a deferred run keeps its cap"
    baseline = spend.run_cap(library)["from_usd"]
    runner._run(db, job)
    assert (calls[1]["cap_usd"], calls[1]["from_usd"]) == (5.0, baseline), "the raised cap and the baseline carry over"
    assert spend.run_cap(library) is None

