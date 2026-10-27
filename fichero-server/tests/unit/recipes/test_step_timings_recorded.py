"""`recipes-run.timing.per-step-recorded` (#6215): each step of a recipe run carries started, ended, seconds, pages
done and seconds a page (the median of its pages' own times), the run its total, and the summary names the slowest
step. All read from rows (the jobs table, the workflow run's stored timeline), so the figures survive a restart."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fichero_server.execution import jobs
from fichero_server.recipes import run_view

T0 = datetime(2026, 10, 26, 22, 0, tzinfo=timezone.utc)


def _file(doc, ms, node="read", status="success"):
    return {"type": "file", "node_id": node, "document_id": doc, "file_path": f"/{doc}.png", "status": status,
            "started_at": T0.isoformat(), "running_at": T0.isoformat(), "duration_ms": ms}


def _row(db, job_id, start_s, end_s):
    jobs._ensure(db)
    db.execute("INSERT INTO jobs (id, kind, subject, state, attempts, started_by, created_at, started_at, finished_at) "
               "VALUES (?, 'workflow', 's', 'done', 0, 'workflow', ?, ?, ?)",
               [job_id, T0, T0 + timedelta(seconds=start_s), None if end_s is None else T0 + timedelta(seconds=end_s)])


def test_a_page_time_is_its_own_summed_over_nodes_and_the_median_is_used():
    timeline = {"steps": [_file("a", 2000), _file("a", 1000, node="lines"), _file("b", 4000), _file("c", 60000),
                          _file("d", 9999, status="failed"), {"type": "node", "duration_ms": 999999}]}
    assert sorted(run_view.page_seconds(timeline)) == [3.0, 4.0, 60.0]
    t = run_view.step_timing(T0, T0 + timedelta(seconds=70), run_view.page_seconds(timeline), T0)
    assert (t.seconds, t.pages_done, t.seconds_per_page) == (70.0, 3, 4.0)  # median, not the mean (22.3)


def test_a_running_step_counts_to_now_and_a_step_not_started_has_no_seconds():
    assert run_view.step_timing(T0, None, [], T0 + timedelta(seconds=5)).seconds == 5.0
    assert run_view.step_timing(None, None, [], T0).seconds is None


def test_a_two_step_run_carries_each_steps_timing_and_the_same_after_a_restart(db, monkeypatch):
    _row(db, "run", 0, 100)
    _row(db, "thread-lines", 1, 31)
    _row(db, "thread-read", 31, 99)
    import json

    from fichero_server.db import activity_records as records
    import fichero_server.workflows.run_account as accounts

    for thread, files in (("thread-lines", [_file("a", 10000, "lines"), _file("b", 20000, "lines")]),
                          ("thread-read", [_file("a", 30000), _file("b", 36000), _file("c", 2000)])):
        db.execute(f"INSERT INTO {records.RUNS} (id, workflow_id, workflow_name, status, progress_timeline) "
                   "VALUES (?, 'w', 'w', 'completed', ?)", [thread, json.dumps({"steps": files})])

    async def _no_account(*_a, **_k):
        return None

    monkeypatch.setattr(accounts, "run_account", _no_account)

    def status():
        return {"job_id": "run", "state": "done", "reason": None, "started_by": "person", "steps": [
            {"steps": ["find-lines"], "card": "workflow", "state": "done", "child_id": "thread-lines"},
            {"steps": ["read-a-line"], "card": "workflow", "state": "done", "child_id": "thread-read"},
            {"steps": ["find-names-tag-words"], "card": "names", "state": "not run", "child_id": None}]}

    first = asyncio.run(run_view.with_accounts(db, status()))
    lines, read, names = first["steps"]
    assert first["seconds"] == 100.0
    assert (lines["timing"].seconds, lines["timing"].pages_done, lines["timing"].seconds_per_page) == (30.0, 2, 15.0)
    assert (read["timing"].seconds, read["timing"].pages_done, read["timing"].seconds_per_page) == (68.0, 3, 30.0)
    assert "timing" not in names

    again = asyncio.run(run_view.with_accounts(db, status()))  # a fresh read from the rows: nothing kept in memory
    assert [s.get("timing") for s in again["steps"]] == [s.get("timing") for s in first["steps"]]

    words = run_view.slowest_words([run_view.RecipeRunStep(**s) for s in first["steps"]])
    assert words == f"Slowest step: {run_view.RecipeRunStep(**read).title}: 30 s a page on 3 pages"


def test_a_step_with_no_pages_of_its_own_is_named_by_its_whole_time():
    steps = [run_view.RecipeRunStep(steps=["find-names-tag-words"], card="names", state="done",
                                    timing=run_view.StepTiming(seconds=12.5))]
    assert run_view.slowest_words(steps).endswith(": 12.5 s")
    assert run_view.slowest_words([]) is None
