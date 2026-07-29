"""
Colors Tool

Extracts dominant color palette from images.
Inherits from vision_base.py - uses output_format="json" for structured color data.
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
    artifact_type="colors",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="colors",
)

COLORS_CONFIG = {
    "color_count": {
        "type": "integer",
        "default": 5,
        "min": 1,
        "max": 12,
        "description": "Number of colors",
    },
    "format": {
        "type": "string",
        "enum": ["hex", "rgb", "name"],
        "default": "hex",
        "description": "Color format",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(color_count: int, color_format: str) -> str:
    """Build the colors prompt."""
    format_instructions = {
        "hex": 'Use hex codes (e.g., "#FF5733")',
        "rgb": 'Use RGB values (e.g., "rgb(255, 87, 51)")',
        "name": 'Use color names (e.g., "burnt orange")',
    }

    return f"""Extract the {color_count} most dominant colors from this image.

{format_instructions.get(color_format, format_instructions["hex"])}

Return as JSON:
{{
    "colors": [
        {{"color": "<value>", "name": "<descriptive name>", "percentage": <0-100>}},
        ...
    ],
    "mood": "<overall color mood: warm/cool/neutral/vibrant/muted>"
}}

Return ONLY valid JSON."""


def build_colors_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    color_count = config.get("color_count", 5)
    color_format = config.get("format", "hex")
    return _build_prompt(color_count, color_format)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="colors",
    display_name="Colors",
    description="Extract color palette",
    category="vision",
    icon="paintpalette",
    color="pink",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, COLORS_CONFIG),
    default_prompt=_build_prompt(5, "hex"),
    prompt_builder=build_colors_prompt,
    sort_order=14,
)
async def colors(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Extract dominant color palette from images."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get colors-specific config
    color_count = inputs.get("color_count", 5)
    color_format = inputs.get("format", "hex")

    # Build prompt
    prompt = inputs.get("prompt") or _build_prompt(color_count, color_format)

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
        max_image_dimension=inputs.get("max_image_dimension", 1024),
        # JSON output for structured color data
        temperature=inputs.get("temperature", 0.3),
        max_tokens=inputs.get("max_tokens"),
        output_format=inputs.get("output_format", "json"),
        output_options={},
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "colors",
    )
