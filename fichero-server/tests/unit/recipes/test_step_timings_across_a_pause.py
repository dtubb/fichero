"""`recipes-run.timing.page-time-is-the-page-job`, `recipes-run.timing.survives-pause-and-restart` and the Search part of
`recipes-run.timing.every-step-timed` (#6809). A step's seconds a page is the median of its pages' own jobs (the time each
page's job ran on the lane, never the time it stood in the fan-out); its pages done count every page whose job finished,
before a pause or a kill as well as after; its seconds and the run's are the time those jobs ran, so time paused or dead
is not counted. Measured on the review's run: 59 to 140 s a page said against 5.3 to 22.6 s a page done; "3 pages, 75.5 s"
for 5 pages and 44 s of work around a 31 s pause; Search with no timing at all."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from fichero_server.execution import jobs
from fichero_server.recipes import run_view, runner

T0 = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc)


def _row(db, job_id, kind, start_s, end_s, *, parent=None, subject="s", state="done", detail=None):
    jobs._ensure(db)
    db.execute("INSERT INTO jobs (id, kind, subject, state, attempts, started_by, created_at, started_at, finished_at, "
               "parent_id, detail) VALUES (?, ?, ?, ?, 0, 'workflow', ?, ?, ?, ?, ?)",
               [job_id, kind, subject, state, T0, T0 + timedelta(seconds=start_s),
                None if end_s is None else T0 + timedelta(seconds=end_s), parent, detail])


@pytest.fixture
def no_account(monkeypatch):
    import fichero_server.workflows.run_account as accounts

    async def _none(*_a, **_k):
        return None

    monkeypatch.setattr(accounts, "run_account", _none)


def _status(steps):
    return {"job_id": "run", "state": "done", "reason": None, "started_by": "person", "steps": steps}


def _find_lines_around_a_pause(db):
    """Five pages of 10 s each: three before a 31 s pause, two after; the step's run stood 81 s."""
    _row(db, "run", "run-a-recipe", 0, 81)
    _row(db, "lines", "workflow", 0, 81, parent="run")
    _row(db, "lines:segment", "workflow-step", 0, 81, parent="lines")
    for i, start in enumerate((0, 10, 20, 61, 71)):
        _row(db, f"page-{i}", "find-lines", start, start + 10, parent="lines:segment", subject=f"p{i}")


def test_pages_done_before_a_pause_count_and_the_pause_does_not(db, no_account):
    _find_lines_around_a_pause(db)
    out = asyncio.run(run_view.with_accounts(db, _status([
        {"steps": ["find-lines"], "card": "workflow", "state": "done", "child_id": "lines"}])))
    t = out["steps"][0]["timing"]
    assert (t.pages_done, t.seconds, t.seconds_per_page) == (5, 50.0, 10.0)
    assert out["seconds"] == 50.0


def test_a_page_time_is_its_job_not_its_wait_for_the_lane(db, no_account):
    """Three pages handed in at once to the one lane: each ran 5 s, the last waited 10 s for it."""
    _row(db, "run", "run-a-recipe", 0, 15)
    _row(db, "read", "workflow", 0, 15, parent="run")
    _row(db, "read:read", "workflow-step", 0, 15, parent="read")
    for i in range(3):
        _row(db, f"line-{i}", "read-a-line", i * 5, i * 5 + 5, parent="read:read", subject=f"p{i}")
    _row(db, "line-again", "read-a-line", 15, 15, parent="read:read", subject="p9", state="failed")
    out = asyncio.run(run_view.with_accounts(db, _status([
        {"steps": ["read-a-line"], "card": "workflow", "state": "done", "child_id": "read"}])))
    t = out["steps"][0]["timing"]
    assert (t.pages_done, t.seconds_per_page) == (3, 5.0)


def test_a_page_read_by_two_jobs_is_one_page_with_both_times(db, no_account):
    _row(db, "run", "run-a-recipe", 0, 9)
    _row(db, "read", "workflow", 0, 9, parent="run")
    _row(db, "read:read", "workflow-step", 0, 9, parent="read")
    _row(db, "find", "find-lines", 0, 3, parent="read:read", subject="p1")
    _row(db, "line", "read-a-line", 3, 9, parent="read:read", subject="p1")
    t = asyncio.run(run_view.with_accounts(db, _status([
        {"steps": ["read-a-line"], "card": "workflow", "state": "done", "child_id": "read"}])))["steps"][0]["timing"]
    assert (t.pages_done, t.seconds, t.seconds_per_page) == (1, 9.0, 9.0)


