"""`source.store.one-managed-database` (#5645): the batch store keeps its rows as models through the library's one
managed `Database`, and a library made with the old hand-made tables opens with every row it had.

Spec: docs/contributor_manual/specs/source/source-model.md. WHY: `BatchManager` opened its own DuckDB connection to
the library file on each call and wrote hand-made tables, outside the managed lock and the schema, export and
migration walkers; #5644's stale indexes did their worst damage to such tables. Real libraries (the Marshall
Diaries) hold rows in the old tables, so the fold must copy every one, check it, and never bring a deleted one back.
The old library here is written with raw SQL in the shape the old store made, as an older build left it.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from fichero_server.db import Database
from fichero_server.execution.batch import BatchItemStatus, BatchManager, BatchStatus

OLD_TABLES = """
CREATE TABLE batches (batch_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, status TEXT NOT NULL,
    max_concurrent INTEGER DEFAULT 5, created_at TIMESTAMP NOT NULL, started_at TIMESTAMP, completed_at TIMESTAMP,
    error_message TEXT);
CREATE TABLE batch_items (batch_id TEXT NOT NULL, thread_id TEXT NOT NULL, item_index INTEGER NOT NULL,
    inputs JSON NOT NULL, status TEXT NOT NULL, error TEXT, started_at TIMESTAMP, completed_at TIMESTAMP,
    PRIMARY KEY (batch_id, thread_id));
CREATE INDEX idx_batch_items_batch_id ON batch_items(batch_id);
CREATE TABLE batch_progress_snapshots (batch_id TEXT NOT NULL, timestamp TIMESTAMP NOT NULL, completed_count INTEGER,
    failed_count INTEGER, avg_duration_ms FLOAT, PRIMARY KEY (batch_id, timestamp));
"""


def _old_library(tmp_path: Path) -> Path:
    """A package whose database an older build wrote: three batches, the second failed part way, in the old tables."""
    package = tmp_path / "Marshall.fichero"
    package.mkdir()
    path = package / "fichero.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute(OLD_TABLES)
    made = datetime(2026, 9, 1, 12, 0)
    for n, status in enumerate(["completed", "partial_failure", "pending"]):
        conn.execute("INSERT INTO batches VALUES (?, 'wf-diaries', ?, 3, ?, ?, ?, ?)",
                     [f"batch-{n}", status, made.replace(hour=12 + n), made if n < 2 else None,
                      made.replace(hour=13 + n) if n < 2 else None, "1 page failed" if n == 1 else None])
        for i in range(4):
            item_status = "failed" if (n == 1 and i == 2) else "completed" if n < 2 else "pending"
            conn.execute("INSERT INTO batch_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         [f"batch-{n}", f"thread-{n}-{i}", i, json.dumps({"document_id": f"page-{n}-{i}"}),
                          item_status, "unreadable" if item_status == "failed" else None,
                          made if n < 2 else None, made if n < 2 else None])
    conn.close()
    return path


def _run(coro):
    return asyncio.run(coro)


def test_a_library_with_the_old_tables_opens_with_every_batch_and_item(tmp_path):
    path = _old_library(tmp_path)
    db = Database(path)
    try:
        assert not db.migration_failures, db.migration_failures
        manager = BatchManager(str(path))
        batches = {b.batch_id: b for b in _run(manager.list_batches())}
        assert set(batches) == {"batch-0", "batch-1", "batch-2"}
        failed = batches["batch-1"]
        assert failed.status is BatchStatus.PARTIAL_FAILURE and failed.error_message == "1 page failed"
        assert failed.max_concurrent == 3 and failed.workflow_id == "wf-diaries"
        assert [i.item_index for i in failed.items] == [0, 1, 2, 3]
        assert failed.items[2].status is BatchItemStatus.FAILED and failed.items[2].error == "unreadable"
        assert failed.items[0].inputs == {"document_id": "page-1-0"}
        assert failed.created_at.tzinfo is not None, "times come back as UTC instants"
        # The old tables are kept, untouched, until a later step removes them.
        assert db.conn.execute("SELECT count(*) FROM batch_items").fetchone()[0] == 12
    finally:
        db.close()


def test_the_store_uses_the_managed_connection_not_its_own(tmp_path, monkeypatch):
    """Nothing in the batch store opens a connection of its own any more (#5645: it had five)."""
    from fichero_server.execution import batch

    assert not hasattr(batch, "connect_utc")
    path = _old_library(tmp_path)
    db = Database(path)
    try:
        manager = BatchManager(str(path))
        made = _run(manager.create_batch("wf-diaries", [{"document_id": "new"}]))
        assert _run(manager.get_batch(made.batch_id)) is not None
    finally:
        db.close()


def test_the_fold_runs_once_and_a_deleted_batch_never_comes_back(tmp_path):
    path = _old_library(tmp_path)
    db = Database(path)
    manager = BatchManager(str(path))
    _run(manager.delete_batch("batch-0"))
    db.close()

    again = Database(path)  # reopened: the old tables still hold batch-0, the fold is recorded
    try:
        ids = {b.batch_id for b in _run(BatchManager(str(path)).list_batches())}
        assert ids == {"batch-1", "batch-2"}
        assert again.conn.execute("SELECT count(*) FROM batchitemrecords").fetchone()[0] == 8
    finally:
        again.close()


def test_a_fold_cut_short_finishes_on_the_next_open_without_doubling(tmp_path):
    from fichero_server.models.knowledge import LibrarySetting

    path = _old_library(tmp_path)
    db = Database(path)
    # As if the engine died after part of the copy, before the fold was recorded.
    db.conn.execute("DELETE FROM batchitemrecords WHERE batch_id = 'batch-2'")
    db.conn.execute("DELETE FROM librarysettings WHERE id = ?", [Database.BATCH_TABLES_FOLDED_SETTING])
    db.close()

    again = Database(path)
    try:
        assert again.conn.execute("SELECT count(*) FROM batchitemrecords").fetchone()[0] == 12
        assert again.conn.execute("SELECT count(*) FROM batchrecords").fetchone()[0] == 3
        assert again.get(LibrarySetting, Database.BATCH_TABLES_FOLDED_SETTING) is not None
    finally:
        again.close()


def test_a_new_library_has_nothing_to_fold(tmp_path):
    package = tmp_path / "New.fichero"
    package.mkdir()
    db = Database(package / "fichero.duckdb")
    try:
        assert not db.migration_failures
        assert db.conn.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE table_name IN ('batches', 'batch_items')").fetchone()[0] == 0
        made = _run(BatchManager(str(db.path)).create_batch("wf", [{"a": 1}, {"a": 2}]))
        loaded = _run(BatchManager(str(db.path)).get_batch(made.batch_id))  # a fresh manager reads the rows
        assert loaded is not None and [i.inputs for i in loaded.items] == [{"a": 1}, {"a": 2}]
        assert loaded.created_at.tzinfo is not None and loaded.created_at <= datetime.now(timezone.utc)
    finally:
        db.close()
