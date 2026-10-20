"""Fable runner review P2/P3 (2026-10-19): #7 resume does not word a batch like a page, #20 a batch is listed once, #21 a lane
thread that dies wakes the lane again, #8/#14 a job ends on the connection the project has NOW, #15 the stale-run sweep runs on
the engine's background loop."""
from __future__ import annotations

import ast
from pathlib import Path

from fichero_server.execution import jobs

JOBS_SOURCE = Path(jobs.__file__).read_text()


def _row(db, job_id, kind, state, subject="s"):
    jobs._record(db, job_id, kind=kind, subject=subject, parent_id=None, state=state, reason=None, name=None)


def test_resume_does_not_word_a_batch_row_like_a_page(db):
    """#7: a batch running when the engine was killed read "Its workflow run stopped before this page was done"."""
    jobs._ensure(db)
    _row(db, "b1", "batch", "running")
    jobs.resume(db)
    state, reason = db.execute_fetchone("SELECT state, reason FROM jobs WHERE id = 'b1'")
    assert state == "cancelled" and "batch" in reason and "page" not in reason


def test_a_batch_is_listed_once_not_as_its_record_and_its_row(db):
    """#20."""
    jobs._ensure(db)
    _row(db, "b2", "batch", "running")
    assert [r for r in jobs.snapshot(db) if r["id"] == "b2"] == []


def test_a_lane_thread_that_dies_on_an_error_wakes_the_lane_again():
    """#21: the waiting jobs sat until the next enqueue."""
    loop = next(n for n in ast.walk(ast.parse(JOBS_SOURCE)) if isinstance(n, ast.FunctionDef) and n.name == "_loop")
    handlers = [h for h in ast.walk(loop) if isinstance(h, ast.ExceptHandler)]
    assert any("Timer" in ast.unparse(h) and "wake" in ast.unparse(h) for h in handlers)


def test_a_job_ends_on_the_connection_the_project_has_now_not_only_the_one_it_started_on():
    """#8, #14: `open_database(key) is db` skipped the end-of-job write after a reopen: the row stayed running for good, and a
    deferral counted as an attempt."""
    assert "open_database(key) is db" not in JOBS_SOURCE


def test_the_stale_run_sweep_is_scheduled_on_the_background_loop(tmp_path, monkeypatch):
    """#15."""
    from fichero_server.execution import runner
    from fichero_server.workflows import activity

    scheduled = []

    def record(coro):
        scheduled.append(coro)
        coro.close()

    monkeypatch.setattr(runner, "on_background_loop", record)
    path = str(tmp_path / "fresh.fichero" / "library.duckdb")
    try:
        activity.get_activity_tracker(path)  # no running loop here: the sweep used to be skipped
    finally:
        activity._activity_trackers.pop(path, None)
    assert len(scheduled) == 1
