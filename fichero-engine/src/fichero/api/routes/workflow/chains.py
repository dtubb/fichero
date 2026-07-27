"""
API Routes for Workflow Chains

Provides endpoints for managing and executing workflow chains.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from fichero.workflows.chaining import (
    WorkflowChain,
    ChainStep,
    OutputMapping,
    ChainStepCondition,
    ChainExecutor,
    ChainExecutionResult,
    ChainProgressEvent,
    ChainStepStatus,
    chain_store,
)
from fichero.workflows.types import WorkflowDef
from fichero.workflows.workflow_store import WorkflowStore
from fichero.db import db_manager
from fichero.api.library_header import require_library_path
from fichero.api.main import assert_library_read_authorized

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chains", tags=["chains"])


# =============================================================================
# Request/Response Models
# =============================================================================


class OutputMappingRequest(BaseModel):
    """Request model for output mapping."""

    source_path: str = Field(
        ..., description="Path to source data (e.g., '$.outputs.node_id.key')"
    )
    target_key: str = Field(..., description="Input key name in next workflow")
    transform: str | None = None


class ChainStepConditionRequest(BaseModel):
    """Request model for chain step condition."""

    expression: str = Field(..., description="Condition expression")
    true_step: str | None = None
    false_step: str | None = None


class ChainStepRequest(BaseModel):
    """Request model for chain step."""

    id: str
    workflow_id: str
    name: str = ""
    input_mappings: list[OutputMappingRequest] = Field(default_factory=list)
    static_inputs: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form JSON inputs merged into this step at execution time. "
            "Values stay workflow-defined and are not coerced."
        ),
    )
    condition: ChainStepConditionRequest | None = None
    continue_on_error: bool = False
    timeout_seconds: int = 300


class ChainStepResponse(BaseModel):
    """Typed response model for a workflow chain step."""

    id: str
    workflow_id: str
    name: str = ""
    input_mappings: list[OutputMappingRequest] = Field(default_factory=list)
    static_inputs: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form JSON inputs merged into this step at execution time. "
            "Values stay workflow-defined and are not coerced."
        ),
    )
    condition: ChainStepConditionRequest | None = None
    continue_on_error: bool = False
    timeout_seconds: int = 300


class CreateChainRequest(BaseModel):
    """Request to create a new workflow chain."""

    name: str = Field(..., min_length=1)
    description: str = ""
    steps: list[ChainStepRequest] = Field(default_factory=list)
    entry_step: str | None = None
    initial_inputs: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form JSON inputs for the chain entrypoint. Values are passed "
            "through as-is and must match the target workflow contract."
        ),
    )


class UpdateChainRequest(BaseModel):
    """Request to update an existing chain."""

    name: str | None = None
    description: str | None = None
    steps: list[ChainStepRequest] | None = None
    entry_step: str | None = None
    initial_inputs: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Free-form JSON inputs for the chain entrypoint. Values are passed "
            "through as-is and must match the target workflow contract."
        ),
    )


class ExecuteChainRequest(BaseModel):
    """Request to execute a workflow chain."""

    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form JSON execution inputs. This remains dynamic because each "
            "workflow chain defines its own input contract."
        ),
    )
    input_files: list[str] = Field(default_factory=list)


class ChainResponse(BaseModel):
    """Response model for chain data."""

    id: str
    name: str
    description: str
    steps: list[ChainStepResponse]
    entry_step: str | None
    initial_inputs: dict[str, Any] = Field(
        description=(
            "Free-form JSON inputs for the chain entrypoint. Values are passed "
            "through as-is and must match the target workflow contract."
        )
    )
    created_at: str
    updated_at: str
    folder_path: str = Field(
        description="Folder organization path for the chain."
    )
    sort_order: int = Field(
        description="Sort order within the chain folder."
    )


class ChainListResponse(BaseModel):
    """Response model for chain list."""

    chains: list[ChainResponse]
    total: int


class ChainExecutionResponse(BaseModel):
    """Response model for chain execution."""

    execution_id: str
    chain_id: str
    status: str
    message: str


class ChainDeletedResponse(BaseModel):
    deleted: bool
    id: str


class ChainStepResultInfo(BaseModel):
    step_id: str
    workflow_id: str
    status: str
    error: str | None
    duration_ms: float | None


class ChainEventInfo(BaseModel):
    event_type: str
    step_id: str | None
    message: str | None
    progress: float | None
    timestamp: str


class ChainExecutionStatusResponse(BaseModel):
    execution_id: str
    chain_id: str
    status: str
    step_results: list[ChainStepResultInfo]
    final_outputs: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form JSON outputs produced by the final workflow step. "
            "Output shape remains workflow-defined."
        ),
    )
    final_files: list[str] = Field(default_factory=list)
    total_duration_ms: float | None
    events: list[ChainEventInfo]


class ChainCancelResponse(BaseModel):
    cancelled: bool
    execution_id: str
    message: str | None = None


class PaleographyPresetResponse(BaseModel):
    """Draft or saved paleography stage chain."""

    chain: ChainResponse
    matched_workflows: dict[str, str]


# =============================================================================
# In-progress Execution Tracking
# =============================================================================

# Track running chain executions with TTL-based eviction
# Limit to MAX_TRACKED_EXECUTIONS to prevent unbounded memory growth
MAX_TRACKED_EXECUTIONS = 1000
MAX_EVENTS_PER_EXECUTION = 100
_running_executions: dict[str, ChainExecutionResult] = {}
_running_executors: dict[str, ChainExecutor] = {}
_execution_events: dict[str, list[ChainProgressEvent]] = {}
_execution_order: list[str] = []  # Track insertion order for LRU eviction


def _evict_old_executions() -> None:
    """Evict oldest executions if we exceed the limit."""
    while len(_execution_order) > MAX_TRACKED_EXECUTIONS:
        oldest_id = _execution_order.pop(0)
        _running_executions.pop(oldest_id, None)
        _running_executors.pop(oldest_id, None)
        _execution_events.pop(oldest_id, None)


def _on_chain_event(event: ChainProgressEvent) -> None:
    """Handle chain progress events."""
    execution_id = event.execution_id
    if execution_id not in _execution_events:
        _execution_events[execution_id] = []
    _execution_events[execution_id].append(event)
    # Limit events per execution
    if len(_execution_events[execution_id]) > MAX_EVENTS_PER_EXECUTION:
        _execution_events[execution_id] = _execution_events[execution_id][
            -MAX_EVENTS_PER_EXECUTION:
        ]
    logger.debug(f"Chain event: {event.event_type} - {event.message}")


def _create_workflow_loader(library_path: str) -> Callable[[str], WorkflowDef | None]:
    """Create a workflow loader function for the given library.

    Args:
        library_path: Path to the .fichero library

    Returns:
        Function that loads workflows by ID
    """

    def loader(workflow_id: str) -> WorkflowDef | None:
        try:
            db = db_manager.get_database(library_path)
            store = WorkflowStore(db)
            workflow = store.get(workflow_id)
            if workflow and workflow.definition:
                # Convert stored workflow to WorkflowDef
                return WorkflowDef(**workflow.definition)
            return None
        except Exception as e:
            logger.error(f"Failed to load workflow {workflow_id}: {e}")
            return None

    return loader


def _best_workflow_match(
    workflows: list[Any], preferred_terms: list[str]
) -> Any | None:
    lowered_terms = [term.lower() for term in preferred_terms]
    scored: list[tuple[int, Any]] = []
    for workflow in workflows:
        name = getattr(workflow, "name", "")
        name_lower = str(name).lower()
        score = 0
        for idx, term in enumerate(lowered_terms):
            if term in name_lower:
                score = max(score, max(1, 10 - idx))
        if score > 0:
            scored.append((score, workflow))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _build_paleography_chain(
    workflows: list[Any], *, chain_name: str = "Paleography A/B/C"
) -> tuple[WorkflowChain, dict[str, str]]:
    """Build a stageable A/B/C paleography chain from available workflows."""
    transcribe = _best_workflow_match(
        workflows, ["paleography", "handwriting", "htr", "transcribe", "ocr", "prepare"]
    )
    extract = _best_workflow_match(
        workflows, ["extract", "entities", "ner", "kg", "claims"]
    )
    catalogue = _best_workflow_match(
        workflows, ["catalogue", "catalog", "summary", "synthesis", "digest"]
    )

    if not transcribe or not extract or not catalogue:
        missing = []
        if not transcribe:
            missing.append("A/transcribe")
        if not extract:
            missing.append("B/extract-ner")
        if not catalogue:
            missing.append("C/catalogue")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot build paleography preset, missing workflows: {', '.join(missing)}",
        )

    matched = {
        "A": transcribe.id,
        "B": extract.id,
        "C": catalogue.id,
    }

    steps = [
        ChainStep(
            id="stage_a_transcription",
            workflow_id=transcribe.id,
            name="A: Transcription",
            static_inputs={"stage": "A"},
        ),
        ChainStep(
            id="stage_b_extract_ner",
            workflow_id=extract.id,
            name="B: Extraction/NER",
            input_mappings=[
                OutputMapping(
                    source_path="$.outputs",
                    target_key="upstream_outputs",
                )
            ],
            static_inputs={"stage": "B"},
        ),
        ChainStep(
            id="stage_c_catalogue",
            workflow_id=catalogue.id,
            name="C: Catalogue",
            input_mappings=[
                OutputMapping(
                    source_path="$.outputs",
                    target_key="upstream_outputs",
                )
            ],
            static_inputs={"stage": "C"},
        ),
    ]

    chain = WorkflowChain(
        name=chain_name,
        description=(
            "Stageable paleography chain: A transcription, "
            "B extraction/NER/claims, C catalogue."
        ),
        steps=steps,
        entry_step="stage_a_transcription",
        initial_inputs={},
    )
    return chain, matched


# =============================================================================
# Chain CRUD Endpoints
# =============================================================================


@router.post("", response_model=ChainResponse)
async def create_chain(request: CreateChainRequest) -> ChainResponse:
    """Create a new workflow chain."""
    # Convert request to domain model
    steps = []
    for step_req in request.steps:
        mappings = [
            OutputMapping(
                source_path=m.source_path,
                target_key=m.target_key,
                transform=m.transform,
            )
            for m in step_req.input_mappings
        ]
        condition = None
        if step_req.condition:
            condition = ChainStepCondition(
                expression=step_req.condition.expression,
                true_step=step_req.condition.true_step,
                false_step=step_req.condition.false_step,
            )
        steps.append(
            ChainStep(
                id=step_req.id,
                workflow_id=step_req.workflow_id,
                name=step_req.name,
                input_mappings=mappings,
                static_inputs=step_req.static_inputs,
                condition=condition,
                continue_on_error=step_req.continue_on_error,
                timeout_seconds=step_req.timeout_seconds,
            )
        )

    chain = WorkflowChain(
        name=request.name,
        description=request.description,
        steps=steps,
        entry_step=request.entry_step,
        initial_inputs=request.initial_inputs,
    )

    saved = chain_store.save(chain)
    return _chain_to_response(saved)


@router.get("", response_model=ChainListResponse)
async def list_chains(limit: int = 50, offset: int = 0) -> ChainListResponse:
    """List all workflow chains."""
    chains = chain_store.list(limit=limit, offset=offset)
    return ChainListResponse(
        chains=[_chain_to_response(c) for c in chains],
        total=len(chain_store._chains),
    )


@router.get("/{chain_id}", response_model=ChainResponse)
async def get_chain(chain_id: str) -> ChainResponse:
    """Get a workflow chain by ID."""
    chain = chain_store.get(chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail=f"Chain not found: {chain_id}")
    return _chain_to_response(chain)


@router.put("/{chain_id}", response_model=ChainResponse)
async def update_chain(chain_id: str, request: UpdateChainRequest) -> ChainResponse:
    """Update an existing workflow chain."""
    chain = chain_store.get(chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail=f"Chain not found: {chain_id}")

    if request.name is not None:
        chain.name = request.name
    if request.description is not None:
        chain.description = request.description
    if request.entry_step is not None:
        chain.entry_step = request.entry_step
    if request.initial_inputs is not None:
        chain.initial_inputs = request.initial_inputs

    if request.steps is not None:
        steps = []
        for step_req in request.steps:
            mappings = [
                OutputMapping(
                    source_path=m.source_path,
                    target_key=m.target_key,
                    transform=m.transform,
                )
                for m in step_req.input_mappings
            ]
            condition = None
            if step_req.condition:
                condition = ChainStepCondition(
                    expression=step_req.condition.expression,
                    true_step=step_req.condition.true_step,
                    false_step=step_req.condition.false_step,
                )
            steps.append(
                ChainStep(
                    id=step_req.id,
                    workflow_id=step_req.workflow_id,
                    name=step_req.name,
                    input_mappings=mappings,
                    static_inputs=step_req.static_inputs,
                    condition=condition,
                    continue_on_error=step_req.continue_on_error,
                    timeout_seconds=step_req.timeout_seconds,
                )
            )
        chain.steps = steps

    saved = chain_store.save(chain)
    return _chain_to_response(saved)


@router.delete("/{chain_id}")
async def delete_chain(chain_id: str) -> ChainDeletedResponse:
    """Delete a workflow chain."""
    if not chain_store.delete(chain_id):
        raise HTTPException(status_code=404, detail=f"Chain not found: {chain_id}")
    return ChainDeletedResponse(deleted=True, id=chain_id)


@router.get("/presets/paleography", response_model=PaleographyPresetResponse)
async def paleography_preset_preview(
    request: Request,
    x_fichero_library_path: str = Depends(require_library_path),
) -> PaleographyPresetResponse:
    """Draft a stageable A/B/C paleography chain from current workflows."""
    assert_library_read_authorized(request, x_fichero_library_path)
    db = db_manager.get_database(x_fichero_library_path)
    store = WorkflowStore(db)
    chain, matched = _build_paleography_chain(store.list_all())
    return PaleographyPresetResponse(
        chain=_chain_to_response(chain),
        matched_workflows=matched,
    )


@router.post("/presets/paleography", response_model=PaleographyPresetResponse)
async def paleography_preset_create(
    request: Request,
    x_fichero_library_path: str = Depends(require_library_path),
) -> PaleographyPresetResponse:
    """Create and save the A/B/C paleography chain preset."""
    assert_library_read_authorized(request, x_fichero_library_path)
    db = db_manager.get_database(x_fichero_library_path)
    store = WorkflowStore(db)
    chain, matched = _build_paleography_chain(store.list_all())
    saved = chain_store.save(chain)
    return PaleographyPresetResponse(
        chain=_chain_to_response(saved),
        matched_workflows=matched,
    )


# =============================================================================
# Chain Execution Endpoints
# =============================================================================


@router.post("/{chain_id}/execute", response_model=ChainExecutionResponse)
async def execute_chain(
    chain_id: str,
    request: ExecuteChainRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    x_fichero_library_path: str = Depends(require_library_path),
) -> ChainExecutionResponse:
    """Execute a workflow chain.

    Starts execution in background and returns immediately with execution ID.
    Use GET /chains/executions/{execution_id} to poll for status.

    Requires X-Fichero-Library-Path header to identify the library.
    """
    chain = chain_store.get(chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail=f"Chain not found: {chain_id}")
    assert_library_read_authorized(http_request, x_fichero_library_path)

    # Create workflow loader for this library
    workflow_loader = _create_workflow_loader(x_fichero_library_path)

    # Create executor
    executor = ChainExecutor(
        workflow_loader=workflow_loader,
        event_callback=_on_chain_event,
    )

    # Generate execution ID
    execution_id = str(uuid.uuid4())

    # Initialize tracking with eviction
    _execution_order.append(execution_id)
    _evict_old_executions()
    _execution_events[execution_id] = []
    _running_executions[execution_id] = ChainExecutionResult(
        chain_id=chain_id,
        execution_id=execution_id,
        status=ChainStepStatus.PENDING,
    )
    _running_executors[execution_id] = executor

    # Define background task
    async def run_chain():
        try:
            initial_inputs = dict(request.inputs)
            initial_inputs["library_path"] = x_fichero_library_path
            result = await executor.execute(
                chain=chain,
                initial_inputs=initial_inputs,
                initial_files=request.input_files,
            )
            _running_executions[execution_id] = result
        except Exception as e:
            logger.exception(f"Chain execution failed: {e}")
            _running_executions[execution_id] = ChainExecutionResult(
                chain_id=chain_id,
                execution_id=execution_id,
                status=ChainStepStatus.FAILED,
            )
        finally:
            _running_executors.pop(execution_id, None)

    # Start in background
    background_tasks.add_task(run_chain)

    return ChainExecutionResponse(
        execution_id=execution_id,
        chain_id=chain_id,
        status="running",
        message="Chain execution started",
    )


@router.get("/executions/{execution_id}")
async def get_chain_execution(execution_id: str) -> ChainExecutionStatusResponse:
    """Get the status and result of a chain execution."""
    if execution_id not in _running_executions:
        raise HTTPException(
            status_code=404, detail=f"Execution not found: {execution_id}"
        )

    result = _running_executions[execution_id]
    events = _execution_events.get(execution_id, [])

    return ChainExecutionStatusResponse(
        execution_id=execution_id,
        chain_id=result.chain_id,
        status=result.status.value,
        step_results=[
            ChainStepResultInfo(
                step_id=sr.step_id,
                workflow_id=sr.workflow_id,
                status=sr.status.value,
                error=sr.error,
                duration_ms=sr.duration_ms,
            )
            for sr in result.step_results
        ],
        final_outputs=result.final_outputs,
        final_files=result.final_files,
        total_duration_ms=result.total_duration_ms,
        events=[
            ChainEventInfo(
                event_type=e.event_type.value,
                step_id=e.step_id,
                message=e.message,
                progress=e.progress,
                timestamp=e.timestamp.isoformat(),
            )
            for e in events[-20:]  # Last 20 events
        ],
    )


@router.delete("/executions/{execution_id}")
async def cancel_chain_execution(execution_id: str) -> ChainCancelResponse:
    """Cancel a running chain execution.

    Note: May not immediately stop if a workflow step is in progress.
    """
    if execution_id not in _running_executions:
        raise HTTPException(
            status_code=404, detail=f"Execution not found: {execution_id}"
        )

    # Mark as cancelled (executor checks this flag)
    result = _running_executions[execution_id]
    if result.status == ChainStepStatus.PENDING:
        executor = _running_executors.get(execution_id)
        if executor:
            executor.cancel()
        result.status = ChainStepStatus.CANCELLED
        _running_executions[execution_id] = result
        return ChainCancelResponse(cancelled=True, execution_id=execution_id)

    return ChainCancelResponse(
        cancelled=False,
        execution_id=execution_id,
        message=f"Execution already in status: {result.status.value}",
    )


# =============================================================================
# Helper Functions
# =============================================================================


def _chain_to_response(chain: WorkflowChain) -> ChainResponse:
    """Convert domain model to response model."""
    return ChainResponse(
        id=chain.id,
        name=chain.name,
        description=chain.description,
        steps=[
            ChainStepResponse(
                id=s.id,
                workflow_id=s.workflow_id,
                name=s.name,
                input_mappings=[
                    OutputMappingRequest(
                        source_path=m.source_path,
                        target_key=m.target_key,
                        transform=m.transform,
                    )
                    for m in s.input_mappings
                ],
                static_inputs=s.static_inputs,
                condition=ChainStepConditionRequest(
                    expression=s.condition.expression,
                    true_step=s.condition.true_step,
                    false_step=s.condition.false_step,
                )
                if s.condition
                else None,
                continue_on_error=s.continue_on_error,
                timeout_seconds=s.timeout_seconds,
            )
            for s in chain.steps
        ],
        entry_step=chain.entry_step,
        initial_inputs=chain.initial_inputs,
        created_at=chain.created_at.isoformat(),
        updated_at=chain.updated_at.isoformat(),
        folder_path=chain.folder_path,
        sort_order=chain.sort_order,
    )
