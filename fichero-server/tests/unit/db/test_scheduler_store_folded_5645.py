"""`source.store.one-managed-database` (#5645), slice 3: the scheduler keeps its schedules and their runs as models
through the library's one managed `Database`, and a library made with the old hand-made tables opens with every row.

Spec: docs/contributor_manual/specs/source/source-model.md. WHY: `WorkflowScheduler` opened its own DuckDB connection to
the library file on each call (8 sites) and wrote hand-made `schedules` and `schedule_runs` tables. It also gave a
schedule's start and end dates back as naive times. The old library is written with raw SQL, as an older build did.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import duckdb

from fichero_server.db import Database
from fichero_server.workflows.scheduler import ScheduleStatus, ScheduleType, WorkflowScheduler

OLD_TABLES = """
CREATE TABLE schedules (schedule_id TEXT PRIMARY KEY, name TEXT NOT NULL, workflow_id TEXT NOT NULL,
    schedule_type TEXT NOT NULL, cron_expression TEXT, interval_seconds INTEGER, run_at TIMESTAMP,
    timezone TEXT DEFAULT 'UTC', start_date TIMESTAMP, end_date TIMESTAMP, max_runs INTEGER, inputs JSON DEFAULT '{}',
    status TEXT NOT NULL, use_batch BOOLEAN DEFAULT FALSE, batch_items JSON DEFAULT '[]',
    max_concurrent INTEGER DEFAULT 5, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL,
    last_run_at TIMESTAMP, next_run_at TIMESTAMP, run_count INTEGER DEFAULT 0, error_message TEXT);
