"""Background Task API Routes.

Provides REST endpoints for:
- Creating reindex jobs (/api/tasks/reindex)
- Triggering metrics recomputation (/api/tasks/metrics)
- Querying job status and progress
- Managing background task queue
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fichero.api.library_header import require_library_path
from pydantic import BaseModel, Field

from fichero.workflows.tasks import (
    TaskType,
    TaskStatus,
    BackgroundTask,
    _TASK_LIBRARY_PATH_OPTION,
    get_task_queue,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])


# Request/Response Models


class CreateTaskRequest(BaseModel):
    """Request to create a background task."""

    name: Optional[str] = Field(None, description="Optional display name for the task")
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
    embedding_stats: dict[str, Any] = Field(..., description="Embedding statistics")
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
        )
        if task.result
        else None,
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
    x_fichero_library_path: str = Depends(require_library_path),
) -> TaskResponse:
    """Create a reindex task."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    name = request.name if request and request.name else "Reindex Documents"
    options = dict(request.options) if request else {}
    options[_TASK_LIBRARY_PATH_OPTION] = x_fichero_library_path
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
    x_fichero_library_path: str = Depends(require_library_path),
) -> TaskResponse:
    """Create a metrics recomputation task."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    name = request.name if request and request.name else "Recompute Metrics"
    options = dict(request.options) if request else {}
    options[_TASK_LIBRARY_PATH_OPTION] = x_fichero_library_path
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
        None,
        description="Filter by status (pending, running, completed, failed, cancelled)",
    ),
    task_type: Optional[str] = Query(
        None, description="Filter by task type (reindex, metrics, repair)"
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    x_fichero_library_path: str = Depends(require_library_path),
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
    x_fichero_library_path: str = Depends(require_library_path),
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
    x_fichero_library_path: str = Depends(require_library_path),
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
    x_fichero_library_path: str = Depends(require_library_path),
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
    x_fichero_library_path: str = Depends(require_library_path),
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

    if task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
        raise HTTPException(status_code=202, detail=f"Task {task_id} is still running")
    logger.error("Terminal task %s has no result (status=%s)", task_id, task.status)
    raise HTTPException(status_code=409, detail=f"Task {task_id} has no result")


@router.get(
    "/reindex/{task_id}/progress",
    response_model=ReindexResponse,
    summary="Get reindex progress",
    description="Get specific progress info for a reindex task.",
)
async def get_reindex_progress(
    task_id: str,
    x_fichero_library_path: str = Depends(require_library_path),
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
    x_fichero_library_path: str = Depends(require_library_path),
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
    required = ("document_count", "embedding_stats", "file_types", "status_distribution")
    missing = [key for key in required if key not in details]
    if missing:
        logger.error("Metrics task %s has incomplete result: %s", task_id, missing)
        raise HTTPException(status_code=409, detail=f"Task {task_id} has incomplete metrics result")
    return MetricsResponse(
        document_count=details["document_count"],
        embedding_stats=details["embedding_stats"],
        file_types=details["file_types"],
        status_distribution=details["status_distribution"],
    )


# Additional Task Types (Issue #369)
# =============================================================================


class KGMetricsResponse(BaseModel):
    """Response for knowledge graph metrics."""

    entity_count: int = Field(..., description="Total number of entities")
    entity_by_type: dict[str, int] = Field(..., description="Entities by type")
    claim_count: int = Field(..., description="Total number of claims")
    claims_by_status: dict[str, int] = Field(
        ..., description="Claims by curation status"
    )
    claims_by_type: dict[str, int] = Field(..., description="Claims by claim type")
    claims_with_sources: int = Field(..., description="Claims with source references")
    link_count: int = Field(..., description="Total number of claim links")
    links_by_relation: dict[str, int] = Field(..., description="Links by relation type")


class VectorRepairResponse(BaseModel):
    """Response for vector repair task."""

    added: int = Field(..., description="Embeddings added")
    removed: int = Field(..., description="Embeddings removed")
    checked: int = Field(..., description="Documents checked")
    document_count: int = Field(..., description="Total documents")
    vector_count: int = Field(..., description="Total vectors in index")


class TaskSystemHealthResponse(BaseModel):
    """Health status for the task system."""

    status: str = Field(..., description="System status: healthy, degraded, or down")
    queue_running: bool = Field(..., description="Whether task queue is active")
    pending_count: int = Field(..., description="Number of pending tasks")
    running_count: int = Field(..., description="Number of running tasks")
    completed_count: int = Field(
        ..., description="Number of completed tasks in last 24h"
    )
    failed_count: int = Field(..., description="Number of failed tasks in last 24h")
    supported_task_types: list[str] = Field(..., description="Supported task types")


@router.post(
    "/vector-repair",
    response_model=TaskResponse,
    summary="Create vector repair job",
    description="Creates a background task to repair LanceDB vector index consistency.",
)
async def create_vector_repair_task(
    request: CreateTaskRequest = None,
    x_fichero_library_path: str = Depends(require_library_path),
) -> TaskResponse:
    """Create a vector repair task."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    name = request.name if request and request.name else "Repair Vector Index"
    options = request.options if request else {}
    priority = request.priority if request else 0

    task = await queue.create_task(
        task_type=TaskType.VECTOR_REPAIR,
        name=name,
        options=options,
        priority=priority,
    )

    return _task_to_response(task)


