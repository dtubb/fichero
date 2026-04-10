"""
Batch Execution API Routes.

Endpoints for managing batch workflow executions:
- Create, execute, pause, resume, cancel batches
- Progress streaming via SSE
- Retry failed items
"""

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from fichero.app_db import get_db_path
from fichero.workflows.batch import (
    BatchEvent,
    BatchExecution,
    BatchItem,
    BatchManager,
    BatchProgress,
    BatchStatus,
)
from fichero.workflows.workflow_store import WorkflowStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/batches", tags=["batches"])

# Singleton batch manager
_batch_manager: Optional[BatchManager] = None


def get_batch_manager() -> BatchManager:
    """Get or create the batch manager singleton."""
    global _batch_manager
    if _batch_manager is None:
        db_path = get_db_path()
        _batch_manager = BatchManager(db_path)
    return _batch_manager


def get_workflow_store() -> WorkflowStore:
    """Get workflow store instance."""
    db_path = get_db_path()
    return WorkflowStore(db_path)


# Pydantic models for API


class BatchItemResponse(BaseModel):
    """Response model for a batch item."""

    thread_id: str
    item_index: int
    inputs: dict[str, Any]
    status: str
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    @classmethod
    def from_item(cls, item: BatchItem) -> "BatchItemResponse":
        return cls(
            thread_id=item.thread_id,
            item_index=item.item_index,
            inputs=item.inputs,
            status=item.status.value,
            error=item.error,
            started_at=item.started_at.isoformat() if item.started_at else None,
            completed_at=item.completed_at.isoformat() if item.completed_at else None,
        )


class BatchProgressResponse(BaseModel):
    """Response model for batch progress."""

    batch_id: str
    total_items: int
    completed_items: int
    failed_items: int
    running_items: int
    pending_items: int
    progress_percent: float
    estimated_remaining_seconds: Optional[float] = None
    avg_item_duration_seconds: Optional[float] = None

    @classmethod
    def from_progress(cls, progress: BatchProgress) -> "BatchProgressResponse":
        return cls(
            batch_id=progress.batch_id,
            total_items=progress.total_items,
            completed_items=progress.completed_items,
            failed_items=progress.failed_items,
            running_items=progress.running_items,
            pending_items=progress.pending_items,
            progress_percent=progress.progress_percent,
            estimated_remaining_seconds=progress.estimated_remaining_seconds,
            avg_item_duration_seconds=progress.avg_item_duration_seconds,
        )


class BatchResponse(BaseModel):
    """Response model for a batch execution."""

    batch_id: str
    workflow_id: str
    status: str
    total_items: int
    completed_items: int
    failed_items: int
    max_concurrent: int
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    items: list[BatchItemResponse] = Field(default_factory=list)

    @classmethod
    def from_batch(
        cls, batch: BatchExecution, include_items: bool = False
    ) -> "BatchResponse":
        return cls(
            batch_id=batch.batch_id,
            workflow_id=batch.workflow_id,
            status=batch.status.value,
            total_items=batch.total_items,
            completed_items=batch.completed_items,
            failed_items=batch.failed_items,
            max_concurrent=batch.max_concurrent,
            created_at=batch.created_at.isoformat(),
            started_at=batch.started_at.isoformat() if batch.started_at else None,
            completed_at=batch.completed_at.isoformat() if batch.completed_at else None,
            error_message=batch.error_message,
            items=[BatchItemResponse.from_item(i) for i in batch.items]
            if include_items
            else [],
        )


class CreateBatchRequest(BaseModel):
    """Request model for creating a batch."""

    workflow_id: str
    items: list[dict[str, Any]] = Field(
        ..., description="List of input dictionaries, one per item"
    )
    max_concurrent: int = Field(
        default=5, ge=1, le=50, description="Maximum concurrent executions"
    )


class BatchEventResponse(BaseModel):
    """Response model for a batch event."""

    batch_id: str
    event_type: str
    thread_id: Optional[str] = None
    item_index: Optional[int] = None
    progress: Optional[BatchProgressResponse] = None
    error: Optional[str] = None
    timestamp: str

    @classmethod
    def from_event(cls, event: BatchEvent) -> "BatchEventResponse":
        return cls(
            batch_id=event.batch_id,
            event_type=event.event_type,
            thread_id=event.thread_id,
            item_index=event.item_index,
            progress=BatchProgressResponse.from_progress(event.progress)
            if event.progress
            else None,
            error=event.error,
            timestamp=event.timestamp.isoformat(),
        )


