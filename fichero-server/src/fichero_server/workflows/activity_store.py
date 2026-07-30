"""
ActivityStore — DuckDB-backed persistence for activity events and workflow runs.

Included by activity.py via composition (ActivityTracker.store).
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from fichero_server.core.timeutil import ensure_utc, utc_now
from typing import Any, Optional

import duckdb
from fichero_server.core.duckdb_session import connect_utc

from fichero_server.workflows.activity_types import (
    Activity,
    ActivityFilter,
    ActivityLevel,
    ActivityStats,
    ActivityType,
    WorkflowRun,
)

logger = logging.getLogger(__name__)

_connection_locks: dict[str, threading.RLock] = {}
_connection_locks_guard = threading.Lock()


def duckdb_connection_lock(db_path: str) -> threading.RLock:
    """Return the process-local lock for independent DuckDB connections."""
    with _connection_locks_guard:
        return _connection_locks.setdefault(str(db_path), threading.RLock())


# Columns of workflow_runs in the canonical CREATE TABLE order. Used by the
# crash-safe rebuild path so the rebuilt table is byte-for-byte equivalent.
_WORKFLOW_RUNS_COLUMNS = (
    "thread_id",
    "workflow_id",
    "workflow_name",
    "python_code",
    "execution_log",
    "status",
    "started_at",
    "completed_at",
    "duration_ms",
    "error",
    "workflow_snapshot",
    "node_name_map",
    "progress_timeline",
    "diagram_mermaid",
    "resolved_scope",
)

# Secondary indexes on workflow_runs that must be recreated after a rebuild.
_WORKFLOW_RUNS_INDEXES = (
    ("idx_workflow_runs_workflow_id", "workflow_runs(workflow_id)"),
    ("idx_workflow_runs_started_at", "workflow_runs(started_at DESC)"),
)

_STALE_RUN_ERROR = (
    "Run interrupted: process crashed or was killed before completion "
    "(recovered on startup)."
)

# Recovery sweeps EVERY non-terminal status (#4316): 'running' rows whose
# worker died, 'accepted' rows whose worker never started, and 'paused' rows
# with no process left to resume them. Inlined as SQL fragments below.
_SWEEPABLE_STATUSES = ("running", "accepted", "paused")
_SWEEPABLE_STATUS_SQL = ", ".join(f"'{s}'" for s in _SWEEPABLE_STATUSES)

_PROGRESS_EVENT_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("node_id", ("node_id", "node")),
    ("file_path", ("file_path",)),
    ("file_index", ("file_index",)),
    ("file_total", ("file_total",)),
    ("progress", ("progress",)),
    ("document_id", ("document_id",)),
    ("page_id", ("page_id",)),
    ("display_name", ("display_name",)),
    ("sequence", ("sequence",)),
)


def _progress_event_data(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data")
    return data if isinstance(data, dict) else {}


def _hydrate_progress_event(event: dict[str, Any]) -> dict[str, Any]:
    hydrated = dict(event)
    data = _progress_event_data(hydrated)
    for field, keys in _PROGRESS_EVENT_FIELDS:
        if hydrated.get(field) is not None:
            continue
        for key in keys:
            value = data.get(key)
            if value is not None:
                hydrated[field] = value
                break
    return hydrated


def _progress_event_key(event: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (
        event.get("node_id"),
        event.get("page_id"),
        event.get("file_path"),
    )


def _progress_terminal_status(event_type: str) -> str | None:
    if event_type == "complete":
        return "completed"
    if event_type in {"error", "systemic_error"}:
        return "failed"
    if event_type == "cancelled":
        return "cancelled"
    if event_type == "pause":
        return "paused"
    return None


def _hydrate_progress_steps(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    active_steps: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    active_nodes: dict[str, dict[str, Any]] = {}

    for event in events:
        event_type = event.get("event")
        timestamp = event.get("timestamp")
        data = _progress_event_data(event)

        if event_type == "node_begin":
            node_id = event.get("node_id")
            if not node_id:
                continue
            step = {
                "node_id": node_id,
                "started_at": timestamp,
                "status": "running",
            }
            steps.append(step)
            active_steps[_progress_event_key(event)] = step
            active_nodes[node_id] = step
            continue

        if event_type == "node_end":
            node_id = event.get("node_id")
            if not node_id:
                continue
            step = active_nodes.get(node_id)
            if step is None:
                continue
            step["completed_at"] = timestamp
            step["status"] = _progress_event_data(event).get("status") or "success"
            if (duration_ms := _progress_event_data(event).get("duration_ms")) is not None:
                step["duration_ms"] = duration_ms
            if (skip_reason := _progress_event_data(event).get("skip_reason")) is not None:
                step["skip_reason"] = skip_reason
            continue

        if event_type not in {"file_start", "file_complete", "file_error"}:
            continue

        key = _progress_event_key(event)
        step = active_steps.get(key)
        if event_type == "file_start" or step is None:
            step = {
                "type": "file",
                "node_id": event.get("node_id"),
                "file_path": event.get("file_path"),
                "document_id": event.get("document_id"),
                "page_id": event.get("page_id"),
                "file_index": event.get("file_index"),
                "file_total": event.get("file_total"),
                "display_name": event.get("display_name"),
                "sequence": event.get("sequence"),
                "started_at": timestamp,
                "status": "running",
            }
            steps.append(step)
            active_steps[key] = step

        if event_type == "file_complete":
            step["completed_at"] = timestamp
            step["status"] = "success"
            started_at = step.get("started_at")
            if started_at and timestamp and "duration_ms" not in step:
                try:
                    step["duration_ms"] = (
                        datetime.fromisoformat(timestamp)
                        - datetime.fromisoformat(started_at)
                    ).total_seconds() * 1000
                except ValueError:
                    pass
        elif event_type == "file_error":
            step["completed_at"] = timestamp
            step["status"] = "error"
            error = data.get("error") or event.get("error")
            if error is not None:
                step["error"] = error
            for key_name in ("error_category", "error_hint", "error_action"):
                value = data.get(key_name) or event.get(key_name)
                if value is not None:
                    step[key_name] = value

    return steps


def _hydrate_progress_nodes(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}

    for event in events:
        event_type = event.get("event")
        timestamp = event.get("timestamp")
        data = _progress_event_data(event)
        node_id = event.get("node_id")

        if not node_id:
            continue

        if event_type == "node_begin":
            nodes[node_id] = {
                "node_id": node_id,
                "display_name": event.get("display_name") or node_id,
                "started_at": timestamp,
                "status": "running",
            }
            continue

        if event_type == "node_end":
            node = nodes.setdefault(
                node_id,
                {
                    "node_id": node_id,
                    "display_name": event.get("display_name") or node_id,
                    "started_at": timestamp,
                    "status": "running",
                },
            )
            node["completed_at"] = timestamp
            node["status"] = data.get("status") or "success"
            if data.get("duration_ms") is not None:
                node["duration_ms"] = data["duration_ms"]
            if data.get("skip_reason") is not None:
                node["skip_reason"] = data["skip_reason"]
            continue

        if event_type == "parallel_complete":
            node = nodes.setdefault(
                node_id,
                {
                    "node_id": node_id,
                    "display_name": event.get("display_name") or node_id,
                    "started_at": timestamp,
                    "status": "running",
                },
            )
            node["total_files"] = data.get("total", 0)
            node["success_count"] = data.get("success_count", 0)
            node["error_count"] = data.get("error_count", 0)

    return nodes


def _hydrate_progress_timeline(
    progress_timeline: dict[str, Any] | None,
    *,
    status: str | None = None,
    error: str | None = None,
    execution_log: str | None = None,
) -> dict[str, Any] | None:
    if not progress_timeline:
        return progress_timeline

    hydrated = dict(progress_timeline)
    events = hydrated.get("events")
    if isinstance(events, list):
        hydrated_events = [
            _hydrate_progress_event(event)
            for event in events
            if isinstance(event, dict)
        ]
        hydrated["events"] = hydrated_events

        if not hydrated.get("steps"):
            hydrated["steps"] = _hydrate_progress_steps(hydrated_events)
        if not hydrated.get("nodes"):
            hydrated["nodes"] = _hydrate_progress_nodes(hydrated_events)
        if not hydrated.get("logs"):
            hydrated["logs"] = [
                line
                for event in hydrated_events
                if event.get("event") == "log"
                and (line := _progress_event_data(event).get("line"))
            ]

        for event in reversed(hydrated_events):
            terminal_status = _progress_terminal_status(event.get("event", ""))
            if terminal_status:
                hydrated.setdefault("terminal_status", terminal_status)
                terminal_error = _progress_event_data(event).get("error")
                if terminal_error is not None:
                    hydrated.setdefault("terminal_error", terminal_error)
                break

    if status is not None:
        hydrated.setdefault("terminal_status", status)
    if error is not None:
        hydrated.setdefault("terminal_error", error)
    if execution_log is not None:
        hydrated.setdefault("execution_log", execution_log)

    return hydrated


def _sql_quote(value: str) -> str:
    """Safely embed a string literal in the rebuild's generated SQL."""
    return "'" + value.replace("'", "''") + "'"


