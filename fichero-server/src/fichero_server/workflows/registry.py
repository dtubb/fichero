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
import threading
import uuid
from typing import Callable, Any

from fichero_server.workflows.types import (
    ToolDef,
    PortDef,
    NodeDef,
    DataType,
)
from fichero_server.workflows.registry_builtins import _register_builtin_tools

logger = logging.getLogger(__name__)

# Global tool registry.
#
# Private names + a module __getattr__ (below) so that reading `registry.TOOLS`
# triggers the tool load first. PEP 562's __getattr__ only fires for names NOT
# in module globals, so these MUST stay underscore-prefixed — re-adding a
# module-level `TOOLS = ...` would silently disable the whole mechanism and
# hand callers the incomplete built-in defs again.
_TOOLS: dict[str, Callable] = {}
_TOOL_DEFS: dict[str, ToolDef] = {}

# Tool implementations are imported on first read, not at module import (#3950).
_TOOLS_LOADED = False
# Guards the load against the lifespan warm-up thread racing a request thread.
_TOOLS_LOCK = threading.Lock()
# Ident of the thread currently importing, so IT alone may re-enter (see below).
_LOADING_THREAD_ID: int | None = None


def _ensure_tools_loaded() -> None:
    """Import tool implementations exactly once, on first read of the registry.

    WHY THIS EXISTS
    ---------------
    `_register_builtin_tools()` installs ~135 basic defs. The @register_tool
    decorators in tools/ then OVERRIDE them with full config schemas (including
    the prompt field). Between those two points the registry holds INCOMPLETE
    definitions, and a reader in that window silently gets wrong data — worse
    than slow. So every public read path calls this first, and the dicts are
    only reachable through it.

    WHY IT RAISES
    -------------
    The previous version caught ImportError and logged it at DEBUG. That is
    exactly how zoom and consistency_check vanished from the registry with no
    error (#3951), and it also meant `import fichero_server.workflows.registry`
    standalone left a permanently incomplete registry that looked healthy.
    A tool registry that cannot load its tools is broken; say so, loudly.

    THREAD SAFETY
    -------------
    The lifespan warms this on an executor THREAD while requests are already
    being served, so two threads can arrive here at once. The re-entrancy pass
    below is therefore keyed to the loading THREAD, not a bare bool: a plain
    `if _loading: return` would let a *request* thread skip the load and read
    the half-populated registry — resurrecting the 116-incomplete-defs bug as
    a race. Other threads block on the lock and get a complete registry.
    """
    global _TOOLS_LOADED, _LOADING_THREAD_ID
    if _TOOLS_LOADED:
        return
    if _LOADING_THREAD_ID == threading.get_ident():
        # Re-entrant on the SAME thread: tools/mcp.py imports TOOLS/TOOL_DEFS
        # from this module while the tools package is still executing. Hand the
        # dicts back as-is — they are the same objects the decorators are
        # populating, and blocking here would deadlock on ourselves.
        return
    with _TOOLS_LOCK:
        # Re-check: another thread may have finished while we waited.
        if _TOOLS_LOADED:
            return
        _LOADING_THREAD_ID = threading.get_ident()
        try:
            # This ONE import is the whole mechanism: every tool registers by
            # being imported in tools/__init__.py. Do NOT special-case
            # individual tools here (#3951) — zoom and consistency_check were
            # listed separately and so were registered ONLY by the eager call
            # this replaced. A tool not in tools/__init__.py does not exist.
            from fichero_server.workflows import tools  # noqa: F401

            _TOOLS_LOADED = True
            logger.debug("Loaded tool implementations")
        finally:
            _LOADING_THREAD_ID = None


def __getattr__(name: str):
    """Expose TOOLS / TOOL_DEFS, loading implementations first (PEP 562)."""
    if name == "TOOLS":
        _ensure_tools_loaded()
        return _TOOLS
    if name == "TOOL_DEFS":
        _ensure_tools_loaded()
        return _TOOL_DEFS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    requires_generative_model: bool = False,
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
        _TOOLS[name] = func

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
        _TOOL_DEFS[name] = ToolDef(
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
            requires_generative_model=requires_generative_model,
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
    _ensure_tools_loaded()
    # Check direct registration first
    if name in _TOOLS:
        return _TOOLS[name]
    # Check aliases
    if name in TOOL_ALIASES:
        return _TOOLS.get(TOOL_ALIASES[name])
    return None


def get_tool_def(name: str) -> ToolDef | None:
    """Get tool metadata by name."""
    _ensure_tools_loaded()
    return _TOOL_DEFS.get(name)


def list_tools() -> list[ToolDef]:
    """List all registered tools, sorted by sort_order then name."""
    _ensure_tools_loaded()
    tools = list(_TOOL_DEFS.values())
    return sorted(tools, key=lambda t: (t.sort_order, t.name))


def is_tool_executable(name: str) -> bool:
    """True when the tool (or its alias target) has a loaded implementation.

    Some built-in defs are palette placeholders with no implementation; a
    workflow containing one dies at graph build ("Unknown tool"). The palette
    endpoints filter on this so the editor only offers what can run (#4322).
    """
    _ensure_tools_loaded()
    if name in _TOOLS:
        return True
    alias = TOOL_ALIASES.get(name)
    return alias is not None and alias in _TOOLS


def list_executable_tools() -> list[ToolDef]:
    """Palette source: only tools that can actually execute (#4322)."""
    return [t for t in list_tools() if is_tool_executable(t.name)]


def list_executable_tools_by_category(category: str) -> list[ToolDef]:
    """Category palette source: only tools that can actually execute (#4322)."""
    return [t for t in list_tools_by_category(category) if is_tool_executable(t.name)]


def list_tools_by_category(category: str) -> list[ToolDef]:
    """List tools in a specific category, sorted by sort_order."""
    _ensure_tools_loaded()
    tools = [t for t in _TOOL_DEFS.values() if t.category == category]
    return sorted(tools, key=lambda t: (t.sort_order, t.name))


def get_categories() -> list[str]:
    """Get all unique tool categories."""
    _ensure_tools_loaded()
    categories = set(t.category for t in _TOOL_DEFS.values())
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
    _ensure_tools_loaded()
    tool_def = _TOOL_DEFS.get(node.tool)
    if not tool_def:
        # Tool not in registry - preserve existing ports for backward compatibility
        # This allows tests and inline workflow definitions to work
        if not node.input_ports and not node.output_ports:
            logger.warning(f"Tool not found in registry: {node.tool}")
        return node

    if node.tool == "sub_workflow":
        try:
            from fichero_server.workflows.subworkflow import (
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
    _ensure_tools_loaded()
    tool_def = _TOOL_DEFS.get(tool_name)
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


# Register the built-in tool defs at import (cheap: plain data, no deps).
# Implementations load on first read — see _ensure_tools_loaded() above (#3950).
_register_builtin_tools(_TOOL_DEFS)
