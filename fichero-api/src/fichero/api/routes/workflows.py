"""
Workflow Routes

API endpoints for workflow tools and execution.
Provides tools with port definitions for the visual node editor.
"""

import logging
from typing import Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from fichero.db import Database
from fichero.api.main import get_library_database
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
    enrich_node_with_ports,
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
    default: Any = None  # Default value for optional inputs


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
    config_schema: dict = {}
    config_defaults: dict = {}  # Default config values for new nodes
    default_output_schema: dict = {}
    default_prompt: str = ""  # Default prompt for LLM tools (shown in UI, empty if none)
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
    label: str = ""
    description: str = ""
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
    nodes: list[NodeDef]
    edges: list[EdgeDef]
    folder_path: str
    sort_order: int


# =============================================================================
# Helper Functions
# =============================================================================

def _dict_to_node_def(node_dict: dict, enrich_ports: bool = True) -> NodeDef:
    """Convert a node dict from database to NodeDef.

    Args:
        node_dict: Node data from database
        enrich_ports: If True, populate ports from tool registry (default).
                      Set to False if you need the raw stored data.

    Returns:
        NodeDef with ports populated from registry (if enrich_ports=True)
    """
    from fichero.workflows.types import PortDef, InputMapping, OutputSchema

    # Convert input_mappings to InputMapping objects
    input_mappings = [InputMapping(**m) for m in node_dict.get("input_mappings", [])]

    # Convert output_schema if present
    output_schema = None
    if node_dict.get("output_schema"):
        output_schema = OutputSchema(**node_dict["output_schema"])

    # Create node without ports initially (ports come from registry)
    node = NodeDef(
        id=node_dict.get("id", ""),
        tool=node_dict.get("tool", ""),
        label=node_dict.get("label"),
        description=node_dict.get("description"),
        input_ports=[],  # Will be enriched from registry
        output_ports=[],  # Will be enriched from registry
        input_mappings=input_mappings,
        inputs=node_dict.get("inputs"),
        config=node_dict.get("config"),
        output_schema=output_schema,
        position_x=node_dict.get("position_x", 0),
        position_y=node_dict.get("position_y", 0),
        enabled=node_dict.get("enabled", True),
        provider_name=node_dict.get("provider_name"),
        model_name=node_dict.get("model_name"),
        uses_llm=node_dict.get("uses_llm", False),
    )

    # Enrich with ports from tool registry
    if enrich_ports:
        node = enrich_node_with_ports(node)

    return node


def _dict_to_edge_def(edge_dict: dict) -> EdgeDef:
    """Convert an edge dict from database to EdgeDef."""
    return EdgeDef(
        id=edge_dict.get("id", ""),
        source=edge_dict.get("source", ""),
        target=edge_dict.get("target", ""),
        source_port=edge_dict.get("source_port", "output"),
        target_port=edge_dict.get("target_port", "input"),
        condition=edge_dict.get("condition"),
        label=edge_dict.get("label"),
        animated=edge_dict.get("animated", False),
    )


def _port_to_response(port: PortDef) -> PortResponse:
    """Convert PortDef to API response."""
    return PortResponse(
        id=port.id,
        name=port.name,
        port_type=port.port_type,
        data_type=port.data_type.value if isinstance(port.data_type, DataType) else str(port.data_type),
        required=port.required,
        description=port.description,
        default=port.default,
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
        config_schema=tool.config_schema or {},
        config_defaults=tool.config_defaults or {},
        default_output_schema=tool.default_output_schema or {},
        default_prompt=tool.default_prompt or "",
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


class PromptRequest(BaseModel):
    """Request to build a prompt with specific config."""
    config: dict = {}


class PromptResponse(BaseModel):
    """Response with built prompt."""
    prompt: str = ""  # Empty string if no prompt


@router.post("/tools/{tool_name}/prompt")
async def get_tool_prompt(tool_name: str, request: PromptRequest) -> PromptResponse:
    """Get the default prompt for a tool, optionally customized by config.

    This allows the UI to show users what prompt will be sent to the LLM
    based on their current configuration settings.
    """
    tool_def = get_tool_def(tool_name)
    if not tool_def:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

    # Use the tool's prompt builder if available, otherwise return default
    prompt = tool_def.get_prompt(request.config)
    return PromptResponse(prompt=prompt)


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
# Workflow CRUD
# =============================================================================

@router.post("")
async def create_workflow(
    workflow: WorkflowDef,
    db: Database = Depends(get_library_database),
) -> WorkflowResponse:
    """Create and save a workflow definition."""
    try:
        from fichero.models import Workflow

        # Convert LangGraph workflow to database model
        # Use model_dump_for_storage() to exclude ports (they come from registry)
        db_workflow = Workflow(
            name=workflow.name,
            description=workflow.description or "",
            format="nodes",
            provider=workflow.provider or "",
            model=workflow.model or "",
            nodes=[node.model_dump_for_storage() for node in workflow.nodes],
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
            nodes=[_dict_to_node_def(n) for n in db_workflow.nodes],
            edges=[_dict_to_edge_def(e) for e in db_workflow.edges],
            folder_path=db_workflow.folder_path,
            sort_order=db_workflow.sort_order,
        )
    except Exception as e:
        logger.exception("Failed to create workflow")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import")
async def import_workflow(
    name: str = "",
    description: str = "",
    workflow_data: dict = {},
    db: Database = Depends(get_library_database),
) -> WorkflowResponse:
    """Import a workflow from JSON data."""
    try:
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
            nodes=[_dict_to_node_def(n) for n in db_workflow.nodes],
            edges=[_dict_to_edge_def(e) for e in db_workflow.edges],
            folder_path=db_workflow.folder_path,
            sort_order=db_workflow.sort_order,
        )
    except Exception as e:
        logger.exception("Failed to import workflow")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}/export")
