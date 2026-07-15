"""
Workflow Execution Core Routes

Execute, stream, resume, and status-check workflows.
"""

import asyncio
import json
import logging
import queue
import threading
from datetime import datetime, timezone
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
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.models import Workflow
from fichero.workflows.activity import get_activity_tracker
from fichero.workflows.checkpointer import AsyncDuckDBCheckpointer
from fichero.workflows.workflow_store import WorkflowStore
from fichero.workflows.runtime import (
    create_compiled_app_with_checkpointer,
    to_workflow_def,
)
from fichero.workflows.builder import build_graph
from fichero.workflows.validation import (
    validate_workflow_connections,
    validate_workflow_preflight,
)

from .schemas import (
    ExecuteAcceptedResponse,
    ExecuteWorkflowRequest,
    ExecutionStatusResponse,
    ResumeWorkflowRequest,
    format_sse,
    workflow_internal_error,
)
from .runner import (
    WorkflowEventHub,
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


def _validate_workflow_for_execution(workflow: Workflow) -> None:
    """Fail fast on malformed workflows before spawning a background run."""
    workflow_def = to_workflow_def(workflow)
    errors = [
        *validate_workflow_connections(workflow_def),
        *validate_workflow_preflight(workflow_def),
    ]

    if not workflow_def.nodes:
        errors.append("Workflow has no nodes")

    if not errors:
        try:
            build_graph(workflow_def, enable_parallel=True)
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        detail = f"Workflow validation failed: {'; '.join(errors)}"
        logger.warning(
            "Workflow validation failed for id=%s name=%r: %s",
            workflow.id,
            workflow.name,
            detail,
        )
        raise HTTPException(
            status_code=400,
            detail=detail,
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
        """Generate SSE events from the workflow's event hub.

        ``state["events"]`` is a :class:`WorkflowEventHub` (#2546). We take
        a PRIVATE subscriber queue via ``.subscribe()`` so multiple watchers
        (the Workflow editor AND the Activity panel, late or concurrent) each
        receive EVERY event instead of competing for a single destructive
        ``.get()``. The hub replays buffered events so a late subscriber
        catches up. The workflow runs on a dedicated worker thread (#1000),
        so the blocking ``.get()`` is offloaded via ``run_in_executor`` to
        keep the API event loop free.
        """
        hub: WorkflowEventHub = state["events"]
        subscriber = hub.subscribe()
        loop = asyncio.get_running_loop()

        try:
            while True:
                try:
                    # Wait for next event with timeout, off the event loop.
                    event = await loop.run_in_executor(
                        None, subscriber.get, True, 60.0
                    )

                    if event is None:
                        # Sentinel value - stream is complete
                        break

                    yield format_sse(event)

                except queue.Empty:
                    # Send keepalive comment to prevent connection timeout
                    yield ": keepalive\n\n"
        finally:
            # Stop feeding this subscriber once the client disconnects.
            hub.unsubscribe(subscriber)

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
    db: Database = Depends(get_library_database_for_write),
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

        _validate_workflow_for_execution(workflow)

        logger.debug(
            "[EXECUTE] workflow=%s id=%s nodes=%s edges=%s",
            workflow.name,
            workflow.id,
            len(workflow.nodes),
            len(workflow.edges),
        )
        for i, node in enumerate(workflow.nodes[:3]):  # Log first 3 nodes
            logger.debug(
                "[EXECUTE] node[%s] tool=%s id=%s",
                i,
                node.get("tool", "?"),
                str(node.get("id", "?"))[:8],
            )
        if not workflow.nodes:
            logger.debug("[EXECUTE] workflow has no nodes; execution would complete instantly")

        # Generate thread ID if not provided or if force_new is True
        if request.force_new or not request.thread_id:
            thread_id = f"thread-{uuid4().hex[:12]}"
        else:
            thread_id = request.thread_id

        # Create the event hub for this workflow. A WorkflowEventHub (#2546)
        # fans events out to every SSE subscriber (editor + Activity, late or
        # concurrent) instead of a single-consumer queue.Queue that only the
        # first subscriber could drain. The producer side is thread-safe: the
        # workflow runs on a dedicated worker thread (#1000) and calls
        # ``hub.put(...)``; each subscriber drains its own queue via
        # run_in_executor.
        event_hub = WorkflowEventHub()

        # Register workflow state
        _set_workflow_state(
            thread_id,
            {
                "workflow_id": request.workflow_id,
                "workflow_name": workflow.name,
                "status": "accepted",
                "events": event_hub,
                "error": None,
                "final_state": None,
            },
        )

        await get_activity_tracker(str(db.path)).store.save_workflow_run(
            thread_id=thread_id,
            workflow_id=request.workflow_id,
            workflow_name=workflow.name,
            status="accepted",
            workflow_snapshot={
                "nodes": workflow.nodes,
                "edges": workflow.edges,
                "inputs": request.inputs,
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

        # Build stream URL. The live SSE handler is `stream_workflow_events`,
        # registered on THIS router (`@router.get("/stream/{thread_id}")`), which
        # is mounted at `/api/workflow-execution` (see main.py). The previous
        # `/api/workflows/stream/...` path had no handler — the `workflows`
        # router exposes no `/stream` route — so the advertised URL 404'd. The
        # SwiftUI client hardcoded the correct path; this makes the advertised
        # `stream_url` honest so any consumer can use it directly (#2546).
        base_url = str(http_request.base_url).rstrip("/")
        stream_url = f"{base_url}/api/workflow-execution/stream/{thread_id}"

        logger.debug("[EXECUTE] started background execution stream_url=%s", stream_url)

        return ExecuteAcceptedResponse(
            thread_id=thread_id,
            workflow_id=request.workflow_id,
            workflow_name=workflow.name,
            status="accepted",
            stream_url=stream_url,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to start workflow {request.workflow_id}")
        raise workflow_internal_error("Failed to start workflow")


def _resume_argument(request: "ResumeWorkflowRequest | None") -> Any:
    """Pick the LangGraph resume argument for a paused run (#2529).

    - A human-in-the-loop answer → ``Command(resume=answer)`` so the value is
      delivered back to the ``interrupt()`` call (a plain dict would not reach
      it).
    - Otherwise continue from the checkpoint with the optional new inputs (or
      ``None`` to just resume).
    """
    if request is not None and request.answer is not None:
        from langgraph.types import Command

        return Command(resume=request.answer)
    return request.inputs if request is not None else None


@router.post("/threads/{thread_id}/resume")
async def resume_workflow(
    thread_id: str,
    request: ResumeWorkflowRequest | None = None,
    db: Database = Depends(get_library_database_for_write),
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

        activity_tracker = get_activity_tracker(str(db.path))
        activity_tracker.workflow_resumed(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name=workflow.name if workflow else "Unknown",
        )
        await activity_tracker.store.update_workflow_run(
            thread_id=thread_id,
            status="running",
            completed_at=None,
        )

        # Resume from checkpoint. A run paused on a LangGraph interrupt()
        # (human-in-the-loop, #2529) must be resumed with Command(resume=answer)
        # so the answer reaches the interrupt() call; a normal pause continues
        # with None / new inputs.
        resume_arg = _resume_argument(request)
        resume_started_at = datetime.now(timezone.utc)
        try:
            final_state = await app.ainvoke(resume_arg, config=config)
        except Exception as resume_exc:
            duration_ms = (
                datetime.now(timezone.utc) - resume_started_at
            ).total_seconds() * 1000
            activity_tracker.workflow_failed(
                workflow_id=workflow_id,
                thread_id=thread_id,
                workflow_name=workflow.name,
                error=str(resume_exc),
                duration_ms=duration_ms,
            )
            await activity_tracker.store.update_workflow_run(
                thread_id=thread_id,
                status="failed",
                error=str(resume_exc),
                duration_ms=duration_ms,
                completed_at=datetime.now(timezone.utc),
            )
            raise

        # Get latest checkpoint
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        duration_ms = (datetime.now(timezone.utc) - resume_started_at).total_seconds() * 1000
        activity_tracker.workflow_completed(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name=workflow.name,
            duration_ms=duration_ms,
        )
        await activity_tracker.store.update_workflow_run(
            thread_id=thread_id,
            status="completed",
            duration_ms=duration_ms,
            completed_at=datetime.now(timezone.utc),
        )

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
    except Exception:
        logger.exception(f"Failed to resume workflow thread {thread_id}")
        raise workflow_internal_error("Failed to resume workflow")


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
        try:
            run = await get_activity_tracker(str(db.path)).store.get_workflow_run(
                thread_id
            )
        except Exception as run_status_exc:
            logger.debug(
                "Could not load workflow run status for %s: %s",
                thread_id,
                run_status_exc,
            )
            run = None

        if run and run.status:
            status = run.status
            workflow_error = run.error or workflow_error
            workflow_name = run.workflow_name or workflow_name
            workflow_id = run.workflow_id or workflow_id
        elif has_pending_writes:
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
    except Exception:
        logger.exception(f"Failed to get status for thread {thread_id}")
        raise workflow_internal_error("Failed to get workflow status")
