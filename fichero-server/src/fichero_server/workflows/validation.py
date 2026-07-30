"""
Tool Validation Functions

Functions for validating tool connections, node configurations, and workflow structure.
"""

from __future__ import annotations

import logging

from collections.abc import Callable

from fichero_server.workflows.types import (
    PortDef,
    NodeDef,
    WorkflowDef,
    DataType,
    ToolDef,
)
from fichero_server.workflows.registry import TOOL_DEFS, enrich_node_with_ports
from fichero_server.llm import LLMConfig
from fichero_server.workflows.subworkflow import validate_sub_workflow_references

logger = logging.getLogger(__name__)


def validate_port_connection(source_port: PortDef, target_port: PortDef) -> bool:
    """Validate that a connection between two ports is compatible.

    Args:
        source_port: The source (output) port
        target_port: The target (input) port

    Returns:
        True if connection is valid, False otherwise
    """
    # Check if source is output and target is input
    if source_port.port_type != "output":
        logger.warning(f"Source port {source_port.id} is not an output port")
        return False

    if target_port.port_type != "input":
        logger.warning(f"Target port {target_port.id} is not an input port")
        return False

    # Check data type compatibility
    source_type = source_port.data_type
    target_type = target_port.data_type

    # ANY type is compatible with anything
    if source_type == DataType.ANY or target_type == DataType.ANY:
        return True

    # Same types are compatible
    if source_type == target_type:
        return True

    # Specific type compatibilities
    compatible_types = {
        DataType.FILES: [DataType.FILE],  # Files can connect to single file
        DataType.ARRAY: [DataType.ANY],  # Arrays can connect to any (individual items)
    }

    if source_type in compatible_types and target_type in compatible_types[source_type]:
        return True

    logger.warning(f"Incompatible data types: {source_type} -> {target_type}")
    return False


def validate_node_connections(
    node: NodeDef,
    tool_def: ToolDef | None = None,
    edge_target_ports: set[str] | None = None,
) -> list[str]:
    """Validate all connections for a node.

    Args:
        node: The node to validate
        tool_def: Optional tool definition for additional validation
        edge_target_ports: Optional set of port ids on this node that are fed
            by an incoming workflow edge (satisfies required-port checks the
            same way an input mapping does)

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Get tool definition if not provided
    if not tool_def:
        tool_def = TOOL_DEFS.get(node.tool)
        if not tool_def:
            errors.append(f"Unknown tool: {node.tool}")
            return errors

    # Check required input ports
    required_inputs = [p for p in tool_def.input_ports if p.required]
    for port in required_inputs:
        # Check if port has a mapping, an incoming edge, or the port has data
        has_mapping = any(m.port_id == port.id for m in node.input_mappings)
        has_edge = bool(edge_target_ports) and port.id in edge_target_ports
        has_default = port.default is not None

        has_input_value = port.id in (node.inputs or {})

        if not has_mapping and not has_edge and not has_default and not has_input_value:
            errors.append(
                f"Required input port '{port.id}' on node '{node.id}' has no mapping or default value"
            )

    # Check that all input mappings reference valid ports
    for mapping in node.input_mappings:
        # Check if target port exists
        target_port_exists = any(p.id == mapping.port_id for p in tool_def.input_ports)
        if not target_port_exists:
            errors.append(
                f"Input mapping references unknown port '{mapping.port_id}' on node '{node.id}'"
            )

    return errors


def validate_workflow_connections(workflow: WorkflowDef) -> list[str]:
    """Validate all connections in a workflow.

    Args:
        workflow: The workflow to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Build a map of enriched nodes (with ports from registry)
    enriched_nodes: dict[str, NodeDef] = {}
    for node in workflow.nodes:
        enriched_nodes[node.id] = enrich_node_with_ports(node)

    # Build a map of node_id -> set of input port ids fed by an incoming edge,
    # so an edge satisfies a required-port check the same way a mapping does.
    edge_targets_by_node: dict[str, set[str]] = {}
    for edge in workflow.edges:
        edge_targets_by_node.setdefault(edge.target, set()).add(edge.target_port)

    # Validate each node
    for node in workflow.nodes:
        node_errors = validate_node_connections(
            node, edge_target_ports=edge_targets_by_node.get(node.id)
        )
        errors.extend(node_errors)

    # Validate each edge
    for edge in workflow.edges:
        source_node = enriched_nodes.get(edge.source)
        if not source_node:
            errors.append(f"Edge references unknown source node: {edge.source}")
            continue

        if edge.route_map:
            for target_id in edge.route_map.values():
                if target_id not in enriched_nodes:
                    errors.append(
                        f"Edge route_map references unknown node: {target_id}"
                    )
            continue

        target_node = enriched_nodes.get(edge.target)
        if not target_node:
            errors.append(f"Edge references unknown target node: {edge.target}")
            continue

        # Find source and target ports (now guaranteed to have ports from registry)
        source_port = next(
            (p for p in source_node.output_ports if p.id == edge.source_port), None
        )
        target_port = next(
            (p for p in target_node.input_ports if p.id == edge.target_port), None
        )

        if not source_port:
            errors.append(
                f"Edge references unknown source port '{edge.source_port}' on node '{edge.source}'"
            )
            continue

        if not target_port:
            errors.append(
                f"Edge references unknown target port '{edge.target_port}' on node '{edge.target}'"
            )
            continue

        # Validate connection compatibility
        if not validate_port_connection(source_port, target_port):
            errors.append(
                f"Invalid connection from {edge.source}.{edge.source_port} to {edge.target}.{edge.target_port}"
            )

    return errors


