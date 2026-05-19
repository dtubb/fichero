"""Workflow thread management routes — history, list, delete, and run data."""

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from fichero.db import Database
from fichero.api.main import get_library_database
from fichero.workflows.workflow_store import WorkflowStore
from fichero.workflows.activity import get_activity_tracker
from fichero.workflows.types import EdgeDef, NodeDef, WorkflowDef

from .schemas import ThreadListResponse
from .core import get_thread_status

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Models
# =============================================================================


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


class ThreadDeletedResponse(BaseModel):
    message: str


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
    # Fields for historical visualization
    workflow_snapshot: dict | None = None
    node_name_map: dict[str, str] | None = None
    progress_timeline: dict | None = None
    diagram_mermaid: str | None = None


# =============================================================================
# Helpers
# =============================================================================


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


# =============================================================================
# Endpoints
# =============================================================================


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
        from fichero.workflows.checkpointer import AsyncDuckDBCheckpointer  # noqa: PLC0415
        checkpointer = AsyncDuckDBCheckpointer.from_db_path(db.path)

        # Check if thread exists
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        latest_tuple = await checkpointer.aget_tuple(config)

        if not latest_tuple:
            raise HTTPException(
                status_code=404, detail=f"No checkpoint found for thread: {thread_id}"
            )

        # workflow_id is in channel_values (CheckpointMetadata is LangGraph-
        # internal; cannot carry user fields — see #1079).
        thread_state = latest_tuple.checkpoint.get("channel_values", {})
        workflow_id = (
            (thread_state.get("workflow_id") if isinstance(thread_state, dict) else None)
            or latest_tuple.metadata.get("workflow_id")
            or "unknown"
        )
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
            logger.info(
                f"Building node name mapping from workflow definition for thread {thread_id}"
            )
            name_counts: dict[str, int] = {}
            for node in workflow.nodes:
                node_id = node.get("id", "")
                # Use label if available, otherwise capitalize tool name
                base_name = (
                    node.get("label")
                    or node.get("tool", "unknown").replace("_", " ").title()
                )

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
                next_nodes = [
                    w[1] for w in checkpoint_tuple.pending_writes if len(w) > 1
                ]

            # Extract node name from various sources
            source = metadata.get("source", "")
            raw_node_name = None

            # Try writes first (the node that wrote data)
            if writes:
                # Filter out internal keys like '__pregel_tasks', 'parallel_results'
                real_node_keys = [
                    k
                    for k in writes.keys()
                    if not k.startswith("__") and k not in ("parallel_results",)
                ]
                if real_node_keys:
                    raw_node_name = real_node_keys[0]

            # Try current_node from channel_values
            if not raw_node_name and channel_values.get("current_node"):
                raw_node_name = channel_values["current_node"]

            # Try completed_nodes (last completed)
            if not raw_node_name:
                completed = channel_values.get("completed_nodes", [])
                if completed:
                    raw_node_name = (
                        completed[-1] if isinstance(completed, list) else str(completed)
                    )

            # Try metadata source (format: "loop:node_name")
            if not raw_node_name and source and ":" in source:
                parts = source.split(":")
                if len(parts) > 1 and parts[1] not in (
                    "start",
                    "__start__",
                    "end",
                    "__end__",
                ):
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
                        translated = [
                            _translate_node_name(n) or n for n in contributing_nodes[:3]
                        ]
                        node_name = f"Parallel: {', '.join(translated)}"
                        if len(contributing_nodes) > 3:
                            node_name += f" +{len(contributing_nodes) - 3}"

            # Try to get timestamp from metadata
            timestamp = metadata.get("created_at") or metadata.get("timestamp")

            snapshots = CheckpointSnapshot(
                checkpoint_id=checkpoint.get("id", ""),
                parent_checkpoint_id=checkpoint_tuple.parent_config["configurable"][
                    "checkpoint_id"
                ]
                if checkpoint_tuple.parent_config
                else None,
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
        # Lazy import — see commit 4168 (May 18) for the circular-dep rationale.
        from fichero.workflows.checkpointer import AsyncDuckDBCheckpointer

        checkpointer = AsyncDuckDBCheckpointer.from_db_path(db.path)

        thread_ids = await checkpointer.alist_threads(limit=limit)

        # Get status for each thread
        threads = []
        for tid in thread_ids:
            try:
                status = await get_thread_status(tid, db)
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
) -> ThreadDeletedResponse:
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
        # Lazy import — see commit 4168 (May 18) for the circular-dep rationale.
        from fichero.workflows.checkpointer import AsyncDuckDBCheckpointer

        checkpointer = AsyncDuckDBCheckpointer.from_db_path(db.path)

        # Check if thread exists
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        checkpoint_tuple = await checkpointer.aget_tuple(config)

        if not checkpoint_tuple:
            raise HTTPException(
                status_code=404, detail=f"No checkpoint found for thread: {thread_id}"
            )

        # Delete all checkpointer-owned state for this thread via the
        # typed public API. The Checkpointer wraps the multi-table delete
        # in a transaction so a partial delete cannot orphan rows. See #1116.
        deleted = await checkpointer.adelete_thread(thread_id)

        logger.info(f"Deleted thread: {thread_id} (rows={deleted})")
        return ThreadDeletedResponse(message=f"Thread deleted: {thread_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete thread {thread_id}")
        raise HTTPException(status_code=500, detail=str(e))


