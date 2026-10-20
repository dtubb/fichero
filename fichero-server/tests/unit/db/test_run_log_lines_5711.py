"""A run's log is its lines (#5711), tested to the spec: `source.store.one-managed-database`
(docs/contributor_manual/specs/source/source-model.md).

WHY: the node-boundary flush appended to one growing value, and DuckDB writes a new version of the whole value: on a
2 MB log every append wrote 2 MB to the write-ahead log, and every eighth or ninth flush paid a checkpoint on the
run's own path (the M4 parity: p95 7.5 -> 104.5 ms).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fichero_server.db import Database
from fichero_server.db import activity_records as records
from fichero_server.execution import jobs
from fichero_server.workflows import run_log_tidy
from fichero_server.workflows.activity_store import ActivityStore

TIMELINE = {"nodes": {}, "steps": []}


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def library(tmp_path):
    db = Database(tmp_path / "fichero.duckdb")
    yield db, ActivityStore(str(db.path))
    db.close()


def _wal_bytes(db) -> int:
    wal = Path(str(db.path) + ".wal")
    return wal.stat().st_size if wal.exists() else 0


def test_a_flush_writes_its_new_lines_not_the_whole_log(library):
    db, store = library
    _run(store.save_workflow_run("t1", "wf", "Read"))
    _run(store.flush_node_boundary("t1", progress_timeline=TIMELINE, log_text="x" * 2_000_000, replace=True))
    db.execute("CHECKPOINT")
    before = _wal_bytes(db)

    _run(store.flush_node_boundary("t1", progress_timeline=TIMELINE, log_text="one more line", replace=False))

    assert _wal_bytes(db) - before < 100_000, "an append writes its line, not the 2 MB log again"
    assert _run(store.get_workflow_run("t1")).execution_log == "x" * 2_000_000 + "\none more line"


def test_the_log_reads_as_it_always_did(library):
    _db, store = library
    _run(store.save_workflow_run("t1", "wf", "Read", execution_log="from the start"))
    assert _run(store.get_workflow_run("t1")).execution_log == "from the start"
    _run(store.flush_node_boundary("t1", progress_timeline=TIMELINE, log_text="a\nb", replace=True))
    _run(store.flush_node_boundary("t1", progress_timeline=TIMELINE, log_text="c", replace=False))
    _run(store.flush_node_boundary("t1", progress_timeline=TIMELINE, log_text="", replace=False))
    _run(store.flush_node_boundary("t1", progress_timeline=TIMELINE, log_text="d\n", replace=False))
    assert _run(store.get_workflow_run("t1")).execution_log == "a\nb\nc\nd\n"
    _run(store.update_workflow_run("t1", status="completed", execution_log="the whole log\nat the end"))
    assert _run(store.get_workflow_run("t1")).execution_log == "the whole log\nat the end"
    _run(store.save_workflow_run("t2", "wf", "Read"))
    assert _run(store.get_workflow_run("t2")).execution_log == ""


def test_a_deleted_run_says_so_at_the_end_of_its_log(library):
    _db, store = library
    _run(store.save_workflow_run("t1", "wf", "Read", execution_log="ran"))
    _run(store.update_workflow_run("t1", status="completed"))

    assert _run(store.delete_workflow_run("t1")) == 1
    assert _run(store.get_workflow_run("t1")).execution_log == "ran\nRun history deleted"


def _logs_as_before(db, logs: dict[str, str | None]) -> None:
    """Runs whose logs a library from before #5711 kept as one value each (one statement, however many)."""
    ids = list(logs)
    db.execute("INSERT INTO workflowrunrecords (id, workflow_id, workflow_name, status, started_at, execution_log) "
               "SELECT r, 'wf', 'Read', 'completed', TIMESTAMP '2026-10-01 12:00' + to_seconds(i), l "
               "FROM (SELECT unnest(?::VARCHAR[]) AS r, unnest(?::VARCHAR[]) AS l, unnest(range(?)) AS i)",
               [ids, [logs[i] for i in ids], len(ids)])
    db.execute("DELETE FROM librarysettings WHERE id = ?", [records.LOGS_AS_LINES_SETTING])


def _reads(store, ids) -> dict[str, str]:
    return {run_id: _run(store.get_workflow_run(run_id)).execution_log for run_id in ids}


def _tidy(db, monkeypatch, *, chunk: int, why=lambda **_: None) -> dict:
    monkeypatch.setattr(run_log_tidy, "CHUNK", chunk)
    monkeypatch.setattr("fichero_server.execution.throttle.why_wait", why)
    return run_log_tidy.run(db, run_log_tidy.SUBJECT)


