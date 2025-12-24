"""
Workflow Routes

API endpoints for workflow tools and execution.
Provides tools with port definitions for the visual node editor.
"""

import logging
from typing import Any, Optional
from datetime import datetime

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
    """Create and save a workflow definition."""
    try:
        # Import here to avoid circular imports
        from fichero.db import db
        from fichero.models import Workflow

        # Convert LangGraph workflow to database model
        db_workflow = Workflow(
            name=workflow.name,
            description=workflow.description or "",
            format="nodes",
            provider=workflow.provider or "",
            model=workflow.model or "",
            nodes=[node.model_dump() for node in workflow.nodes],
            edges=[edge.model_dump() for edge in workflow.edges],
        )

        # Save to database
        db.save(db_workflow)

        return WorkflowResponse(
            id=db_workflow.id,
            name=db_workflow.name,
            description=db_workflow.description,
            provider=db_workflow.provider,
            model=db_workflow.model,
            nodes=db_workflow.nodes,
            edges=db_workflow.edges,
        )
    except Exception as e:
        logger.exception("Failed to create workflow")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import")
async def import_workflow(
    name: str = "",
    description: str = "",
    workflow_data: dict = {}
) -> WorkflowResponse:
    """Import a workflow from JSON data."""
    try:
        from fichero.db import db
        from fichero.models import Workflow
        from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef, PortDef

        # Validate that workflow_data contains required structure
        if "nodes" not in workflow_data or "edges" not in workflow_data:
            raise HTTPException(status_code=400, detail="Invalid workflow data: missing nodes or edges")

        # Create a new workflow with provided data
        workflow_name = name or workflow_data.get("name", "Imported Workflow")
        workflow_description = description or workflow_data.get("description", "")
        workflow_provider = workflow_data.get("provider", "")
        workflow_model = workflow_data.get("model", "")

        db_workflow = Workflow(
            name=workflow_name,
            description=workflow_description,
            format="nodes",
            provider=workflow_provider,
            model=workflow_model,
            nodes=workflow_data.get("nodes", []),
            edges=workflow_data.get("edges", []),
        )

        # Save to database
        db.save(db_workflow)

        return WorkflowResponse(
            id=db_workflow.id,
            name=db_workflow.name,
            description=db_workflow.description,
            provider=db_workflow.provider,
            model=db_workflow.model,
            nodes=db_workflow.nodes,
            edges=db_workflow.edges,
        )
    except Exception as e:
        logger.exception("Failed to import workflow")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}/export")
