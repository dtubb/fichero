"""
Workflow Routes

API endpoints for workflow tools and execution.
Provides tools with port definitions for the visual node editor.
"""

import logging
from typing import Any, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero.app_db import get_app_db
from fichero.db import Database
from fichero.api.library_header import require_library_path
from fichero.api.auth import request_actor
from fichero.api.change_stream import emit_change
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.llm import get_model_cost
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
from fichero.models import ReinstallDefaultWorkflowsResponse

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
    default_prompt: str = (
        ""  # Default prompt for LLM tools (shown in UI, empty if none)
    )
    uses_llm: bool
    supports_batch: bool
    supports_streaming: bool
    supports_structured_output: bool
    sort_order: int
    tested: bool = False  # False = UNTESTED; only the HTR chain is tested today


class CategoryToolsResponse(BaseModel):
    """Tools grouped by category."""

    category: str
    display_name: str
    tools: list[ToolResponse]


class ToolListResponse(BaseModel):
    """All tools by category (standardized {items, count} envelope; items
    are per-category groups)."""

    items: list[CategoryToolsResponse]
    count: int


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
    format: str
    nodes: list[NodeDef]
    edges: list[EdgeDef]
    folder_path: str
    sort_order: int
    # True = shipped preset that has NOT been validated end-to-end. The UI
    # appends "(Untested)" to the name. A preset is trusted only when its JSON
    # config carries `"tested": true` (today: only "Transcribe HTR"). User
    # workflows (is_system=False) are never flagged.
    untested: bool = False


def _workflow_untested(wf) -> bool:
    """A shipped preset is untested unless its config opts in with tested=true.

    Tied to the preset definition, not the node tools: several presets reuse
    the same validated HTR tools yet are not themselves validated workflows.
    """
    return bool(getattr(wf, "is_system", False)) and not bool(
        (getattr(wf, "config", None) or {}).get("tested", False)
    )


class WorkflowListResponse(BaseModel):
    """Standardized {items, count} envelope for GET /api/workflows."""

    items: list[WorkflowResponse]
    count: int


class WorkflowToolListResponse(BaseModel):
    """Standardized {items, count} envelope for GET /api/workflows/tools."""

    items: list[ToolResponse]
    count: int


class WorkflowModeResponse(BaseModel):
    id: str
    label: str
    description: str


class WorkflowModeListResponse(BaseModel):
    items: list[WorkflowModeResponse]
    count: int


class WorkflowCostEstimateRequest(BaseModel):
    """Inputs for pre-run workflow cost estimation."""

    file_count: int = 1
    estimated_input_tokens_per_file: int = 1200
    estimated_output_tokens_per_file: int = 300
    provider: str | None = None
    model: str | None = None


class WorkflowCostEstimateResponse(BaseModel):
    """Estimated run cost for the workflow execute button."""

    workflow_id: str
    provider: str
    model: str
    file_count: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_total_tokens: int
    estimated_cost_usd: float
    input_cost_per_million: float
    output_cost_per_million: float
    pricing_available: bool


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
    from fichero.workflows.types import InputMapping, OutputSchema

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
    """Convert a persisted edge dict to a typed EdgeDef.

    Delegates to ``EdgeDef.model_validate`` so the single typed boundary owns
    deserialization: it normalizes the ``source_port``/``source_port_id`` (and
    ``source``/``source_node_id``) drift and preserves conditional-routing
    fields (``condition``/``route_key``/``route_map``) that an explicit
    field-by-field copy previously dropped (#2537).
    """
    return EdgeDef.model_validate(edge_dict)


