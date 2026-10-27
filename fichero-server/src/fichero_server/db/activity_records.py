"""Activity events and workflow runs: the persistence layer's own SQL for them (#5645).

Every statement runs on the library's one managed connection (`Database.execute*`, under its lock), on the tables of
`ActivityEventRecord` and `WorkflowRunRecord`. Here, not in the store, because these reads are ordered and paged in SQL
(a library can hold tens of thousands of runs) and these writes touch one column of a big row (a run's log grows by a
few lines at each node boundary): `Database.save` and `query` do neither. Each write is one statement, so none holds
the library's lock for longer than it takes.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

EVENTS = "activityeventrecords"
RUNS = "workflowrunrecords"
#: A run's log, one row per line (#5711).
LINES = "workflowrunloglines"
#: Recorded once no run's log is a value from before #5711 any more (`workflows.run_log_tidy`).
LOGS_AS_LINES_SETTING = "run_logs_as_lines_5711"

#: A dead process leaves these statuses behind (#4316); 'paused' is not one (#5357: it needs no process).
SWEEPABLE_STATUSES = ("running", "accepted")
_SWEEPABLE_SQL = ", ".join(f"'{s}'" for s in SWEEPABLE_STATUSES)

#: Every column of a run, in the order `run_row` reads them.
RUN_COLUMNS = ("id", "workflow_id", "workflow_name", "python_code", "execution_log", "status", "started_at",
               "completed_at", "duration_ms", "error", "workflow_snapshot", "node_name_map", "progress_timeline",
               "diagram_mermaid", "resolved_scope", "run_usage", "estimated_cost")
#: A run as a list shows it (#5645): no code, log, snapshot, node map or diagram, whose size grows with the run, so a
#: poll of 50 runs every few seconds reads 50 small rows whatever the logs weigh. Its progress timeline stays: the run
#: account (Activity's progress) reads it.
LIST_COLUMNS = ("id", "workflow_id", "workflow_name", "NULL", "NULL", "status", "started_at", "completed_at",
                "duration_ms", "error", "NULL", "NULL", "progress_timeline", "NULL", "resolved_scope", "run_usage",
                "estimated_cost")
EVENT_COLUMNS = ("id", "type", "level", "timestamp", "message", "workflow_id", "batch_id", "thread_id", "node_id",
                 "metadata", "duration_ms", "error")


def _json(value: Any) -> Optional[str]:
    return json.dumps(value) if value else None


# --- events ------------------------------------------------------------------------------------------------------


def insert_event(db: Any, values: dict[str, Any]) -> None:
    """One event, a plain INSERT (a new row: no upsert, duckdb#26830)."""
    db.execute(f"INSERT INTO {EVENTS} ({', '.join(EVENT_COLUMNS)}) VALUES ({', '.join('?' for _ in EVENT_COLUMNS)})",
               [values.get(c) if c != "metadata" else _json(values.get("metadata")) for c in EVENT_COLUMNS])


def query_events(db: Any, *, types: list[str], levels: list[str], workflow_id: Optional[str],
                 batch_id: Optional[str], thread_id: Optional[str], since: Optional[datetime],
                 until: Optional[datetime], search: Optional[str], limit: int, offset: int) -> list[tuple]:
    """The events matching a filter, newest first. A deleted run's events never show (#4960: an anti-join in SQL, so
    the cost never grows with how many runs were deleted); an event with no run is never excluded."""
    conditions, params = [], []
    for column, values in (("type", types), ("level", levels)):
        if values:
            conditions.append(f"{column} IN ({', '.join('?' for _ in values)})")
            params.extend(values)
    for column, value in (("workflow_id", workflow_id), ("batch_id", batch_id), ("thread_id", thread_id)):
        if value:
            conditions.append(f"{column} = ?")
            params.append(value)
    if since:
        conditions.append("timestamp >= ?")
        params.append(since)
    if until:
        conditions.append("timestamp <= ?")
        params.append(until)
    if search:
        conditions.append("message ILIKE ?")
        params.append(f"%{search}%")
    conditions.append(f"(thread_id IS NULL OR thread_id NOT IN (SELECT id FROM {RUNS} WHERE status = 'deleted'))")
    return db.execute_fetchall(
        f"SELECT {', '.join(EVENT_COLUMNS)} FROM {EVENTS} WHERE {' AND '.join(conditions)} "
        f"ORDER BY timestamp DESC LIMIT ? OFFSET ?", [*params, limit, offset])


def event_stats(db: Any, since: datetime, until: datetime) -> dict[str, Any]:
    """Counts by type and by level, the average workflow duration, and completed against failed workflows."""
    window = "timestamp >= ? AND timestamp <= ?"
    by_type = db.execute_fetchall(f"SELECT type, COUNT(*) FROM {EVENTS} WHERE {window} GROUP BY type", [since, until])
    by_level = db.execute_fetchall(f"SELECT level, COUNT(*) FROM {EVENTS} WHERE {window} GROUP BY level",
                                   [since, until])
    avg = db.execute_fetchone(f"SELECT AVG(duration_ms) FROM {EVENTS} WHERE type = 'workflow_completed' AND {window} "
                              "AND duration_ms IS NOT NULL", [since, until])[0]
    total = db.execute_fetchone(f"SELECT COUNT(*) FROM {EVENTS} WHERE {window}", [since, until])[0]
    return {"by_type": by_type, "by_level": by_level, "avg_duration": avg, "total": total}


def delete_events_before(db: Any, older_than: datetime) -> int:
    row = db.execute_fetchone(f"DELETE FROM {EVENTS} WHERE timestamp < ?", [older_than])
    return row[0] if row else 0


def delete_event(db: Any, event_id: str) -> int:
    row = db.execute_fetchone(f"DELETE FROM {EVENTS} WHERE id = ?", [event_id])
    return row[0] if row else 0


# --- runs --------------------------------------------------------------------------------------------------------


def upsert_run(db: Any, *, thread_id: str, workflow_id: str, workflow_name: str, python_code: Optional[str],
               execution_log: Optional[str], workflow_snapshot: Optional[dict], node_name_map: Optional[dict],
               progress_timeline: Optional[dict], diagram_mermaid: Optional[str], status: str, started_at: datetime,
               resolved_scope: Optional[dict], estimated_cost: Optional[float]) -> None:
    """A run's record at its start, or again at a restart: a value not given keeps the one kept."""
    db.execute(
        f"""INSERT INTO {RUNS} (id, workflow_id, workflow_name, python_code, execution_log, workflow_snapshot,
            node_name_map, progress_timeline, diagram_mermaid, status, started_at, resolved_scope, estimated_cost)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO UPDATE SET
            python_code = COALESCE(EXCLUDED.python_code, {RUNS}.python_code),
            workflow_snapshot = COALESCE(EXCLUDED.workflow_snapshot, {RUNS}.workflow_snapshot),
            node_name_map = COALESCE(EXCLUDED.node_name_map, {RUNS}.node_name_map),
            progress_timeline = COALESCE(EXCLUDED.progress_timeline, {RUNS}.progress_timeline),
            diagram_mermaid = COALESCE(EXCLUDED.diagram_mermaid, {RUNS}.diagram_mermaid),
            resolved_scope = COALESCE(EXCLUDED.resolved_scope, {RUNS}.resolved_scope),
            estimated_cost = COALESCE(EXCLUDED.estimated_cost, {RUNS}.estimated_cost),
            status = EXCLUDED.status,
            workflow_name = EXCLUDED.workflow_name""",
        [thread_id, workflow_id, workflow_name, python_code, None, _json(workflow_snapshot),
         _json(node_name_map), _json(progress_timeline), diagram_mermaid, status, started_at,
         _json(resolved_scope), estimated_cost])
    if execution_log is not None:
        put_log(db, thread_id, execution_log, replace=True)


def update_run(db: Any, thread_id: str, fields: dict[str, Any]) -> None:
    """Set the given columns of one run (a None value is not given, as before); a log given replaces its lines."""
    log = fields.get("execution_log")
    given = {k: (json.dumps(v) if k in ("progress_timeline", "run_usage") else v)
             for k, v in fields.items() if v is not None and k != "execution_log"}
    if given:
        db.execute(f"UPDATE {RUNS} SET {', '.join(f'{k} = ?' for k in given)} WHERE id = ?",
                   [*given.values(), thread_id])
    if log is not None:
        put_log(db, thread_id, log, replace=True)


_INSERT_LINES = (f"INSERT INTO {LINES} (id, run_id, seq, line) SELECT gen_random_uuid()::VARCHAR, ?, {{base}} + s, x "
                 "FROM (SELECT unnest(?::VARCHAR[]) AS x, unnest(range(1, len(?::VARCHAR[]) + 1)) AS s)")


def move_values_into_lines(db: Any, thread_ids: list[str]) -> int:
    """The logs of these runs that are still values from before #5711, moved into lines: numbered far below 0, so a
    line added later follows them; checked against the value they came from, and only then the value cleared. Raises
    when a log does not read back, so the caller's transaction rolls back and the value stays. Returns how many runs
    it moved; a run with no value is left as it is (the common case: one point read)."""
    if not thread_ids:
        return 0
    marks = ", ".join("?" for _ in thread_ids)
    ids = [r[0] for r in db.execute_fetchall(
        f"SELECT id FROM {RUNS} WHERE id IN ({marks}) AND execution_log IS NOT NULL", list(thread_ids))]
    if not ids:
        return 0
    marks = ", ".join("?" for _ in ids)
    # A constant offset, not the run's own line count: carrying the count beside every line made it 6x slower.
    db.execute(f"INSERT INTO {LINES} (id, run_id, seq, line) SELECT gen_random_uuid()::VARCHAR, id, s - 1000000000, "
               "part FROM (SELECT id, unnest(string_split(execution_log, chr(10))) AS part, "
               "unnest(range(1, len(string_split(execution_log, chr(10))) + 1)) AS s "
               f"FROM {RUNS} WHERE id IN ({marks}) AND execution_log <> '')", ids)
    wrong = db.execute_fetchall(
        f"SELECT r.id FROM {RUNS} r WHERE r.id IN ({marks}) AND r.execution_log <> '' AND r.execution_log IS "
        f"DISTINCT FROM (SELECT string_agg(l.line, chr(10) ORDER BY l.seq) FROM {LINES} l WHERE l.run_id = r.id "
        "AND l.seq <= 0)", ids)
    if wrong:
        raise RuntimeError(f"{len(wrong)} run logs did not read back from their lines (first: {wrong[0][0]}); "
                           "left as they were")
    db.execute(f"UPDATE {RUNS} SET execution_log = NULL WHERE id IN ({marks})", ids)
    return len(ids)


def logs_as_lines_done(db: Any) -> bool:
    """Whether this library is marked as having no run log left as a value (`LOGS_AS_LINES_SETTING`)."""
    return db.execute_fetchone("SELECT 1 FROM librarysettings WHERE id = ?", [LOGS_AS_LINES_SETTING]) is not None


def mark_logs_as_lines_done(db: Any) -> None:
    db.execute("INSERT INTO librarysettings (id, value, updated_at) VALUES (?, '1', now()) ON CONFLICT (id) DO NOTHING",
               [LOGS_AS_LINES_SETTING])


def runs_with_values(db: Any, limit: int) -> list[str]:
    """Up to `limit` runs whose logs are still values from before #5711."""
    return [r[0] for r in db.execute_fetchall(
        f"SELECT id FROM {RUNS} WHERE execution_log IS NOT NULL LIMIT ?", [limit])]


def put_log(db: Any, thread_id: str, text: str, *, replace: bool) -> None:
    """A run's log written as lines (#5711): replaced (its lines, and any value kept from before, gone first), or
    `text`'s lines added after its last, so a write is as big as what it adds. A log still a value from before is
    moved into lines first, in the same transaction (a run written again folds itself)."""
    lines = text.split("\n") if text else []
    if replace:
        with db.transaction():
            db.execute(f"DELETE FROM {LINES} WHERE run_id = ?", [thread_id])
            db.execute(f"UPDATE {RUNS} SET execution_log = NULL WHERE id = ? AND execution_log IS NOT NULL",
                       [thread_id])
            if lines:
                db.execute(_INSERT_LINES.format(base="0"), [thread_id, lines, lines])
    elif lines:
        with db.transaction():
            move_values_into_lines(db, [thread_id])
            db.execute(_INSERT_LINES.format(base=f"(SELECT COALESCE(max(seq), 0) FROM {LINES} WHERE run_id = ?)"),
                       [thread_id, thread_id, lines, lines])


def read_log(db: Any, thread_id: str, kept: Optional[str]) -> Optional[str]:
    """A run's log: a value kept from before #5711 that is not moved into lines yet, then its lines, joined."""
    joined = db.execute_fetchone(f"SELECT string_agg(line, chr(10) ORDER BY seq) FROM {LINES} WHERE run_id = ?",
                                 [thread_id], committed=True)[0]
    parts = [p for p in (kept or None, joined) if p is not None]
    return "\n".join(parts) if parts else None


def flush_node_boundary(db: Any, thread_id: str, progress_timeline: dict, log_text: str, *, replace: bool) -> None:
    """A node-boundary flush (#4314): the progress timeline, and the log either replaced (a run's first flush in
    this process, as before) or only its new lines added (#5711: rows of their own, so neither the flush nor the
    write-ahead log it grows follows the log's size)."""
    db.execute(f"UPDATE {RUNS} SET progress_timeline = ? WHERE id = ?", [json.dumps(progress_timeline), thread_id])
    if replace or log_text:
        put_log(db, thread_id, log_text, replace=replace)


def get_run(db: Any, thread_id: str) -> Optional[tuple]:
    """Every column of one run, its log read from its lines (#5711)."""
    row = db.execute_fetchone(f"SELECT {', '.join(RUN_COLUMNS)} FROM {RUNS} WHERE id = ?", [thread_id], committed=True)
    if row is None:
        return None
    at = RUN_COLUMNS.index("execution_log")
    return (*row[:at], read_log(db, thread_id, row[at]), *row[at + 1:])


def list_runs(db: Any, *, workflow_id: Optional[str], statuses: Optional[list[str]], exclude_deleted: bool,
              limit: int, offset: int) -> list[tuple]:
    """Runs newest first, paged in SQL, each in the light projection (`LIST_COLUMNS`)."""
    where, params = [], []
    if workflow_id:
        where.append("workflow_id = ?")
        params.append(workflow_id)
    if statuses:
        where.append(f"status IN ({', '.join('?' for _ in statuses)})")
        params.extend(statuses)
    elif exclude_deleted:
        where.append("status != 'deleted'")
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    return db.execute_fetchall(
        f"SELECT {', '.join(LIST_COLUMNS)} FROM {RUNS} {where_sql} ORDER BY started_at DESC, id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset], committed=True)


def soft_delete_runs(db: Any, thread_ids: list[str], *, skip_running: bool) -> list[str]:
    """Mark runs deleted (nothing is destroyed, #4960); their ids."""
    if not thread_ids:
        return []
    running = " AND status != 'running'" if skip_running else ""
    rows = db.execute_fetchall(
        f"UPDATE {RUNS} SET status = 'deleted', completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP) "
        f"WHERE id IN ({', '.join('?' for _ in thread_ids)}){running} RETURNING id", list(thread_ids))
    deleted = [row[0] for row in rows if row and row[0]]
    if deleted:  # the log says so, a line of its own after its last (#5711)
        with db.transaction():
            move_values_into_lines(db, deleted)
            db.execute(f"INSERT INTO {LINES} (id, run_id, seq, line) SELECT gen_random_uuid()::VARCHAR, r, "
                       f"COALESCE((SELECT max(seq) FROM {LINES} WHERE run_id = r), 0) + 1, 'Run history deleted' "
                       "FROM (SELECT unnest(?::VARCHAR[]) AS r)", [deleted])
    return deleted


def run_ids_by_status(db: Any, statuses: list[str]) -> list[str]:
    if not statuses:
        return []
    rows = db.execute_fetchall(f"SELECT id FROM {RUNS} WHERE status IN ({', '.join('?' for _ in statuses)}) "
                               "AND status != 'deleted'", list(statuses))
    return [row[0] for row in rows if row and row[0]]


def unfinished_runs(db: Any) -> list[tuple[str, Any]]:
    """(thread id, started at) of every run whose record says it is not finished."""
    return [(r[0], r[1]) for r in db.execute_fetchall(
        f"SELECT id, started_at FROM {RUNS} WHERE status IN ({_SWEEPABLE_SQL})")]


def mark_run_failed(db: Any, thread_id: str, reason: str) -> None:
    db.execute(f"UPDATE {RUNS} SET status = 'failed', error = ?, completed_at = COALESCE(completed_at, "
               "CURRENT_TIMESTAMP) WHERE id = ?", [reason, thread_id])


def recover_stale(db: Any, *, error: str, started_before: Optional[datetime],
                  exclude_thread_ids: tuple[str, ...]) -> list[str]:
    """Flip runs a dead process left unfinished to failed; their ids (the caller settles their documents, #4379)."""
    where, params = [f"status IN ({_SWEEPABLE_SQL})"], [error]
    if started_before is not None:
        where.append("started_at < ?")
        params.append(started_before)
    if exclude_thread_ids:
        where.append(f"id NOT IN ({', '.join('?' for _ in exclude_thread_ids)})")
        params.extend(exclude_thread_ids)
    rows = db.execute_fetchall(
        f"UPDATE {RUNS} SET status = 'failed', error = COALESCE(error, ?), completed_at = COALESCE(completed_at, "
        f"CURRENT_TIMESTAMP) WHERE {' AND '.join(where)} RETURNING id", params)
    return [row[0] for row in rows if row and row[0]]


def run_workflow_name(db: Any, run_id: str) -> Optional[str]:
    """The workflow a run ran, by name (the Inspector's 'who read it' names the step), or None for no such run."""
    row = db.execute_fetchone("SELECT workflow_name FROM workflowrunrecords WHERE id = ?", [run_id])
    return row[0] if row else None
