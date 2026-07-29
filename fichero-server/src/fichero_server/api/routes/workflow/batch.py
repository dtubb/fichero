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

from fichero_server.db.app import get_db_path
from fichero_server.workflows.batch import (
    BatchEvent,
    BatchExecution,
    BatchItem,
    BatchItemStatus,
    BatchManager,
    BatchProgress,
    BatchStatus,
)
from fichero_server.workflows.workflow_store import WorkflowStore
from fichero_server.models import BatchListResponse

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


class BatchDeletedResponse(BaseModel):
    status: str
    batch_id: str


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


@router.get("", response_model=BatchListResponse)
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

    return BatchListResponse(items=[BatchResponse.from_batch(b, include_items=False) for b in batches], count=len(batches))


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
async def delete_batch(batch_id: str) -> BatchDeletedResponse:
    """Delete a batch and its items."""
    manager = get_batch_manager()

    batch = await manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    if batch.status == BatchStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot delete a running batch")

    await manager.delete_batch(batch_id)
    return BatchDeletedResponse(status="deleted", batch_id=batch_id)


# Resolve forward refs in BatchListResponse (see #1144).
from fichero_server.models import BatchListResponse  # noqa: E402

BatchListResponse.model_rebuild(_types_namespace={"BatchResponse": BatchResponse})


# ---------------------------------------------------------------------------
# Action layer registration (EPIC #1848 / sweep #2014) — batch domain
# ---------------------------------------------------------------------------
#
# Every batch mutation becomes ONE audited action routed through
# `registry.invoke`, which writes the generic ActionAudit + emits a typed
# change event. The actions WRAP the proven BatchManager methods (iterate-not-
# replace: the algorithms are wrapped, never re-derived); the existing SSE /
# REST routes above are untouched and stay the live-progress path.
#
# Two wrinkles drive the shapes below:
#  1. BatchManager is async + backed by the *app* DuckDB (get_db_path); the
#     action's execute() is sync and the ActionAudit lands in the *library*
#     Database passed to invoke. So execute() ignores `db` for the batch op
#     (uses the manager) and `_run_async` bridges sync->async. `_run_async`
#     also survives being called from inside a running loop (the generic
#     /api/actions/invoke handler) by off-loading to a worker thread.
#  2. create/delete/pause/cancel are discrete mutations wrapped directly.
#     execute/resume/retry are SSE generators that run live workflows; to be
#     faithful single-shot audited actions they DRAIN the generator to
#     completion (auditing who-ran + final batch state). The discrete reset
#     half of retry is also exposed via the extracted manager.reset_failed_items
#     so the transition is testable without a live run.

import asyncio as _asyncio  # noqa: E402
from datetime import datetime as _datetime  # noqa: E402

from pydantic import BaseModel as _BaseModel, Field as _Field  # noqa: E402

from fichero_server.actions.registry import action, ActionContext, ChangeSpec  # noqa: E402


def _run_async(coro: Any) -> Any:
    """Run an awaitable from a sync action.execute().

    Works whether or not an event loop is already running: outside a loop we
    use ``asyncio.run``; inside one (the async /api/actions/invoke handler) we
    off-load to a dedicated worker thread with its own loop so we never call
    ``asyncio.run`` re-entrantly.
    """
    try:
        _asyncio.get_running_loop()
    except RuntimeError:
        return _asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: _asyncio.run(coro)).result()


def _batch_snapshot(batch: BatchExecution) -> dict:
    """JSON-able full snapshot (batch + items) — the audit/undo payload."""
    return BatchResponse.from_batch(batch, include_items=True).model_dump()


def _parse_dt(value: Optional[str]) -> Optional[_datetime]:
    return _datetime.fromisoformat(value) if value else None


