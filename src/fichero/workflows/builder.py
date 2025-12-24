"""
Workflow Builder

Builds and executes LangGraph workflows from JSON definitions.

The builder:
1. Takes a WorkflowDef (JSON-serializable)
2. Creates a LangGraph StateGraph
3. Resolves inputs for each node using the resolver
4. Executes tools with resolved inputs
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from langgraph.graph import StateGraph, START, END

from fichero.workflows.types import State, WorkflowDef, NodeDef
from fichero.workflows.registry import TOOLS, get_tool
from fichero.workflows.resolver import resolve_inputs, evaluate_condition
from fichero.llm import LLMConfig

logger = logging.getLogger(__name__)


def build_graph(workflow: WorkflowDef) -> StateGraph:
    """Build a LangGraph StateGraph from a workflow definition.

    Args:
        workflow: The workflow definition

    Returns:
        Compiled LangGraph ready for execution
    """
    # Create state graph
    graph = StateGraph(State)

    # Build LLM config from workflow defaults
    llm_config = LLMConfig(
        provider=workflow.provider,
        model=workflow.model,
    )

    # Workflow-level config for resolver
    workflow_config = {
        "provider": workflow.provider,
        "model": workflow.model,
        "timeout": workflow.timeout_seconds,
    }

    # Add nodes
    for node_def in workflow.nodes:
        tool_fn = get_tool(node_def.tool)
        if tool_fn is None:
            raise ValueError(f"Unknown tool: {node_def.tool}")

        # Create node wrapper that calls the tool
        node_fn = _make_node_function(node_def, tool_fn, llm_config, workflow_config)
        graph.add_node(node_def.id, node_fn)

    # Add edges
    for edge in workflow.edges:
        if edge.condition:
            # Conditional edge (for branching)
            condition_fn = _make_condition_function(edge.condition, workflow_config)
            graph.add_conditional_edges(
                edge.source,
                condition_fn,
                {True: edge.target, False: END}
            )
        else:
            # Normal edge
            graph.add_edge(edge.source, edge.target)

    # Connect START to entry nodes
    entry_nodes = workflow.get_entry_nodes()
    if not entry_nodes:
        raise ValueError("Workflow has no entry nodes")

    for entry in entry_nodes:
        graph.add_edge(START, entry)

    # Connect exit nodes to END
    exit_nodes = workflow.get_exit_nodes()
    for exit_node in exit_nodes:
        graph.add_edge(exit_node, END)

    return graph.compile()


def _make_node_function(
    node_def: NodeDef,
    tool_fn: callable,
    llm_config: LLMConfig,
    workflow_config: dict[str, Any] | None = None,
):
    """Create a node function that wraps a tool.

    The node function:
    1. Resolves inputs using path syntax ($.nodes.x.y, etc.)
    2. Calls the tool with resolved inputs
    3. Updates state with tool output
    """
    async def node_function(state: State) -> dict:
        """Execute the tool and update state."""
        node_id = node_def.id

        logger.info(f"Executing node: {node_id} (tool: {node_def.tool})")

        try:
            # Resolve inputs from paths ($.nodes.x.y -> actual value)
            resolved_inputs = resolve_inputs(
                node_def.inputs,
                state,
                workflow_config,
            )

            # Merge with static config (config takes precedence)
            tool_kwargs = {**resolved_inputs, **node_def.config}

            # Call the tool with resolved inputs
            result = await tool_fn(
                inputs=tool_kwargs,
                state=state,
                llm_config=llm_config,
            )

            # Update outputs
            outputs = dict(state.get("outputs", {}))
            outputs[node_id] = result

            # Track output files if tool produced any
            output_files = list(state.get("output_files", []))
            if isinstance(result, dict) and "output_files" in result:
                output_files.extend(result["output_files"])

            # Update completed nodes
            completed = list(state.get("completed_nodes", []))
            completed.append(node_id)

            return {
                "outputs": outputs,
                "output_files": output_files,
                "completed_nodes": completed,
                "current_node": node_id,
            }

        except Exception as e:
            logger.error(f"Node {node_id} failed: {e}")
            return {
                "error": str(e),
                "current_node": node_id,
            }

    return node_function


def _make_condition_function(condition: str, workflow_config: dict[str, Any] | None = None):
    """Create a condition function from a path-based expression.

    Supports:
    - $.nodes.x.success == true
    - $.nodes.x.count > 10
    - $.inputs.skip_step == true
    """
    def evaluate(state: State) -> bool:
        """Evaluate the condition expression."""
        return evaluate_condition(condition, state, workflow_config)

    return evaluate


async def execute_workflow(
    workflow: WorkflowDef,
    inputs: dict[str, Any],
    input_files: list[str] | None = None,
) -> State:
    """Execute a workflow with the given inputs.

    Args:
        workflow: The workflow definition
        inputs: Initial inputs to the workflow
        input_files: Optional list of input file paths

    Returns:
        Final execution state
    """
    # Build the graph
    graph = build_graph(workflow)

    # Create initial state
    task_id = str(uuid.uuid4())
    initial_state: State = {
        "task_id": task_id,
        "workflow_id": workflow.id,
        "inputs": inputs,
        "outputs": {},
        "current_node": "",
        "completed_nodes": [],
        "error": None,
        "input_files": input_files or [],
        "output_files": [],
    }

    logger.info(f"Executing workflow: {workflow.name} (task_id: {task_id})")

    # Execute the graph
    final_state = await graph.ainvoke(initial_state)

    if final_state.get("error"):
        logger.error(f"Workflow failed: {final_state['error']}")
    else:
        logger.info(f"Workflow completed: {len(final_state.get('completed_nodes', []))} nodes")

    return final_state