def _port_to_response(port: PortDef) -> PortResponse:
    """Convert PortDef to API response."""
    return PortResponse(
        id=port.id,
        name=port.name,
        port_type=port.port_type,
        data_type=port.data_type.value
        if isinstance(port.data_type, DataType)
        else str(port.data_type),
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
        tested=tool.tested,
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


def _model_pricing_per_million(provider: str, model: str) -> tuple[float, float]:
    """Resolve (input_cost, output_cost) per million tokens."""
    if not provider or not model:
        return 0.0, 0.0

    app_db = get_app_db()
    provider_id = None
    for item in app_db.list_providers():
        if item.provider_type.value == provider:
            provider_id = item.id
            break

    if provider_id:
        for item in app_db.list_models(provider_id=provider_id):
            if item.model_id == model:
                return float(item.input_cost or 0.0), float(item.output_cost or 0.0)

    # Fallback: LiteLLM pricing map (per-token), converted to per-million.
    cost_info = get_model_cost(f"{provider}/{model}") or get_model_cost(model)
    if cost_info:
        return (
            float(cost_info.get("input_cost_per_token") or 0.0) * 1_000_000,
            float(cost_info.get("output_cost_per_token") or 0.0) * 1_000_000,
        )
    return 0.0, 0.0


# =============================================================================
# Tool Routes
# =============================================================================


@router.get("/tools", response_model=WorkflowToolListResponse)
async def list_workflow_tools() -> WorkflowToolListResponse:
    """List all available workflow tools with port definitions."""
    tools = list_tools()
    items = [_tool_to_response(t) for t in tools]
    return WorkflowToolListResponse(items=items, count=len(items))


@router.get("/tools/grouped")
async def list_tools_grouped() -> ToolListResponse:
    """List tools grouped by category for the node editor sidebar."""
    categories = get_categories()
    result = []

    for cat in categories:
        tools = list_tools_by_category(cat)
        if tools:
            result.append(
                CategoryToolsResponse(
                    category=cat,
                    display_name=_category_display_name(cat),
                    tools=[_tool_to_response(t) for t in tools],
                )
            )

    return ToolListResponse(items=result, count=len(result))


@router.get("/tools/{tool_name}")
async def get_tool(tool_name: str) -> ToolResponse:
    """Get details for a specific tool."""
    tool_def = get_tool_def(tool_name)
    if not tool_def:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

    return _tool_to_response(tool_def)


@router.get("/modes", response_model=WorkflowModeListResponse)
async def list_workflow_modes() -> WorkflowModeListResponse:
    """List supported workflow editor display modes."""
    items = [
        WorkflowModeResponse(
            id="icon",
            label="Icon",
            description="Visual canvas editor for workflow nodes and edges.",
        ),
        WorkflowModeResponse(
            id="list",
            label="List",
            description="Linear list of workflow nodes and their wiring.",
        ),
        WorkflowModeResponse(
            id="table",
            label="Table",
            description="Structured table view of node configuration values.",
        ),
    ]
    return WorkflowModeListResponse(items=items, count=len(items))


class PromptRequest(BaseModel):
    """Request to build a prompt with specific config."""

    config: dict = {}


class PromptResponse(BaseModel):
    """Response with built prompt."""

    prompt: str = ""  # Empty string if no prompt


class WorkflowExportResponse(BaseModel):
    id: str
    name: str
    description: str
    provider: str
    model: str
    format: str
    nodes: list
    edges: list
    exported_at: str


class WorkflowDeletedResponse(BaseModel):
    message: str


class WorkflowReorderResponse(BaseModel):
    status: str
    count: int


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
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> NodeResponse:
    """Create a new node instance from a tool.

    This generates a unique node ID and copies the tool's ports.
    """
    node = create_node_from_tool(tool_name, position_x, position_y)
    if not node:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

    emit_change(
        x_fichero_library_path,
        type="workflow.updated",
        actor=actor,
        run_id=None,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )

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


def create_workflow_impl(db: Database, workflow: WorkflowDef) -> "Workflow":  # noqa: F821
    """Build + persist a node-based workflow from a WorkflowDef (the proven
    create logic, extracted verbatim from the ``POST /api/workflows`` route).

    Both the route and the ``workflow.create`` action (EPIC #1848) drive this
    same code — iterate-not-replace: the algorithm is wrapped, never re-derived.
    Uses ``model_dump_for_storage()`` so ports (registry-owned) are not persisted.
    """
    from fichero.models import Workflow

    db_workflow = Workflow(
        name=workflow.name,
        description=workflow.description or "",
        format="nodes",
        provider=workflow.provider or "",
        model=workflow.model or "",
        nodes=[node.model_dump_for_storage() for node in workflow.nodes],
        edges=[edge.model_dump() for edge in workflow.edges],
    )
    db.save(db_workflow)
    return db_workflow


@router.post("")
async def create_workflow(
    workflow: WorkflowDef,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> WorkflowResponse:
    """Create and save a workflow definition."""
    try:
        db_workflow = create_workflow_impl(db, workflow)

        emit_change(
            x_fichero_library_path,
            type="workflow.created",
            actor=actor,
            run_id=None,
            origin_window=x_fichero_origin_window,
            origin_user=actor,
        )

        return WorkflowResponse(
            id=db_workflow.id,
            name=db_workflow.name,
            description=db_workflow.description,
            provider=db_workflow.provider,
            model=db_workflow.model,
            format=db_workflow.format,
            nodes=[_dict_to_node_def(n) for n in db_workflow.nodes],
            edges=[_dict_to_edge_def(e) for e in db_workflow.edges],
            folder_path=db_workflow.folder_path,
            sort_order=db_workflow.sort_order,
            untested=_workflow_untested(db_workflow),
        )
    except Exception as e:
        logger.exception("Failed to create workflow")
        raise HTTPException(status_code=500, detail=str(e))


def import_workflow_impl(
    db: Database, name: str, description: str, workflow_data: dict
) -> "Workflow":  # noqa: F821
    """Validate + persist a workflow from imported JSON (extracted from the
    ``POST /api/workflows/import`` route so the route and the
    ``workflow.import`` action share one implementation).

    Parity with export (#2528): every node/edge is validated against the typed
    NodeDef/EdgeDef models *before* anything is persisted, so a malformed file
    fails loud (HTTP 400) with the offending element — never a silent partial
    import. Export emits the raw stored dicts, so we persist those same dicts
    once they validate (export→import round-trips to an identical graph)."""
    from fichero.models import Workflow

    if "nodes" not in workflow_data or "edges" not in workflow_data:
        raise HTTPException(
            status_code=400, detail="Invalid workflow data: missing nodes or edges"
        )

    nodes = workflow_data.get("nodes", [])
    edges = workflow_data.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise HTTPException(
            status_code=400,
            detail="Invalid workflow data: 'nodes' and 'edges' must be lists",
        )

    # Validate against the typed models up front — fail loud, persist nothing
    # on a bad element (no silent partial import). enrich_ports=False keeps
    # validation to structure, independent of the live tool registry so a
    # round-tripped export validates regardless of registry state.
    for i, node in enumerate(nodes):
        try:
            _dict_to_node_def(node, enrich_ports=False)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid workflow data: node[{i}] failed validation: {exc}",
            )
    for i, edge in enumerate(edges):
        try:
            _dict_to_edge_def(edge)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid workflow data: edge[{i}] failed validation: {exc}",
            )

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
        nodes=nodes,
        edges=edges,
    )
    db.save(db_workflow)
    return db_workflow


