"""
Workflow Chaining System

Allows workflows to be chained together, with the output of one workflow
becoming the input of the next.

Features:
- Define chains of workflows with output-to-input mappings
- Execute chains with progress tracking
- Support conditional branching between workflows
- Handle errors and partial completion
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import uuid
from datetime import datetime
from fichero_server.core.timeutil import utc_now
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field

from fichero_server.workflows.safe_condition import safe_eval_expression
from fichero_server.workflows.types import WorkflowDef
# NOTE: fichero_server.workflows.executor is imported at CALL time, not here (#3950).
# It pulls builder -> langgraph + every tool (Quartz, MCP). api/routes/chains.py
# imports this module for its chain *types*; actually executing a chain is what
# needs the executor. See the one use site in _run_chain below.

# Passthrough wrappers (#3950).
#
# Deferring these imports must not remove them as MODULE ATTRIBUTES: tests
# patch `fichero_server.execution.chaining.<name>`, which needs (1) the attribute to exist for mock.patch,
# and (2) the call site to resolve it as a module GLOBAL so the patch takes
# effect. A function-local import satisfies neither and would let those tests
# pass while silently running the real implementation.


def WorkflowExecutor(*args, **kwargs):
    """Passthrough to fichero_server.workflows.executor.WorkflowExecutor; imports it on first call (#3950)."""
    from fichero_server.workflows.executor import WorkflowExecutor as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


logger = logging.getLogger(__name__)


# =============================================================================
# Chain Definition Models
# =============================================================================


class ChainStepCondition(BaseModel):
    """Conditional execution for a chain step.

    Allows branching based on the output of the previous workflow.
    """

    expression: str = Field(
        ...,
        description="Python expression to evaluate (e.g., '$.outputs.category == \"invoice\"')",
    )
    true_step: str | None = Field(
        default=None,
        description="Step ID to execute if condition is true (None = continue to next)",
    )
    false_step: str | None = Field(
        default=None,
        description="Step ID to execute if condition is false (None = skip to end)",
    )


class OutputMapping(BaseModel):
    """Maps output from one workflow to input of the next.

    Supports path expressions like:
    - $.outputs.node_id.key  - Specific node output
    - $.outputs              - All outputs
    - $.files                - Output files from previous workflow
    """

    source_path: str = Field(
        ..., description="Path expression for source data from previous workflow"
    )
    target_key: str = Field(..., description="Input key name in the next workflow")
    transform: str | None = Field(
        default=None,
        description="Optional transformation (e.g., 'json_extract:$.name')",
    )


class ChainStep(BaseModel):
    """A single step in a workflow chain."""

    id: str = Field(..., description="Unique step identifier")
    workflow_id: str = Field(..., description="ID of workflow to execute")
    name: str = Field(default="", description="Display name for step")

    # Input mapping from previous step
    input_mappings: list[OutputMapping] = Field(
        default_factory=list,
        description="Maps outputs from previous workflow to inputs",
    )

    # Static inputs (added to mapped inputs)
    static_inputs: dict[str, Any] = Field(
        default_factory=dict, description="Additional static inputs for this step"
    )

    # Conditional execution
    condition: ChainStepCondition | None = Field(
        default=None, description="Condition for executing this step"
    )

    # Error handling
    continue_on_error: bool = Field(
        default=False, description="Continue chain even if this step fails"
    )

    # Execution settings
    timeout_seconds: int = Field(
        default=300, description="Max execution time for this step"
    )


class WorkflowChain(BaseModel):
    """Definition of a workflow chain.

    Chains multiple workflows together, passing outputs from one
    as inputs to the next.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Chain name")
    description: str = ""

    # Chain structure
    steps: list[ChainStep] = Field(
        default_factory=list, description="Ordered list of workflow steps"
    )

    # Entry point (first step to execute)
    entry_step: str | None = Field(
        default=None, description="ID of first step (defaults to first in list)"
    )

    # Initial inputs for the chain
    initial_inputs: dict[str, Any] = Field(
        default_factory=dict, description="Default initial inputs for the chain"
    )

    # Metadata
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    folder_path: str = "/"  # Folder organization path
    sort_order: int = 0  # Sort order within folder

    def get_step(self, step_id: str) -> ChainStep | None:
        """Get step by ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_next_step(self, current_step_id: str) -> ChainStep | None:
        """Get the next step after the given step."""
        for i, step in enumerate(self.steps):
            if step.id == current_step_id:
                if i + 1 < len(self.steps):
                    return self.steps[i + 1]
                return None
        return None


# =============================================================================
# Chain Execution State
# =============================================================================


class ChainStepStatus(str, Enum):
    """Status of a chain step execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChainStepResult(BaseModel):
    """Result of executing a chain step."""

    step_id: str
    workflow_id: str
    status: ChainStepStatus
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    output_files: list[str] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float = 0


class ChainExecutionResult(BaseModel):
    """Result of executing a complete chain."""

    chain_id: str
    execution_id: str
    status: ChainStepStatus
    step_results: list[ChainStepResult] = Field(default_factory=list)
    final_outputs: dict[str, Any] = Field(default_factory=dict)
    final_files: list[str] = Field(default_factory=list)
    total_duration_ms: float = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None


# =============================================================================
# Chain Event Types
# =============================================================================


class ChainEventType(str, Enum):
    """Types of chain execution events."""

    CHAIN_STARTED = "chain_started"
    CHAIN_COMPLETED = "chain_completed"
    CHAIN_FAILED = "chain_failed"
    CHAIN_CANCELLED = "chain_cancelled"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    STEP_SKIPPED = "step_skipped"


class ChainProgressEvent(BaseModel):
    """Progress event for chain execution."""

    event_type: ChainEventType
    chain_id: str
    execution_id: str
    step_id: str | None = None
    step_index: int | None = None
    total_steps: int = 0
    message: str = ""
    error: str | None = None
    progress: float = 0.0  # 0.0 to 1.0
    timestamp: datetime = Field(default_factory=utc_now)


# =============================================================================
# Output Resolver
# =============================================================================


def resolve_output_path(data: dict[str, Any], path: str) -> Any:
    """Resolve a path expression against workflow output data.

    Supports:
    - $.outputs.node_id.key  - Specific node output
    - $.outputs              - All outputs
    - $.files                - Output files
    - $.inputs.key           - Original inputs
    """
    if not path.startswith("$."):
        return path  # Literal value

    parts = path[2:].split(".")  # Remove "$." prefix
    current = data

    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if 0 <= idx < len(current) else None
        else:
            return None

        if current is None:
            return None

    return current


def map_outputs_to_inputs(
    previous_result: ChainStepResult,
    mappings: list[OutputMapping],
    static_inputs: dict[str, Any],
) -> dict[str, Any]:
    """Map outputs from previous workflow to inputs for next workflow."""
    # Start with static inputs
    inputs = dict(static_inputs)

    # Build source data from previous result
    source_data = {
        "outputs": previous_result.outputs,
        "files": previous_result.output_files,
        "inputs": previous_result.inputs,
    }

    # Apply mappings
    for mapping in mappings:
        value = resolve_output_path(source_data, mapping.source_path)
        if value is not None:
            # Apply transform if specified
            if mapping.transform:
                value = apply_transform(value, mapping.transform)
            inputs[mapping.target_key] = value

    return inputs


def apply_transform(value: Any, transform: str) -> Any:
    """Apply a transformation to a value.

    Supported transforms:
    - json_extract:$.path   - Extract from JSON
    - join:separator        - Join array elements
    - first                 - Get first element
    - last                  - Get last element
    - count                 - Get length
    """
    if ":" in transform:
        transform_name, transform_arg = transform.split(":", 1)
    else:
        transform_name = transform
        transform_arg = None

    if transform_name == "join" and isinstance(value, list):
        separator = transform_arg or ", "
        return separator.join(str(v) for v in value)

    elif transform_name == "first" and isinstance(value, list):
        return value[0] if value else None

    elif transform_name == "last" and isinstance(value, list):
        return value[-1] if value else None

    elif transform_name == "count":
        return len(value) if hasattr(value, "__len__") else 0

    elif transform_name == "json_extract" and transform_arg:
        return resolve_output_path({"$": value}, transform_arg.replace("$", "$."))

    return value


def evaluate_condition(condition: ChainStepCondition, data: dict[str, Any]) -> bool:
    """Evaluate a step condition against previous output data.

    Uses a safe expression evaluator that only allows comparison and logical operations.
    Supported operators: ==, !=, <, >, <=, >=, and, or, not, in, is
    Supported literals: strings, numbers, booleans, None, lists
    """
    expression = condition.expression

    # Replace path expressions with actual values
    path_pattern = r"\$\.[a-zA-Z0-9_.]+"

    def replace_path(match: re.Match) -> str:
        path = match.group(0)
        value = resolve_output_path(data, path)
        if isinstance(value, str):
            return f'"{value}"'
        elif value is None:
            return "None"
        elif isinstance(value, bool):
            return str(value)
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, list):
            return repr(value)
        else:
            return repr(str(value))

    resolved_expr = re.sub(path_pattern, replace_path, expression)

    try:
        result = safe_eval_expression(resolved_expr)
        return bool(result)
    except SyntaxError as e:
        logger.warning(f"Condition syntax error: {e}")
        return False
    except ValueError as e:
        logger.warning(f"Condition evaluation error: {e}")
        return False
    except Exception as e:
        logger.warning(f"Condition evaluation failed: {e}")
        return False


# =============================================================================
# Chain Executor
# =============================================================================


class ChainExecutor:
    """Executes workflow chains with progress tracking."""

    def __init__(
        self,
        workflow_loader: Callable[[str], WorkflowDef | None],
        event_callback: Callable[[ChainProgressEvent], None] | None = None,
    ):
        """Initialize chain executor.

        Args:
            workflow_loader: Function to load workflow definition by ID
            event_callback: Optional callback for progress events
        """
        self.workflow_loader = workflow_loader
        self.event_callback = event_callback
        self._cancel_requested = False

    def cancel(self) -> None:
        """Request cancellation of current execution."""
        self._cancel_requested = True

    async def execute(
        self,
        chain: WorkflowChain,
        initial_inputs: dict[str, Any] | None = None,
        initial_files: list[str] | None = None,
    ) -> ChainExecutionResult:
        """Execute a workflow chain.

        Args:
            chain: Chain definition to execute
            initial_inputs: Override initial inputs (merged with chain defaults)
            initial_files: Initial input files

        Returns:
            ChainExecutionResult with all step results
        """
        execution_id = str(uuid.uuid4())
        start_time = utc_now()
        self._cancel_requested = False

        # Merge initial inputs
        inputs = dict(chain.initial_inputs)
        if initial_inputs:
            inputs.update(initial_inputs)

        # Initialize result
        result = ChainExecutionResult(
            chain_id=chain.id,
            execution_id=execution_id,
            status=ChainStepStatus.PENDING,
            started_at=start_time,
        )

        # Emit chain started event
        await self._emit_event(
            ChainProgressEvent(
                event_type=ChainEventType.CHAIN_STARTED,
                chain_id=chain.id,
                execution_id=execution_id,
                total_steps=len(chain.steps),
                message=f"Starting chain '{chain.name}' with {len(chain.steps)} steps",
            )
        )

        try:
            # Determine first step
            current_step_id = chain.entry_step or (
                chain.steps[0].id if chain.steps else None
            )
            step_index = 0

            # Create initial "previous result" for first step
            previous_result = ChainStepResult(
                step_id="__initial__",
                workflow_id="",
                status=ChainStepStatus.COMPLETED,
                inputs=inputs,
                outputs={"inputs": inputs},
                output_files=initial_files or [],
            )

            # Execute chain steps
            while current_step_id:
                if self._cancel_requested:
                    result.status = ChainStepStatus.CANCELLED
                    await self._emit_event(
                        ChainProgressEvent(
                            event_type=ChainEventType.CHAIN_CANCELLED,
                            chain_id=chain.id,
                            execution_id=execution_id,
                            message="Chain execution cancelled",
                        )
                    )
                    break

                step = chain.get_step(current_step_id)
                if not step:
                    logger.error(f"Step not found: {current_step_id}")
                    break

                # Check condition if present
                if step.condition:
                    condition_data = {
                        "outputs": previous_result.outputs,
                        "files": previous_result.output_files,
                    }
                    condition_met = evaluate_condition(step.condition, condition_data)

                    if not condition_met:
                        # Skip this step
                        step_result = ChainStepResult(
                            step_id=step.id,
                            workflow_id=step.workflow_id,
                            status=ChainStepStatus.SKIPPED,
                        )
                        step_results = list(result.step_results or [])
                        step_results.append(step_result)
                        result.step_results = step_results

                        await self._emit_event(
                            ChainProgressEvent(
                                event_type=ChainEventType.STEP_SKIPPED,
                                chain_id=chain.id,
                                execution_id=execution_id,
                                step_id=step.id,
                                step_index=step_index,
                                total_steps=len(chain.steps),
                                message=f"Skipped step '{step.name or step.id}'",
                            )
                        )

                        # Determine next step based on condition
                        if step.condition.false_step:
                            current_step_id = step.condition.false_step
                        else:
                            next_step = chain.get_next_step(current_step_id)
                            current_step_id = next_step.id if next_step else None
                        step_index += 1
                        continue

                # Execute the step
                step_result = await self._execute_step(
                    chain=chain,
                    step=step,
                    previous_result=previous_result,
                    initial_inputs=inputs,
                    initial_files=initial_files or [],
                    execution_id=execution_id,
                    step_index=step_index,
                )
                step_results = list(result.step_results or [])
                step_results.append(step_result)
                result.step_results = step_results

                # Handle step failure
                if step_result.status == ChainStepStatus.FAILED:
                    if not step.continue_on_error:
                        result.status = ChainStepStatus.FAILED
                        await self._emit_event(
                            ChainProgressEvent(
                                event_type=ChainEventType.CHAIN_FAILED,
                                chain_id=chain.id,
                                execution_id=execution_id,
                                step_id=step.id,
                                error=step_result.error,
                                message=f"Chain failed at step '{step.name or step.id}'",
                            )
                        )
                        break

                # Update previous result for next step
                previous_result = step_result

                # Determine next step
                if step.condition and step.condition.true_step:
                    current_step_id = step.condition.true_step
                else:
                    next_step = chain.get_next_step(current_step_id)
                    current_step_id = next_step.id if next_step else None

                step_index += 1

            # Finalize result
            if result.status == ChainStepStatus.PENDING:
                result.status = ChainStepStatus.COMPLETED
                result.final_outputs = previous_result.outputs
                result.final_files = previous_result.output_files

                await self._emit_event(
                    ChainProgressEvent(
                        event_type=ChainEventType.CHAIN_COMPLETED,
                        chain_id=chain.id,
                        execution_id=execution_id,
                        total_steps=len(chain.steps),
                        progress=1.0,
                        message=f"Chain '{chain.name}' completed successfully",
                    )
                )

            result.completed_at = utc_now()
            result.total_duration_ms = (
                result.completed_at - start_time
            ).total_seconds() * 1000

            return result

        except Exception as e:
            logger.exception(f"Chain execution failed: {e}")
            result.status = ChainStepStatus.FAILED
            result.completed_at = utc_now()

            await self._emit_event(
                ChainProgressEvent(
                    event_type=ChainEventType.CHAIN_FAILED,
                    chain_id=chain.id,
                    execution_id=execution_id,
                    error=str(e),
                    message=f"Chain failed with error: {e}",
                )
            )

            return result

    async def _execute_step(
        self,
        chain: WorkflowChain,
        step: ChainStep,
        previous_result: ChainStepResult,
        initial_inputs: dict[str, Any],
        initial_files: list[str],
        execution_id: str,
        step_index: int,
    ) -> ChainStepResult:
        """Execute a single chain step."""
        start_time = utc_now()

        # Emit step started event
        await self._emit_event(
            ChainProgressEvent(
                event_type=ChainEventType.STEP_STARTED,
                chain_id=chain.id,
                execution_id=execution_id,
                step_id=step.id,
                step_index=step_index,
                total_steps=len(chain.steps),
                progress=step_index / len(chain.steps),
                message=f"Starting step '{step.name or step.id}'",
            )
        )

        # Load workflow
        workflow = self.workflow_loader(step.workflow_id)
        if not workflow:
            return ChainStepResult(
                step_id=step.id,
                workflow_id=step.workflow_id,
                status=ChainStepStatus.FAILED,
                error=f"Workflow not found: {step.workflow_id}",
                started_at=start_time,
                completed_at=utc_now(),
            )

        # Map inputs from previous step
        step_inputs = map_outputs_to_inputs(
            previous_result=previous_result,
            mappings=step.input_mappings,
            static_inputs=step.static_inputs,
        )
        step_inputs = {**initial_inputs, **step_inputs}

        # Get input files from previous step
        input_files = previous_result.output_files or initial_files

        try:
            # Create executor for this workflow
            executor = WorkflowExecutor(workflow)

            # Execute with timeout
            final_state = await asyncio.wait_for(
                executor.execute(
                    inputs=step_inputs,
                    input_files=input_files,
                ),
                timeout=step.timeout_seconds,
            )

            # Check for workflow error
            if final_state.get("error"):
                return ChainStepResult(
                    step_id=step.id,
                    workflow_id=step.workflow_id,
                    status=ChainStepStatus.FAILED,
                    inputs=step_inputs,
                    outputs=final_state.get("outputs", {}),
                    output_files=final_state.get("output_files", []),
                    error=final_state["error"],
                    started_at=start_time,
                    completed_at=utc_now(),
                    duration_ms=(utc_now() - start_time).total_seconds() * 1000,
                )

            # Success
            completed_at = utc_now()
            result = ChainStepResult(
                step_id=step.id,
                workflow_id=step.workflow_id,
                status=ChainStepStatus.COMPLETED,
                inputs=step_inputs,
                outputs=final_state.get("outputs", {}),
                output_files=final_state.get("output_files", []),
                started_at=start_time,
                completed_at=completed_at,
                duration_ms=(completed_at - start_time).total_seconds() * 1000,
            )

            await self._emit_event(
                ChainProgressEvent(
                    event_type=ChainEventType.STEP_COMPLETED,
                    chain_id=chain.id,
                    execution_id=execution_id,
                    step_id=step.id,
                    step_index=step_index,
                    total_steps=len(chain.steps),
                    progress=(step_index + 1) / len(chain.steps),
                    message=f"Completed step '{step.name or step.id}'",
                )
            )

            return result

        except asyncio.TimeoutError:
            return ChainStepResult(
                step_id=step.id,
                workflow_id=step.workflow_id,
                status=ChainStepStatus.FAILED,
                inputs=step_inputs,
                error=f"Step timed out after {step.timeout_seconds}s",
                started_at=start_time,
                completed_at=utc_now(),
                duration_ms=(utc_now() - start_time).total_seconds() * 1000,
            )

        except Exception as e:
            logger.exception(f"Step execution failed: {e}")

            await self._emit_event(
                ChainProgressEvent(
                    event_type=ChainEventType.STEP_FAILED,
                    chain_id=chain.id,
                    execution_id=execution_id,
                    step_id=step.id,
                    step_index=step_index,
                    error=str(e),
                    message=f"Step '{step.name or step.id}' failed: {e}",
                )
            )

            return ChainStepResult(
                step_id=step.id,
                workflow_id=step.workflow_id,
                status=ChainStepStatus.FAILED,
                inputs=step_inputs,
                error=str(e),
                started_at=start_time,
                completed_at=utc_now(),
                duration_ms=(utc_now() - start_time).total_seconds() * 1000,
            )

    async def _emit_event(self, event: ChainProgressEvent) -> None:
        """Emit a progress event."""
        if self.event_callback:
            try:
                if inspect.iscoroutinefunction(self.event_callback):
                    await self.event_callback(event)
                else:
                    self.event_callback(event)
            except Exception as e:
                logger.warning(f"Event callback failed: {e}")


# =============================================================================
# Chain Store (In-Memory for now)
# =============================================================================


class ChainStore:
    """Manages workflow chain definitions.

    Currently stores in memory; could be extended to persist to database.
    """

    def __init__(self):
        self._chains: dict[str, WorkflowChain] = {}

    def save(self, chain: WorkflowChain) -> WorkflowChain:
        """Save a chain definition."""
        chain.updated_at = utc_now()
        self._chains[chain.id] = chain
        return chain

    def get(self, chain_id: str) -> WorkflowChain | None:
        """Get a chain by ID."""
        return self._chains.get(chain_id)

    def list(self, limit: int = 50, offset: int = 0) -> list[WorkflowChain]:
        """List all chains."""
        chains = sorted(
            self._chains.values(),
            key=lambda c: c.updated_at,
            reverse=True,
        )
        return chains[offset : offset + limit]

    def delete(self, chain_id: str) -> bool:
        """Delete a chain by ID."""
        if chain_id in self._chains:
            del self._chains[chain_id]
            return True
        return False


# Global chain store instance
chain_store = ChainStore()
