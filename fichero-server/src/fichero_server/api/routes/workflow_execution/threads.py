"""Workflow thread management routes — history, list, delete, and run data."""

import base64
import json
import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from fichero_server.db import Database
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.models import Artifact, Document
from fichero_server.workflows.workflow_store import WorkflowStore
from fichero_server.workflows.activity import get_activity_tracker
from fichero_server.workflows.activity_types import WorkflowRun
from fichero_server.workflows.types import EdgeDef, NodeDef, WorkflowDef
from fichero_server.workflows.run_steps import (
    RunStep,
    RunStepArtifact,
    build_run_steps,
)
from fichero_server.workflows.run_status import (
    DELETABLE_STATUSES,
    DELETED_STATUS,
    NON_TERMINAL_STATUSES,
    RunStatus,
    is_terminal,
    normalize_status,
)
from fichero_server.execution.cancellation import request_cancellation


from .schemas import ThreadListResponse, workflow_internal_error
from .core import get_thread_status

# Resolved on first access, not at import (#3950): checkpointer.py pulls
# langgraph, and this router is imported at engine startup.
#
# It MUST remain a module attribute so tests can patch
# `threads.AsyncDuckDBCheckpointer.from_db_path` — that patch does a getattr on
# this module, which fires __getattr__ below, imports the real class and
# patches it. The call-time imports in the handlers then resolve to the same
# (patched) class object, so the test seam is unchanged.
def __getattr__(name: str):
    """Resolve AsyncDuckDBCheckpointer on first access (PEP 562)."""
    if name == "AsyncDuckDBCheckpointer":
        from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer as _cls

        globals()[name] = _cls
        return _cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    # One generated enum for the app to adopt (#4316) — legacy synonyms are
    # normalized server-side before construction.
    status: RunStatus
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    error: str | None = None
    # Fields for historical visualization
    workflow_snapshot: dict | None = None
    node_name_map: dict[str, str] | None = None
    progress_timeline: dict | None = None
    diagram_mermaid: str | None = None
    planned_steps: list["WorkflowPlannedStepResponse"] = Field(default_factory=list)
    run_artifacts: list["WorkflowRunArtifactResponse"] = Field(default_factory=list)
    # #4284: one record per step of the run — what it was asked to do, what it
    # did, and what it produced. A run of N planned steps always yields N
    # records, so a step that produced nothing is visible as such instead of
    # being absent like a step that never ran.
    steps: list["WorkflowRunStepResponse"] = Field(default_factory=list)
    diagram_svg_url: str | None = None


class WorkflowPlannedStepResponse(BaseModel):
    """One node from the persisted workflow snapshot."""

    node_id: str
    node_name: str
    tool: str
    upstream_ids: list[str] = Field(default_factory=list)
    downstream_ids: list[str] = Field(default_factory=list)


class WorkflowRunArtifactResponse(BaseModel):
    """Artifact produced by a workflow run, with navigation targets.

    Carries the whole provenance chain (#4284): which run, which step, which
    workflow, which document it was derived from, and which provider/model
    produced it. An artifact that cannot be traced back to all of those is a
    file, not a record.
    """

    artifact_id: str
    artifact_type: str
    document_id: str
    document_name: str | None = None
    source_document_id: str | None = None
    source_document_name: str | None = None
    run_id: str | None = None
    workflow_id: str | None = None
    step_name: str | None = None
    node_name: str | None = None
    provider: str | None = None
    model: str | None = None
    sequence: int | None = None
    created_at: str | None = None
    # Preview only — the full artifact stays addressable at
    # GET /api/artifacts/{artifact_id}. Truncation is in the RESPONSE, never
    # in what was stored.
    content_chars: int = 0
    content_preview: str | None = None
    content_truncated: bool = False
    has_structured_data: bool = False


class WorkflowRunStepResponse(BaseModel):
    """One step of a run: planned, observed, and what it produced (#4284)."""

    node_id: str
    node_name: str
    tool: str
    # not_run | running | completed | skipped | failed | cancelled
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    error: str | None = None
    skip_reason: str | None = None
    # The step's terminal status came from the RUN ending, not from the step
    # reporting an outcome of its own.
    terminated_by_run: bool = False
    files_total: int = 0
    files_succeeded: int = 0
    files_failed: int = 0
    artifact_count: int = 0
    # Reached a terminal state having produced no artifact. Stated, not
    # inferred from an empty list.
    produced_nothing: bool = False
    artifacts: list[WorkflowRunArtifactResponse] = Field(default_factory=list)


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


