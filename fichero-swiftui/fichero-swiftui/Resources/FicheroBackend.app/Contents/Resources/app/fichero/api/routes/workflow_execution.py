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
    force_new: bool = False  # If True, ignore provided thread_id and create a fresh execution
    skip_cache: bool = False  # If True, bypass node result cache (still writes new results)


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


class CheckpointSnapshot(BaseModel):
    """A single checkpoint in the execution history."""
    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    step: int
    timestamp: str | None = None
    node_name: str | None = None  # Node that produced this checkpoint
    state_values: dict[str, Any] = Field(default_factory=dict)  # State at this step
    writes: dict[str, Any] = Field(default_factory=dict)  # What was written
    next_nodes: list[str] = Field(default_factory=list)  # Next nodes to execute


class CheckpointHistoryResponse(BaseModel):
    """Response with full checkpoint history for a thread."""
    thread_id: str
    workflow_id: str
    workflow_name: str
    total_steps: int
    checkpoints: list[CheckpointSnapshot]


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
    execution_log_lines: list[str] = []  # Collect execution logs
    progress_timeline: dict[str, Any] = {"nodes": {}, "steps": []}  # Capture progress for historical viewing

    async def log_execution(message: str) -> None:
        """Log a message to both console and execution log, and stream via SSE."""
        timestamp = datetime.utcnow().strftime("%H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] {message}"
        execution_log_lines.append(log_line)
        print(log_line)
        # Stream log line to frontend
        await event_queue.put(SSEEvent(
            event="log",
            thread_id=thread_id,
            workflow_id=workflow_id,
            data={"line": log_line}
        ))

    try:
        # Mark as running
        state["status"] = "running"

        await log_execution(f"Starting workflow '{workflow.name}'")

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

        # Resolve default provider/model if not set on workflow
        if not workflow_def.provider or not workflow_def.model:
            try:
                from fichero.app_db import get_app_db
                app_db = get_app_db()
                default = app_db.get_default_model()
                if default:
                    if not workflow_def.provider:
                        workflow_def.provider = default[0]
                    if not workflow_def.model:
                        workflow_def.model = default[1]
                    logger.info(f"Using default provider: {workflow_def.provider}/{workflow_def.model}")
            except Exception as e:
                logger.warning(f"Could not load default provider: {e}")

        # Generate and save Python code
        await log_execution(f"Generating Python code for workflow")
        python_code = _generate_workflow_python_code(workflow)

        # Create workflow snapshot for historical visualization (even if workflow is deleted)
        await log_execution(f"Creating workflow snapshot")
        workflow_snapshot = {
            "nodes": [
                {"id": n["id"], "tool": n["tool"], "label": n.get("label", "")}
                for n in workflow.nodes
            ],
            "edges": [
                {"source": e.get("source") or e.get("source_node_id", ""),
                 "target": e.get("target") or e.get("target_node_id", "")}
                for e in workflow.edges
            ]
        }

        # Build node name mapping (UUID → readable name)
        await log_execution(f"Building node name mapping")
        node_name_map = {}
        name_counts = {}
        for node in workflow.nodes:
            node_id = node["id"]
            base_name = node.get("label") or node["tool"].replace("_", " ").title()

            # Handle duplicate names with numbering
            if base_name in name_counts:
                name_counts[base_name] += 1
                unique_name = f"{base_name} {name_counts[base_name]}"
            else:
                name_counts[base_name] = 1
                unique_name = base_name

            node_name_map[node_id] = unique_name

        # Generate Mermaid diagram for historical viewing
        await log_execution(f"Generating workflow diagram")
        try:
            app_preview = build_graph(workflow_def, enable_parallel=True, checkpointer=None)
            diagram_mermaid = app_preview.get_graph().draw_mermaid()
        except Exception as e:
            logger.warning(f"Could not generate diagram: {e}")
            diagram_mermaid = None

        # Save workflow run with all metadata
        await activity_tracker.store.save_workflow_run(
            thread_id=thread_id,
            workflow_id=workflow_id,
            workflow_name=workflow.name,
            python_code=python_code,
            workflow_snapshot=workflow_snapshot,
            node_name_map=node_name_map,
            diagram_mermaid=diagram_mermaid,
            started_at=start_time,
        )
        await log_execution(f"Saved workflow run record with snapshot")

        # Create event callback for parallel processing events
        async def emit_parallel_event(event_type: str, data: dict) -> None:
            """Callback to emit SSE events from parallel node processing."""
            # Emit SSE event (existing behavior)
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

            # Capture file-level timeline for historical viewing and log to console
            if event_type == "file_start":
                file_index = data.get("file_index", 0)
                file_total = data.get("file_total", 0)
                file_path = data.get("file_path", "")
                # Extract just the filename for cleaner logging
                file_name = file_path.split("/")[-1] if file_path else "unknown"
                await log_execution(f"  Processing file {file_index}/{file_total}: {file_name}")

                progress_timeline["steps"].append({
                    "type": "file",
                    "node_id": data.get("node_id", ""),
                    "file_path": file_path,
                    "file_index": file_index,
                    "file_total": file_total,
                    "started_at": datetime.utcnow().isoformat(),
                    "status": "running"
                })
            elif event_type == "file_complete":
                file_index = data.get("file_index", 0)
                file_total = data.get("file_total", 0)
                file_path = data.get("file_path", "")
                file_name = file_path.split("/")[-1] if file_path else "unknown"

                # Find and update the matching file entry
                duration_ms = 0
                for entry in reversed(progress_timeline["steps"]):
                    if (entry.get("type") == "file" and
                        entry.get("file_path") == file_path and
                        entry.get("status") == "running"):
                        entry["completed_at"] = datetime.utcnow().isoformat()
                        entry["status"] = "success"
                        # Calculate duration
                        start = datetime.fromisoformat(entry["started_at"])
                        duration_ms = (datetime.utcnow() - start).total_seconds() * 1000
                        entry["duration_ms"] = duration_ms
                        break

                await log_execution(f"  File {file_index}/{file_total} completed: {file_name} ({duration_ms:.0f}ms)")
            elif event_type == "file_error":
                file_path = data.get("file_path", "")
                file_name = file_path.split("/")[-1] if file_path else "unknown"
                error_msg = data.get("error", "Unknown error")
                await log_execution(f"  ERROR processing {file_name}: {error_msg}")

                # Find and update the matching file entry
                for entry in reversed(progress_timeline["steps"]):
                    if (entry.get("type") == "file" and
                        entry.get("file_path") == file_path and
                        entry.get("status") == "running"):
                        entry["completed_at"] = datetime.utcnow().isoformat()
                        entry["status"] = "error"
                        entry["error"] = error_msg
                        break
            elif event_type == "parallel_complete":
                # Save aggregate stats for the node
                progress_timeline["nodes"][data.get("node_id", "")] = {
                    "total_files": data.get("total", 0),
                    "success_count": data.get("success_count", 0),
                    "error_count": data.get("error_count", 0)
                }

        # Build graph with parallel execution support, event callback, and checkpointer
        app = build_graph(
            workflow_def,
            enable_parallel=True,
            event_callback=emit_parallel_event,
            checkpointer=checkpointer,
            skip_cache=request.skip_cache,
        )

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

        # Identify exit nodes (nodes with no outgoing edges) using raw IDs
        exit_node_ids = set()
        all_source_nodes = {e.get("source") or e.get("source_node_id", "") for e in workflow.edges}
        for node in workflow.nodes:
            node_id = node.get("id", "")
            if node_id and node_id not in all_source_nodes:
                exit_node_ids.add(node_id)

        def _normalize_node_name(name: str) -> str:
            """Strip LangGraph internal suffixes to get the original node ID."""
            if name.endswith("_aggregate"):
                return name[: -len("_aggregate")]
            if name.endswith("_process"):
                return name[: -len("_process")]
            return name

        logger.debug(f"Exit nodes for completion: {exit_node_ids}")
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
                    original_id = _normalize_node_name(node_name)

                    # Skip node_begin for _aggregate (internal — the node already started with _process)
                    if node_name.endswith("_aggregate"):
                        continue

                    await log_execution(f"Node '{original_id}' started")

                    # Log activity: node started
                    activity_tracker.node_started(
                        workflow_id=workflow_id,
                        thread_id=thread_id,
                        node_id=original_id,
                        node_name=original_id,
                    )

                    # Capture node start to progress timeline
                    progress_timeline["steps"].append({
                        "node_id": original_id,
                        "started_at": datetime.utcnow().isoformat(),
                        "status": "running"
                    })

                    await event_queue.put(SSEEvent(
                        event="node_begin",
                        thread_id=thread_id,
                        workflow_id=workflow_id,
                        node_id=original_id,
                        data={"node": original_id}
                    ))

            elif event_kind == "on_chain_end" and event.get("name"):
                node_name = event.get("name", "")
                output = event.get("data", {}).get("output", {})

                if node_name not in ("__start__", "LangGraph"):
                    original_id = _normalize_node_name(node_name)

                    # Skip node_end for _process (node isn't done until _aggregate finishes)
                    if node_name.endswith("_process"):
                        continue

                    # Calculate node duration (use _process start time if this is _aggregate)
                    process_name = f"{original_id}_process" if node_name.endswith("_aggregate") else node_name
                    node_start = node_start_times.get(process_name, node_start_times.get(node_name, datetime.utcnow()))
                    node_duration_ms = (datetime.utcnow() - node_start).total_seconds() * 1000

                    # Build activity metadata from output
                    activity_metadata = {}

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
                            # Add to activity metadata
                            activity_metadata["success_count"] = success_count
                            activity_metadata["error_count"] = error_count
                            activity_metadata["total_files"] = len(file_results)

                    # Extract useful metadata from output
                    if isinstance(output, dict):
                        # Files processed
                        if "files" in output:
                            files = output["files"]
                            if isinstance(files, list):
                                activity_metadata["files_processed"] = len(files)

                        # Artifacts created
                        if "artifacts" in output:
                            artifacts = output["artifacts"]
                            if isinstance(artifacts, list):
                                activity_metadata["artifacts_created"] = len(artifacts)

                        # Text/results count
                        if "results" in output:
                            results = output["results"]
                            if isinstance(results, list):
                                activity_metadata["results_count"] = len(results)

                        # Output files
                        if "output_files" in output:
                            output_files = output["output_files"]
                            if isinstance(output_files, list):
                                activity_metadata["output_files"] = len(output_files)

                        # Error from output
                        if "error" in output and output["error"]:
                            activity_metadata["error"] = str(output["error"])[:200]

                    await log_execution(f"Node '{original_id}' completed in {node_duration_ms:.0f}ms")

                    # Log activity: node completed
                    activity_tracker.node_completed(
                        workflow_id=workflow_id,
                        thread_id=thread_id,
                        node_id=original_id,
                        node_name=original_id,
                        duration_ms=node_duration_ms,
                        **activity_metadata,
                    )

                    # Update progress timeline with node completion
                    for entry in reversed(progress_timeline["steps"]):
                        if (entry.get("node_id") == original_id and
                            entry.get("status") == "running" and
                            entry.get("type") is None):  # Only update node steps, not file steps
                            entry["completed_at"] = datetime.utcnow().isoformat()
                            entry["status"] = "success"
                            entry["duration_ms"] = node_duration_ms
                            # Add metadata
                            if "files_processed" in activity_metadata:
                                entry["files_processed"] = activity_metadata["files_processed"]
                            if "artifacts_created" in activity_metadata:
                                entry["artifacts_created"] = activity_metadata["artifacts_created"]
                            break

                    await event_queue.put(SSEEvent(
                        event="node_end",
                        thread_id=thread_id,
                        workflow_id=workflow_id,
                        node_id=original_id,
                        data={"node": original_id, "duration_ms": node_duration_ms}
                    ))

                    # Track exit node completion (using normalized ID)
                    if original_id in exit_node_ids:
                        completed_exit_nodes.add(original_id)
                        logger.info(f"Exit node completed: {original_id}, {len(completed_exit_nodes)}/{len(exit_node_ids)}")

                        # Check if all exit nodes are done
                        if exit_node_ids and completed_exit_nodes >= exit_node_ids:
                            logger.info("All exit nodes completed, ending stream")
                            break

        # Get final state
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        final_state = checkpoint_tuple.checkpoint.get("channel_values") if checkpoint_tuple else {}

        # Store final state
        state["status"] = "completed"
        state["final_state"] = final_state

        # Calculate total duration
        total_duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Build completion metadata from final state
        completion_metadata = {
            "nodes_completed": len(completed_exit_nodes),
        }

        # Extract stats from final state
        if isinstance(final_state, dict):
            # Count files processed
            if "files" in final_state:
                files = final_state["files"]
                if isinstance(files, list):
                    completion_metadata["total_files"] = len(files)

            # Count artifacts
            if "artifacts" in final_state:
                artifacts = final_state["artifacts"]
                if isinstance(artifacts, list):
                    completion_metadata["total_artifacts"] = len(artifacts)

            # Count results
            if "results" in final_state:
                results = final_state["results"]
                if isinstance(results, list):
                    completion_metadata["total_results"] = len(results)

        # Log activity: workflow completed
        activity_tracker.workflow_completed(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name=workflow.name,
            duration_ms=total_duration_ms,
            **completion_metadata,
        )

        await log_execution(f"Workflow completed successfully in {total_duration_ms:.0f}ms")

        # Save execution log and progress timeline to workflow run
        execution_log = "\n".join(execution_log_lines)
        await activity_tracker.store.update_workflow_run(
            thread_id=thread_id,
            status="completed",
            execution_log=execution_log,
            progress_timeline=progress_timeline,
            duration_ms=total_duration_ms,
            completed_at=datetime.utcnow(),
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

        await log_execution(f"SYSTEMIC ERROR: {e.error_count}/{e.total_count} consecutive failures")
        await log_execution(f"Sample errors: {e.errors[:3] if e.errors else []}")

        # Log activity: workflow failed (systemic error)
        activity_tracker.workflow_failed(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name=workflow.name,
            error=f"Systemic error: {e.error_count}/{e.total_count} consecutive failures",
            duration_ms=total_duration_ms,
        )

        # Save execution log and progress timeline to workflow run
        execution_log = "\n".join(execution_log_lines)
        await activity_tracker.store.update_workflow_run(
            thread_id=thread_id,
            status="failed",
            execution_log=execution_log,
            progress_timeline=progress_timeline,
            duration_ms=total_duration_ms,
            error=f"Systemic error: {e.error_count}/{e.total_count} consecutive failures",
            completed_at=datetime.utcnow(),
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

        await log_execution(f"ERROR: {str(e)}")

        # Log activity: workflow failed
        activity_tracker.workflow_failed(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name=workflow.name,
            error=str(e),
            duration_ms=total_duration_ms,
        )

        # Save execution log and progress timeline to workflow run
        execution_log = "\n".join(execution_log_lines)
        await activity_tracker.store.update_workflow_run(
            thread_id=thread_id,
            status="failed",
            execution_log=execution_log,
            progress_timeline=progress_timeline,
            duration_ms=total_duration_ms,
            error=str(e),
            completed_at=datetime.utcnow(),
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

        # Generate thread ID if not provided or if force_new is True
        if request.force_new or not request.thread_id:
            thread_id = f"thread-{uuid4().hex[:12]}"
        else:
            thread_id = request.thread_id

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


@router.get("/threads/{thread_id}/history")
async def get_thread_history(
    thread_id: str,
    db: Database = Depends(get_library_database),
    limit: int = 100,
) -> CheckpointHistoryResponse:
    """
    Get the full checkpoint history for a workflow execution thread.

    Returns all checkpoints (state snapshots) in chronological order,
    showing the state at each step of execution. This enables:
    - Debugging workflow execution step-by-step
    - Understanding what each node produced
    - Time-travel debugging (viewing state at any point)

    Args:
        thread_id: Thread ID
        limit: Maximum number of checkpoints to return (default 100)

    Returns:
        Full checkpoint history with state at each step

    Raises:
        404: Thread not found
    """
    try:
        # Get checkpointer
        checkpointer = AsyncDuckDBCheckpointer.from_db_path(db.path)

        # Check if thread exists
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        latest_tuple = await checkpointer.aget_tuple(config)

        if not latest_tuple:
            raise HTTPException(
                status_code=404,
                detail=f"No checkpoint found for thread: {thread_id}"
            )

        # Get workflow info
        workflow_id = latest_tuple.metadata.get("workflow_id", "unknown")
        store = WorkflowStore(db)
        workflow = store.get(workflow_id) if workflow_id != "unknown" else None
        workflow_name = workflow.name if workflow else "Unknown"

        # Try to get saved node name mapping from workflow run first
        activity_tracker = get_activity_tracker(str(db.path))
        run = await activity_tracker.store.get_workflow_run(thread_id)
        node_names: dict[str, str] = {}

        if run and run.get("node_name_map"):
            # Use saved mapping (works even if workflow was deleted)
            node_names = run["node_name_map"]
            logger.info(f"Using saved node name mapping for thread {thread_id}")
        elif workflow:
            # Fallback: build from workflow definition
            logger.info(f"Building node name mapping from workflow definition for thread {thread_id}")
            name_counts: dict[str, int] = {}
            for node in workflow.nodes:
                node_id = node.get("id", "")
                # Use label if available, otherwise capitalize tool name
                base_name = node.get("label") or node.get("tool", "unknown").replace("_", " ").title()

                # Ensure uniqueness
                if base_name in name_counts:
                    name_counts[base_name] += 1
                    unique_name = f"{base_name} {name_counts[base_name]}"
                else:
                    name_counts[base_name] = 1
                    unique_name = base_name

                node_names[node_id] = unique_name
        else:
            # No mapping available - UUIDs will be shown
            logger.warning(f"No node name mapping available for thread {thread_id}")

        def _translate_node_name(raw_name: str | None) -> str | None:
            """Translate a raw node ID/name to human-readable name."""
            if not raw_name:
                return None
            # Strip LangGraph suffixes (_process, _aggregate)
            clean_name = raw_name
            if clean_name.endswith("_aggregate"):
                clean_name = clean_name[: -len("_aggregate")]
            elif clean_name.endswith("_process"):
                clean_name = clean_name[: -len("_process")]
            # Look up in mapping
            return node_names.get(clean_name, raw_name)

        # Get all checkpoints for this thread using alist
        checkpoints: list[CheckpointSnapshot] = []
        step = 0

        async for checkpoint_tuple in checkpointer.alist(config, limit=limit):
            checkpoint = checkpoint_tuple.checkpoint
            metadata = checkpoint_tuple.metadata

            # Extract useful info from checkpoint
            channel_values = checkpoint.get("channel_values", {})

            # Get writes from metadata (what was written at this step)
            writes = metadata.get("writes", {})

            # Get next nodes from checkpoint (nodes pending execution)
            next_nodes = []
            if checkpoint_tuple.pending_writes:
                next_nodes = [w[1] for w in checkpoint_tuple.pending_writes if len(w) > 1]

            # Extract node name from various sources
            source = metadata.get("source", "")
            raw_node_name = None

            # Try writes first (the node that wrote data)
            if writes:
                # Filter out internal keys like '__pregel_tasks', 'parallel_results'
                real_node_keys = [k for k in writes.keys()
                                  if not k.startswith("__") and k not in ("parallel_results",)]
                if real_node_keys:
                    raw_node_name = real_node_keys[0]

            # Try current_node from channel_values
            if not raw_node_name and channel_values.get("current_node"):
                raw_node_name = channel_values["current_node"]

            # Try completed_nodes (last completed)
            if not raw_node_name:
                completed = channel_values.get("completed_nodes", [])
                if completed:
                    raw_node_name = completed[-1] if isinstance(completed, list) else str(completed)

            # Try metadata source (format: "loop:node_name")
            if not raw_node_name and source and ":" in source:
                parts = source.split(":")
                if len(parts) > 1 and parts[1] not in ("start", "__start__", "end", "__end__"):
                    raw_node_name = parts[1]

            # Translate raw node name to human-readable name
            node_name = _translate_node_name(raw_node_name)

            # For parallel_results, show the nodes that contributed (with translation)
            if not node_name and "parallel_results" in writes:
                parallel_data = writes.get("parallel_results", {})
                if isinstance(parallel_data, dict) and parallel_data:
                    contributing_nodes = list(parallel_data.keys())
                    if contributing_nodes:
                        # Translate each contributing node name
                        translated = [_translate_node_name(n) or n for n in contributing_nodes[:3]]
                        node_name = f"Parallel: {', '.join(translated)}"
                        if len(contributing_nodes) > 3:
                            node_name += f" +{len(contributing_nodes) - 3}"

            # Try to get timestamp from metadata
            timestamp = metadata.get("created_at") or metadata.get("timestamp")

            snapshots = CheckpointSnapshot(
                checkpoint_id=checkpoint.get("id", ""),
                parent_checkpoint_id=checkpoint_tuple.parent_config["configurable"]["checkpoint_id"]
                    if checkpoint_tuple.parent_config else None,
                step=metadata.get("step", step),
                timestamp=timestamp,
                node_name=node_name,
                state_values=_sanitize_state_for_json(channel_values),
                writes=_sanitize_state_for_json(writes),
                next_nodes=next_nodes,
            )
            checkpoints.append(snapshots)
            step += 1

        # Reverse to get chronological order (oldest first)
        checkpoints.reverse()

        # Update step numbers to be chronological
        for i, cp in enumerate(checkpoints):
            cp.step = i

        return CheckpointHistoryResponse(
            thread_id=thread_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            total_steps=len(checkpoints),
            checkpoints=checkpoints,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get history for thread {thread_id}")
        raise HTTPException(status_code=500, detail=str(e))


def _sanitize_state_for_json(state: Any) -> dict[str, Any]:
    """
    Sanitize state values for JSON serialization.

    Removes non-serializable objects and converts complex types to strings.
    """
    if not isinstance(state, dict):
        return {"value": str(state) if state else None}

    result = {}
    for key, value in state.items():
        try:
            # Try to serialize - if it works, keep it
            json.dumps(value)
            result[key] = value
        except (TypeError, ValueError):
            # If not serializable, convert to string representation
            if hasattr(value, "__dict__"):
                result[key] = str(value)
            elif isinstance(value, (list, tuple)):
                result[key] = [str(v) for v in value]
            else:
                result[key] = str(value)
    return result


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
    from fichero.workflows.builder import build_graph, PARALLEL_TOOLS, SOURCE_TOOLS

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

    # Resolve default provider/model if not set on workflow
    if not workflow_def.provider or not workflow_def.model:
        try:
            from fichero.app_db import get_app_db
            app_db = get_app_db()
            default = app_db.get_default_model()
            if default:
                if not workflow_def.provider:
                    workflow_def.provider = default[0]
                if not workflow_def.model:
                    workflow_def.model = default[1]
                logger.info(f"Using default provider: {workflow_def.provider}/{workflow_def.model}")
        except Exception as e:
            logger.warning(f"Could not load default provider: {e}")

    logger.debug(f"Building workflow '{workflow_def.name}': {len(workflow_def.nodes)} nodes, {len(workflow_def.edges)} edges")

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
    # Group parallel edges by source node (one conditional edge per source)
    parallel_by_source: dict[str, list[str]] = {}
    for edge in workflow_def.edges:
        if (edge.source, edge.target) in parallel_edges:
            if edge.source not in parallel_by_source:
                parallel_by_source[edge.source] = []
            parallel_by_source[edge.source].append(edge.target)

    # Add fan-out conditional edges (one per source node)
    for source_id, target_ids in parallel_by_source.items():
        fan_out_fn = _make_fan_out_function(source_id, target_ids)
        graph.add_conditional_edges(
            source_id,
            fan_out_fn,
            [f"{t}_process" for t in target_ids]
        )
        for target_id in target_ids:
            graph.add_edge(f"{target_id}_process", f"{target_id}_aggregate")

    # Add non-parallel edges
    for edge in workflow_def.edges:
        if (edge.source, edge.target) in parallel_edges:
            continue  # Already handled above
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


# =============================================================================
# Visualization & Code Export Endpoints
# =============================================================================

class WorkflowVisualizationResponse(BaseModel):
    """Response with workflow visualization data."""
    workflow_id: str
    workflow_name: str
    mermaid_code: str  # Mermaid diagram code
    node_count: int
    edge_count: int


class WorkflowCodeExportResponse(BaseModel):
    """Response with exported Python code for the workflow."""
    workflow_id: str
    workflow_name: str
    python_code: str


@router.get("/workflows/{workflow_id}/visualization")
async def get_workflow_visualization(
    workflow_id: str,
    db: Database = Depends(get_library_database),
    xray: bool = False,
) -> WorkflowVisualizationResponse:
    """
    Get visualization (Mermaid diagram) for a workflow.

    Returns Mermaid code that can be rendered as a graph diagram.
    Use https://mermaid.live or any Mermaid renderer to visualize.

    Args:
        workflow_id: Workflow ID
        xray: If True, show internal subgraph details

    Returns:
        Mermaid diagram code and workflow metadata
    """
    try:
        # Load workflow
        store = WorkflowStore(db)
        workflow = store.get(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow not found: {workflow_id}"
            )

        # Build graph (without checkpointer for visualization)
        from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef
        from fichero.workflows.builder import build_graph

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

        # Build compiled graph
        app = build_graph(workflow_def, enable_parallel=True, checkpointer=None)

        # Get Mermaid code
        graph_obj = app.get_graph(xray=xray)
        mermaid_code = graph_obj.draw_mermaid()

        return WorkflowVisualizationResponse(
            workflow_id=workflow_id,
            workflow_name=workflow.name,
            mermaid_code=mermaid_code,
            node_count=len(workflow.nodes),
            edge_count=len(workflow.edges),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate visualization for workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{workflow_id}/visualization.png")
async def get_workflow_visualization_png(
    workflow_id: str,
    db: Database = Depends(get_library_database),
    xray: bool = False,
) -> Response:
    """
    Get visualization as PNG image for a workflow.

    Returns the workflow graph as a PNG image.

    Args:
        workflow_id: Workflow ID
        xray: If True, show internal subgraph details

    Returns:
        PNG image of the workflow graph
    """
    try:
        # Load workflow
        store = WorkflowStore(db)
        workflow = store.get(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow not found: {workflow_id}"
            )

        # Build graph
        from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef
        from fichero.workflows.builder import build_graph

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

        # Build compiled graph
        app = build_graph(workflow_def, enable_parallel=True, checkpointer=None)

        # Get PNG bytes
        graph_obj = app.get_graph(xray=xray)
        png_bytes = graph_obj.draw_mermaid_png()

        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": f'inline; filename="{workflow.name}.png"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate PNG for workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{workflow_id}/code")
async def get_workflow_code(
    workflow_id: str,
    db: Database = Depends(get_library_database),
) -> WorkflowCodeExportResponse:
    """
    Export workflow as Python code.

    Generates Python code that recreates this workflow using LangGraph.
    The code can be run standalone or modified for custom use cases.

    Args:
        workflow_id: Workflow ID

    Returns:
        Python code as a string
    """
    try:
        # Load workflow
        store = WorkflowStore(db)
        workflow = store.get(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow not found: {workflow_id}"
            )

        # Generate Python code
        code = _generate_workflow_python_code(workflow)

        return WorkflowCodeExportResponse(
            workflow_id=workflow_id,
            workflow_name=workflow.name,
            python_code=code,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to export code for workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


def _generate_workflow_python_code(workflow: Workflow) -> str:
    """
    Generate Python code for a workflow.

    Creates runnable Python code that builds and executes the workflow
    using LangGraph primitives.
    """
    # Collect tool imports
    tools_used = set(n.get("tool", "") for n in workflow.nodes if n.get("tool"))

    # Build code
    lines = [
        '"""',
        f'Workflow: {workflow.name}',
        f'Description: {workflow.description or "No description"}',
        f'Generated from Fichero workflow ID: {workflow.id}',
        '"""',
        '',
        'from typing import Any, TypedDict',
        'from langgraph.graph import StateGraph, START, END',
        '',
        '# Import Fichero tools (adjust imports for your environment)',
        'from fichero.workflows.registry import get_tool',
        'from fichero.llm import LLMConfig',
        '',
        '',
        '# =============================================================================',
        '# State Definition',
        '# =============================================================================',
        '',
        'class State(TypedDict, total=False):',
        '    """Workflow state passed between nodes."""',
        '    files: list[str]  # Input files',
        '    results: list[Any]  # Processing results',
        '    artifacts: list[dict]  # Generated artifacts',
        '    errors: list[str]  # Error messages',
        '    library_path: str  # Library database path',
        '',
        '',
        '# =============================================================================',
        '# Node Functions',
        '# =============================================================================',
        '',
    ]

    # Generate node functions
    for node in workflow.nodes:
        node_id = node.get("id", "unknown")
        tool_name = node.get("tool", "unknown")
        label = node.get("label", tool_name)
        config = node.get("config", {})

        # Create safe function name
        func_name = f'node_{node_id.replace("-", "_")[:20]}'

        lines.extend([
            f'def {func_name}(state: State) -> dict[str, Any]:',
            f'    """',
            f'    Node: {label}',
            f'    Tool: {tool_name}',
            f'    """',
            f'    tool_fn = get_tool("{tool_name}")',
            f'    if tool_fn is None:',
            f'        return {{"errors": state.get("errors", []) + ["Tool not found: {tool_name}"]}}',
            f'    ',
            f'    # Get inputs from state',
            f'    inputs = {{',
            f'        "files": state.get("files", []),',
            f'        "results": state.get("results", []),',
        ])

        # Add config values
        for key, value in config.items():
            if isinstance(value, str):
                lines.append(f'        "{key}": "{value}",')
            else:
                lines.append(f'        "{key}": {value!r},')

        lines.extend([
            f'    }}',
            f'    ',
            f'    # Execute tool',
            f'    try:',
            f'        result = tool_fn(inputs)',
            f'        return result',
            f'    except Exception as e:',
            f'        return {{"errors": state.get("errors", []) + [str(e)]}}',
            f'',
            f'',
        ])

    # Build graph
    lines.extend([
        '# =============================================================================',
        '# Build Graph',
        '# =============================================================================',
        '',
        'def build_workflow() -> StateGraph:',
        f'    """Build the {workflow.name} workflow graph."""',
        '    graph = StateGraph(State)',
        '    ',
        '    # Add nodes',
    ])

    # Add nodes
    for node in workflow.nodes:
        node_id = node.get("id", "unknown")
        func_name = f'node_{node_id.replace("-", "_")[:20]}'
        lines.append(f'    graph.add_node("{node_id}", {func_name})')

    lines.append('    ')
    lines.append('    # Add edges')

    # Determine entry nodes (nodes with no incoming edges)
    target_nodes = set(e.get("target") or e.get("target_node_id", "") for e in workflow.edges)
    source_nodes = set(e.get("source") or e.get("source_node_id", "") for e in workflow.edges)
    all_node_ids = set(n.get("id", "") for n in workflow.nodes)
    entry_nodes = all_node_ids - target_nodes

    # Add START edges
    for entry_node in entry_nodes:
        if entry_node:
            lines.append(f'    graph.add_edge(START, "{entry_node}")')

    # Add workflow edges
    for edge in workflow.edges:
        source = edge.get("source") or edge.get("source_node_id", "")
        target = edge.get("target") or edge.get("target_node_id", "")
        if source and target:
            lines.append(f'    graph.add_edge("{source}", "{target}")')

    # Determine exit nodes (nodes with no outgoing edges)
    exit_nodes = all_node_ids - source_nodes

    # Add END edges
    for exit_node in exit_nodes:
        if exit_node:
            lines.append(f'    graph.add_edge("{exit_node}", END)')

    lines.extend([
        '    ',
        '    return graph',
        '',
        '',
        '# =============================================================================',
        '# Main Execution',
        '# =============================================================================',
        '',
        'if __name__ == "__main__":',
        '    # Build and compile the graph',
        '    graph = build_workflow()',
        '    app = graph.compile()',
        '    ',
        '    # Example execution',
        '    initial_state = {',
        '        "files": [],  # Add your input files here',
        '        "results": [],',
        '        "artifacts": [],',
        '        "errors": [],',
        '        "library_path": "",  # Set your library path',
        '    }',
        '    ',
        '    # Run the workflow',
        '    final_state = app.invoke(initial_state)',
        '    ',
        '    # Print results',
        '    print("Results:", final_state.get("results", []))',
        '    print("Artifacts:", final_state.get("artifacts", []))',
        '    if final_state.get("errors"):',
        '        print("Errors:", final_state["errors"])',
    ])

    return '\n'.join(lines)


# =============================================================================
# Cache Management Endpoints
# =============================================================================

class CacheStatsResponse(BaseModel):
    """Response with cache statistics."""
    total_entries: int
    workflows_cached: int | None = None
    nodes_cached: int | None = None
    tools_cached: int
    oldest_entry: str | None = None
    newest_entry: str | None = None


class CacheClearResponse(BaseModel):
    """Response after clearing cache."""
    entries_deleted: int
    message: str


@router.get("/workflows/{workflow_id}/cache/stats")
async def get_workflow_cache_stats(
    workflow_id: str,
    db: Database = Depends(get_library_database),
) -> CacheStatsResponse:
    """
    Get cache statistics for a workflow.

    Shows how many node results are cached, which tools are cached, etc.

    Args:
        workflow_id: Workflow ID

    Returns:
        Cache statistics
    """
    try:
        from fichero.workflows.cache import get_node_cache

        cache = get_node_cache(db.path)
        stats = cache.get_stats(workflow_id=workflow_id)

        return CacheStatsResponse(**stats)

    except Exception as e:
        logger.exception(f"Failed to get cache stats for workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/workflows/{workflow_id}/cache")
async def clear_workflow_cache(
    workflow_id: str,
    db: Database = Depends(get_library_database),
) -> CacheClearResponse:
    """
    Clear all cached results for a workflow.

    This will cause all nodes to be re-executed on the next run.

    Args:
        workflow_id: Workflow ID

    Returns:
        Number of entries deleted
    """
    try:
        from fichero.workflows.cache import get_node_cache

        cache = get_node_cache(db.path)
        count = cache.clear_workflow(workflow_id)

        return CacheClearResponse(
            entries_deleted=count,
            message=f"Cleared {count} cached entries for workflow {workflow_id}"
        )

    except Exception as e:
        logger.exception(f"Failed to clear cache for workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cache")
async def clear_all_cache(
    db: Database = Depends(get_library_database),
) -> CacheClearResponse:
    """
    Clear all cached node results.

    This will cause all nodes in all workflows to be re-executed on next run.

    Returns:
        Number of entries deleted
    """
    try:
        from fichero.workflows.cache import get_node_cache

        cache = get_node_cache(db.path)
        count = cache.clear_all()

        return CacheClearResponse(
            entries_deleted=count,
            message=f"Cleared entire cache: {count} entries"
        )

    except Exception as e:
        logger.exception("Failed to clear cache")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Workflow Run Data Endpoints
# =============================================================================

class WorkflowRunResponse(BaseModel):
    """Response with workflow run data (code, logs, etc.)."""
    thread_id: str
    workflow_id: str
    workflow_name: str
    python_code: str | None = None
    execution_log: str | None = None
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    error: str | None = None
    # New fields for historical visualization
    workflow_snapshot: dict | None = None
    node_name_map: dict[str, str] | None = None
    progress_timeline: dict | None = None
    diagram_mermaid: str | None = None


@router.get("/threads/{thread_id}/run")
async def get_workflow_run(
    thread_id: str,
    db: Database = Depends(get_library_database),
) -> WorkflowRunResponse:
    """
    Get workflow run data including Python code and execution log.

    Returns the saved Python code and execution log for a completed run.
    Useful for debugging and understanding what happened during execution.

    Args:
        thread_id: Thread ID

    Returns:
        Workflow run data with code and logs

    Raises:
        404: Run not found
    """
    try:
        activity_tracker = get_activity_tracker(str(db.path))
        run = await activity_tracker.store.get_workflow_run(thread_id)

        if not run:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow run not found for thread: {thread_id}"
            )

        return WorkflowRunResponse(
            thread_id=run["thread_id"],
            workflow_id=run["workflow_id"],
            workflow_name=run["workflow_name"],
            python_code=run.get("python_code"),
            execution_log=run.get("execution_log"),
            status=run.get("status", "unknown"),
            started_at=run.get("started_at"),  # Already ISO string from activity.py
            completed_at=run.get("completed_at"),  # Already ISO string from activity.py
            duration_ms=run.get("duration_ms"),
            error=run.get("error"),
            # New fields for historical visualization
            workflow_snapshot=run.get("workflow_snapshot"),
            node_name_map=run.get("node_name_map"),
            progress_timeline=run.get("progress_timeline"),
            diagram_mermaid=run.get("diagram_mermaid"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get workflow run for thread {thread_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads/{thread_id}/diagram.png")
async def get_thread_diagram_png(
    thread_id: str,
    db: Database = Depends(get_library_database),
) -> Response:
    """
    Get workflow diagram PNG from workflow run snapshot.

    This endpoint generates a diagram from the saved workflow snapshot,
    which means it works even if the original workflow definition was deleted.

    Args:
        thread_id: Thread ID of the workflow run

    Returns:
        PNG image of the workflow diagram

    Raises:
        404: Run not found or no snapshot available
        500: Failed to generate diagram
    """
    try:
        from fichero.workflows.builder import build_graph
        from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef

        activity_tracker = get_activity_tracker(str(db.path))
        run = await activity_tracker.store.get_workflow_run(thread_id)

        if not run:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow run not found: {thread_id}"
            )

        workflow_snapshot = run.get("workflow_snapshot")
        if not workflow_snapshot:
            raise HTTPException(
                status_code=404,
                detail="No workflow snapshot available for this run"
            )

        # Rebuild workflow definition from snapshot
        workflow_def = WorkflowDef(
            id=run["workflow_id"],
            name=run["workflow_name"],
            description="",
            provider="",
            model="",
            nodes=[
                NodeDef(
                    id=n["id"],
                    tool=n["tool"],
                    label=n.get("label", ""),
                    inputs={},
                    config={},
                )
                for n in workflow_snapshot["nodes"]
            ],
            edges=[
                EdgeDef(
                    source=e["source"],
                    target=e["target"],
                    source_port="output",
                    target_port="input",
                )
                for e in workflow_snapshot["edges"]
            ],
        )

        # Build graph and generate PNG
        app = build_graph(workflow_def, enable_parallel=True, checkpointer=None)
        png_bytes = app.get_graph().draw_mermaid_png()

        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": f'inline; filename="{run["workflow_name"]}.png"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate diagram for thread {thread_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache/stats")
async def get_all_cache_stats(
    db: Database = Depends(get_library_database),
) -> CacheStatsResponse:
    """
    Get overall cache statistics.

    Shows total cached entries across all workflows.

    Returns:
        Cache statistics
    """
    try:
        from fichero.workflows.cache import get_node_cache

        cache = get_node_cache(db.path)
        stats = cache.get_stats()

        return CacheStatsResponse(**stats)

    except Exception as e:
        logger.exception("Failed to get cache stats")
        raise HTTPException(status_code=500, detail=str(e))
