"""Workflow visualization and Python code export routes."""

import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from fichero.db import Database
from fichero.api.main import get_library_database
from fichero.workflows.workflow_store import WorkflowStore
# NOTE: runtime.to_workflow_def is imported at CALL time, not here (#3950):
# runtime -> builder -> langgraph + every tool. build_graph below was
# already deferred this way.

from .runner import _generate_workflow_python_code
from .schemas import workflow_internal_error

logger = logging.getLogger(__name__)
# Passthrough wrappers (#3950).
#
# Deferring these imports must not remove them as MODULE ATTRIBUTES: tests
# patch `fichero.api.routes.workflow_execution.visualization.<name>`, which needs (1) the attribute to exist for mock.patch,
# and (2) the call site to resolve it as a module GLOBAL so the patch takes
# effect. A function-local import satisfies neither and would let those tests
# pass while silently running the real implementation.


def to_workflow_def(*args, **kwargs):
    """Passthrough to fichero.workflows.runtime.to_workflow_def; imports it on first call (#3950)."""
    from fichero.workflows.runtime import to_workflow_def as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


router = APIRouter()


# =============================================================================
# Models
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


# =============================================================================
# Endpoints
# =============================================================================


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
                status_code=404, detail=f"Workflow not found: {workflow_id}"
            )

        workflow_def = to_workflow_def(workflow)

        # Build compiled graph
        from fichero.workflows.builder import build_graph  # noqa: PLC0415
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
    except Exception:
        logger.exception(f"Failed to generate visualization for workflow {workflow_id}")
        raise workflow_internal_error("Failed to generate workflow visualization")


# /workflows/{workflow_id}/visualization.png lied about its content type —
# it returned the SAME JSON Mermaid payload as /visualization, never a PNG.
# Deleted in the endpoint cleanup (2026-07-27); the thread-level
# /threads/{thread_id}/diagram.png endpoint genuinely renders PNG.


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
                status_code=404, detail=f"Workflow not found: {workflow_id}"
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
    except Exception:
        logger.exception(f"Failed to export code for workflow {workflow_id}")
        raise workflow_internal_error("Failed to export workflow code")
