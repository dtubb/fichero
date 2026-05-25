"""
Workflow Execution Core Routes

Execute, stream, resume, and status-check workflows.
"""

import asyncio
import json
import logging
import queue
import threading
from typing import Any, AsyncGenerator
from uuid import uuid4

from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    BackgroundTasks,
    Request,
)
from fastapi.responses import StreamingResponse

from fichero.db import Database
from fichero.api.main import get_library_database
from fichero.models import Workflow
from fichero.workflows.checkpointer import AsyncDuckDBCheckpointer
from fichero.workflows.workflow_store import WorkflowStore
from fichero.workflows.runtime import (
    create_compiled_app_with_checkpointer,
    to_workflow_def,
)

from .schemas import (
    ExecuteAcceptedResponse,
    ExecuteWorkflowRequest,
    ExecutionStatusResponse,
    ResumeWorkflowRequest,
    format_sse,
)
from .runner import (
    _get_workflow_state,
    _run_workflow_in_background,
    _set_workflow_state,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Helper Functions
# =============================================================================


def _sanitize_for_json(value: Any) -> Any:
    """Recursively convert LangGraph/runtime values to JSON-safe data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_for_json(v) for v in value]
    if hasattr(value, "model_dump"):
        return _sanitize_for_json(value.model_dump())
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _build_workflow_with_checkpointer(
    workflow: Workflow,
    checkpointer: AsyncDuckDBCheckpointer,
    interrupt_before: list[str] | None = None,
    interrupt_after: list[str] | None = None,
    enable_parallel: bool = True,
):
    """
    Build a workflow with checkpointing using the shared runtime path.
    """
    workflow_def = to_workflow_def(workflow)
    return create_compiled_app_with_checkpointer(
        workflow_def,
        checkpointer=checkpointer,
        enable_parallel=enable_parallel,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/stream/{thread_id}")
async def stream_workflow_events(thread_id: str) -> StreamingResponse:
    """
    Subscribe to SSE events for a running workflow.

    This endpoint returns a Server-Sent Events stream for a workflow
    that was started via POST /execute. Connect to this endpoint
    immediately after receiving the 202 Accepted response.

    Events include:
    - start: Workflow execution started
    - node_begin: A node started executing
    - node_end: A node finished executing
    - parallel_complete: Parallel file processing completed
    - complete: Workflow finished successfully
    - error: An error occurred
    - systemic_error: Too many consecutive failures

    Args:
        thread_id: The thread ID returned from /execute

    Returns:
        StreamingResponse with SSE events
    """
    # Check if workflow is being tracked
    state = _get_workflow_state(thread_id)
    if not state:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow thread not found: {thread_id}. It may have already completed.",
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events from the workflow's event queue.

        The queue is a thread-safe ``queue.Queue`` — the workflow runs
        on a dedicated worker thread (#1000), so the blocking ``.get()``
        is offloaded to a thread-pool worker via ``run_in_executor`` to
        keep the API event loop free.
        """
        event_queue: queue.Queue = state["events"]
        loop = asyncio.get_running_loop()

        while True:
            try:
                # Wait for next event with timeout, off the event loop.
                event = await loop.run_in_executor(
                    None, event_queue.get, True, 60.0
                )

                if event is None:
                    # Sentinel value - stream is complete
                    break

                yield format_sse(event)

            except queue.Empty:
                # Send keepalive comment to prevent connection timeout
                yield ": keepalive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/execute", status_code=202)
