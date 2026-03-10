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
        default_input = [PortDef(id="input", name="Input", port_type="input", data_type=DataType.ANY)]
        default_output = [PortDef(id="output", name="Output", port_type="output", data_type=DataType.ANY)]

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
    order = ["source", "vision", "audio", "video", "transform", "llm", "convert", "logic", "sink", "utility"]
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

    # Create a new node with ports from registry
    # Use model_copy to preserve all existing fields
    return node.model_copy(update={
        'input_ports': list(tool_def.input_ports),
        'output_ports': list(tool_def.output_ports),
        'uses_llm': tool_def.uses_llm,  # Also sync uses_llm from registry
    })


def create_node_from_tool(tool_name: str, position_x: float = 0, position_y: float = 0) -> NodeDef | None:
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
# Built-in Tool Definitions (registered without implementations for now)
# =============================================================================

def _register_builtin_tools():
    """Register all built-in tool definitions.

    These are the tools available in the node editor.
    Actual implementations will be loaded separately.
    """

    # =========================================================================
    # Source Nodes
    # =========================================================================

    TOOL_DEFS["files"] = ToolDef(
        name="files",
        display_name="Files",
        description="Input files from drag/drop or folder",
        category="source",
        icon="doc.on.doc",
        color="green",
        input_ports=[],  # No inputs - this is a source
        output_ports=[
            PortDef(id="files", name="Files", port_type="output", data_type=DataType.FILES),
        ],
        sort_order=1,
    )

    TOOL_DEFS["collection"] = ToolDef(
        name="collection",
        display_name="Collection",
        description="Files from a library collection",
        category="source",
        icon="folder",
        color="green",
        input_ports=[],
        output_ports=[
            PortDef(id="files", name="Files", port_type="output", data_type=DataType.FILES),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "collection_id": {"type": "string", "description": "Collection to pull from"},
            },
        },
        sort_order=2,
    )

    TOOL_DEFS["search"] = ToolDef(
        name="search",
        display_name="Search",
        description="Files matching a search query",
        category="source",
        icon="magnifyingglass",
        color="green",
        input_ports=[],
        output_ports=[
            PortDef(id="files", name="Files", port_type="output", data_type=DataType.FILES),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 100},
            },
        },
        sort_order=3,
    )

    # =========================================================================
    # Vision Nodes
    # =========================================================================

    TOOL_DEFS["transcribe"] = ToolDef(
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
            PortDef(id="structured", name="Structured", port_type="output", data_type=DataType.JSON),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "language": {"type": "string", "default": "en"},
                "preserve_layout": {"type": "boolean", "default": False},
            },
        },
        uses_llm=True,
        supports_batch=True,
        supports_structured_output=True,
        sort_order=10,
    )

    TOOL_DEFS["describe"] = ToolDef(
        name="describe",
        display_name="Describe",
        description="Generate descriptions of images",
        category="vision",
        icon="eye",
        color="blue",
        input_ports=[
            PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES),
        ],
        output_ports=[
            PortDef(id="descriptions", name="Descriptions", port_type="output", data_type=DataType.JSON),
        ],
        uses_llm=True,
        supports_batch=True,
        sort_order=11,
    )

    TOOL_DEFS["analyze"] = ToolDef(
        name="analyze",
        display_name="Analyze",
        description="Analyze document structure and content",
        category="vision",
        icon="doc.text.magnifyingglass",
        color="blue",
        input_ports=[
            PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES),
        ],
        output_ports=[
            PortDef(id="analysis", name="Analysis", port_type="output", data_type=DataType.JSON),
        ],
        uses_llm=True,
        supports_structured_output=True,
        sort_order=12,
    )

    # =========================================================================
    # Transform Nodes
    # =========================================================================

    TOOL_DEFS["enhance"] = ToolDef(
        name="enhance",
        display_name="Enhance",
        description="Improve image quality (contrast, sharpness, etc.)",
        category="transform",
        icon="wand.and.stars",
        color="pink",
        input_ports=[
            PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES),
        ],
        output_ports=[
            PortDef(id="files", name="Files", port_type="output", data_type=DataType.FILES),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "contrast": {"type": "number", "default": 1.2},
                "sharpness": {"type": "number", "default": 1.5},
                "denoise": {"type": "boolean", "default": True},
            },
        },
        supports_batch=True,
        sort_order=20,
    )

    TOOL_DEFS["crop"] = ToolDef(
        name="crop",
        display_name="Crop",
        description="Crop images to a region",
        category="transform",
        icon="crop",
        color="pink",
        input_ports=[
            PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES),
        ],
        output_ports=[
            PortDef(id="files", name="Files", port_type="output", data_type=DataType.FILES),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "auto_detect": {"type": "boolean", "default": True, "description": "Auto-detect content bounds"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
        },
        supports_batch=True,
        sort_order=21,
    )

    TOOL_DEFS["rotate"] = ToolDef(
        name="rotate",
        display_name="Rotate",
        description="Rotate images",
        category="transform",
        icon="rotate.right",
        color="pink",
        input_ports=[
            PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES),
        ],
        output_ports=[
            PortDef(id="files", name="Files", port_type="output", data_type=DataType.FILES),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "degrees": {"type": "integer", "enum": [90, 180, 270], "default": 90},
                "auto_deskew": {"type": "boolean", "default": False},
            },
        },
        supports_batch=True,
        sort_order=22,
    )

    TOOL_DEFS["segment"] = ToolDef(
        name="segment",
        display_name="Segment",
        description="Split document into segments (pages, sections)",
        category="transform",
        icon="rectangle.split.3x1",
        color="pink",
        input_ports=[
            PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES),
        ],
        output_ports=[
            PortDef(id="segments", name="Segments", port_type="output", data_type=DataType.FILES),
        ],
        uses_llm=True,
        supports_batch=True,
        sort_order=23,
    )

    # =========================================================================
    # LLM Nodes
    # =========================================================================

    TOOL_DEFS["summarize"] = ToolDef(
        name="summarize",
        display_name="Summarize",
        description="Generate text summaries",
        category="llm",
        icon="text.quote",
        color="purple",
        input_ports=[
            PortDef(id="text", name="Text", port_type="input", data_type=DataType.TEXT),
        ],
        output_ports=[
            PortDef(id="summary", name="Summary", port_type="output", data_type=DataType.TEXT),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "max_length": {"type": "integer", "default": 200},
                "style": {"type": "string", "enum": ["brief", "detailed", "bullets"], "default": "brief"},
            },
        },
        uses_llm=True,
        sort_order=30,
    )

    TOOL_DEFS["translate"] = ToolDef(
        name="translate",
        display_name="Translate",
        description="Translate text to another language",
        category="llm",
        icon="globe",
        color="purple",
        input_ports=[
            PortDef(id="text", name="Text", port_type="input", data_type=DataType.TEXT),
        ],
        output_ports=[
            PortDef(id="translated", name="Translated", port_type="output", data_type=DataType.TEXT),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "target_language": {"type": "string", "default": "en"},
                "preserve_formatting": {"type": "boolean", "default": True},
            },
        },
        uses_llm=True,
        sort_order=31,
    )

    TOOL_DEFS["extract_entities"] = ToolDef(
        name="extract_entities",
        display_name="Extract Entities",
        description="Extract named entities (people, places, dates, etc.)",
        category="llm",
        icon="person.text.rectangle",
        color="purple",
        input_ports=[
            PortDef(id="text", name="Text", port_type="input", data_type=DataType.TEXT),
        ],
        output_ports=[
            PortDef(id="entities", name="Entities", port_type="output", data_type=DataType.JSON),
        ],
        default_output_schema={
            "type": "object",
            "properties": {
                "people": {"type": "array", "items": {"type": "string"}},
                "organizations": {"type": "array", "items": {"type": "string"}},
                "locations": {"type": "array", "items": {"type": "string"}},
                "dates": {"type": "array", "items": {"type": "string"}},
            },
        },
        uses_llm=True,
        supports_structured_output=True,
        sort_order=32,
    )

    TOOL_DEFS["classify"] = ToolDef(
        name="classify",
        display_name="Classify",
        description="Classify documents into categories",
        category="llm",
        icon="tag",
        color="purple",
        input_ports=[
            PortDef(id="text", name="Text", port_type="input", data_type=DataType.TEXT),
        ],
        output_ports=[
            PortDef(id="category", name="Category", port_type="output", data_type=DataType.TEXT),
            PortDef(id="confidence", name="Confidence", port_type="output", data_type=DataType.NUMBER),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of possible categories",
                },
            },
        },
        uses_llm=True,
        supports_structured_output=True,
        sort_order=33,
    )

    TOOL_DEFS["custom_llm"] = ToolDef(
        name="custom_llm",
        display_name="Custom LLM",
        description="Custom LLM prompt with configurable output schema",
        category="llm",
        icon="text.bubble",
        color="purple",
        input_ports=[
            PortDef(id="input", name="Input", port_type="input", data_type=DataType.ANY),
        ],
        output_ports=[
            PortDef(id="output", name="Output", port_type="output", data_type=DataType.ANY),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The prompt template"},
                "output_schema": {"type": "object", "description": "JSON Schema for output"},
            },
        },
        uses_llm=True,
        supports_structured_output=True,
        sort_order=34,
    )

    # =========================================================================
    # Logic Nodes
    # =========================================================================

    TOOL_DEFS["if"] = ToolDef(
        name="if",
        display_name="IF",
        description="Conditional branching based on expression",
        category="logic",
        icon="arrow.triangle.branch",
        color="yellow",
        input_ports=[
            PortDef(id="input", name="Input", port_type="input", data_type=DataType.ANY),
        ],
        output_ports=[
            PortDef(id="true", name="True", port_type="output", data_type=DataType.ANY),
            PortDef(id="false", name="False", port_type="output", data_type=DataType.ANY),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "condition": {
                    "type": "string",
                    "description": "Condition expression (e.g., $.nodes.classify.category == 'invoice')",
                },
            },
            "required": ["condition"],
        },
        sort_order=40,
    )

    TOOL_DEFS["switch"] = ToolDef(
        name="switch",
        display_name="Switch",
        description="Multi-way branching based on value",
        category="logic",
        icon="arrow.triangle.swap",
        color="yellow",
        input_ports=[
            PortDef(id="input", name="Input", port_type="input", data_type=DataType.ANY),
            PortDef(id="value", name="Value", port_type="input", data_type=DataType.ANY),
        ],
        output_ports=[
            PortDef(id="case_1", name="Case 1", port_type="output", data_type=DataType.ANY),
            PortDef(id="case_2", name="Case 2", port_type="output", data_type=DataType.ANY),
            PortDef(id="case_3", name="Case 3", port_type="output", data_type=DataType.ANY),
            PortDef(id="default", name="Default", port_type="output", data_type=DataType.ANY),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "cases": {
                    "type": "object",
                    "description": "Map of value to output port ID",
                    "additionalProperties": {"type": "string"},
                },
            },
        },
        sort_order=41,
    )

    TOOL_DEFS["loop"] = ToolDef(
        name="loop",
        display_name="Loop",
        description="Iterate over items in a collection",
        category="logic",
        icon="repeat",
        color="yellow",
        input_ports=[
            PortDef(id="items", name="Items", port_type="input", data_type=DataType.ARRAY),
        ],
        output_ports=[
            PortDef(id="item", name="Item", port_type="output", data_type=DataType.ANY),
            PortDef(id="done", name="Done", port_type="output", data_type=DataType.ARRAY),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "parallel": {"type": "integer", "default": 1, "description": "Max parallel iterations"},
            },
        },
        sort_order=42,
    )

    TOOL_DEFS["filter"] = ToolDef(
        name="filter",
        display_name="Filter",
        description="Filter items based on condition",
        category="logic",
        icon="line.3.horizontal.decrease.circle",
        color="yellow",
        input_ports=[
            PortDef(id="items", name="Items", port_type="input", data_type=DataType.ARRAY),
        ],
        output_ports=[
            PortDef(id="passed", name="Passed", port_type="output", data_type=DataType.ARRAY),
            PortDef(id="failed", name="Failed", port_type="output", data_type=DataType.ARRAY),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "condition": {"type": "string", "description": "Filter condition per item"},
            },
        },
        sort_order=43,
    )

    TOOL_DEFS["merge"] = ToolDef(
        name="merge",
        display_name="Merge",
        description="Merge multiple branches into one",
        category="logic",
        icon="arrow.triangle.merge",
        color="yellow",
        input_ports=[
            PortDef(id="input_1", name="Input 1", port_type="input", data_type=DataType.ANY, required=False),
            PortDef(id="input_2", name="Input 2", port_type="input", data_type=DataType.ANY, required=False),
            PortDef(id="input_3", name="Input 3", port_type="input", data_type=DataType.ANY, required=False),
        ],
        output_ports=[
            PortDef(id="merged", name="Merged", port_type="output", data_type=DataType.ANY),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "strategy": {
                    "type": "string",
                    "enum": ["first", "all", "concat"],
                    "default": "first",
                    "description": "How to merge: first available, wait for all, or concatenate",
                },
            },
        },
        sort_order=44,
    )

    # =========================================================================
    # Convert Nodes
    # =========================================================================

    TOOL_DEFS["to_pdf"] = ToolDef(
        name="to_pdf",
        display_name="To PDF",
        description="Export as PDF document",
        category="convert",
        icon="doc.richtext",
        color="orange",
        input_ports=[
            PortDef(id="content", name="Content", port_type="input", data_type=DataType.ANY),
        ],
        output_ports=[
            PortDef(id="file", name="File", port_type="output", data_type=DataType.FILE),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "include_images": {"type": "boolean", "default": True},
                "page_size": {"type": "string", "enum": ["letter", "a4"], "default": "letter"},
            },
        },
        sort_order=50,
    )

    TOOL_DEFS["to_word"] = ToolDef(
        name="to_word",
        display_name="To Word",
        description="Export as Word document",
        category="convert",
        icon="doc.text",
        color="orange",
        input_ports=[
            PortDef(id="content", name="Content", port_type="input", data_type=DataType.ANY),
        ],
        output_ports=[
            PortDef(id="file", name="File", port_type="output", data_type=DataType.FILE),
        ],
        sort_order=51,
    )

    TOOL_DEFS["to_excel"] = ToolDef(
        name="to_excel",
        display_name="To Excel",
        description="Export as Excel spreadsheet",
        category="convert",
        icon="tablecells",
        color="orange",
        input_ports=[
            PortDef(id="data", name="Data", port_type="input", data_type=DataType.JSON),
        ],
        output_ports=[
            PortDef(id="file", name="File", port_type="output", data_type=DataType.FILE),
        ],
        sort_order=52,
    )

    TOOL_DEFS["to_json"] = ToolDef(
        name="to_json",
        display_name="To JSON",
        description="Export as JSON file",
        category="convert",
        icon="curlybraces",
        color="orange",
        input_ports=[
            PortDef(id="data", name="Data", port_type="input", data_type=DataType.ANY),
        ],
        output_ports=[
            PortDef(id="file", name="File", port_type="output", data_type=DataType.FILE),
        ],
        sort_order=53,
    )

    # =========================================================================
    # Sink Nodes
    # =========================================================================

    TOOL_DEFS["save_to_library"] = ToolDef(
        name="save_to_library",
        display_name="Save to Library",
        description="Save output to library collection",
        category="sink",
        icon="square.and.arrow.down",
        color="red",
        input_ports=[
            PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES),
        ],
        output_ports=[],  # No outputs - this is a sink
        config_schema={
            "type": "object",
            "properties": {
                "collection_id": {"type": "string", "description": "Target collection"},
            },
        },
        sort_order=60,
    )

    TOOL_DEFS["export"] = ToolDef(
        name="export",
        display_name="Export",
        description="Export files to a folder",
        category="sink",
        icon="folder.badge.plus",
        color="red",
        input_ports=[
            PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES),
        ],
        output_ports=[],
        config_schema={
            "type": "object",
            "properties": {
                "folder": {"type": "string", "description": "Export folder path"},
                "naming": {"type": "string", "enum": ["original", "sequential", "timestamp"], "default": "original"},
            },
        },
        sort_order=61,
    )

    logger.debug(f"Registered {len(TOOL_DEFS)} built-in tools")


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
        logger.debug("Loaded tool implementations")
    except ImportError as e:
        logger.debug(f"Tool implementations not loaded: {e}")


# Register all tools on module import
_register_builtin_tools()
_load_tool_implementations()
