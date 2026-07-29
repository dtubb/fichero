"""
Quality Tool

Assesses image quality across multiple dimensions.
Inherits from vision_base.py - returns JSON with quality scores.
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
    artifact_type="quality",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="quality",
)

QUALITY_CONFIG = {
    "aspects": {
        "type": "array",
        "items": {"type": "string"},
        "default": ["sharpness", "exposure", "noise", "composition", "color_balance"],
        "description": "Quality aspects to assess",
    },
    "scale": {
        "type": "string",
        "enum": ["1-5", "1-10", "percentage"],
        "default": "1-10",
        "description": "Rating scale",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(aspects: list[str], scale: str) -> str:
    """Build the quality assessment prompt."""
    aspects_str = ", ".join(aspects)

    scale_text = {
        "1-5": "Rate each aspect from 1 (poor) to 5 (excellent)",
        "1-10": "Rate each aspect from 1 (poor) to 10 (excellent)",
        "percentage": "Rate each aspect as a percentage (0-100)",
    }.get(scale, "Rate each aspect from 1 (poor) to 10 (excellent)")

    return f"""Assess the technical quality of this image.

Evaluate these aspects: {aspects_str}

{scale_text}. Also provide an overall quality score.

Return as JSON:
{{
    "overall": <score>,
    "scores": {{
        "<aspect>": <score>,
        ...
    }},
    "issues": ["<any quality issues found>"],
    "strengths": ["<quality strengths>"]
}}

Return ONLY valid JSON."""


def build_quality_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    aspects = config.get(
        "aspects", ["sharpness", "exposure", "noise", "composition", "color_balance"]
    )
    scale = config.get("scale", "1-10")
    return _build_prompt(aspects, scale)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="quality",
    display_name="Quality",
    description="Assess image quality",
    category="vision",
    icon="star.leadinghalf.filled",
    color="yellow",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, QUALITY_CONFIG),
    default_prompt=_build_prompt(
        ["sharpness", "exposure", "noise", "composition", "color_balance"], "1-10"
    ),
    prompt_builder=build_quality_prompt,
    sort_order=23,
)
async def quality(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Assess image quality."""

    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    aspects = inputs.get(
        "aspects", ["sharpness", "exposure", "noise", "composition", "color_balance"]
    )
    scale = inputs.get("scale", "1-10")

    prompt = inputs.get("prompt") or _build_prompt(aspects, scale)

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
        temperature=inputs.get("temperature", 0.2),
        max_tokens=inputs.get("max_tokens", 1024),
        output_format=inputs.get("output_format", "json"),
        output_options={},
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "quality",
    )