# API Endpoints


@router.post("", response_model=BatchResponse)
async def create_batch(request: CreateBatchRequest) -> BatchResponse:
    """
    Create a new batch execution.

    The batch is created in PENDING status and must be started with
    the /execute endpoint or the /progress SSE endpoint.
    """
    manager = get_batch_manager()

    if not request.items:
        raise HTTPException(status_code=400, detail="At least one item is required")

    batch = await manager.create_batch(
        workflow_id=request.workflow_id,
        items_inputs=request.items,
        max_concurrent=request.max_concurrent,
    )

    logger.info(f"Created batch {batch.batch_id} with {len(request.items)} items")
    return BatchResponse.from_batch(batch, include_items=True)


@router.get("", response_model=list[BatchResponse])
async def list_batches(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[BatchResponse]:
    """List all batches with optional status filtering."""
    manager = get_batch_manager()

    filter_status = BatchStatus(status) if status else None
    batches = await manager.list_batches(
        status=filter_status, limit=limit, offset=offset
    )

    return [BatchResponse.from_batch(b, include_items=False) for b in batches]


@router.get("/{batch_id}", response_model=BatchResponse)
async def get_batch(batch_id: str, include_items: bool = True) -> BatchResponse:
    """Get batch details by ID."""
    manager = get_batch_manager()

    batch = await manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    return BatchResponse.from_batch(batch, include_items=include_items)


@router.get("/{batch_id}/progress", response_model=BatchProgressResponse)
async def get_batch_progress(batch_id: str) -> BatchProgressResponse:
    """Get current progress for a batch."""
    manager = get_batch_manager()

    batch = await manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    return BatchProgressResponse.from_progress(batch.get_progress())


@router.post("/{batch_id}/execute")
async def execute_batch(batch_id: str):
    """
    Execute a batch with Server-Sent Events progress streaming.

    Returns an SSE stream of batch events.
    """
    manager = get_batch_manager()
    store = get_workflow_store()

    batch = await manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    async def event_generator():
        try:
            async for event in manager.execute_batch(batch_id, store):
                response = BatchEventResponse.from_event(event)
                yield f"data: {response.model_dump_json()}\n\n"
        except Exception as e:
            error_event = {
                "batch_id": batch_id,
                "event_type": "error",
                "error": str(e),
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{batch_id}/pause", response_model=BatchResponse)
async def pause_batch(batch_id: str) -> BatchResponse:
    """Pause a running batch."""
    manager = get_batch_manager()

    try:
        batch = await manager.pause_batch(batch_id)
        return BatchResponse.from_batch(batch, include_items=False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{batch_id}/resume")
async def resume_batch(batch_id: str):
    """
    Resume a paused batch with SSE progress streaming.

    Returns an SSE stream of batch events.
    """
    manager = get_batch_manager()
    store = get_workflow_store()

    batch = await manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    async def event_generator():
        try:
            async for event in manager.resume_batch(batch_id, store):
                response = BatchEventResponse.from_event(event)
                yield f"data: {response.model_dump_json()}\n\n"
        except Exception as e:
            error_event = {
                "batch_id": batch_id,
                "event_type": "error",
                "error": str(e),
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{batch_id}/cancel", response_model=BatchResponse)
async def cancel_batch(batch_id: str) -> BatchResponse:
    """Cancel a running or paused batch."""
    manager = get_batch_manager()

    try:
        batch = await manager.cancel_batch(batch_id)
        return BatchResponse.from_batch(batch, include_items=False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{batch_id}/retry")
async def retry_batch(batch_id: str):
    """
    Retry failed items in a batch with SSE progress streaming.

    Returns an SSE stream of batch events.
    """
    manager = get_batch_manager()
    store = get_workflow_store()

    batch = await manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    async def event_generator():
        try:
            async for event in manager.retry_failed_items(batch_id, store):
                response = BatchEventResponse.from_event(event)
                yield f"data: {response.model_dump_json()}\n\n"
        except Exception as e:
            error_event = {
                "batch_id": batch_id,
                "event_type": "error",
                "error": str(e),
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/{batch_id}")
async def delete_batch(batch_id: str) -> dict[str, str]:
    """Delete a batch and its items."""
    manager = get_batch_manager()

    batch = await manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    if batch.status == BatchStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot delete a running batch")

    await manager.delete_batch(batch_id)
    return {"status": "deleted", "batch_id": batch_id}
