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

from fichero.workflows.types import (
    State,
    NodeDef,
    EdgeDef,
    WorkflowDef,
    ToolDef,
)
from fichero.workflows.registry import TOOLS, register_tool, list_tools, get_tool_def
from fichero.workflows.builder import build_graph, execute_workflow
from fichero.workflows.resolver import resolve_inputs, resolve_value, evaluate_condition

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
    # Builder
    "build_graph",
    "execute_workflow",
    # Resolver
    "resolve_inputs",
    "resolve_value",
    "evaluate_condition",
]
