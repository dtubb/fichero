"""
ActivityStore -- activity events and workflow runs, kept as models through the library's one managed Database (#5645).

Included by activity.py via composition (ActivityTracker.store). The rows are `ActivityEventRecord` and
`WorkflowRunRecord` (`models.activity_records`); the ordered, paged and partial SQL is the persistence layer's
(`db.activity_records`), on the managed connection under its lock. Callers get the `Activity` and `WorkflowRun` they
always did. A library made before this kept them in `activities` and `workflow_runs`; `Database._fold_activity_tables`
copies them once, at open.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from fichero_server.core.timeutil import ensure_utc, utc_now
from typing import Any, Optional

from fichero_server.workflows.activity_types import (
    Activity,
    ActivityFilter,
    ActivityLevel,
    ActivityStats,
    ActivityType,
    WorkflowRun,
)

logger = logging.getLogger(__name__)


class _Records:
    """`db.activity_records`, imported at first use, not at engine start (#3950's import budget)."""

    def __getattr__(self, name: str) -> Any:
        from fichero_server.db import activity_records

        return getattr(activity_records, name)


records = _Records()

_STALE_RUN_ERROR = (
    "Run interrupted: process crashed or was killed before completion "
    "(recovered on startup)."
)

# Recovery sweeps the statuses a dead process leaves behind (#4316): 'running'
# rows whose worker died and 'accepted' rows whose worker never started. A
# 'paused' run is NOT swept (#5357, `activity.durable.paused-stays-paused`): it
# needs no process, and its Resume carries on from its checkpoint on disk, after
# a relaunch as before one. Inlined as SQL fragments below.

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

        if event_type not in {"file_start", "file_running", "file_complete", "file_error"}:
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

        if event_type == "file_running":
            step["running_at"] = timestamp  # it got its slot: its own time counts from here (#6178)
        elif event_type == "file_complete":
            step["completed_at"] = timestamp
            step["status"] = "success"
            started_at = step.get("running_at") or step.get("started_at")
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


def unfinished_runs(db: Any) -> list[tuple[str, Any]]:
    """(thread id, started at) of every run whose record says it is not finished, through the project's own
    connection (opening a project, #5555)."""
    return records.unfinished_runs(db)


def mark_run_failed(db: Any, thread_id: str, reason: str) -> None:
    """A run's record ends failed with `reason` (an interrupted run, #5555)."""
    records.mark_run_failed(db, thread_id, reason)


class ActivityStore:
    """Activity events and workflow runs of one library, through its one managed Database (#5645)."""

    def __init__(self, db_path: str):
        """The store for the library whose database file is `db_path`, opened now as it always was."""
        self.db_path = db_path
        self.db  # noqa: B018 -- the open (and its on-open work) happens at the store's making, not its first use

    @property
    def db(self) -> Any:
        """The library's managed Database, looked up on each use (#6238): a store outlives a close and reopen of its
        library, and the Database it was built with is closed for good after it."""
        from fichero_server.db.manager import database_for_file

        return database_for_file(self.db_path)

    async def save(self, activity: Activity) -> None:
        """Save an activity to the database."""
        await asyncio.to_thread(self.save_now, activity)

    def save_now(self, activity: Activity) -> None:
        """Save an activity on the caller's thread: for a caller with no event loop (a job or timer thread,
        `activity.persists-from-any-thread`). One plain INSERT on the managed connection."""
        records.insert_event(self.db, {
            "id": activity.id, "type": activity.type.value, "level": activity.level.value,
            "timestamp": activity.timestamp, "message": activity.message, "workflow_id": activity.workflow_id,
            "batch_id": activity.batch_id, "thread_id": activity.thread_id, "node_id": activity.node_id,
            "metadata": activity.metadata or None, "duration_ms": activity.duration_ms, "error": activity.error})

    async def query(self, filter: ActivityFilter) -> list[Activity]:
        """Query activities with filtering, newest first; a deleted run's events never show (#4960)."""

        def _query():
            rows = records.query_events(
                self.db, types=[t.value for t in filter.types or []], levels=[lvl.value for lvl in filter.levels or []],
                workflow_id=filter.workflow_id, batch_id=filter.batch_id, thread_id=filter.thread_id,
                since=filter.since, until=filter.until, search=filter.search, limit=filter.limit,
                offset=filter.offset)
            return [
                Activity(
                    id=row[0],
                    type=ActivityType(row[1]),
                    level=ActivityLevel(row[2]),
                    # naive stored value IS UTC (#4347) -- re-attach offset
                    timestamp=ensure_utc(row[3]),
                    message=row[4],
                    workflow_id=row[5],
                    batch_id=row[6],
                    thread_id=row[7],
                    node_id=row[8],
                    metadata=(json.loads(row[9]) if isinstance(row[9], str) else row[9]) or {},
                    duration_ms=row[10],
                    error=row[11],
                )
                for row in rows
            ]

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
            got = records.event_stats(self.db, since, until)
            by_type = {t[0]: t[1] for t in got["by_type"]}
            by_level = {lc[0]: lc[1] for lc in got["by_level"]}
            completed = by_type.get("workflow_completed", 0)
            failed = by_type.get("workflow_failed", 0)
            total_workflows = completed + failed
            return ActivityStats(
                total_activities=got["total"],
                activities_by_type=by_type,
                activities_by_level=by_level,
                error_count=by_level.get("error", 0),
                warning_count=by_level.get("warning", 0),
                avg_workflow_duration_ms=got["avg_duration"],
                success_rate=(completed / total_workflows * 100) if total_workflows > 0 else 100.0,
                period_start=since,
                period_end=until,
            )

        return await asyncio.to_thread(_get_stats)

    def delete_old_sync(self, older_than: datetime) -> int:
        """Delete activities older than specified date (sync, for use inside registry.invoke)."""
        return records.delete_events_before(self.db, older_than)

    async def delete_old(self, older_than: datetime) -> int:
        """Delete activities older than specified date."""
        return await asyncio.to_thread(self.delete_old_sync, older_than)

    def delete_by_id_sync(self, activity_id: str) -> int:
        """Delete ONE activity by id (sync, for use inside registry.invoke). 0 when the id is unknown, so the caller
        can 404 honestly rather than report a delete that did nothing."""
        return records.delete_event(self.db, activity_id)

    async def delete_by_id(self, activity_id: str) -> int:
        """Delete ONE activity by id."""
        return await asyncio.to_thread(self.delete_by_id_sync, activity_id)

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
        estimated_cost: Optional[float] = None,
    ) -> None:
        """Save a new workflow run record (a value not given keeps the one kept, at a restart).

        ``resolved_scope`` is what the SERVER resolved the run to operate on -- not what the client asked for
        (#4384/#4396): #4396 was a client sending a whole folder for a one-file selection, and only the resolved set
        shows that.
        """
        await asyncio.to_thread(
            records.upsert_run, self.db, thread_id=thread_id, workflow_id=workflow_id, workflow_name=workflow_name,
            python_code=python_code, execution_log=execution_log, workflow_snapshot=workflow_snapshot,
            node_name_map=node_name_map, progress_timeline=progress_timeline, diagram_mermaid=diagram_mermaid,
            status=status, started_at=started_at or datetime.now(timezone.utc), resolved_scope=resolved_scope,
            estimated_cost=estimated_cost)
        # The run's row in the one job table follows its record (#5353, `activity.jobs-are-a-tree`).
        from fichero_server.execution import jobs

        await asyncio.to_thread(jobs.record_run, self.db_path, thread_id, status=status, name=workflow_name)

    async def update_workflow_run(
        self,
        thread_id: str,
        status: Optional[str] = None,
        execution_log: Optional[str] = None,
        progress_timeline: Optional[dict] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
        completed_at: Optional[datetime] = None,
        run_usage: Optional[dict] = None,
        partial: Optional[str] = None,
    ) -> None:
        """Update an existing workflow run record.

        ``partial`` ("Partial: 4 of 6 pages read") rides on the run's job row as its reason when it completed with pages failed (#5937).

        ``run_usage`` is the run's own accounting -- tokens, model calls and cost -- written on EVERY terminal path,
        not just success: a run that failed halfway still spent what it spent (2026-09-03).

        A run whose project was closed while it ran (#5608) keeps its state: the runner's end after the close (its
        pages stopped by the close) is not how it ended; the project's next open marks it interrupted.
        """
        from fichero_server.workflows.run_account import closed_mid_run

        if closed_mid_run(thread_id):
            status = error = completed_at = None

        await asyncio.to_thread(records.update_run, self.db, thread_id, {
            "status": status, "execution_log": execution_log, "progress_timeline": progress_timeline,
            "duration_ms": duration_ms, "error": error, "completed_at": completed_at, "run_usage": run_usage})
        if status is not None:  # the run's job row follows (#5353)
            from fichero_server.execution import jobs

            await asyncio.to_thread(jobs.record_run, self.db_path, thread_id, status=status, reason=error or partial)

    async def flush_node_boundary(self, thread_id: str, *, progress_timeline: dict, log_text: str,
                                  replace: bool) -> None:
        """A node-boundary flush (#4314): the timeline, and the log replaced (the run's first flush in this process)
        or only its new lines appended (#5645: the whole log was rewritten at every node, so a flush grew with the
        run, and on the managed connection it would hold the library's lock that long)."""
        await asyncio.to_thread(records.flush_node_boundary, self.db, thread_id, progress_timeline, log_text,
                                replace=replace)

    def _row_to_workflow_run(self, row: tuple) -> WorkflowRun:
        """A run's row (`records.RUN_COLUMNS`, or the list's light projection) as a WorkflowRun. A listed run
        (`records.LIST_COLUMNS`) carries no code, log, snapshot, node map or diagram: those read as empty, and a
        caller that needs them reads the run itself (`get_workflow_run`)."""

        def _obj(value):
            return json.loads(value) if isinstance(value, str) and value else (value or None)

        progress_timeline = _hydrate_progress_timeline(
            _obj(row[12]),
            status=row[5],
            error=row[9],
            execution_log=row[4],
        )
        return WorkflowRun(
            thread_id=row[0],
            workflow_id=row[1],
            workflow_name=row[2],
            python_code=row[3] or "",
            execution_log=row[4] or "",
            status=row[5],
            # by the #4347 contract a stored naive value IS UTC: re-attach the offset on the way out
            started_at=ensure_utc(row[6]),
            completed_at=ensure_utc(row[7]),
            duration_ms=row[8],
            error=row[9],
            workflow_snapshot=_obj(row[10]),
            node_name_map=_obj(row[11]),
            progress_timeline=progress_timeline,
            diagram_mermaid=row[13],
            resolved_scope=_obj(row[14]),
            # None for a run recorded before the column existed, which is not the same as one that cost nothing.
            run_usage=_obj(row[15]),
            # None for a legacy run or one whose model could not be priced at start (not the same as free).
            estimated_cost=row[16] if len(row) > 16 else None,
        )

    async def get_workflow_run(self, thread_id: str) -> Optional[WorkflowRun]:
        """Get a workflow run by thread_id, every column."""

        def _get():
            row = records.get_run(self.db, thread_id)
            return self._row_to_workflow_run(row) if row else None

        return await asyncio.to_thread(_get)

    async def delete_workflow_run(self, thread_id: str) -> int:
        """Mark a persisted workflow run as deleted."""
        return len(await asyncio.to_thread(records.soft_delete_runs, self.db, [thread_id], skip_running=False))

    def delete_workflow_runs_sync(self, thread_ids: list[str]) -> list[str]:
        """Soft-delete runs. Nothing is destroyed (#4960, revised: the app promises "you can put it back later", and
        the Trash needs a deleted run's history to restore it). A deleted run's events are hidden on the READ side
        (`query`'s anti-join). Bulk: one UPDATE, not one per id. Sync, for use inside ``registry.invoke``.
        Checkpoints are not touched. Returns the ids actually soft-deleted (already deleted, running or unknown ids
        are absent, never an error)."""
        return records.soft_delete_runs(self.db, thread_ids, skip_running=True)

    def workflow_run_ids_by_status_sync(self, statuses: list[str]) -> list[str]:
        """Thread ids of every non-deleted run whose status is in ``statuses`` (resolved at invoke time, so a delete's
        audit record names exactly what it removed)."""
        return records.run_ids_by_status(self.db, statuses)

    async def list_workflow_runs(
        self,
        workflow_id: Optional[str] = None,
        limit: int = 50,
        *,
        offset: int = 0,
        statuses: Optional[list[str]] = None,
        exclude_deleted: bool = True,
    ) -> list[WorkflowRun]:
        """Runs newest first, paged and filtered in SQL (#4960: the cost does not grow with the runs a library holds),
        each in the light projection: no code, log, snapshot, node map or diagram (#5645: Activity polls this; read
        one run whole with `get_workflow_run`)."""

        def _list():
            rows = records.list_runs(self.db, workflow_id=workflow_id, statuses=statuses,
                                     exclude_deleted=exclude_deleted, limit=limit, offset=offset)
            return [self._row_to_workflow_run(row) for row in rows]

        return await asyncio.to_thread(_list)

    async def recover_stale_runs(
        self,
        max_age_hours: int = 2,
        exclude_thread_ids: tuple[str, ...] = (),
    ) -> list[str]:
        """Flip stale unfinished runs ('running', 'accepted') older than ``max_age_hours`` to 'failed' and return their
        ``thread_id``s, so the caller can settle the documents they left processing (#4379). Runs this process is
        tracking (``exclude_thread_ids``) are never flipped (F5).

        On the managed connection: a stale index after a crashed session's WAL replay, the FATAL #1362's table rebuild
        guarded against, is rebuilt by `connect_utc` at open (#5644), and the managed Database recovers its own
        connection should one still happen. A failure here is logged and nothing is flipped; it never takes the
        library down."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        def _recover():
            try:
                flipped = records.recover_stale(self.db, error=_STALE_RUN_ERROR, started_before=cutoff,
                                                exclude_thread_ids=tuple(exclude_thread_ids))
            except Exception as exc:  # noqa: BLE001 -- recovery degrades run history, never the library
                logger.error("recover_stale_runs: could not flip stale runs for %s: %s", self.db_path, exc)
                return []
            if flipped:
                logger.warning("recover_stale_runs: flipped %d stale run(s) to 'failed' for %s", len(flipped),
                               self.db_path)
            return flipped

        return await asyncio.to_thread(_recover)
