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

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from fichero_server.workflows.types import State, WorkflowDef, NodeDef
from fichero_server.workflows.registry import get_tool, get_tool_def
from fichero_server.workflows.resolver import resolve_inputs, evaluate_condition
from fichero_server.workflows.cache import (
    get_node_cache,
    compute_cache_key,
    compute_batch_cache_key,
    is_sequentially_cacheable,
    CACHEABLE_TOOLS,
)
from fichero_server.workflows.tools.output_quality import (
    assess_result_quality,
    detect_page_contamination_warnings,
)
from fichero_server.llm import LLMConfig

logger = logging.getLogger(__name__)

# Concurrency cap for parallel vision fan-out (#2221).
# Bounds the number of simultaneously in-flight LLM/image calls so a batch
# of multi-page PDFs processes steadily instead of exhausting RAM all at once.
VISION_FAN_OUT_CONCURRENCY: int = 4
_vision_fan_out_sem: asyncio.Semaphore | None = None
_vision_fan_out_sem_loop: asyncio.AbstractEventLoop | None = None


def _get_vision_semaphore() -> asyncio.Semaphore:
    """Return the shared vision/LLM fan-out concurrency semaphore.

    The semaphore is a module global so a single cap (VISION_FAN_OUT_CONCURRENCY)
    governs every concurrently in-flight vision/LLM call within a run — whether
    they arrive via the graph-level Send fan-out (_make_parallel_node_function)
    or the in-tool bounded path (vision_base). asyncio.Semaphore binds its
    internal waiter Futures to whatever loop is running on first contention, so
    a semaphore created on run A's event loop and reused (uncontended-or-not) on
    run B's fresh loop can surface "got Future attached to a different loop".
    The run path builds a fresh per-run event loop, so guard against it: rebind
    the semaphore whenever the running loop differs from the one it was created
    on. Within a single run (one loop) it is created once and shared, so the
    cap-4 throttle is preserved; across runs/loops it is recreated cleanly.
    """
    global _vision_fan_out_sem, _vision_fan_out_sem_loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if _vision_fan_out_sem is None or _vision_fan_out_sem_loop is not loop:
        _vision_fan_out_sem = asyncio.Semaphore(VISION_FAN_OUT_CONCURRENCY)
        _vision_fan_out_sem_loop = loop
    return _vision_fan_out_sem


def _required_llm_capability_for_category(category: str | None) -> str:
    category_key = str(category or "").strip().lower()
    if category_key in {"vision", "audio", "video"}:
        return category_key
    return "text"


def _resolve_node_llm_config(
    node_def: NodeDef, workflow_llm_config: LLMConfig
) -> LLMConfig:
    """Node-context wrapper around ``_resolve_node_llm_config_inner``.

    Resolution failures surface in the run-validation error list (and in
    mid-run errors), which previously carried a bare "Model X is not marked
    as vision-capable" with no clue WHICH node failed (#4187). The preflight
    path (validation.py) already prefixes the node; this makes the
    build-graph path agree. Message-only — the validation rule is untouched.
    """
    try:
        return _resolve_node_llm_config_inner(node_def, workflow_llm_config)
    except ValueError as exc:
        node_label = node_def.label or node_def.id or node_def.tool
        raise ValueError(f"Node '{node_label}' ({node_def.tool}): {exc}") from exc


def _resolve_node_llm_config_inner(
    node_def: NodeDef, workflow_llm_config: LLMConfig
) -> LLMConfig:
    """Resolve the effective LLM config for a node.

    Priority order:
      1. Node-specific provider_name/model_name (from node or node.config)
      2. Workflow-level default (workflow_llm_config)
      3. Category default from app settings (if tool is_llm)
      4. Any configured enabled provider + model in the app DB

    Without the final fallback, a shipped preset like Catalogue — whose LLM
    node has no provider and which runs on a fresh install where category
    defaults aren't set — fails with "LLM provider not configured." even
    though the user has a working provider configured. #704 / Catalogue
    breakage on 2026-04-24.
    """
    node_provider = node_def.provider_name or node_def.config.get("provider_name", "")
    node_model = node_def.model_name or node_def.config.get("model_name", "")
    tool_def = get_tool_def(node_def.tool)
    required_capability = None
    if tool_def and tool_def.uses_llm:
        required_capability = _required_llm_capability_for_category(tool_def.category)

    profile_ref = (
        node_def.config.get("model_profile_id")
        or node_def.config.get("profile_id")
        or node_def.config.get("model_profile")
    )
    if not profile_ref:
        from fichero_server.llm import extract_model_profile_reference

        profile_ref = extract_model_profile_reference(node_provider)
    if profile_ref:
        from fichero_server.llm import resolve_model_profile_for_capability

        return resolve_model_profile_for_capability(
            str(profile_ref),
            base_config=workflow_llm_config,
            required_capability=required_capability,
        )

    if node_provider or node_model:
        provider = node_provider or workflow_llm_config.provider
        model = node_model or workflow_llm_config.model
        # Alias resolution against app-level defaults (#810/#2200).
        # Lets shipped presets stay portable across users with different
        # configured providers — the node declares a tier, the user picks
        # the concrete model in Settings.
        from fichero_server.llm import resolve_model_alias_for_capability
        provider, model = resolve_model_alias_for_capability(
            provider,
            model,
            required_capability=required_capability,
        )
        return LLMConfig(provider=provider, model=model)

    if not (tool_def and tool_def.uses_llm):
        return workflow_llm_config

    try:
        from fichero_server.db.app import get_app_db
        app_db = get_app_db()

        from fichero_server.llm import extract_model_profile_reference

        workflow_profile_ref = extract_model_profile_reference(
            workflow_llm_config.provider
        )
        if workflow_profile_ref:
            from fichero_server.llm import resolve_model_profile_for_capability

            return resolve_model_profile_for_capability(
                workflow_profile_ref,
                base_config=workflow_llm_config,
                required_capability=required_capability,
            )

        if workflow_llm_config.provider and workflow_llm_config.model:
            return workflow_llm_config

        cat_default = app_db.get_default_model_for_category(tool_def.category)
        if cat_default:
            return LLMConfig(provider=cat_default[0], model=cat_default[1])

        generic_default = app_db.get_default_model()
        if generic_default:
            logger.info(
                "Node %s (tool=%s) falling back to generic default provider %s/%s",
                node_def.id, node_def.tool, generic_default[0], generic_default[1],
            )
            return LLMConfig(provider=generic_default[0], model=generic_default[1])

        # Apple is registered as a provider for Vision/Speech but llm.chat()
        # doesn't support it yet (no Foundation Models adapter). Skip Apple
        # for LLM (text) fallback, but keep it for vision nodes (#2243) where
        # Apple Intelligence IS the intended out-of-the-box provider.
        llm_unsupported = {"apple"} if required_capability != "vision" else set()
        for provider in app_db.list_providers():
            if not provider.enabled:
                continue
            if provider.provider_type.value in llm_unsupported:
                continue
            models = [m for m in app_db.list_models(provider.id) if m.enabled]
            if not models:
                continue
            logger.warning(
                "Node %s (tool=%s) has no provider configured and no defaults set; "
                "falling back to first configured provider %s/%s",
                node_def.id, node_def.tool, provider.provider_type.value, models[0].model_id,
            )
            return LLMConfig(
                provider=provider.provider_type.value, model=models[0].model_id,
            )
    except Exception as e:
        logger.debug("Provider fallback lookup failed for %s: %s", node_def.tool, e)

    return workflow_llm_config