@router.post("/import")
async def import_workflow(
    name: str = "",
    description: str = "",
    workflow_data: dict = {},
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> WorkflowResponse:
    """Import a workflow from JSON data."""
    try:
        db_workflow = import_workflow_impl(db, name, description, workflow_data)

        emit_change(
            x_fichero_library_path,
            type="workflow.created",
            actor=actor,
            run_id=None,
            origin_window=x_fichero_origin_window,
            origin_user=actor,
        )

        return WorkflowResponse(
            id=db_workflow.id,
            name=db_workflow.name,
            description=db_workflow.description,
            provider=db_workflow.provider,
            model=db_workflow.model,
            format=db_workflow.format,
            nodes=[_dict_to_node_def(n) for n in db_workflow.nodes],
            edges=[_dict_to_edge_def(e) for e in db_workflow.edges],
            folder_path=db_workflow.folder_path,
            sort_order=db_workflow.sort_order,
            untested=_workflow_untested(db_workflow),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to import workflow")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}/export")
async def export_workflow(
    workflow_id: str,
    db: Database = Depends(get_library_database),
) -> WorkflowExportResponse:
    """Export a workflow as JSON data for sharing/importing."""
    try:
        from fichero.models import Workflow

        workflow = db.get(Workflow, workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404, detail=f"Workflow not found: {workflow_id}"
            )

        # Return the workflow data as JSON for export
        return WorkflowExportResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            provider=workflow.provider,
            model=workflow.model,
            format=workflow.format,
            nodes=workflow.nodes,
            edges=workflow.edges,
            exported_at=datetime.now().isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to export workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/reinstall-defaults",
    response_model=ReinstallDefaultWorkflowsResponse,
)
async def reinstall_default_workflows(
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ReinstallDefaultWorkflowsResponse:
    """Delete and re-seed the bundled default workflows (Transcribe, Catalogue).

    Used when we ship a new preset version (new nodes, fixed edge schema, etc.)
    and want users to pick it up without manually deleting their old copies.
    Only workflows with is_template=True are touched — user-duplicated or
    renamed workflows are untouched even if the name happens to match.
    """
    from fichero.workflows.default_workflows import seed_default_workflows

    try:
        seeded = seed_default_workflows(db, force=True)

        emit_change(
            x_fichero_library_path,
            type="workflow.created",
            actor=actor,
            run_id=None,
            origin_window=x_fichero_origin_window,
            origin_user=actor,
        )
        return ReinstallDefaultWorkflowsResponse(seeded=seeded, status="ok")
    except Exception as exc:
        logger.exception("Failed to reinstall default workflows")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    folder_path: str | None = None,
    db: Database = Depends(get_library_database),
) -> WorkflowListResponse:
    """List saved workflows, optionally filtered by folder.

    When ``folder_path`` is omitted, all workflows are returned regardless
    of folder. Pass an explicit value (e.g. "/Catalogue") to filter.
    """
    try:
        from fichero.models import Workflow

        if folder_path is None:
            workflows = db.all(Workflow)
        else:
            workflows = db.query(Workflow, folder_path=folder_path)

        items = [
            WorkflowResponse(
                id=workflow.id,
                name=workflow.name,
                description=workflow.description,
                provider=workflow.provider,
                model=workflow.model,
                format=workflow.format,
                nodes=[_dict_to_node_def(n) for n in workflow.nodes],
                edges=[_dict_to_edge_def(e) for e in workflow.edges],
                folder_path=workflow.folder_path,
                sort_order=workflow.sort_order,
                untested=_workflow_untested(workflow),
            )
            for workflow in sorted(workflows, key=lambda w: w.sort_order)
        ]
        return WorkflowListResponse(items=items, count=len(items))
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
            raise HTTPException(
                status_code=404, detail=f"Workflow not found: {workflow_id}"
            )

        return WorkflowResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            provider=workflow.provider,
            model=workflow.model,
            format=workflow.format,
            nodes=[_dict_to_node_def(n) for n in workflow.nodes],
            edges=[_dict_to_edge_def(e) for e in workflow.edges],
            folder_path=workflow.folder_path,
            sort_order=workflow.sort_order,
            untested=_workflow_untested(workflow),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{workflow_id}/estimate-cost", response_model=WorkflowCostEstimateResponse
)
async def estimate_workflow_cost(
    workflow_id: str,
    request: WorkflowCostEstimateRequest,
    db: Database = Depends(get_library_database),
) -> WorkflowCostEstimateResponse:
    """Estimate run cost from file count and per-file token assumptions."""
    from fichero.models import Workflow

    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=404, detail=f"Workflow not found: {workflow_id}"
        )

    file_count = max(1, int(request.file_count))
    input_tokens_per_file = max(1, int(request.estimated_input_tokens_per_file))
    output_tokens_per_file = max(1, int(request.estimated_output_tokens_per_file))

    provider = (request.provider or workflow.provider or "").strip()
    model = (request.model or workflow.model or "").strip()
    input_cost_per_million, output_cost_per_million = _model_pricing_per_million(
        provider, model
    )

    estimated_input_tokens = file_count * input_tokens_per_file
    estimated_output_tokens = file_count * output_tokens_per_file
    estimated_cost_usd = estimated_input_tokens * (
        input_cost_per_million / 1_000_000
    ) + estimated_output_tokens * (output_cost_per_million / 1_000_000)

    return WorkflowCostEstimateResponse(
        workflow_id=workflow_id,
        provider=provider,
        model=model,
        file_count=file_count,
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        estimated_total_tokens=estimated_input_tokens + estimated_output_tokens,
        estimated_cost_usd=estimated_cost_usd,
        input_cost_per_million=input_cost_per_million,
        output_cost_per_million=output_cost_per_million,
        pricing_available=(input_cost_per_million > 0 or output_cost_per_million > 0),
    )