def _batch_from_snapshot(snap: dict) -> BatchExecution:
    """Reconstruct a BatchExecution from a `_batch_snapshot` dict (for restore)."""
    items = [
        BatchItem(
            thread_id=i["thread_id"],
            item_index=i["item_index"],
            inputs=i.get("inputs") or {},
            status=BatchItemStatus(i["status"]),
            error=i.get("error"),
            started_at=_parse_dt(i.get("started_at")),
            completed_at=_parse_dt(i.get("completed_at")),
        )
        for i in snap.get("items", [])
    ]
    return BatchExecution(
        batch_id=snap["batch_id"],
        workflow_id=snap["workflow_id"],
        status=BatchStatus(snap["status"]),
        items=items,
        created_at=_parse_dt(snap["created_at"]) or _datetime.now(),
        started_at=_parse_dt(snap.get("started_at")),
        completed_at=_parse_dt(snap.get("completed_at")),
        error_message=snap.get("error_message"),
        max_concurrent=snap.get("max_concurrent", 5),
    )


# -- params models -----------------------------------------------------------


class CreateBatchParams(_BaseModel):
    workflow_id: str
    items: list[dict[str, Any]] = _Field(
        min_length=1, description="Input dicts, one per item (>=1)."
    )
    max_concurrent: int = _Field(default=5, ge=1, le=50)


class _BatchIdParams(_BaseModel):
    batch_id: str


class DeleteBatchParams(_BatchIdParams):
    pass


class RestoreBatchParams(_BaseModel):
    snapshot: dict = _Field(description="A `_batch_snapshot` dict to re-insert.")


class ExecuteBatchParams(_BatchIdParams):
    pass


class PauseBatchParams(_BatchIdParams):
    pass


class ResumeBatchParams(_BatchIdParams):
    pass


class CancelBatchParams(_BatchIdParams):
    pass


class RetryBatchParams(_BatchIdParams):
    pass


# -- inverts -----------------------------------------------------------------