# =============================================================================
# Parallel Execution Configuration
# =============================================================================

# Default concurrency limit for parallel file processing
DEFAULT_MAX_CONCURRENT = 10

# Tools that support parallel file processing
PARALLEL_TOOLS = {"transcribe", "describe", "summarize", "entities"}


def _result_worth_caching(result: Any) -> bool:
    """Decide whether to write a parallel-node result to the durable cache.

    An empty transcribe / extract / summary cached forever poisons every
    subsequent run on the same file with the same key — the user sees an
    instant 5ms 'completion' that returns nothing, and there's no way to
    recover short of manually clearing the cache. Better to skip caching
    on empty: the node will redo the work next time.

    Heuristic: cache anything that has either non-empty `text`, non-empty
    `value`, or any artifacts/results. Skip when all of those are empty,
    none, or missing.
    """
    if not isinstance(result, dict):
        return bool(result)
    text = result.get("text")
    if isinstance(text, str) and text.strip():
        return True
    value = result.get("value")
    if isinstance(value, dict) and any(value.values()):
        return True
    if isinstance(value, list) and value:
        return True
    if result.get("results"):
        return True
    if result.get("artifacts"):
        return True
    return False

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


def _is_quota_error(exception: Exception) -> bool:
    """Detect if an exception is a quota/rate-limit error.

    Checks for common quota error indicators: 403 status code,
    "quota", "rate limit", or "key limit" in the error message.
    """
    error_str = str(exception).lower()
    return any(indicator in error_str for indicator in [
        "403", "quota", "rate limit", "key limit", "rate_limit"
    ])


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
    interrupt_before: list[str] | None = None,
    interrupt_after: list[str] | None = None,
    skip_cache: bool = False,
) -> Any:
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
    from langgraph.graph import StateGraph, START, END  # noqa: PLC0415

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

    # Validate edge references before any downstream node_names lookup.
    valid_node_ids = {node.id for node in workflow.nodes}
    for edge in workflow.edges:
        if edge.route_map:
            if edge.source not in valid_node_ids:
                raise ValueError(
                    f"Route-map edge source {edge.source!r} is not in workflow nodes"
                )
            unknown_targets = [v for v in edge.route_map.values() if v not in valid_node_ids]
            if unknown_targets:
                raise ValueError(
                    f"Route-map edge targets are not in workflow nodes: {unknown_targets}"
                )
            continue
        if edge.source not in valid_node_ids or edge.target not in valid_node_ids:
            raise ValueError(
                "Edge references unknown node "
                f"(source={edge.source!r}, target={edge.target!r}); "
                f"known nodes: {sorted(valid_node_ids)}"
            )

    # Build edge lookup for auto-wiring (route_map edges have no single target)
    edges_by_target = {}
    for edge in workflow.edges:
        if edge.route_map or not edge.target:
            continue
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

    # Identify route_map edges whose targets are PARALLEL_TOOLS (#2236).
    # Example: classify → route_map → {typescript: transcribe-ts, ...}
    # These need the same per-file Send fan-out as direct SOURCE→PARALLEL edges.
    # Maps routed_target_id → files_source_id (the SOURCE_TOOL one hop upstream).
    route_map_parallel: dict[str, str] = {}
    if enable_parallel:
        for edge in workflow.edges:
            if not edge.route_map:
                continue
            for target_id in edge.route_map.values():
                target_node = workflow.get_node(target_id)
                if not (target_node and target_node.tool in PARALLEL_TOOLS):
                    continue
                # Walk one hop upstream to find the SOURCE_TOOL providing files
                for upstream in workflow.edges:
                    if upstream.target != edge.source:
                        continue
                    up_node = workflow.get_node(upstream.source)
                    if up_node and up_node.tool in SOURCE_TOOLS:
                        route_map_parallel[target_id] = upstream.source
                        logger.info(
                            "Route-map fan-out detected: %s → %s (files from %s)",
                            edge.source, target_id, upstream.source,
                        )
                        break

    # Add nodes using human-readable names
    for node_def in workflow.nodes:
        tool_fn = get_tool(node_def.tool)
        if tool_fn is None:
            raise ValueError(f"Unknown tool: {node_def.tool}")

        incoming_edges = edges_by_target.get(node_def.id, [])
        node_name = node_names[node_def.id]  # Human-readable name

        # Check if this node receives parallel fan-out (direct edge OR route_map)
        is_parallel_target = (
            any((e["source"], node_def.id) in parallel_edges for e in incoming_edges)
            or node_def.id in route_map_parallel
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
                node_def,
                tool_fn,
                llm_config,
                workflow_config,
                incoming_edges,
                event_callback,
            )
            graph.add_node(node_name, node_fn)

    # Add edges
    # Group parallel edges by source node (one conditional edge per source).
    # A source may connect to the SAME parallel target through more than one
    # port (e.g. files-source → transcribe carries both `files` and the
    # per-page `documents` port, #2523). The fan-out is per (source, target),
    # not per port, so the target must appear ONCE — otherwise the per-file
    # Send list is duplicated and every page is transcribed twice.
    parallel_by_source: dict[str, list[str]] = {}
    for edge in workflow.edges:
        if (edge.source, edge.target) in parallel_edges:
            targets = parallel_by_source.setdefault(edge.source, [])
            if edge.target not in targets:
                targets.append(edge.target)

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

    def _source_graph_name(source_id: str) -> str:
        source_name = node_names[source_id]
        source_is_parallel = (
            any(
                (e.source, e.target) in parallel_edges and e.target == source_id
                for e in workflow.edges
            )
            or source_id in route_map_parallel
        )
        if source_is_parallel:
            return f"{source_name}_aggregate"
        return source_name

    unconditional_by_target: dict[str, list[Any]] = {}
    for edge in workflow.edges:
        if edge.route_map or edge.condition or (edge.source, edge.target) in parallel_edges:
            continue
        unconditional_by_target.setdefault(edge.target, []).append(edge)

    # Node ids that were registered as _process + _aggregate (not bare name).
    # Any edge whose TARGET is in this set must route to "{name}_process".
    parallel_target_node_ids: set[str] = (
        {target for (_, target) in parallel_edges} | set(route_map_parallel.keys())
    )

    def _target_graph_name(target_id: str) -> str:
        name = node_names[target_id]
        if target_id in parallel_target_node_ids:
            return f"{name}_process"
        return name

    waiting_edge_targets: set[str] = set()
    for target_id, incoming in unconditional_by_target.items():
        source_names = list(dict.fromkeys(_source_graph_name(edge.source) for edge in incoming))
        if len(source_names) <= 1:
            continue
        graph.add_edge(source_names, _target_graph_name(target_id))
        waiting_edge_targets.add(target_id)

    # Add non-parallel edges
    added_simple_edges: set[tuple[str, str]] = set()
    for edge in workflow.edges:
        source_name = node_names[edge.source]

        if edge.route_map:
            # Route_map targets that are PARALLEL_TOOLS need combined route+fan-out.
            has_parallel_targets = any(
                tid in route_map_parallel for tid in edge.route_map.values()
            )
            if has_parallel_targets and enable_parallel:
                fan_out_fn = _make_route_map_fan_out_function(
                    edge.route_key, edge.route_map, node_names, route_map_parallel,
                )
                path_map = {}
                for tid in edge.route_map.values():
                    if tid in route_map_parallel:
                        path_map[f"{node_names[tid]}_process"] = f"{node_names[tid]}_process"
                    else:
                        path_map[node_names[tid]] = node_names[tid]
                graph.add_conditional_edges(source_name, fan_out_fn, path_map)
            else:
                route_fn = _make_route_function(edge.route_key, edge.route_map, node_names)
                path_map = {node_names[tid]: node_names[tid] for tid in edge.route_map.values()}
                graph.add_conditional_edges(source_name, route_fn, path_map)
            continue

        target_name = _target_graph_name(edge.target)

        if (edge.source, edge.target) in parallel_edges:
            continue  # Already handled above
        elif edge.target in waiting_edge_targets and not edge.condition:
            continue  # Already handled as a fan-in waiting edge above
        elif edge.condition:
            # Conditional edge (for branching)
            condition_fn = _make_condition_function(edge.condition, workflow_config)
            graph.add_conditional_edges(
                source_name, condition_fn, {True: target_name, False: END}
            )
        else:
            graph_source_name = _source_graph_name(edge.source)
            edge_key = (graph_source_name, target_name)
            if edge_key in added_simple_edges:
                continue
            graph.add_edge(graph_source_name, target_name)
            added_simple_edges.add(edge_key)

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
        # Check if this exit node was parallelized (direct edge OR route_map fan-out)
        is_parallel = (
            any(
                (e.source, e.target) in parallel_edges and e.target == exit_id
                for e in workflow.edges
            )
            or exit_id in route_map_parallel
        )
        if is_parallel:
            graph.add_edge(f"{exit_name}_aggregate", END)
        else:
            graph.add_edge(exit_name, END)

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
    )


