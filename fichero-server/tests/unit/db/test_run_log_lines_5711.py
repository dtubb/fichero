"""A run's log is its lines (#5711), tested to the spec: `source.store.one-managed-database`
(docs/contributor_manual/specs/source/source-model.md).

WHY: the node-boundary flush appended to one growing value, and DuckDB writes a new version of the whole value: on a
2 MB log every append wrote 2 MB to the write-ahead log, and every eighth or ninth flush paid a checkpoint on the
run's own path (the M4 parity: p95 7.5 -> 104.5 ms).
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from fichero_server.db import Database
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
    """Runs whose logs a library from before #5711 kept as one value each."""
    for n, (run_id, log) in enumerate(logs.items()):
        db.execute("INSERT INTO workflowrunrecords (id, workflow_id, workflow_name, status, started_at, execution_log) "
                   "VALUES (?, 'wf', 'Read', 'completed', ?, ?)", [run_id, datetime(2026, 10, 1, 12, n), log])
    db.execute("DELETE FROM librarysettings WHERE id = ?", [Database.RUN_LOG_FOLD_SETTING])


def test_a_library_s_logs_from_before_are_moved_into_lines_in_chunks(tmp_path, monkeypatch):
    path = tmp_path / "fichero.duckdb"
    logs = {f"r{n:02d}": f"line 1 of {n}\nline 2 of {n}\n" for n in range(9)}
    logs |= {"empty": "", "none": None, "one": "only line"}
    db = Database(path)
    _logs_as_before(db, logs)
    db.close()
    monkeypatch.setattr(Database, "RUN_LOG_FOLD_CHUNK", 4)

    db = Database(path)
    try:
        store = ActivityStore(str(db.path))
        for run_id, log in logs.items():
            assert _run(store.get_workflow_run(run_id)).execution_log == (log or ""), run_id
        assert db.execute_fetchone("SELECT count(*) FROM workflowrunrecords WHERE execution_log IS NOT NULL "
                                   "AND execution_log <> ''")[0] == 0, "every log value moved into lines"
        assert db.execute_fetchone("SELECT count(*) FROM librarysettings WHERE id = ?",
                                   [Database.RUN_LOG_FOLD_SETTING])[0] == 1
        assert not db.migration_failures
    finally:
        db.close()


def test_a_run_not_moved_yet_reads_its_old_log_then_its_lines(library):
    """A fold cut short leaves a run's log a value; a flush on it appends lines after it, and both read as one."""
    db, store = library
    _logs_as_before(db, {"t1": "before the fold"})

    _run(store.flush_node_boundary("t1", progress_timeline=TIMELINE, log_text="after", replace=False))

    assert _run(store.get_workflow_run("t1")).execution_log == "before the fold\nafter"
