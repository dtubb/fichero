"""
Compare Tool

Compares two or more images to identify differences and similarities.
Inherits from vision_base.py but processes multiple images together.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from fichero_server.workflows.types import State
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.llm_base import (
    BASE_OUTPUT_PORTS,
    merge_config_schema,
    build_context_section,
    build_output_constraint,
    parse_output,
)
from fichero_server.workflows.tools.vision_base import (
    VISION_INPUT_PORTS,
    VISION_CONFIG_SCHEMA,
    VisionToolConfig,
    file_to_data_uri,
)
from fichero_server.llm import vision, LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = VisionToolConfig(
    artifact_type="comparison",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
)

COMPARE_CONFIG = {
    "focus": {
        "type": "string",
        "enum": ["differences", "similarities", "both", "changes"],
        "default": "both",
        "description": "Comparison focus",
    },
    "aspects": {
        "type": "array",
        "items": {"type": "string"},
        "default": ["content", "style", "layout", "color"],
        "description": "Aspects to compare",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(focus: str, aspects: list[str]) -> str:
    """Build the comparison prompt."""
    focus_instructions = {
        "differences": "Focus on what is DIFFERENT between the images.",
        "similarities": "Focus on what is SIMILAR between the images.",
        "both": "Describe both similarities and differences.",
        "changes": "Describe what changed from the first image to subsequent ones (before/after).",
    }

    aspects_str = ", ".join(aspects)

    return f"""Compare these images.

{focus_instructions.get(focus, focus_instructions["both"])}

Consider these aspects: {aspects_str}

Provide a clear, structured comparison."""


def build_compare_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    focus = config.get("focus", "both")
    aspects = config.get("aspects", ["content", "style", "layout", "color"])
    return _build_prompt(focus, aspects)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="compare",
    display_name="Compare",
    description="Compare multiple images",
    category="vision",
    icon="square.on.square.badge.person.crop",
    color="orange",
    uses_llm=True,
    supports_batch=False,  # Processes all files together, not individually
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, COMPARE_CONFIG),
    default_prompt=_build_prompt("both", ["content", "style", "layout", "color"]),
    prompt_builder=build_compare_prompt,
    sort_order=19,
)
async def compare(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Compare multiple images together."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    if isinstance(files, str):
        files = [files]

    if len(files) < 2:
        return {
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "error": "Compare requires at least 2 images",
        }

    # Get compare-specific config
    focus = inputs.get("focus", "both")
    aspects = inputs.get("aspects", ["content", "style", "layout", "color"])
    max_image_dimension = inputs.get("max_image_dimension", 1024)
    temperature = inputs.get("temperature")
    max_tokens = inputs.get("max_tokens")
    output_format = inputs.get("output_format", "text")

    # Build prompt
    prompt = inputs.get("prompt") or _build_prompt(focus, aspects)

    # Build context
    context_section = build_context_section(context, input_metadata)
    output_constraint = build_output_constraint(output_format)
    final_prompt = f"{context_section}{prompt}{output_constraint}"

    # Override LLMConfig
    effective_config = llm_config
    if temperature is not None or max_tokens is not None:
        effective_config = dataclasses.replace(
            llm_config,
            temperature=temperature
            if temperature is not None
            else llm_config.temperature,
            max_tokens=max_tokens if max_tokens is not None else llm_config.max_tokens,
        )

    try:
        # Convert all images and send together
        image_uris = []
        for file_path in files:
            uri = file_to_data_uri(file_path, max_dimension=max_image_dimension)
            image_uris.append(uri)

        # Call vision with multiple images
        response = await vision(
            images=image_uris,
            prompt=final_prompt,
            config=effective_config,
        )

        parsed = parse_output(response, output_format)

        return {
            "text": response,
            "value": parsed,
            "texts": [response],
            "values": [parsed],
            "results": [{"files": files, "text": response, "value": parsed}],
            "artifacts": [],
        }

    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        return {
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "error": str(e),
        }
