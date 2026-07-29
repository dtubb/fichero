"""
Fichero Workflows Package

LangGraph-based workflow execution for document processing.
Workflows are defined as JSON and executed as directed graphs.

Key components:
- types: State, NodeDef, EdgeDef, WorkflowDef
- builder: Build LangGraph from JSON definition
- registry: Tool registry for workflow nodes
- resolver: Input path resolution ($.nodes.x.y, transforms, etc.)
- tools/: Individual tool implementations

Path Syntax:
    $.nodes.{id}.{key}       - Output from another node
    $.inputs.{key}           - Initial workflow input
    $.files                  - All input files
    $.files[n]               - Specific file
    $.config.{key}           - Workflow config
    $.nodes.x.items[*].text  - Extract from all items
    $.nodes.x.texts | join("\\n") - Transform with pipe
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from fichero_server.workflows.types import State, NodeDef, EdgeDef, WorkflowDef, ToolDef
    from fichero_server.workflows.registry import (
        TOOLS,
        register_tool,
        list_tools,
        get_tool_def,
        enrich_node_with_ports,
    )
    from fichero_server.workflows.builder import build_graph, execute_workflow
    from fichero_server.workflows.resolver import resolve_inputs, resolve_value, evaluate_condition

# Which submodule owns each re-exported name. Resolved on first access (#3950).
#
# These re-exports used to be eager, which meant that touching ANY member of
# this package — even `fichero_server.workflows.types.State`, a plain dataclass — ran
# builder.py, and so imported langgraph. routes/chains.py paid the entire AI
# stack to obtain a type. Nothing outside this package imports the re-exported
# names (every real caller uses a submodule import), so making them lazy is
# invisible to callers and removes the package from the hot import path.
_LAZY_EXPORTS: dict[str, str] = {
    "State": "types",
    "NodeDef": "types",
    "EdgeDef": "types",
    "WorkflowDef": "types",
    "ToolDef": "types",
    "TOOLS": "registry",
    "register_tool": "registry",
    "list_tools": "registry",
    "get_tool_def": "registry",
    "enrich_node_with_ports": "registry",
    "build_graph": "builder",
    "execute_workflow": "builder",
    "resolve_inputs": "resolver",
    "resolve_value": "resolver",
    "evaluate_condition": "resolver",
}


def __getattr__(name: str) -> Any:
    """Resolve a re-export from its owning submodule on first access (PEP 562)."""
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(f"fichero_server.workflows.{module_name}")
    value = getattr(module, name)
    globals()[name] = value  # cache: __getattr__ won't fire for this name again
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    # Types
    "State",
    "NodeDef",
    "EdgeDef",
    "WorkflowDef",
    "ToolDef",
    # Registry
    "TOOLS",
    "register_tool",
    "list_tools",
    "get_tool_def",
    "enrich_node_with_ports",
    # Builder
    "build_graph",
    "execute_workflow",
    # Resolver
    "resolve_inputs",
    "resolve_value",
    "evaluate_condition",
]
