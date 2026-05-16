"""Background workflow execution engine.

Contains:
- In-memory workflow state tracking
- Python code generation for workflows
- Background runner that streams SSE events
"""

import logging
import queue
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fichero.db import Database
from fichero.models import Workflow
from fichero.workflows.builder import SystemicErrorDetected, build_graph
from fichero.workflows.activity import get_activity_tracker
from fichero.workflows.runtime import (
    build_initial_state,
    create_compiled_app,
    to_workflow_def,
)

from .schemas import ExecuteWorkflowRequest, SSEEvent

logger = logging.getLogger(__name__)

# =============================================================================
# Background Task State
# =============================================================================

# Key: thread_id, Value: dict with workflow state and a thread-safe
# queue.Queue for events (the workflow runs on a worker thread — #1000)
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


# Internal LangChain LCEL runnables whose on_chain_start / on_chain_end
# events should NOT surface to the SSE workflow stream. (#1002)
#
# LangChain composes a single user-authored "Catalogue / Extract All"
# node out of ~10 internal Runnable nodes (RunnableSequence,
# RunnableLambda, RunnableParallel<…>, RunnableAssign<…>,
# RunnableWithFallbacks). Each fires its own start/end event ~doubling
# (with the paired log SSE) the wire volume per user node. The frontend
# already filters them out via ``activityHumanNodeName()``; we drop
# them at the source so we're not paying for the round trip.
_INTERNAL_LANGCHAIN_NAME_PREFIXES: tuple[str, ...] = ("Runnable",)


def _is_internal_langchain_node(name: str) -> bool:
    """Return True for framework-internal LCEL runnables.

    Catches ``RunnableSequence``, ``RunnableLambda``,
    ``RunnableParallel<parsed,parsing_error>``,
    ``RunnableAssign<parsed,parsing_error>``, and
    ``RunnableWithFallbacks`` — every Runnable subclass LangChain
    composes inside a single user-authored workflow node. (#1002)
    """
    return name.startswith(_INTERNAL_LANGCHAIN_NAME_PREFIXES)


# =============================================================================
# Python Code Generation
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

    Runs on a dedicated worker thread with its own event loop (#1000),
    spawned from the /execute route. Events go into
    ``_running_workflows[thread_id]["events"]`` — a thread-safe
    ``queue.Queue`` the SSE endpoint drains from the API loop.
    """
    # Re-acquire the Database on THIS worker thread. The `db` passed in
    # belongs to the API thread, and a DuckDB Connection is not
    # thread-safe — db_manager keys connections by thread, so this
    # returns a fresh connection to the same file for the worker. Tool
    # nodes likewise get their own connection via db_manager. (#1000)
    if hasattr(db, "path"):
        from fichero.db_manager import db_manager
        db = db_manager.get_database(db.path.parent)

    # Get the queue for this thread
    state = _get_workflow_state(thread_id)
    if not state:
        logger.error(f"No workflow state found for thread {thread_id}")
        return

    event_queue: "queue.Queue" = state["events"]
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
        event_queue.put(
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
        event_queue.put(
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
            event_queue.put(
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
            # #1127 — cancellation check. If the user POSTed
            # /threads/{id}/cancel, the cancel endpoint sets
            # state["cancel_requested"]=True. Break out of the stream;
            # the LangGraph checkpointer has already persisted partial
            # results (per the issue invariant: "partial results are
            # NOT rolled back"), and the activity tracker emits a
            # workflow_cancelled event in the surrounding finally.
            if state.get("cancel_requested"):
                state["status"] = "cancelled"
                await log_execution(
                    f"Workflow '{workflow.name}' cancelled by user "
                    f"(thread_id={thread_id}) — partial results "
                    f"preserved"
                )
                event_queue.put(
                    SSEEvent(
                        event="cancelled",
                        thread_id=thread_id,
                        workflow_id=workflow_id,
                        data={"reason": "user_requested"},
                    )
                )
                activity_tracker.workflow_cancelled(
                    workflow_id=workflow_id,
                    thread_id=thread_id,
                )
                return

            event_kind = event.get("event", "")

            if event_kind == "on_chain_start" and event.get("name"):
                node_name = event.get("name", "")
                if (
                    node_name not in ("__start__", "LangGraph")
                    and not _is_internal_langchain_node(node_name)
                ):
                    node_start_times[node_name] = datetime.now(timezone.utc)
                    original_id = _normalize_node_name(node_name)

                    # Skip node_begin for _aggregate (internal — the node already started with _process)
                    if node_name.endswith("_aggregate"):
                        continue

                    if node_name.endswith("_process"):
                        # Each parallel file invocation fires its own on_chain_start.
                        # Extract file context from state so the log shows filename + progress.
                        input_state = event.get("data", {}).get("input", {})
                        parallel_file = input_state.get("parallel_file", "")
                        parallel_index = input_state.get("parallel_index")
                        parallel_total = input_state.get("parallel_total")
                        filename = Path(parallel_file).name if parallel_file else ""
                        if filename and parallel_index is not None and parallel_total is not None:
                            await log_execution(
                                f"Node '{original_id}' — {filename} ({parallel_index + 1}/{parallel_total})"
                            )
                        else:
                            await log_execution(f"Node '{original_id}' started")
                    else:
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

                    event_queue.put(
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

                if (
                    node_name not in ("__start__", "LangGraph")
                    and not _is_internal_langchain_node(node_name)
                ):
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
                            event_queue.put(
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

                    event_queue.put(
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
        event_queue.put(
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

        event_queue.put(
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

        event_queue.put(
            SSEEvent(
                event="error",
                thread_id=thread_id,
                workflow_id=workflow_id,
                data={"error": str(e)},
            )
        )

    finally:
        # Signal end of stream
        event_queue.put(None)  # Sentinel to signal stream end

        # Release this worker thread's DuckDB connection + DBWriter so a
        # finished run doesn't leak them — the worker thread is daemon
        # and about to exit, but its db_manager entries would otherwise
        # linger keyed by the dead thread id. (#1000)
        try:
            from fichero.db_manager import db_manager
            db_manager.close_current_thread()
        except Exception as exc:
            logger.warning("worker-thread db cleanup failed: %s", exc)
