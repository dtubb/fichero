"""Background Task API Routes.

Provides REST endpoints for:
- Creating reindex jobs (/api/tasks/reindex)
- Triggering metrics recomputation (/api/tasks/metrics)
- Querying job status and progress
- Managing background task queue
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.workflows.tasks import (
    TaskType,
    TaskStatus,
    BackgroundTask,
    get_task_queue,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# Request/Response Models


class CreateTaskRequest(BaseModel):
    """Request to create a background task."""

    name: Optional[str] = Field(
        None, description="Optional display name for the task"
    )
    options: dict[str, Any] = Field(
        default_factory=dict, description="Task-specific options"
    )
    priority: int = Field(
        0, ge=0, le=100, description="Priority (lower = higher priority)"
    )


class TaskProgressResponse(BaseModel):
    """Task progress information."""

    current: int = Field(..., description="Current progress value")
    total: int = Field(..., description="Total items to process")
    percent: float = Field(..., description="Completion percentage")
    message: str = Field(..., description="Current status message")
    updated_at: str = Field(..., description="Last update timestamp")


class TaskResultResponse(BaseModel):
    """Task execution result."""

    success: bool = Field(..., description="Whether the task succeeded")
    message: str = Field(..., description="Result message")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Detailed results"
    )
    error: Optional[str] = Field(None, description="Error message if failed")


class TaskResponse(BaseModel):
    """Response model for a background task."""

    task_id: str = Field(..., description="Unique task identifier")
    task_type: str = Field(..., description="Type of task")
    name: str = Field(..., description="Display name")
    status: str = Field(..., description="Current status")
    progress: TaskProgressResponse = Field(..., description="Progress information")
    result: Optional[TaskResultResponse] = Field(
        None, description="Result if completed"
    )
    created_at: str = Field(..., description="Creation timestamp")
    started_at: Optional[str] = Field(None, description="Start timestamp")
    completed_at: Optional[str] = Field(None, description="Completion timestamp")
    error_message: Optional[str] = Field(None, description="Error if failed")


class TaskListResponse(BaseModel):
    """Response for task list."""

    tasks: list[TaskResponse] = Field(..., description="List of tasks")
    total: int = Field(..., description="Total count")
    offset: int = Field(..., description="Current offset")
    limit: int = Field(..., description="Page size")


class MetricsResponse(BaseModel):
    """Response for metrics recomputation."""

    document_count: int = Field(..., description="Total document count")
    embedding_stats: dict[str, Any] = Field(
        ..., description="Embedding statistics"
    )
    file_types: dict[str, int] = Field(..., description="File type distribution")
    status_distribution: dict[str, int] = Field(
        ..., description="Document status distribution"
    )


class ReindexResponse(BaseModel):
    """Response for reindex operation."""

    indexed: int = Field(..., description="Number of documents indexed")
    total: int = Field(..., description="Total documents processed")
    skipped: int = Field(..., description="Documents skipped (no content)")


# Helper functions


def _task_to_response(task: BackgroundTask) -> TaskResponse:
    """Convert BackgroundTask to API response."""
    return TaskResponse(
        task_id=task.task_id,
        task_type=task.task_type.value,
        name=task.name,
        status=task.status.value,
        progress=TaskProgressResponse(
            current=task.progress.current,
            total=task.progress.total,
            percent=task.progress.percent,
            message=task.progress.message,
            updated_at=task.progress.updated_at.isoformat(),
        ),
        result=TaskResultResponse(
            success=task.result.success,
            message=task.result.message,
            details=task.result.details,
            error=task.result.error,
        ) if task.result else None,
        created_at=task.created_at.isoformat(),
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        error_message=task.error_message,
    )


# Endpoints


@router.post(
    "/reindex",
    response_model=TaskResponse,
    summary="Create reindex job",
    description="Creates a background task to reindex all documents in LanceDB.",
)
async def create_reindex_task(
    request: CreateTaskRequest = None,
    x_fichero_library_path: str = Header(..., description="Library path"),
) -> TaskResponse:
    """Create a reindex task."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    name = request.name if request and request.name else "Reindex Documents"
    options = request.options if request else {}
    priority = request.priority if request else 0

    task = await queue.create_task(
        task_type=TaskType.REINDEX,
        name=name,
        options=options,
        priority=priority,
    )

    return _task_to_response(task)


