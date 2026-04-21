"""
Workflow Builder

Builds and executes LangGraph workflows from JSON definitions.

The builder:
1. Takes a WorkflowDef (JSON-serializable)
2. Creates a LangGraph StateGraph
3. Resolves inputs for each node using the resolver
4. Executes tools with resolved inputs
5. Uses Send API for parallel file processing (fan-out/fan-in)
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from fichero.workflows.types import State, WorkflowDef, NodeDef
from fichero.workflows.registry import get_tool, get_tool_def
from fichero.workflows.resolver import resolve_inputs, evaluate_condition
from fichero.workflows.cache import get_node_cache, compute_cache_key, CACHEABLE_TOOLS
from fichero.llm import LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Parallel Execution Configuration
# =============================================================================

# Default concurrency limit for parallel file processing
DEFAULT_MAX_CONCURRENT = 10

# Tools that support parallel file processing
PARALLEL_TOOLS = {"transcribe", "describe", "summarize", "entities"}

# Source tools that output files (triggers parallel processing when connected to PARALLEL_TOOLS)
SOURCE_TOOLS = {"files", "collection", "folder", "search"}

# =============================================================================
# Error Detection Configuration
# =============================================================================

# Maximum consecutive errors before aborting (indicates systemic issue)
MAX_CONSECUTIVE_ERRORS = 5

# Error rate threshold - if more than this fraction fails, abort (0.5 = 50%)
ERROR_RATE_THRESHOLD = 0.5

# Minimum files before checking error rate (avoid aborting on small batches)
MIN_FILES_FOR_ERROR_RATE = 10


class WorkflowExecutionError(Exception):
    """Base exception for workflow execution errors."""

    pass


class SystemicErrorDetected(WorkflowExecutionError):
    """Raised when too many consecutive or rate-based errors indicate a systemic issue.

    This typically means:
    - API key is invalid
    - Network is down
    - Service is unavailable
    - Rate limiting in effect
    """

    def __init__(
        self,
        message: str = "",
        error_count: int = 0,
        total_count: int = 0,
        errors: list[dict] | None = None,
    ):
        super().__init__(message)
        self.error_count = error_count
        self.total_count = total_count
        self.errors = errors or []


def _generate_node_names(workflow: WorkflowDef) -> dict[str, str]:
    """Generate human-readable node names from workflow definition.

    Uses label if available, otherwise tool name. Ensures uniqueness by
    appending numbers if needed.

    Args:
        workflow: The workflow definition

    Returns:
        Dictionary mapping node ID (UUID) to human-readable name
    """
    node_names: dict[str, str] = {}
    name_counts: dict[str, int] = {}

    for node in workflow.nodes:
        # Use label if available, otherwise capitalize tool name
        base_name = node.label or node.tool.replace("_", " ").title()

        # Ensure uniqueness
        if base_name in name_counts:
            name_counts[base_name] += 1
            unique_name = f"{base_name} {name_counts[base_name]}"
        else:
            name_counts[base_name] = 1
            unique_name = base_name

        node_names[node.id] = unique_name

    return node_names


def build_graph(
    workflow: WorkflowDef,
    enable_parallel: bool = True,
    event_callback: Any | None = None,
    checkpointer: Any | None = None,
    skip_cache: bool = False,
) -> StateGraph:
    """Build a LangGraph StateGraph from a workflow definition.

    Args:
        workflow: The workflow definition
        enable_parallel: Whether to enable parallel file processing (default: True)
        event_callback: Optional async callback for emitting SSE events during parallel
            processing. Signature: async def callback(event_type: str, data: dict) -> None
        checkpointer: Optional LangGraph checkpointer for state persistence
        skip_cache: If True, bypass node result cache (still writes to cache)

    Returns:
        Compiled LangGraph ready for execution
    """
    # Generate human-readable node names for the graph
    node_names = _generate_node_names(workflow)

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
        "workflow_id": workflow.id,
        "skip_cache": skip_cache,
    }

    # Build edge lookup for auto-wiring
    edges_by_target = {}
    for edge in workflow.edges:
        if edge.target not in edges_by_target:
            edges_by_target[edge.target] = []
        edges_by_target[edge.target].append(
            {
                "source": edge.source,
                "source_port": edge.source_port,
                "target_port": edge.target_port,
            }
        )

    # Identify parallel processing edges (source -> batch tool)
    parallel_edges = set()
    if enable_parallel:
        for edge in workflow.edges:
            target_node = workflow.get_node(edge.target)
            if target_node and target_node.tool in PARALLEL_TOOLS:
                # Check if source outputs files
                source_node = workflow.get_node(edge.source)
                if source_node and source_node.tool in SOURCE_TOOLS:
                    parallel_edges.add((edge.source, edge.target))
                    logger.info(
                        f"Parallel edge detected: {edge.source} -> {edge.target}"
                    )

    # Add nodes using human-readable names
    for node_def in workflow.nodes:
        tool_fn = get_tool(node_def.tool)
        if tool_fn is None:
            raise ValueError(f"Unknown tool: {node_def.tool}")

        incoming_edges = edges_by_target.get(node_def.id, [])
        node_name = node_names[node_def.id]  # Human-readable name

        # Check if this node receives parallel fan-out
        is_parallel_target = any(
            (e["source"], node_def.id) in parallel_edges for e in incoming_edges
        )

        if is_parallel_target:
            # Create single-file processing node for parallel execution
            node_fn = _make_parallel_node_function(
                node_def, tool_fn, llm_config, workflow_config, event_callback
            )
            # Add aggregation node
            agg_fn = _make_aggregation_function(node_def.id)
            graph.add_node(f"{node_name}_process", node_fn)
            graph.add_node(f"{node_name}_aggregate", agg_fn)
        else:
            # Standard node
            node_fn = _make_node_function(
                node_def, tool_fn, llm_config, workflow_config, incoming_edges
            )
            graph.add_node(node_name, node_fn)

    # Add edges
    # Group parallel edges by source node (one conditional edge per source)
    parallel_by_source: dict[str, list[str]] = {}
    for edge in workflow.edges:
        if (edge.source, edge.target) in parallel_edges:
            if edge.source not in parallel_by_source:
                parallel_by_source[edge.source] = []
            parallel_by_source[edge.source].append(edge.target)

    # Add fan-out conditional edges (one per source node)
    for source_id, target_ids in parallel_by_source.items():
        source_name = node_names[source_id]
        fan_out_fn = _make_fan_out_function(source_id, target_ids, node_names)
        target_process_names = [f"{node_names[t]}_process" for t in target_ids]
        graph.add_conditional_edges(source_name, fan_out_fn, target_process_names)
        # Connect each process node to its aggregate
        for target_id in target_ids:
            target_name = node_names[target_id]
            graph.add_edge(f"{target_name}_process", f"{target_name}_aggregate")

    # Add non-parallel edges
    for edge in workflow.edges:
        source_name = node_names[edge.source]
        target_name = node_names[edge.target]

        if (edge.source, edge.target) in parallel_edges:
            continue  # Already handled above
        elif edge.condition:
            # Conditional edge (for branching)
            condition_fn = _make_condition_function(edge.condition, workflow_config)
            graph.add_conditional_edges(
                source_name, condition_fn, {True: target_name, False: END}
            )
        else:
            # Check if source was parallelized - connect from aggregate
            source_is_parallel = any(
                (e.source, e.target) in parallel_edges and e.target == edge.source
                for e in workflow.edges
            )
            if source_is_parallel:
                graph.add_edge(f"{source_name}_aggregate", target_name)
            else:
                graph.add_edge(source_name, target_name)

    # Connect START to entry nodes
    entry_nodes = workflow.get_entry_nodes()
    if not entry_nodes:
        raise ValueError("Workflow has no entry nodes")

    for entry_id in entry_nodes:
        entry_name = node_names[entry_id]
        graph.add_edge(START, entry_name)

    # Connect exit nodes to END
    exit_nodes = workflow.get_exit_nodes()
    for exit_id in exit_nodes:
        exit_name = node_names[exit_id]
        # Check if this exit node was parallelized
        is_parallel = any(
            (e.source, e.target) in parallel_edges and e.target == exit_id
            for e in workflow.edges
        )
        if is_parallel:
            graph.add_edge(f"{exit_name}_aggregate", END)
        else:
            graph.add_edge(exit_name, END)

    return graph.compile(checkpointer=checkpointer)


def _make_node_function(
    node_def: NodeDef,
    tool_fn: callable,
    llm_config: LLMConfig,
    workflow_config: dict[str, Any] | None = None,
    incoming_edges: list[dict] | None = None,
):
    """Create a node function that wraps a tool.

    The node function:
    1. Resolves inputs using path syntax ($.nodes.x.y, etc.)
    2. Calls the tool with resolved inputs
    3. Updates state with tool output

    Args:
        node_def: The node definition
        tool_fn: The tool function to call
        llm_config: LLM configuration
        workflow_config: Workflow-level configuration
        incoming_edges: List of edges where this node is the target (for auto-wiring)
    """
    # Build node-specific LLM config if provider/model specified on node or in config
    node_llm_config = llm_config
    node_provider = node_def.provider_name or node_def.config.get("provider_name", "")
    node_model = node_def.model_name or node_def.config.get("model_name", "")
    if node_provider or node_model:
        node_llm_config = LLMConfig(
            provider=node_provider or llm_config.provider,
            model=node_model or llm_config.model,
        )
    else:
        # No explicit provider on node — try category default from settings
        tool_def = get_tool_def(node_def.tool)
        if tool_def and tool_def.uses_llm:
            try:
                from fichero.app_db import get_app_db

                cat_default = get_app_db().get_default_model_for_category(
                    tool_def.category
                )
                if cat_default:
                    node_llm_config = LLMConfig(
                        provider=cat_default[0],
                        model=cat_default[1],
                    )
            except Exception as e:
                logger.debug(
                    f"Could not load category default for {tool_def.category}: {e}"
                )

    async def node_function(state: State) -> dict:
        """Execute the tool and update state."""
        node_id = node_def.id
        node_label = node_def.label or node_def.tool

        logger.info(
            f"Running: {node_label} (tool: {node_def.tool}, provider: {node_llm_config.provider or 'NOT SET'})"
        )

        try:
            # Convert input_mappings to inputs dict for resolver
            # input_mappings: [{port_id: "files", source_path: "$.nodes.x.files"}]
            # -> inputs: {"files": "$.nodes.x.files"}
            inputs_from_mappings = {}
            for mapping in node_def.input_mappings:
                inputs_from_mappings[mapping.port_id] = mapping.source_path

            # AUTO-WIRE: If no explicit input_mappings, use edges to wire inputs
            # This allows visual connections to automatically pass data
            if incoming_edges and not inputs_from_mappings:
                for edge in incoming_edges:
                    source_node = edge.get("source") or edge.get("source_node_id")
                    source_port = edge.get(
                        "source_port", "files"
                    )  # Default to "files" for source tools
                    target_port = edge.get(
                        "target_port", "files"
                    )  # Default to "files" for input
                    if source_node:
                        # Create automatic path reference: $.nodes.{source_node}.{source_port}
                        inputs_from_mappings[target_port] = (
                            f"$.nodes.{source_node}.{source_port}"
                        )
                        logger.info(
                            f"Auto-wired: {target_port} <- $.nodes.{source_node}.{source_port}"
                        )

            # Merge: input_mappings take precedence over static inputs
            all_inputs = {**node_def.inputs, **inputs_from_mappings}

            # Resolve inputs from paths ($.nodes.x.y -> actual value)
            resolved_inputs = resolve_inputs(
                all_inputs,
                state,
                workflow_config,
            )

            # Merge with static config (config takes precedence)
            tool_kwargs = {**resolved_inputs, **node_def.config}

            # Call the tool with resolved inputs
            result = await tool_fn(
                inputs=tool_kwargs,
                state=state,
                llm_config=node_llm_config,
            )

            # Check if tool returned an error (tools return {"error": "..."} on failure)
            if isinstance(result, dict) and result.get("error"):
                error_msg = result["error"]
                print(f"[STEP] ✗ FAILED: {node_label}")
                print(f"[STEP]   Error: {error_msg}")
                logger.error(f"Node {node_id} tool returned error: {error_msg}")
                return {
                    "error": f"Step '{node_label}' failed: {error_msg}",
                    "current_node": node_id,
                }

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

            print(f"[STEP] ✓ Completed: {node_label}")

            return {
                "outputs": outputs,
                "output_files": output_files,
                "completed_nodes": completed,
                "current_node": node_id,
            }

        except Exception as e:
            error_msg = str(e)
            print(f"[STEP] ✗ FAILED: {node_label}")
            print(f"[STEP]   Error: {error_msg}")
            logger.error(f"Node {node_id} failed: {e}")
            return {
                "error": f"Step '{node_label}' failed: {error_msg}",
                "current_node": node_id,
            }

    return node_function


def _make_fan_out_function(
    source_node_id: str, target_node_ids: list[str], node_names: dict[str, str]
):
    """Create a function that fans out to parallel processing using Send API.

    For each file from the source node, creates Send() objects to process it
    in parallel across all target nodes.

    Args:
        source_node_id: UUID of source node
        target_node_ids: List of target node UUIDs
        node_names: Mapping from UUID to human-readable name
    """

    def fan_out(state: State) -> list[Send]:
        """Fan out to parallel file processing."""
        # Get files from source node output (still uses UUID as key in outputs)
        source_output = state.get("outputs", {}).get(source_node_id, {})
        files = source_output.get("files", [])
        documents = source_output.get("documents", [])

        if not files:
            logger.warning(f"No files from {source_node_id} to fan out")
            return []

        total = len(files)
        logger.info(f"Fanning out {total} files to {len(target_node_ids)} targets")

        # Create Send for each file × each target
        sends = []
        for target_node_id in target_node_ids:
            target_name = node_names[target_node_id]
            for i, file_path in enumerate(files):
                # Find matching document metadata
                doc = None
                if i < len(documents):
                    doc = documents[i]
                elif documents:
                    # Try to match by path
                    for d in documents:
                        if isinstance(d, dict) and d.get("path") == file_path:
                            doc = d
                            break

                sends.append(
                    Send(
                        f"{target_name}_process",
                        {
                            # Pass single file info for this branch
                            "parallel_file": file_path,
                            "parallel_document": doc,
                            "parallel_index": i,
                            "parallel_total": total,
                            # Preserve essential state
                            "task_id": state.get("task_id", ""),
                            "workflow_id": state.get("workflow_id", ""),
                            "library_path": state.get("library_path", ""),
                            "outputs": state.get("outputs", {}),
                        },
                    )
                )

        return sends

    return fan_out


def _make_parallel_node_function(
    node_def: NodeDef,
    tool_fn: callable,
    llm_config: LLMConfig,
    workflow_config: dict[str, Any] | None = None,
    event_callback: Any | None = None,
):
    """Create a node function that processes a single file in parallel.

    This is used with the Send API - each invocation processes one file.

    Args:
        event_callback: Optional async callback for emitting SSE events.
            Signature: async def callback(event_type: str, data: dict) -> None
    """
    # Build node-specific LLM config if provider/model specified on node or in config
    node_llm_config = llm_config
    node_provider = node_def.provider_name or node_def.config.get("provider_name", "")
    node_model = node_def.model_name or node_def.config.get("model_name", "")
    if node_provider or node_model:
        node_llm_config = LLMConfig(
            provider=node_provider or llm_config.provider,
            model=node_model or llm_config.model,
        )
    else:
        # No explicit provider on node — try category default from settings
        tool_def = get_tool_def(node_def.tool)
        if tool_def and tool_def.uses_llm:
            try:
                from fichero.app_db import get_app_db

                cat_default = get_app_db().get_default_model_for_category(
                    tool_def.category
                )
                if cat_default:
                    node_llm_config = LLMConfig(
                        provider=cat_default[0],
                        model=cat_default[1],
                    )
            except Exception as e:
                logger.debug(
                    f"Could not load category default for {tool_def.category}: {e}"
                )

    # Extract caching config
    workflow_id = workflow_config.get("workflow_id", "") if workflow_config else ""
    skip_cache = workflow_config.get("skip_cache", False) if workflow_config else False
    is_cacheable = node_def.tool in CACHEABLE_TOOLS

    async def parallel_node_function(state: State) -> dict:
        """Process a single file in parallel."""
        node_id = node_def.id

        # Get single file info from state (set by Send)
        file_path = state.get("parallel_file", "")
        document = state.get("parallel_document")
        index = state.get("parallel_index", 0)
        total = state.get("parallel_total", 1)

        # Get library path for cache access
        library_path = state.get("library_path", "")

        # --- Cache Check ---
        cache = None
        cache_key = None
        if is_cacheable and library_path and not skip_cache:
            try:
                db_path = Path(library_path) / "fichero.duckdb"
                if db_path.exists():
                    cache = get_node_cache(db_path)
                    cache_key = compute_cache_key(
                        workflow_id=workflow_id,
                        node_id=node_id,
                        tool=node_def.tool,
                        config=node_def.config,
                        provider=node_llm_config.provider,
                        model=node_llm_config.model,
                        file_path=file_path,
                    )

                    # Check cache
                    cached_result = cache.get(cache_key)
                    if cached_result is not None:
                        print(
                            f"[PARALLEL] [{index + 1}/{total}] CACHE HIT: {file_path}"
                        )
                        logger.info(f"Cache hit for {file_path}")

                        # Emit file_complete event for cached result
                        if event_callback:
                            try:
                                await event_callback(
                                    "file_complete",
                                    {
                                        "node_id": node_id,
                                        "file_path": file_path,
                                        "file_index": index,
                                        "file_total": total,
                                        "progress": float(index + 1) / max(total, 1),
                                        "cached": True,
                                    },
                                )
                            except Exception as cb_err:
                                logger.warning(
                                    f"Failed to emit cached file_complete event: {cb_err}"
                                )

                        # Return cached result
                        return {
                            "parallel_results": {
                                node_id: [
                                    {
                                        "file": file_path,
                                        "index": index,
                                        "total": total,
                                        "result": cached_result,
                                        "success": True,
                                        "cached": True,
                                    }
                                ]
                            },
                        }
            except Exception as cache_err:
                logger.warning(f"Cache check failed: {cache_err}")

        # Emit file_start event via callback
        if event_callback:
            try:
                await event_callback(
                    "file_start",
                    {
                        "node_id": node_id,
                        "file_path": file_path,
                        "file_index": index,
                        "file_total": total,
                        "progress": float(index) / max(total, 1),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to emit file_start event: {e}")

        print(f"[PARALLEL] [{index + 1}/{total}] Processing: {file_path}")
        logger.info(f"Parallel processing file {index + 1}/{total}: {file_path}")

        try:
            # Build inputs for single file
            tool_inputs = {
                "files": [file_path],  # Single file as list
                "documents": [document] if document else [],
                **node_def.config,  # Static config
            }

            # Call the tool
            result = await tool_fn(
                inputs=tool_inputs,
                state=state,
                llm_config=node_llm_config,
            )

            # Check for errors - both top-level and in results array
            error_msg = None
            if isinstance(result, dict):
                # Check top-level error
                if result.get("error"):
                    error_msg = result["error"]
                # Also check results array for errors (defensive)
                elif result.get("results"):
                    for r in result.get("results", []):
                        if isinstance(r, dict) and r.get("error"):
                            error_msg = r["error"]
                            break

            if error_msg:
                print(f"[PARALLEL] [{index + 1}/{total}] FAILED: {error_msg}")
                # Emit file_error event
                if event_callback:
                    try:
                        await event_callback(
                            "file_error",
                            {
                                "node_id": node_id,
                                "file_path": file_path,
                                "file_index": index,
                                "file_total": total,
                                "error": error_msg,
                                "progress": float(index + 1) / max(total, 1),
                            },
                        )
                    except Exception as cb_err:
                        logger.warning(f"Failed to emit file_error event: {cb_err}")
                return {
                    "parallel_results": {
                        node_id: [
                            {
                                "file": file_path,
                                "index": index,
                                "total": total,  # Include total for SSE
                                "error": error_msg,
                                "success": False,
                            }
                        ]
                    },
                }

            print(f"[PARALLEL] [{index + 1}/{total}] Completed: {file_path}")

            # --- Cache Write ---
            if cache and cache_key and is_cacheable:
                try:
                    cache.set(
                        cache_key=cache_key,
                        result=result,
                        workflow_id=workflow_id,
                        node_id=node_id,
                        tool=node_def.tool,
                        file_path=file_path,
                    )
                    logger.debug(f"Cached result for {file_path}")
                except Exception as cache_err:
                    logger.warning(f"Cache write failed: {cache_err}")

            # Emit file_complete event
            if event_callback:
                try:
                    await event_callback(
                        "file_complete",
                        {
                            "node_id": node_id,
                            "file_path": file_path,
                            "file_index": index,
                            "file_total": total,
                            "progress": float(index + 1) / max(total, 1),
                        },
                    )
                except Exception as cb_err:
                    logger.warning(f"Failed to emit file_complete event: {cb_err}")

            # Return result for aggregation
            return {
                "parallel_results": {
                    node_id: [
                        {
                            "file": file_path,
                            "index": index,
                            "total": total,  # Include total for SSE
                            "result": result,
                            "success": True,
                        }
                    ]
                },
            }

        except Exception as e:
            error_msg = str(e)
            print(f"[PARALLEL] [{index + 1}/{total}] ERROR: {error_msg}")
            logger.error(f"Parallel processing failed for {file_path}: {e}")
            # Emit file_error event for exception
            if event_callback:
                try:
                    await event_callback(
                        "file_error",
                        {
                            "node_id": node_id,
                            "file_path": file_path,
                            "file_index": index,
                            "file_total": total,
                            "error": error_msg,
                            "progress": float(index + 1) / max(total, 1),
                        },
                    )
                except Exception as cb_err:
                    logger.warning(f"Failed to emit file_error event: {cb_err}")
            return {
                "parallel_results": {
                    node_id: [
                        {
                            "file": file_path,
                            "index": index,
                            "total": total,  # Include total for SSE
                            "error": error_msg,
                            "success": False,
                        }
                    ]
                },
            }

    return parallel_node_function


def _make_aggregation_function(node_id: str):
    """Create a function that aggregates results from parallel processing.

    Collects all parallel results and combines them into a single output.
    Detects systemic errors (consecutive failures or high error rate) and raises
    SystemicErrorDetected to abort the workflow early.
    """

    async def aggregate(state: State) -> dict:
        """Aggregate parallel processing results."""
        parallel_results = state.get("parallel_results", {}).get(node_id, [])

        if not parallel_results:
            logger.warning(f"No parallel results to aggregate for {node_id}")
            return {}

        # Sort by index to maintain order
        sorted_results = sorted(parallel_results, key=lambda x: x.get("index", 0))

        # Aggregate results
        all_texts = []
        all_results = []
        all_artifacts = []
        errors = []
        success_count = 0

        # Track consecutive errors for systemic error detection
        consecutive_errors = 0
        max_consecutive_errors = 0

        for item in sorted_results:
            if item.get("success"):
                success_count += 1
                consecutive_errors = 0  # Reset on success
                result = item.get("result", {})
                if isinstance(result, dict):
                    if result.get("text"):
                        all_texts.append(result["text"])
                    if result.get("results"):
                        all_results.extend(result["results"])
                    if result.get("artifacts"):
                        all_artifacts.extend(result["artifacts"])
            else:
                consecutive_errors += 1
                max_consecutive_errors = max(max_consecutive_errors, consecutive_errors)
                errors.append(
                    {
                        "file": item.get("file"),
                        "error": item.get("error"),
                    }
                )

        total = len(sorted_results)
        error_count = len(errors)
        error_rate = error_count / total if total > 0 else 0

        print(
            f"[AGGREGATE] {node_id}: {success_count}/{total} succeeded, {error_count} errors"
        )
        print(
            f"[AGGREGATE] Error rate: {error_rate:.1%}, Max consecutive errors: {max_consecutive_errors}"
        )

        # Check for systemic errors - these indicate fundamental issues that won't resolve
        # by continuing (e.g., invalid API key, network down, rate limiting)
        if max_consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            error_msg = (
                f"Systemic error detected: {max_consecutive_errors} consecutive failures. "
                f"This typically indicates an API key issue, network problem, or rate limiting. "
                f"First error: {errors[0]['error'] if errors else 'unknown'}"
            )
            logger.error(error_msg)
            raise SystemicErrorDetected(
                message=error_msg,
                error_count=error_count,
                total_count=total,
                errors=errors[:10],  # Include first 10 errors for diagnosis
            )

        # Check error rate for larger batches
        if total >= MIN_FILES_FOR_ERROR_RATE and error_rate > ERROR_RATE_THRESHOLD:
            error_msg = (
                f"High error rate detected: {error_rate:.1%} ({error_count}/{total} failed). "
                f"Threshold is {ERROR_RATE_THRESHOLD:.0%}. "
                f"Common error: {errors[0]['error'] if errors else 'unknown'}"
            )
            logger.error(error_msg)
            raise SystemicErrorDetected(
                message=error_msg,
                error_count=error_count,
                total_count=total,
                errors=errors[:10],
            )

        # Build aggregated output
        aggregated = {
            "text": "\n\n".join(all_texts),
            "texts": all_texts,
            "results": all_results,
            "artifacts": all_artifacts,
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors if errors else None,
            "max_consecutive_errors": max_consecutive_errors,
        }

        # Update outputs
        outputs = dict(state.get("outputs", {}))
        outputs[node_id] = aggregated

        # Update completed nodes
        completed = list(state.get("completed_nodes", []))
        if node_id not in completed:
            completed.append(node_id)

        return {
            "outputs": outputs,
            "completed_nodes": completed,
            "current_node": node_id,
        }

    return aggregate


def _make_condition_function(
    condition: str, workflow_config: dict[str, Any] | None = None
):
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
    library_path: str | None = None,
) -> State:
    """Execute a workflow with the given inputs.

    Args:
        workflow: The workflow definition
        inputs: Initial inputs to the workflow
        input_files: Optional list of input file paths
        library_path: Path to the .fichero library package (required for source tools)

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
        "library_path": library_path or "",  # Required for source tools to access DB
        "inputs": inputs,
        "outputs": {},
        "current_node": "",
        "completed_nodes": [],
        "error": None,
        "input_files": input_files or [],
        "output_files": [],
        # Parallel execution state
        "parallel_results": {},
        "parallel_index": 0,
        "parallel_total": 0,
        "parallel_file": "",
        "parallel_document": None,
    }

    logger.info(f"Executing workflow: {workflow.name} (task_id: {task_id})")

    # Execute the graph
    final_state = await graph.ainvoke(initial_state)

    if final_state.get("error"):
        logger.error(f"Workflow failed: {final_state['error']}")
    else:
        logger.info(
            f"Workflow completed: {len(final_state.get('completed_nodes', []))} nodes"
        )

    return final_state