def _rebuild_workflow_runs_flipping_stale(
    db_path: str,
    *,
    started_before: Optional[datetime] = None,
    exclude_thread_ids: tuple[str, ...] = (),
) -> Optional[list[str]]:
    """Crash-safe recovery: rebuild ``workflow_runs`` with stale 'running' rows
    flipped to 'failed', WITHOUT any in-place index-backed DELETE/UPDATE.

    DuckDB maintains an ART index for the ``thread_id`` PRIMARY KEY (plus the
    secondary indexes). After a crash + WAL replay the index can desync from
    the table heap; an in-place ``UPDATE``/``DELETE`` then raises::

        Invalid Input Error: Failed to delete all rows from index.
        Only deleted 0 out of N rows.

    which DuckDB escalates to a FATAL error that invalidates the *entire*
    database for the lifetime of the process (#1362). Every later query
    against that connection then 500s with "database has been invalidated".

    A ``CREATE TABLE ... AS SELECT`` reads the heap and writes a brand-new
    table + fresh indexes, so it never touches the corrupt ART delete path.
    We DROP the old table and RENAME the new one into place inside a single
    transaction, so a crash mid-rebuild leaves the original intact.

    Args:
        db_path: Path to the library DuckDB file.
        started_before: When set, only rows with ``started_at < started_before``
            are flipped (mirrors ``recover_stale_runs`` max_age semantics).
            When ``None``, every ``running`` row is flipped (startup guard).

    Returns:
        The ``thread_id`` of every row flipped 'running' -> 'failed'. ``None``
        if the rebuild itself failed (caller should treat as "degraded, do not
        raise"). The ids — not just a count — because the caller must settle
        each dead run's documents through ``finalize_run_documents`` (#4379);
        a bare count cannot name what to settle.
    """
    # Use a FRESH connection: the caller's connection may already be poisoned
    # by the FatalException that sent us down this path.
    conn = connect_utc(db_path)
    try:
        # Build the status-flip CASE. Only non-terminal rows (optionally older
        # than the cutoff, and never a live run this process is tracking)
        # become 'failed'; everything else is copied verbatim. (#4316)
        flip_predicate = f"status IN ({_SWEEPABLE_STATUS_SQL})"
        if started_before is not None:
            flip_predicate += (
                " AND started_at < TIMESTAMP '"
                f"{started_before.strftime('%Y-%m-%d %H:%M:%S')}'"
            )
        if exclude_thread_ids:
            excluded = ", ".join(_sql_quote(t) for t in exclude_thread_ids)
            flip_predicate += f" AND thread_id NOT IN ({excluded})"

        status_expr = f"CASE WHEN {flip_predicate} THEN 'failed' ELSE status END"
        error_expr = (
            f"CASE WHEN {flip_predicate} "
            f"THEN COALESCE(error, '{_STALE_RUN_ERROR}') ELSE error END"
        )
        completed_expr = (
            f"CASE WHEN {flip_predicate} "
            "THEN COALESCE(completed_at, CURRENT_TIMESTAMP) ELSE completed_at END"
        )

        select_cols = []
        for col in _WORKFLOW_RUNS_COLUMNS:
            if col == "status":
                select_cols.append(f"{status_expr} AS status")
            elif col == "error":
                select_cols.append(f"{error_expr} AS error")
            elif col == "completed_at":
                select_cols.append(f"{completed_expr} AS completed_at")
            else:
                select_cols.append(col)
        select_expr = ", ".join(select_cols)

        # Name the rows we will flip (read-only SELECT — safe on a fresh conn).
        # Captured BEFORE the rebuild: afterwards the predicate no longer
        # matches them, because they are the rows the rebuild just flipped.
        flipped_ids = [
            row[0]
            for row in conn.execute(
                f"SELECT thread_id FROM workflow_runs WHERE {flip_predicate}"
            ).fetchall()
            if row and row[0]
        ]
        flipped = len(flipped_ids)

        conn.execute("BEGIN TRANSACTION")
        conn.execute("DROP TABLE IF EXISTS workflow_runs__rebuild")
        conn.execute(
            f"CREATE TABLE workflow_runs__rebuild AS "
            f"SELECT {select_expr} FROM workflow_runs"
        )
        conn.execute("DROP TABLE workflow_runs")
        conn.execute(
            "ALTER TABLE workflow_runs__rebuild RENAME TO workflow_runs"
        )
        conn.execute("COMMIT")

        # CREATE TABLE AS does NOT carry over the PRIMARY KEY or secondary
        # indexes — recreate them so query plans and uniqueness are preserved.
        # A UNIQUE index on thread_id reinstates the PK's enforcement.
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_runs_thread_id "
                "ON workflow_runs(thread_id)"
            )
        except Exception as idx_exc:  # pragma: no cover - defensive
            logger.warning(
                "workflow_runs rebuild: could not recreate thread_id unique "
                "index (non-fatal): %s",
                idx_exc,
            )
        for idx_name, idx_target in _WORKFLOW_RUNS_INDEXES:
            try:
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_target}"
                )
            except Exception as idx_exc:  # pragma: no cover - defensive
                logger.warning(
                    "workflow_runs rebuild: could not recreate index %s "
                    "(non-fatal): %s",
                    idx_name,
                    idx_exc,
                )

        logger.warning(
            "workflow_runs rebuilt crash-safe: flipped %d stale 'running' "
            "run(s) to 'failed' (sidestepped ART-index delete bug, #1362)",
            flipped,
        )
        return flipped_ids
    except Exception:
        # The rebuild itself failed. Roll back if a txn is open, log, and
        # report degraded — NEVER re-raise, or we re-poison library-open.
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        logger.exception(
            "workflow_runs crash-safe rebuild FAILED for %s — zombie rows "
            "left as-is; library remains open (#1362)",
            db_path,
        )
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _recover_stale_workflow_runs(
    conn: "duckdb.DuckDBPyConnection",
    db_path: str,
    *,
    started_before: Optional[datetime] = None,
    exclude_thread_ids: tuple[str, ...] = (),
) -> Optional[list[str]]:
    """Flip stale 'running' workflow_runs to 'failed' without ever leaving the
    connection (or the DB) in a poisoned state.

    Fast path: a normal in-place UPDATE on the supplied ``conn``.
    Fallback: if that raises ANY ``duckdb.Error`` (notably the FATAL
    "Failed to delete all rows from index"), the connection is now poisoned,
    so we discard it and rebuild the table from scratch on a fresh connection
    via :func:`_rebuild_workflow_runs_flipping_stale`.

    Args:
        conn: The (possibly-soon-to-be-poisoned) connection to try first.
        db_path: Library DuckDB path, used to open a fresh connection on fallback.
        started_before: Optional cutoff; see the rebuild helper.

    Returns:
        The ``thread_id`` of every flipped row, or ``None`` if even the rebuild
        failed (degraded). Ids rather than a count so the caller can settle
        each dead run's documents (#4379).
    """
    params: list = [_STALE_RUN_ERROR]
    where = f"status IN ({_SWEEPABLE_STATUS_SQL})"
    if started_before is not None:
        where += " AND started_at < ?"
    if exclude_thread_ids:
        placeholders = ", ".join("?" * len(exclude_thread_ids))
        where += f" AND thread_id NOT IN ({placeholders})"

    sql = f"""
        UPDATE workflow_runs
        SET status = 'failed',
            error = COALESCE(error, ?),
            completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)
        WHERE {where}
        RETURNING thread_id
    """
    if started_before is not None:
        params.append(started_before)
    params.extend(exclude_thread_ids)

    try:
        # Pre-count is cheap and lets us report even though RETURNING also works.
        result = conn.execute(sql, params)
        rows = result.fetchall() if result else []
        flipped_ids = [row[0] for row in rows if row and row[0]]
        flipped = len(flipped_ids)
        if flipped:
            logger.warning(
                "recover_stale_runs: flipped %d stale 'running' run(s) to "
                "'failed' (in-place) for %s",
                flipped,
                db_path,
            )
        return flipped_ids
    except duckdb.Error as exc:
        # Connection is now poisoned (FATAL index error or otherwise). Do NOT
        # touch `conn` again. Rebuild the table on a fresh connection.
        logger.warning(
            "recover_stale_runs: in-place UPDATE failed (%s: %s) — falling "
            "back to crash-safe table rebuild for %s (#1362)",
            type(exc).__name__,
            exc,
            db_path,
        )
        return _rebuild_workflow_runs_flipping_stale(
            db_path,
            started_before=started_before,
            exclude_thread_ids=exclude_thread_ids,
        )


