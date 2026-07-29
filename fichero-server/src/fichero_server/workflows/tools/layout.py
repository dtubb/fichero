"""
Layout Tool

Analyzes document structure and layout (headers, paragraphs, tables, columns).
Inherits from vision_base.py - uses output_format="json" for structured layout data.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero_server.workflows.types import State
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.llm_base import BASE_OUTPUT_PORTS, merge_config_schema
from fichero_server.workflows.tools.vision_base import (
    VISION_INPUT_PORTS,
    VISION_CONFIG_SCHEMA,
    VisionToolConfig,
    process_vision,
)
from fichero_server.llm import LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = VisionToolConfig(
    artifact_type="layout",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="layout",
)

LAYOUT_CONFIG = {
    "elements": {
        "type": "array",
        "items": {"type": "string"},
        "default": ["headers", "paragraphs", "tables", "images", "lists"],
        "description": "Elements to detect",
    },
    "include_hierarchy": {
        "type": "boolean",
        "default": True,
        "description": "Include nesting structure",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(elements: list[str], include_hierarchy: bool) -> str:
    """Build the layout analysis prompt."""
    elements_str = ", ".join(elements)

    hierarchy_text = ""
    if include_hierarchy:
        hierarchy_text = """
    "hierarchy": [
        {"level": 1, "type": "<element type>", "content": "<summary>", "children": [...]},
        ...
    ],"""

    return f"""Analyze the layout and structure of this document/image.

Detect these elements: {elements_str}

Return as JSON:
{{
    "page_type": "<document/form/article/presentation/other>",
    "columns": <number of columns>,
    "elements": [
        {{"type": "<{"|".join(elements)}>", "content": "<brief content summary>", "position": "<top/middle/bottom>"}},
        ...
    ],{hierarchy_text}
    "reading_order": "<left-to-right/top-to-bottom/columns/complex>"
}}

Return ONLY valid JSON."""


def build_layout_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    elements = config.get(
        "elements", ["headers", "paragraphs", "tables", "images", "lists"]
    )
    include_hierarchy = config.get("include_hierarchy", True)
    return _build_prompt(elements, include_hierarchy)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="layout",
    display_name="Layout",
    description="Analyze document structure",
    category="vision",
    icon="rectangle.split.3x3",
    color="indigo",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, LAYOUT_CONFIG),
    default_prompt=_build_prompt(
        ["headers", "paragraphs", "tables", "images", "lists"], True
    ),
    prompt_builder=build_layout_prompt,
    sort_order=18,
)
async def layout(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Analyze document layout and structure."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get layout-specific config
    elements = inputs.get(
        "elements", ["headers", "paragraphs", "tables", "images", "lists"]
    )
    include_hierarchy = inputs.get("include_hierarchy", True)

    # Build prompt
    prompt = inputs.get("prompt") or _build_prompt(elements, include_hierarchy)

    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        # Vision-specific
        vision_mode="llm",
        max_image_dimension=inputs.get("max_image_dimension", 2048),
        # JSON output for structured layout data
        temperature=inputs.get("temperature", 0.2),  # Low temp for structure
        max_tokens=inputs.get("max_tokens", 4096),  # Layout can be verbose
        output_format=inputs.get("output_format", "json"),
        output_options={},
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "layout",
    )