class CancelResponse(BaseModel):
    """Response from POST /threads/{thread_id}/cancel (#1127).

    ``partial_results_preserved`` is always True for now — the issue's
    invariant is that artifacts and entities written before the cancel
    stay in place. Future work could add a soft-rollback option that
    deletes per-thread writes; for now we surface the contract clearly
    in the response shape.
    """

    thread_id: str
    status: str  # "cancel_requested" | "not_running" | "already_terminal"
    partial_results_preserved: bool = True
    message: str = ""


@router.post("/threads/{thread_id}/cancel", response_model=CancelResponse)
async def cancel_workflow(
    thread_id: str,
) -> CancelResponse:
    """Signal a running workflow to stop at the next astream_events
    tick (#1127).

    The runner's astream_events loop checks ``state["cancel_requested"]``
    on every event; setting it here causes the loop to break,
    a ``workflow_cancelled`` SSE event to fire, and an activity-log
    entry to record the cancellation. Partial results (artifacts,
    entities, claims already written) are intentionally preserved so
    a comparison loop can inspect what got done before the user
    interrupted.

    Idempotent: cancelling a thread that's already cancelled /
    completed / failed returns ``status="already_terminal"`` and a
    descriptive message instead of raising. Cancelling a thread that
    isn't in the running registry at all returns
    ``status="not_running"``.
    """
    # Import lazily to keep test isolation tight — the runner module
    # imports a lot of LangChain machinery; we only need its registry.
    from .runner import _get_workflow_state

    state = _get_workflow_state(thread_id)
    if state is None:
        return CancelResponse(
            thread_id=thread_id,
            status="not_running",
            partial_results_preserved=True,
            message=(
                f"No running workflow with thread_id={thread_id}. "
                "It may have already finished or never started."
            ),
        )

    current = state.get("status")
    if current in ("completed", "failed", "cancelled"):
        return CancelResponse(
            thread_id=thread_id,
            status="already_terminal",
            partial_results_preserved=True,
            message=(
                f"Workflow is already in terminal state '{current}'; "
                "nothing to cancel."
            ),
        )

    # The astream loop in runner picks this flag up on the next event
    # tick. No need to await anything here — the runner handles the
    # graceful exit, SSE event emission, and activity logging.
    state["cancel_requested"] = True
    logger.info(
        "cancel_workflow: marked thread %s for cancellation", thread_id,
    )
    return CancelResponse(
        thread_id=thread_id,
        status="cancel_requested",
        partial_results_preserved=True,
        message=(
            "Cancellation requested. Workflow will stop at the next "
            "execution tick; partial results stay in place."
        ),
    )


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
                detail=f"Workflow run not found for thread: {thread_id}",
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
        activity_tracker = get_activity_tracker(str(db.path))
        run = await activity_tracker.store.get_workflow_run(thread_id)

        if not run:
            raise HTTPException(
                status_code=404, detail=f"Workflow run not found: {thread_id}"
            )

        workflow_snapshot = run.get("workflow_snapshot")
        if not workflow_snapshot:
            raise HTTPException(
                status_code=404, detail="No workflow snapshot available for this run"
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

        # Build graph and generate PNG using local PYPPETEER rendering.
        # This eliminates the remote mermaid.ink dependency which 400s on
        # complex graphs whose URL-encoded mermaid source exceeds the upstream
        # limit (#952, #1025).
        try:
            from fichero.workflows.builder import build_graph  # noqa: PLC0415
            from langchain_core.runnables.graph import MermaidDrawMethod  # noqa: PLC0415
            app = build_graph(workflow_def, enable_parallel=True, checkpointer=None)
            png_bytes = app.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.PYPPETEER)
        except Exception as render_exc:
            logger.warning(
                "Mermaid PNG render failed for thread %s (likely upstream "
                "mermaid.ink 400 on a complex graph): %s",
                thread_id, render_exc,
            )
            raise HTTPException(
                status_code=503,
                detail="Diagram renderer unavailable (upstream mermaid.ink failed).",
            )

        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": f'inline; filename="{run["workflow_name"]}.png"'
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate diagram for thread {thread_id}")
        raise HTTPException(status_code=500, detail=str(e))
