"""The task API (`/api/tasks`): reindex, metrics, repair, vector repair, KG metrics and re-anchor.

Each task is a job (#5353): a row in the project's `jobs` table of one of the six task kinds
(`task_workers.TASK_JOB_KINDS`), run by the one scheduler (`execution/jobs.py`), durable, pausable
and shown in Activity. `JobTaskQueue` answers the routes from those rows in the shapes they always
had. The `TaskQueue` this replaced (APScheduler, its own `background_tasks` table in a file of its
own) was never started by the engine, so the routes answered 503 for its whole life; it is gone.
"""

import asyncio
import json
from typing import Any, Optional

from fichero_server.core.timeutil import ensure_utc

from .task_types import (
    BackgroundTask,
    TaskConfig,
    TaskProgress,
    TaskResult,
    TaskStatus,
    TaskType,
)

__all__ = [
    "BackgroundTask",
    "JobTaskQueue",
    "TaskConfig",
    "TaskProgress",
    "TaskResult",
    "TaskStatus",
    "TaskType",
    "job_task_queue",
]

#: The library path the routes put in a task's options; not part of the task itself.
_TASK_LIBRARY_PATH_OPTION = "_library_path"


# =============================================================================
# The task API over the job table (#5353)
# =============================================================================

_JOB_STATUS = {
    "waiting": TaskStatus.PENDING,
    "paused": TaskStatus.PENDING,
    "running": TaskStatus.RUNNING,
    "done": TaskStatus.COMPLETED,
    "failed": TaskStatus.FAILED,
    "cancelled": TaskStatus.CANCELLED,
}


class JobTaskQueue:
    """What `/api/tasks` asks of a queue, answered from the project's `jobs` table: a task is a
    job of one of the six task kinds (`task_workers.TASK_JOB_KINDS`), run by the one scheduler.
    ponytail: priority is not used; the lanes order work."""

    def __init__(self, library_path: str):
        from fichero_server.db.manager import db_manager

        from .task_workers import register_job_kinds

        register_job_kinds()
        self.db = db_manager.get_database(library_path)

    @property
    def _running(self) -> bool:
        """What `/api/tasks/health` calls the queue running: background work is not paused."""
        from fichero_server.execution import jobs

        return not jobs.is_paused()

    async def create_task(self, task_type: TaskType, name: str, options: Optional[dict[str, Any]] = None,
                          priority: int = 0, timeout_seconds: Optional[int] = None) -> BackgroundTask:
        from fichero_server.execution import jobs

        options = {k: v for k, v in (options or {}).items() if k != _TASK_LIBRARY_PATH_OPTION}
        # Asking twice for the same work while it waits is one job.
        subject = json.dumps(options, sort_keys=True, default=str)
        job_id = await asyncio.to_thread(
            jobs.enqueue, self.db, task_type.value, subject, started_by="person",
            detail=json.dumps({"name": name, "options": options}, default=str))
        return await self.get_task(job_id)

    async def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        rows = await self._find(job_id=task_id, limit=1)
        return rows[0] if rows else None

    async def list_tasks(self, status: Optional[TaskStatus] = None, task_type: Optional[TaskType] = None,
                         limit: int = 100, offset: int = 0) -> list[BackgroundTask]:
        states = [state for state, mapped in _JOB_STATUS.items() if mapped == status] if status else None
        return await self._find(states=states, kind=task_type.value if task_type else None,
                                limit=limit, offset=offset)

    async def cancel_task(self, task_id: str) -> Optional[BackgroundTask]:
        from fichero_server.execution import jobs

        task = await self.get_task(task_id)
        if task is None:
            return None
        if task.status != TaskStatus.PENDING:
            raise ValueError(f"Cannot cancel task with status {task.status.value}")
        await asyncio.to_thread(jobs.cancel_job, self.db, task_id)
        return await self.get_task(task_id)

    async def delete_task(self, task_id: str) -> bool:
        from fichero_server.execution import jobs

        task = await self.get_task(task_id)
        if task is None:
            return False
        if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            raise ValueError("Cannot delete running/pending task")
        await asyncio.to_thread(jobs.delete_job, self.db, task_id)
        return True

    async def _find(self, *, job_id: str | None = None, states: list[str] | None = None,
                    kind: str | None = None, limit: int = 100, offset: int = 0) -> list[BackgroundTask]:
        from fichero_server.execution import jobs

        from .task_workers import TASK_JOB_KINDS

        kinds = [kind] if kind else list(TASK_JOB_KINDS)
        rows = await asyncio.to_thread(jobs.find_jobs, self.db, kinds=kinds, states=states, job_id=job_id,
                                       limit=limit, offset=offset)
        return [_job_to_task(row) for row in rows]


def _job_to_task(row: dict[str, Any]) -> BackgroundTask:
    job_id, kind, state, reason = row["id"], row["kind"], row["state"], row["reason"]
    detail_json, created_at = row["detail"], row["created_at"]
    started_at, finished_at = row["started_at"], row["finished_at"]
    detail = json.loads(detail_json or "{}")
    task_type = TaskType(kind)
    progress = detail.get("progress") or {}
    result = detail.get("result")
    task = BackgroundTask(
        task_id=job_id,
        task_type=task_type,
        name=detail.get("name") or kind,
        status=_JOB_STATUS.get(state, TaskStatus.PENDING),
        config=TaskConfig(task_type=task_type, options=detail.get("options") or {}),
        progress=TaskProgress(current=progress.get("current", 0), total=progress.get("total", 0),
                              percent=progress.get("percent", 0.0), message=progress.get("message") or reason or ""),
        result=TaskResult(**result) if result else None,
        created_at=ensure_utc(created_at),
        started_at=ensure_utc(started_at),
        completed_at=ensure_utc(finished_at),
        error_message=reason if state == "failed" else None,
    )
    return task


def job_task_queue(library_path: str) -> JobTaskQueue:
    """The queue `/api/tasks` uses: the library's job table."""
    return JobTaskQueue(library_path)
