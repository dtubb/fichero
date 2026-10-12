"""`source.store.one-managed-database` (#5645), slice 2: the file watcher keeps its triggers and their runs as models
through the library's one managed `Database`, and a library made with the old hand-made tables opens with every row.

Spec: docs/contributor_manual/specs/source/source-model.md. WHY: `FileWatcherManager` opened its own DuckDB connection
to the library file on each call (8 sites) and wrote hand-made `file_triggers` and `trigger_executions` tables.
Reading them back also took a trigger's `events` from its `recursive` column (the row's fifth value), so a trigger
read from the table lost the events it watched for. The old library is written with raw SQL, as an older build did.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import duckdb

from fichero_server.db import Database
from fichero_server.workflows.file_watcher import FileWatcherManager, FilterMode, TriggerEvent, TriggerStatus

OLD_TABLES = """
CREATE TABLE file_triggers (trigger_id TEXT PRIMARY KEY, name TEXT NOT NULL, workflow_id TEXT NOT NULL,
    watch_path TEXT NOT NULL, recursive BOOLEAN DEFAULT TRUE, events JSON DEFAULT '["created"]',
    filter_mode TEXT DEFAULT 'glob', filter_pattern TEXT, filter_extensions JSON DEFAULT '[]',
    exclude_patterns JSON DEFAULT '[]', debounce_seconds FLOAT DEFAULT 1.0, batch_delay_seconds FLOAT DEFAULT 5.0,
    inputs_template JSON DEFAULT '{}', status TEXT NOT NULL, use_batch BOOLEAN DEFAULT TRUE,
    max_concurrent INTEGER DEFAULT 5, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL,
    last_triggered_at TIMESTAMP, trigger_count INTEGER DEFAULT 0, error_message TEXT);
CREATE TABLE trigger_executions (execution_id TEXT PRIMARY KEY, trigger_id TEXT NOT NULL,
    triggered_at TIMESTAMP NOT NULL, file_paths JSON NOT NULL, batch_id TEXT, status TEXT NOT NULL, error TEXT,
    completed_at TIMESTAMP);
CREATE INDEX idx_trigger_executions_trigger ON trigger_executions(trigger_id);
"""


def _old_library(tmp_path: Path) -> Path:
    """A package an older build wrote: two triggers (one paused, one with only the columns it had to fill), and
    three runs of the first."""
    package = tmp_path / "Marshall.fichero"
    package.mkdir()
    path = package / "fichero.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute(OLD_TABLES)
    made = datetime(2026, 9, 1, 12, 0)
    conn.execute(
        "INSERT INTO file_triggers VALUES ('trig-scans', 'New scans', 'wf-read', '/Volumes/Scans', FALSE, "
        "'[\"created\", \"modified\"]', 'extension', NULL, '[\"tif\", \"jpg\"]', '[\"*.tmp\"]', 2.0, 10.0, "
        "'{\"document\": \"{file_path}\"}', 'active', TRUE, 3, ?, ?, ?, 3, NULL)", [made, made, made])
    # Only what an older build had to fill: every default comes from the old table.
    conn.execute("INSERT INTO file_triggers (trigger_id, name, workflow_id, watch_path, status, created_at, updated_at) "
                 "VALUES ('trig-old', 'Inbox', 'wf-import', '/Users/x/Inbox', 'paused', ?, ?)", [made, made])
    for n in range(3):
        conn.execute("INSERT INTO trigger_executions VALUES (?, 'trig-scans', ?, ?, ?, ?, ?, ?)",
                     [f"run-{n}", made.replace(hour=12 + n), json.dumps([f"/Volumes/Scans/p{n}.tif"]),
                      f"batch-{n}", "failed" if n == 1 else "completed", "unreadable" if n == 1 else None, made])
    conn.close()
    return path


def _run(coro):
    return asyncio.run(coro)


def _watcher(path: Path) -> FileWatcherManager:
    manager = FileWatcherManager(str(path), SimpleNamespace(get=lambda _id: None))
    manager._setup_watcher = lambda trigger: None  # no folder is watched in a test
    return manager


def test_a_library_with_the_old_tables_opens_with_every_trigger_and_run(tmp_path):
    path = _old_library(tmp_path)
    db = Database(path)
    try:
        assert not db.migration_failures, db.migration_failures
        watcher = _watcher(path)
        triggers = {t.trigger_id: t for t in _run(watcher.list_triggers())}
        assert set(triggers) == {"trig-scans", "trig-old"}
        scans = triggers["trig-scans"]
        assert scans.config.events == [TriggerEvent.CREATED, TriggerEvent.MODIFIED], "its events, not its recursive"
        assert scans.config.recursive is False and scans.config.filter_mode is FilterMode.EXTENSION
        assert scans.config.filter_extensions == ["tif", "jpg"] and scans.config.exclude_patterns == ["*.tmp"]
        assert scans.inputs_template == {"document": "{file_path}"} and scans.trigger_count == 3
        assert scans.created_at.tzinfo is not None
        old = triggers["trig-old"]
        assert old.status is TriggerStatus.PAUSED and old.config.events == [TriggerEvent.CREATED]
        assert old.config.recursive is True and old.max_concurrent == 5, "the old table's defaults came across"
        runs = _run(watcher.get_trigger_executions("trig-scans"))
        assert [r.execution_id for r in runs] == ["run-2", "run-1", "run-0"], "newest first"
        assert runs[1].status == "failed" and runs[1].error == "unreadable"
        assert runs[0].file_paths == ["/Volumes/Scans/p2.tif"] and runs[0].batch_id == "batch-2"
        assert db.conn.execute("SELECT count(*) FROM trigger_executions").fetchone()[0] == 3, "old table kept"
    finally:
        db.close()


def test_the_watcher_holds_no_connection_of_its_own(tmp_path):
    from fichero_server.workflows import file_watcher

    assert not hasattr(file_watcher, "connect_utc")
    path = _old_library(tmp_path)
    db = Database(path)
    try:
        assert len(_run(_watcher(path).list_triggers(status=TriggerStatus.ACTIVE))) == 1
    finally:
        db.close()


def test_a_deleted_trigger_never_comes_back_and_a_cut_short_fold_finishes(tmp_path):
    path = _old_library(tmp_path)
    db = Database(path)
    _run(_watcher(path).delete_trigger("trig-old"))
    db.close()

    again = Database(path)
    try:
        assert {t.trigger_id for t in _run(_watcher(path).list_triggers())} == {"trig-scans"}
        # As if a fold died part way: some runs missing, the fold not recorded.
        again.conn.execute("DELETE FROM triggerexecutionrecords WHERE id = 'run-0'")
        again.conn.execute("DELETE FROM librarysettings WHERE id = ?", [Database.WATCHER_TABLES_FOLDED_SETTING])
    finally:
        again.close()
    third = Database(path)
    try:
        # The missing run is copied again, once. (Removing the fold's record by hand also lets the old table's
        # deleted trigger back in; a real fold writes its record in the same transaction as its copy, so it cannot.)
        assert third.conn.execute("SELECT count(*) FROM triggerexecutionrecords").fetchone()[0] == 3
    finally:
        third.close()