async def execute_workflow(
    request: ExecuteWorkflowRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_library_database),
) -> ExecuteAcceptedResponse:
    """
    Execute a workflow (non-blocking).

    This endpoint starts workflow execution in the background and returns
    immediately with a 202 Accepted response. Use the stream_url to
    subscribe to real-time progress events via SSE.

    Flow:
    1. POST /execute → 202 Accepted with thread_id and stream_url
    2. GET /stream/{thread_id} → SSE stream with progress events
    3. Events: start, node_begin, node_end, parallel_complete, complete, error

    Args:
        request: Execution parameters including workflow_id and inputs

    Returns:
        202 Accepted with thread_id and stream_url for SSE subscription

    Raises:
        404: Workflow not found
    """
    try:
        # Load workflow
        store = WorkflowStore(db)
        workflow = store.get(request.workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404, detail=f"Workflow not found: {request.workflow_id}"
            )

        # Debug: log workflow data being executed
        print(f"[EXECUTE] Workflow '{workflow.name}' (id={workflow.id})")
        print(f"[EXECUTE]   nodes: {len(workflow.nodes)}, edges: {len(workflow.edges)}")
        for i, node in enumerate(workflow.nodes[:3]):  # Log first 3 nodes
            print(
                f"[EXECUTE]   node[{i}]: tool={node.get('tool', '?')}, id={node.get('id', '?')[:8]}..."
            )
        if not workflow.nodes:
            print(
                "[EXECUTE]   WARNING: Workflow has no nodes! Execution will complete instantly."
            )

        # Generate thread ID if not provided or if force_new is True
        if request.force_new or not request.thread_id:
            thread_id = f"thread-{uuid4().hex[:12]}"
        else:
            thread_id = request.thread_id

        # Create event queue for this workflow. A thread-safe queue.Queue
        # (not asyncio.Queue) because the workflow runs on a dedicated
        # worker thread (#1000) and pushes events across the thread
        # boundary; the SSE endpoint drains it via run_in_executor.
        event_queue: queue.Queue = queue.Queue()

        # Register workflow state
        _set_workflow_state(
            thread_id,
            {
                "workflow_id": request.workflow_id,
                "workflow_name": workflow.name,
                "status": "accepted",
                "events": event_queue,
                "error": None,
                "final_state": None,
            },
        )

        # Start background execution on a DEDICATED WORKER THREAD with
        # its own event loop (#1000). Previously this was
        # asyncio.create_task on the FastAPI main loop — any tool node
        # that did synchronous blocking work (a long DuckDB query, a
        # sync embedding call, an fm-bridge subprocess wait) froze the
        # whole loop, so /api/health stopped responding and the app
        # blanked. Running on its own thread keeps the API loop free no
        # matter what a tool node does. Cross-thread event delivery goes
        # through the thread-safe queue.Queue created above.
        def _run_workflow_thread() -> None:
            asyncio.run(
                _run_workflow_in_background(
                    thread_id=thread_id,
                    workflow=workflow,
                    request=request,
                    db=db,
                )
            )

        threading.Thread(
            target=_run_workflow_thread,
            name=f"workflow-{thread_id}",
            daemon=True,
        ).start()

        # Build stream URL
        base_url = str(http_request.base_url).rstrip("/")
        stream_url = f"{base_url}/api/workflows/stream/{thread_id}"

        print(f"[EXECUTE] Started background execution, stream at: {stream_url}")

        return ExecuteAcceptedResponse(
            thread_id=thread_id,
            workflow_id=request.workflow_id,
            workflow_name=workflow.name,
            status="accepted",
            stream_url=stream_url,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to start workflow {request.workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/threads/{thread_id}/resume")
async def resume_workflow(
    thread_id: str,
    request: ResumeWorkflowRequest | None = None,
    db: Database = Depends(get_library_database),
) -> ExecutionStatusResponse:
    """
    Resume a paused workflow from checkpoint.

    Continues execution from the last checkpoint, optionally with new inputs.

    Args:
        thread_id: Thread ID from original execution
        request: Optional new inputs

    Returns:
        Execution status after resume

    Raises:
        404: Thread not found
        500: Resume error
    """
    try:
        # Get checkpointer
        checkpointer = AsyncDuckDBCheckpointer.from_db_path(db.path)

        # Get checkpoint
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        checkpoint_tuple = await checkpointer.aget_tuple(config)

        if not checkpoint_tuple:
            raise HTTPException(
                status_code=404, detail=f"No checkpoint found for thread: {thread_id}"
            )

        # workflow_id is stored in channel_values (CheckpointMetadata is
        # LangGraph-internal and cannot carry user fields — see #1079).
        resume_state = checkpoint_tuple.checkpoint.get("channel_values", {})
        workflow_id = (
            (resume_state.get("workflow_id") if isinstance(resume_state, dict) else None)
            or checkpoint_tuple.metadata.get("workflow_id")
            or "unknown"
        )

        # Load workflow to rebuild graph
        store = WorkflowStore(db)
        workflow = store.get(workflow_id) if workflow_id != "unknown" else None

        if not workflow:
            raise HTTPException(
                status_code=404,
                detail=f"Cannot resume - workflow not found: {workflow_id}",
            )

        # Rebuild graph with checkpointer
        app = _build_workflow_with_checkpointer(workflow, checkpointer)

        # Resume from checkpoint (pass None to continue, or new inputs)
        inputs = request.inputs if request else None
        final_state = await app.ainvoke(inputs, config=config)

        # Get latest checkpoint
        checkpoint_tuple = await checkpointer.aget_tuple(config)

        return ExecutionStatusResponse(
            thread_id=thread_id,
            workflow_id=workflow_id,
            workflow_name=workflow.name if workflow else "Unknown",
            status="completed",
            checkpoint_id=checkpoint_tuple.checkpoint["id"]
            if checkpoint_tuple
            else None,
            current_state=_sanitize_for_json(final_state),
            error=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to resume workflow thread {thread_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads/{thread_id}/status")
async def get_thread_status(
    thread_id: str,
    db: Database = Depends(get_library_database),
) -> ExecutionStatusResponse:
    """
    Get status of a workflow execution thread.

    Retrieves the current state and checkpoint information for a thread.

    Args:
        thread_id: Thread ID

    Returns:
        Current execution status

    Raises:
        404: Thread not found
    """
    try:
        # Get checkpointer
        checkpointer = AsyncDuckDBCheckpointer.from_db_path(db.path)

        # Get checkpoint
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        checkpoint_tuple = await checkpointer.aget_tuple(config)

        if not checkpoint_tuple:
            raise HTTPException(
                status_code=404, detail=f"No checkpoint found for thread: {thread_id}"
            )

        # Extract workflow info. CheckpointMetadata is LangGraph-internal
        # (source/step/parents/run_id) — workflow_id is stored in the graph
        # state's channel_values (#1079). Fall back to metadata for compat
        # with any future LangGraph version that does propagate it.
        current_state = checkpoint_tuple.checkpoint.get("channel_values", {})
        workflow_id = (
            (current_state.get("workflow_id") if isinstance(current_state, dict) else None)
            or checkpoint_tuple.metadata.get("workflow_id")
            or "unknown"
        )

        # Try to get workflow name
        store = WorkflowStore(db)
        workflow = store.get(workflow_id) if workflow_id != "unknown" else None
        workflow_name = workflow.name if workflow else "Unknown"
        has_pending_writes = len(checkpoint_tuple.pending_writes) > 0

        # Check for error in state
        workflow_error = (
            current_state.get("error") if isinstance(current_state, dict) else None
        )

        if has_pending_writes:
            status = "paused"
        elif workflow_error:
            status = "failed"
        else:
            status = "completed"

        return ExecutionStatusResponse(
            thread_id=thread_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            status=status,
            checkpoint_id=checkpoint_tuple.checkpoint["id"],
            current_state=_sanitize_for_json(current_state),
            error=workflow_error,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get status for thread {thread_id}")
        raise HTTPException(status_code=500, detail=str(e))