CREATE TABLE schedule_runs (run_id TEXT PRIMARY KEY, schedule_id TEXT NOT NULL, started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP, status TEXT NOT NULL, batch_id TEXT, error TEXT);
CREATE INDEX idx_schedule_runs_schedule ON schedule_runs(schedule_id);
CREATE INDEX idx_schedules_status ON schedules(status);
"""


def _old_library(tmp_path: Path) -> Path:
    """A package an older build wrote: a nightly cron schedule with three runs, an interval one paused part way, and
    a one-time one with only the columns it had to fill."""
    package = tmp_path / "Marshall.fichero"
    package.mkdir()
    path = package / "fichero.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute(OLD_TABLES)
    made = datetime(2026, 9, 1, 12, 0)
    conn.execute(
        "INSERT INTO schedules VALUES ('nightly', 'Read new pages', 'wf-read', 'cron', '0 2 * * *', NULL, NULL, "
        "'America/Bogota', ?, ?, 30, '{\"folder\": \"inbox\"}', 'active', TRUE, '[{\"page\": 1}, {\"page\": 2}]', 2, "
        "?, ?, ?, ?, 3, NULL)", [made, made.replace(month=12), made, made, made, made.replace(day=2)])
    conn.execute(
        "INSERT INTO schedules VALUES ('hourly', 'Embed', 'wf-embed', 'interval', NULL, 3600, NULL, 'UTC', NULL, NULL, "
        "NULL, '{}', 'paused', FALSE, '[]', 5, ?, ?, NULL, NULL, 0, 'paused by you')", [made, made])
    conn.execute("INSERT INTO schedules (schedule_id, name, workflow_id, schedule_type, run_at, status, created_at, "
                 "updated_at) VALUES ('once', 'Export', 'wf-export', 'once', ?, 'completed', ?, ?)",
                 [made.replace(hour=20), made, made])
    for n in range(3):
        conn.execute("INSERT INTO schedule_runs VALUES (?, 'nightly', ?, ?, ?, ?, ?)",
                     [f"run-{n}", made.replace(hour=2 + n), made.replace(hour=3 + n),
                      "failed" if n == 1 else "completed", f"batch-{n}", "no pages" if n == 1 else None])
    conn.close()
    return path


def _run(coro):
    return asyncio.run(coro)


def _scheduler(path: Path) -> WorkflowScheduler:
    return WorkflowScheduler(str(path), SimpleNamespace(get=lambda _id: None))


def test_a_library_with_the_old_tables_opens_with_every_schedule_and_run(tmp_path):
    path = _old_library(tmp_path)
    db = Database(path)
    try:
        assert not db.migration_failures, db.migration_failures
        scheduler = _scheduler(path)
        schedules = {s.schedule_id: s for s in _run(scheduler.list_schedules())}
        assert set(schedules) == {"nightly", "hourly", "once"}
        nightly = schedules["nightly"]
        assert nightly.config.schedule_type is ScheduleType.CRON and nightly.config.cron_expression == "0 2 * * *"
        assert nightly.config.timezone == "America/Bogota" and nightly.config.max_runs == 30
        assert nightly.inputs == {"folder": "inbox"} and nightly.batch_items == [{"page": 1}, {"page": 2}]
        assert nightly.use_batch is True and nightly.max_concurrent == 2 and nightly.run_count == 3
        assert nightly.config.start_date.tzinfo is not None and nightly.config.end_date.month == 12
        hourly = schedules["hourly"]
        assert hourly.status is ScheduleStatus.PAUSED and hourly.config.interval_seconds == 3600
        assert hourly.error_message == "paused by you"
        once = schedules["once"]
        assert once.config.run_at.hour == 20 and once.config.timezone == "UTC" and once.inputs == {}
        assert once.max_concurrent == 5 and once.run_count == 0, "the old table's defaults came across"
        runs = _run(scheduler.get_schedule_runs("nightly"))
        assert [r.run_id for r in runs] == ["run-2", "run-1", "run-0"], "newest first"
        assert runs[1].status == "failed" and runs[1].error == "no pages" and runs[0].batch_id == "batch-2"
        assert db.conn.execute("SELECT count(*) FROM schedule_runs").fetchone()[0] == 3, "old table kept"
    finally:
        db.close()


def test_the_scheduler_holds_no_connection_of_its_own(tmp_path):
    from fichero_server.workflows import scheduler

    assert not hasattr(scheduler, "connect_utc")
    path = _old_library(tmp_path)
    db = Database(path)
    try:
        active = _run(_scheduler(path).list_schedules(status=ScheduleStatus.ACTIVE))
        assert [s.schedule_id for s in active] == ["nightly"]
    finally:
        db.close()


def test_a_deleted_schedule_never_comes_back_and_a_cut_short_fold_finishes(tmp_path):
    path = _old_library(tmp_path)
    db = Database(path)
    _run(_scheduler(path).delete_schedule("hourly"))
    db.close()

    again = Database(path)
    try:
        assert {s.schedule_id for s in _run(_scheduler(path).list_schedules())} == {"nightly", "once"}
        again.conn.execute("DELETE FROM schedulerunrecords WHERE id = 'run-0'")  # as if a fold died part way
        again.conn.execute("DELETE FROM librarysettings WHERE id = ?", [Database.SCHEDULER_TABLES_FOLDED_SETTING])
    finally:
        again.close()
    third = Database(path)
    try:
        assert third.conn.execute("SELECT count(*) FROM schedulerunrecords").fetchone()[0] == 3, "copied once"
    finally:
        third.close()


def test_rows_an_older_engine_writes_after_the_fold_are_said_not_copied(tmp_path):
    path = _old_library(tmp_path)
    Database(path).close()
    conn = duckdb.connect(str(path))
    conn.execute("SET TimeZone = 'UTC'")  # as every engine's session is (`connect_utc`)
    conn.execute("INSERT INTO schedule_runs VALUES ('run-old-engine', 'nightly', now()::TIMESTAMP + INTERVAL 1 MINUTE, "
                 "NULL, 'running', NULL, NULL)")
    conn.close()
    db = Database(path)
    try:
        (said,) = [f for f in db.migration_failures if f.error_type == "WrittenByAnOlderEngine"]
        assert said.message.startswith("1 rows were written to the old scheduler tables")
    finally:
        db.close()
