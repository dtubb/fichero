"""
Built-in tool definitions for the workflow registry.

Called by registry.py once on startup: _register_builtin_tools(TOOL_DEFS).
"""

from __future__ import annotations

import logging

from fichero.workflows.types import DataType, PortDef, ToolDef

logger = logging.getLogger(__name__)


def _register_builtin_tools(tool_defs: dict) -> None:
    """Register all built-in tool definitions into *tool_defs*.

    These are the tools available in the node editor.
    Actual implementations are loaded separately by _load_tool_implementations().
    """

    # =========================================================================
    # Source Nodes
    # =========================================================================

    tool_defs["files"] = ToolDef(
        name="files",
        display_name="Files",
        description="Input files from drag/drop or folder",
        category="source",
        icon="doc.on.doc",
        color="green",
        input_ports=[],  # No inputs - this is a source
        output_ports=[
            PortDef(
                id="files", name="Files", port_type="output", data_type=DataType.FILES
            ),
        ],
        sort_order=1,
    )

    tool_defs["collection"] = ToolDef(
        name="collection",
        display_name="Collection",
        description="Files from a library collection",
        category="source",
        icon="folder",
        color="green",
        input_ports=[],
        output_ports=[
            PortDef(
                id="files", name="Files", port_type="output", data_type=DataType.FILES
            ),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "collection_id": {
                    "type": "string",
                    "description": "Collection to pull from",
                },
            },
        },
        sort_order=2,
    )

    tool_defs["search"] = ToolDef(
        name="search",
        display_name="Search",
        description="Files matching a search query",
        category="source",
        icon="magnifyingglass",
        color="green",
        input_ports=[],
        output_ports=[
            PortDef(
                id="files", name="Files", port_type="output", data_type=DataType.FILES
            ),
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

    tool_defs["transcribe"] = ToolDef(
        name="transcribe",
        display_name="Transcribe",
        description="Extract text from images using vision LLM",
        category="vision",
        icon="text.viewfinder",
        color="blue",
        input_ports=[
            PortDef(
                id="files", name="Files", port_type="input", data_type=DataType.FILES
            ),
        ],
        output_ports=[
            PortDef(
                id="text", name="Text", port_type="output", data_type=DataType.TEXT
            ),
            PortDef(
                id="structured",
                name="Structured",
                port_type="output",
                data_type=DataType.JSON,
            ),
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

    tool_defs["describe"] = ToolDef(
        name="describe",
        display_name="Describe",
        description="Generate descriptions of images",
        category="vision",
        icon="eye",
        color="blue",
        input_ports=[
            PortDef(
                id="files", name="Files", port_type="input", data_type=DataType.FILES
            ),
        ],
        output_ports=[
            PortDef(
                id="descriptions",
                name="Descriptions",
                port_type="output",
                data_type=DataType.JSON,
            ),
        ],
        uses_llm=True,
        supports_batch=True,
        sort_order=11,
    )

    tool_defs["analyze"] = ToolDef(
        name="analyze",
        display_name="Analyze",
        description="Analyze document structure and content",
        category="vision",
        icon="doc.text.magnifyingglass",
        color="blue",
        input_ports=[
            PortDef(
                id="files", name="Files", port_type="input", data_type=DataType.FILES
            ),
        ],
        output_ports=[
            PortDef(
                id="analysis",
                name="Analysis",
                port_type="output",
                data_type=DataType.JSON,
            ),
        ],
        uses_llm=True,
        supports_structured_output=True,
        sort_order=12,
    )

    # =========================================================================
    # Transform Nodes
    # =========================================================================

    tool_defs["enhance"] = ToolDef(
        name="enhance",
        display_name="Enhance",
        description="Improve image quality (contrast, sharpness, etc.)",
        category="transform",
        icon="wand.and.stars",
        color="pink",
        input_ports=[
            PortDef(
                id="files", name="Files", port_type="input", data_type=DataType.FILES
            ),
        ],
        output_ports=[
            PortDef(
                id="files", name="Files", port_type="output", data_type=DataType.FILES
            ),
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

    tool_defs["crop"] = ToolDef(
        name="crop",
        display_name="Crop",
        description="Crop images to a region",
        category="transform",
        icon="crop",
        color="pink",
        input_ports=[
            PortDef(
                id="files", name="Files", port_type="input", data_type=DataType.FILES
            ),
        ],
        output_ports=[
            PortDef(
                id="files", name="Files", port_type="output", data_type=DataType.FILES
            ),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "auto_detect": {
                    "type": "boolean",
                    "default": True,
                    "description": "Auto-detect content bounds",
                },
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
        },
        supports_batch=True,
        sort_order=21,
    )

    tool_defs["zoom"] = ToolDef(
        name="zoom",
        display_name="Zoom",
        description="Crop and magnify image regions or line strips",
        category="transform",
        icon="plus.magnifyingglass",
        color="pink",
        input_ports=[PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES)],
        output_ports=[PortDef(id="files", name="Files", port_type="output", data_type=DataType.FILES)],
        config_schema={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["region", "tile"], "default": "tile"},
                "x": {"type": "integer"}, "y": {"type": "integer"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
                "rows": {"type": "integer", "default": 0, "minimum": 0},
                "overlap": {"type": "number", "default": 0.15, "minimum": 0.0, "maximum": 0.3},
                "scale": {"type": "number", "default": 2.0, "minimum": 1.0, "maximum": 6.0},
                "output_format": {"type": "string", "enum": ["jpg", "png", "tiff", "webp"], "default": "jpg"},
                "compression_quality": {"type": "integer", "default": 90, "minimum": 1, "maximum": 100},
                "output_dir": {"type": "string", "default": ""},
            },
        },
        supports_batch=True,
        sort_order=27,
    )

    tool_defs["rotate"] = ToolDef(
        name="rotate",
        display_name="Rotate",
        description="Rotate images",
        category="transform",
        icon="rotate.right",
        color="pink",
        input_ports=[
            PortDef(
                id="files", name="Files", port_type="input", data_type=DataType.FILES
            ),
        ],
        output_ports=[
            PortDef(
                id="files", name="Files", port_type="output", data_type=DataType.FILES
            ),
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

    tool_defs["segment"] = ToolDef(
        name="segment",
        display_name="Segment",
        description="Split document into segments (pages, sections)",
        category="transform",
        icon="rectangle.split.3x1",
        color="pink",
        input_ports=[
            PortDef(
                id="files", name="Files", port_type="input", data_type=DataType.FILES
            ),
        ],
        output_ports=[
            PortDef(
                id="segments",
                name="Segments",
                port_type="output",
                data_type=DataType.FILES,
            ),
        ],
        uses_llm=True,
        supports_batch=True,
        sort_order=23,
    )

    # =========================================================================
    # LLM Nodes
    # =========================================================================

    tool_defs["summarize"] = ToolDef(
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
            PortDef(
                id="summary",
                name="Summary",
                port_type="output",
                data_type=DataType.TEXT,
            ),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "max_length": {"type": "integer", "default": 200},
                "style": {
                    "type": "string",
                    "enum": ["brief", "detailed", "bullets"],
                    "default": "brief",
                },
            },
        },
        uses_llm=True,
        sort_order=30,
    )

    tool_defs["translate"] = ToolDef(
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
            PortDef(
                id="translated",
                name="Translated",
                port_type="output",
                data_type=DataType.TEXT,
            ),
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

    tool_defs["extract_entities"] = ToolDef(
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
            PortDef(
                id="entities",
                name="Entities",
                port_type="output",
                data_type=DataType.JSON,
            ),
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

    tool_defs["classify"] = ToolDef(
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
            PortDef(
                id="category",
                name="Category",
                port_type="output",
                data_type=DataType.TEXT,
            ),
            PortDef(
                id="confidence",
                name="Confidence",
                port_type="output",
                data_type=DataType.NUMBER,
            ),
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

    tool_defs["custom_llm"] = ToolDef(
        name="custom_llm",
        display_name="Custom LLM",
        description="Custom LLM prompt with configurable output schema",
        category="llm",
        icon="text.bubble",
        color="purple",
        input_ports=[
            PortDef(
                id="input", name="Input", port_type="input", data_type=DataType.ANY
            ),
        ],
        output_ports=[
            PortDef(
                id="output", name="Output", port_type="output", data_type=DataType.ANY
            ),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The prompt template"},
                "output_schema": {
                    "type": "object",
                    "description": "JSON Schema for output",
                },
            },
        },
        uses_llm=True,
        supports_structured_output=True,
        sort_order=34,
    )

    # =========================================================================
    # Logic Nodes
    # =========================================================================

    tool_defs["if"] = ToolDef(
        name="if",
        display_name="IF",
        description="Conditional branching based on expression",
        category="logic",
        icon="arrow.triangle.branch",
        color="yellow",
        input_ports=[
            PortDef(
                id="input", name="Input", port_type="input", data_type=DataType.ANY
            ),
        ],
        output_ports=[
            PortDef(id="true", name="True", port_type="output", data_type=DataType.ANY),
            PortDef(
                id="false", name="False", port_type="output", data_type=DataType.ANY
            ),
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

    tool_defs["switch"] = ToolDef(
        name="switch",
        display_name="Switch",
        description="Multi-way branching based on value",
        category="logic",
        icon="arrow.triangle.swap",
        color="yellow",
        input_ports=[
            PortDef(
                id="input", name="Input", port_type="input", data_type=DataType.ANY
            ),
            PortDef(
                id="value", name="Value", port_type="input", data_type=DataType.ANY
            ),
        ],
        output_ports=[
            PortDef(
                id="case_1", name="Case 1", port_type="output", data_type=DataType.ANY
            ),
            PortDef(
                id="case_2", name="Case 2", port_type="output", data_type=DataType.ANY
            ),
            PortDef(
                id="case_3", name="Case 3", port_type="output", data_type=DataType.ANY
            ),
            PortDef(
                id="default", name="Default", port_type="output", data_type=DataType.ANY
            ),
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

    tool_defs["loop"] = ToolDef(
        name="loop",
        display_name="Loop",
        description="Iterate over items in a collection",
        category="logic",
        icon="repeat",
        color="yellow",
        input_ports=[
            PortDef(
                id="items", name="Items", port_type="input", data_type=DataType.ARRAY
            ),
        ],
        output_ports=[
            PortDef(id="item", name="Item", port_type="output", data_type=DataType.ANY),
            PortDef(
                id="done", name="Done", port_type="output", data_type=DataType.ARRAY
            ),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "parallel": {
                    "type": "integer",
                    "default": 1,
                    "description": "Max parallel iterations",
                },
            },
        },
        sort_order=42,
    )

    tool_defs["filter"] = ToolDef(
        name="filter",
        display_name="Filter",
        description="Filter items based on condition",
        category="logic",
        icon="line.3.horizontal.decrease.circle",
        color="yellow",
        input_ports=[
            PortDef(
                id="items", name="Items", port_type="input", data_type=DataType.ARRAY
            ),
        ],
        output_ports=[
            PortDef(
                id="passed", name="Passed", port_type="output", data_type=DataType.ARRAY
            ),
            PortDef(
                id="failed", name="Failed", port_type="output", data_type=DataType.ARRAY
            ),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "condition": {
                    "type": "string",
                    "description": "Filter condition per item",
                },
            },
        },
        sort_order=43,
    )

    tool_defs["merge"] = ToolDef(
        name="merge",
        display_name="Merge",
        description="Merge multiple branches into one",
        category="logic",
        icon="arrow.triangle.merge",
        color="yellow",
        input_ports=[
            PortDef(
                id="input_1",
                name="Input 1",
                port_type="input",
                data_type=DataType.ANY,
                required=False,
            ),
            PortDef(
                id="input_2",
                name="Input 2",
                port_type="input",
                data_type=DataType.ANY,
                required=False,
            ),
            PortDef(
                id="input_3",
                name="Input 3",
                port_type="input",
                data_type=DataType.ANY,
                required=False,
            ),
        ],
        output_ports=[
            PortDef(
                id="merged", name="Merged", port_type="output", data_type=DataType.ANY
            ),
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

    tool_defs["to_pdf"] = ToolDef(
        name="to_pdf",
        display_name="To PDF",
        description="Export as PDF document",
        category="convert",
        icon="doc.richtext",
        color="orange",
        input_ports=[
            PortDef(
                id="content", name="Content", port_type="input", data_type=DataType.ANY
            ),
        ],
        output_ports=[
            PortDef(
                id="file", name="File", port_type="output", data_type=DataType.FILE
            ),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "include_images": {"type": "boolean", "default": True},
                "page_size": {
                    "type": "string",
                    "enum": ["letter", "a4"],
                    "default": "letter",
                },
            },
        },
        sort_order=50,
    )

    tool_defs["to_word"] = ToolDef(
        name="to_word",
        display_name="To Word",
        description="Export as Word document",
        category="convert",
        icon="doc.text",
        color="orange",
        input_ports=[
            PortDef(
                id="content", name="Content", port_type="input", data_type=DataType.ANY
            ),
        ],
        output_ports=[
            PortDef(
                id="file", name="File", port_type="output", data_type=DataType.FILE
            ),
        ],
        sort_order=51,
    )

    tool_defs["to_excel"] = ToolDef(
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
            PortDef(
                id="file", name="File", port_type="output", data_type=DataType.FILE
            ),
        ],
        sort_order=52,
    )

    tool_defs["to_json"] = ToolDef(
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
            PortDef(
                id="file", name="File", port_type="output", data_type=DataType.FILE
            ),
        ],
        sort_order=53,
    )

    # =========================================================================
    # Sink Nodes
    # =========================================================================

    tool_defs["save_to_library"] = ToolDef(
        name="save_to_library",
        display_name="Save to Library",
        description="Save output to library collection",
        category="sink",
        icon="square.and.arrow.down",
        color="red",
        input_ports=[
            PortDef(
                id="files", name="Files", port_type="input", data_type=DataType.FILES
            ),
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

    tool_defs["export"] = ToolDef(
        name="export",
        display_name="Export",
        description="Export files to a folder",
        category="sink",
        icon="folder.badge.plus",
        color="red",
        input_ports=[
            PortDef(
                id="files", name="Files", port_type="input", data_type=DataType.FILES
            ),
        ],
        output_ports=[],
        config_schema={
            "type": "object",
            "properties": {
                "folder": {"type": "string", "description": "Export folder path"},
                "naming": {
                    "type": "string",
                    "enum": ["original", "sequential", "timestamp"],
                    "default": "original",
                },
            },
        },
        sort_order=61,
    )

    logger.debug(f"Registered {len(tool_defs)} built-in tools")
