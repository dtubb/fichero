"""
Describe Tool

Generates descriptions of images using vision LLM.
Inherits from vision_base.py - only defines describe-specific config and prompt.
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
    artifact_type="description",
    update_page_content=False,  # Descriptions aren't the doc's text
    trigger_embedding=False,
    supports_apple_vision=False,  # Need LLM for descriptions
    metadata_field="description",  # Store in metadata for quick access
)

# Describe-specific config (added to VISION_CONFIG_SCHEMA)
DESCRIBE_CONFIG = {
    "detail_level": {
        "type": "string",
        "enum": ["brief", "detailed", "comprehensive"],
        "default": "detailed",
        "description": "Detail level",
    },
    "focus": {
        "type": "string",
        "description": "Focus area",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(detail_level: str, focus: str) -> str:
    """Build the description prompt."""
    detail_instructions = {
        "brief": "Provide a brief, one-sentence description.",
        "detailed": (
            "Provide a detailed visual description covering what is depicted, "
            "layout, figures, handwriting versus print, condition, composition, "
            "and context."
        ),
        "comprehensive": (
            "Provide a comprehensive visual description including all visible "
            "elements, their relationships, layout, figures, handwriting versus "
            "print, physical condition, colors, textures, lighting, and any text "
            "or symbols."
        ),
    }

    prompt = f"""Describe this image.

{detail_instructions.get(detail_level, detail_instructions["detailed"])}
"""

    if focus:
        prompt += f"\nFocus particularly on: {focus}"

    return prompt


def build_describe_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    detail_level = config.get("detail_level", "detailed")
    focus = config.get("focus", "")
    return _build_prompt(detail_level, focus)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="describe",
    parallelism="elementwise",
    display_name="Describe",
    description="Generate image descriptions",
    category="vision",
    icon="eye",
    color="blue",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, DESCRIBE_CONFIG),
    config_defaults={
        "vision_mode": "llm",
        "detail_level": "detailed",
        "save_to_db": True,
    },
    default_prompt=_build_prompt("detailed", ""),
    prompt_builder=build_describe_prompt,
    sort_order=11,
)
async def describe(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Generate descriptions of images using vision AI."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get describe-specific config
    detail_level = inputs.get("detail_level", "detailed")
    focus = inputs.get("focus", "")

    # Build prompt
    prompt = inputs.get("prompt") or _build_prompt(detail_level, focus)

    # Process with shared logic - pass all inherited config
    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        # Vision-specific
        vision_mode=inputs.get("vision_mode", "llm"),
        max_image_dimension=inputs.get("max_image_dimension", 2048),
        # Inherited from BASE_CONFIG
        temperature=inputs.get("temperature"),
        max_tokens=inputs.get("max_tokens"),
        output_format=inputs.get("output_format", "text"),
        output_options={
            "choices": inputs.get("choices"),
            "max_words": inputs.get("max_words"),
            "max_items": inputs.get("max_items"),
        },
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "description",
    )