def _iso(v: Any) -> str | None:
    return v.isoformat() if hasattr(v, "isoformat") else v


def _run_node_names(run: WorkflowRun | None) -> dict[str, str]:
    return dict(run.node_name_map or {}) if run else {}


def _workflow_def_from_run(run: WorkflowRun) -> WorkflowDef:
    workflow_snapshot = run.workflow_snapshot
    if not workflow_snapshot:
        raise HTTPException(
            status_code=404, detail="No workflow snapshot available for this run"
        )
    return WorkflowDef(
        id=run.workflow_id,
        name=run.workflow_name,
        description="",
        provider="",
        model="",
        nodes=[
            NodeDef(
                id=node["id"],
                tool=node["tool"],
                label=node.get("label", ""),
                inputs={},
                config={},
            )
            for node in workflow_snapshot.get("nodes", [])
        ],
        edges=[
            EdgeDef(
                source=edge["source"],
                target=edge["target"],
                source_port=edge.get("source_port", "output"),
                target_port=edge.get("target_port", "input"),
            )
            for edge in workflow_snapshot.get("edges", [])
        ],
    )


def _planned_steps_from_run(run: WorkflowRun) -> list[WorkflowPlannedStepResponse]:
    workflow_snapshot = run.workflow_snapshot or {}
    node_name_map = _run_node_names(run)
    nodes = workflow_snapshot.get("nodes", [])
    edges = workflow_snapshot.get("edges", [])
    upstreams: dict[str, list[str]] = {}
    downstreams: dict[str, list[str]] = {}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            continue
        downstreams.setdefault(source, []).append(target)
        upstreams.setdefault(target, []).append(source)

    planned_steps: list[WorkflowPlannedStepResponse] = []
    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            continue
        planned_steps.append(
            WorkflowPlannedStepResponse(
                node_id=node_id,
                node_name=node_name_map.get(node_id) or node.get("label") or node.get("tool", node_id),
                tool=node.get("tool", "unknown"),
                upstream_ids=upstreams.get(node_id, []),
                downstream_ids=downstreams.get(node_id, []),
            )
        )
    return planned_steps


def _artifact_row(record: RunStepArtifact) -> WorkflowRunArtifactResponse:
    return WorkflowRunArtifactResponse(**asdict(record))


def _step_row(step: RunStep) -> WorkflowRunStepResponse:
    payload = asdict(step)
    payload["artifacts"] = [
        _artifact_row(RunStepArtifact(**a)) for a in payload["artifacts"]
    ]
    return WorkflowRunStepResponse(**payload)


def _run_step_records(
    db: Database,
    thread_id: str,
    *,
    run: WorkflowRun,
    planned_steps: list[WorkflowPlannedStepResponse],
    node_name_map: dict[str, str],
) -> list[RunStep]:
    """Join the run's snapshot, timeline, and artifacts into per-step records.

    One DB read for the artifacts and one for the documents they name; the
    join itself is pure (workflows.run_steps) so it is testable without HTTP.
    """
    artifacts = list(db.query(Artifact, run_id=thread_id))
    doc_ids = {
        doc_id
        for artifact in artifacts
        for doc_id in (artifact.document_id, artifact.source_document_id)
        if doc_id
    }
    document_names = (
        {doc.id: doc.name for doc in db.query(Document) if doc.id in doc_ids}
        if doc_ids
        else {}
    )
    return build_run_steps(
        planned_nodes=[
            {"node_id": s.node_id, "node_name": s.node_name, "tool": s.tool}
            for s in planned_steps
        ],
        progress_timeline=run.progress_timeline,
        artifacts=artifacts,
        node_name_map=node_name_map,
        document_names=document_names,
    )


def _flatten_run_artifacts(steps: list[RunStep]) -> list[WorkflowRunArtifactResponse]:
    """Every artifact of the run, in pipeline order.

    Each artifact belongs to exactly one step record (unattributed ones land
    under the '(unattributed)' pseudo-step), so flattening loses nothing.
    Pipeline order when sequence is populated (#4313); created_at fallback for
    artifacts persisted before the sequence field existed.
    """
    flat = [artifact for step in steps for artifact in step.artifacts]
    flat.sort(
        key=lambda item: (
            item.sequence if item.sequence is not None else 0,
            str(item.created_at or ""),
        )
    )
    return [_artifact_row(record) for record in flat]