def _make_node_function(
    node_def: NodeDef,
    tool_fn: callable,
    llm_config: LLMConfig,
    workflow_config: dict[str, Any] | None = None,
    incoming_edges: list[dict] | None = None,
    event_callback: Any | None = None,
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
    node_llm_config = _resolve_node_llm_config(node_def, llm_config)

    # Pre-compute caching eligibility once (closure over node_def + workflow_config).
    workflow_id = workflow_config.get("workflow_id", "") if workflow_config else ""
    skip_cache = workflow_config.get("skip_cache", False) if workflow_config else False
    _is_seq_cacheable = is_sequentially_cacheable(node_def.tool)

    async def node_function(state: State) -> dict:
        """Execute the tool and update state."""
        node_id = node_def.id
        node_label = node_def.label or node_def.tool

        completed_nodes = state.get("completed_nodes") or []
        if node_id in completed_nodes:
            logger.info("Skipping already-completed node: %s", node_id)
            return {}

        if incoming_edges:
            outputs = state.get("outputs", {}) or {}
            missing_sources = sorted(
                {
                    source_node
                    for edge in incoming_edges
                    if (source_node := edge.get("source") or edge.get("source_node_id"))
                    and source_node not in outputs
                }
            )
            if missing_sources:
                logger.info(
                    "Deferring %s until upstream output(s) exist: %s",
                    node_id,
                    ", ".join(missing_sources),
                )
                return {}

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
                        source_path = f"$.nodes.{source_node}.{source_port}"
                        existing = inputs_from_mappings.get(target_port)
                        if existing is None:
                            inputs_from_mappings[target_port] = source_path
                        elif isinstance(existing, list):
                            existing.append(source_path)
                        else:
                            inputs_from_mappings[target_port] = [existing, source_path]
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
            if node_def.tool == "sub_workflow":
                tool_kwargs.setdefault("__node_id", node_id)
            if event_callback:
                async def emit_tool_progress(
                    event_type: str,
                    data: dict[str, Any],
                ) -> None:
                    payload = dict(data)
                    payload.setdefault("node_id", node_id)
                    await event_callback(event_type, payload)

                tool_kwargs["__progress_callback"] = emit_tool_progress

            # --- Sequential-node batch cache check (#2246) ---
            # Mirrors the per-file parallel cache but keys on the whole
            # input-files batch so catalogue/extract_all/cleanup re-runs
            # against unchanged files skip the LLM call entirely.
            seq_cache = None
            seq_cache_key = None
            if _is_seq_cacheable and not skip_cache:
                library_path = state.get("library_path", "")
                if library_path:
                    try:
                        db_path = Path(library_path) / "fichero.duckdb"
                        if db_path.exists():
                            seq_cache = get_node_cache(db_path)
                            file_paths = list(state.get("files") or [])
                            seq_cache_key = compute_batch_cache_key(
                                workflow_id=workflow_id,
                                node_id=node_id,
                                tool=node_def.tool,
                                config=node_def.config,
                                provider=node_llm_config.provider,
                                model=node_llm_config.model,
                                file_paths=file_paths,
                            )
                            cached_result = seq_cache.get(seq_cache_key)
                            if cached_result is not None and not _result_worth_caching(
                                cached_result
                            ):
                                logger.info(
                                    "Stale empty sequential cache entry for %s; ignoring",
                                    node_label,
                                )
                                cached_result = None
                            if cached_result is not None:
                                logger.info(
                                    "Sequential cache HIT: %s (%d files)",
                                    node_label,
                                    len(file_paths),
                                )
                                outputs = dict(state.get("outputs", {}))
                                outputs[node_id] = cached_result.result
                                completed = list(state.get("completed_nodes", []))
                                completed.append(node_id)
                                return {
                                    "outputs": outputs,
                                    "completed_nodes": completed,
                                    "current_node": node_id,
                                }
                    except Exception as cache_err:
                        logger.warning(
                            "Sequential cache check failed for %s: %s",
                            node_label,
                            cache_err,
                        )

            # Call the tool with resolved inputs
            result = await tool_fn(
                inputs=tool_kwargs,
                state=state,
                llm_config=node_llm_config,
            )

            # Check if tool returned an error (tools return {"error": "..."} on failure).
            # Raise SystemicErrorDetected to ABORT the workflow rather than
            # silently set state.error and let downstream nodes proceed on
            # empty data (#839). The historical behaviour was to return-with-
            # error and continue, which produced indistinguishable-from-
            # success runs that hung waiting on missing inputs (e.g. extract_all
            # 100% guardrail-refused → empty entity context → catalogue
            # narrative call hung indefinitely).
            #
            # Tools that legitimately surface partial-success without aborting
            # should NOT return an "error" key — they should return their
            # partial result and rely on downstream consumers to handle missing
            # data. Setting "error" is now a hard abort signal.
            if isinstance(result, dict) and result.get("error"):
                error_msg = result["error"]
                print(f"[STEP] ✗ FAILED: {node_label}")
                print(f"[STEP]   Error: {error_msg}")
                logger.error(f"Node {node_id} tool returned error: {error_msg}")
                raise SystemicErrorDetected(
                    message=f"Step '{node_label}' failed: {error_msg}",
                    error_count=1,
                    total_count=1,
                    errors=[{"node": node_id, "error": error_msg}],
                )

            # #2613: a node that intentionally has nothing to do (e.g. an
            # empty-query Reference Corpus Search) reports a clear skip and
            # lets the pipeline continue with empty outputs. It must NOT be
            # treated as a failure or run through the quality gate.
            if isinstance(result, dict) and result.get("skipped"):
                skip_reason = result.get("skip_reason", "skipped")
                print(f"[STEP] ⊘ SKIPPED: {node_label} — {skip_reason}")
                logger.info("Node %s skipped: %s", node_id, skip_reason)

            # Quality gate (#1029): a node can return without raising yet
            # produce garbage — a page that OCR'd to box glyphs, a
            # transcription that is mostly [ilegible]. Advancing the
            # pipeline on that noise yields a "successful" but empty run
            # the user can't diagnose. When the node's quality_gate config
            # is on (default), abort so the failure is visible and the
            # cached re-run is cheap.
            #
            # The gate stops the run only when EVERY page the node
            # produced is garbage — a few bad pages in an otherwise-fine
            # multi-page document do not abort it. Gates on garbage, NOT
            # on empty output — emptiness is each tool's own concern.
            if isinstance(result, dict) and node_def.config.get(
                "quality_gate", True
            ):
                should_stop, reason = assess_result_quality(result)
                if should_stop:
                    print(f"[STEP] ✗ QUALITY GATE: {node_label}")
                    print(f"[STEP]   {reason}")
                    logger.error(
                        f"Node {node_id} failed quality gate: {reason}"
                    )
                    raise SystemicErrorDetected(
                        message=(
                            f"Step '{node_label}' produced unreadable "
                            f"output — {reason}"
                        ),
                        error_count=1,
                        total_count=1,
                        errors=[{"node": node_id, "error": reason}],
                    )

            # Page-level cross-document contamination heuristic (#1399):
            # flag suspicious outlier pages (language/jurisdiction mismatch)
            # without aborting the run.
            if isinstance(result, dict):
                contamination = detect_page_contamination_warnings(result)
                if contamination:
                    logger.warning(
                        "Node %s flagged %d possible mis-filed page(s)",
                        node_id,
                        len(contamination),
                    )
                    existing_warnings = result.get("quality_warnings")
                    if isinstance(existing_warnings, list):
                        result["quality_warnings"] = [
                            *existing_warnings,
                            *contamination,
                        ]
                    else:
                        result["quality_warnings"] = contamination

            # --- Sequential-node batch cache write (#2246) ---
            if (
                seq_cache is not None
                and seq_cache_key is not None
                and isinstance(result, dict)
                and _result_worth_caching(result)
            ):
                try:
                    seq_cache.set(
                        cache_key=seq_cache_key,
                        result=result,
                        workflow_id=workflow_id,
                        node_id=node_id,
                        tool=node_def.tool,
                        file_path=None,
                    )
                    logger.debug(
                        "Sequential cache SET: %s (%s)", node_label, seq_cache_key[:16]
                    )
                except Exception as cache_err:
                    logger.warning(
                        "Sequential cache write failed for %s: %s", node_label, cache_err
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

            print(f"[STEP] ✓ Completed: {node_label}")

            return {
                "outputs": outputs,
                "output_files": output_files,
                "completed_nodes": completed,
                "current_node": node_id,
            }

        except SystemicErrorDetected:
            # Hard-abort signal — must propagate, not be reduced to a dict.
            # The aggregator + node-error paths raise this when the workflow
            # genuinely cannot continue; LangGraph propagates it to the
            # executor which marks the run as failed and stops the spinners
            # (#839).
            raise
        except Exception as e:
            error_msg = str(e)
            print(f"[STEP] ✗ FAILED: {node_label}")
            print(f"[STEP]   Error: {error_msg}")
            logger.error(f"Node {node_id} failed: {e}")

            # All unhandled node exceptions abort the workflow (#1347).
            # Prior behaviour: return {"error": ...} which set state.error
            # but let LangGraph advance to the next node — downstream nodes
            # (catalogue, kg_writer) then ran on empty data and silently
            # persisted nothing, reporting 'completed' with an empty KG.
            #
            # Fix: raise SystemicErrorDetected so LangGraph propagates the
            # exception and the runner marks the run as failed immediately.
            # Quota/rate-limit errors are detected and logged with more
            # specific context before raising; all others use a generic message.
            if _is_quota_error(e):
                logger.warning(
                    f"Quota/rate-limit error detected in {node_label}: {error_msg}"
                )
                raise SystemicErrorDetected(
                    message=f"Quota/rate-limit error in step '{node_label}': {error_msg}",
                    error_count=1,
                    total_count=1,
                )

            raise SystemicErrorDetected(
                message=f"Step '{node_label}' failed: {error_msg}",
                error_count=1,
                total_count=1,
                errors=[{"node": node_id, "error": error_msg}],
            )

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

    from langgraph.types import Send  # noqa: PLC0415

    # NOTE: no `-> list[Send]` return annotation. langgraph's
    # add_conditional_edges calls get_type_hints() on this function, which
    # evaluates annotations in the module namespace — where `Send` is NOT
    # defined (it's a function-local import to keep langgraph out of module
    # import time, per the May-18 lazy-import refactor). Annotating the return
    # re-introduced `NameError: name 'Send' is not defined` at graph-build.
    def fan_out(state: State):
        """Fan out to parallel file processing. Returns list[Send]."""
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
                            # Preserve essential state. Intentionally NOT
                            # copying the whole "outputs" dict here (#2532):
                            # _make_parallel_node_function reads only
                            # parallel_file/document/index/total + library_path,
                            # and its tool reads library_path/task_id from
                            # state — none read "outputs". At thousands of files
                            # this Send list materialises one payload per file
                            # BEFORE the vision semaphore throttles anything, so
                            # duplicating the full outputs-blob per Send was a
                            # multiplicative RAM cost for data nobody consumed.
                            # The aggregator runs in the main graph and still
                            # sees the full outputs channel.
                            "task_id": state.get("task_id", ""),
                            "workflow_id": state.get("workflow_id", ""),
                            "library_path": state.get("library_path", ""),
                        },
                    )
                )

        # Memory bound at large fan-out widths (#2532/#2541 C3). Three costs,
        # only one of which is dangerous and it is already capped:
        #
        #  1. HEAVY in-flight work (image bytes, LLM request/response buffers).
        #     This is the OOM risk. It is bounded NOT here but at execution
        #     time: _make_parallel_node_function wraps each tool call in the
        #     module-global vision semaphore (_get_vision_semaphore, cap
        #     VISION_FAN_OUT_CONCURRENCY=4). LangGraph creates a coroutine per
        #     Send, but all but ~4 block on the semaphore before allocating any
        #     heavy buffer, so peak heavy memory is O(4), independent of file
        #     count. test_parallel_fan_out_bounds_concurrency locks this.
        #
        #  2. This Send list: O(files) lightweight descriptors. Each payload was
        #     trimmed (above) to a handful of small fields — NO "outputs" blob —
        #     so 5,000 files is a few MB of dict descriptors, not the
        #     multiplicative outputs-per-Send cost that motivated the trim.
        #
        #  3. parallel_results retention until the aggregator barrier — see the
        #     ponytail note in _make_aggregation_function. That is the genuine
        #     remaining O(files) ceiling; bounding it means streaming the
        #     barrier, which is the invasive "needs its own design" change.
        #
        # ponytail: chunking files into multi-file Sends would shrink (2) but is
        # deliberately NOT done — the per-file Send is a hard contract
        # (exactly-once per-page resume + distinct per-page cache keys, #896,
        # locked by test_parallel_checkpointer_resume), and a multi-file Send
        # loses per-file checkpoint/resume granularity. (2) is cheap; the real
        # throttle is the semaphore in (1).
        return sends

    return fan_out


