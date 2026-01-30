"""
Activity Tracking System for Fichero Workflows.

Provides comprehensive activity logging and real-time streaming:
- Activity logging for workflow and batch events
- WebSocket streaming for real-time updates
- Query interface for historical activity
- Aggregated metrics and statistics
"""

import asyncio
import json
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, AsyncIterator, Callable, Optional

import duckdb

logger = logging.getLogger(__name__)


class ActivityType(str, Enum):
    """Types of activity events."""
    # Workflow events
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_PAUSED = "workflow_paused"
    WORKFLOW_RESUMED = "workflow_resumed"
    WORKFLOW_CANCELLED = "workflow_cancelled"

    # Node events
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    NODE_RETRY = "node_retry"

    # Batch events
    BATCH_CREATED = "batch_created"
    BATCH_STARTED = "batch_started"
    BATCH_COMPLETED = "batch_completed"
    BATCH_FAILED = "batch_failed"
    BATCH_PAUSED = "batch_paused"
    BATCH_RESUMED = "batch_resumed"
    BATCH_CANCELLED = "batch_cancelled"
    BATCH_ITEM_STARTED = "batch_item_started"
    BATCH_ITEM_COMPLETED = "batch_item_completed"
    BATCH_ITEM_FAILED = "batch_item_failed"

    # System events
    SYSTEM_INFO = "system_info"
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"