@router.post(
    "/metrics",
    response_model=TaskResponse,
    summary="Trigger metrics recomputation",
    description="Creates a background task to recompute library metrics.",
)
async def create_metrics_task(
    request: CreateTaskRequest = None,
    x_fichero_library_path: str = Header(..., description="Library path"),
) -> TaskResponse:
    """Create a metrics recomputation task."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    name = request.name if request and request.name else "Recompute Metrics"
    options = request.options if request else {}
    priority = request.priority if request else 0

    task = await queue.create_task(
        task_type=TaskType.METRICS,
        name=name,
        options=options,
        priority=priority,
    )

    return _task_to_response(task)


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List background tasks",
    description="List all background tasks with optional filtering.",
)
async def list_tasks(
    status: Optional[str] = Query(
        None, description="Filter by status (pending, running, completed, failed, cancelled)"
    ),
    task_type: Optional[str] = Query(
        None, description="Filter by task type (reindex, metrics, repair)"
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    x_fichero_library_path: str = Header(..., description="Library path"),
) -> TaskListResponse:
    """List background tasks."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    # Parse status filter
    status_filter = None
    if status:
        try:
            status_filter = TaskStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}",
            )

    # Parse task type filter
    type_filter = None
    if task_type:
        try:
            type_filter = TaskType(task_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid task type: {task_type}",
            )

    tasks = await queue.list_tasks(
        status=status_filter,
        task_type=type_filter,
        limit=limit,
        offset=offset,
    )

    return TaskListResponse(
        tasks=[_task_to_response(task) for task in tasks],
        total=len(tasks),  # Note: actual total would require separate count query
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Get task status",
    description="Get detailed status and progress for a specific task.",
)
async def get_task(
    task_id: str,
    x_fichero_library_path: str = Header(..., description="Library path"),
) -> TaskResponse:
    """Get task by ID."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    task = await queue.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )

    return _task_to_response(task)


@router.post(
    "/{task_id}/cancel",
    response_model=TaskResponse,
    summary="Cancel pending task",
    description="Cancel a task that hasn't started yet.",
)
async def cancel_task(
    task_id: str,
    x_fichero_library_path: str = Header(..., description="Library path"),
) -> TaskResponse:
    """Cancel a pending task."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    try:
        task = await queue.cancel_task(task_id)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )

    return _task_to_response(task)


@router.delete(
    "/{task_id}",
    status_code=204,
    summary="Delete completed task",
    description="Delete a task that has completed, failed, or been cancelled.",
)
async def delete_task(
    task_id: str,
    x_fichero_library_path: str = Header(..., description="Library path"),
) -> None:
    """Delete a task."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    try:
        deleted = await queue.delete_task(task_id)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )


@router.get(
    "/{task_id}/result",
    response_model=Optional[TaskResultResponse],
    summary="Get task result",
    description="Get the result of a completed task (reindex counts, metrics data, etc.).",
)
async def get_task_result(
    task_id: str,
    x_fichero_library_path: str = Header(..., description="Library path"),
) -> Optional[TaskResultResponse]:
    """Get task result."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    task = await queue.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )

    if task.result:
        return TaskResultResponse(
            success=task.result.success,
            message=task.result.message,
            details=task.result.details,
            error=task.result.error,
        )

    return None


@router.get(
    "/reindex/{task_id}/progress",
    response_model=ReindexResponse,
    summary="Get reindex progress",
    description="Get specific progress info for a reindex task.",
)
async def get_reindex_progress(
    task_id: str,
    x_fichero_library_path: str = Header(..., description="Library path"),
) -> ReindexResponse:
    """Get reindex task progress."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    task = await queue.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )

    if task.task_type != TaskType.REINDEX:
        raise HTTPException(
            status_code=400,
            detail=f"Task {task_id} is not a reindex task",
        )

    # Return progress, or full result if completed
    details = task.result.details if task.result else {}
    return ReindexResponse(
        indexed=details.get("indexed", task.progress.current),
        total=details.get("total", task.progress.total),
        skipped=details.get("skipped", 0),
    )


@router.get(
    "/metrics/{task_id}/data",
    response_model=MetricsResponse,
    summary="Get metrics data",
    description="Get computed metrics from a completed metrics task.",
)
async def get_metrics_data(
    task_id: str,
    x_fichero_library_path: str = Header(..., description="Library path"),
) -> MetricsResponse:
    """Get metrics task result data."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    task = await queue.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )

    if task.task_type != TaskType.METRICS:
        raise HTTPException(
            status_code=400,
            detail=f"Task {task_id} is not a metrics task",
        )

    if not task.result or not task.result.success:
        raise HTTPException(
            status_code=400,
            detail=f"Task {task_id} has not completed successfully",
        )

    details = task.result.details
    return MetricsResponse(
        document_count=details.get("document_count", 0),
        embedding_stats=details.get("embedding_stats", {}),
        file_types=details.get("file_types", {}),
        status_distribution=details.get("status_distribution", {}),
    )