def _required_llm_capability(tool_def: ToolDef) -> str:
    category = str(tool_def.category or "").strip().lower()
    if category in {"vision", "audio", "video"}:
        return category
    return "text"


def _node_provider_model(node: NodeDef) -> tuple[str, str]:
    provider = node.provider_name or node.config.get("provider_name", "")
    model = node.model_name or node.config.get("model_name", "")
    return (provider, model)


def _node_model_profile_ref(node: NodeDef) -> str:
    ref = (
        node.config.get("model_profile_id")
        or node.config.get("profile_id")
        or node.config.get("model_profile")
    )
    if ref:
        return str(ref)

    provider, _model = _node_provider_model(node)
    from fichero_server.llm import extract_model_profile_reference

    return extract_model_profile_reference(provider) or ""


def _require_provider_credentials(provider: str) -> None:
    """Raise when a RESOLVED cloud provider has no API key configured (#4325).

    Missing credentials used to surface as a construction exception inside the
    node, mid-run. Checking presence here turns that into a pre-run preflight
    message that names the provider. Local/built-in providers (apple, mock,
    ollama, lmstudio, omlx) and unknown/custom provider names are never
    gated — only catalog cloud providers that declare an api_key_env.
    """
    from fichero_server.llm import get_api_key
    from fichero_server.llm.providers import get_provider_info

    info = get_provider_info((provider or "").strip().lower())
    if info is None or info.is_local or info.is_builtin or not info.api_key_env:
        return
    if get_api_key(info.type.value):
        return
    raise ValueError(
        f"Provider '{info.name}' requires an API key and none is configured. "
        f"Add a {info.name} key in Settings (or set {info.api_key_env}), "
        "or pick an on-device model for this node."
    )