class ActivityLevel(str, Enum):
    """Severity level of activity."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Activity:
    """Represents a single activity event."""
    id: str
    type: ActivityType
    level: ActivityLevel
    timestamp: datetime
    message: str
    workflow_id: Optional[str] = None
    batch_id: Optional[str] = None
    thread_id: Optional[str] = None
    node_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        # Convert all metadata values to strings for Swift client compatibility
        string_metadata = {k: str(v) if v is not None else None for k, v in self.metadata.items()}
        return {
            "id": self.id,
            "type": self.type.value,
            "level": self.level.value,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "workflow_id": self.workflow_id,
            "batch_id": self.batch_id,
            "thread_id": self.thread_id,
            "node_id": self.node_id,
            "metadata": string_metadata,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Activity":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            type=ActivityType(data["type"]),
            level=ActivityLevel(data["level"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            message=data["message"],
            workflow_id=data.get("workflow_id"),
            batch_id=data.get("batch_id"),
            thread_id=data.get("thread_id"),
            node_id=data.get("node_id"),
            metadata=data.get("metadata", {}),
            duration_ms=data.get("duration_ms"),
            error=data.get("error"),
        )


@dataclass
class ActivityStats:
    """Aggregated activity statistics."""
    total_activities: int
    activities_by_type: dict[str, int]
    activities_by_level: dict[str, int]
    error_count: int
    warning_count: int
    avg_workflow_duration_ms: Optional[float]
    success_rate: float
    period_start: datetime
    period_end: datetime


class ActivityFilter:
    """Filter criteria for querying activities."""

    def __init__(
        self,
        types: Optional[list[ActivityType]] = None,
        levels: Optional[list[ActivityLevel]] = None,
        workflow_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ):
        self.types = types
        self.levels = levels
        self.workflow_id = workflow_id
        self.batch_id = batch_id
        self.thread_id = thread_id
        self.since = since
        self.until = until
        self.search = search
        self.limit = limit
        self.offset = offset


class ActivityStore:
    """
    Persistent storage for activity events.

    Uses DuckDB for efficient querying and analytics.
    """

    def __init__(self, db_path: str):
        """Initialize activity store with database path."""
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database tables for activity tracking."""
        conn = duckdb.connect(self.db_path)
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
        finally:
            conn.close()

    async def save(self, activity: Activity) -> None:
        """Save an activity to the database."""
        def _save():
            logger.info(f"ActivityStore.save: connecting to {self.db_path}")
            conn = duckdb.connect(self.db_path)
            try:
                conn.execute("""
                    INSERT INTO activities
                    (id, type, level, timestamp, message, workflow_id, batch_id,
                     thread_id, node_id, metadata, duration_ms, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
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
                ])
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
            conn = duckdb.connect(self.db_path)
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
                    params.extend([l.value for l in filter.levels])

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
                    activities.append(Activity(
                        id=row[0],
                        type=ActivityType(row[1]),
                        level=ActivityLevel(row[2]),
                        timestamp=row[3],
                        message=row[4],
                        workflow_id=row[5],
                        batch_id=row[6],
                        thread_id=row[7],
                        node_id=row[8],
                        metadata=json.loads(row[9]) if row[9] else {},
                        duration_ms=row[10],
                        error=row[11],
                    ))
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
            since = datetime.now() - timedelta(hours=24)
        if not until:
            until = datetime.now()

        def _get_stats():
            conn = duckdb.connect(self.db_path)
            try:
                # Count by type
                type_counts = conn.execute("""
                    SELECT type, COUNT(*) as count
                    FROM activities
                    WHERE timestamp >= ? AND timestamp <= ?
                    GROUP BY type
                """, [since, until]).fetchall()

                # Count by level
                level_counts = conn.execute("""
                    SELECT level, COUNT(*) as count
                    FROM activities
                    WHERE timestamp >= ? AND timestamp <= ?
                    GROUP BY level
                """, [since, until]).fetchall()

                # Average workflow duration
                avg_duration = conn.execute("""
                    SELECT AVG(duration_ms)
                    FROM activities
                    WHERE type = 'workflow_completed'
                    AND timestamp >= ? AND timestamp <= ?
                    AND duration_ms IS NOT NULL
                """, [since, until]).fetchone()[0]

                # Success rate (completed vs failed workflows)
                workflow_counts = conn.execute("""
                    SELECT type, COUNT(*) as count
                    FROM activities
                    WHERE type IN ('workflow_completed', 'workflow_failed')
                    AND timestamp >= ? AND timestamp <= ?
                    GROUP BY type
                """, [since, until]).fetchall()

                completed = sum(c[1] for c in workflow_counts if c[0] == 'workflow_completed')
                failed = sum(c[1] for c in workflow_counts if c[0] == 'workflow_failed')
                total_workflows = completed + failed
                success_rate = (completed / total_workflows * 100) if total_workflows > 0 else 100.0

                # Total count
                total = conn.execute("""
                    SELECT COUNT(*)
                    FROM activities
                    WHERE timestamp >= ? AND timestamp <= ?
                """, [since, until]).fetchone()[0]

                return ActivityStats(
                    total_activities=total,
                    activities_by_type={t[0]: t[1] for t in type_counts},
                    activities_by_level={l[0]: l[1] for l in level_counts},
                    error_count=sum(l[1] for l in level_counts if l[0] == 'error'),
                    warning_count=sum(l[1] for l in level_counts if l[0] == 'warning'),
                    avg_workflow_duration_ms=avg_duration,
                    success_rate=success_rate,
                    period_start=since,
                    period_end=until,
                )
            finally:
                conn.close()

        return await asyncio.to_thread(_get_stats)

    async def delete_old(self, older_than: datetime) -> int:
        """Delete activities older than specified date."""
        def _delete():
            conn = duckdb.connect(self.db_path)
            try:
                result = conn.execute("""
                    DELETE FROM activities
                    WHERE timestamp < ?
                """, [older_than])
                return result.fetchone()[0] if result else 0
            finally:
                conn.close()

        return await asyncio.to_thread(_delete)

    # =========================================================================
    # Workflow Run Methods
    # =========================================================================

    async def save_workflow_run(
        self,
        thread_id: str,
        workflow_id: str,
        workflow_name: str,
        python_code: Optional[str] = None,
        started_at: Optional[datetime] = None,
    ) -> None:
        """Save a new workflow run record."""
        def _save():
            conn = duckdb.connect(self.db_path)
            try:
                conn.execute("""
                    INSERT INTO workflow_runs
                    (thread_id, workflow_id, workflow_name, python_code, status, started_at)
                    VALUES (?, ?, ?, ?, 'running', ?)
                    ON CONFLICT (thread_id) DO UPDATE SET
                        python_code = COALESCE(EXCLUDED.python_code, workflow_runs.python_code),
                        workflow_name = EXCLUDED.workflow_name
                """, [
                    thread_id,
                    workflow_id,
                    workflow_name,
                    python_code,
                    started_at or datetime.utcnow(),
                ])
            finally:
                conn.close()

        await asyncio.to_thread(_save)

    async def update_workflow_run(
        self,
        thread_id: str,
        status: Optional[str] = None,
        execution_log: Optional[str] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
        completed_at: Optional[datetime] = None,
    ) -> None:
        """Update an existing workflow run record."""
        def _update():
            conn = duckdb.connect(self.db_path)
            try:
                updates = []
                params = []

                if status is not None:
                    updates.append("status = ?")
                    params.append(status)
                if execution_log is not None:
                    updates.append("execution_log = ?")
                    params.append(execution_log)
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
                    conn.execute(f"""
                        UPDATE workflow_runs
                        SET {', '.join(updates)}
                        WHERE thread_id = ?
                    """, params)
            finally:
                conn.close()

        await asyncio.to_thread(_update)

    async def append_execution_log(self, thread_id: str, log_line: str) -> None:
        """Append a line to the execution log."""
        def _append():
            conn = duckdb.connect(self.db_path)
            try:
                conn.execute("""
                    UPDATE workflow_runs
                    SET execution_log = COALESCE(execution_log, '') || ? || '\n'
                    WHERE thread_id = ?
                """, [log_line, thread_id])
            finally:
                conn.close()

        await asyncio.to_thread(_append)

    async def get_workflow_run(self, thread_id: str) -> Optional[dict[str, Any]]:
        """Get a workflow run by thread_id."""
        def _get():
            conn = duckdb.connect(self.db_path)
            try:
                result = conn.execute("""
                    SELECT thread_id, workflow_id, workflow_name, python_code,
                           execution_log, status, started_at, completed_at,
                           duration_ms, error
                    FROM workflow_runs
                    WHERE thread_id = ?
                """, [thread_id]).fetchone()

                if result:
                    return {
                        "thread_id": result[0],
                        "workflow_id": result[1],
                        "workflow_name": result[2],
                        "python_code": result[3],
                        "execution_log": result[4],
                        "status": result[5],
                        "started_at": result[6].isoformat() if result[6] else None,
                        "completed_at": result[7].isoformat() if result[7] else None,
                        "duration_ms": result[8],
                        "error": result[9],
                    }
                return None
            finally:
                conn.close()

        return await asyncio.to_thread(_get)

    async def list_workflow_runs(
        self,
        workflow_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List workflow runs, optionally filtered by workflow_id."""
        def _list():
            conn = duckdb.connect(self.db_path)
            try:
                if workflow_id:
                    result = conn.execute("""
                        SELECT thread_id, workflow_id, workflow_name, status,
                               started_at, completed_at, duration_ms, error
                        FROM workflow_runs
                        WHERE workflow_id = ?
                        ORDER BY started_at DESC
                        LIMIT ?
                    """, [workflow_id, limit]).fetchall()
                else:
                    result = conn.execute("""
                        SELECT thread_id, workflow_id, workflow_name, status,
                               started_at, completed_at, duration_ms, error
                        FROM workflow_runs
                        ORDER BY started_at DESC
                        LIMIT ?
                    """, [limit]).fetchall()

                return [
                    {
                        "thread_id": row[0],
                        "workflow_id": row[1],
                        "workflow_name": row[2],
                        "status": row[3],
                        "started_at": row[4].isoformat() if row[4] else None,
                        "completed_at": row[5].isoformat() if row[5] else None,
                        "duration_ms": row[6],
                        "error": row[7],
                    }
                    for row in result
                ]
            finally:
                conn.close()

        return await asyncio.to_thread(_list)


class ActivityTracker:
    """
    Central activity tracking service.

    Combines persistent storage with real-time streaming capabilities.
    """

    def __init__(self, db_path: str, max_recent: int = 1000):
        """
        Initialize activity tracker.

        Args:
            db_path: Path to DuckDB database
            max_recent: Maximum number of recent activities to keep in memory
        """
        self.store = ActivityStore(db_path)
        self._recent: deque[Activity] = deque(maxlen=max_recent)
        self._subscribers: dict[str, asyncio.Queue[Activity]] = {}
        self._running = False

    def log(
        self,
        type: ActivityType,
        message: str,
        level: ActivityLevel = ActivityLevel.INFO,
        workflow_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        node_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
    ) -> Activity:
        """
        Log an activity event.

        Returns the created Activity object.
        """
        activity = Activity(
            id=str(uuid.uuid4()),
            type=type,
            level=level,
            timestamp=datetime.now(),
            message=message,
            workflow_id=workflow_id,
            batch_id=batch_id,
            thread_id=thread_id,
            node_id=node_id,
            metadata=metadata or {},
            duration_ms=duration_ms,
            error=error,
        )

        # Add to recent buffer
        self._recent.appendleft(activity)

        # Save to database (fire and forget)
        asyncio.create_task(self._save_activity(activity))

        # Notify subscribers
        asyncio.create_task(self._notify_subscribers(activity))

        # Log to Python logger as well
        log_level = getattr(logging, level.value.upper(), logging.INFO)
        logger.log(log_level, f"[{type.value}] {message}")

        return activity

    async def _save_activity(self, activity: Activity) -> None:
        """Save activity to persistent storage."""
        try:
            logger.info(f"Saving activity to DB: {activity.type.value} - {activity.message[:50]}")
            await self.store.save(activity)
            logger.info(f"Activity saved successfully: {activity.id}")
        except Exception as e:
            logger.error(f"Failed to save activity: {e}", exc_info=True)

    async def _notify_subscribers(self, activity: Activity) -> None:
        """Notify all subscribers of new activity."""
        for queue in self._subscribers.values():
            try:
                await queue.put(activity)
            except asyncio.QueueFull:
                # Drop oldest if queue is full
                try:
                    queue.get_nowait()
                    await queue.put(activity)
                except asyncio.QueueEmpty:
                    pass

    def subscribe(self, filter: Optional[ActivityFilter] = None) -> str:
        """
        Subscribe to activity stream.

        Returns subscription ID for use with unsubscribe and stream.
        """
        sub_id = str(uuid.uuid4())
        self._subscribers[sub_id] = asyncio.Queue(maxsize=100)
        return sub_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from activity stream."""
        if subscription_id in self._subscribers:
            del self._subscribers[subscription_id]

    async def stream(
        self,
        subscription_id: str,
        filter: Optional[ActivityFilter] = None,
    ) -> AsyncIterator[Activity]:
        """
        Stream activities for a subscription.

        Yields Activity objects as they occur.
        """
        if subscription_id not in self._subscribers:
            raise ValueError(f"Invalid subscription ID: {subscription_id}")

        queue = self._subscribers[subscription_id]

        try:
            while True:
                activity = await queue.get()

                # Apply filter if provided
                if filter:
                    if filter.types and activity.type not in filter.types:
                        continue
                    if filter.levels and activity.level not in filter.levels:
                        continue
                    if filter.workflow_id and activity.workflow_id != filter.workflow_id:
                        continue
                    if filter.batch_id and activity.batch_id != filter.batch_id:
                        continue

                yield activity
        finally:
            self.unsubscribe(subscription_id)

    def get_recent(self, limit: int = 50) -> list[Activity]:
        """Get recent activities from memory buffer."""
        return list(self._recent)[:limit]

    async def query(self, filter: ActivityFilter) -> list[Activity]:
        """Query historical activities."""
        return await self.store.query(filter)

    async def get_stats(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> ActivityStats:
        """Get activity statistics."""
        return await self.store.get_stats(since, until)

    # Convenience methods for common activity types

    def workflow_started(
        self,
        workflow_id: str,
        thread_id: str,
        workflow_name: str,
        **metadata,
    ) -> Activity:
        """Log workflow started event."""
        return self.log(
            type=ActivityType.WORKFLOW_STARTED,
            message=f"Workflow '{workflow_name}' started",
            workflow_id=workflow_id,
            thread_id=thread_id,
            metadata={"workflow_name": workflow_name, **metadata},
        )

    def workflow_completed(
        self,
        workflow_id: str,
        thread_id: str,
        workflow_name: str,
        duration_ms: float,
        **metadata,
    ) -> Activity:
        """Log workflow completed event."""
        return self.log(
            type=ActivityType.WORKFLOW_COMPLETED,
            message=f"Workflow '{workflow_name}' completed in {duration_ms:.0f}ms",
            workflow_id=workflow_id,
            thread_id=thread_id,
            duration_ms=duration_ms,
            metadata={"workflow_name": workflow_name, **metadata},
        )

    def workflow_failed(
        self,
        workflow_id: str,
        thread_id: str,
        workflow_name: str,
        error: str,
        duration_ms: Optional[float] = None,
        **metadata,
    ) -> Activity:
        """Log workflow failed event."""
        return self.log(
            type=ActivityType.WORKFLOW_FAILED,
            level=ActivityLevel.ERROR,
            message=f"Workflow '{workflow_name}' failed: {error}",
            workflow_id=workflow_id,
            thread_id=thread_id,
            error=error,
            duration_ms=duration_ms,
            metadata={"workflow_name": workflow_name, **metadata},
        )

    def node_started(
        self,
        workflow_id: str,
        thread_id: str,
        node_id: str,
        node_name: str,
        **metadata,
    ) -> Activity:
        """Log node started event."""
        return self.log(
            type=ActivityType.NODE_STARTED,
            level=ActivityLevel.DEBUG,
            message=f"Node '{node_name}' started",
            workflow_id=workflow_id,
            thread_id=thread_id,
            node_id=node_id,
            metadata={"node_name": node_name, **metadata},
        )

    def node_completed(
        self,
        workflow_id: str,
        thread_id: str,
        node_id: str,
        node_name: str,
        duration_ms: float,
        **metadata,
    ) -> Activity:
        """Log node completed event."""
        return self.log(
            type=ActivityType.NODE_COMPLETED,
            level=ActivityLevel.DEBUG,
            message=f"Node '{node_name}' completed in {duration_ms:.0f}ms",
            workflow_id=workflow_id,
            thread_id=thread_id,
            node_id=node_id,
            duration_ms=duration_ms,
            metadata={"node_name": node_name, **metadata},
        )

    def node_failed(
        self,
        workflow_id: str,
        thread_id: str,
        node_id: str,
        node_name: str,
        error: str,
        **metadata,
    ) -> Activity:
        """Log node failed event."""
        return self.log(
            type=ActivityType.NODE_FAILED,
            level=ActivityLevel.ERROR,
            message=f"Node '{node_name}' failed: {error}",
            workflow_id=workflow_id,
            thread_id=thread_id,
            node_id=node_id,
            error=error,
            metadata={"node_name": node_name, **metadata},
        )

    def batch_started(
        self,
        batch_id: str,
        workflow_id: str,
        total_items: int,
        **metadata,
    ) -> Activity:
        """Log batch started event."""
        return self.log(
            type=ActivityType.BATCH_STARTED,
            message=f"Batch started with {total_items} items",
            batch_id=batch_id,
            workflow_id=workflow_id,
            metadata={"total_items": total_items, **metadata},
        )

    def batch_completed(
        self,
        batch_id: str,
        workflow_id: str,
        total_items: int,
        completed_items: int,
        failed_items: int,
        duration_ms: float,
        **metadata,
    ) -> Activity:
        """Log batch completed event."""
        return self.log(
            type=ActivityType.BATCH_COMPLETED,
            message=f"Batch completed: {completed_items}/{total_items} successful, {failed_items} failed",
            batch_id=batch_id,
            workflow_id=workflow_id,
            duration_ms=duration_ms,
            metadata={
                "total_items": total_items,
                "completed_items": completed_items,
                "failed_items": failed_items,
                **metadata,
            },
        )

    def batch_item_completed(
        self,
        batch_id: str,
        thread_id: str,
        item_index: int,
        duration_ms: float,
        **metadata,
    ) -> Activity:
        """Log batch item completed event."""
        return self.log(
            type=ActivityType.BATCH_ITEM_COMPLETED,
            level=ActivityLevel.DEBUG,
            message=f"Batch item {item_index} completed",
            batch_id=batch_id,
            thread_id=thread_id,
            duration_ms=duration_ms,
            metadata={"item_index": item_index, **metadata},
        )

    def batch_item_failed(
        self,
        batch_id: str,
        thread_id: str,
        item_index: int,
        error: str,
        **metadata,
    ) -> Activity:
        """Log batch item failed event."""
        return self.log(
            type=ActivityType.BATCH_ITEM_FAILED,
            level=ActivityLevel.ERROR,
            message=f"Batch item {item_index} failed: {error}",
            batch_id=batch_id,
            thread_id=thread_id,
            error=error,
            metadata={"item_index": item_index, **metadata},
        )


# Per-library activity tracker instances
# Key: database path string, Value: ActivityTracker instance
_activity_trackers: dict[str, ActivityTracker] = {}
_tracker_lock = __import__('threading').Lock()


def get_activity_tracker(db_path: Optional[str] = None) -> ActivityTracker:
    """Get or create activity tracker for a library.

    Each library has its own ActivityTracker storing activities in that
    library's database. This ensures activity data is kept with the library.

    Args:
        db_path: Path to the library's database file. REQUIRED for proper
                 per-library tracking. If None, falls back to app database
                 (not recommended).

    Returns:
        ActivityTracker instance for the specified library
    """
    if db_path is None:
        # Fallback to app database - not ideal but maintains backward compatibility
        from fichero.app_db import get_db_path
        db_path = get_db_path()
        logger.warning(
            "get_activity_tracker() called without db_path - using app database. "
            "Activity data should be stored per-library."
        )

    # Ensure we're using the string path
    db_path = str(db_path)
    logger.info(f"get_activity_tracker called with db_path: {db_path}")

    with _tracker_lock:
        if db_path not in _activity_trackers:
            logger.info(f"Creating NEW ActivityTracker for: {db_path}")
            _activity_trackers[db_path] = ActivityTracker(db_path)
        else:
            logger.debug(f"Reusing existing ActivityTracker for: {db_path}")
        return _activity_trackers[db_path]


def close_activity_tracker(db_path: str) -> None:
    """Close and remove activity tracker for a library.

    Call when closing a library to clean up resources.
    """
    with _tracker_lock:
        if db_path in _activity_trackers:
            del _activity_trackers[db_path]
            logger.info(f"Closed ActivityTracker for: {db_path}")
