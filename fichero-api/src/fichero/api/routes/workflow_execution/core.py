"""
Workflow Execution Core Routes

Execute, stream, resume, and status-check workflows.
Includes SSE streaming, background task management, and Python code generation.
"""

import asyncio
import logging
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
from pydantic import BaseModel, Field

from fichero.db import Database
from fichero.api.main import get_library_database
from fichero.models import Workflow
from fichero.workflows.checkpointer import AsyncDuckDBCheckpointer
from fichero.workflows.workflow_store import WorkflowStore
from fichero.workflows.builder import SystemicErrorDetected, build_graph
from fichero.workflows.activity import get_activity_tracker
from fichero.workflows.runtime import (
    build_initial_state,
    create_compiled_app,
    create_compiled_app_with_checkpointer,
    to_workflow_def,
)

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
    interrupt_before: list[str] = Field(
        default_factory=list
    )  # Node IDs to pause before
    interrupt_after: list[str] = Field(default_factory=list)  # Node IDs to pause after
    force_new: bool = (
        False  # If True, ignore provided thread_id and create a fresh execution
    )
    skip_cache: bool = (
        False  # If True, bypass node result cache (still writes new results)
    )


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
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
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
# Python Code Generation (used by background runner and code-export endpoint)
# =============================================================================


def _generate_workflow_python_code(workflow: Workflow) -> str:
    """
    Generate Python code for a workflow.

    Creates runnable Python code that builds and executes the workflow
    using LangGraph primitives.
    """
    # Build code
    lines = [
        '"""',
        f"Workflow: {workflow.name}",
        f"Description: {workflow.description or 'No description'}",
        f"Generated from Fichero workflow ID: {workflow.id}",
        '"""',
        "",
        "from typing import Any, TypedDict",
        "from langgraph.graph import StateGraph, START, END",
        "",
        "# Import Fichero tools (adjust imports for your environment)",
        "from fichero.workflows.registry import get_tool",
        "from fichero.llm import LLMConfig",
        "",
        "",
        "# =============================================================================",
        "# State Definition",
        "# =============================================================================",
        "",
        "class State(TypedDict, total=False):",
        '    """Workflow state passed between nodes."""',
        "    files: list[str]  # Input files",
        "    results: list[Any]  # Processing results",
        "    artifacts: list[dict]  # Generated artifacts",
        "    errors: list[str]  # Error messages",
        "    library_path: str  # Library database path",
        "",
        "",
        "# =============================================================================",
        "# Node Functions",
        "# =============================================================================",
        "",
    ]

    # Generate node functions
    for node in workflow.nodes:
        node_id = node.get("id", "unknown")
        tool_name = node.get("tool", "unknown")
        label = node.get("label", tool_name)
        config = node.get("config", {})

        # Create safe function name
        func_name = f"node_{node_id.replace('-', '_')[:20]}"

        lines.extend(
            [
                f"def {func_name}(state: State) -> dict[str, Any]:",
                '    """',
                f"    Node: {label}",
                f"    Tool: {tool_name}",
                '    """',
                f'    tool_fn = get_tool("{tool_name}")',
                "    if tool_fn is None:",
                f'        return {{"errors": state.get("errors", []) + ["Tool not found: {tool_name}"]}}',
                "    ",
                "    # Get inputs from state",
                "    inputs = {",
                '        "files": state.get("files", []),',
                '        "results": state.get("results", []),',
            ]
        )

        # Add config values
        for key, value in config.items():
            if isinstance(value, str):
                lines.append(f'        "{key}": "{value}",')
            else:
                lines.append(f'        "{key}": {value!r},')

        lines.extend(
            [
                "    }",
                "    ",
                "    # Execute tool",
                "    try:",
                "        result = tool_fn(inputs)",
                "        return result",
                "    except Exception as e:",
                '        return {"errors": state.get("errors", []) + [str(e)]}',
                "",
                "",
            ]
        )

    # Build graph
    lines.extend(
        [
            "# =============================================================================",
            "# Build Graph",
            "# =============================================================================",
            "",
            "def build_workflow() -> StateGraph:",
            f'    """Build the {workflow.name} workflow graph."""',
            "    graph = StateGraph(State)",
            "    ",
            "    # Add nodes",
        ]
    )

    # Add nodes
    for node in workflow.nodes:
        node_id = node.get("id", "unknown")
        func_name = f"node_{node_id.replace('-', '_')[:20]}"
        lines.append(f'    graph.add_node("{node_id}", {func_name})')

    lines.append("    ")
    lines.append("    # Add edges")

    # Determine entry nodes (nodes with no incoming edges)
    target_nodes = set(
        e.get("target") or e.get("target_node_id", "") for e in workflow.edges
    )
    source_nodes = set(
        e.get("source") or e.get("source_node_id", "") for e in workflow.edges
    )
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

    lines.extend(
        [
            "    ",
            "    return graph",
            "",
            "",
            "# =============================================================================",
            "# Main Execution",
            "# =============================================================================",
            "",
            'if __name__ == "__main__":',
            "    # Build and compile the graph",
            "    graph = build_workflow()",
            "    app = graph.compile()",
            "    ",
            "    # Example execution",
            "    initial_state = {",
            '        "files": [],  # Add your input files here',
            '        "results": [],',
            '        "artifacts": [],',
            '        "errors": [],',
            '        "library_path": "",  # Set your library path',
            "    }",
            "    ",
            "    # Run the workflow",
            "    final_state = app.invoke(initial_state)",
            "    ",
            "    # Print results",
            '    print("Results:", final_state.get("results", []))',
            '    print("Artifacts:", final_state.get("artifacts", []))',
            '    if final_state.get("errors"):',
            '        print("Errors:", final_state["errors"])',
        ]
    )

    return "\n".join(lines)


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
    start_time = datetime.now(timezone.utc)
    node_start_times: dict[str, datetime] = {}
    execution_log_lines: list[str] = []  # Collect execution logs
    progress_timeline: dict[str, Any] = {
        "nodes": {},
        "steps": [],
    }  # Capture progress for historical viewing

    async def log_execution(message: str) -> None:
        """Log a message to both console and execution log, and stream via SSE."""
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] {message}"
        execution_log_lines.append(log_line)
        print(log_line)
        # Stream log line to frontend
        await event_queue.put(
            SSEEvent(
                event="log",
                thread_id=thread_id,
                workflow_id=workflow_id,
                data={"line": log_line},
            )
        )

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
        await event_queue.put(
            SSEEvent(
                event="start",
                thread_id=thread_id,
                workflow_id=workflow_id,
                data={"workflow_name": workflow.name, "inputs": request.inputs},
            )
        )

        # Build workflow using the shared runtime conversion path.
        workflow_def = to_workflow_def(workflow)

        # Generate and save Python code
        await log_execution("Generating Python code for workflow")
        python_code = _generate_workflow_python_code(workflow)

        # Create workflow snapshot for historical visualization (even if workflow is deleted)
        await log_execution("Creating workflow snapshot")
        workflow_snapshot = {
            "nodes": [
                {"id": n["id"], "tool": n["tool"], "label": n.get("label", "")}
                for n in workflow.nodes
            ],
            "edges": [
                {
                    "source": e.get("source") or e.get("source_node_id", ""),
                    "target": e.get("target") or e.get("target_node_id", ""),
                }
                for e in workflow.edges
            ],
        }

        # Build node name mapping (UUID → readable name)
        await log_execution("Building node name mapping")
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
        await log_execution("Generating workflow diagram")
        try:
            app_preview = build_graph(
                workflow_def, enable_parallel=True, checkpointer=None
            )
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
        await log_execution("Saved workflow run record with snapshot")

        # Create event callback for parallel processing events
        async def emit_parallel_event(event_type: str, data: dict) -> None:
            """Callback to emit SSE events from parallel node processing."""
            # Emit SSE event (existing behavior)
            await event_queue.put(
                SSEEvent(
                    event=event_type,
                    thread_id=thread_id,
                    workflow_id=workflow_id,
                    node_id=data.get("node_id", ""),
                    file_path=data.get("file_path"),
                    file_index=data.get("file_index"),
                    file_total=data.get("file_total"),
                    progress=data.get("progress"),
                    data={"error": data.get("error")} if data.get("error") else {},
                )
            )

            # Capture file-level timeline for historical viewing and log to console
            if event_type == "file_start":
                file_index = data.get("file_index", 0)
                file_total = data.get("file_total", 0)
                file_path = data.get("file_path", "")
                # Extract just the filename for cleaner logging
                file_name = file_path.split("/")[-1] if file_path else "unknown"
                await log_execution(
                    f"  Processing file {file_index}/{file_total}: {file_name}"
                )

                progress_timeline["steps"].append(
                    {
                        "type": "file",
                        "node_id": data.get("node_id", ""),
                        "file_path": file_path,
                        "file_index": file_index,
                        "file_total": file_total,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "status": "running",
                    }
                )
            elif event_type == "file_complete":
                file_index = data.get("file_index", 0)
                file_total = data.get("file_total", 0)
                file_path = data.get("file_path", "")
                file_name = file_path.split("/")[-1] if file_path else "unknown"

                # Find and update the matching file entry
                duration_ms = 0
                for entry in reversed(progress_timeline["steps"]):
                    if (
                        entry.get("type") == "file"
                        and entry.get("file_path") == file_path
                        and entry.get("status") == "running"
                    ):
                        entry["completed_at"] = datetime.now(timezone.utc).isoformat()
                        entry["status"] = "success"
                        # Calculate duration
                        start = datetime.fromisoformat(entry["started_at"])
                        duration_ms = (
                            datetime.now(timezone.utc) - start
                        ).total_seconds() * 1000
                        entry["duration_ms"] = duration_ms
                        break

                await log_execution(
                    f"  File {file_index}/{file_total} completed: {file_name} ({duration_ms:.0f}ms)"
                )
            elif event_type == "file_error":
                file_path = data.get("file_path", "")
                file_name = file_path.split("/")[-1] if file_path else "unknown"
                error_msg = data.get("error", "Unknown error")
                await log_execution(f"  ERROR processing {file_name}: {error_msg}")

                # Find and update the matching file entry
                for entry in reversed(progress_timeline["steps"]):
                    if (
                        entry.get("type") == "file"
                        and entry.get("file_path") == file_path
                        and entry.get("status") == "running"
                    ):
                        entry["completed_at"] = datetime.now(timezone.utc).isoformat()
                        entry["status"] = "error"
                        entry["error"] = error_msg
                        break
            elif event_type == "parallel_complete":
                # Save aggregate stats for the node
                progress_timeline["nodes"][data.get("node_id", "")] = {
                    "total_files": data.get("total", 0),
                    "success_count": data.get("success_count", 0),
                    "error_count": data.get("error_count", 0),
                }

        # Build graph with shared runtime path (same engine used by batch execution).
        app, checkpointer = create_compiled_app(
            workflow_def,
            db_path=db.path,
            enable_parallel=True,
            event_callback=emit_parallel_event,
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
        initial_state = build_initial_state(
            request.inputs,
            library_path=str(db.path.parent) if hasattr(db, "path") else "",
        )

        # Identify exit nodes (nodes with no outgoing edges) using raw IDs
        exit_node_ids = set()
        all_source_nodes = {
            e.get("source") or e.get("source_node_id", "") for e in workflow.edges
        }
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
                    node_start_times[node_name] = datetime.now(timezone.utc)
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
                    progress_timeline["steps"].append(
                        {
                            "node_id": original_id,
                            "started_at": datetime.now(timezone.utc).isoformat(),
                            "status": "running",
                        }
                    )

                    await event_queue.put(
                        SSEEvent(
                            event="node_begin",
                            thread_id=thread_id,
                            workflow_id=workflow_id,
                            node_id=original_id,
                            data={"node": original_id},
                        )
                    )

            elif event_kind == "on_chain_end" and event.get("name"):
                node_name = event.get("name", "")
                output = event.get("data", {}).get("output", {})

                if node_name not in ("__start__", "LangGraph"):
                    original_id = _normalize_node_name(node_name)

                    # Skip node_end for _process (node isn't done until _aggregate finishes)
                    if node_name.endswith("_process"):
                        continue

                    # Calculate node duration (use _process start time if this is _aggregate)
                    process_name = (
                        f"{original_id}_process"
                        if node_name.endswith("_aggregate")
                        else node_name
                    )
                    node_start = node_start_times.get(
                        process_name,
                        node_start_times.get(node_name, datetime.now(timezone.utc)),
                    )
                    node_duration_ms = (
                        datetime.now(timezone.utc) - node_start
                    ).total_seconds() * 1000

                    # Build activity metadata from output
                    activity_metadata = {}

                    # Check for parallel processing completion
                    if isinstance(output, dict) and "parallel_results" in output:
                        results = output.get("parallel_results", {})
                        for node_id, file_results in results.items():
                            success_count = sum(
                                1 for r in file_results if r.get("success")
                            )
                            error_count = len(file_results) - success_count
                            await event_queue.put(
                                SSEEvent(
                                    event="parallel_complete",
                                    thread_id=thread_id,
                                    workflow_id=workflow_id,
                                    node_id=node_id,
                                    data={
                                        "success_count": success_count,
                                        "error_count": error_count,
                                        "total": len(file_results),
                                    },
                                )
                            )
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

                    await log_execution(
                        f"Node '{original_id}' completed in {node_duration_ms:.0f}ms"
                    )

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
                        if (
                            entry.get("node_id") == original_id
                            and entry.get("status") == "running"
                            and entry.get("type") is None
                        ):  # Only update node steps, not file steps
                            entry["completed_at"] = datetime.now(
                                timezone.utc
                            ).isoformat()
                            entry["status"] = "success"
                            entry["duration_ms"] = node_duration_ms
                            # Add metadata
                            if "files_processed" in activity_metadata:
                                entry["files_processed"] = activity_metadata[
                                    "files_processed"
                                ]
                            if "artifacts_created" in activity_metadata:
                                entry["artifacts_created"] = activity_metadata[
                                    "artifacts_created"
                                ]
                            break

                    await event_queue.put(
                        SSEEvent(
                            event="node_end",
                            thread_id=thread_id,
                            workflow_id=workflow_id,
                            node_id=original_id,
                            data={"node": original_id, "duration_ms": node_duration_ms},
                        )
                    )

                    # Track exit node completion (using normalized ID)
                    if original_id in exit_node_ids:
                        completed_exit_nodes.add(original_id)
                        logger.info(
                            f"Exit node completed: {original_id}, {len(completed_exit_nodes)}/{len(exit_node_ids)}"
                        )

                        # Check if all exit nodes are done
                        if exit_node_ids and completed_exit_nodes >= exit_node_ids:
                            logger.info("All exit nodes completed, ending stream")
                            break

        # Get final state
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        final_state = (
            checkpoint_tuple.checkpoint.get("channel_values")
            if checkpoint_tuple
            else {}
        )

        # Store final state
        state["status"] = "completed"
        state["final_state"] = final_state

        # Calculate total duration
        total_duration_ms = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds() * 1000

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

        await log_execution(
            f"Workflow completed successfully in {total_duration_ms:.0f}ms"
        )

        # Save execution log and progress timeline to workflow run
        execution_log = "\n".join(execution_log_lines)
        await activity_tracker.store.update_workflow_run(
            thread_id=thread_id,
            status="completed",
            execution_log=execution_log,
            progress_timeline=progress_timeline,
            duration_ms=total_duration_ms,
            completed_at=datetime.now(timezone.utc),
        )

        # Send complete event
        await event_queue.put(
            SSEEvent(
                event="complete",
                thread_id=thread_id,
                workflow_id=workflow_id,
                data={
                    "checkpoint_id": checkpoint_tuple.checkpoint["id"]
                    if checkpoint_tuple
                    else None,
                    "final_state": final_state,
                    "duration_ms": total_duration_ms,
                },
            )
        )

    except SystemicErrorDetected as e:
        logger.error(f"Systemic error in background workflow {workflow_id}: {e}")
        state["status"] = "failed"
        state["error"] = str(e)

        # Calculate duration
        total_duration_ms = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds() * 1000

        await log_execution(
            f"SYSTEMIC ERROR: {e.error_count}/{e.total_count} consecutive failures"
        )
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
            completed_at=datetime.now(timezone.utc),
        )

        await event_queue.put(
            SSEEvent(
                event="systemic_error",
                thread_id=thread_id,
                workflow_id=workflow_id,
                data={
                    "error": str(e),
                    "error_count": e.error_count,
                    "total_count": e.total_count,
                    "sample_errors": e.errors[:5] if e.errors else [],
                },
            )
        )

    except Exception as e:
        logger.exception(f"Background workflow error for {workflow_id}")
        state["status"] = "failed"
        state["error"] = str(e)

        # Calculate duration
        total_duration_ms = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds() * 1000

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
            completed_at=datetime.now(timezone.utc),
        )

        await event_queue.put(
            SSEEvent(
                event="error",
                thread_id=thread_id,
                workflow_id=workflow_id,
                data={"error": str(e)},
            )
        )

    finally:
        # Signal end of stream
        await event_queue.put(None)  # Sentinel to signal stream end


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
    Build a workflow with checkpointing using the shared runtime path.
    """
    if interrupt_before or interrupt_after:
        logger.debug(
            "Interrupt hooks are not currently applied in shared runtime builder"
        )

    workflow_def = to_workflow_def(workflow)
    return create_compiled_app_with_checkpointer(
        workflow_def,
        checkpointer=checkpointer,
        enable_parallel=enable_parallel,
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

        # Create event queue for this workflow
        event_queue: asyncio.Queue = asyncio.Queue()

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

        # Start background execution
        # Note: We use asyncio.create_task instead of background_tasks.add_task
        # because background_tasks runs after the response is sent, but we need
        # the task to start immediately so events can begin flowing
        asyncio.create_task(
            _run_workflow_in_background(
                thread_id=thread_id,
                workflow=workflow,
                request=request,
                db=db,
            )
        )

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
                status_code=404, detail=f"No checkpoint found for thread: {thread_id}"
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
            current_state=current_state,
            error=workflow_error,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get status for thread {thread_id}")
        raise HTTPException(status_code=500, detail=str(e))
