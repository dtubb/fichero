"""`designer.budget.fix-during-the-run` (#6295): a step refused for a cap leaves the run paused at the cap, not failed; a raised cap
carries it on from its checkpoint (nothing read again); a lowered or unchanged cap never does."""
# ruff: noqa: F811 -- fixtures
from __future__ import annotations

import json

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import spend
from fichero_server.recipes import runner

CHECKPOINT = {"steps": [{"card": "x", "state": "done", "ran_on": ["p1", "p2"]}], "batches_done": 1, "batch_states": ["done"]}


@pytest.fixture(autouse=True)
def _lane_stays_asleep(monkeypatch):
    monkeypatch.setattr(jobs, "wake_lane", lambda db: None)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)


@pytest.fixture
def caps(monkeypatch):
    now = {"month": 10.0, "project": 50.0, "run": None}
    monkeypatch.setattr(spend, "caps_now", lambda library: dict(now))
    return now


def _run(db, detail=None):
    runner.register_job_kinds()
    job = jobs.enqueue(db, runner.KIND, "cap-test", detail=json.dumps(detail or dict(CHECKPOINT)))
    return job


def _paused(db, caps):
    job = _run(db)
    detail = json.loads(jobs.read_job(db, job)["detail"])
    with pytest.raises(jobs.JobDeferred):
        runner._pause_at_the_cap(db, job, detail, "Read", "this project's cloud spend is capped at $10.00 a month, of which $9.99 is spent")
    return job


def test_the_cap_sentences_are_told_from_other_refusals():
    assert spend.refused_for_cap("this run's cloud spend is capped at $1.00, of which $0.99 is spent")
    assert spend.refused_for_cap("this project's cloud spend is capped at $10.00 a month, of which $9.99 is spent")
    assert not spend.refused_for_cap("gpt-x has no listed price, so its cost cannot be held") and not spend.refused_for_cap(None)


def test_a_cap_refusal_pauses_the_run_and_keeps_its_checkpoint_and_says_why(db, caps):
    job = _paused(db, caps)
    row = jobs.read_job(db, job)
    detail = json.loads(row["detail"])
    assert row["reason"].startswith("Paused at the cap: this project's cloud spend is capped at $10.00")
    assert detail["paused_at_cap"]["step"] == "Read" and detail["paused_at_cap"]["caps"]["month"] == 10.0
    assert detail["steps"] == CHECKPOINT["steps"] and detail["batches_done"] == 1  # nothing lost, nothing to read again


def test_a_run_cap_that_was_dropped_is_not_a_raise_to_a_number(db, caps):
    job = _paused(db, caps)
    caps["run"] = 3.0  # no run cap -> a run cap of $3 is a limit, not a raise
    with pytest.raises(jobs.JobDeferred):
        runner._wait_for_a_raised_cap(db, job, jobs.read_job(db, job))


def test_an_unchanged_or_lowered_cap_never_resumes_it(db, caps):
    job = _paused(db, caps)
    for change in ({}, {"month": 5.0}, {"month": 5.0, "project": 20.0}):
        caps.update({"month": 10.0, "project": 50.0, **change})
        with pytest.raises(jobs.JobDeferred):
            runner._wait_for_a_raised_cap(db, job, jobs.read_job(db, job))
    assert "paused_at_cap" in json.loads(jobs.read_job(db, job)["detail"])


@pytest.mark.parametrize("raised", [{"month": 20.0}, {"project": None}, {"run": 3.0}])
def test_a_raised_cap_carries_on_from_the_checkpoint_without_rereading(db, caps, raised):
    caps["run"] = 2.0  # a run with its own cap; the raise is of whichever cap was refusing
    job = _paused(db, caps)
    caps.update(raised)
    runner._wait_for_a_raised_cap(db, job, jobs.read_job(db, job))  # no JobDeferred: the run goes on
    row = jobs.read_job(db, job)
    detail = json.loads(row["detail"])
    assert "paused_at_cap" not in detail and row["reason"] == "Carrying on: the cap was raised"
    assert detail["steps"] == CHECKPOINT["steps"] and detail["batches_done"] == 1  # the same pages are done; none is read again
