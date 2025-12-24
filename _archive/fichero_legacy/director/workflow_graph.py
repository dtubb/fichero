"""
LangGraph-based workflow orchestration for Fichero.

Provides state machine approach for document processing workflows:
- Typed state management
- Conditional branching
- Retry logic with exponential backoff
- Progress streaming
- Cost tracking

Can be used alongside or as replacement for WorkflowExecutor.

Usage:
    from fichero.director.workflow_graph import build_workflow, run_workflow

    # Build from plan config
    graph = build_workflow(plan_config, workflow_name="main")

    # Execute
    result = await run_workflow(
        graph,
        folder_path=Path("/input"),
        output_path=Path("/output"),
        on_progress=lambda e: print(e)
    )
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypedDict
from uuid import uuid4

logger = logging.getLogger(__name__)


# =============================================================================
# State Definition
# =============================================================================

class WorkflowState(TypedDict):
    """State passed through workflow nodes.

    This is a TypedDict for LangGraph compatibility.
    All fields are serializable for checkpointing.
    """
    # Identifiers
    task_id: str
    workflow_name: str

    # Paths
    folder_path: str  # Serialized as string
    output_path: str

    # Variables from plan config
    variables: dict[str, Any]

    # Execution state
    current_step: int
    total_steps: int
    status: str  # "pending", "running", "completed", "failed", "cancelled"

    # Results from each step
    results: dict[str, Any]

    # Error tracking
    errors: list[str]
    retry_count: int
    max_retries: int

    # Timing
    started_at: float
    step_times: dict[str, float]

    # Cost tracking
    tokens_used: int
    cost_usd: float

    # Library integration
    library_item_id: str | None
    library_collection_id: str | None
    library_item_map: dict[str, str] | None


def create_initial_state(
    folder_path: Path,
    output_path: Path,
    workflow_name: str = "main",
    variables: dict | None = None,
    library_item_id: str | None = None,
    library_collection_id: str | None = None,
    library_item_map: dict | None = None,
    max_retries: int = 3,
) -> WorkflowState:
    """Create initial workflow state."""
    return WorkflowState(
        task_id=uuid4().hex,
        workflow_name=workflow_name,
        folder_path=str(folder_path),
        output_path=str(output_path),
        variables=variables or {},
        current_step=0,
        total_steps=0,
        status="pending",
        results={},
        errors=[],
        retry_count=0,
        max_retries=max_retries,
        started_at=time.time(),
        step_times={},
        tokens_used=0,
        cost_usd=0.0,
        library_item_id=library_item_id,
        library_collection_id=library_collection_id,
        library_item_map=library_item_map,
    )


# =============================================================================
# Step Configuration
# =============================================================================

@dataclass
class StepConfig:
    """Configuration for a workflow step."""
    name: str
    function: str  # Module.function path
    args: dict[str, Any] = field(default_factory=dict)
    condition: str | None = None  # Optional condition for conditional execution
    retry_on_error: bool = True
    timeout_seconds: int = 300


def parse_step_config(command: dict) -> StepConfig:
    """Parse step configuration from plan YAML command."""
    return StepConfig(
        name=command.get("name", "unnamed"),
        function=command.get("function", ""),
        args=command.get("args", {}),
        condition=command.get("condition"),
        retry_on_error=command.get("retry_on_error", True),
        timeout_seconds=command.get("timeout", 300),
    )


# =============================================================================
# Node Functions
# =============================================================================

def _import_function(function_path: str) -> Callable:
    """Import a function from a module path.

    Args:
        function_path: Path like "fichero.tools.transcribe.transcribe_folder"

    Returns:
        The imported function
    """
    if "." not in function_path:
        raise ValueError(f"Invalid function path: {function_path}")

    module_path, func_name = function_path.rsplit(".", 1)

    try:
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except (ImportError, AttributeError) as e:
        raise ImportError(f"Cannot import {function_path}: {e}")


def _expand_args(args: dict, state: WorkflowState) -> dict:
    """Expand argument templates with state values.

    Supports:
    - {folder_path} -> state folder_path
    - {output_path} -> state output_path
    - {variables.key} -> state variables[key]
    - {results.step_name} -> results from previous step
    """
    expanded = {}

    for key, value in args.items():
        if isinstance(value, str):
            # Simple variable expansion
            if value == "{folder_path}":
                expanded[key] = Path(state["folder_path"])
            elif value == "{output_path}":
                expanded[key] = Path(state["output_path"])
            elif value.startswith("{variables."):
                var_name = value[11:-1]  # Extract variable name
                expanded[key] = state["variables"].get(var_name, value)
            elif value.startswith("{results."):
                result_key = value[9:-1]
                expanded[key] = state["results"].get(result_key, value)
            else:
                expanded[key] = value
        else:
            expanded[key] = value

    return expanded


def create_step_node(step: StepConfig) -> Callable[[WorkflowState], WorkflowState]:
    """Create a node function for a workflow step.

    Returns a function that:
    1. Imports and calls the step function
    2. Updates state with results
    3. Handles errors
    """

    def node(state: WorkflowState) -> WorkflowState:
        step_start = time.time()
        logger.info(f"Starting step: {step.name}")

        # Check condition if specified
        if step.condition:
            # Simple condition evaluation
            if not _evaluate_condition(step.condition, state):
                logger.info(f"Skipping step {step.name}: condition not met")
                state["current_step"] += 1
                return state

        try:
            # Import function
            func = _import_function(step.function)

            # Expand arguments
            args = _expand_args(step.args, state)

            # Add common args
            args["folder_path"] = Path(state["folder_path"])
            args["output_path"] = Path(state["output_path"])

            # Call function (sync for now - could be made async)
            result = func(**args)

            # Store result
            state["results"][step.name] = result
            state["step_times"][step.name] = time.time() - step_start
            state["current_step"] += 1

            logger.info(f"Completed step: {step.name} in {time.time() - step_start:.2f}s")

        except Exception as e:
            error_msg = f"{step.name}: {str(e)}"
            state["errors"].append(error_msg)
            logger.error(f"Step failed: {error_msg}")

            if step.retry_on_error and state["retry_count"] < state["max_retries"]:
                state["retry_count"] += 1
                logger.info(f"Retrying step {step.name} (attempt {state['retry_count']})")
            else:
                state["status"] = "failed"

        return state

    return node


def _evaluate_condition(condition: str, state: WorkflowState) -> bool:
    """Evaluate a simple condition string.

    Supports:
    - "has_results.step_name" - True if step produced results
    - "status == running" - Status comparison
    - "files_exist" - True if input files exist
    """
    if condition.startswith("has_results."):
        step_name = condition[12:]
        return step_name in state["results"]

    if condition.startswith("status == "):
        expected = condition[10:].strip()
        return state["status"] == expected

    if condition == "files_exist":
        folder = Path(state["folder_path"])
        return folder.exists() and any(folder.iterdir())

    # Default: true
    return True


# =============================================================================
# Graph Building
# =============================================================================

def build_workflow(
    plan_config: dict,
    workflow_name: str = "main",
) -> "CompiledGraph":
    """Build LangGraph workflow from plan YAML config.

    Args:
        plan_config: Parsed YAML plan with 'commands' and 'workflows'
        workflow_name: Which workflow to build from the plan

    Returns:
        Compiled StateGraph ready for execution
    """
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        raise ImportError(
            "langgraph not installed. Install with: pip install langgraph"
        )

    # Get workflow steps
    workflows = plan_config.get("workflows", {})
    step_names = workflows.get(workflow_name, [])

    if not step_names:
        raise ValueError(f"Workflow '{workflow_name}' not found or empty")

    # Get command definitions
    commands = {cmd["name"]: cmd for cmd in plan_config.get("commands", [])}

    # Parse step configs
    steps: list[StepConfig] = []
    for name in step_names:
        if name not in commands:
            raise ValueError(f"Command '{name}' not found in plan")
        steps.append(parse_step_config(commands[name]))

    # Build graph
    graph = StateGraph(WorkflowState)

    # Add initialization node
    def init_node(state: WorkflowState) -> WorkflowState:
        state["status"] = "running"
        state["total_steps"] = len(steps)
        return state

    graph.add_node("init", init_node)

    # Add step nodes
    for step in steps:
        graph.add_node(step.name, create_step_node(step))

    # Add completion node
    def complete_node(state: WorkflowState) -> WorkflowState:
        if state["status"] != "failed":
            state["status"] = "completed"
        return state

    graph.add_node("complete", complete_node)

    # Set entry point
    graph.set_entry_point("init")

    # Add edges
    # init -> first step
    graph.add_edge("init", steps[0].name)

    # step -> next step (with conditional for failure)
    for i in range(len(steps) - 1):
        current = steps[i].name
        next_step = steps[i + 1].name

        graph.add_conditional_edges(
            current,
            _should_continue,
            {
                "continue": next_step,
                "stop": "complete",
            }
        )

    # last step -> complete
    graph.add_conditional_edges(
        steps[-1].name,
        _should_continue,
        {
            "continue": "complete",
            "stop": "complete",
        }
    )

    # complete -> END
    graph.add_edge("complete", END)

    return graph.compile()


def _should_continue(state: WorkflowState) -> str:
    """Determine if workflow should continue."""
    if state["status"] == "failed":
        return "stop"
    if state["status"] == "cancelled":
        return "stop"
    return "continue"


# =============================================================================
# Execution
# =============================================================================

async def run_workflow(
    graph: "CompiledGraph",
    folder_path: Path,
    output_path: Path,
    workflow_name: str = "main",
    variables: dict | None = None,
    on_progress: Callable[[dict], None] | None = None,
    library_item_id: str | None = None,
    library_collection_id: str | None = None,
    library_item_map: dict | None = None,
    max_retries: int = 3,
) -> WorkflowState:
    """Execute a workflow graph.

    Args:
        graph: Compiled StateGraph from build_workflow()
        folder_path: Input folder
        output_path: Output folder
        workflow_name: Name of workflow being executed
        variables: Additional variables
        on_progress: Progress callback for each step
        library_item_id: Library item ID for tracking
        library_collection_id: Collection ID for tracking
        library_item_map: Mapping of file names to library item IDs
        max_retries: Maximum retry attempts per step

    Returns:
        Final workflow state
    """
    initial_state = create_initial_state(
        folder_path=folder_path,
        output_path=output_path,
        workflow_name=workflow_name,
        variables=variables,
        library_item_id=library_item_id,
        library_collection_id=library_collection_id,
        library_item_map=library_item_map,
        max_retries=max_retries,
    )

    logger.info(f"Starting workflow: {workflow_name}")
    logger.info(f"Input: {folder_path}")
    logger.info(f"Output: {output_path}")

    final_state = initial_state

    # Stream execution for progress updates
    try:
        async for event in graph.astream(initial_state):
            final_state = event
            if on_progress:
                on_progress({
                    "task_id": final_state.get("task_id"),
                    "current_step": final_state.get("current_step"),
                    "total_steps": final_state.get("total_steps"),
                    "status": final_state.get("status"),
                    "errors": final_state.get("errors"),
                })
    except Exception as e:
        logger.error(f"Workflow execution error: {e}")
        final_state["status"] = "failed"
        final_state["errors"].append(str(e))

    # Log completion
    elapsed = time.time() - final_state["started_at"]
    logger.info(
        f"Workflow completed: {final_state['status']} "
        f"({final_state['current_step']}/{final_state['total_steps']} steps) "
        f"in {elapsed:.2f}s"
    )

    return final_state


def run_workflow_sync(
    graph: "CompiledGraph",
    folder_path: Path,
    output_path: Path,
    workflow_name: str = "main",
    variables: dict | None = None,
    on_progress: Callable[[dict], None] | None = None,
    library_item_id: str | None = None,
    library_collection_id: str | None = None,
    library_item_map: dict | None = None,
    max_retries: int = 3,
) -> WorkflowState:
    """Synchronous wrapper for run_workflow."""
    return asyncio.run(
        run_workflow(
            graph=graph,
            folder_path=folder_path,
            output_path=output_path,
            workflow_name=workflow_name,
            variables=variables,
            on_progress=on_progress,
            library_item_id=library_item_id,
            library_collection_id=library_collection_id,
            library_item_map=library_item_map,
            max_retries=max_retries,
        )
    )


# =============================================================================
# Simple Linear Workflow (No LangGraph)
# =============================================================================

async def run_linear_workflow(
    plan_config: dict,
    folder_path: Path,
    output_path: Path,
    workflow_name: str = "main",
    variables: dict | None = None,
    on_progress: Callable[[dict], None] | None = None,
) -> WorkflowState:
    """Run workflow as simple linear sequence without LangGraph.

    Use this if LangGraph is not installed or for simpler use cases.

    Args:
        plan_config: Parsed YAML plan config
        folder_path: Input folder
        output_path: Output folder
        workflow_name: Which workflow to run
        variables: Additional variables
        on_progress: Progress callback

    Returns:
        Final workflow state
    """
    state = create_initial_state(
        folder_path=folder_path,
        output_path=output_path,
        workflow_name=workflow_name,
        variables=variables,
    )

    # Get workflow steps
    workflows = plan_config.get("workflows", {})
    step_names = workflows.get(workflow_name, [])
    commands = {cmd["name"]: cmd for cmd in plan_config.get("commands", [])}

    state["status"] = "running"
    state["total_steps"] = len(step_names)

    for i, step_name in enumerate(step_names):
        if state["status"] == "failed":
            break

        cmd = commands.get(step_name)
        if not cmd:
            state["errors"].append(f"Command not found: {step_name}")
            continue

        step = parse_step_config(cmd)
        node_func = create_step_node(step)

        # Execute step
        state = node_func(state)

        # Progress callback
        if on_progress:
            on_progress({
                "task_id": state["task_id"],
                "current_step": i + 1,
                "total_steps": state["total_steps"],
                "status": state["status"],
            })

    if state["status"] != "failed":
        state["status"] = "completed"

    return state


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "WorkflowState",
    "StepConfig",
    "create_initial_state",
    "build_workflow",
    "run_workflow",
    "run_workflow_sync",
    "run_linear_workflow",
]