async def _get_workflow_run_or_404(db: Database, thread_id: str) -> WorkflowRun:
    activity_tracker = get_activity_tracker(str(db.path))
    run = await activity_tracker.store.get_workflow_run(thread_id)
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow run not found for thread: {thread_id}",
        )
    return run


async def _render_run_diagram_png(run: WorkflowRun) -> bytes:
    workflow_def = _workflow_def_from_run(run)

    from fichero_server.workflows.builder import build_graph  # noqa: PLC0415
    from langchain_core.runnables.graph import MermaidDrawMethod  # noqa: PLC0415

    app = build_graph(workflow_def, enable_parallel=True, checkpointer=None)
    graph_obj = app.get_graph()
    return await run_in_threadpool(
        graph_obj.draw_mermaid_png,
        draw_method=MermaidDrawMethod.PYPPETEER,
    )


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
        from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer  # noqa: PLC0415

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

        if run and run.node_name_map:
            # Use saved mapping (works even if workflow was deleted)
            node_names = run.node_name_map
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
    except Exception:
        logger.exception(f"Failed to get history for thread {thread_id}")
        raise workflow_internal_error("Failed to get workflow history")


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
        from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer  # noqa: PLC0415

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

    except Exception:
        logger.exception("Failed to list threads")
        raise workflow_internal_error("Failed to list workflow threads")


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    db: Database = Depends(get_library_database_for_write),
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
        from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer  # noqa: PLC0415

        checkpointer = AsyncDuckDBCheckpointer.from_db_path(db.path)

        # Check if thread exists in either canonical store. Accepted runs are
        # persisted before the first checkpoint, so delete must not depend on
        # checkpoint presence alone.
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        activity_store = get_activity_tracker(str(db.path)).store
        run = await activity_store.get_workflow_run(thread_id)

        if not checkpoint_tuple and not run:
            raise HTTPException(
                status_code=404, detail=f"No checkpoint found for thread: {thread_id}"
            )

        # #2624/#4316: one canonical deletable set — terminal states, the
        # soft-delete marker, and paused/accepted (previously dead ends that
        # 409'd forever, e.g. a run paused before its first checkpoint).
        run_status = normalize_status(run.status) if run else None
        if run and run_status not in DELETABLE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot delete non-terminal workflow run '{thread_id}' "
                    f"with status '{run.status}'"
                ),
            )

        # Deleting a paused/accepted run: signal cancellation first so a
        # late-starting or evicted worker aborts instead of resurrecting the
        # row it is about to lose (#4316/#4317).
        if run_status in NON_TERMINAL_STATUSES:
            request_cancellation(thread_id)

        deleted = await checkpointer.adelete_thread(thread_id) if checkpoint_tuple else 0
        if run:
            get_activity_tracker(str(db.path)).workflow_deleted(
                workflow_id=run.workflow_id,
                thread_id=thread_id,
                workflow_name=run.workflow_name,
                previous_status=run.status,
            )
        activity_deleted = await activity_store.delete_workflow_run(thread_id)

        logger.info(
            "Deleted thread: %s (checkpoint_rows=%s, activity_rows=%s)",
            thread_id,
            deleted,
            activity_deleted,
        )
        return ThreadDeletedResponse(message=f"Thread deleted: {thread_id}")

    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to delete thread {thread_id}")
        raise workflow_internal_error("Failed to delete workflow thread")


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


class PauseResponse(BaseModel):
    """Response from POST /threads/{thread_id}/pause."""

    thread_id: str
    status: str  # "pause_requested" | "not_running" | "already_terminal"
    message: str = ""


