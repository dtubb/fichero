"""`source.store.one-managed-database` (#5645), slice 4: the activity store keeps its events and runs as models through
the library's one managed `Database`; a library made with the old hand-made tables opens with every row, folded in
chunks; Activity's list reads a light row; a node-boundary flush appends rather than rewriting the whole log.

Spec: docs/contributor_manual/specs/source/source-model.md. WHY: `ActivityStore` opened its own DuckDB connection to the
library file for each of 16 kinds of call, on the hottest paths in the engine (every node boundary of every run,
every activity event, every Activity poll), outside the managed lock; the poll read 50 runs with their code and
logs; each node flush rewrote the run's whole log. Real libraries (the Marshall Diaries) hold many runs.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from fichero_server.db import Database
from fichero_server.workflows.activity_store import ActivityStore
from fichero_server.workflows.activity_types import Activity, ActivityFilter, ActivityLevel, ActivityType

#: An older library's shape: `workflow_runs` from before `run_usage` and `estimated_cost` existed.
OLD_TABLES = """
CREATE TABLE activities (id TEXT PRIMARY KEY, type TEXT NOT NULL, level TEXT NOT NULL, timestamp TIMESTAMP NOT NULL,
    message TEXT NOT NULL, workflow_id TEXT, batch_id TEXT, thread_id TEXT, node_id TEXT, metadata JSON,
    duration_ms FLOAT, error TEXT);
CREATE TABLE workflow_runs (thread_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, workflow_name TEXT NOT NULL,
    python_code TEXT, execution_log TEXT, status TEXT DEFAULT 'running', started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP, duration_ms FLOAT, error TEXT, workflow_snapshot JSON, node_name_map JSON,
    progress_timeline JSON, diagram_mermaid TEXT, resolved_scope JSON);
