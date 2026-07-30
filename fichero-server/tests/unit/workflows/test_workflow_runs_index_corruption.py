"""Regression tests for #1362 — startup recovery of zombie workflow_runs must
NEVER fatal-poison the DuckDB connection over ART-indexed rows.

Background
----------
``workflow_runs`` has a PRIMARY KEY on ``thread_id`` (an ART index) plus
secondary indexes. After a crash + WAL replay the ART index can desync from
the table heap. An in-place ``UPDATE``/``DELETE`` then raises::

    Invalid Input Error: Failed to delete all rows from index.
    Only deleted 0 out of N rows.

which DuckDB escalates to a FATAL error: the *entire* database is invalidated
for the process lifetime, so every later endpoint (``/api/workflows``,
``/api/activity``) 500s with "database has been invalidated". A user's live
library is bricked until restart — and a fresh restart re-runs the same
recovery UPDATE and re-triggers the fatal (the recurrence in #1362).

The morning fix only flipped zombie rows in-place before ``CREATE INDEX`` —
the in-place UPDATE *is* the statement that fatals, so that fix was incomplete.

Fix under test
--------------
``_recover_stale_workflow_runs`` tries an in-place UPDATE first, and on ANY
``duckdb.Error`` (notably the FATAL index error) discards the poisoned
connection and rebuilds ``workflow_runs`` from scratch on a fresh connection
via ``_rebuild_workflow_runs_flipping_stale`` (CREATE TABLE AS SELECT → DROP →
RENAME → recreate indexes). The rebuild never performs an indexed in-place
delete, so it sidesteps the bug entirely and leaves a usable connection.

NOTE: the raw "Failed to delete all rows from index" FATAL could NOT be
reproduced on a *cleanly-written* DuckDB 1.5.3 file (it requires a genuinely
corrupt crash/WAL state). These tests therefore (a) exercise the happy path
on a real indexed table with zombie rows, and (b) force the fatal via a
monkeypatched connection to prove the fallback rebuild repairs the table and
leaves a usable connection — exactly the live failure mode.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import duckdb
import pytest

from fichero_server.workflows.activity_store import (
    ActivityStore,
    _rebuild_workflow_runs_flipping_stale,
    _recover_stale_workflow_runs,
)


# Canonical workflow_runs DDL with the PK ART index + secondary indexes, the
# way ActivityStore._init_database builds it.
_DDL = """
CREATE TABLE workflow_runs (
    thread_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    workflow_name TEXT NOT NULL,
    python_code TEXT,
    execution_log TEXT,
    status TEXT DEFAULT 'running',
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration_ms FLOAT,
    error TEXT,
    workflow_snapshot JSON,
    node_name_map JSON,
    progress_timeline JSON,
    diagram_mermaid TEXT
)
"""


def _seed_indexed_zombies(db_path: str, n: int = 4) -> None:
    """Create workflow_runs WITH indexes and ``n`` stale 'running' rows.

    Mirrors the live crash chunk: a shared workflow_id (hex) across threads
    and old started_at timestamps (May 23–29).
    """
    conn = duckdb.connect(db_path)
    try:
        conn.execute(_DDL)
        conn.execute(
            "CREATE INDEX idx_workflow_runs_workflow_id ON workflow_runs(workflow_id)"
        )
        conn.execute(
            "CREATE INDEX idx_workflow_runs_started_at "
            "ON workflow_runs(started_at DESC)"
        )
        for i in range(n):
            conn.execute(
                "INSERT INTO workflow_runs"
                "(thread_id, workflow_id, workflow_name, status, started_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    f"thread-b0b9c8db6bc{i}",
                    "364a050ba492487f8a7116c8c4e8afa6",
                    "wf",
                    "running",
                    datetime.datetime(2026, 5, 23 + i),
                ],
            )
    finally:
        conn.close()


def _status_counts(db_path: str) -> dict[str, int]:
    conn = duckdb.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT status, count(*) FROM workflow_runs GROUP BY status"
        ).fetchall()
        return {status: count for status, count in rows}
    finally:
        conn.close()


class TestStartupRecoveryIsCrashSafe:
    """The happy path: recovery on a real indexed table with zombie rows must
    flip them and leave the connection usable (no fatal)."""

    def test_construction_does_not_flip_and_sweep_recovers(
        self, tmp_path: Path
    ) -> None:
        """#4316: constructing ActivityStore must NOT flip rows — reopening a
        library mid-run used to fail LIVE runs (F5). The explicit sweep
        (recover_stale_runs) is what recovers zombies, crash-safe."""
        import asyncio

        db_path = str(tmp_path / "lib.duckdb")
        _seed_indexed_zombies(db_path, n=4)

        store = ActivityStore(db_path)

        # (a) construction alone leaves the rows untouched (F5 regression)
        counts = _status_counts(db_path)
        assert counts.get("running") == 4, f"construction flipped rows: {counts}"

        # (c) the explicit sweep flips them, crash-safe
        recovered = asyncio.run(store.recover_stale_runs(max_age_hours=0))
        assert recovered == 4
        counts = _status_counts(db_path)
        assert counts.get("failed") == 4, f"expected 4 failed, got {counts}"
        assert "running" not in counts

        # (b) the database is still usable afterward — a follow-up query must
        #     succeed, not raise "database has been invalidated".
        conn = duckdb.connect(db_path)
        try:
            total = conn.execute("SELECT count(*) FROM workflow_runs").fetchone()
            assert total == (4,)
            # the workflows-list query shape used by /api/workflows
            rows = conn.execute(
                "SELECT thread_id, status FROM workflow_runs "
                "ORDER BY started_at DESC"
            ).fetchall()
            assert len(rows) == 4
        finally:
            conn.close()

    def test_recover_stale_runs_respects_cutoff_on_indexed_table(
        self, tmp_path: Path
    ) -> None:
        """recover_stale_runs only flips rows older than the cutoff."""
        db_path = str(tmp_path / "lib.duckdb")
        conn = duckdb.connect(db_path)
        try:
            conn.execute(_DDL)
            conn.execute(
                "CREATE INDEX idx_workflow_runs_started_at "
                "ON workflow_runs(started_at DESC)"
            )
            old = datetime.datetime(2026, 5, 23)
            recent = datetime.datetime.now()
            conn.execute(
                "INSERT INTO workflow_runs"
                "(thread_id, workflow_id, workflow_name, status, started_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ["old-zombie", "wf", "wf", "running", old],
            )
            conn.execute(
                "INSERT INTO workflow_runs"
                "(thread_id, workflow_id, workflow_name, status, started_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ["fresh-live", "wf", "wf", "running", recent],
            )
        finally:
            conn.close()

        cutoff = datetime.datetime(2026, 5, 24)
        conn = duckdb.connect(db_path)
        try:
            flipped = _recover_stale_workflow_runs(
                conn, db_path, started_before=cutoff
            )
        finally:
            conn.close()

        assert flipped == 1
        counts = _status_counts(db_path)
        assert counts.get("running") == 1  # fresh-live untouched
        assert counts.get("failed") == 1  # old-zombie flipped


class TestFatalFallbackRebuild:
    """Force the FATAL index error and assert the defensive rebuild repairs the
    table and leaves a usable connection. This is the recurrence guard."""

    def test_fatal_on_update_triggers_rebuild_and_leaves_usable_db(
        self, tmp_path: Path
    ) -> None:
        db_path = str(tmp_path / "lib.duckdb")
        _seed_indexed_zombies(db_path, n=4)

        class PoisonedConn:
            """Stands in for a connection whose first execute() fatals on the
            ART-index delete path, exactly like the live crash."""

            def __init__(self) -> None:
                self.closed = False

            def execute(self, *args, **kwargs):
                raise duckdb.FatalException(
                    "FATAL Error: Failed: database has been invalidated because "
                    "of a previous fatal error.\nOriginal error: Invalid Input "
                    "Error: Failed to delete all rows from index. Only deleted "
                    "0 out of 4 rows."
                )

            def close(self) -> None:
                self.closed = True

        # The poisoned connection fatals on the in-place UPDATE; the helper must
        # fall back to a fresh-connection table rebuild.
        flipped = _recover_stale_workflow_runs(
            PoisonedConn(), db_path, started_before=None
        )

        # (a) it did NOT raise — control reached here
        # zombie rows are now 'failed'
        assert flipped == 4, f"expected 4 rebuilt-flipped rows, got {flipped}"
        counts = _status_counts(db_path)
        assert counts.get("failed") == 4
        assert "running" not in counts

        # (b) the connection/db is still usable — follow-up SELECT succeeds
        conn = duckdb.connect(db_path)
        try:
            assert conn.execute(
                "SELECT count(*) FROM workflow_runs"
            ).fetchone() == (4,)

            # the PK uniqueness must be reinstated by the rebuild — inserting a
            # duplicate thread_id must fail (proves the unique index exists).
            with pytest.raises(duckdb.Error):
                conn.execute(
                    "INSERT INTO workflow_runs"
                    "(thread_id, workflow_id, workflow_name, status, started_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [
                        "thread-b0b9c8db6bc0",  # duplicate of seeded row 0
                        "x",
                        "x",
                        "failed",
                        datetime.datetime(2026, 5, 23),
                    ],
                )

            # secondary indexes were recreated
            idx = {
                r[0]
                for r in conn.execute(
                    "SELECT index_name FROM duckdb_indexes() "
                    "WHERE table_name = 'workflow_runs'"
                ).fetchall()
            }
            assert "idx_workflow_runs_workflow_id" in idx
            assert "idx_workflow_runs_started_at" in idx
        finally:
            conn.close()

    def test_rebuild_preserves_nonstale_rows_verbatim(
        self, tmp_path: Path
    ) -> None:
        """The rebuild must copy completed/failed/recent rows unchanged and only
        flip the stale 'running' ones."""
        db_path = str(tmp_path / "lib.duckdb")
        conn = duckdb.connect(db_path)
        try:
            conn.execute(_DDL)
            base = datetime.datetime(2026, 5, 23)
            conn.execute(
                "INSERT INTO workflow_runs"
                "(thread_id, workflow_id, workflow_name, status, started_at, "
                " error, python_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ["done", "wf", "Done", "completed", base, None, "print(1)"],
            )
            conn.execute(
                "INSERT INTO workflow_runs"
                "(thread_id, workflow_id, workflow_name, status, started_at, "
                " error) VALUES (?, ?, ?, ?, ?, ?)",
                ["already-failed", "wf", "F", "failed", base, "boom"],
            )
            conn.execute(
                "INSERT INTO workflow_runs"
                "(thread_id, workflow_id, workflow_name, status, started_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ["zombie", "wf", "Z", "running", base],
            )
        finally:
            conn.close()

        flipped = _rebuild_workflow_runs_flipping_stale(db_path, started_before=None)
        assert flipped == 1

        conn = duckdb.connect(db_path)
        try:
            rows = {
                r[0]: r
                for r in conn.execute(
                    "SELECT thread_id, status, error, python_code "
                    "FROM workflow_runs"
                ).fetchall()
            }
        finally:
            conn.close()

        # completed row unchanged, python_code preserved
        assert rows["done"][1] == "completed"
        assert rows["done"][3] == "print(1)"
        # pre-existing failed row keeps its original error verbatim
        assert rows["already-failed"][1] == "failed"
        assert rows["already-failed"][2] == "boom"
        # zombie flipped and given a recovery error message
        assert rows["zombie"][1] == "failed"
        assert rows["zombie"][2] and "interrupted" in rows["zombie"][2].lower()


class TestActivityStoreRecoverStaleRunsApi:
    """The public async API still works end-to-end on an indexed table."""

    @pytest.mark.asyncio
    async def test_recover_stale_runs_async_on_indexed_table(
        self, tmp_path: Path
    ) -> None:
        from datetime import timezone, timedelta

        db_path = str(tmp_path / "lib.duckdb")
        store = ActivityStore(db_path)

        two_hours_ago = datetime.datetime.now(timezone.utc) - timedelta(hours=2)
        await store.save_workflow_run(
            thread_id="zombie-async",
            workflow_id="wf",
            workflow_name="Z",
            started_at=two_hours_ago,
        )

        recovered = await store.recover_stale_runs(max_age_hours=1)
        assert recovered == 1

        run = await store.get_workflow_run("zombie-async")
        assert run is not None
        assert run.status == "failed"

        # db remains usable
        runs = await store.list_workflow_runs(limit=10)
        assert any(r.thread_id == "zombie-async" for r in runs)
