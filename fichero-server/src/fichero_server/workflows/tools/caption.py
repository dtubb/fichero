"""
Caption Tool

Generates a short one-line caption for images.
Inherits from vision_base.py - uses output_format="words" for concise output.
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
    artifact_type="caption",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="caption",
)

CAPTION_CONFIG = {
    "style": {
        "type": "string",
        "enum": ["neutral", "descriptive", "creative", "technical"],
        "default": "neutral",
        "description": "Caption style",
    },
    "max_length": {
        "type": "integer",
        "default": 15,
        "description": "Max words",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(style: str, max_length: int) -> str:
    """Build the caption prompt."""
    style_instructions = {
        "neutral": "Write a factual, objective caption.",
        "descriptive": "Write a vivid, descriptive caption.",
        "creative": "Write an engaging, creative caption.",
        "technical": "Write a precise, technical caption.",
    }

    return f"""Write a single-line caption for this image.

{style_instructions.get(style, style_instructions["neutral"])}
Keep it under {max_length} words. No punctuation at the end.
Output only the caption text, nothing else."""


def build_caption_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    style = config.get("style", "neutral")
    max_length = config.get("max_length", 15)
    return _build_prompt(style, max_length)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="caption",
    parallelism="elementwise",
    display_name="Caption",
    description="Generate short image caption",
    category="vision",
    icon="text.below.photo",
    color="blue",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, CAPTION_CONFIG),
    default_prompt=_build_prompt("neutral", 15),
    prompt_builder=build_caption_prompt,
    sort_order=11,
)
async def caption(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Generate short captions for images."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get caption-specific config
    style = inputs.get("style", "neutral")
    max_length = inputs.get("max_length", 15)

    # Build prompt
    prompt = inputs.get("prompt") or _build_prompt(style, max_length)

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
        # Constrain output length
        temperature=inputs.get("temperature"),
        max_tokens=inputs.get("max_tokens", 100),
        output_format=inputs.get("output_format", "words"),
        output_options={
            "max_words": max_length,
        },
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "caption",
    )