def _make_route_map_fan_out_function(
    route_key: str,
    route_map: dict[str, str],
    node_names: dict[str, str],
    route_map_parallel: dict[str, str],
):
    """Create a combined route + fan-out conditional edge function (#2236).

    When the route_key resolves to a PARALLEL_TOOL target, returns Send() objects
    (one per file from the upstream SOURCE_TOOL) instead of a string node name.
    For non-parallel targets, returns the target node name (standard routing).

    NOTE: no return type annotation — add_conditional_edges calls get_type_hints()
    in the module namespace where local Send import is not defined.
    """
    from langgraph.types import Send  # noqa: PLC0415

    first_target_id = next(iter(route_map.values()), "")
    first_is_parallel = first_target_id in route_map_parallel
    first_fallback = (
        f"{node_names[first_target_id]}_process"
        if first_is_parallel and first_target_id in node_names
        else node_names.get(first_target_id, "")
    )
    parts = route_key.rsplit(".", 1)
    needs_human_key = parts[0] + ".needs_human_selection" if len(parts) == 2 else ""

    def route_and_fan_out(state: State):
        from fichero_server.workflows.resolver import resolve_value  # noqa: PLC0415

        val = resolve_value(route_key, state, None)
        val_str = str(val) if val is not None else ""
        human_target = route_map.get("needs_human_selection")
        needs_human = bool(
            needs_human_key and resolve_value(needs_human_key, state, False)
        )
        if needs_human and human_target in node_names:
            logger.info(
                "route_map_fan_out: %r → needs_human_selection=True; routing to %s",
                route_key,
                node_names[human_target],
            )
            return node_names[human_target]

        target_id = route_map.get(val_str)

        if not target_id or target_id not in node_names:
            if human_target in node_names:
                logger.info(
                    "route_map_fan_out: key %r resolved to unknown value %r; routing to %s",
                    route_key,
                    val_str,
                    node_names[human_target],
                )
                return node_names[human_target]
            logger.warning(
                "route_map_fan_out: key %r resolved to unknown value %r; "
                "falling back to %s", route_key, val_str, first_fallback,
            )
            return first_fallback

        target_name = node_names[target_id]

        if target_id not in route_map_parallel:
            return target_name

        # Fan out: one Send per file from the upstream SOURCE_TOOL
        files_source_id = route_map_parallel[target_id]
        source_output = state.get("outputs", {}).get(files_source_id, {})
        files = source_output.get("files", [])
        documents = source_output.get("documents", [])

        if not files:
            logger.warning(
                "route_map_fan_out: no files from %s to fan out to %s",
                files_source_id, target_id,
            )
            return f"{target_name}_process"

        total = len(files)
        sends = []
        for i, file_path in enumerate(files):
            doc = None
            if i < len(documents):
                doc = documents[i]
            elif documents:
                for d in documents:
                    if isinstance(d, dict) and d.get("path") == file_path:
                        doc = d
                        break
            sends.append(
                Send(
                    f"{target_name}_process",
                    {
                        "parallel_file": file_path,
                        "parallel_document": doc,
                        "parallel_index": i,
                        "parallel_total": total,
                        # No "outputs" blob per Send — see _make_fan_out_function
                        # (#2532): the parallel worker + its tool read only the
                        # parallel_* keys + library_path/task_id, never outputs.
                        "task_id": state.get("task_id", ""),
                        "workflow_id": state.get("workflow_id", ""),
                        "library_path": state.get("library_path", ""),
                    },
                )
            )
        return sends

    return route_and_fan_out


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
    node_llm_config = _resolve_node_llm_config(node_def, llm_config)

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

        event_document_meta: dict[str, Any] = {}
        if isinstance(document, dict):
            leaf_id = document.get("id")
            parent_id = document.get("parent_id")
            display_name = document.get("name")
            sequence = document.get("sequence")
            if isinstance(parent_id, str) and parent_id and isinstance(leaf_id, str) and leaf_id:
                event_document_meta["document_id"] = parent_id
                event_document_meta["page_id"] = leaf_id
            elif isinstance(leaf_id, str) and leaf_id:
                event_document_meta["document_id"] = leaf_id
            if isinstance(display_name, str) and display_name:
                event_document_meta["display_name"] = display_name
            if isinstance(sequence, int):
                event_document_meta["sequence"] = sequence

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
                    # Pass document.id so per-page PDF fan-out gets
                    # distinct cache keys even though all six page
                    # children share the parent PDF's path. (#896 root
                    # cause: shared key meant the page-1 result was
                    # returned for pages 2-6, producing Davidson ×6.)
                    doc_id_for_cache: str | None = None
                    if isinstance(document, dict):
                        doc_id_for_cache = document.get("id")
                    cache_key = compute_cache_key(
                        workflow_id=workflow_id,
                        node_id=node_id,
                        tool=node_def.tool,
                        config=node_def.config,
                        provider=node_llm_config.provider,
                        model=node_llm_config.model,
                        file_path=file_path,
                        document_id=doc_id_for_cache,
                    )

                    # Check cache. Treat empty/unusable cached entries as
                    # misses so existing poisoned entries from prior runs
                    # don't block recovery — pairs with the cache-write
                    # gate below that no longer stores empties (#834,
                    # #837 follow-up). Without this, libraries that
                    # cached an empty Apple Vision result while a
                    # bug was active stay broken until manually cleared.
                    cached_result = cache.get(cache_key)
                    if cached_result is not None and not _result_worth_caching(cached_result):
                        logger.info(
                            f"Stale empty cache entry for {file_path}; ignoring + redoing"
                        )
                        cached_result = None
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
                                    **event_document_meta,
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
                        **event_document_meta,
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
            if event_callback:
                async def emit_tool_progress(
                    event_type: str,
                    data: dict[str, Any],
                ) -> None:
                    payload = dict(data)
                    payload.setdefault("node_id", node_id)
                    payload.setdefault("file_path", file_path)
                    payload.setdefault("file_index", index)
                    payload.setdefault("file_total", total)
                    for meta_key, meta_value in event_document_meta.items():
                        payload.setdefault(meta_key, meta_value)
                    await event_callback(event_type, payload)

                tool_inputs["__progress_callback"] = emit_tool_progress

            # Cap concurrent in-flight vision/LLM calls to avoid OOM when a
            # large batch dispatches dozens of Sends simultaneously (#2221).
            async with _get_vision_semaphore():
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
                                **event_document_meta,
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
            # Skip caching when the result has no usable content. An empty
            # transcribe returning "" gets cached forever and poisons every
            # subsequent run on the same file (#834 / #837 follow-up). Better
            # to re-do the work next time and hope for non-empty.
            if cache and cache_key and is_cacheable and _result_worth_caching(result):
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
            elif cache and cache_key and is_cacheable:
                logger.info(
                    f"Skipping cache write for {file_path}: empty/unusable result"
                )

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
                            **event_document_meta,
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

            # Detect quota/rate-limit errors and pause workflow (#1222)
            if _is_quota_error(e):
                logger.warning(f"Quota/rate-limit error detected in parallel processing: {error_msg}")
                raise SystemicErrorDetected(
                    message=f"Quota/rate-limit error in {node_id}: {error_msg}",
                    error_count=1,
                    total_count=total,
                )

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
                            **event_document_meta,
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
        """Aggregate parallel processing results.

        Defers emission until all parallel sends have landed (#837). Each
        parallel sub-node carries its `total` count alongside its result;
        we use it as a barrier — until len(parallel_results) >= total,
        return {} (no state update) so LangGraph re-fires the aggregator
        on the next per-Send arrival without committing partial output
        to downstream consumers.

        Without this barrier, the auto-aggregator was firing on the first
        Send dispatch with empty parallel_results and silently emitting
        an empty aggregate, which downstream user-aggregate nodes then
        consumed — leaving catalogue/extract_all with no text input even
        though transcribe was still running (#837, full trace in the
        issue). The deferred-emission pattern lets LangGraph's Send fan-
        out work as a true barrier.
        """
        # ponytail (#2541 C3 aggregator ceiling): this barrier holds ALL branch
        # results in State until the last Send lands — parallel_results[node_id]
        # is a list of `total` entries, each carrying the branch's full `result`
        # dict (transcription text, page_records, artifacts). At thousands of
        # files this is the dominant retained memory: O(files × result_size),
        # e.g. ~5,000 pages × a few KB of text/records ≈ tens of MB, plus the
        # per-Send checkpoint write-amplification the checkpointer must persist.
        # Bounding it requires STREAMING aggregation (persist + drop each branch
        # result as it lands, emit downstream incrementally) instead of the
        # all-at-once barrier — but the barrier is a correctness contract:
        # downstream nodes (catalogue, kg_writer) consume the COMPLETE aggregate,
        # and the deferred-emission barrier is exactly what fixed #837. Streaming
        # it is a separate design (incremental reducers + a downstream that can
        # consume partial input) and is intentionally NOT half-done here. Ceiling
        # for now: a run fans out at most one PARALLEL node's worth of pages at a
        # time, so peak retention is bounded by the largest single fan-out's
        # total page count, not the whole library.
        parallel_results = state.get("parallel_results", {}).get(node_id, [])

        if not parallel_results:
            logger.warning(f"No parallel results to aggregate for {node_id}")
            return {}

        # Determine expected count from the first result that carries one.
        # Returns 0 when no result carries `total` — defensive, would mean
        # every parallel_node_function forgot to thread `total` through.
        expected_total = 0
        for item in parallel_results:
            t = item.get("total") if isinstance(item, dict) else None
            if isinstance(t, int) and t > 0:
                expected_total = t
                break
        if expected_total > 0 and len(parallel_results) < expected_total:
            logger.info(
                f"Aggregator {node_id}: deferring — got "
                f"{len(parallel_results)}/{expected_total} results so far"
            )
            return {}

        # Sort by index to maintain order
        sorted_results = sorted(parallel_results, key=lambda x: x.get("index", 0))

        # Aggregate results
        all_texts = []
        all_results = []
        all_artifacts = []
        all_page_records: list[dict] = []
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
                    page_recs = result.get("page_records")
                    if isinstance(page_recs, list):
                        for rec in page_recs:
                            if isinstance(rec, dict) and rec.get("text"):
                                all_page_records.append(rec)
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

        if success_count == 0 and error_count > 0:
            error_msg = (
                f"All parallel branches failed for {node_id}. "
                f"First error: {errors[0]['error'] if errors else 'unknown'}"
            )
            logger.error(error_msg)
            raise SystemicErrorDetected(
                message=error_msg,
                error_count=error_count,
                total_count=total,
                errors=errors[:10],
            )

        # Build aggregated output. `records` carries per-page provenance
        # for the records port (extract_all, page_cleanup) — flat list of
        # {doc_id, text} across all parallel files, in the same parallel-
        # index order as `texts`. See vision_base._build_page_records_for_file.
        aggregated = {
            "text": "\n\n".join(all_texts),
            "texts": all_texts,
            "records": all_page_records,
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


def _make_route_function(
    route_key: str,
    route_map: dict[str, str],
    node_names: dict[str, str],
):
    """Create a routing function for multi-way conditional edges.

    Resolves route_key from state, looks up the result in route_map (value →
    node ID), and returns the corresponding graph node name.

    Behaviour when the value is unknown or needs_human_selection=True:
    - If the route_map has a "needs_human_selection" branch AND the source node
      set needs_human_selection=True (or the value is not in the route_map),
      the workflow is routed there so the condition is surfaced explicitly
      rather than silently continuing down an arbitrary branch.
    - If no such branch exists, falls back to the first route_map entry and
      logs at ERROR level so the missing branch is discoverable. (#2238)

    NOTE: no return type annotation — add_conditional_edges calls
    get_type_hints() in the module namespace where local imports are not
    defined.  See the fan_out function for the same pattern.
    """
    from fichero_server.workflows.resolver import resolve_value  # noqa: PLC0415

    first_node_name = node_names.get(next(iter(route_map.values()), ""), "")
    # Derive the needs_human_selection key from the same JSONPath namespace
    # as route_key so we don't need to hard-code the source node name.
    # e.g. "$.nodes.classify.script_type" → "$.nodes.classify.needs_human_selection"
    parts = route_key.rsplit(".", 1)
    needs_human_key = parts[0] + ".needs_human_selection" if len(parts) == 2 else ""

    def route(state: State):
        val = resolve_value(route_key, state, None)
        val_str = str(val) if val is not None else ""
        human_target = route_map.get("needs_human_selection")

        # Honour the needs_human_selection signal from the source node (#2238).
        # Prefer a dedicated "needs_human_selection" branch when available.
        needs_human = bool(
            needs_human_key and resolve_value(needs_human_key, state, False)
        )
        if needs_human and human_target in node_names:
            logger.info(
                "route_map: %r → needs_human_selection=True; routing to %s",
                route_key,
                node_names[human_target],
            )
            return node_names[human_target]

        target_id = route_map.get(val_str)
        if target_id and target_id in node_names:
            return node_names[target_id]
        if human_target in node_names:
            logger.info(
                "route_map: key %r resolved to unknown value %r; routing to %s",
                route_key,
                val_str,
                node_names[human_target],
            )
            return node_names[human_target]

        logger.error(
            "route_map: key %r resolved to unknown value %r "
            "(needs_human_selection=%r); falling back to %s. "
            "Add a '%s' or 'needs_human_selection' branch to the workflow route_map.",
            route_key,
            val_str,
            needs_human,
            first_node_name,
            val_str,
        )
        return first_node_name

    return route


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