def update_workflow_impl(
    db: Database, workflow_id: str, workflow: WorkflowDef
) -> "Workflow":  # noqa: F821
    """Replace a node-based workflow's editable fields (extracted from the
    ``PUT /api/workflows/{id}`` route so the route and the ``workflow.update``
    action share one implementation). Raises ``HTTPException(404)`` for an
    unknown id. Demotes ``is_template`` once a user edits a preset (#780)."""
    from fichero.models import Workflow

    existing = db.get(Workflow, workflow_id)
    if not existing:
        raise HTTPException(
            status_code=404, detail=f"Workflow not found: {workflow_id}"
        )

    # Use model_dump_for_storage() to exclude ports (they come from registry)
    existing.name = workflow.name
    existing.description = workflow.description or ""
    existing.format = "nodes"
    existing.provider = workflow.provider or ""
    existing.model = workflow.model or ""
    existing.nodes = [node.model_dump_for_storage() for node in workflow.nodes]
    existing.edges = [edge.model_dump() for edge in workflow.edges]
    existing.updated_at = datetime.now()
    # Once a user edits a preset workflow, it stops being a template —
    # reinstall-defaults must NOT wipe it on next app launch (#780).
    # Same intent as macOS Finder's "user has customized this" flag —
    # auto-restore is for files the user hasn't touched.
    if getattr(existing, "is_template", False):
        existing.is_template = False
    db.save(existing)
    return existing


