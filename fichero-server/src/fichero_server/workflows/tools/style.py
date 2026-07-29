"""
Style Tool

Classifies the artistic/document style of an image.
Inherits from vision_base.py - uses output_format="choice" with reference_values.
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
    artifact_type="style",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="style",
)

DEFAULT_STYLES = [
    "photograph",
    "oil_painting",
    "watercolor",
    "drawing",
    "digital_art",
    "print",
    "manuscript",
    "engraving",
    "lithograph",
    "screen_capture",
    "diagram",
    "map",
]

STYLE_CONFIG = {
    "styles": {
        "type": "array",
        "items": {"type": "string"},
        "default": DEFAULT_STYLES,
        "description": "Style categories",
    },
    "include_details": {
        "type": "boolean",
        "default": True,
        "description": "Include style analysis",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(styles: list[str], include_details: bool) -> str:
    """Build the style classification prompt."""
    styles_str = ", ".join(styles)

    if include_details:
        return f"""Classify the artistic/document style of this image.

Choose ONE primary style from: {styles_str}

Also analyze:
- Medium/technique used
- Color palette characteristics
- Approximate era/period if identifiable
- Notable stylistic features

Return as JSON:
{{
    "style": "<primary style>",
    "medium": "<specific medium or technique>",
    "palette": "<warm/cool/muted/vibrant/monochrome>",
    "era": "<approximate period if identifiable>",
    "features": ["<notable stylistic features>"]
}}

Return ONLY valid JSON."""
    else:
        return f"""Classify the style of this image.

Choose ONE from: {styles_str}

Return ONLY the style type, nothing else."""


def build_style_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    styles = config.get("styles", DEFAULT_STYLES)
    include_details = config.get("include_details", True)
    return _build_prompt(styles, include_details)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="style",
    display_name="Style",
    description="Classify artistic/document style",
    category="vision",
    icon="paintbrush",
    color="pink",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, STYLE_CONFIG),
    default_prompt=_build_prompt(DEFAULT_STYLES, True),
    prompt_builder=build_style_prompt,
    sort_order=28,
)
async def style(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Classify artistic/document style."""

    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    styles = inputs.get("styles", DEFAULT_STYLES)
    include_details = inputs.get("include_details", True)

    prompt = inputs.get("prompt") or _build_prompt(styles, include_details)

    output_format = "json" if include_details else "choice"

    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        vision_mode="llm",
        max_image_dimension=inputs.get("max_image_dimension", 1024),
        temperature=inputs.get("temperature", 0.3),
        max_tokens=inputs.get("max_tokens", 1024),
        output_format=inputs.get("output_format", output_format),
        output_options={},
        reference_values=inputs.get("reference_values") or {"style": styles},
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "style",
    )