def validate_workflow_llm_preflight(
    workflow: WorkflowDef,
    workflow_llm_config: LLMConfig | None = None,
) -> list[str]:
    """Resolve LLM aliases and policy-check workflow nodes without execution."""
    errors: list[str] = []
    llm_config = workflow_llm_config or LLMConfig(
        provider=workflow.provider,
        model=workflow.model,
    )

    for node in workflow.nodes:
        tool_def = TOOL_DEFS.get(node.tool)
        if not (tool_def and tool_def.uses_llm):
            continue

        capability = _required_llm_capability(tool_def)
        node_provider, node_model = _node_provider_model(node)
        profile_ref = _node_model_profile_ref(node)
        kind = "vision" if capability == "vision" else "llm"

        try:
            if profile_ref:
                from fichero_server.llm import (
                    enforce_local_only_provider,
                    resolve_model_profile_for_capability,
                )

                profile_config = resolve_model_profile_for_capability(
                    profile_ref,
                    base_config=llm_config,
                    required_capability=capability,
                )
                enforce_local_only_provider(
                    profile_config.provider,
                    profile_config.model,
                    kind=kind,
                )
                _require_provider_credentials(profile_config.provider)
                continue

            if node_provider or node_model:
                provider = node_provider or llm_config.provider
                model = node_model or llm_config.model
                from fichero_server.llm import (
                    enforce_local_only_provider,
                    resolve_model_alias_for_capability,
                )

                provider, model = resolve_model_alias_for_capability(
                    provider,
                    model,
                    required_capability=capability,
                )
                enforce_local_only_provider(provider, model, kind=kind)
                _require_provider_credentials(provider)
                continue

            provider = llm_config.provider
            model = llm_config.model
            from fichero_server.llm import extract_model_profile_reference

            workflow_profile_ref = extract_model_profile_reference(provider)
            if workflow_profile_ref:
                from fichero_server.llm import (
                    enforce_local_only_provider,
                    resolve_model_profile_for_capability,
                )

                profile_config = resolve_model_profile_for_capability(
                    workflow_profile_ref,
                    base_config=llm_config,
                    required_capability=capability,
                )
                enforce_local_only_provider(
                    profile_config.provider,
                    profile_config.model,
                    kind=kind,
                )
                _require_provider_credentials(profile_config.provider)
                continue

            if not (provider and model):
                try:
                    from fichero_server.db.app import get_app_db

                    app_db = get_app_db()
                    cat_default = app_db.get_default_model_for_category(
                        tool_def.category
                    )
                except Exception as exc:
                    logger.debug(
                        "Workflow preflight category default lookup failed for %s: %s",
                        node.tool,
                        exc,
                    )
                    cat_default = None
                if cat_default:
                    provider, model = cat_default

            if provider or model:
                from fichero_server.llm import (
                    enforce_local_only_provider,
                    resolve_model_alias_for_capability,
                )

                provider, model = resolve_model_alias_for_capability(
                    provider,
                    model,
                    required_capability=capability,
                )
                enforce_local_only_provider(provider, model, kind=kind)
                _require_provider_credentials(provider)
        except Exception as exc:
            node_label = node.label or node.id or node.tool
            errors.append(f"Node '{node_label}' ({node.tool}): {exc}")

    return errors


def validate_workflow_preflight(
    workflow: WorkflowDef,
    workflow_llm_config: LLMConfig | None = None,
    workflow_resolver: Callable[[str], WorkflowDef | None] | None = None,
) -> list[str]:
    """Validate LLM alias/capability/privacy policy before execution."""
    return [
        *validate_workflow_llm_preflight(workflow, workflow_llm_config),
        *validate_sub_workflow_references(
            workflow,
            workflow_resolver=workflow_resolver,
        ),
    ]


def get_compatible_tools(target_port: PortDef) -> list[ToolDef]:
    """Get tools that can connect to a specific target port.

    Args:
        target_port: The target input port

    Returns:
        List of compatible tool definitions
    """
    compatible_tools = []

    for tool_name, tool_def in TOOL_DEFS.items():
        # Check if this tool has any output ports compatible with target
        for output_port in tool_def.output_ports:
            if validate_port_connection(output_port, target_port):
                compatible_tools.append(tool_def)
                break  # Only need one compatible output per tool

    return compatible_tools
