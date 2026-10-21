"""Fable runner review P2/P3 (2026-10-19): #7 resume does not word a batch like a page, #20 a batch is listed once, #21 a lane
thread that dies wakes the lane again, #8/#14 a job ends on the connection the project has NOW, #15 the stale-run sweep runs on
the engine's background loop."""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

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
    """#20 (issue #5878)."""
    jobs._ensure(db)
    _row(db, "b2", "batch", "running")
    assert [r for r in jobs.snapshot(db) if r["id"] == "b2"] == []


@pytest.mark.parametrize("kind", jobs.RUN_KINDS)
@pytest.mark.parametrize("state", ["running", "waiting"])
def test_every_run_kind_is_listed_once_not_as_its_record_and_its_row(db, kind, state):
    """#20 (issue #5878): the snapshot hid workflow rows but showed batch ones; every run kind's record is its own row, so none
    is listed as a job beside it."""
    jobs._ensure(db)
    _row(db, f"r-{kind}-{state}", kind, state)
    _row(db, "control", "embed", "failed")  # a job that is not a run: this snapshot lists it, so an empty list proves nothing
    listed = [r["id"] for r in jobs.snapshot(db)]
    assert "control" in listed, listed
    assert f"r-{kind}-{state}" not in listed


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
    """#15 (issue #5873): a recipe step builds its tracker inside asyncio.run, which cancels what it scheduled when it returns."""
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



@pytest.mark.asyncio
async def test_a_page_waiting_for_the_lane_looks_less_often_the_longer_it_waits(monkeypatch):
    """#18: 500 waiting pages woke the run's loop 2,000 times a second."""
    seen = []
    real_wait = asyncio.wait

    async def recording_wait(fs, timeout=None, **k):
        seen.append(timeout)
        if len(seen) >= 6:
            raise RuntimeError("enough")
        return await real_wait(fs, timeout=0, **k)

    monkeypatch.setattr(jobs.asyncio, "wait", recording_wait)
    monkeypatch.setattr(jobs, "_stop_requested", lambda run_id: False)
    monkeypatch.setattr(jobs, "_still_open", lambda db: True)
    monkeypatch.setattr(jobs, "_pause_requested", lambda run_id: False)
    signal = asyncio.get_running_loop().create_future()
    with pytest.raises(RuntimeError):
        await jobs._wait_for_lane(None, None, signal, "run-x")
    assert seen == [0.25, 0.5, 1.0, 1.0, 1.0, 1.0]


def test_the_reason_is_written_before_the_lane_takes_a_familys_lock_to_release_it():
    """#19: the release takes the family's own lock, which a call in flight can hold; the row must not sit silent behind it."""
    run = next(n for n in ast.walk(ast.parse(JOBS_SOURCE)) if isinstance(n, ast.FunctionDef) and n.name == "_run")
    text = ast.unparse(run)
    assert text.index("let go of its models") < text.index("_RELEASE[_family(lane.loaded_model)]")


def test_an_embed_batch_that_times_out_while_memory_is_tight_is_deferred_not_failed(monkeypatch):
    """#23: a slow cold start under memory pressure failed the job and every queued page behind it."""
    from fichero_server.db import embed_process
    from fichero_server.execution import throttle

    class Conn:
        closed = False

        def send(self, _):
            pass

        def poll(self, _timeout):
            return False

        def close(self):
            self.closed = True

    class Process:
        def is_alive(self):
            return True

    embedder = embed_process.RemoteEmbedder.__new__(embed_process.RemoteEmbedder)
    embedder._lock = __import__("threading").Lock()
    embedder._conn, embedder._process, embedder._embed_timeout = Conn(), Process(), 0.0
    embedder.close = lambda: None  # the child is stopped; not under test
    monkeypatch.setattr(throttle, "memory_is_busy", lambda: True)
    with pytest.raises(throttle.MemoryShortError):
        embedder.embed(["a"])
    monkeypatch.setattr(throttle, "memory_is_busy", lambda: False)
    with pytest.raises(embed_process.EmbedderUnavailable):
        embedder.embed(["a"])
