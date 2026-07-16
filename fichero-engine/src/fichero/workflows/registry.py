"""
Tool Registry

Central registry of all available workflow tools.
Tools are registered with their metadata for use in workflows and the node editor.

Each tool defines:
- Input/output ports for visual connections
- Configuration schema
- LLM requirements
- Visual styling (icon, color)
"""

from __future__ import annotations

import logging
import uuid
from typing import Callable, Any

from fichero.workflows.types import (
    ToolDef,
    PortDef,
    NodeDef,
    DataType,
)
from fichero.workflows.registry_builtins import _register_builtin_tools

logger = logging.getLogger(__name__)

# Global tool registry
TOOLS: dict[str, Callable] = {}
TOOL_DEFS: dict[str, ToolDef] = {}


def register_tool(
    name: str,
    display_name: str,
    description: str = "",
    category: str = "general",
    icon: str = "gearshape",
    color: str = "gray",
    input_ports: list[PortDef] | None = None,
    output_ports: list[PortDef] | None = None,
    config_schema: dict[str, Any] | None = None,
    config_defaults: dict[str, Any] | None = None,
    default_output_schema: dict[str, Any] | None = None,
    default_prompt: str | None = None,
    prompt_builder: Callable[[dict[str, Any]], str] | None = None,
    uses_llm: bool = False,
    supports_batch: bool = False,
    supports_streaming: bool = False,
    supports_structured_output: bool = False,
    sort_order: int = 100,
    tested: bool = False,
):
    """Decorator to register a tool function.

    Usage:
        @register_tool(
            name="transcribe",
            display_name="Transcribe",
            description="Extract text from images using vision LLM",
            category="vision",
            icon="text.viewfinder",
            color="blue",
            input_ports=[
                PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES),
            ],
            output_ports=[
                PortDef(id="text", name="Text", port_type="output", data_type=DataType.TEXT),
            ],
            uses_llm=True,
            default_prompt="Extract all text from this image...",
            prompt_builder=build_transcribe_prompt,  # Optional: dynamic prompt
        )
        async def transcribe(state: State, config: dict) -> dict:
            ...
    """

    def decorator(func: Callable) -> Callable:
        # Store the function
        TOOLS[name] = func

        # Default ports only when omitted (None), not when explicitly empty.
        # Source tools intentionally pass [] to indicate no input ports.
        default_input = [
            PortDef(id="input", name="Input", port_type="input", data_type=DataType.ANY)
        ]
        default_output = [
            PortDef(
                id="output", name="Output", port_type="output", data_type=DataType.ANY
            )
        ]

        # Store metadata
        TOOL_DEFS[name] = ToolDef(
            name=name,
            display_name=display_name,
            description=description,
            category=category,
            icon=icon,
            color=color,
            input_ports=default_input if input_ports is None else input_ports,
            output_ports=default_output if output_ports is None else output_ports,
            config_schema=config_schema or {},
            config_defaults=config_defaults or {},
            default_output_schema=default_output_schema,
            default_prompt=default_prompt,
            prompt_builder=prompt_builder,
            uses_llm=uses_llm,
            supports_batch=supports_batch,
            supports_streaming=supports_streaming,
            supports_structured_output=supports_structured_output,
            sort_order=sort_order,
            tested=tested,
        )

        logger.debug(f"Registered tool: {name}")
        return func

    return decorator


# Aliases for tools (map UI name → implementation)
TOOL_ALIASES: dict[str, str] = {
    "summarize": "summarize_file",  # Generic summarize uses summarize_file
}


def get_tool(name: str) -> Callable | None:
    """Get a tool function by name."""
    # Check direct registration first
    if name in TOOLS:
        return TOOLS[name]
    # Check aliases
    if name in TOOL_ALIASES:
        return TOOLS.get(TOOL_ALIASES[name])
    return None


def get_tool_def(name: str) -> ToolDef | None:
    """Get tool metadata by name."""
    return TOOL_DEFS.get(name)


def list_tools() -> list[ToolDef]:
    """List all registered tools, sorted by sort_order then name."""
    tools = list(TOOL_DEFS.values())
    return sorted(tools, key=lambda t: (t.sort_order, t.name))


