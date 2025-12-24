"""
Workflow Routes

API endpoints for workflow tools and execution.
Provides tools with port definitions for the visual node editor.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fichero.workflows.types import (
    ToolDef,
    PortDef,
    DataType,
    WorkflowDef,
    NodeDef,
    EdgeDef,
)
from fichero.workflows.registry import (
    list_tools,
    get_tool_def,
    list_tools_by_category,
    get_categories,
    create_node_from_tool,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================

class PortResponse(BaseModel):
    """Port definition for node editor."""
    id: str
    name: str
    port_type: str  # "input" or "output"
    data_type: str
    required: bool = True
    description: str = ""


class ToolResponse(BaseModel):
    """Tool definition with ports for node editor."""
    name: str
    display_name: str
    description: str
    category: str
    icon: str
    color: str
    input_ports: list[PortResponse]
    output_ports: list[PortResponse]
    config_schema: dict
    default_output_schema: dict | None
    uses_llm: bool
    supports_batch: bool
    supports_streaming: bool
    supports_structured_output: bool
    sort_order: int


class CategoryToolsResponse(BaseModel):
    """Tools grouped by category."""
    category: str
    display_name: str
    tools: list[ToolResponse]


class ToolListResponse(BaseModel):
    """All tools by category."""
    categories: list[CategoryToolsResponse]


class NodeResponse(BaseModel):
    """Node created from tool."""
    id: str
    tool: str
    label: str | None
    description: str | None
    input_ports: list[PortResponse]
    output_ports: list[PortResponse]
    position_x: float
    position_y: float


class WorkflowResponse(BaseModel):
    """Workflow definition response."""
    id: str
    name: str
    description: str
    provider: str
    model: str
    nodes: list[dict]
    edges: list[dict]


class WorkflowRunRequest(BaseModel):
    """Request to run a workflow."""
    inputs: dict[str, Any] = {}
    input_files: list[str] = []


class WorkflowRunResponse(BaseModel):
    """Result of running a workflow."""
    task_id: str
    workflow_id: str
    status: str
    completed_nodes: list[str]
    outputs: dict[str, Any]
    output_files: list[str]
    error: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================

def _port_to_response(port: PortDef) -> PortResponse:
    """Convert PortDef to API response."""
    return PortResponse(
        id=port.id,
        name=port.name,
        port_type=port.port_type,
        data_type=port.data_type.value if isinstance(port.data_type, DataType) else str(port.data_type),
        required=port.required,
        description=port.description,
    )


def _tool_to_response(tool: ToolDef) -> ToolResponse:
    """Convert ToolDef to API response."""
    return ToolResponse(
        name=tool.name,
        display_name=tool.display_name,
        description=tool.description,
        category=tool.category,
        icon=tool.icon,
        color=tool.color,
        input_ports=[_port_to_response(p) for p in tool.input_ports],
        output_ports=[_port_to_response(p) for p in tool.output_ports],
        config_schema=tool.config_schema,
        default_output_schema=tool.default_output_schema,
        uses_llm=tool.uses_llm,
        supports_batch=tool.supports_batch,
        supports_streaming=tool.supports_streaming,
        supports_structured_output=tool.supports_structured_output,
        sort_order=tool.sort_order,
    )


def _category_display_name(category: str) -> str:
    """Get display name for category."""
    names = {
        "source": "Sources",
        "vision": "Vision",
        "transform": "Transform",
        "llm": "LLM",
        "convert": "Convert",
        "logic": "Logic",
        "sink": "Outputs",
        "utility": "Utility",
    }
    return names.get(category, category.title())


# =============================================================================
# Tool Routes
# =============================================================================

@router.get("/tools")
async def list_workflow_tools() -> list[ToolResponse]:
    """List all available workflow tools with port definitions."""
    tools = list_tools()
    return [_tool_to_response(t) for t in tools]


@router.get("/tools/grouped")
async def list_tools_grouped() -> ToolListResponse:
    """List tools grouped by category for the node editor sidebar."""
    categories = get_categories()
    result = []

    for cat in categories:
        tools = list_tools_by_category(cat)
        if tools:
            result.append(CategoryToolsResponse(
                category=cat,
                display_name=_category_display_name(cat),
                tools=[_tool_to_response(t) for t in tools],
            ))

    return ToolListResponse(categories=result)


@router.get("/tools/{tool_name}")
async def get_tool(tool_name: str) -> ToolResponse:
    """Get details for a specific tool."""
    tool_def = get_tool_def(tool_name)
    if not tool_def:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

    return _tool_to_response(tool_def)


@router.post("/tools/{tool_name}/create-node")
async def create_node(
    tool_name: str,
    position_x: float = 0,
    position_y: float = 0,
) -> NodeResponse:
    """Create a new node instance from a tool.

    This generates a unique node ID and copies the tool's ports.
    """
    node = create_node_from_tool(tool_name, position_x, position_y)
    if not node:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

    return NodeResponse(
        id=node.id,
        tool=node.tool,
        label=node.label,
        description=node.description,
        input_ports=[_port_to_response(p) for p in node.input_ports],
        output_ports=[_port_to_response(p) for p in node.output_ports],
        position_x=node.position_x,
        position_y=node.position_y,
    )


# =============================================================================
# Workflow Execution Routes
# =============================================================================

@router.post("/run")
async def run_workflow_inline(
    workflow: WorkflowDef,
    request: WorkflowRunRequest,
) -> WorkflowRunResponse:
    """Run a workflow inline (doesn't save the workflow definition)."""
    try:
        # Import here to avoid circular imports
        from fichero.workflows import execute_workflow

        final_state = await execute_workflow(
            workflow=workflow,
            inputs=request.inputs,
            input_files=request.input_files,
        )

        return WorkflowRunResponse(
            task_id=final_state.get("task_id", ""),
            workflow_id=final_state.get("workflow_id", ""),
            status="completed" if not final_state.get("error") else "failed",
            completed_nodes=final_state.get("completed_nodes", []),
            outputs=final_state.get("outputs", {}),
            output_files=final_state.get("output_files", []),
            error=final_state.get("error"),
        )
    except Exception as e:
        logger.exception("Workflow execution failed")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Workflow CRUD
# =============================================================================

@router.post("")
async def create_workflow(workflow: WorkflowDef) -> WorkflowResponse:
    """Save a workflow definition."""
    # TODO: Store in database
    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        provider=workflow.provider,
        model=workflow.model,
        nodes=[n.model_dump() for n in workflow.nodes],
        edges=[e.model_dump() for e in workflow.edges],
    )


@router.get("")
async def list_workflows() -> list[WorkflowResponse]:
    """List saved workflows."""
    # TODO: Load from database
    return []


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str) -> WorkflowResponse:
    """Get a saved workflow."""
    # TODO: Load from database
    raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """Delete a saved workflow."""
    # TODO: Delete from database
    raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")


@router.post("/{workflow_id}/run")
async def run_saved_workflow(
    workflow_id: str,
    request: WorkflowRunRequest,
) -> WorkflowRunResponse:
    """Run a saved workflow."""
    # TODO: Load from database and run
    raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
