"""
Safety Tool

Classifies image content safety level.
Inherits from vision_base.py - uses output_format="json" for multi-category assessment.
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
    artifact_type="safety",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="safety",
)

SAFETY_CONFIG = {
    "categories": {
        "type": "array",
        "items": {"type": "string"},
        "default": ["violence", "adult", "drugs", "hate", "self_harm"],
        "description": "Safety categories to check",
    },
    "threshold": {
        "type": "string",
        "enum": ["strict", "moderate", "permissive"],
        "default": "moderate",
        "description": "Sensitivity level",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(categories: list[str], threshold: str) -> str:
    """Build the safety classification prompt."""
    categories_str = ", ".join(categories)

    threshold_text = {
        "strict": "Be conservative - flag anything that could be concerning even in mild forms.",
        "moderate": "Flag content that would be inappropriate for general audiences.",
        "permissive": "Only flag explicit or severe content.",
    }.get(threshold, "Flag content that would be inappropriate for general audiences.")

    return f"""Assess the content safety of this image.

Check for these categories: {categories_str}

{threshold_text}

Return as JSON:
{{
    "safe": <true/false>,
    "overall_rating": "<safe/caution/unsafe>",
    "categories": {{
        "<category>": {{
            "detected": <true/false>,
            "severity": "<none/mild/moderate/severe>",
            "description": "<brief description if detected>"
        }}
    }},
    "summary": "<brief safety assessment>"
}}

Return ONLY valid JSON."""


def build_safety_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    categories = config.get(
        "categories", ["violence", "adult", "drugs", "hate", "self_harm"]
    )
    threshold = config.get("threshold", "moderate")
    return _build_prompt(categories, threshold)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="safety",
    display_name="Safety",
    description="Content safety assessment",
    category="vision",
    icon="shield.checkered",
    color="red",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, SAFETY_CONFIG),
    default_prompt=_build_prompt(
        ["violence", "adult", "drugs", "hate", "self_harm"], "moderate"
    ),
    prompt_builder=build_safety_prompt,
    sort_order=24,
)
async def safety(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Assess content safety of images."""

    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    categories = inputs.get(
        "categories", ["violence", "adult", "drugs", "hate", "self_harm"]
    )
    threshold = inputs.get("threshold", "moderate")

    prompt = inputs.get("prompt") or _build_prompt(categories, threshold)

    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        vision_mode="llm",
        max_image_dimension=inputs.get("max_image_dimension", 512),
        temperature=inputs.get("temperature", 0.1),
        max_tokens=inputs.get("max_tokens", 1024),
        output_format=inputs.get("output_format", "json"),
        output_options={},
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "safety",
    )