async def export_workflow(
    workflow_id: str,
    db: Database = Depends(get_library_database),
) -> dict:
    """Export a workflow as JSON data for sharing/importing."""
    try:
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
    folder_path: str = "/",
    db: Database = Depends(get_library_database),
) -> list[WorkflowResponse]:
    """List saved workflows, optionally filtered by folder."""
    try:
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
                nodes=[_dict_to_node_def(n) for n in workflow.nodes],
                edges=[_dict_to_edge_def(e) for e in workflow.edges],
                folder_path=workflow.folder_path,
                sort_order=workflow.sort_order,
            )
            for workflow in sorted(workflows, key=lambda w: w.sort_order)
        ]
    except Exception as e:
        logger.exception("Failed to list workflows")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    db: Database = Depends(get_library_database),
) -> WorkflowResponse:
    """Get a saved workflow by ID."""
    try:
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
            nodes=[_dict_to_node_def(n) for n in workflow.nodes],
            edges=[_dict_to_edge_def(e) for e in workflow.edges],
            folder_path=workflow.folder_path,
            sort_order=workflow.sort_order,
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
    db: Database = Depends(get_library_database),
) -> WorkflowResponse:
    """Update an existing workflow."""
    try:
        from fichero.models import Workflow

        # Debug: log what's being received and saved
        print(f"[UPDATE] workflow: id={workflow_id}")
        print(f"[UPDATE]   received nodes: {len(workflow.nodes)}, edges: {len(workflow.edges)}")
        for node in workflow.nodes[:3]:  # Log first 3 nodes
            print(f"[UPDATE]   node: tool={node.tool}, id={node.id[:8]}...")

        # Get existing workflow
        existing = db.get(Workflow, workflow_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
        
        # Update fields
        # Use model_dump_for_storage() to exclude ports (they come from registry)
        existing.name = workflow.name
        existing.description = workflow.description or ""
        existing.format = "nodes"
        existing.provider = workflow.provider or ""
        existing.model = workflow.model or ""
        existing.nodes = [node.model_dump_for_storage() for node in workflow.nodes]
        existing.edges = [edge.model_dump() for edge in workflow.edges]
        existing.updated_at = datetime.now()
        
        # Save changes
        db.save(existing)

        # Debug: verify what was saved
        print(f"[UPDATE]   saved nodes: {len(existing.nodes)}, edges: {len(existing.edges)}")

        return WorkflowResponse(
            id=existing.id,
            name=existing.name,
            description=existing.description,
            provider=existing.provider,
            model=existing.model,
            nodes=[_dict_to_node_def(n) for n in existing.nodes],
            edges=[_dict_to_edge_def(e) for e in existing.edges],
            folder_path=existing.folder_path,
            sort_order=existing.sort_order,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


class WorkflowPatchRequest(BaseModel):
    """Request for partial workflow update.

    All fields are optional strings - send only the fields you want to update.
    """
    name: Optional[str] = None
    description: Optional[str] = None
    folder_path: Optional[str] = None
    sort_order: Optional[int] = None

    model_config = {"extra": "allow"}


@router.patch("/{workflow_id}")
async def patch_workflow(
    workflow_id: str,
    patch: WorkflowPatchRequest,
    db: Database = Depends(get_library_database),
) -> WorkflowResponse:
    """Partially update a workflow (rename, move to folder, etc.)."""
    try:
        from fichero.models import Workflow

        workflow = db.get(Workflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

        # Apply only the fields that were provided
        if patch.name is not None:
            workflow.name = patch.name
        if patch.description is not None:
            workflow.description = patch.description
        if patch.folder_path is not None:
            workflow.folder_path = patch.folder_path
        if patch.sort_order is not None:
            workflow.sort_order = patch.sort_order

        workflow.updated_at = datetime.now()
        db.save(workflow)

        return WorkflowResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            provider=workflow.provider,
            model=workflow.model,
            nodes=[_dict_to_node_def(n) for n in workflow.nodes],
            edges=[_dict_to_edge_def(e) for e in workflow.edges],
            folder_path=workflow.folder_path,
            sort_order=workflow.sort_order,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to patch workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    db: Database = Depends(get_library_database),
):
    """Delete a saved workflow."""
    try:
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
async def duplicate_workflow(
    workflow_id: str,
    db: Database = Depends(get_library_database),
) -> WorkflowResponse:
    """Duplicate a workflow with a new ID and modified name."""
    try:
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
            nodes=[_dict_to_node_def(n) for n in new_workflow.nodes],
            edges=[_dict_to_edge_def(e) for e in new_workflow.edges],
            folder_path=new_workflow.folder_path,
            sort_order=new_workflow.sort_order,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to duplicate workflow")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reorder")
async def reorder_workflows(
    workflow_ids: list[str],
    folder_path: str = "/",
    db: Database = Depends(get_library_database),
) -> dict:
    """Reorder workflows within a folder."""
    try:
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


