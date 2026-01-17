"""
Workflow Execution Routes

API endpoints for executing workflows with LangGraph checkpointing.
Enables durable execution, pause/resume, and thread management.
Includes Server-Sent Events (SSE) for real-time progress updates.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from fichero.db import Database
from fichero.api.main import get_library_database
from fichero.models import Workflow
from fichero.workflows.checkpointer import AsyncDuckDBCheckpointer
from fichero.workflows.workflow_store import WorkflowStore
from fichero.workflows.builder import SystemicErrorDetected, SOURCE_TOOLS, PARALLEL_TOOLS
from fichero.workflows.activity import get_activity_tracker

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class ExecuteWorkflowRequest(BaseModel):
    """Request to execute a workflow."""
    workflow_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    thread_id: str | None = None  # Optional - generated if not provided
    checkpoint_ns: str = ""  # Checkpoint namespace for sub-workflows
    interrupt_before: list[str] = Field(default_factory=list)  # Node IDs to pause before
    interrupt_after: list[str] = Field(default_factory=list)  # Node IDs to pause after


class ExecutionStatusResponse(BaseModel):
    """Response with workflow execution status."""
    thread_id: str
    workflow_id: str
    workflow_name: str
    status: str  # "running", "paused", "completed", "failed"
    checkpoint_id: str | None = None
    current_state: dict[str, Any] | None = None
    error: str | None = None


class ResumeWorkflowRequest(BaseModel):
    """Request to resume a paused workflow."""
    inputs: dict[str, Any] | None = None  # Optional new inputs


class CancelWorkflowRequest(BaseModel):
    """Request to cancel a running workflow."""
    pass  # No parameters needed


class ThreadListResponse(BaseModel):
    """Response with list of execution threads."""
    threads: list[ExecutionStatusResponse]


class ExecuteAcceptedResponse(BaseModel):
    """Response when workflow execution has been accepted (202)."""
    thread_id: str
    workflow_id: str
    workflow_name: str
    status: str = "accepted"  # Will transition to "running"
    stream_url: str  # URL to subscribe for SSE events


# =============================================================================
# Background Task Management
# =============================================================================

# Store for tracking background workflow executions
# Key: thread_id, Value: dict with workflow state and asyncio.Queue for events
_running_workflows: dict[str, dict[str, Any]] = {}


def _get_workflow_state(thread_id: str) -> dict[str, Any] | None:
    """Get the current state of a running workflow."""
    return _running_workflows.get(thread_id)


def _set_workflow_state(thread_id: str, state: dict[str, Any]) -> None:
    """Update the state of a running workflow."""
    _running_workflows[thread_id] = state


def _remove_workflow_state(thread_id: str) -> None:
    """Remove a workflow from tracking (after completion)."""
    _running_workflows.pop(thread_id, None)


class SSEEvent(BaseModel):
    """Server-Sent Event for workflow execution updates."""
    # Events: "start", "node_begin", "node_end", "complete", "error", "pause"
    #         "parallel_start", "file_start", "file_complete", "file_error", "parallel_complete"
    event: str
    thread_id: str
    workflow_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    # Parallel execution fields
    node_id: str | None = None
    file_path: str | None = None
    file_index: int | None = None
    file_total: int | None = None
    progress: float | None = None  # 0.0 to 1.0


# =============================================================================
# SSE Streaming Support
# =============================================================================

def format_sse(event: SSEEvent) -> str:
    """Format an SSE event for streaming."""
    data = event.model_dump_json()
    formatted = f"event: {event.event}\ndata: {data}\n\n"
    # Debug: log every SSE event being sent
    print(f"[SSE-YIELD] {event.event}: {str(event.data)[:80]}...")
    return formatted


# =============================================================================
# Background Execution
# =============================================================================

async def _run_workflow_in_background(
    thread_id: str,
    workflow: Workflow,
    request: ExecuteWorkflowRequest,
    db: Database,
) -> None:
    """
    Run a workflow in the background, publishing events to a queue.

    This function is spawned as a background task when the user calls /execute.
    Events are stored in _running_workflows[thread_id]["events"] queue.
    """
    # Get the queue for this thread
    state = _get_workflow_state(thread_id)
    if not state:
        logger.error(f"No workflow state found for thread {thread_id}")
        return

    event_queue: asyncio.Queue = state["events"]
    workflow_id = request.workflow_id

    # Activity tracking
    activity_tracker = get_activity_tracker(str(db.path))
    start_time = datetime.utcnow()
    node_start_times: dict[str, datetime] = {}

    try:
        # Mark as running
        state["status"] = "running"

        # Log activity: workflow started
        activity_tracker.workflow_started(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name=workflow.name,
            input_count=len(request.inputs),
        )

        # Send start event
        await event_queue.put(SSEEvent(
            event="start",
            thread_id=thread_id,
            workflow_id=workflow_id,
            data={"workflow_name": workflow.name, "inputs": request.inputs}
        ))

        # Get checkpointer
        checkpointer = AsyncDuckDBCheckpointer.from_db_path(db.path)

        # Build workflow using the parallel-aware builder
        from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef
        from fichero.workflows.builder import build_graph

        # Convert Workflow model to WorkflowDef
        workflow_def = WorkflowDef(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description or "",
            provider=workflow.provider or "",
            model=workflow.model or "",
            nodes=[
                NodeDef(
                    id=n["id"],
                    tool=n["tool"],
                    label=n.get("label", ""),
                    inputs=n.get("inputs", {}),
                    config=n.get("config", {}),
                    provider_name=n.get("provider_name", ""),
                    model_name=n.get("model_name", ""),
                )
                for n in workflow.nodes
            ],
            edges=[
                EdgeDef(
                    source=e.get("source") or e.get("source_node_id", ""),
                    target=e.get("target") or e.get("target_node_id", ""),
                    source_port=e.get("source_port", "output"),
                    target_port=e.get("target_port", "input"),
                )
                for e in workflow.edges
            ],
        )

        # Create event callback for parallel processing events
        async def emit_parallel_event(event_type: str, data: dict) -> None:
            """Callback to emit SSE events from parallel node processing."""
            await event_queue.put(SSEEvent(
                event=event_type,
                thread_id=thread_id,
                workflow_id=workflow_id,
                node_id=data.get("node_id", ""),
                file_path=data.get("file_path"),
                file_index=data.get("file_index"),
                file_total=data.get("file_total"),
                progress=data.get("progress"),
                data={"error": data.get("error")} if data.get("error") else {},
            ))

        # Build graph with parallel execution support and event callback
        app = build_graph(workflow_def, enable_parallel=True, event_callback=emit_parallel_event)

        # Execute with streaming
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": request.checkpoint_ns,
            }
        }

        # Build initial state with library_path
        initial_state = {
            **request.inputs,
            "library_path": str(db.path.parent) if hasattr(db, 'path') else "",
        }

        # Identify exit nodes (nodes with no outgoing edges)
        exit_node_ids = set()
        all_source_nodes = {e.get("source") or e.get("source_node_id", "") for e in workflow.edges}
        for node in workflow.nodes:
            node_id = node.get("id", "")
            if node_id and node_id not in all_source_nodes:
                # This node has no outgoing edges - it's an exit node
                # Account for parallel processing which adds _aggregate suffix
                exit_node_ids.add(node_id)
                exit_node_ids.add(f"{node_id}_aggregate")

        print(f"[EXECUTE] Exit nodes for completion detection: {exit_node_ids}")
        completed_exit_nodes = set()

        # Stream execution events
        async for event in app.astream_events(
            initial_state,
            config=config,
            version="v2",
        ):
            event_kind = event.get("event", "")

            if event_kind == "on_chain_start" and event.get("name"):
                node_name = event.get("name", "")
                if node_name not in ("__start__", "LangGraph"):
                    node_start_times[node_name] = datetime.utcnow()

                    # Log activity: node started
                    activity_tracker.node_started(
                        workflow_id=workflow_id,
                        thread_id=thread_id,
                        node_id=node_name,
                        node_name=node_name,
                    )

                    await event_queue.put(SSEEvent(
                        event="node_begin",
                        thread_id=thread_id,
                        workflow_id=workflow_id,
                        node_id=node_name,
                        data={"node": node_name}
                    ))

            elif event_kind == "on_chain_end" and event.get("name"):
                node_name = event.get("name", "")
                output = event.get("data", {}).get("output", {})

                if node_name not in ("__start__", "LangGraph"):
                    # Calculate node duration
                    node_start = node_start_times.get(node_name, datetime.utcnow())
                    node_duration_ms = (datetime.utcnow() - node_start).total_seconds() * 1000

                    # Check for parallel processing completion
                    if isinstance(output, dict) and "parallel_results" in output:
                        results = output.get("parallel_results", {})
                        for node_id, file_results in results.items():
                            success_count = sum(1 for r in file_results if r.get("success"))
                            error_count = len(file_results) - success_count
                            await event_queue.put(SSEEvent(
                                event="parallel_complete",
                                thread_id=thread_id,
                                workflow_id=workflow_id,
                                node_id=node_id,
                                data={
                                    "success_count": success_count,
                                    "error_count": error_count,
                                    "total": len(file_results),
                                }
                            ))

                    # Log activity: node completed
                    activity_tracker.node_completed(
                        workflow_id=workflow_id,
                        thread_id=thread_id,
                        node_id=node_name,
                        node_name=node_name,
                        duration_ms=node_duration_ms,
                    )

                    await event_queue.put(SSEEvent(
                        event="node_end",
                        thread_id=thread_id,
                        workflow_id=workflow_id,
                        node_id=node_name,
                        data={"node": node_name, "duration_ms": node_duration_ms}
                    ))

                    # Track exit node completion
                    if node_name in exit_node_ids:
                        completed_exit_nodes.add(node_name)
                        print(f"[EXECUTE] Exit node completed: {node_name}, completed: {completed_exit_nodes}/{exit_node_ids}")

                        # Check if all exit nodes are done
                        if exit_node_ids and completed_exit_nodes >= exit_node_ids:
                            print(f"[EXECUTE] All exit nodes completed, breaking from astream_events loop")
                            break

        # Get final state
        print(f"[COMPLETE] Getting final state from checkpointer...")
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        final_state = checkpoint_tuple.checkpoint.get("channel_values") if checkpoint_tuple else {}
        print(f"[COMPLETE] Got final state, keys: {list(final_state.keys()) if final_state else 'none'}")

        # Store final state
        state["status"] = "completed"
        state["final_state"] = final_state

        # Calculate total duration
        total_duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Log activity: workflow completed
        activity_tracker.workflow_completed(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name=workflow.name,
            duration_ms=total_duration_ms,
        )

        # Send complete event
        await event_queue.put(SSEEvent(
            event="complete",
            thread_id=thread_id,
            workflow_id=workflow_id,
            data={
                "checkpoint_id": checkpoint_tuple.checkpoint["id"] if checkpoint_tuple else None,
                "final_state": final_state,
                "duration_ms": total_duration_ms,
            }
        ))

    except SystemicErrorDetected as e:
        logger.error(f"Systemic error in background workflow {workflow_id}: {e}")
        state["status"] = "failed"
        state["error"] = str(e)

        # Calculate duration
        total_duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Log activity: workflow failed (systemic error)
        activity_tracker.workflow_failed(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name=workflow.name,
            error=f"Systemic error: {e.error_count}/{e.total_count} consecutive failures",
            duration_ms=total_duration_ms,
        )

        await event_queue.put(SSEEvent(
            event="systemic_error",
            thread_id=thread_id,
            workflow_id=workflow_id,
            data={
                "error": str(e),
                "error_count": e.error_count,
                "total_count": e.total_count,
                "sample_errors": e.errors[:5] if e.errors else [],
            }
        ))

    except Exception as e:
        logger.exception(f"Background workflow error for {workflow_id}")
        state["status"] = "failed"
        state["error"] = str(e)

        # Calculate duration
        total_duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Log activity: workflow failed
        activity_tracker.workflow_failed(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name=workflow.name,
            error=str(e),
            duration_ms=total_duration_ms,
        )

        await event_queue.put(SSEEvent(
            event="error",
            thread_id=thread_id,
            workflow_id=workflow_id,
            data={"error": str(e)}
        ))

    finally:
        # Signal end of stream
        await event_queue.put(None)  # Sentinel to signal stream end


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
            detail=f"Workflow thread not found: {thread_id}. It may have already completed."
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events from the workflow's event queue."""
        event_queue: asyncio.Queue = state["events"]

        while True:
            try:
                # Wait for next event with timeout
                event = await asyncio.wait_for(event_queue.get(), timeout=60.0)

                if event is None:
                    # Sentinel value - stream is complete
                    break

                yield format_sse(event)

            except asyncio.TimeoutError:
                # Send keepalive comment to prevent connection timeout
                yield ": keepalive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
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
                status_code=404,
                detail=f"Workflow not found: {request.workflow_id}"
            )

        # Debug: log workflow data being executed
        print(f"[EXECUTE] Workflow '{workflow.name}' (id={workflow.id})")
        print(f"[EXECUTE]   nodes: {len(workflow.nodes)}, edges: {len(workflow.edges)}")
        for i, node in enumerate(workflow.nodes[:3]):  # Log first 3 nodes
            print(f"[EXECUTE]   node[{i}]: tool={node.get('tool', '?')}, id={node.get('id', '?')[:8]}...")
        if not workflow.nodes:
            print("[EXECUTE]   WARNING: Workflow has no nodes! Execution will complete instantly.")

        # Generate thread ID if not provided
        thread_id = request.thread_id or f"thread-{uuid4().hex[:12]}"

        # Create event queue for this workflow
        event_queue: asyncio.Queue = asyncio.Queue()

        # Register workflow state
        _set_workflow_state(thread_id, {
            "workflow_id": request.workflow_id,
            "workflow_name": workflow.name,
            "status": "accepted",
            "events": event_queue,
            "error": None,
            "final_state": None,
        })

        # Start background execution
        # Note: We use asyncio.create_task instead of background_tasks.add_task
        # because background_tasks runs after the response is sent, but we need
        # the task to start immediately so events can begin flowing
        asyncio.create_task(_run_workflow_in_background(
            thread_id=thread_id,
            workflow=workflow,
            request=request,
            db=db,
        ))

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
                status_code=404,
                detail=f"No checkpoint found for thread: {thread_id}"
            )

        # Extract workflow_id from checkpoint metadata
        # (Note: We should store this in checkpoint metadata in the future)
        # For now, we'll need to pass it or retrieve it another way

        # Get workflow from checkpoint state
        # This is a simplified version - in production, store workflow_id in checkpoint metadata
        workflow_id = checkpoint_tuple.metadata.get("workflow_id", "unknown")

        # Load workflow to rebuild graph
        store = WorkflowStore(db)
        workflow = store.get(workflow_id) if workflow_id != "unknown" else None

        if not workflow:
            # Try to continue without rebuilding - this will work if the graph structure hasn't changed
            raise HTTPException(
                status_code=404,
                detail=f"Cannot resume - workflow not found: {workflow_id}"
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
            checkpoint_id=checkpoint_tuple.checkpoint["id"] if checkpoint_tuple else None,
            current_state=final_state,
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
                status_code=404,
                detail=f"No checkpoint found for thread: {thread_id}"
            )

        # Extract workflow info from metadata
        workflow_id = checkpoint_tuple.metadata.get("workflow_id", "unknown")

        # Try to get workflow name
        store = WorkflowStore(db)
        workflow = store.get(workflow_id) if workflow_id != "unknown" else None
        workflow_name = workflow.name if workflow else "Unknown"

        # Determine status from checkpoint
        current_state = checkpoint_tuple.checkpoint.get("channel_values", {})
        has_pending_writes = len(checkpoint_tuple.pending_writes) > 0

        # Check for error in state
        workflow_error = current_state.get("error") if isinstance(current_state, dict) else None

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
            current_state=current_state,
            error=workflow_error,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get status for thread {thread_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads")
async def list_threads(
    db: Database = Depends(get_library_database),
    limit: int = 100,
) -> ThreadListResponse:
    """
    List all execution threads with checkpoints.

    Returns recent execution threads sorted by checkpoint ID (newest first).

    Args:
        limit: Maximum number of threads to return

    Returns:
        List of threads with their current status
    """
    try:
        # Get checkpointer
        checkpointer = AsyncDuckDBCheckpointer.from_db_path(db.path)

        # Query all checkpoints from database
        # Note: This is a simplified version - in production, add filtering and pagination
        query = """
            SELECT DISTINCT thread_id
            FROM checkpoints
            ORDER BY checkpoint_id DESC
            LIMIT ?
        """
        result = checkpointer.conn.execute(query, [limit])
        thread_ids = [row[0] for row in result.fetchall()]

        # Get status for each thread
        threads = []
        for thread_id in thread_ids:
            try:
                status = await get_thread_status(thread_id, db)
                threads.append(status)
            except HTTPException:
                # Skip threads that can't be retrieved
                continue

        return ThreadListResponse(threads=threads)

    except Exception as e:
        logger.exception("Failed to list threads")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, str]:
    """
    Delete a workflow execution thread and its checkpoints.

    Removes all checkpoint data for the specified thread.

    Args:
        thread_id: Thread ID to delete

    Returns:
        Success message

    Raises:
        404: Thread not found
    """
    try:
        # Get checkpointer
        checkpointer = AsyncDuckDBCheckpointer.from_db_path(db.path)

        # Check if thread exists
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        checkpoint_tuple = await checkpointer.aget_tuple(config)

        if not checkpoint_tuple:
            raise HTTPException(
                status_code=404,
                detail=f"No checkpoint found for thread: {thread_id}"
            )

        # Delete all checkpoints for this thread
        checkpointer.conn.execute(
            "DELETE FROM checkpoints WHERE thread_id = ?",
            [thread_id]
        )

        # Delete all checkpoint writes for this thread
        checkpointer.conn.execute(
            "DELETE FROM checkpoint_writes WHERE thread_id = ?",
            [thread_id]
        )

        logger.info(f"Deleted thread: {thread_id}")
        return {"message": f"Thread deleted: {thread_id}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete thread {thread_id}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Helper Functions
# =============================================================================

def _build_workflow_with_checkpointer(
    workflow: Workflow,
    checkpointer: AsyncDuckDBCheckpointer,
    interrupt_before: list[str] | None = None,
    interrupt_after: list[str] | None = None,
    enable_parallel: bool = True,
):
    """
    Build a LangGraph workflow with checkpointing enabled.

    Uses the parallel-aware build_graph() function for proper fan-out/fan-in
    execution of batch processing nodes.

    Args:
        workflow: Workflow database model
        checkpointer: AsyncDuckDBCheckpointer instance
        interrupt_before: Optional list of node IDs to pause before
        interrupt_after: Optional list of node IDs to pause after
        enable_parallel: Whether to enable parallel file processing (default: True)

    Returns:
        Compiled LangGraph application with checkpointing
    """
    from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef
    from fichero.workflows.builder import build_graph, PARALLEL_TOOLS

    # Convert Workflow model to WorkflowDef
    workflow_def = WorkflowDef(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description or "",
        provider=workflow.provider or "",
        model=workflow.model or "",
        nodes=[
            NodeDef(
                id=n["id"],
                tool=n["tool"],
                label=n.get("label", ""),
                inputs=n.get("inputs", {}),
                config=n.get("config", {}),
                provider_name=n.get("provider_name", ""),
                model_name=n.get("model_name", ""),
            )
            for n in workflow.nodes
        ],
        edges=[
            EdgeDef(
                source=e.get("source") or e.get("source_node_id", ""),
                target=e.get("target") or e.get("target_node_id", ""),
                source_port=e.get("source_port", "output"),
                target_port=e.get("target_port", "input"),
            )
            for e in workflow.edges
        ],
    )

    # Debug: Log workflow structure
    print(f"[BUILD] Workflow '{workflow_def.name}' (id={workflow_def.id})")
    print(f"[BUILD]   nodes: {len(workflow_def.nodes)}, edges: {len(workflow_def.edges)}")
    print(f"[BUILD]   parallel execution: {enable_parallel}")

    # Log nodes
    for node in workflow_def.nodes:
        print(f"[BUILD] Node {node.id[:8]}... tool={node.tool}")
        print(f"[BUILD]   inputs: {node.inputs}")
        print(f"[BUILD]   config: {node.config}")
        print(f"[BUILD]   provider: {node.provider_name or '(workflow default)'}")
        print(f"[BUILD]   model: {node.model_name or '(workflow default)'}")

    # Log edges and detect parallel edges
    print(f"[BUILD] Edges:")
    for edge in workflow_def.edges:
        target_node = workflow_def.get_node(edge.target)
        source_node = workflow_def.get_node(edge.source)
        is_parallel = (
            enable_parallel
            and target_node
            and target_node.tool in PARALLEL_TOOLS
            and source_node
            and source_node.tool in SOURCE_TOOLS
        )
        parallel_marker = " [PARALLEL]" if is_parallel else ""
        print(f"[BUILD]   {edge.source} -> {edge.target}{parallel_marker}")

    # Build graph using parallel-aware builder
    # Note: build_graph returns a compiled graph, but we need to recompile with checkpointer
    # So we use the StateGraph directly but with parallel detection
    from langgraph.graph import StateGraph, START, END
    from fichero.workflows.types import State
    from fichero.workflows.registry import get_tool
    from fichero.workflows.builder import (
        _make_node_function,
        _make_fan_out_function,
        _make_parallel_node_function,
        _make_aggregation_function,
    )
    from fichero.llm import LLMConfig

    # Create state graph
    graph = StateGraph(State)

    # Build LLM config
    llm_config = LLMConfig(provider=workflow_def.provider, model=workflow_def.model)
    workflow_config = {"provider": workflow_def.provider, "model": workflow_def.model}

    # Build edge lookup for auto-wiring
    edges_by_target = {}
    for edge in workflow_def.edges:
        if edge.target not in edges_by_target:
            edges_by_target[edge.target] = []
        edges_by_target[edge.target].append({
            "source": edge.source,
            "source_port": edge.source_port,
            "target_port": edge.target_port,
        })

    # Identify parallel processing edges (source -> batch tool)
    parallel_edges = set()
    if enable_parallel:
        for edge in workflow_def.edges:
            target_node = workflow_def.get_node(edge.target)
            if target_node and target_node.tool in PARALLEL_TOOLS:
                source_node = workflow_def.get_node(edge.source)
                if source_node and source_node.tool in SOURCE_TOOLS:
                    parallel_edges.add((edge.source, edge.target))
                    print(f"[BUILD] Parallel edge detected: {edge.source} -> {edge.target}")

    # Add nodes
    for node_def in workflow_def.nodes:
        tool_fn = get_tool(node_def.tool)
        if tool_fn is None:
            raise ValueError(f"Unknown tool: {node_def.tool}")

        incoming_edges = edges_by_target.get(node_def.id, [])

        # Check if this node receives parallel fan-out
        is_parallel_target = any(
            (e["source"], node_def.id) in parallel_edges
            for e in incoming_edges
        )

        if is_parallel_target:
            # Create single-file processing node for parallel execution
            node_fn = _make_parallel_node_function(
                node_def, tool_fn, llm_config, workflow_config
            )
            # Add aggregation node
            agg_fn = _make_aggregation_function(node_def.id)
            graph.add_node(f"{node_def.id}_process", node_fn)
            graph.add_node(f"{node_def.id}_aggregate", agg_fn)
            print(f"[BUILD] Added parallel nodes: {node_def.id}_process, {node_def.id}_aggregate")
        else:
            # Standard node
            node_fn = _make_node_function(
                node_def, tool_fn, llm_config, workflow_config, incoming_edges
            )
            graph.add_node(node_def.id, node_fn)

    # Add edges
    for edge in workflow_def.edges:
        if (edge.source, edge.target) in parallel_edges:
            # Create fan-out edge using Send API
            fan_out_fn = _make_fan_out_function(edge.source, edge.target)
            graph.add_conditional_edges(
                edge.source,
                fan_out_fn,
                [f"{edge.target}_process"]
            )
            # Connect process to aggregate
            graph.add_edge(f"{edge.target}_process", f"{edge.target}_aggregate")
            print(f"[BUILD] Added parallel edges: {edge.source} -> fan-out -> {edge.target}_process -> {edge.target}_aggregate")
        else:
            # Check if source was parallelized - connect from aggregate
            source_is_parallel = any(
                (e.source, e.target) in parallel_edges and e.target == edge.source
                for e in workflow_def.edges
            )
            if source_is_parallel:
                graph.add_edge(f"{edge.source}_aggregate", edge.target)
            else:
                graph.add_edge(edge.source, edge.target)

    # Connect START to entry nodes
    entry_nodes = workflow_def.get_entry_nodes()
    if not entry_nodes:
        raise ValueError("Workflow has no entry nodes")

    for entry in entry_nodes:
        print(f"[BUILD] START -> {entry}")
        graph.add_edge(START, entry)

    # Connect exit nodes to END
    exit_nodes = workflow_def.get_exit_nodes()
    for exit_node in exit_nodes:
        # Check if this exit node was parallelized
        is_parallel = any(
            (e.source, e.target) in parallel_edges and e.target == exit_node
            for e in workflow_def.edges
        )
        if is_parallel:
            print(f"[BUILD] {exit_node}_aggregate -> END")
            graph.add_edge(f"{exit_node}_aggregate", END)
        else:
            print(f"[BUILD] {exit_node} -> END")
            graph.add_edge(exit_node, END)

    # Compile with checkpointer
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
    )
