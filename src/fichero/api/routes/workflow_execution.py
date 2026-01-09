"""
Workflow Execution Routes

API endpoints for executing workflows with LangGraph checkpointing.
Enables durable execution, pause/resume, and thread management.
"""

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from fichero.db import Database
from fichero.api.main import get_library_database
from fichero.models import Workflow
from fichero.workflows.checkpointer import AsyncDuckDBCheckpointer
from fichero.workflows.workflow_store import WorkflowStore

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


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/execute")
async def execute_workflow(
    request: ExecuteWorkflowRequest,
    db: Database = Depends(get_library_database),
) -> ExecutionStatusResponse:
    """
    Execute a workflow with checkpointing.

    This endpoint starts workflow execution with full state persistence.
    The workflow can be paused, resumed, and survives server restarts.

    Args:
        request: Execution parameters including workflow_id and inputs

    Returns:
        Execution status with thread_id for tracking

    Raises:
        404: Workflow not found
        500: Execution error
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

        # Generate thread ID if not provided
        thread_id = request.thread_id or f"thread-{uuid4().hex[:12]}"

        # Get checkpointer
        checkpointer = AsyncDuckDBCheckpointer.from_db_path(db.path)

        # Build LangGraph workflow with checkpointing
        app = _build_workflow_with_checkpointer(
            workflow,
            checkpointer,
            interrupt_before=request.interrupt_before,
            interrupt_after=request.interrupt_after,
        )

        # Execute workflow
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": request.checkpoint_ns,
            }
        }

        try:
            final_state = await app.ainvoke(request.inputs, config=config)

            # Get latest checkpoint to determine status
            checkpoint_tuple = await checkpointer.aget_tuple(config)

            return ExecutionStatusResponse(
                thread_id=thread_id,
                workflow_id=request.workflow_id,
                workflow_name=workflow.name,
                status="completed",
                checkpoint_id=checkpoint_tuple.checkpoint["id"] if checkpoint_tuple else None,
                current_state=final_state,
                error=None,
            )

        except Exception as e:
            # Execution interrupted (paused at interrupt point)
            checkpoint_tuple = await checkpointer.aget_tuple(config)

            if "interrupt" in str(e).lower() or checkpoint_tuple:
                # Workflow paused successfully
                return ExecutionStatusResponse(
                    thread_id=thread_id,
                    workflow_id=request.workflow_id,
                    workflow_name=workflow.name,
                    status="paused",
                    checkpoint_id=checkpoint_tuple.checkpoint["id"] if checkpoint_tuple else None,
                    current_state=checkpoint_tuple.checkpoint.get("channel_values") if checkpoint_tuple else None,
                    error=None,
                )
            else:
                # Actual error
                raise

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to execute workflow {request.workflow_id}")
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

        status = "paused" if has_pending_writes else "completed"

        return ExecutionStatusResponse(
            thread_id=thread_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            status=status,
            checkpoint_id=checkpoint_tuple.checkpoint["id"],
            current_state=current_state,
            error=None,
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
):
    """
    Build a LangGraph workflow with checkpointing enabled.

    Args:
        workflow: Workflow database model
        checkpointer: AsyncDuckDBCheckpointer instance
        interrupt_before: Optional list of node IDs to pause before
        interrupt_after: Optional list of node IDs to pause after

    Returns:
        Compiled LangGraph application with checkpointing
    """
    from langgraph.graph import StateGraph
    from fichero.workflows.types import State, NodeDef
    from fichero.workflows.registry import get_tool
    from fichero.workflows.builder import _make_node_function
    from fichero.llm import LLMConfig

    # Create state graph
    graph = StateGraph(State)

    # Build LLM config
    llm_config = LLMConfig(provider=workflow.provider, model=workflow.model)
    workflow_config = {"provider": workflow.provider, "model": workflow.model}

    # Add nodes
    for node_dict in workflow.nodes:
        tool_fn = get_tool(node_dict["tool"])
        if not tool_fn:
            raise ValueError(f"Unknown tool: {node_dict['tool']}")

        # Create NodeDef
        node_def = NodeDef(
            id=node_dict["id"],
            tool=node_dict["tool"],
            label=node_dict.get("label"),
            inputs=node_dict.get("inputs", {}),
            config=node_dict.get("config", {}),
        )

        node_fn = _make_node_function(node_def, tool_fn, llm_config, workflow_config)
        graph.add_node(node_dict["id"], node_fn)

    # Add edges
    for edge_dict in workflow.edges:
        source = edge_dict.get("source") or edge_dict.get("source_node_id")
        target = edge_dict.get("target") or edge_dict.get("target_node_id")

        if source and target:
            graph.add_edge(source, target)

    # Compile with checkpointer
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
    )