CREATE INDEX idx_activities_timestamp ON activities(timestamp DESC);
CREATE INDEX idx_workflow_runs_started_at ON workflow_runs(started_at DESC);
"""
RUNS = 30


def _old_library(tmp_path: Path) -> Path:
    """30 runs (one failed, one deleted, one paused), 3 events each, as an older build left them."""
    package = tmp_path / "Marshall.fichero"
    package.mkdir()
    path = package / "fichero.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute(OLD_TABLES)
    start = datetime(2026, 9, 1, 12, 0)
    for n in range(RUNS):
        status = {3: "failed", 4: "deleted", 5: "paused"}.get(n, "completed")
        conn.execute("INSERT INTO workflow_runs VALUES (?, 'wf-read', 'Read the diaries', ?, ?, ?, ?, ?, 900.0, ?, ?, "
                     "?, ?, 'graph TD; a-->b', ?)",
                     [f"run-{n:02d}", f"code {n}", f"line 1 of {n}\nline 2 of {n}", status,
                      start + timedelta(minutes=n), start + timedelta(minutes=n, seconds=30),
                      "a page failed" if n == 3 else None, json.dumps({"nodes": [n]}), json.dumps({"n1": "Read"}),
                      json.dumps({"events": [{"type": "node_end", "node_id": "n1", "page_id": f"p{n}"}]}),
                      json.dumps({"documents": [f"d{n}"]})])
        for e in range(3):
            conn.execute("INSERT INTO activities VALUES (?, 'node_completed', 'info', ?, ?, 'wf-read', NULL, ?, 'n1', "
                         "?, 12.5, NULL)", [f"ev-{n:02d}-{e}", start + timedelta(minutes=n, seconds=e),
                                            f"node {e} of run {n}", f"run-{n:02d}", json.dumps({"page": e})])
    conn.close()
    return path


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def small_chunks(monkeypatch):
    """Folds 7 rows to a transaction, so 30 runs and 90 events take several chunks each."""
    monkeypatch.setattr(Database, "ACTIVITY_FOLD_CHUNK", 7)


def test_a_library_with_the_old_tables_opens_with_every_run_and_event(tmp_path, small_chunks):
    path = _old_library(tmp_path)
    db = Database(path)
    try:
        assert not db.migration_failures, db.migration_failures
        store = ActivityStore(str(path))
        run = _run(store.get_workflow_run("run-03"))
        assert run.status == "failed" and run.error == "a page failed" and run.python_code == "code 3"
        assert run.execution_log == "line 1 of 3\nline 2 of 3" and run.workflow_snapshot == {"nodes": [3]}
        assert run.resolved_scope == {"documents": ["d3"]} and run.started_at.tzinfo is not None
        assert run.run_usage is None and run.estimated_cost is None, "columns the old table never had come as NULL"
        listed = _run(store.list_workflow_runs(limit=100))
        assert len(listed) == RUNS - 1, "the deleted run is not listed"
        assert [r.thread_id for r in listed[:2]] == ["run-29", "run-28"], "newest first"
        events = _run(store.query(ActivityFilter(limit=1000)))
        assert len(events) == (RUNS - 1) * 3, "a deleted run's events stay hidden (#4960)"
        assert events[0].id == "ev-29-2" and events[0].metadata == {"page": 2}
        assert db.conn.execute("SELECT count(*) FROM workflow_runs").fetchone()[0] == RUNS, "old table kept"
    finally:
        db.close()


def test_the_activity_list_reads_a_light_row(tmp_path):
    """The poll reads 50 runs every few seconds: no code, log, snapshot, node map or diagram (`get_workflow_run`
    reads one run whole). The progress timeline stays: the run account reads it."""
    path = _old_library(tmp_path)
    db = Database(path)
    try:
        (listed,) = [r for r in _run(ActivityStore(str(path)).list_workflow_runs(limit=50)) if r.thread_id == "run-03"]
        assert listed.python_code == "" and listed.execution_log == ""
        assert listed.workflow_snapshot is None and listed.diagram_mermaid is None
        assert listed.status == "failed" and listed.error == "a page failed"
        assert listed.progress_timeline and listed.progress_timeline.get("steps") is not None
    finally:
        db.close()


def test_the_store_holds_no_connection_of_its_own(tmp_path):
    from fichero_server.workflows import activity_store

    assert not hasattr(activity_store, "connect_utc") and not hasattr(activity_store, "duckdb_connection_lock")
    path = _old_library(tmp_path)
    db = Database(path)
    try:
        store = ActivityStore(str(path))
        assert store.db is not None
        store.save_now(Activity(id="ev-new", type=ActivityType.NODE_COMPLETED, level=ActivityLevel.INFO,
                                timestamp=datetime.now(), message="saved on the managed connection"))
        assert _run(store.query(ActivityFilter(limit=1)))[0].id == "ev-new"
    finally:
        db.close()


def test_a_node_flush_appends_and_the_log_reads_as_one(tmp_path):
    """A run's first flush in a process replaces its log (as before); later ones append only their new lines; the
    stored log is exactly the lines joined, as the old whole-log rewrite left it."""
    package = tmp_path / "New.fichero"
    package.mkdir()
    db = Database(package / "fichero.duckdb")
    try:
        store = ActivityStore(str(db.path))
        _run(store.save_workflow_run("t1", "wf", "Read", execution_log="from an earlier process"))
        timeline = {"nodes": {}, "steps": []}
        _run(store.flush_node_boundary("t1", progress_timeline=timeline, log_text="a\nb", replace=True))
        _run(store.flush_node_boundary("t1", progress_timeline=timeline, log_text="c", replace=False))
        _run(store.flush_node_boundary("t1", progress_timeline=timeline, log_text="", replace=False))
        _run(store.flush_node_boundary("t1", progress_timeline=timeline, log_text="d\ne", replace=False))
        assert _run(store.get_workflow_run("t1")).execution_log == "a\nb\nc\nd\ne"
    finally:
        db.close()


def test_a_deleted_run_stays_deleted_and_a_cut_short_fold_finishes_once(tmp_path, small_chunks):
    path = _old_library(tmp_path)
    db = Database(path)
    store = ActivityStore(str(path))
    assert store.delete_workflow_runs_sync(["run-07"]) == ["run-07"]
    db.close()

    again = Database(path)  # the old table still says run-07 completed; the fold is recorded, so it is not copied
    try:
        assert _run(ActivityStore(str(path)).get_workflow_run("run-07")).status == "deleted"
        # As if the fold had died part way: some rows missing, the fold not recorded.
        again.conn.execute("DELETE FROM workflowrunrecords WHERE id IN ('run-20', 'run-21')")
        again.conn.execute("DELETE FROM activityeventrecords WHERE id LIKE 'ev-2%'")
        again.conn.execute("DELETE FROM librarysettings WHERE id = ?", [Database.ACTIVITY_TABLES_FOLDED_SETTING])
    finally:
        again.close()
    third = Database(path)
    try:
        assert third.conn.execute("SELECT count(*) FROM workflowrunrecords").fetchone()[0] == RUNS
        assert third.conn.execute("SELECT count(*) FROM activityeventrecords").fetchone()[0] == RUNS * 3
    finally:
        third.close()


def test_rows_an_older_engine_writes_after_the_fold_are_said_not_copied(tmp_path):
    path = _old_library(tmp_path)
    Database(path).close()
    conn = duckdb.connect(str(path))
    conn.execute("SET TimeZone = 'UTC'")  # as every engine's session is (`connect_utc`)
    conn.execute("INSERT INTO workflow_runs (thread_id, workflow_id, workflow_name, status, started_at) "
                 "VALUES ('run-old-engine', 'wf', 'W', 'running', now()::TIMESTAMP + INTERVAL 1 MINUTE)")
    conn.close()
    db = Database(path)
    try:
        (said,) = [f for f in db.migration_failures if f.error_type == "WrittenByAnOlderEngine"]
        assert said.message.startswith("1 rows were written to the old activity tables")
        assert _run(ActivityStore(str(path)).get_workflow_run("run-old-engine")) is None
    finally:
        db.close()


def test_a_new_library_has_no_old_activity_tables(tmp_path):
    """The old `activities` table is no longer made at every open (it was, by the manager's migration)."""
    from fichero_server.db.manager import db_manager

    package = tmp_path / "Fresh.fichero"
    package.mkdir()
    db = db_manager.get_database(package)
    try:
        assert not db.migration_failures
        assert db.conn.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name IN ('activities', "
                               "'workflow_runs')").fetchone()[0] == 0
        indexes = {r[0] for r in db.conn.execute("SELECT index_name FROM duckdb_indexes()").fetchall()}
        assert {"idx_workflowrunrecords_started_at", "idx_activityeventrecords_timestamp"} <= indexes
    finally:
        db_manager.close_database(package)