@router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    workflow: WorkflowDef,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> WorkflowResponse:
    """Update an existing workflow."""
    try:
        # Debug: log what's being received and saved
        print(f"[UPDATE] workflow: id={workflow_id}")
        print(
            f"[UPDATE]   received nodes: {len(workflow.nodes)}, edges: {len(workflow.edges)}"
        )
        for node in workflow.nodes[:3]:  # Log first 3 nodes
            print(f"[UPDATE]   node: tool={node.tool}, id={node.id[:8]}...")

        existing = update_workflow_impl(db, workflow_id, workflow)

        emit_change(
            x_fichero_library_path,
            type="workflow.updated",
            actor=actor,
            run_id=None,
            origin_window=x_fichero_origin_window,
            origin_user=actor,
        )

        # Debug: verify what was saved
        print(
            f"[UPDATE]   saved nodes: {len(existing.nodes)}, edges: {len(existing.edges)}"
        )

        return WorkflowResponse(
            id=existing.id,
            name=existing.name,
            description=existing.description,
            provider=existing.provider,
            model=existing.model,
            format=existing.format,
            nodes=[_dict_to_node_def(n) for n in existing.nodes],
            edges=[_dict_to_edge_def(e) for e in existing.edges],
            folder_path=existing.folder_path,
            sort_order=existing.sort_order,
            untested=_workflow_untested(existing),
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
    format: Optional[str] = None
    folder_path: Optional[str] = None
    sort_order: Optional[int] = None

    model_config = ConfigDict(extra="allow")


def patch_workflow_impl(
    db: Database, workflow_id: str, patch: "WorkflowPatchRequest"
) -> "Workflow":  # noqa: F821
    """Apply a partial workflow update — rename, move folder, reorder (extracted
    from the ``PATCH /api/workflows/{id}`` route so the route and the
    ``workflow.patch`` action share one implementation). Only the explicitly
    provided fields are written. Raises ``HTTPException(404)`` for an unknown id."""
    from fichero.models import Workflow

    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=404, detail=f"Workflow not found: {workflow_id}"
        )

    if patch.name is not None:
        workflow.name = patch.name
    if patch.description is not None:
        workflow.description = patch.description
    if patch.format is not None:
        workflow.format = patch.format
    if patch.folder_path is not None:
        workflow.folder_path = patch.folder_path
    if patch.sort_order is not None:
        workflow.sort_order = patch.sort_order

    workflow.updated_at = datetime.now()
    db.save(workflow)
    return workflow


@router.patch("/{workflow_id}")
async def patch_workflow(
    workflow_id: str,
    patch: WorkflowPatchRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> WorkflowResponse:
    """Partially update a workflow (rename, move to folder, etc.)."""
    try:
        workflow = patch_workflow_impl(db, workflow_id, patch)

        emit_change(
            x_fichero_library_path,
            type="workflow.updated",
            actor=actor,
            run_id=None,
            origin_window=x_fichero_origin_window,
            origin_user=actor,
        )

        return WorkflowResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            provider=workflow.provider,
            model=workflow.model,
            format=workflow.format,
            nodes=[_dict_to_node_def(n) for n in workflow.nodes],
            edges=[_dict_to_edge_def(e) for e in workflow.edges],
            folder_path=workflow.folder_path,
            sort_order=workflow.sort_order,
            untested=_workflow_untested(workflow),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to patch workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


def delete_workflow_impl(db: Database, workflow_id: str) -> "Workflow":  # noqa: F821
    """Delete a saved workflow and return the deleted row (extracted from the
    ``DELETE /api/workflows/{id}`` route so the route and the ``workflow.delete``
    action share one implementation). Returning the row lets the action snapshot
    it as the undo payload. Raises ``HTTPException(404)`` for an unknown id."""
    from fichero.models import Workflow

    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=404, detail=f"Workflow not found: {workflow_id}"
        )
    db.delete(workflow)
    return workflow


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> WorkflowDeletedResponse:
    """Delete a saved workflow."""
    try:
        delete_workflow_impl(db, workflow_id)

        emit_change(
            x_fichero_library_path,
            type="workflow.deleted",
            actor=actor,
            run_id=None,
            origin_window=x_fichero_origin_window,
            origin_user=actor,
        )

        return WorkflowDeletedResponse(
            message=f"Workflow {workflow_id} deleted successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete workflow {workflow_id}")
        raise HTTPException(status_code=500, detail=str(e))


def duplicate_workflow_impl(db: Database, workflow_id: str) -> "Workflow":  # noqa: F821
    """Duplicate a workflow with a new id and "(Copy)" name (extracted from the
    ``POST /api/workflows/{id}/duplicate`` route so the route and the
    ``workflow.duplicate`` action share one implementation). Raises
    ``HTTPException(404)`` for an unknown id."""
    from fichero.models import Workflow

    original = db.get(Workflow, workflow_id)
    if not original:
        raise HTTPException(
            status_code=404, detail=f"Workflow not found: {workflow_id}"
        )

    new_workflow = Workflow(
        name=f"{original.name} (Copy)",
        description=original.description,
        format=original.format,
        provider=original.provider,
        model=original.model,
        nodes=original.nodes,
        edges=original.edges,
        folder_path=original.folder_path,  # Keep in same folder
        sort_order=original.sort_order,  # Preserve order preference
        untested=_workflow_untested(original),
    )
    db.save(new_workflow)  # generates a new id
    return new_workflow


