"""
API Routes for Workflow Chains

Provides endpoints for managing and executing workflow chains.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from fichero_server.execution.chaining import (
    WorkflowChain,
    ChainStep,
    OutputMapping,
    ChainStepCondition,
    ChainEventType,
    ChainExecutor,
    ChainExecutionResult,
    ChainProgressEvent,
    ChainStepResult,
    ChainStepStatus,
    chain_store,
)
from fichero_server.workflows.types import WorkflowDef
from fichero_server.workflows.workflow_store import WorkflowStore
from fichero_server.db import db_manager
from fichero_server.api.library_header import require_library_path
from fichero_server.api.main import assert_library_read_authorized

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
    provider_override: str | None = Field(
        default=None, description="Provider override for this step's run"
    )
    model_override: str | None = Field(
        default=None, description="Model override for this step's run"
    )


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
    provider_override: str | None = Field(
        default=None, description="Provider override for this step's run"
    )
    model_override: str | None = Field(
        default=None, description="Model override for this step's run"
    )


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


class ExecuteChainStepsRequest(BaseModel):
    """Request to run a chain's steps as real, sequential workflow runs.

    The workflow bar's staged chain rides this (2026-08-30): every step is a
    full workflow execution — thread id, SSE stream, activity record — with
    the SAME frozen inputs (the selection the user pressed play on), plus the
    step's own static_inputs merged on top.
    """

    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form JSON run inputs shared by every step (frozen selection, "
            "user context, hints). Each step merges its static_inputs on top. "
            "Values stay workflow-defined and are not coerced."
        ),
    )


class ChainStepThreadInfo(BaseModel):
    """One chain step's pre-assigned workflow-run identity."""

    step_id: str
    workflow_id: str
    name: str = ""
    thread_id: str
    stream_url: str