def test_opening_a_library_with_10k_runs_from_before_moves_nothing_and_queues_the_tidy(tmp_path, monkeypatch):
    """The open does nothing that grows with the history: the logs stay values, read as before, and one background
    job is queued to move them (#5711: moving them at open took tens of seconds on a big library)."""
    from fichero_server.db.manager import db_manager
    from fichero_server.execution import jobs

    # A lane an earlier test left running would claim the queued job before this reads it ("waiting"): hold the queue (P0 red,
    # passed alone). `_flag_cache` is what every claim reads; monkeypatch puts it back.
    monkeypatch.setitem(jobs._flag_cache, jobs.PAUSE_SETTING_KEY, True)

    package = tmp_path / "Big.fichero"
    package.mkdir()
    db = Database(package / "fichero.duckdb")
    _logs_as_before(db, {f"r{n:05d}": f"run {n}\nline two\n" for n in range(10_000)})
    db.close()

    db = db_manager.get_database(package)
    try:
        assert db.execute_fetchone("SELECT count(*) FROM workflowrunloglines")[0] == 0
        assert db.execute_fetchone("SELECT count(*) FROM workflowrunrecords WHERE execution_log IS NOT NULL")[0] \
            == 10_000
        assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ? AND state = 'waiting'",
                                   [run_log_tidy.KIND])[0] == 1
        assert _run(ActivityStore(str(db.path)).get_workflow_run("r09999")).execution_log == "run 9999\nline two\n"
    finally:
        db_manager.close_database(package)


def test_a_mixed_library_reads_every_log_the_same_before_and_after_the_tidy(library, monkeypatch):
    db, store = library
    logs = {f"r{n:02d}": f"line 1 of {n}\nline 2 of {n}\n" for n in range(9)}
    logs |= {"empty": "", "none": None, "one": "only line", "blank lines": "\n\na\n\n"}
    _logs_as_before(db, logs)
    _run(store.save_workflow_run("new", "wf", "Read", execution_log="written as lines"))
    _run(store.flush_node_boundary("r00", progress_timeline=TIMELINE, log_text="after", replace=False))
    expected = {k: (v or "") for k, v in logs.items()} | {"new": "written as lines", "r00": logs["r00"] + "\nafter"}
    assert _reads(store, expected) == expected

    assert _tidy(db, monkeypatch, chunk=4) == {"runs_moved": 11}  # not "none" (no value), nor r00 (moved by its flush)

    assert _reads(store, expected) == expected
    assert db.execute_fetchone("SELECT count(*) FROM workflowrunrecords WHERE execution_log IS NOT NULL")[0] == 0
    assert db.execute_fetchone("SELECT count(*) FROM librarysettings WHERE id = ?",
                               [records.LOGS_AS_LINES_SETTING])[0] == 1
    assert run_log_tidy.queue_if_needed(db) is None, "marked done: the next open queues nothing"


def test_the_tidy_steps_aside_when_the_throttle_holds_and_carries_on_later(library, monkeypatch):
    db, store = library
    logs = {f"r{n:02d}": f"run {n}" for n in range(10)}
    _logs_as_before(db, logs)
    answers = iter([None, "Waiting: someone is using the Mac"])

    with pytest.raises(jobs.JobDeferred, match="someone is using the Mac"):
        _tidy(db, monkeypatch, chunk=4, why=lambda **_: next(answers))
    assert db.execute_fetchone("SELECT count(*) FROM workflowrunrecords WHERE execution_log IS NOT NULL")[0] == 6

    assert _tidy(db, monkeypatch, chunk=4) == {"runs_moved": 6}
    assert _reads(store, logs) == logs


def test_a_log_that_does_not_read_back_stays_a_value(library, monkeypatch):
    """The check before a value is cleared: a chunk whose lines do not read back rolls back, value kept."""
    db, store = library
    _logs_as_before(db, {"t1": "a\nb"})
    real = db.execute_fetchall

    def lying(sql, params=None, *a, **k):
        if "IS DISTINCT FROM" in sql:
            return [("t1",)]
        return real(sql, params, *a, **k)

    monkeypatch.setattr(db, "execute_fetchall", lying)
    with pytest.raises(RuntimeError, match="did not read back"):
        _tidy(db, monkeypatch, chunk=4)
    monkeypatch.setattr(db, "execute_fetchall", real)
    assert db.execute_fetchone("SELECT execution_log FROM workflowrunrecords WHERE id = 't1'")[0] == "a\nb"
    assert db.execute_fetchone("SELECT count(*) FROM workflowrunloglines")[0] == 0
    assert _run(store.get_workflow_run("t1")).execution_log == "a\nb"


def test_a_run_written_again_moves_its_own_log_first(library):
    db, store = library
    _logs_as_before(db, {"t1": "before the fold"})

    _run(store.flush_node_boundary("t1", progress_timeline=TIMELINE, log_text="after", replace=False))

    assert db.execute_fetchone("SELECT execution_log FROM workflowrunrecords WHERE id = 't1'")[0] is None
    assert _run(store.get_workflow_run("t1")).execution_log == "before the fold\nafter"
