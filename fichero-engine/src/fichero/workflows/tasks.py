"""Background Task System for reindex, repair, and metrics jobs.

Provides:
- Task queue with persistent storage
- Background workers using APScheduler
- Progress tracking and status updates
- Support for reindex, metrics recomputation, and repair operations
"""

import asyncio
import json
import threading
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import duckdb

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

from fichero.db import Database
from fichero.api.change_stream import emit_change

from .task_types import (
    BackgroundTask,
    TaskConfig,
    TaskProgress,
    TaskResult,
    TaskStatus,
    TaskType,
)
from .task_workers import TaskWorkersMixin

# Re-export types for backward compatibility
__all__ = [
    "BackgroundTask",
    "TaskConfig",
    "TaskProgress",
    "TaskQueue",
    "TaskResult",
    "TaskStatus",
    "TaskType",
    "get_task_queue",
    "init_task_queue",
    "shutdown_task_queue",
]

logger = logging.getLogger(__name__)

_TASK_LIBRARY_PATH_OPTION = "_library_path"


class TaskQueue(TaskWorkersMixin):
    """Persistent task queue with background execution."""

    def __init__(self, db_path: str, database: Optional[Database] = None):
        self.db_path = db_path
        self.database = database
        self._tasks: dict[str, BackgroundTask] = {}
        self._scheduler: "Optional[AsyncIOScheduler]" = None
        self._running: bool = False
        self._lock = asyncio.Lock()
        self._db_lock = threading.Lock()   # serializes concurrent DuckDB writes
        self._executing: set[str] = set()   # task_ids currently being executed
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database tables for task tracking."""
        # ponytail: not a managed shared conn (#2508). Despite receiving an
        # optional managed ``self.database``, every SQL method here opens a FRESH
        # ``conn = duckdb.connect(self.db_path)`` per operation (guarded by the
        # store's own ``self._db_lock`` for writes) and closes it — a
        # connection-per-operation pattern, not the package's managed Database
        # connection. Database._lock and the locked execute() helpers do not
        # apply. Folding TaskQueue's SQL onto self.database is a separate
        # architectural call (lead review).
        conn = duckdb.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS background_tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    options JSON DEFAULT '{}',
                    priority INTEGER DEFAULT 0,
                    timeout_seconds INTEGER,
                    progress_current INTEGER DEFAULT 0,
                    progress_total INTEGER DEFAULT 0,
                    progress_message TEXT DEFAULT '',
                    progress_updated_at TIMESTAMP,
                    result_success BOOLEAN,
                    result_message TEXT,
                    result_details JSON DEFAULT '{}',
                    result_error TEXT,
                    created_at TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status
                ON background_tasks(status)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_created
                ON background_tasks(created_at DESC)
            """)
        finally:
            conn.close()

    async def start(self) -> None:
        """Start the task queue and scheduler."""
        if self._running:
            return

        # Initialize APScheduler for background execution (imported here to keep
        # apscheduler off the engine API bind path — #4038 startup speedup).
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.jobstores.memory import MemoryJobStore
        from apscheduler.executors.asyncio import AsyncIOExecutor

        jobstores = {"default": MemoryJobStore()}
        executors = {"default": AsyncIOExecutor()}
        job_defaults = {"coalesce": True, "max_instances": 1}

        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
        )
        self._scheduler.start()

        # Load pending tasks from database
        await self._load_pending_tasks()

        self._running = True
        logger.info("Task queue started")

    async def stop(self) -> None:
        """Stop the task queue."""
        if self._scheduler:
            self._scheduler.shutdown(wait=True)
        self._running = False
        logger.info("Task queue stopped")

    async def _load_pending_tasks(self) -> None:
        """Load pending and running tasks from database."""

        def _load():
            conn = duckdb.connect(self.db_path)
            try:
                results = conn.execute("""
                    SELECT * FROM background_tasks
                    WHERE status IN ('pending', 'running')
                    ORDER BY priority ASC, created_at ASC
                """).fetchall()
                return results
            finally:
                conn.close()

        rows = await asyncio.to_thread(_load)

        for row in rows:
            task = self._row_to_task(row)
            self._tasks[task.task_id] = task

            # Resume running tasks as pending (they were interrupted)
            if task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.PENDING
                task.error_message = "Interrupted by restart"
                await self._save_task(task)
                logger.info(f"Reset interrupted task {task.task_id} to pending")

        logger.info(f"Loaded {len(rows)} pending tasks")

        # Start processing if there are pending tasks
        if self._tasks:
            self._schedule_next_task()

    def _row_to_task(self, row) -> BackgroundTask:
        """Convert database row to BackgroundTask."""
        # Parse progress
        progress = TaskProgress(
            current=row[7] or 0,
            total=row[8] or 0,
            message=row[9] or "",
            updated_at=row[10] or datetime.now(),
        )
        if progress.total > 0:
            progress.percent = (progress.current / progress.total) * 100

        # Parse result if completed/failed
        result = None
        if row[11] is not None:  # result_success
            result = TaskResult(
                success=row[11],
                message=row[12] or "",
                details=json.loads(row[13]) if row[13] else {},
                error=row[14],
            )

        return BackgroundTask(
            task_id=row[0],
            task_type=TaskType(row[1]),
            name=row[2],
            status=TaskStatus(row[3]),
            config=TaskConfig(
                task_type=TaskType(row[1]),
                options=json.loads(row[4]) if row[4] else {},
                priority=row[5] or 0,
                timeout_seconds=row[6],
            ),
            progress=progress,
            result=result,
            created_at=row[15],
            started_at=row[16],
            completed_at=row[17],
            error_message=row[18],
        )

    async def create_task(
        self,
        task_type: TaskType,
        name: str,
        options: Optional[dict[str, Any]] = None,
        priority: int = 0,
        timeout_seconds: Optional[int] = None,
    ) -> BackgroundTask:
        """Create a new background task."""
        task_id = str(uuid.uuid4())
        now = datetime.now()

        task = BackgroundTask(
            task_id=task_id,
            task_type=task_type,
            name=name,
            status=TaskStatus.PENDING,
            config=TaskConfig(
                task_type=task_type,
                options=options or {},
                priority=priority,
                timeout_seconds=timeout_seconds,
            ),
            created_at=now,
        )

        await self._save_task(task)
        self._tasks[task_id] = task

        # Schedule for execution
        self._schedule_next_task()

        logger.info(f"Created {task_type.value} task {task_id}: {name}")
        return task

    def _task_library_path(self, task: BackgroundTask) -> str | None:
        library_path = task.config.options.get(_TASK_LIBRARY_PATH_OPTION)
        if isinstance(library_path, str) and library_path:
            return library_path
        if self.database is not None and getattr(self.database, "path", None) is not None:
            return str(Path(self.database.path).parent)
        return None

    def _emit_task_change(self, task: BackgroundTask, change_type: str) -> None:
        library_path = self._task_library_path(task)
        if not library_path:
            return
        emit_change(
            library_path,
            type=change_type,
            run_id=task.task_id,
            actor="system",
            metadata={
                "task_type": task.task_type.value,
                "task_name": task.name,
                "status": task.status.value,
                "message": task.progress.message,
                "current": str(task.progress.current),
                "total": str(task.progress.total),
                "percent": str(task.progress.percent),
            },
        )

    async def _save_task(self, task: BackgroundTask) -> None:
        """Save task to database."""

        def _save():
            with self._db_lock:
                conn = duckdb.connect(self.db_path)
                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO background_tasks (
                            task_id, task_type, name, status,
                            options, priority, timeout_seconds,
                            progress_current, progress_total, progress_message,
                            progress_updated_at,
                            result_success, result_message, result_details, result_error,
                            created_at, started_at, completed_at, error_message
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        [
                            task.task_id,
                            task.task_type.value,
                            task.name,
                            task.status.value,
                            json.dumps(task.config.options),
                            task.config.priority,
                            task.config.timeout_seconds,
                            task.progress.current,
                            task.progress.total,
                            task.progress.message,
                            task.progress.updated_at,
                            task.result.success if task.result else None,
                            task.result.message if task.result else None,
                            json.dumps(task.result.details) if task.result else None,
                            task.result.error if task.result else None,
                            task.created_at,
                            task.started_at,
                            task.completed_at,
                            task.error_message,
                        ],
                    )
                finally:
                    conn.close()

        try:
            await asyncio.to_thread(_save)
        except (asyncio.CancelledError, RuntimeError):
            # Event loop shutting down (e.g. test teardown) — save synchronously
            _save()

    def _schedule_next_task(self) -> None:
        """Schedule the next pending task for execution."""
        if not self._scheduler or not self._running:
            return

        # Find highest priority pending task
        pending = [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]
        if not pending:
            return

        # Sort by priority, then creation time
        next_task = min(pending, key=lambda t: (t.config.priority, t.created_at))

        # Schedule immediate execution
        self._scheduler.add_job(
            self._execute_task,
            trigger="date",
            args=[next_task.task_id],
            id=f"task_{next_task.task_id}",
            replace_existing=True,
        )
        logger.debug(f"Scheduled task {next_task.task_id}")

    async def _claim_for_direct_execution(self, task: BackgroundTask) -> bool:
        """Claim a task for direct execution (not via APScheduler).

        Returns True if successfully claimed, False if already running/done.
        Called by _execute_* methods when invoked directly (e.g. from tests or
        the API), so that a concurrent APScheduler _execute_task sees the task
        as already executing and skips it.
        """
        async with self._lock:
            if task.task_id in self._executing:
                return False
            if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
                return False
            self._executing.add(task.task_id)
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now()
            return True

    async def _execute_task(self, task_id: str) -> None:
        """Execute a background task."""
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status != TaskStatus.PENDING:
                return
            if task_id in self._executing:
                return

            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            self._executing.add(task_id)
            await self._save_task(task)

        logger.info(f"Starting task {task_id}: {task.name}")
        self._emit_task_change(task, "backend.work.started")

        try:
            # Execute based on task type (call _do_* directly — task is already claimed)
            if task.task_type == TaskType.REINDEX:
                result = await self._do_reindex(task)
            elif task.task_type == TaskType.METRICS:
                result = await self._do_metrics(task)
            elif task.task_type == TaskType.REPAIR:
                result = await self._do_repair(task)
            elif task.task_type == TaskType.VECTOR_REPAIR:
                result = await self._do_vector_repair(task)
            elif task.task_type == TaskType.KG_METRICS:
                result = await self._do_kg_metrics(task)
            else:
                raise ValueError(f"Unknown task type: {task.task_type}")

            task.result = result
            task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            if not result.success:
                task.error_message = result.error

        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.result = TaskResult(
                success=False,
                message="Task execution failed",
                error=str(e),
            )

        finally:
            task.completed_at = datetime.now()
            self._executing.discard(task_id)
            await self._save_task(task)
            terminal_type = (
                "backend.work.completed"
                if task.status == TaskStatus.COMPLETED
                else "backend.work.cancelled"
                if task.status == TaskStatus.CANCELLED
                else "backend.work.failed"
            )
            self._emit_task_change(task, terminal_type)

            # Schedule next task
            self._schedule_next_task()

    async def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Get task by ID."""
        if task_id in self._tasks:
            return self._tasks[task_id]

        def _load():
            conn = duckdb.connect(self.db_path)
            try:
                result = conn.execute(
                    "SELECT * FROM background_tasks WHERE task_id = ?", [task_id]
                ).fetchone()
                return result
            finally:
                conn.close()

        row = await asyncio.to_thread(_load)
        if row:
            task = self._row_to_task(row)
            self._tasks[task_id] = task
            return task
        return None

    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BackgroundTask]:
        """List tasks with optional filtering."""

        def _list():
            conn = duckdb.connect(self.db_path)
            try:
                query = "SELECT * FROM background_tasks WHERE 1=1"
                params = []

                if status:
                    query += " AND status = ?"
                    params.append(status.value)
                if task_type:
                    query += " AND task_type = ?"
                    params.append(task_type.value)

                query += " ORDER BY priority ASC, created_at ASC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                results = conn.execute(query, params).fetchall()
                return results
            finally:
                conn.close()

        rows = await asyncio.to_thread(_list)
        return [self._row_to_task(row) for row in rows]

    async def cancel_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Cancel a pending task."""
        task = await self.get_task(task_id)
        if not task:
            return None

        if task.status != TaskStatus.PENDING:
            raise ValueError(f"Cannot cancel task with status {task.status.value}")

        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now()
        await self._save_task(task)
        self._emit_task_change(task, "backend.work.cancelled")

        logger.info(f"Cancelled task {task_id}")
        return task

    async def delete_task(self, task_id: str) -> bool:
        """Delete a completed/cancelled/failed task."""
        task = await self.get_task(task_id)
        if not task:
            return False

        if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            raise ValueError("Cannot delete running/pending task")

        def _delete():
            conn = duckdb.connect(self.db_path)
            try:
                conn.execute(
                    "DELETE FROM background_tasks WHERE task_id = ?", [task_id]
                )
            finally:
                conn.close()

        await asyncio.to_thread(_delete)

        if task_id in self._tasks:
            del self._tasks[task_id]

        logger.info(f"Deleted task {task_id}")
        return True


# =============================================================================
# Global instance + factory functions
# =============================================================================

# Global task queue instance
_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> Optional[TaskQueue]:
    """Get the global task queue instance."""
    return _task_queue


async def init_task_queue(
    db_path: str, database: Optional[Database] = None
) -> TaskQueue:
    """Initialize and start the global task queue."""
    global _task_queue
    _task_queue = TaskQueue(db_path, database)
    await _task_queue.start()
    return _task_queue


async def shutdown_task_queue() -> None:
    """Shutdown the task queue."""
    global _task_queue
    if _task_queue:
        await _task_queue.stop()
        _task_queue = None