class ActivityStore:
    """
    Persistent storage for activity events.

    Uses DuckDB for efficient querying and analytics.
    """

    def __init__(self, db_path: str):
        """Initialize activity store with database path."""
        self.db_path = db_path
        self._init_database()

    # ponytail: not a managed shared conn (#2508). Every method below opens a
    # FRESH ``conn = duckdb.connect(self.db_path)`` for the duration of one
    # operation and closes it — a connection-per-operation pattern, never the
    # package's managed Database connection. So the Database._lock seam and the
    # locked execute()/execute_fetchall() helpers do not apply here. Folding
    # ActivityStore onto the shared Database is a separate architectural call
    # (lead review).

    def _init_database(self) -> None:
        """Initialize database tables for activity tracking."""
        conn = connect_utc(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS activities (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    level TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    message TEXT NOT NULL,
                    workflow_id TEXT,
                    batch_id TEXT,
                    thread_id TEXT,
                    node_id TEXT,
                    metadata JSON,
                    duration_ms FLOAT,
                    error TEXT
                )
            """)

            # Workflow runs table - stores run-level data including code and logs
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    thread_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    workflow_name TEXT NOT NULL,
                    python_code TEXT,
                    execution_log TEXT,
                    status TEXT DEFAULT 'running',
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    duration_ms FLOAT,
                    error TEXT
                )
            """)

            # Add new columns for workflow snapshot, node mapping, progress, and diagram
            # These allow historical runs to be visualized even if workflow is deleted
            try:
                conn.execute(
                    "ALTER TABLE workflow_runs ADD COLUMN workflow_snapshot JSON"
                )
            except Exception:
                pass  # Column already exists

            try:
                conn.execute("ALTER TABLE workflow_runs ADD COLUMN node_name_map JSON")
            except Exception:
                pass  # Column already exists

            try:
                conn.execute(
                    "ALTER TABLE workflow_runs ADD COLUMN progress_timeline JSON"
                )
            except Exception:
                pass  # Column already exists

            try:
                # #4384/#4396: what the run was ACTUALLY scoped to, resolved by
                # the server. Without it a run records what workflow ran but
                # never what it ran ON, so Activity cannot report scope and an
                # over-scoped run is invisible until its effects show up in the
                # data — which is how #4396 was found.
                conn.execute(
                    "ALTER TABLE workflow_runs ADD COLUMN resolved_scope JSON"
                )
            except Exception:
                pass  # Column already exists

            try:
                conn.execute(
                    "ALTER TABLE workflow_runs ADD COLUMN diagram_mermaid TEXT"
                )
            except Exception:
                pass  # Column already exists

            # Indexes for efficient queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activities_timestamp
                ON activities(timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activities_type
                ON activities(type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activities_workflow_id
                ON activities(workflow_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activities_batch_id
                ON activities(batch_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activities_level
                ON activities(level)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow_id
                ON workflow_runs(workflow_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflow_runs_started_at
                ON workflow_runs(started_at DESC)
            """)

            # NOTE (#4316): the cutoff-less zombie sweep that used to run here
            # on EVERY ActivityStore construction is gone — reopening a library
            # mid-run constructed a fresh store and flipped LIVE runs to
            # 'failed' (F5). Recovery now happens only via
            # ActivityTracker/_recover_stale_runs_bg (activity.py), which
            # excludes the runs this process is actively tracking; the
            # crash-safe rebuild path (#1362) is preserved inside
            # _recover_stale_workflow_runs.
        finally:
            try:
                conn.close()
            except Exception:
                pass

    async def save(self, activity: Activity) -> None:
        """Save an activity to the database."""

        def _save():
            logger.info(f"ActivityStore.save: connecting to {self.db_path}")
            with duckdb_connection_lock(self.db_path):
                conn = connect_utc(self.db_path)
                try:
                    conn.execute(
                    """
                    INSERT INTO activities
                    (id, type, level, timestamp, message, workflow_id, batch_id,
                     thread_id, node_id, metadata, duration_ms, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        activity.id,
                        activity.type.value,
                        activity.level.value,
                        activity.timestamp,
                        activity.message,
                        activity.workflow_id,
                        activity.batch_id,
                        activity.thread_id,
                        activity.node_id,
                        json.dumps(activity.metadata) if activity.metadata else None,
                        activity.duration_ms,
                        activity.error,
                    ],
                )
                    logger.info(f"ActivityStore.save: INSERT successful for {activity.id}")
                except Exception as e:
                    logger.error(f"ActivityStore.save: INSERT failed: {e}")
                    raise
                finally:
                    conn.close()

        await asyncio.to_thread(_save)

    async def query(self, filter: ActivityFilter) -> list[Activity]:
        """Query activities with filtering."""

        def _query():
            conn = connect_utc(self.db_path)
            try:
                conditions = []
                params = []

                if filter.types:
                    placeholders = ", ".join("?" * len(filter.types))
                    conditions.append(f"type IN ({placeholders})")
                    params.extend([t.value for t in filter.types])

                if filter.levels:
                    placeholders = ", ".join("?" * len(filter.levels))
                    conditions.append(f"level IN ({placeholders})")
                    params.extend([lvl.value for lvl in filter.levels])

                if filter.workflow_id:
                    conditions.append("workflow_id = ?")
                    params.append(filter.workflow_id)

                if filter.batch_id:
                    conditions.append("batch_id = ?")
                    params.append(filter.batch_id)

                if filter.thread_id:
                    conditions.append("thread_id = ?")
                    params.append(filter.thread_id)

                if filter.since:
                    conditions.append("timestamp >= ?")
                    params.append(filter.since)

                if filter.until:
                    conditions.append("timestamp <= ?")
                    params.append(filter.until)

                if filter.search:
                    conditions.append("message ILIKE ?")
                    params.append(f"%{filter.search}%")

                where_clause = " AND ".join(conditions) if conditions else "1=1"

                query = f"""
                    SELECT id, type, level, timestamp, message, workflow_id,
                           batch_id, thread_id, node_id, metadata, duration_ms, error
                    FROM activities
                    WHERE {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """
                params.extend([filter.limit, filter.offset])

                result = conn.execute(query, params).fetchall()

                activities = []
                for row in result:
                    activities.append(
                        Activity(
                            id=row[0],
                            type=ActivityType(row[1]),
                            level=ActivityLevel(row[2]),
                            # naive stored value IS UTC (#4347) — re-attach offset
                            timestamp=ensure_utc(row[3]),
                            message=row[4],
                            workflow_id=row[5],
                            batch_id=row[6],
                            thread_id=row[7],
                            node_id=row[8],
                            metadata=json.loads(row[9]) if row[9] else {},
                            duration_ms=row[10],
                            error=row[11],
                        )
                    )
                return activities
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def get_stats(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> ActivityStats:
        """Get aggregated activity statistics."""
        if not since:
            since = utc_now() - timedelta(hours=24)
        if not until:
            until = utc_now()

        def _get_stats():
            conn = connect_utc(self.db_path)
            try:
                # Count by type
                type_counts = conn.execute(
                    """
                    SELECT type, COUNT(*) as count
                    FROM activities
                    WHERE timestamp >= ? AND timestamp <= ?
                    GROUP BY type
                """,
                    [since, until],
                ).fetchall()

                # Count by level
                level_counts = conn.execute(
                    """
                    SELECT level, COUNT(*) as count
                    FROM activities
                    WHERE timestamp >= ? AND timestamp <= ?
                    GROUP BY level
                """,
                    [since, until],
                ).fetchall()

                # Average workflow duration
                avg_duration = conn.execute(
                    """
                    SELECT AVG(duration_ms)
                    FROM activities
                    WHERE type = 'workflow_completed'
                    AND timestamp >= ? AND timestamp <= ?
                    AND duration_ms IS NOT NULL
                """,
                    [since, until],
                ).fetchone()[0]

                # Success rate (completed vs failed workflows)
                workflow_counts = conn.execute(
                    """
                    SELECT type, COUNT(*) as count
                    FROM activities
                    WHERE type IN ('workflow_completed', 'workflow_failed')
                    AND timestamp >= ? AND timestamp <= ?
                    GROUP BY type
                """,
                    [since, until],
                ).fetchall()

                completed = sum(
                    c[1] for c in workflow_counts if c[0] == "workflow_completed"
                )
                failed = sum(c[1] for c in workflow_counts if c[0] == "workflow_failed")
                total_workflows = completed + failed
                success_rate = (
                    (completed / total_workflows * 100)
                    if total_workflows > 0
                    else 100.0
                )

                # Total count
                total = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM activities
                    WHERE timestamp >= ? AND timestamp <= ?
                """,
                    [since, until],
                ).fetchone()[0]

                return ActivityStats(
                    total_activities=total,
                    activities_by_type={t[0]: t[1] for t in type_counts},
                    activities_by_level={lc[0]: lc[1] for lc in level_counts},
                    error_count=sum(lc[1] for lc in level_counts if lc[0] == "error"),
                    warning_count=sum(
                        lc[1] for lc in level_counts if lc[0] == "warning"
                    ),
                    avg_workflow_duration_ms=avg_duration,
                    success_rate=success_rate,
                    period_start=since,
                    period_end=until,
                )
            finally:
                conn.close()

        return await asyncio.to_thread(_get_stats)

    def delete_old_sync(self, older_than: datetime) -> int:
        """Delete activities older than specified date (sync, for use inside registry.invoke)."""
        conn = connect_utc(self.db_path)
        try:
            result = conn.execute(
                """
                DELETE FROM activities
                WHERE timestamp < ?
            """,
                [older_than],
            )
            return result.fetchone()[0] if result else 0
        finally:
            conn.close()

    async def delete_old(self, older_than: datetime) -> int:
        """Delete activities older than specified date."""
        return await asyncio.to_thread(self.delete_old_sync, older_than)

    # =========================================================================
    # Workflow Run Methods
    # =========================================================================

    async def save_workflow_run(
        self,
        thread_id: str,
        workflow_id: str,
        workflow_name: str,
        python_code: Optional[str] = None,
        execution_log: Optional[str] = None,
        workflow_snapshot: Optional[dict] = None,
        node_name_map: Optional[dict[str, str]] = None,
        progress_timeline: Optional[dict] = None,
        diagram_mermaid: Optional[str] = None,
        started_at: Optional[datetime] = None,
        status: str = "running",
        resolved_scope: Optional[dict] = None,
    ) -> None:
        """Save a new workflow run record.

        ``resolved_scope`` is what the SERVER resolved the run to operate on —
        not what the client asked for (#4384/#4396). Recording the client's
        request would hide exactly the defect worth catching: #4396 was a
        client sending a whole folder for a one-file selection, and only the
        resolved set shows that.
        """

        def _save():
            conn = connect_utc(self.db_path)
            try:
                # Convert dicts to JSON strings
                workflow_snapshot_json = (
                    json.dumps(workflow_snapshot) if workflow_snapshot else None
                )
                node_name_map_json = (
                    json.dumps(node_name_map) if node_name_map else None
                )
                progress_timeline_json = (
                    json.dumps(progress_timeline) if progress_timeline else None
                )
                resolved_scope_json = (
                    json.dumps(resolved_scope) if resolved_scope else None
                )

                conn.execute(
                    """
                    INSERT INTO workflow_runs
                    (thread_id, workflow_id, workflow_name, python_code, execution_log,
                     workflow_snapshot, node_name_map, progress_timeline,
                     diagram_mermaid, status, started_at, resolved_scope)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (thread_id) DO UPDATE SET
                        python_code = COALESCE(EXCLUDED.python_code, workflow_runs.python_code),
                        execution_log = COALESCE(EXCLUDED.execution_log, workflow_runs.execution_log),
                        workflow_snapshot = COALESCE(EXCLUDED.workflow_snapshot, workflow_runs.workflow_snapshot),
                        node_name_map = COALESCE(EXCLUDED.node_name_map, workflow_runs.node_name_map),
                        progress_timeline = COALESCE(EXCLUDED.progress_timeline, workflow_runs.progress_timeline),
                        diagram_mermaid = COALESCE(EXCLUDED.diagram_mermaid, workflow_runs.diagram_mermaid),
                        resolved_scope = COALESCE(EXCLUDED.resolved_scope, workflow_runs.resolved_scope),
                        status = EXCLUDED.status,
                        workflow_name = EXCLUDED.workflow_name
                """,
                    [
                        thread_id,
                        workflow_id,
                        workflow_name,
                        python_code,
                        execution_log,
                        workflow_snapshot_json,
                        node_name_map_json,
                        progress_timeline_json,
                        diagram_mermaid,
                        status,
                        started_at or datetime.now(timezone.utc),
                        resolved_scope_json,
                    ],
                )
            finally:
                conn.close()

        await asyncio.to_thread(_save)

    async def update_workflow_run(
        self,
        thread_id: str,
        status: Optional[str] = None,
        execution_log: Optional[str] = None,
        progress_timeline: Optional[dict] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
        completed_at: Optional[datetime] = None,
    ) -> None:
        """Update an existing workflow run record."""

        def _update():
            conn = connect_utc(self.db_path)
            try:
                updates = []
                params = []

                if status is not None:
                    updates.append("status = ?")
                    params.append(status)
                if execution_log is not None:
                    updates.append("execution_log = ?")
                    params.append(execution_log)
                if progress_timeline is not None:
                    updates.append("progress_timeline = ?")
                    params.append(json.dumps(progress_timeline))
                if duration_ms is not None:
                    updates.append("duration_ms = ?")
                    params.append(duration_ms)
                if error is not None:
                    updates.append("error = ?")
                    params.append(error)
                if completed_at is not None:
                    updates.append("completed_at = ?")
                    params.append(completed_at)

                if updates:
                    params.append(thread_id)
                    conn.execute(
                        f"""
                        UPDATE workflow_runs
                        SET {", ".join(updates)}
                        WHERE thread_id = ?
                    """,
                        params,
                    )
            finally:
                conn.close()

        await asyncio.to_thread(_update)

    async def append_execution_log(self, thread_id: str, log_line: str) -> None:
        """Append a line to the execution log."""

        def _append():
            conn = connect_utc(self.db_path)
            try:
                conn.execute(
                    """
                    UPDATE workflow_runs
                    SET execution_log = COALESCE(execution_log, '') || ? || '\n'
                    WHERE thread_id = ?
                """,
                    [log_line, thread_id],
                )
            finally:
                conn.close()

        await asyncio.to_thread(_append)

    def _row_to_workflow_run(self, row: tuple) -> WorkflowRun:
        """Convert a database row to a WorkflowRun instance."""
        workflow_snapshot = json.loads(row[10]) if row[10] else None
        node_name_map = json.loads(row[11]) if row[11] else None
        progress_timeline = json.loads(row[12]) if row[12] else None
        progress_timeline = _hydrate_progress_timeline(
            progress_timeline,
            status=row[5],
            error=row[9],
            execution_log=row[4],
        )

        return WorkflowRun(
            thread_id=row[0],
            workflow_id=row[1],
            workflow_name=row[2],
            python_code=row[3],
            execution_log=row[4],
            status=row[5],
            # DuckDB TIMESTAMP columns are naive; by the #4347 contract a stored
            # naive value IS UTC, so re-attach the offset on the way out rather
            # than letting an offset-less ISO string reach the client.
            started_at=ensure_utc(row[6]),
            completed_at=ensure_utc(row[7]),
            duration_ms=row[8],
            error=row[9],
            workflow_snapshot=workflow_snapshot,
            node_name_map=node_name_map,
            progress_timeline=progress_timeline,
            diagram_mermaid=row[13],
            # #4384: what the run was scoped to. Index 14 — the SELECTs
            # feeding this mapping all list resolved_scope last.
            resolved_scope=json.loads(row[14]) if len(row) > 14 and row[14] else None,
        )

    async def get_workflow_run(self, thread_id: str) -> Optional[WorkflowRun]:
        """Get a workflow run by thread_id."""

        def _get():
            conn = connect_utc(self.db_path)
            try:
                result = conn.execute(
                    """
                    SELECT thread_id, workflow_id, workflow_name, python_code,
                           execution_log, status, started_at, completed_at,
                           duration_ms, error, workflow_snapshot, node_name_map,
                           progress_timeline, diagram_mermaid, resolved_scope
                    FROM workflow_runs
                    WHERE thread_id = ?
                """,
                    [thread_id],
                ).fetchone()

                if result:
                    return self._row_to_workflow_run(result)
                return None
            finally:
                conn.close()

        return await asyncio.to_thread(_get)

    async def delete_workflow_run(self, thread_id: str) -> int:
        """Mark a persisted workflow run as deleted."""

        def _delete():
            conn = connect_utc(self.db_path)
            try:
                rows = conn.execute(
                    """
                    UPDATE workflow_runs
                    SET status = 'deleted',
                        completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                        execution_log = COALESCE(execution_log, '') || 'Run history deleted\n'
                    WHERE thread_id = ?
                    RETURNING thread_id
                    """,
                    [thread_id],
                ).fetchall()
                return len(rows)
            finally:
                conn.close()

        return await asyncio.to_thread(_delete)

    async def list_workflow_runs(
        self,
        workflow_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[WorkflowRun]:
        """List workflow runs, optionally filtered by workflow_id."""

        def _list():
            conn = connect_utc(self.db_path)
            try:
                if workflow_id:
                    result = conn.execute(
                        """
                        SELECT thread_id, workflow_id, workflow_name, python_code,
                               execution_log, status, started_at, completed_at,
                               duration_ms, error, workflow_snapshot, node_name_map,
                               progress_timeline, diagram_mermaid, resolved_scope
                        FROM workflow_runs
                        WHERE workflow_id = ?
                        ORDER BY started_at DESC
                        LIMIT ?
                    """,
                        [workflow_id, limit],
                    ).fetchall()
                else:
                    result = conn.execute(
                        """
                        SELECT thread_id, workflow_id, workflow_name, python_code,
                               execution_log, status, started_at, completed_at,
                               duration_ms, error, workflow_snapshot, node_name_map,
                               progress_timeline, diagram_mermaid, resolved_scope
                        FROM workflow_runs
                        ORDER BY started_at DESC
                        LIMIT ?
                    """,
                        [limit],
                    ).fetchall()

                return [self._row_to_workflow_run(row) for row in result]
            finally:
                conn.close()

        return await asyncio.to_thread(_list)

    async def recover_stale_runs(
        self,
        max_age_hours: int = 2,
        exclude_thread_ids: tuple[str, ...] = (),
    ) -> list[str]:
        """Transition stale non-terminal workflow_run rows to 'failed' and
        return the ``thread_id`` of every run flipped.

        Sweeps EVERY non-terminal status — 'running', 'accepted', 'paused'
        (#4316) — for runs whose worker died without reaching a terminal
        state (crash, OOM, app restart, or a dev-loop reload killing the
        worker mid-run — #4379). Only rows older than ``max_age_hours`` are
        touched, and runs named in ``exclude_thread_ids`` (the ones THIS
        process is actively tracking) are never flipped, so reopening a
        library mid-run can't fail a live run (F5).

        The ids matter because flipping the RUN row is only half of a
        terminal transition: the documents that run left at
        ``Status.processing`` must also be settled, and only the caller (which
        has the library ``Database``) can do that. Returning ids rather than a
        count is what makes that possible (#4379).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        def _recover():
            # Crash-safe: in-place UPDATE first, table rebuild on ART-index
            # FATAL (#1362). Never poisons the live library connection.
            conn = connect_utc(self.db_path)
            try:
                recovered = _recover_stale_workflow_runs(
                    conn,
                    self.db_path,
                    started_before=cutoff,
                    exclude_thread_ids=tuple(exclude_thread_ids),
                )
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            # None means even the rebuild failed; nothing was flipped, so
            # there is nothing for the caller to settle either.
            return recovered or []

        return await asyncio.to_thread(_recover)