@router.post(
    "/kg-metrics",
    response_model=TaskResponse,
    summary="Create knowledge graph metrics job",
    description="Creates a background task to recompute knowledge graph metrics.",
)
async def create_kg_metrics_task(
    request: CreateTaskRequest = None,
    x_fichero_library_path: str = Depends(require_library_path),
) -> TaskResponse:
    """Create a knowledge graph metrics task."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    name = request.name if request and request.name else "Recompute KG Metrics"
    options = request.options if request else {}
    priority = request.priority if request else 0

    task = await queue.create_task(
        task_type=TaskType.KG_METRICS,
        name=name,
        options=options,
        priority=priority,
    )

    return _task_to_response(task)


@router.get(
    "/vector-repair/{task_id}/progress",
    response_model=VectorRepairResponse,
    summary="Get vector repair progress",
    description="Get specific progress info for a vector repair task.",
)
async def get_vector_repair_progress(
    task_id: str,
    x_fichero_library_path: str = Depends(require_library_path),
) -> VectorRepairResponse:
    """Get vector repair task progress."""
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

    if task.task_type != TaskType.VECTOR_REPAIR:
        raise HTTPException(
            status_code=400,
            detail=f"Task {task_id} is not a vector repair task",
        )

    details = task.result.details if task.result else {}
    return VectorRepairResponse(
        added=details.get("added", 0),
        removed=details.get("removed", 0),
        checked=details.get("checked", task.progress.current),
        document_count=details.get("document_count", 0),
        vector_count=details.get("vector_count", 0),
    )


@router.get(
    "/kg-metrics/{task_id}/data",
    response_model=KGMetricsResponse,
    summary="Get KG metrics data",
    description="Get computed metrics from a completed KG metrics task.",
)
async def get_kg_metrics_data(
    task_id: str,
    x_fichero_library_path: str = Depends(require_library_path),
) -> KGMetricsResponse:
    """Get knowledge graph metrics task result data."""
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

    if task.task_type != TaskType.KG_METRICS:
        raise HTTPException(
            status_code=400,
            detail=f"Task {task_id} is not a KG metrics task",
        )

    if not task.result or not task.result.success:
        raise HTTPException(
            status_code=400,
            detail=f"Task {task_id} has not completed successfully",
        )

    details = task.result.details
    required = (
        "entity_count", "entity_by_type", "claim_count", "claims_by_status",
        "claims_by_type", "claims_with_sources", "link_count", "links_by_relation",
    )
    missing = [key for key in required if key not in details]
    if missing:
        logger.error("KG metrics task %s has incomplete result: %s", task_id, missing)
        raise HTTPException(status_code=409, detail=f"Task {task_id} has incomplete KG metrics result")
    return KGMetricsResponse(
        entity_count=details["entity_count"],
        entity_by_type=details["entity_by_type"],
        claim_count=details["claim_count"],
        claims_by_status=details["claims_by_status"],
        claims_by_type=details["claims_by_type"],
        claims_with_sources=details["claims_with_sources"],
        link_count=details["link_count"],
        links_by_relation=details["links_by_relation"],
    )


@router.get(
    "/health",
    response_model=TaskSystemHealthResponse,
    summary="Get task system health",
    description="Get health status and statistics for the background task system.",
)
async def get_task_system_health(
    x_fichero_library_path: str = Depends(require_library_path),
) -> TaskSystemHealthResponse:
    """Get health status of the task system."""
    queue = get_task_queue()
    if not queue:
        raise HTTPException(
            status_code=503,
            detail="Task queue not initialized",
        )

    # Get task counts by status
    all_tasks = await queue.list_tasks(limit=1000)

    pending_count = sum(1 for t in all_tasks if t.status == TaskStatus.PENDING)
    running_count = sum(1 for t in all_tasks if t.status == TaskStatus.RUNNING)

    last_24h = datetime.now() - timedelta(hours=24)
    recent_tasks = [t for t in all_tasks if t.created_at > last_24h]
    completed_count = sum(1 for t in recent_tasks if t.status == TaskStatus.COMPLETED)
    failed_count = sum(1 for t in recent_tasks if t.status == TaskStatus.FAILED)

    # Determine status
    status = "healthy"
    if failed_count > completed_count:
        status = "degraded"
    if not queue._running:
        status = "down"

    return TaskSystemHealthResponse(
        status=status,
        queue_running=queue._running,
        pending_count=pending_count,
        running_count=running_count,
        completed_count=completed_count,
        failed_count=failed_count,
        supported_task_types=[
            TaskType.REINDEX.value,
            TaskType.METRICS.value,
            TaskType.REPAIR.value,
            TaskType.VECTOR_REPAIR.value,
            TaskType.KG_METRICS.value,
        ],
    )