class ChainStepsAcceptedResponse(BaseModel):
    """202 body for POST /chains/{chain_id}/execute-steps.

    Thread ids are assigned up front so a client can watch any step's run
    (SSE stream, Activity trace) the moment it starts.
    """

    execution_id: str
    chain_id: str
    status: str
    steps: list[ChainStepThreadInfo]


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

    Resolves the id in the library first, then as a global DEFAULT
    (#4450/#4139) — a chain step referencing a shipped preset must run in
    every library, while the run stays pinned to `library_path`.

    Args:
        library_path: Path to the .fichero library

    Returns:
        Function that loads workflows by ID
    """

    def loader(workflow_id: str) -> WorkflowDef | None:
        from fichero_server.workflows.default_workflows import (
            resolve_default_workflow,
        )
        from fichero_server.workflows.runtime import to_workflow_def

        try:
            db = db_manager.get_database(library_path)
            store = WorkflowStore(db)
            workflow = store.get(workflow_id) or resolve_default_workflow(workflow_id)
            if workflow is None:
                return None
            # #4139: this used to read `workflow.definition` — an attribute
            # the Workflow model has never had — so the AttributeError was
            # swallowed below and EVERY chain step resolved to None. The
            # model's real shape is nodes/edges; to_workflow_def is the one
            # shared normalizer (same one /execute validation uses).
            return to_workflow_def(workflow)
        except Exception as e:
            logger.error(f"Failed to load workflow {workflow_id}: {e}")
            return None

    return loader


def _chain_candidate_workflows(db, library_path: str) -> list[Any]:
    """This library's workflows plus the app's DEFAULTS (#4450/#4139).

    Defaults live only in the global library (#4102); building a chain from
    ``store.list_all()`` alone meant a non-global library could never match
    "Transcribe Paleography" and the scorer fell back to whatever generic
    user workflow contained "transcribe" — the exact defect in #4139. The
    library's own row wins on an id collision.
    """
    from fichero_server.db.paths import is_global_library_package
    from fichero_server.workflows.default_workflows import (
        list_global_default_workflows,
    )

    workflows = WorkflowStore(db).list_all()
    if not is_global_library_package(library_path):
        present = {w.id for w in workflows}
        workflows += [
            w for w in list_global_default_workflows() if w.id not in present
        ]
    return workflows


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
                provider_override=step_req.provider_override,
                model_override=step_req.model_override,
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
                    provider_override=step_req.provider_override,
                    model_override=step_req.model_override,
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
    chain, matched = _build_paleography_chain(
        _chain_candidate_workflows(db, x_fichero_library_path)
    )
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
    chain, matched = _build_paleography_chain(
        _chain_candidate_workflows(db, x_fichero_library_path)
    )
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
# Step-wise Chain Execution (workflow bar, 2026-08-30)
# =============================================================================
#
# The legacy /execute endpoint runs a chain through the standalone
# ChainExecutor/WorkflowExecutor path: no thread ids, no SSE, no activity
# records, no per-step model overrides. The workflow bar's staged chain needs
# each step to be a REAL workflow run — the same machinery as
# /api/workflow-execution/execute — so /execute-steps runs the chain's steps
# IN LIST ORDER, one full workflow execution per step, sequential because
# step N+1 reads what step N wrote, stopping on failure unless the step says
# continue_on_error. Conditions/entry_step/output-mappings are the legacy
# executor's graph semantics and are deliberately NOT honored here.

# Runner threads by execution id — lets tests join deterministically, and a
# debugger see which chain owns which thread.
_running_step_threads: dict[str, threading.Thread] = {}


class _ChainStepsCanceller:
    """Cancel flag checked between steps; registered in _running_executors so
    the existing DELETE /executions/{id} endpoint cancels this path too."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled


# Passthrough seams (same pattern as chaining.py's WorkflowExecutor, #3950):
# deferred imports kept as MODULE attributes so tests can patch
# `fichero_server.api.routes.workflow.chains.<name>` and the call sites
# resolve the patched global.


def _acquire_chain_db(library_path: str):
    """This worker thread's Database for the library (thread-keyed, #1000)."""
    return db_manager.get_database(library_path)


def _load_step_workflow(db, workflow_id: str):
    """Load the step's Workflow model: this library first, then a shipped
    DEFAULT (#4450/#4139) — same resolution as /workflow-execution/execute."""
    from fichero_server.workflows.default_workflows import (  # noqa: PLC0415
        resolve_default_workflow,
    )

    return WorkflowStore(db).get(workflow_id) or resolve_default_workflow(workflow_id)


def _validate_step_workflow(workflow, request, db) -> None:
    """Same preflight as a direct run — including run-eligibility of the
    step's provider/model override (#3804)."""
    from fichero_server.api.routes.workflow_execution.core import (  # noqa: PLC0415
        _validate_workflow_for_execution,
    )

    _validate_workflow_for_execution(workflow, request, db)


async def _record_step_run_accepted(db, thread_id: str, workflow, request) -> None:
    """The same activity row a direct run writes at accept time."""
    from fichero_server.workflows.activity import get_activity_tracker  # noqa: PLC0415

    await get_activity_tracker(str(db.path)).store.save_workflow_run(
        thread_id=thread_id,
        workflow_id=request.workflow_id,
        workflow_name=workflow.name,
        status="accepted",
        workflow_snapshot={
            "nodes": workflow.nodes,
            "edges": workflow.edges,
            "inputs": request.inputs,
        },
    )


async def _run_step_workflow(*, thread_id: str, workflow, request, db) -> None:
    """Passthrough to the REAL background runner — SSE events, pause/cancel,
    caches, document finalization — exactly as a direct run gets."""
    from fichero_server.execution.runner import (  # noqa: PLC0415
        _run_workflow_in_background,
    )

    await _run_workflow_in_background(
        thread_id=thread_id, workflow=workflow, request=request, db=db
    )


def _step_run_outcome(thread_id: str) -> tuple[str, str | None]:
    """(status, error) the run settled with, read from the workflow state the
    runner maintains ('completed' / 'failed' / 'cancelled')."""
    from fichero_server.execution.runner import _get_workflow_state  # noqa: PLC0415

    state = _get_workflow_state(thread_id) or {}
    error = state.get("error")
    return state.get("status", "failed"), str(error) if error else None


def _set_step_result(
    result: ChainExecutionResult,
    index: int,
    step: ChainStep,
    status: ChainStepStatus,
    error: str | None = None,
) -> None:
    """Replace one step's result IN PLACE in the tracked execution, so a
    status poll mid-run reports exactly the steps that have settled."""
    updated = list(result.step_results)
    updated[index] = ChainStepResult(
        step_id=step.id,
        workflow_id=step.workflow_id,
        status=status,
        error=error,
    )
    result.step_results = updated


def _emit_step_event(
    execution_id: str,
    chain: WorkflowChain,
    event_type: ChainEventType,
    step: ChainStep | None = None,
    step_index: int | None = None,
    message: str = "",
    error: str | None = None,
) -> None:
    total = len(chain.steps) or 1
    done = (step_index + 1) if step_index is not None else 0
    _on_chain_event(
        ChainProgressEvent(
            event_type=event_type,
            chain_id=chain.id,
            execution_id=execution_id,
            step_id=step.id if step else None,
            step_index=step_index,
            total_steps=len(chain.steps),
            message=message,
            error=error,
            progress=min(1.0, done / total),
        )
    )


async def _run_chain_steps(
    execution_id: str,
    chain: WorkflowChain,
    step_threads: list[tuple[ChainStep, str]],
    inputs: dict[str, Any],
    library_path: str,
    canceller: _ChainStepsCanceller,
) -> None:
    """Run the chain's steps sequentially through the real workflow runner."""
    from fichero_server.api.routes.workflow_execution.schemas import (  # noqa: PLC0415
        ExecuteWorkflowRequest,
    )
    from fichero_server.core.timeutil import utc_now  # noqa: PLC0415

    result = _running_executions[execution_id]
    result.started_at = utc_now()
    failed = False
    _emit_step_event(
        execution_id,
        chain,
        ChainEventType.CHAIN_STARTED,
        message=f"Starting chain '{chain.name}' with {len(chain.steps)} steps",
    )

    db = _acquire_chain_db(library_path)
    for index, (step, thread_id) in enumerate(step_threads):
        if failed or canceller.cancelled:
            # Later chips stay visibly un-run: the rail shows exactly where
            # the chain stopped, mirroring the client loop it replaces.
            _set_step_result(result, index, step, ChainStepStatus.SKIPPED)
            _emit_step_event(
                execution_id, chain, ChainEventType.STEP_SKIPPED, step, index,
                message=f"Skipped step '{step.name or step.id}'",
            )
            continue

        error: str | None = None
        workflow = _load_step_workflow(db, step.workflow_id)
        exec_request = None
        if workflow is None:
            error = f"Workflow not found: {step.workflow_id}"
        else:
            exec_request = ExecuteWorkflowRequest(
                workflow_id=step.workflow_id,
                # The frozen chain inputs ride every step; the step's own
                # static_inputs win on a key collision.
                inputs={**inputs, **step.static_inputs},
                thread_id=thread_id,
                provider_override=step.provider_override,
                model_override=step.model_override,
            )
            try:
                _validate_step_workflow(workflow, exec_request, db)
            except HTTPException as exc:
                error = str(exc.detail)
            except Exception as exc:  # pragma: no cover - defensive
                error = str(exc)

        if error is None:
            _set_step_result(result, index, step, ChainStepStatus.RUNNING)
            _emit_step_event(
                execution_id, chain, ChainEventType.STEP_STARTED, step, index,
                message=f"Starting step '{step.name or step.id}'",
            )
            try:
                await _record_step_run_accepted(db, thread_id, workflow, exec_request)
                await _run_step_workflow(
                    thread_id=thread_id,
                    workflow=workflow,
                    request=exec_request,
                    db=db,
                )
            except Exception as exc:
                logger.exception(f"Chain step run failed: {exc}")
                error = str(exc)
            if error is None:
                status_str, run_error = _step_run_outcome(thread_id)
                if status_str != "completed" or run_error:
                    error = run_error or f"Run ended with status: {status_str}"

        if error is None:
            _set_step_result(result, index, step, ChainStepStatus.COMPLETED)
            _emit_step_event(
                execution_id, chain, ChainEventType.STEP_COMPLETED, step, index,
                message=f"Completed step '{step.name or step.id}'",
            )
        else:
            _set_step_result(result, index, step, ChainStepStatus.FAILED, error)
            _emit_step_event(
                execution_id, chain, ChainEventType.STEP_FAILED, step, index,
                message=f"Step '{step.name or step.id}' failed", error=error,
            )
            # The engine owns stop-on-failure: the review pass must not spend
            # money on the transcription that does not exist.
            if not step.continue_on_error:
                failed = True

    if canceller.cancelled or result.status == ChainStepStatus.CANCELLED:
        result.status = ChainStepStatus.CANCELLED
        _emit_step_event(
            execution_id, chain, ChainEventType.CHAIN_CANCELLED,
            message="Chain execution cancelled",
        )
    elif failed:
        result.status = ChainStepStatus.FAILED
        _emit_step_event(
            execution_id, chain, ChainEventType.CHAIN_FAILED,
            message=f"Chain '{chain.name}' failed",
        )
    else:
        result.status = ChainStepStatus.COMPLETED
        _emit_step_event(
            execution_id, chain, ChainEventType.CHAIN_COMPLETED,
            message=f"Chain '{chain.name}' completed successfully",
        )
    result.completed_at = utc_now()
    if result.started_at:
        result.total_duration_ms = (
            result.completed_at - result.started_at
        ).total_seconds() * 1000


def _chain_steps_thread_main(
    execution_id: str,
    chain: WorkflowChain,
    step_threads: list[tuple[ChainStep, str]],
    inputs: dict[str, Any],
    library_path: str,
    canceller: _ChainStepsCanceller,
) -> None:
    """Thread entry: own event loop (#1000 — a blocking tool node must never
    freeze the API loop), settle tracking however the run ends."""
    try:
        asyncio.run(
            _run_chain_steps(
                execution_id, chain, step_threads, inputs, library_path, canceller
            )
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(f"Chain step execution crashed: {exc}")
        result = _running_executions.get(execution_id)
        if result is not None and result.status not in (
            ChainStepStatus.COMPLETED,
            ChainStepStatus.CANCELLED,
        ):
            result.status = ChainStepStatus.FAILED
    finally:
        _running_executors.pop(execution_id, None)
        _running_step_threads.pop(execution_id, None)


@router.post(
    "/{chain_id}/execute-steps",
    response_model=ChainStepsAcceptedResponse,
    status_code=202,
)
async def execute_chain_steps(
    chain_id: str,
    request: ExecuteChainStepsRequest,
    http_request: Request,
    x_fichero_library_path: str = Depends(require_library_path),
) -> ChainStepsAcceptedResponse:
    """Run a chain's steps as real, sequential workflow runs (workflow bar).

    202 with a pre-assigned thread id per step; poll
    GET /chains/executions/{execution_id} for per-step statuses, or attach to
    any step's SSE stream_url as it runs.
    """
    chain = chain_store.get(chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail=f"Chain not found: {chain_id}")
    if not chain.steps:
        raise HTTPException(status_code=400, detail="Chain has no steps to run")
    assert_library_read_authorized(http_request, x_fichero_library_path)

    # Register per-step workflow state UP FRONT (light import — dict writes
    # and a hub), so a client can attach to a step's SSE stream before the
    # step starts and the stream endpoint recognizes the thread.
    from fichero_server.execution.runner import (  # noqa: PLC0415
        WorkflowEventHub,
        _set_workflow_state,
    )

    execution_id = str(uuid.uuid4())
    step_threads: list[tuple[ChainStep, str]] = []
    for step in chain.steps:
        thread_id = f"thread-{uuid.uuid4().hex[:12]}"
        step_threads.append((step, thread_id))
        _set_workflow_state(
            thread_id,
            {
                "workflow_id": step.workflow_id,
                "workflow_name": step.name or step.workflow_id,
                "status": "accepted",
                "events": WorkflowEventHub(),
                "error": None,
                "final_state": None,
            },
        )

    # Track the execution through the SAME registries the legacy path uses,
    # so status/cancel endpoints serve both. Status stays PENDING while
    # running (legacy-compatible: cancel requires it; pollers key on the
    # terminal statuses). Step results are pre-seeded so a poll lists every
    # step from the first second.
    _execution_order.append(execution_id)
    _evict_old_executions()
    _execution_events[execution_id] = []
    tracked = ChainExecutionResult(
        chain_id=chain_id,
        execution_id=execution_id,
        status=ChainStepStatus.PENDING,
        step_results=[
            ChainStepResult(
                step_id=step.id,
                workflow_id=step.workflow_id,
                status=ChainStepStatus.PENDING,
            )
            for step, _ in step_threads
        ],
    )
    _running_executions[execution_id] = tracked
    canceller = _ChainStepsCanceller()
    _running_executors[execution_id] = canceller

    runner = threading.Thread(
        target=_chain_steps_thread_main,
        args=(
            execution_id,
            chain,
            step_threads,
            dict(request.inputs),
            x_fichero_library_path,
            canceller,
        ),
        name=f"chain-steps-{execution_id[:8]}",
        daemon=True,
    )
    _running_step_threads[execution_id] = runner
    runner.start()

    base_url = str(http_request.base_url).rstrip("/")
    return ChainStepsAcceptedResponse(
        execution_id=execution_id,
        chain_id=chain_id,
        status="running",
        steps=[
            ChainStepThreadInfo(
                step_id=step.id,
                workflow_id=step.workflow_id,
                name=step.name,
                thread_id=thread_id,
                stream_url=f"{base_url}/api/workflow-execution/stream/{thread_id}",
            )
            for step, thread_id in step_threads
        ],
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
                provider_override=s.provider_override,
                model_override=s.model_override,
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