def _invert_create(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a create by deleting the created batch."""
    if not after or not after.get("batch_id"):
        return None
    return ("batch.delete", {"batch_id": after["batch_id"]})


def _invert_delete(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a delete by restoring the pre-delete snapshot."""
    if not before:
        return None
    return ("batch.restore", {"snapshot": before})


# -- actions -----------------------------------------------------------------


@action(
    "batch.create",
    CreateBatchParams,
    domains=["batch"],
    undoable=True,
    invert=_invert_create,
)
def _action_create_batch(
    db: Any, params: CreateBatchParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    manager = get_batch_manager()
    batch = _run_async(
        manager.create_batch(
            workflow_id=params.workflow_id,
            items_inputs=params.items,
            max_concurrent=params.max_concurrent,
        )
    )
    after = _batch_snapshot(batch)
    spec = ChangeSpec(
        domains=["batch"],
        target_ids=[batch.batch_id],
        before=None,
        after=after,
        emit_type="batch.created",
    )
    return after, spec


@action(
    "batch.delete",
    DeleteBatchParams,
    domains=["batch"],
    undoable=True,
    invert=_invert_delete,
)
def _action_delete_batch(
    db: Any, params: DeleteBatchParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    manager = get_batch_manager()

    async def _run() -> tuple[Optional[str], Optional[dict]]:
        existing = await manager.get_batch(params.batch_id)
        if existing is None:
            return None, None
        # Guard BEFORE mutating: a running batch must not be deleted (mirrors
        # the DELETE route's 400). Snapshot then delete only when safe.
        if existing.status == BatchStatus.RUNNING:
            return BatchStatus.RUNNING.value, None
        snapshot = _batch_snapshot(existing)
        await manager.delete_batch(params.batch_id)
        return existing.status.value, snapshot

    status, before = _run_async(_run())
    if status is None:
        raise HTTPException(status_code=404, detail=f"Batch {params.batch_id} not found")
    if status == BatchStatus.RUNNING.value:
        raise HTTPException(status_code=400, detail="Cannot delete a running batch")
    spec = ChangeSpec(
        domains=["batch"],
        target_ids=[params.batch_id],
        before=before,
        after=None,
        emit_type="batch.deleted",
    )
    return {"status": "deleted", "batch_id": params.batch_id}, spec


@action(
    "batch.restore",
    RestoreBatchParams,
    domains=["batch"],
    undoable=False,
)
def _action_restore_batch(
    db: Any, params: RestoreBatchParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Inverse of batch.delete — re-insert a snapshotted batch + its items."""
    manager = get_batch_manager()
    batch = _batch_from_snapshot(params.snapshot)

    async def _run() -> None:
        await manager._save_batch(batch)

    _run_async(_run())
    manager._batches[batch.batch_id] = batch
    after = _batch_snapshot(batch)
    spec = ChangeSpec(
        domains=["batch"],
        target_ids=[batch.batch_id],
        before=None,
        after=after,
        emit_type="batch.created",
    )
    return after, spec


@action(
    "batch.pause",
    PauseBatchParams,
    domains=["batch"],
    undoable=False,
)
def _action_pause_batch(
    db: Any, params: PauseBatchParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    manager = get_batch_manager()
    batch = _run_async(manager.pause_batch(params.batch_id))
    after = _batch_snapshot(batch)
    spec = ChangeSpec(
        domains=["batch"],
        target_ids=[params.batch_id],
        before={"status": BatchStatus.RUNNING.value},
        after={"status": batch.status.value},
        emit_type="batch.paused",
    )
    return after, spec


@action(
    "batch.cancel",
    CancelBatchParams,
    domains=["batch"],
    undoable=False,
)
def _action_cancel_batch(
    db: Any, params: CancelBatchParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    manager = get_batch_manager()

    async def _run() -> tuple[Optional[str], BatchExecution]:
        before_batch = await manager.get_batch(params.batch_id)
        before_status = before_batch.status.value if before_batch else None
        cancelled = await manager.cancel_batch(params.batch_id)
        return before_status, cancelled

    before_status, batch = _run_async(_run())
    after = _batch_snapshot(batch)
    spec = ChangeSpec(
        domains=["batch"],
        target_ids=[params.batch_id],
        before={"status": before_status},
        after={"status": batch.status.value},
        emit_type="batch.cancelled",
    )
    return after, spec


@action(
    "batch.execute",
    ExecuteBatchParams,
    domains=["batch"],
    undoable=False,
)
def _action_execute_batch(
    db: Any, params: ExecuteBatchParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Run a batch to completion (drains the SSE generator) and audits the run.

    The live-progress SSE route above stays the UI path; this single-shot
    action is what chat tools (#1847) / App Intents (#1837) / tests drive.
    """
    manager = get_batch_manager()
    store = get_workflow_store()

    async def _run() -> tuple[Optional[dict], Optional[dict]]:
        before_batch = await manager.get_batch(params.batch_id)
        before = _batch_snapshot(before_batch) if before_batch else None
        async for _event in manager.execute_batch(params.batch_id, store):
            pass
        final = await manager.get_batch(params.batch_id)
        after = _batch_snapshot(final) if final else None
        return before, after

    before, after = _run_async(_run())
    spec = ChangeSpec(
        domains=["batch"],
        target_ids=[params.batch_id],
        before=before,
        after=after,
        emit_type="batch.executed",
    )
    return after or {"batch_id": params.batch_id}, spec


@action(
    "batch.resume",
    ResumeBatchParams,
    domains=["batch"],
    undoable=False,
)
def _action_resume_batch(
    db: Any, params: ResumeBatchParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Resume a paused batch to completion (drains the SSE generator)."""
    manager = get_batch_manager()
    store = get_workflow_store()

    async def _run() -> tuple[Optional[dict], Optional[dict]]:
        before_batch = await manager.get_batch(params.batch_id)
        before = _batch_snapshot(before_batch) if before_batch else None
        async for _event in manager.resume_batch(params.batch_id, store):
            pass
        final = await manager.get_batch(params.batch_id)
        after = _batch_snapshot(final) if final else None
        return before, after

    before, after = _run_async(_run())
    spec = ChangeSpec(
        domains=["batch"],
        target_ids=[params.batch_id],
        before=before,
        after=after,
        emit_type="batch.resumed",
    )
    return after or {"batch_id": params.batch_id}, spec


@action(
    "batch.retry",
    RetryBatchParams,
    domains=["batch"],
    undoable=False,
)
def _action_retry_batch(
    db: Any, params: RetryBatchParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Retry a batch's failed items: reset them to PENDING then run to completion.

    Audits the whole retry (who-retried + final state). The discrete reset is
    the extracted ``manager.reset_failed_items`` so the transition stays one
    proven code path with the streaming retry route.
    """
    manager = get_batch_manager()
    store = get_workflow_store()

    async def _run() -> tuple[Optional[dict], Optional[dict]]:
        before_batch = await manager.get_batch(params.batch_id)
        before = _batch_snapshot(before_batch) if before_batch else None
        async for _event in manager.retry_failed_items(params.batch_id, store):
            pass
        final = await manager.get_batch(params.batch_id)
        after = _batch_snapshot(final) if final else None
        return before, after

    before, after = _run_async(_run())
    spec = ChangeSpec(
        domains=["batch"],
        target_ids=[params.batch_id],
        before=before,
        after=after,
        emit_type="batch.retried",
    )
    return after or {"batch_id": params.batch_id}, spec


# ---------------------------------------------------------------------------
# The MISSING workflow action (#2018) — workflow.run (single-shot)
# ---------------------------------------------------------------------------
#
# The #2000-era inventory flagged "run workflow on docs" as a capability with no
# single endpoint: the UI does it in TWO steps (POST /batches to create, then
# POST /batches/{id}/execute to run). workflow.run COLLAPSES that into one audited
# action — it WRAPS the proven BatchManager.create_batch + execute_batch
# (iterate-not-replace: both algorithms are wrapped, never re-derived), draining
# the SSE generator to completion, and returns the run/task id (the batch_id) the
# caller polls. NOT undoable: a workflow run produces artifacts/side effects with
# no clean inverse (delete the batch via batch.delete if you must discard it).


class WorkflowRunParams(_BaseModel):
    workflow_id: str
    items: list[dict[str, Any]] = _Field(
        min_length=1, description="Input dicts, one per document (>=1)."
    )
    max_concurrent: int = _Field(default=5, ge=1, le=50)


@action(
    "workflow.run",
    WorkflowRunParams,
    domains=["workflow", "batch"],
    undoable=False,
)
def _action_workflow_run(
    db: Any, params: WorkflowRunParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Create a batch over the docs AND run it to completion in one shot.

    Returns ``run_id`` / ``batch_id`` (same value) so a caller can poll
    ``/api/batches/{id}`` for results — the one-call equivalent of the UI's
    create-then-execute two-step.
    """
    manager = get_batch_manager()
    store = get_workflow_store()

    async def _run() -> Optional[BatchExecution]:
        batch = await manager.create_batch(
            workflow_id=params.workflow_id,
            items_inputs=params.items,
            max_concurrent=params.max_concurrent,
        )
        async for _event in manager.execute_batch(batch.batch_id, store):
            pass
        return await manager.get_batch(batch.batch_id)

    final = _run_async(_run())
    after = _batch_snapshot(final) if final else None
    run_id = final.batch_id if final else None
    result = {
        "run_id": run_id,
        "batch_id": run_id,
        "status": final.status.value if final else None,
    }
    spec = ChangeSpec(
        domains=["workflow", "batch"],
        target_ids=[run_id] if run_id else [],
        before=None,
        after=after,
        emit_type="workflow.run",
    )
    return result, spec