async def export_workflow(workflow_id: str) -> dict:
    """Export a workflow as JSON data for sharing/importing."""
    try:
        from fichero.db import db
        from fichero.models import Workflow

        workflow = db.get(Workflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

        # Return the workflow data as JSON for export
        return {
            "id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
            "provider": workflow.provider,
            "model": workflow.model,
            "format": workflow.format,
            "nodes": workflow.nodes,
            "edges": workflow.edges,
            "exported_at": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to export workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_workflows(
    folder_path: str = "/"
) -> list[WorkflowResponse]:
    """List saved workflows, optionally filtered by folder."""
    try:
        from fichero.db import db
        from fichero.models import Workflow
        
        # Query workflows from database
        workflows = db.query(Workflow, folder_path=folder_path)
        
        return [
            WorkflowResponse(
                id=workflow.id,
                name=workflow.name,
                description=workflow.description,
                provider=workflow.provider,
                model=workflow.model,
                nodes=workflow.nodes,
                edges=workflow.edges,
            )
            for workflow in sorted(workflows, key=lambda w: w.sort_order)
        ]
    except Exception as e:
        logger.exception("Failed to list workflows")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str) -> WorkflowResponse:
    """Get a saved workflow by ID."""
    try:
        from fichero.db import db
        from fichero.models import Workflow
        
        workflow = db.get(Workflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
        
        return WorkflowResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            provider=workflow.provider,
            model=workflow.model,
            nodes=workflow.nodes,
            edges=workflow.edges,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    workflow: WorkflowDef,
) -> WorkflowResponse:
    """Update an existing workflow."""
    try:
        from fichero.db import db
        from fichero.models import Workflow
        
        # Get existing workflow
        existing = db.get(Workflow, workflow_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
        
        # Update fields
        existing.name = workflow.name
        existing.description = workflow.description or ""
        existing.format = "nodes"
        existing.provider = workflow.provider or ""
        existing.model = workflow.model or ""
        existing.nodes = [node.model_dump() for node in workflow.nodes]
        existing.edges = [edge.model_dump() for edge in workflow.edges]
        existing.updated_at = datetime.now()
        
        # Save changes
        db.save(existing)
        
        return WorkflowResponse(
            id=existing.id,
            name=existing.name,
            description=existing.description,
            provider=existing.provider,
            model=existing.model,
            nodes=existing.nodes,
            edges=existing.edges,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """Delete a saved workflow."""
    try:
        from fichero.db import db
        from fichero.models import Workflow

        workflow = db.get(Workflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

        # Delete from database
        db.delete(workflow)

        return {"message": f"Workflow {workflow_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/duplicate")
async def duplicate_workflow(workflow_id: str) -> WorkflowResponse:
    """Duplicate a workflow with a new ID and modified name."""
    try:
        from fichero.db import db
        from fichero.models import Workflow

        # Get the original workflow
        original = db.get(Workflow, workflow_id)
        if not original:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

        # Create a new workflow with same properties but new ID and modified name
        new_workflow = Workflow(
            name=f"{original.name} (Copy)",
            description=original.description,
            format=original.format,
            provider=original.provider,
            model=original.model,
            nodes=original.nodes,
            edges=original.edges,
            folder_path=original.folder_path,  # Keep in same folder
            sort_order=original.sort_order    # Preserve order preference
        )

        # Save to database (this will generate a new ID)
        db.save(new_workflow)

        return WorkflowResponse(
            id=new_workflow.id,
            name=new_workflow.name,
            description=new_workflow.description,
            provider=new_workflow.provider,
            model=new_workflow.model,
            nodes=new_workflow.nodes,
            edges=new_workflow.edges,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to duplicate workflow")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reorder")
async def reorder_workflows(workflow_ids: list[str], folder_path: str = "/") -> dict:
    """Reorder workflows within a folder."""
    try:
        from fichero.db import db
        from fichero.models import Workflow

        # Update sort_order for each workflow
        for i, workflow_id in enumerate(workflow_ids):
            workflow = db.get(Workflow, workflow_id)
            if not workflow:
                raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

            # Update sort order
            workflow.sort_order = i
            db.save(workflow)

        return {"status": "reordered", "count": len(workflow_ids)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to reorder workflows")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/run")
async def run_saved_workflow(
    workflow_id: str,
    request: WorkflowRunRequest,
) -> WorkflowRunResponse:
    """Run a saved workflow."""
    try:
        from fichero.db import db
        from fichero.models import Workflow
        
        # Load workflow from database
        db_workflow = db.get(Workflow, workflow_id)
        if not db_workflow:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
        
        # Convert to LangGraph format
        if db_workflow.format == "nodes":
            workflow_def = _convert_to_langgraph_format(db_workflow)
        else:
            # Convert legacy steps to LangGraph format
            workflow_def = _convert_steps_to_langgraph_format(db_workflow)
        
        # Import here to avoid circular imports
        from fichero.workflows import execute_workflow
        
        final_state = await execute_workflow(
            workflow=workflow_def,
            inputs=request.inputs,
            input_files=request.input_files,
        )
        
        return WorkflowRunResponse(
            task_id=final_state.get("task_id", ""),
            workflow_id=workflow_id,
            status="completed" if not final_state.get("error") else "failed",
            completed_nodes=final_state.get("completed_nodes", []),
            outputs=final_state.get("outputs", {}),
            output_files=final_state.get("output_files", []),
            error=final_state.get("error"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to run saved workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Helper Functions
# =============================================================================

def _convert_to_langgraph_format(db_workflow) -> WorkflowDef:
    """Convert database workflow to LangGraph WorkflowDef."""
    from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef, PortDef
    
    # Convert nodes
    nodes = []
    for node_dict in db_workflow.nodes:
        # Convert port dicts to PortDef objects
        input_ports = [PortDef(**port) for port in node_dict.get("input_ports", [])]
        output_ports = [PortDef(**port) for port in node_dict.get("output_ports", [])]
        
        node = NodeDef(
            id=node_dict["id"],
            tool=node_dict["tool"],
            label=node_dict.get("label"),
            description=node_dict.get("description"),
            input_ports=input_ports,
            output_ports=output_ports,
            position_x=node_dict.get("position_x", 0),
            position_y=node_dict.get("position_y", 0),
            enabled=node_dict.get("enabled", True),
            input_mappings=node_dict.get("input_mappings", []),
        )
        nodes.append(node)
    
    # Convert edges
    edges = []
    for edge_dict in db_workflow.edges:
        edge = EdgeDef(
            source=edge_dict["source"],
            target=edge_dict["target"],
            source_port=edge_dict.get("source_port", "output"),
            target_port=edge_dict.get("target_port", "input"),
            condition=edge_dict.get("condition"),
            label=edge_dict.get("label"),
        )
        edges.append(edge)
    
    return WorkflowDef(
        id=db_workflow.id,
        name=db_workflow.name,
        description=db_workflow.description,
        provider=db_workflow.provider,
        model=db_workflow.model,
        nodes=nodes,
        edges=edges,
    )


def _convert_steps_to_langgraph_format(db_workflow) -> WorkflowDef:
    """Convert legacy steps to LangGraph WorkflowDef."""
    from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef
    from fichero.workflows.registry import create_node_from_tool
    
    # Create nodes from steps
    nodes = []
    edges = []
    previous_node_id = None
    
    for i, step in enumerate(db_workflow.steps):
        tool_name = step["tool"]
        position_x = 150 + (i * 200)
        position_y = 200
        
        # Create node from tool
        node = create_node_from_tool(tool_name, position_x, position_y)
        if node:
            # Override with step-specific settings
            node.label = step.get("name", node.label)
            
            nodes.append(node)
            
            # Create edge from previous node
            if previous_node_id:
                edges.append(EdgeDef(
                    source=previous_node_id,
                    target=node.id,
                    source_port="output",
                    target_port="input",
                ))
            
            previous_node_id = node.id
    
    return WorkflowDef(
        id=db_workflow.id,
        name=db_workflow.name,
        description=db_workflow.description,
        provider=db_workflow.provider,
        model=db_workflow.model,
        nodes=nodes,
        edges=edges,
    )
