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


def test_a_real_batch_refused_on_page_two_pauses_then_a_raised_cap_reads_only_page_two(db, jobs_run_by_the_test, monkeypatch):
    """The whole path through `_run_batch_steps` with a fake reader (no model): page 1 is read and noted; the cap refuses page 2;
    the run is deferred, not failed; raising the cap resumes it and the reader is asked for page 2 alone."""
    from fichero_server.models import DocType, Document, FileType, Status
    from fichero_server.recipes import done
    from tests.unit.recipes.test_a_page_is_noted_as_it_finishes_1134 import NAMES

    pages = []
    for name in ("a.jpg", "b.jpg"):
        doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, path=f"/p/{name}", status=Status.completed)
        db.save(doc)
        pages.append(doc.id)
    sentence = "this project's cloud spend is capped at $10.00 a month, of which $9.99 is spent"
    asked: list[list[str]] = []
    cap = {"month": 10.0, "project": None, "run": None}
    monkeypatch.setattr(spend, "caps_now", lambda library: dict(cap))
    monkeypatch.setattr(spend, "raised_since", lambda library, held: cap["month"] > (held.get("month") or 0) + 1e-9)

    def reader(db_, card_, documents, kinds, job_id, scratch, started_by, adopt=None):
        asked.append(list(documents))
        for page in documents:
            if cap["month"] <= 10.0 and page == pages[1]:
                return None, "failed", sentence  # the cap refuses page 2
            done.page_finished(db_, job_id, page)
        return "child-1", "done", None

    monkeypatch.setattr(runner, "_run_card", reader)
    job_id = runner.enqueue(db, {"runs": [NAMES], "skipped": []}, documents=pages, started_by="owner")
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    with pytest.raises(jobs.JobDeferred):
        runner.run(db, subject)  # paused at the cap: deferred, not failed
    detail = json.loads(jobs.read_job(db, job_id)["detail"])
    assert detail["paused_at_cap"]["step"] and detail["steps"][0]["ran_on"] == [pages[0]]  # page 1 done, noted on the run
    assert asked == [pages]
    with pytest.raises(jobs.JobDeferred):
        runner.run(db, subject)  # the cap is unchanged: still paused, the reader not asked again
    assert asked == [pages]
    cap["month"] = 20.0  # raised
    runner.run(db, subject)
    assert asked == [pages, [pages[1]]], "page 1 is never read again"
    assert "paused_at_cap" not in json.loads(jobs.read_job(db, job_id)["detail"])


def test_stop_here_ends_a_run_paused_at_the_cap_and_keeps_what_is_done(db, caps):
    """The third fix, "stop here and keep what is done": a run paused at the cap waits off the lane, so the run's own Stop ends it now."""
    job = _paused(db, caps)
    assert runner.request_cancel(db, job) == "cancelled"
    row = jobs.read_job(db, job)
    assert row["state"] == "cancelled"
    assert json.loads(row["detail"])["steps"] == CHECKPOINT["steps"]  # the finished pages stay noted on the run


def test_a_run_paused_at_the_cap_says_so_in_its_status_for_the_apps_offer(db, caps):
    job = _paused(db, caps)
    status = runner.status(db, job)
    assert status["stopped_at_cap"] is True and status["reason"].startswith("Paused at the cap: this project's cloud spend")