def list_tools_by_category(category: str) -> list[ToolDef]:
    """List tools in a specific category, sorted by sort_order."""
    tools = [t for t in TOOL_DEFS.values() if t.category == category]
    return sorted(tools, key=lambda t: (t.sort_order, t.name))


def get_categories() -> list[str]:
    """Get all unique tool categories."""
    categories = set(t.category for t in TOOL_DEFS.values())
    # Return in preferred order
    order = [
        "source",
        "vision",
        "audio",
        "video",
        "transform",
        "llm",
        "convert",
        "logic",
        "sink",
        "utility",
    ]
    result = [c for c in order if c in categories]
    # Add any categories not in our preferred order
    for c in sorted(categories):
        if c not in result:
            result.append(c)
    return result


def enrich_node_with_ports(node: NodeDef) -> NodeDef:
    """Enrich a node with port definitions from the tool registry.

    Ports are defined in the tool registry and should NOT be stored with nodes.
    This function adds the port definitions to a node for:
    - API responses (so UI can display ports)
    - Validation (to check port compatibility)
    - Execution (to resolve input/output connections)

    Args:
        node: A NodeDef, typically loaded from database without ports

    Returns:
        A new NodeDef with ports populated from the tool registry.
        If the tool is not found, returns the node unchanged (preserving any
        existing ports for backward compatibility with tests/inline definitions).
    """
    tool_def = TOOL_DEFS.get(node.tool)
    if not tool_def:
        # Tool not in registry - preserve existing ports for backward compatibility
        # This allows tests and inline workflow definitions to work
        if not node.input_ports and not node.output_ports:
            logger.warning(f"Tool not found in registry: {node.tool}")
        return node

    if node.tool == "sub_workflow":
        try:
            from fichero.workflows.subworkflow import (
                contract_ports,
                parse_sub_workflow_config,
            )

            config = parse_sub_workflow_config(node.config)
            return node.model_copy(
                update={
                    "input_ports": contract_ports(
                        config.input_contract,
                        port_type="input",
                    ),
                    "output_ports": contract_ports(
                        config.output_contract,
                        port_type="output",
                    ),
                    "uses_llm": False,
                }
            )
        except Exception:
            # Preserve the static registry ports so validation can report the
            # typed config error instead of hiding the node entirely.
            pass

    # Create a new node with ports from registry
    # Use model_copy to preserve all existing fields
    return node.model_copy(
        update={
            "input_ports": list(tool_def.input_ports),
            "output_ports": list(tool_def.output_ports),
            "uses_llm": tool_def.uses_llm,  # Also sync uses_llm from registry
        }
    )


def create_node_from_tool(
    tool_name: str, position_x: float = 0, position_y: float = 0
) -> NodeDef | None:
    """Create a new node instance from a tool definition.

    Note: The returned node has ports populated for immediate use in the UI.
    When saving to database, use node.model_dump_for_storage() to exclude ports.
    """
    tool_def = TOOL_DEFS.get(tool_name)
    if not tool_def:
        return None

    # Create node with ports for immediate UI use
    # When saving, use model_dump_for_storage() to exclude ports
    return NodeDef(
        id=f"{tool_name}_{uuid.uuid4().hex[:8]}",
        tool=tool_name,
        input_ports=list(tool_def.input_ports),
        output_ports=list(tool_def.output_ports),
        config={},
        position_x=position_x,
        position_y=position_y,
        label=tool_def.display_name,
        description=tool_def.description,
        uses_llm=tool_def.uses_llm,
    )


# =============================================================================
# Import tool implementations
# =============================================================================


def _load_tool_implementations():
    """Load actual tool implementations.

    Importing the tools module triggers all @register_tool decorators,
    which override the basic built-in definitions with full config schemas.
    """
    try:
        # Import the entire tools module to trigger all @register_tool decorators
        # This ensures tools have their full config schemas (including prompt field)
        from fichero.workflows import tools  # noqa: F401
        from fichero.workflows.tools import zoom  # noqa: F401

        logger.debug("Loaded tool implementations")
    except ImportError as e:
        logger.debug(f"Tool implementations not loaded: {e}")


# Register all tools on module import
_register_builtin_tools(TOOL_DEFS)
_load_tool_implementations()
