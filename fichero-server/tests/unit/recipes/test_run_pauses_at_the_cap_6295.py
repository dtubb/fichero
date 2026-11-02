"""`designer.budget.fix-during-the-run` (#6295), on the one cap-pause path (`spend._STOPPED_AT_CAP`): a call refused for a cap pauses
its step's run and the recipe parks on it; raising a cap resumes it by the one Resume (`pause_recipe`) from the run's checkpoint,
no page read again; a lowered or unchanged cap never does; Stop ends it now with the finished pages kept."""
# ruff: noqa: F811 -- fixtures
from __future__ import annotations

import json

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import spend
from fichero_server.recipes import runner

CHECKPOINT = {"steps": [{"card": "x", "state": "done", "ran_on": ["p1", "p2"]}], "batches_done": 1, "batch_states": ["done"]}
STOP = {"words": "Paused at the cloud spend cap: a call could cost up to $0.04 and ...", "needed_cap_usd": 10.04, "needed_project_cap_usd": None}


@pytest.fixture(autouse=True)
def _lane_stays_asleep(monkeypatch):
    monkeypatch.setattr(jobs, "wake_lane", lambda db: None)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    spend._STOPPED_AT_CAP.clear()
    yield
    spend._STOPPED_AT_CAP.clear()


@pytest.fixture
def caps(monkeypatch):
    now = {"month": 10.0, "project": 50.0, "run": None}
    monkeypatch.setattr(spend, "caps_now", lambda library: dict(now))
    return now


@pytest.fixture
def resumed(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(runner, "_resume_step_run", lambda database, thread, recipe=None: seen.append(thread))
    return seen


def _parked(db, caps, detail=None):
    """A recipe run waiting on its step's run, which the cap hold paused (the stop record carries the caps as they stood)."""
    runner.register_job_kinds()
    recipe = jobs.enqueue(db, runner.KIND, "cap-test", detail=json.dumps({**CHECKPOINT, **(detail or {})}))
    child = jobs.enqueue(db, "workflow", "thread-capped")
    jobs.set_parent(db, child, recipe)
    db.execute("UPDATE jobs SET state = 'paused' WHERE id = ?", [child])
    spend._STOPPED_AT_CAP[child] = {**STOP, "caps": spend.caps_now("lib")}
    row = json.loads(jobs.read_job(db, recipe)["detail"])
    row["awaiting"] = {"card": "x", "child": child}
    jobs.save_detail(db, recipe, json.dumps(row), reason="Paused with its run")
    return recipe, child


def test_a_stop_at_a_cap_records_the_caps_it_stopped_under(db, caps):
    _recipe, child = _parked(db, caps)
    assert spend.stopped_at_cap([child])["caps"] == {"month": 10.0, "project": 50.0, "run": None}


def test_only_a_cap_that_is_higher_than_it_was_counts_as_a_raise(db, caps):
    _recipe, child = _parked(db, caps)
    for change in ({}, {"month": 5.0}, {"month": 5.0, "project": 20.0}, {"run": 3.0}):  # none, lowered, lowered, no run cap -> a limit
        caps.update({"month": 10.0, "project": 50.0, "run": None, **change})
        assert spend.raised_cap_stops("lib") == []
    for change in ({"month": 20.0}, {"project": None}):
        caps.update({"month": 10.0, "project": 50.0, "run": None, **change})
        assert spend.raised_cap_stops("lib") == [child]


def test_an_unchanged_or_lowered_cap_resumes_nothing_and_a_raised_one_resumes_by_the_one_resume(db, caps, resumed):
    recipe, child = _parked(db, caps)
    caps["month"] = 5.0
    assert runner.resume_capped_runs(db) == [] and resumed == []
    caps["month"] = 20.0
    assert runner.resume_capped_runs(db) == [recipe]
    assert resumed == [child], "the step's paused run is resumed from its own checkpoint, as Resume does"
    assert spend.stopped_at_cap([child]) is None, "the stop is forgotten"
    row = json.loads(jobs.read_job(db, recipe)["detail"])
    assert row["steps"] == CHECKPOINT["steps"] and row["batches_done"] == 1  # nothing lost, nothing to read again


def test_a_run_paused_at_the_cap_says_so_in_its_status_for_the_apps_offer(db, caps):
    recipe, _child = _parked(db, caps)
    status = runner.status(db, recipe)
    assert status["stopped_at_cap"] is True and status["reason"] == STOP["words"]


def test_stop_here_ends_a_run_paused_at_the_cap_and_keeps_what_is_done(db, caps):
    recipe, _child = _parked(db, caps)
    assert runner.request_cancel(db, recipe) == "cancelled"
    row = jobs.read_job(db, recipe)
    assert row["state"] == "cancelled" and json.loads(row["detail"])["steps"] == CHECKPOINT["steps"]


def test_a_real_batch_paused_at_the_cap_on_page_two_resumes_on_a_raise_and_reads_page_two_only(db, jobs_run_by_the_test, caps, resumed,
                                                                                               monkeypatch):
    """Through `_run_batch_steps` with a fake reader (no model): page 1 is read and noted; the cap hold pauses the step's run on page 2
    and the recipe parks on it; an unchanged cap leaves it; a raise resumes it by the one Resume, and the step's run reads page 2 alone."""
    from fichero_server.models import DocType, Document, FileType, Status
    from fichero_server.recipes import done
    from tests.unit.recipes.test_a_page_is_noted_as_it_finishes_1134 import NAMES

    pages = []
    for name in ("a.jpg", "b.jpg"):
        doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, path=f"/p/{name}", status=Status.completed)
        db.save(doc)
        pages.append(doc.id)
    asked: list[list[str]] = []
    child_of: dict[str, str] = {}

    def reader(db_, card_, documents, kinds, job_id, scratch, started_by, adopt=None):
        asked.append(list(documents))
        if adopt:  # the step's run, resumed: it reads what was left
            for page in documents:
                done.page_finished(db_, job_id, page)
            return adopt, "done", None
        done.page_finished(db_, job_id, documents[0])  # page 1 read and noted
        child = jobs.enqueue(db_, "workflow", "thread-capped")  # the cap hold paused page 2's run
        jobs.set_parent(db_, child, job_id)
        db_.execute("UPDATE jobs SET state = 'paused' WHERE id = ?", [child])
        spend._STOPPED_AT_CAP[child] = {**STOP, "caps": spend.caps_now("lib")}
        child_of["id"] = child
        raise runner.ParkedOnStepRun(child)

    monkeypatch.setattr(runner, "_run_card", reader)
    job_id = runner.enqueue(db, {"runs": [NAMES], "skipped": []}, documents=pages, started_by="owner")
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    with pytest.raises(jobs.JobDeferred):
        runner.run(db, subject)  # the recipe parks: not failed
    child = child_of["id"]
    assert runner.status(db, job_id)["stopped_at_cap"] is True and asked == [pages]
    caps["month"] = 5.0
    assert runner.resume_capped_runs(db) == [] and resumed == []  # lowered: it stays paused
    caps["month"] = 20.0
    assert runner.resume_capped_runs(db) == [job_id] and resumed == [child]  # raised: the one Resume
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [child])  # the step's run goes on
    runner.run(db, subject)
    assert asked == [pages, [pages[1]]], "page 1 is never read again"