async def _cancel_settled_run(
    db: Database,
    thread_id: str,
    run: WorkflowRun | None,
    state: dict | None,
) -> None:
    """Directly settle a run whose worker coroutine is gone (paused, or
    accepted with a dead worker): mark it cancelled and free its documents.

    A paused run's worker returned at the pause boundary, so no flag/event can
    ever reach it — cancel must finish the job itself (#4316).
    """
    now_status = "cancelled"
    if state is not None:
        state["status"] = now_status
    tracker = get_activity_tracker(str(db.path))
    if run:
        tracker.workflow_cancelled(
            workflow_id=run.workflow_id,
            thread_id=thread_id,
            workflow_name=run.workflow_name,
            partial_results_preserved=True,
        )
    from datetime import datetime, timezone  # noqa: PLC0415

    await tracker.store.update_workflow_run(
        thread_id=thread_id,
        status=now_status,
        completed_at=datetime.now(timezone.utc),
    )

    # #4315: settle any documents the run left at Status.processing.
    try:
        from fichero_server.workflows.checkpointer import (  # noqa: PLC0415
            AsyncDuckDBCheckpointer,
        )
        from fichero_server.workflows.completion import (  # noqa: PLC0415
            collect_processed_document_ids,
            finalize_run_documents,
        )

        checkpointer = AsyncDuckDBCheckpointer.from_db_path(db.path)
        tup = await checkpointer.aget_tuple(
            {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        )
        channel_values = tup.checkpoint.get("channel_values") if tup else {}
        finalize_run_documents(
            db,
            collect_processed_document_ids(channel_values or {}),
            "cancelled",
            workflow_run={
                "thread_id": thread_id,
                "workflow_id": run.workflow_id if run else None,
                "workflow_name": run.workflow_name if run else None,
                "result": {"status": "cancelled", "reason": "cancelled_while_paused"},
                "completed_at": datetime.now(timezone.utc),
            },
        )
    except Exception as finalize_exc:  # pragma: no cover - defensive
        logger.warning(
            "cancel_workflow: document finalize failed for %s: %s",
            thread_id,
            finalize_exc,
        )


@router.post("/threads/{thread_id}/cancel", response_model=CancelResponse)
async def cancel_workflow(
    thread_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> CancelResponse:
    """Cancel a workflow run in ANY non-terminal state (#1127, #4316, #4317).

    - A running (or about-to-run ``accepted``) worker is signalled through
      BOTH the registry flag and the shared cancellation event
      (execution.cancellation), which the runner's event loop AND the
      per-file fan-out check — so cancel reaches a run even after registry
      eviction, and stops multi-file nodes at the next file boundary.
    - A ``paused`` run has no live coroutine to signal — its worker returned
      at the pause boundary — so cancel settles it directly: run row →
      cancelled, processing documents → pending (#4315).

    Partial results (artifacts, entities, claims already written) are
    intentionally preserved. Idempotent: terminal runs return
    ``status="already_terminal"``; unknown threads ``status="not_running"``.
    """
    # Import lazily to keep test isolation tight — the runner module
    # imports a lot of LangChain machinery; we only need its registry.
    from fichero_server.execution.runner import _get_workflow_state

    state = _get_workflow_state(thread_id)
    run: WorkflowRun | None = None
    try:
        run = await get_activity_tracker(str(db.path)).store.get_workflow_run(
            thread_id
        )
    except Exception as run_exc:  # pragma: no cover - defensive
        logger.debug("cancel_workflow: run lookup failed for %s: %s", thread_id, run_exc)

    current = (
        state.get("status") if state is not None else normalize_status(run.status)
        if run
        else None
    )
    if current is None:
        return CancelResponse(
            thread_id=thread_id,
            status="not_running",
            partial_results_preserved=True,
            message=(
                f"No running workflow with thread_id={thread_id}. "
                "It may have already finished or never started."
            ),
        )

    if is_terminal(current) or current == DELETED_STATUS:
        return CancelResponse(
            thread_id=thread_id,
            status="already_terminal",
            partial_results_preserved=True,
            message=(
                f"Workflow is already in terminal state '{current}'; "
                "nothing to cancel."
            ),
        )

    # Reaches the runner loop, the per-file fan-out, and evicted-but-live
    # workers alike (#4317).
    request_cancellation(thread_id)

    if current == RunStatus.paused.value or state is None:
        # Paused: the worker coroutine already returned — settle directly.
        # No registry state: the worker is either dead (accepted/paused row)
        # or evicted; for an evicted RUNNING worker the event above will make
        # it settle itself, so only settle non-running rows here.
        if current == RunStatus.running.value:
            logger.info(
                "cancel_workflow: thread %s not in registry but recorded "
                "running — cancellation event set for an evicted worker",
                thread_id,
            )
            return CancelResponse(
                thread_id=thread_id,
                status="cancel_requested",
                partial_results_preserved=True,
                message=(
                    "Cancellation requested. The run is no longer tracked in "
                    "memory; a live worker will stop at its next boundary, "
                    "otherwise recovery will settle it."
                ),
            )
        await _cancel_settled_run(db, thread_id, run, state)
        logger.info(
            "cancel_workflow: settled %s run %s as cancelled", current, thread_id
        )
        return CancelResponse(
            thread_id=thread_id,
            status="cancelled",
            partial_results_preserved=True,
            message=(
                f"Workflow was {current}; it has been cancelled and its "
                "documents released."
            ),
        )

    # Running / accepted with a live worker: flag + event, worker settles.
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


@router.post("/threads/{thread_id}/pause", response_model=PauseResponse)
async def pause_workflow(
    thread_id: str,
) -> PauseResponse:
    """Signal a running workflow to pause at the next execution tick."""
    from fichero_server.execution.runner import _get_workflow_state

    state = _get_workflow_state(thread_id)
    if state is None:
        return PauseResponse(
            thread_id=thread_id,
            status="not_running",
            message=(
                f"No running workflow with thread_id={thread_id}. "
                "It may have already finished or never started."
            ),
        )

    current = state.get("status")
    if is_terminal(current):
        return PauseResponse(
            thread_id=thread_id,
            status="already_terminal",
            message=(
                f"Workflow is already in terminal state '{current}'; "
                "nothing to pause."
            ),
        )

    state["pause_requested"] = True
    logger.info("pause_workflow: marked thread %s for pause", thread_id)
    return PauseResponse(
        thread_id=thread_id,
        status="pause_requested",
        message=(
            "Pause requested. Workflow will pause at the next "
            "execution tick and can be resumed later."
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
        run = await _get_workflow_run_or_404(db, thread_id)
        node_name_map = _run_node_names(run)
        planned_steps = _planned_steps_from_run(run)
        step_records = _run_step_records(
            db,
            thread_id,
            run=run,
            planned_steps=planned_steps,
            node_name_map=node_name_map,
        )

        return WorkflowRunResponse(
            thread_id=run.thread_id,
            workflow_id=run.workflow_id,
            workflow_name=run.workflow_name,
            python_code=run.python_code,
            execution_log=run.execution_log,
            # normalize legacy synonyms; None falls back to the column default
            # ('running'). An unknown string raises — never silently rebadged.
            status=RunStatus(normalize_status(run.status) or "running"),
            started_at=_iso(run.started_at),
            completed_at=_iso(run.completed_at),
            duration_ms=run.duration_ms,
            error=run.error,
            workflow_snapshot=run.workflow_snapshot,
            node_name_map=node_name_map,
            progress_timeline=run.progress_timeline,
            diagram_mermaid=run.diagram_mermaid,
            planned_steps=planned_steps,
            run_artifacts=_flatten_run_artifacts(step_records),
            steps=[_step_row(step) for step in step_records],
            diagram_svg_url=f"/api/workflow-execution/threads/{thread_id}/diagram.svg",
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to get workflow run for thread {thread_id}")
        raise workflow_internal_error("Failed to get workflow run")


@router.get(
    "/threads/{thread_id}/diagram.png",
    response_class=Response,
    responses={
        200: {
            "content": {
                "image/png": {"schema": {"type": "string", "format": "binary"}},
            },
            "description": "PNG image of the workflow diagram",
        },
    },
)
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
        run = await _get_workflow_run_or_404(db, thread_id)

        try:
            png_bytes = await _render_run_diagram_png(run)
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
                "Content-Disposition": f'inline; filename="{run.workflow_name}.png"'
            },
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to generate diagram for thread {thread_id}")
        raise workflow_internal_error("Failed to generate workflow diagram")


@router.get("/threads/{thread_id}/diagram.svg")
async def get_thread_diagram_svg(
    thread_id: str,
    db: Database = Depends(get_library_database),
) -> Response:
    """Get workflow diagram as an SVG wrapper around the rendered run graph."""
    try:
        run = await _get_workflow_run_or_404(db, thread_id)
        png_bytes = await _render_run_diagram_png(run)
        png_b64 = base64.b64encode(png_bytes).decode("ascii")
        # ponytail: reuse the known-good PNG render path and wrap it in SVG;
        # switch to direct Mermaid→SVG only when a stable local renderer exists.
        svg = (
            "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" "
            "viewBox=\"0 0 100 100\" preserveAspectRatio=\"xMidYMid meet\">"
            f"<image href=\"data:image/png;base64,{png_b64}\" width=\"100\" height=\"100\" "
            "preserveAspectRatio=\"xMidYMid meet\"/></svg>"
        )
        return Response(
            content=svg,
            media_type="image/svg+xml",
            headers={
                "Content-Disposition": f'inline; filename="{run.workflow_name}.svg"'
            },
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to generate SVG diagram for thread {thread_id}")
        raise workflow_internal_error("Failed to generate workflow diagram")