def test_search_is_timed_by_its_embed_jobs(db, no_account):
    _row(db, "run", "run-a-recipe", 0, 30)
    _row(db, "vec-1", "make-a-vector", 0, 4, parent="run", subject="batch:1",
         detail=json.dumps({"documents": ["a", "b"]}))
    _row(db, "vec-2", "make-a-vector", 20, 22, parent="run", subject="batch:2", detail=json.dumps({"documents": ["c"]}))
    out = asyncio.run(run_view.with_accounts(db, _status([
        {"steps": ["search"], "card": "embed", "state": "done", "child_id": None, "embed_jobs": ["vec-1", "vec-2"]}])))
    t = out["steps"][0]["timing"]
    assert (t.pages_done, t.seconds, t.seconds_per_page) == (3, 6.0, 2.0)


def test_the_search_step_keeps_its_embed_jobs(db, monkeypatch):
    from fichero_server.actions import page_text_cache

    _row(db, "run", "run-a-recipe", 0, None, state="running")
    _row(db, "vec-1", "make-a-vector", 0, 4, subject="batch:1", detail=json.dumps({"documents": ["a"]}))
    monkeypatch.setattr(page_text_cache, "queue_reembed_batches", lambda *_a, **_k: ["vec-1"])
    monkeypatch.setattr(runner, "search_embedded", lambda *_a: None)
    scratch: dict = {}
    assert runner._run_embed(db, ["a"], "run", "person", scratch) == (None, "done", None)
    assert scratch["embed_jobs"] == ["vec-1"]


def test_the_search_row_says_its_pages_in_words(db, monkeypatch):
    """The run's row while Search runs: "Making vectors for search: 2 of 3 pages", never "Running step make-a-vector:
    0 of 1 folder done" (a step id, `recipes-run.journey.progress-in-words`)."""
    from fichero_server.actions import page_text_cache

    _row(db, "run", "run-a-recipe", 0, None, state="running")
    _row(db, "vec-1", "make-a-vector", 0, 4, subject="batch:1", detail=json.dumps({"documents": ["a", "b"]}))
    _row(db, "vec-2", "make-a-vector", 4, None, subject="batch:2", state="running",
         detail=json.dumps({"documents": ["c"]}))
    monkeypatch.setattr(page_text_cache, "queue_reembed_batches", lambda *_a, **_k: ["vec-1", "vec-2"])
    monkeypatch.setattr(runner, "search_embedded", lambda *_a: None)
    said = []

    def _poll(_seconds):  # the lane finishes the second batch while the run waits
        said.append(jobs.read_job(db, "run")["reason"])
        db.execute("UPDATE jobs SET state = 'done', finished_at = ? WHERE id = 'vec-2'", [T0 + timedelta(seconds=6)])

    monkeypatch.setattr(runner.time, "sleep", _poll)
    assert runner._run_embed(db, ["a", "b", "c"], "run", "person", {}) == (None, "done", None)
    assert said == ["Making vectors for search: 2 of 3 pages"]
    assert runner.doing_words({"job": "make-a-vector", "card": "embed"}) == "Making vectors for search"


def test_leave_out_is_timed(db, monkeypatch, no_account):
    """Leave Out makes no job: its run on each batch is kept on the step (`spans`), and timed from it."""
    from fichero_server.recipes import leave_out

    clock = iter([T0, T0 + timedelta(seconds=4)])
    monkeypatch.setattr(leave_out, "utc_now", lambda: next(clock))
    monkeypatch.setattr(leave_out, "leave_out_pages", lambda *_a, **_k: {"pages": 2})
    scratch: dict = {}
    assert leave_out.run_step(db, ["a", "b"], "run", scratch) == (None, "done", None)
    spans = scratch["spans"] + [[(T0 + timedelta(seconds=30)).isoformat(), (T0 + timedelta(seconds=32)).isoformat(), 2]]
    out = asyncio.run(run_view.with_accounts(db, _status([
        {"steps": ["leave-out"], "card": "leave-out", "state": "done", "child_id": None, "spans": spans}])))
    t = out["steps"][0]["timing"]
    assert (t.pages_done, t.seconds, t.seconds_per_page) == (4, 6.0, 1.5)
    assert out["seconds"] == 6.0