@router.post("/{workflow_id}/duplicate")
async def duplicate_workflow(
    workflow_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> WorkflowResponse:
    """Duplicate a workflow with a new ID and modified name."""
    try:
        new_workflow = duplicate_workflow_impl(db, workflow_id)

        emit_change(
            x_fichero_library_path,
            type="workflow.created",
            actor=actor,
            run_id=None,
            origin_window=x_fichero_origin_window,
            origin_user=actor,
        )

        return WorkflowResponse(
            id=new_workflow.id,
            name=new_workflow.name,
            description=new_workflow.description,
            provider=new_workflow.provider,
            model=new_workflow.model,
            format=new_workflow.format,
            nodes=[_dict_to_node_def(n) for n in new_workflow.nodes],
            edges=[_dict_to_edge_def(e) for e in new_workflow.edges],
            folder_path=new_workflow.folder_path,
            sort_order=new_workflow.sort_order,
            untested=_workflow_untested(new_workflow),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to duplicate workflow")
        raise HTTPException(status_code=500, detail=str(e))


def reorder_workflows_impl(
    db: Database, workflow_ids: list[str], folder_path: str = "/"
) -> "list[Workflow]":  # noqa: F821
    """Assign ``sort_order = position`` for each workflow in ``workflow_ids``
    (extracted from the ``POST /api/workflows/reorder`` route so the route and
    the ``workflow.reorder`` action share one implementation). Returns the
    updated rows. Raises ``HTTPException(404)`` for an unknown id."""
    from fichero.models import Workflow

    updated: list[Workflow] = []
    for i, workflow_id in enumerate(workflow_ids):
        workflow = db.get(Workflow, workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404, detail=f"Workflow not found: {workflow_id}"
            )
        workflow.sort_order = i
        db.save(workflow)
        updated.append(workflow)
    return updated


@router.post("/reorder")
async def reorder_workflows(
    workflow_ids: list[str],
    folder_path: str = "/",
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> WorkflowReorderResponse:
    """Reorder workflows within a folder."""
    try:
        reorder_workflows_impl(db, workflow_ids, folder_path)

        emit_change(
            x_fichero_library_path,
            type="workflow.updated",
            actor=actor,
            run_id=None,
            origin_window=x_fichero_origin_window,
            origin_user=actor,
        )

        return WorkflowReorderResponse(status="reordered", count=len(workflow_ids))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to reorder workflows")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Action layer registration (EPIC #1848 / sweep #2014) — workflow domain
# ---------------------------------------------------------------------------
#
# Every workflow mutation (create / import / update / patch / delete /
# duplicate / reorder / create_node) becomes a registered, audited action that
# WRAPS the proven ``*_impl`` above — the typed routes stay green and untouched;
# the action is the additional uniform path that chat tools / App Intents /
# tests drive via POST /api/actions/invoke. ``before``/``after`` snapshots ARE
# the undo payload.
#
# Undo design: ``db.save`` is an upsert by id, so a single ``workflow.restore``
# (full-snapshot upsert) inverts BOTH a delete (re-inserts the row, same id) and
# an edit (overwrites with the prior snapshot). ``restore`` records whether the
# row pre-existed, so its OWN inverse is ``delete`` (after a recreate) or
# ``restore`` (after an overwrite) — keeping every undo/redo chain sane.
# ``reorder``/``set_sort_orders`` are inverted by re-applying the captured prior
# (id -> sort_order) map. ``create_node`` is a pure factory (no persisted DB
# state) so it is NOT undoable.

from fichero.actions.registry import action, ActionContext, ChangeSpec  # noqa: E402


def _snap_workflow(wf) -> dict:
    """JSON-able snapshot of a Workflow row (the undo payload)."""
    return wf.model_dump(mode="json")


class WorkflowUpdateParams(BaseModel):
    """``workflow.update`` params — the full WorkflowDef plus its target id."""

    workflow_id: str
    workflow: WorkflowDef


class WorkflowPatchParams(WorkflowPatchRequest):
    """``workflow.patch`` params — the patch fields plus the target id."""

    workflow_id: str


class WorkflowImportParams(BaseModel):
    name: str = ""
    description: str = ""
    workflow_data: dict = Field(default_factory=dict)


class WorkflowIdParams(BaseModel):
    """Shared params for id-only actions (delete / duplicate)."""

    workflow_id: str


class WorkflowRestoreParams(BaseModel):
    """``workflow.restore`` — re-materialize / overwrite a workflow by snapshot."""

    snapshot: dict


class WorkflowReorderParams(BaseModel):
    workflow_ids: list[str]
    folder_path: str = "/"


class _SortOrderEntry(BaseModel):
    id: str
    sort_order: int


class WorkflowSetSortOrdersParams(BaseModel):
    """Inverse-of-reorder: set explicit (id -> sort_order) for each entry."""

    orders: list[_SortOrderEntry]


class WorkflowCreateNodeParams(BaseModel):
    tool_name: str
    position_x: float = 0
    position_y: float = 0


def _invert_to_delete(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a create/import/duplicate by hard-deleting the row it produced."""
    if not after:
        return None
    wid = after.get("id")
    if not wid:
        return None
    return ("workflow.delete", {"workflow_id": wid})


def _invert_to_restore_before(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo an edit/delete by restoring the captured pre-change snapshot."""
    if not before:
        return None
    return ("workflow.restore", {"snapshot": before})


def _invert_restore(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Inverse of restore — depends on whether the row pre-existed.

    If ``before`` is None the restore RE-CREATED a missing row (it was undoing a
    delete) -> redo by deleting again. If ``before`` is a snapshot the restore
    OVERWROTE an existing row (undoing an edit) -> redo by restoring that prior
    snapshot, which re-applies the edit. This keeps delete<->restore and
    edit<->restore redo chains correct."""
    if not after:
        return None
    wid = after.get("id")
    if before is None:
        if not wid:
            return None
        return ("workflow.delete", {"workflow_id": wid})
    return ("workflow.restore", {"snapshot": before})


def _invert_set_sort_orders(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a reorder / set-sort-orders by re-applying the prior order map."""
    if not before or not before.get("orders"):
        return None
    return ("workflow.set_sort_orders", {"orders": before["orders"]})


@action(
    "workflow.create",
    WorkflowDef,
    domains=["workflow"],
    undoable=True,
    invert=_invert_to_delete,
)
def _action_create_workflow(
    db: Database, params: WorkflowDef, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    wf = create_workflow_impl(db, params)
    after = _snap_workflow(wf)
    spec = ChangeSpec(
        domains=["workflow"],
        target_ids=[wf.id],
        before=None,
        after=after,
        emit_type="workflow.created",
    )
    return after, spec


@action(
    "workflow.import",
    WorkflowImportParams,
    domains=["workflow"],
    undoable=True,
    invert=_invert_to_delete,
)
def _action_import_workflow(
    db: Database, params: WorkflowImportParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    wf = import_workflow_impl(db, params.name, params.description, params.workflow_data)
    after = _snap_workflow(wf)
    spec = ChangeSpec(
        domains=["workflow"],
        target_ids=[wf.id],
        before=None,
        after=after,
        emit_type="workflow.created",
    )
    return after, spec


@action(
    "workflow.update",
    WorkflowUpdateParams,
    domains=["workflow"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_update_workflow(
    db: Database, params: WorkflowUpdateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    from fichero.models import Workflow

    existing = db.get(Workflow, params.workflow_id)
    if existing is None:
        raise HTTPException(
            status_code=404, detail=f"Workflow not found: {params.workflow_id}"
        )
    before = _snap_workflow(existing)
    wf = update_workflow_impl(db, params.workflow_id, params.workflow)
    after = _snap_workflow(wf)
    spec = ChangeSpec(
        domains=["workflow"],
        target_ids=[wf.id],
        before=before,
        after=after,
        emit_type="workflow.updated",
    )
    return after, spec


@action(
    "workflow.patch",
    WorkflowPatchParams,
    domains=["workflow"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_patch_workflow(
    db: Database, params: WorkflowPatchParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    from fichero.models import Workflow

    existing = db.get(Workflow, params.workflow_id)
    if existing is None:
        raise HTTPException(
            status_code=404, detail=f"Workflow not found: {params.workflow_id}"
        )
    before = _snap_workflow(existing)
    patch = WorkflowPatchRequest(
        **params.model_dump(exclude={"workflow_id"}, exclude_unset=True)
    )
    wf = patch_workflow_impl(db, params.workflow_id, patch)
    after = _snap_workflow(wf)
    spec = ChangeSpec(
        domains=["workflow"],
        target_ids=[wf.id],
        before=before,
        after=after,
        emit_type="workflow.updated",
    )
    return after, spec


@action(
    "workflow.delete",
    WorkflowIdParams,
    domains=["workflow"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_delete_workflow(
    db: Database, params: WorkflowIdParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    deleted = delete_workflow_impl(db, params.workflow_id)
    before = _snap_workflow(deleted)
    spec = ChangeSpec(
        domains=["workflow"],
        target_ids=[params.workflow_id],
        before=before,
        after=None,
        emit_type="workflow.deleted",
    )
    return before, spec


@action(
    "workflow.restore",
    WorkflowRestoreParams,
    domains=["workflow"],
    undoable=True,
    invert=_invert_restore,
)
def _action_restore_workflow(
    db: Database, params: WorkflowRestoreParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Upsert a workflow from its snapshot (preserving id). Records whether the
    row pre-existed so its inverse picks delete (recreate) vs restore (edit)."""
    from fichero.models import Workflow

    wid = params.snapshot.get("id")
    existing = db.get(Workflow, wid) if wid else None
    before = _snap_workflow(existing) if existing else None
    wf = Workflow(**params.snapshot)
    db.save(wf)
    after = _snap_workflow(wf)
    spec = ChangeSpec(
        domains=["workflow"],
        target_ids=[wf.id],
        before=before,
        after=after,
        emit_type="workflow.updated" if before else "workflow.created",
    )
    return after, spec


@action(
    "workflow.duplicate",
    WorkflowIdParams,
    domains=["workflow"],
    undoable=True,
    invert=_invert_to_delete,
)
def _action_duplicate_workflow(
    db: Database, params: WorkflowIdParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    wf = duplicate_workflow_impl(db, params.workflow_id)
    after = _snap_workflow(wf)
    spec = ChangeSpec(
        domains=["workflow"],
        target_ids=[wf.id],
        before=None,
        after=after,
        emit_type="workflow.created",
    )
    return after, spec


@action(
    "workflow.reorder",
    WorkflowReorderParams,
    domains=["workflow"],
    undoable=True,
    invert=_invert_set_sort_orders,
)
def _action_reorder_workflows(
    db: Database, params: WorkflowReorderParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    from fichero.models import Workflow

    # Capture prior sort_order for each id BEFORE the impl reassigns them, so the
    # inverse can restore the exact prior ordering (reorder is NOT a contiguous
    # 0..n permutation of the same set — undo must use explicit per-id orders).
    before_orders = []
    for wid in params.workflow_ids:
        wf = db.get(Workflow, wid)
        if wf is not None:
            before_orders.append({"id": wid, "sort_order": wf.sort_order})
    updated = reorder_workflows_impl(db, params.workflow_ids, params.folder_path)
    after_orders = [{"id": w.id, "sort_order": w.sort_order} for w in updated]
    spec = ChangeSpec(
        domains=["workflow"],
        target_ids=list(params.workflow_ids),
        before={"orders": before_orders},
        after={"orders": after_orders},
        emit_type="workflow.updated",
    )
    return {"count": len(updated)}, spec


@action(
    "workflow.set_sort_orders",
    WorkflowSetSortOrdersParams,
    domains=["workflow"],
    undoable=True,
    invert=_invert_set_sort_orders,
)
def _action_set_sort_orders(
    db: Database, params: WorkflowSetSortOrdersParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Inverse-of-reorder: set explicit per-id sort_order values. Itself
    undoable + redoable via the captured before/after order maps."""
    from fichero.models import Workflow

    before_orders = []
    after_orders = []
    for entry in params.orders:
        wf = db.get(Workflow, entry.id)
        if wf is None:
            raise HTTPException(
                status_code=404, detail=f"Workflow not found: {entry.id}"
            )
        before_orders.append({"id": wf.id, "sort_order": wf.sort_order})
        wf.sort_order = entry.sort_order
        db.save(wf)
        after_orders.append({"id": wf.id, "sort_order": entry.sort_order})
    spec = ChangeSpec(
        domains=["workflow"],
        target_ids=[e.id for e in params.orders],
        before={"orders": before_orders},
        after={"orders": after_orders},
        emit_type="workflow.updated",
    )
    return {"count": len(params.orders)}, spec


@action(
    "workflow.create_node",
    WorkflowCreateNodeParams,
    domains=["workflow"],
    undoable=False,
)
def _action_create_node(
    db: Database, params: WorkflowCreateNodeParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Build a node instance from a tool (pure factory — no persisted DB state,
    so NOT undoable). Mirrors the ``POST /tools/{tool}/create-node`` route."""
    node = create_node_from_tool(params.tool_name, params.position_x, params.position_y)
    if not node:
        raise HTTPException(
            status_code=404, detail=f"Tool not found: {params.tool_name}"
        )
    node_dict = {
        "id": node.id,
        "tool": node.tool,
        "label": node.label,
        "description": node.description,
        "position_x": node.position_x,
        "position_y": node.position_y,
    }
    spec = ChangeSpec(
        domains=["workflow"],
        target_ids=[node.id],
        before=None,
        after=node_dict,
        emit_type="workflow.updated",
    )
    return node_dict, spec
