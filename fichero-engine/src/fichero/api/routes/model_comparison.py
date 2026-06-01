"""
Model Comparison API Routes

Endpoints for comparing responses across multiple LLM models.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.app_db import AppDatabase, get_app_db
from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import Workflow
from fichero.workflows.resolver import resolve_inputs
from fichero.workflows.model_comparison import (
    ComparisonRequest,
    ModelSpec,
    get_comparison_engine,
)
from fichero.workflows.registry import get_tool_def
from fichero.workflows.types import NodeDef, State, WorkflowDef

router = APIRouter(prefix="/model-comparison", tags=["model-comparison"])


# =============================================================================
# Request/Response Models
# =============================================================================


class CompareRequest(BaseModel):
    """Request to compare models."""

    prompt: str = Field(..., description="Prompt to send to all models")
    models: list[dict] = Field(default_factory=list, description="Models to compare")
    system_prompt: str | None = Field(
        default=None, description="Optional system prompt"
    )
    timeout_seconds: int = Field(default=60, description="Timeout per model")
    expect_json: bool = Field(
        default=False,
        description="Mark structured decode success by parsing responses as JSON",
    )
    response_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON schema requested by the comparison UI",
    )


class VisionCompareRequest(BaseModel):
    """Request to compare vision models."""

    images: list[str] = Field(..., description="Image URLs or base64 data URIs")
    prompt: str = Field(
        default="Describe this image in detail",
        description="Prompt for vision analysis",
    )
    models: list[dict] = Field(
        default_factory=list, description="Vision-capable models to compare"
    )
    detail: str = Field(
        default="auto", description="Image detail level: auto, low, high"
    )
    timeout_seconds: int = Field(default=120, description="Timeout per model")


class ToolCompareRequest(BaseModel):
    """Request to compare models running a workflow tool."""

    tool_name: str = Field(
        ...,
        description="Name of the workflow tool (describe, summarize, classify, etc.)",
    )
    inputs: dict = Field(..., description="Tool-specific inputs (files, text, etc.)")
    models: list[dict] = Field(default_factory=list, description="Models to compare")
    tool_config: dict | None = Field(
        default=None, description="Optional tool configuration overrides"
    )
    timeout_seconds: int = Field(default=120, description="Timeout per model")


class ModelInfo(BaseModel):
    """Information about a model."""

    provider: str
    model: str
    input_price_per_million: float
    output_price_per_million: float
    enabled: bool = True


class ModelResultResponse(BaseModel):
    """Result from a single model in a comparison run."""

    provider: str
    model: str
    response: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: str | None
    structured_decode_success: bool | None = None
    structured_decode_error: str | None = None
    guardrail_fallback_used: bool = False
    fallback_provider: str | None = None
    fallback_model: str | None = None
    raw_response: Any | None = None
    timestamp: str


class ComparisonResultResponse(BaseModel):
    """Result of comparing multiple models on the same prompt."""

    prompt: str
    models_compared: list[str]
    results: list[ModelResultResponse]
    fastest_model: str | None
    cheapest_model: str | None
    total_cost_usd: float
    total_latency_ms: float
    comparison_id: str
    timestamp: str


class ComparisonHistoryResponse(BaseModel):
    history: list[ComparisonResultResponse]


class ModelListResponse(BaseModel):
    models: list[ModelInfo]


class CostEstimateItem(BaseModel):
    provider: str
    model: str
    estimated_cost_usd: float


class CostEstimateResponse(BaseModel):
    estimated_input_tokens: int
    estimated_output_tokens: int
    model_estimates: list[CostEstimateItem]
    total_estimated_cost_usd: float


class TierModelInfo(BaseModel):
    provider: str
    model: str
    input_price: float
    output_price: float
    tier: str


class ModelsByTierResponse(BaseModel):
    frontier: list[TierModelInfo] = []
    mid: list[TierModelInfo] = []
    budget: list[TierModelInfo] = []
    local: list[TierModelInfo] = []


class PresetModelSpec(BaseModel):
    provider: str
    model: str


class ComparisonPreset(BaseModel):
    name: str
    description: str
    models: list[PresetModelSpec]


class PresetsResponse(BaseModel):
    presets: list[ComparisonPreset]


class ToolPortInfo(BaseModel):
    id: str
    name: str
    required: bool


class ComparisonToolInfo(BaseModel):
    name: str
    display_name: str
    description: str
    category: str
    input_ports: list[ToolPortInfo]


class ToolListResponse(BaseModel):
    items: list[ComparisonToolInfo]
    count: int


class NodeModelApplyPatch(BaseModel):
    provider_name: str
    model_name: str


class NodeComparisonItem(BaseModel):
    provider: str
    model: str
    apply_patch: NodeModelApplyPatch
    result: ModelResultResponse


class NodeCompareRequest(BaseModel):
    workflow_id: str | None = Field(
        default=None, description="Saved workflow ID when workflow is not supplied"
    )
    workflow: WorkflowDef | None = Field(
        default=None, description="Unsaved workflow definition from the editor"
    )
    node_id: str = Field(..., description="Node to run across models")
    models: list[dict] = Field(default_factory=list, description="Models to compare")
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Pinned workflow inputs for resolving this node",
    )
    outputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Pinned upstream node outputs for resolving this node",
    )
    input_files: list[str] = Field(default_factory=list)
    pinned_inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved node inputs that override mappings/static inputs",
    )
    workflow_config: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=120, description="Timeout per model")


class NodeComparisonResponse(BaseModel):
    workflow_id: str | None
    node_id: str
    tool_name: str
    input_snapshot: dict[str, Any]
    comparison: ComparisonResultResponse
    choices: list[NodeComparisonItem]


class ApplyNodeModelRequest(BaseModel):
    workflow_id: str
    node_id: str
    provider_name: str
    model_name: str


class ApplyNodeModelResponse(BaseModel):
    workflow_id: str
    node_id: str
    provider_name: str
    model_name: str


def _get_app_database() -> AppDatabase:
    return get_app_db()


def _configured_models(app_db: AppDatabase) -> list[dict[str, Any]]:
    providers = {p.id: p for p in app_db.list_providers() if p.enabled}
    models: list[dict[str, Any]] = []
    for model in app_db.list_models():
        provider = providers.get(model.provider_id)
        if not provider or not model.enabled:
            continue
        models.append(
            {
                "provider": provider.provider_type.value,
                "model": model.model_id,
                "input_price_per_million": model.input_cost or 0.0,
                "output_price_per_million": model.output_cost or 0.0,
                "capabilities": model.capabilities,
                "enabled": model.enabled,
            }
        )
    return models


def _model_specs(
    requested: list[dict[str, Any]],
    app_db: AppDatabase,
    *,
    require_capability: str | None = None,
) -> list[ModelSpec]:
    raw_models = requested or _configured_models(app_db)
    if require_capability and not requested:
        raw_models = [
            m for m in raw_models
            if require_capability in (m.get("capabilities") or [require_capability])
        ]
    specs = [
        ModelSpec(
            provider=m.get("provider", ""),
            model=m.get("model", ""),
            temperature=m.get("temperature", 0.7),
            max_tokens=m.get("max_tokens"),
        )
        for m in raw_models
        if m.get("provider") and m.get("model")
    ]
    if not specs:
        raise HTTPException(
            status_code=400,
            detail="No enabled models are configured in Settings",
        )
    return specs


def _workflow_from_request(
    request: NodeCompareRequest,
    db: Database,
) -> WorkflowDef:
    if request.workflow:
        return request.workflow
    if not request.workflow_id:
        raise HTTPException(status_code=400, detail="workflow_id or workflow required")
    workflow = db.get(Workflow, request.workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowDef(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        provider=workflow.provider,
        model=workflow.model,
        nodes=[NodeDef(**node) for node in workflow.nodes],
        edges=workflow.edges,
    )


def _node_inputs(
    node: NodeDef,
    request: NodeCompareRequest,
) -> dict[str, Any]:
    mapped_inputs = {
        mapping.port_id: mapping.source_path
        for mapping in node.input_mappings
    }
    state: State = {
        "task_id": "model-comparison-node",
        "workflow_id": request.workflow_id or "",
        "library_path": "",
        "selected_doc_ids": [],
        "inputs": request.inputs,
        "outputs": request.outputs,
        "current_node": node.id,
        "completed_nodes": list(request.outputs.keys()),
        "error": None,
        "input_files": request.input_files,
        "output_files": [],
        "parallel_results": {},
        "parallel_index": 0,
        "parallel_total": 0,
        "parallel_file": "",
        "parallel_document": None,
    }
    resolved = resolve_inputs(
        {**node.inputs, **mapped_inputs},
        state,
        request.workflow_config,
    )
    return {**resolved, **node.config, **request.pinned_inputs}


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/compare")
async def compare_models(
    request: CompareRequest,
    app_db: AppDatabase = Depends(_get_app_database),
) -> ComparisonResultResponse:
    """Compare responses from multiple models.

    Runs the same prompt against all specified models in parallel
    and returns comparison results with timing and cost metrics.
    """
    model_specs = _model_specs(request.models, app_db)

    comparison_request = ComparisonRequest(
        prompt=request.prompt,
        models=model_specs,
        system_prompt=request.system_prompt,
        timeout_seconds=request.timeout_seconds,
        expect_json=request.expect_json,
        response_schema=request.response_schema,
    )

    engine = get_comparison_engine()
    result = await engine.compare(comparison_request)

    return ComparisonResultResponse(**result.to_dict())


@router.get("/history")
async def get_comparison_history(limit: int = 10) -> ComparisonHistoryResponse:
    """Get recent comparison history."""
    engine = get_comparison_engine()
    return ComparisonHistoryResponse(
        history=[
            ComparisonResultResponse(**(r if isinstance(r, dict) else r.to_dict()))
            for r in engine.get_history(limit)
        ]
    )


@router.get("/comparison/{comparison_id}")
async def get_comparison(comparison_id: str) -> ComparisonResultResponse:
    """Get a specific comparison by ID."""
    engine = get_comparison_engine()
    result = engine.get_comparison(comparison_id)
    if not result:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return ComparisonResultResponse(**result.to_dict())


@router.get("/models")
async def list_available_models(
    app_db: AppDatabase = Depends(_get_app_database),
) -> ModelListResponse:
    """List enabled Settings models with pricing information."""
    return ModelListResponse(
        models=[ModelInfo(**model) for model in _configured_models(app_db)]
    )


@router.post("/estimate-cost")
async def estimate_comparison_cost(
    request: CompareRequest,
    app_db: AppDatabase = Depends(_get_app_database),
) -> CostEstimateResponse:
    """Estimate the cost of running a comparison.

    Uses approximate token counts to estimate costs before running.
    """
    from fichero.workflows.model_comparison import estimate_cost

    # Estimate input tokens (rough: ~4 chars per token)
    estimated_input_tokens = len(request.prompt) // 4
    if request.system_prompt:
        estimated_input_tokens += len(request.system_prompt) // 4

    # Estimate output tokens (assume ~500 tokens average response)
    estimated_output_tokens = 500

    estimates = []
    total_estimated_cost = 0.0

    for spec in _model_specs(request.models, app_db):
        model_name = spec.model
        cost = estimate_cost(
            model_name, estimated_input_tokens, estimated_output_tokens
        )
        estimates.append(CostEstimateItem(
            provider=spec.provider,
            model=model_name,
            estimated_cost_usd=cost,
        ))
        total_estimated_cost += cost

    return CostEstimateResponse(
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        model_estimates=estimates,
        total_estimated_cost_usd=total_estimated_cost,
    )


@router.get("/presets")
async def get_comparison_presets(
    app_db: AppDatabase = Depends(_get_app_database),
) -> PresetsResponse:
    """Get Settings-backed model presets for common comparison scenarios."""
    configured = _configured_models(app_db)
    if not configured:
        return PresetsResponse(presets=[])
    cheapest = sorted(
        configured,
        key=lambda m: (m["input_price_per_million"], m["output_price_per_million"]),
    )
    presets = [
        ComparisonPreset(
            name="Configured Models",
            description="All enabled models from Settings",
            models=[PresetModelSpec(provider=m["provider"], model=m["model"]) for m in configured],
        ),
        ComparisonPreset(
            name="Lowest Cost",
            description="Lowest-cost enabled models from Settings",
            models=[PresetModelSpec(provider=m["provider"], model=m["model"]) for m in cheapest[:3]],
        ),
    ]
    return PresetsResponse(presets=presets)


@router.get("/models-by-tier")
async def get_models_grouped_by_tier(
    app_db: AppDatabase = Depends(_get_app_database),
) -> ModelsByTierResponse:
    """Get all models grouped by performance/cost tier.

    Returns models organized into:
    - frontier: Best quality, highest cost (GPT-4o, Claude 3.5 Sonnet, etc.)
    - mid: Good quality, moderate cost (GPT-4o-mini, Claude Haiku, etc.)
    - budget: Basic quality, low cost (GPT-3.5, etc.)
    - local: Free, runs locally (Llama, Mistral via Ollama)
    """
    configured = _configured_models(app_db)
    raw: dict[str, list[dict[str, Any]]] = {
        "frontier": [],
        "mid": [],
        "budget": [],
        "local": [],
    }
    for model in configured:
        price = model["input_price_per_million"] + model["output_price_per_million"]
        tier = "local" if price == 0 else "budget" if price < 2 else "frontier" if price > 20 else "mid"
        raw[tier].append({
            "provider": model["provider"],
            "model": model["model"],
            "input_price": model["input_price_per_million"],
            "output_price": model["output_price_per_million"],
            "tier": tier,
        })
    return ModelsByTierResponse(
        frontier=[TierModelInfo(**m) for m in raw.get("frontier", [])],
        mid=[TierModelInfo(**m) for m in raw.get("mid", [])],
        budget=[TierModelInfo(**m) for m in raw.get("budget", [])],
        local=[TierModelInfo(**m) for m in raw.get("local", [])],
    )


@router.post("/compare-vision")
async def compare_vision_models(
    request: VisionCompareRequest,
    app_db: AppDatabase = Depends(_get_app_database),
) -> ComparisonResultResponse:
    """Compare vision models on the same image(s).

    Sends the same image(s) to multiple vision-capable models
    and returns comparison results with timing and cost metrics.

    Images can be:
    - URLs (https://...)
    - Base64 data URIs (data:image/jpeg;base64,...)
    """
    model_specs = _model_specs(request.models, app_db, require_capability="vision")

    engine = get_comparison_engine()
    result = await engine.compare_vision(
        images=request.images,
        prompt=request.prompt,
        models=model_specs,
        detail=request.detail,
        timeout_seconds=request.timeout_seconds,
    )

    return ComparisonResultResponse(**result.to_dict())


@router.post("/compare-tool")
async def compare_tool_across_models(
    request: ToolCompareRequest,
    app_db: AppDatabase = Depends(_get_app_database),
) -> ComparisonResultResponse:
    """Compare models running the same workflow tool.

    Runs a workflow tool (describe, summarize, classify, etc.) with
    multiple models and compares their outputs.

    Available tools can be found via the /api/workflows/tools endpoint.
    """
    model_specs = _model_specs(request.models, app_db)

    engine = get_comparison_engine()
    result = await engine.compare_tool(
        tool_name=request.tool_name,
        inputs=request.inputs,
        models=model_specs,
        tool_config=request.tool_config,
        timeout_seconds=request.timeout_seconds,
    )

    return ComparisonResultResponse(**result.to_dict())


@router.post("/compare-node")
async def compare_workflow_node(
    request: NodeCompareRequest,
    app_db: AppDatabase = Depends(_get_app_database),
    db: Database = Depends(get_library_database),
) -> NodeComparisonResponse:
    """Compare one workflow node across Settings-configured models."""
    workflow = _workflow_from_request(request, db)
    node = next((n for n in workflow.nodes if n.id == request.node_id), None)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if not get_tool_def(node.tool):
        raise HTTPException(status_code=404, detail=f"Unknown tool: {node.tool}")

    inputs = _node_inputs(node, request)
    model_specs = _model_specs(request.models, app_db)
    engine = get_comparison_engine()
    result = await engine.compare_tool(
        tool_name=node.tool,
        inputs=inputs,
        models=model_specs,
        timeout_seconds=request.timeout_seconds,
    )
    choices = [
        NodeComparisonItem(
            provider=r.provider,
            model=r.model,
            apply_patch=NodeModelApplyPatch(
                provider_name=r.provider,
                model_name=r.model,
            ),
            result=ModelResultResponse(**r.to_dict()),
        )
        for r in result.results
    ]
    return NodeComparisonResponse(
        workflow_id=request.workflow_id or workflow.id,
        node_id=node.id,
        tool_name=node.tool,
        input_snapshot=inputs,
        comparison=ComparisonResultResponse(**result.to_dict()),
        choices=choices,
    )


@router.post("/compare-node/apply")
async def apply_model_to_workflow_node(
    request: ApplyNodeModelRequest,
    db: Database = Depends(get_library_database),
) -> ApplyNodeModelResponse:
    """Persist a selected provider/model choice onto one workflow node."""
    workflow = db.get(Workflow, request.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    node_updated = False
    updated_nodes: list[dict[str, Any]] = []
    for raw_node in workflow.nodes:
        node_dict = dict(raw_node)
        if node_dict.get("id") == request.node_id:
            node_dict["provider_name"] = request.provider_name
            node_dict["model_name"] = request.model_name
            node_updated = True
        updated_nodes.append(node_dict)

    if not node_updated:
        raise HTTPException(status_code=404, detail="Node not found")

    workflow.nodes = updated_nodes
    db.save(workflow)
    return ApplyNodeModelResponse(
        workflow_id=workflow.id,
        node_id=request.node_id,
        provider_name=request.provider_name,
        model_name=request.model_name,
    )


@router.get("/tools")
async def list_available_tools() -> ToolListResponse:
    """List available workflow tools that can be used for comparison.

    Returns tools that support LLM comparison (have uses_llm=True).
    """
    from fichero.workflows.registry import list_tools

    tools = [
        ComparisonToolInfo(
            name=tool_def.name,
            display_name=tool_def.display_name,
            description=tool_def.description,
            category=tool_def.category,
            input_ports=[
                ToolPortInfo(id=p.id, name=p.name, required=p.required)
                for p in tool_def.input_ports
            ],
        )
        for tool_def in list_tools()
        if tool_def.uses_llm
    ]

    return ToolListResponse(items=tools, count=len(tools))
