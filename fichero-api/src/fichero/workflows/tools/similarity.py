"""
Similarity Tool

Computes similarity scores between two or more images.
Like compare, processes multiple images together (not batch).
Returns numeric scores by aspect.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from fichero.workflows.types import State
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.llm_base import (
    BASE_OUTPUT_PORTS,
    merge_config_schema,
    build_context_section,
    parse_output,
)
from fichero.workflows.tools.vision_base import (
    VISION_INPUT_PORTS,
    VISION_CONFIG_SCHEMA,
    VisionToolConfig,
    file_to_data_uri,
)
from fichero.llm import vision, LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = VisionToolConfig(
    artifact_type="similarity",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
)

SIMILARITY_CONFIG = {
    "aspects": {
        "type": "array",
        "items": {"type": "string"},
        "default": ["content", "composition", "color", "style"],
        "description": "Aspects to score",
    },
    "scale": {
        "type": "string",
        "enum": ["percentage", "1-10", "1-5"],
        "default": "percentage",
        "description": "Score scale",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================

def _build_prompt(aspects: list[str], scale: str) -> str:
    """Build the similarity scoring prompt."""
    aspects_str = ", ".join(aspects)

    scale_text = {
        "percentage": "Score each aspect as a percentage (0-100, where 100 = identical)",
        "1-10": "Score each aspect from 1 (completely different) to 10 (identical)",
        "1-5": "Score each aspect from 1 (completely different) to 5 (identical)",
    }.get(scale, "Score each aspect as a percentage (0-100)")

    return f"""Compare these images and score their similarity.

{scale_text}

Score these aspects: {aspects_str}

Also provide an overall similarity score.

Return as JSON:
{{
    "overall_similarity": <score>,
    "scores": {{
        "<aspect>": <score>,
        ...
    }},
    "most_similar": "<which aspect is most similar>",
    "most_different": "<which aspect is most different>",
    "notes": "<brief explanation of key differences>"
}}

Return ONLY valid JSON."""


def build_similarity_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    aspects = config.get("aspects", ["content", "composition", "color", "style"])
    scale = config.get("scale", "percentage")
    return _build_prompt(aspects, scale)


# =============================================================================
# Tool Registration
# =============================================================================

@register_tool(
    name="similarity",
    display_name="Similarity",
    description="Score image similarity",
    category="vision",
    icon="square.on.square.dashed",
    color="orange",
    uses_llm=True,
    supports_batch=False,  # Processes all files together
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, SIMILARITY_CONFIG),
    default_prompt=_build_prompt(["content", "composition", "color", "style"], "percentage"),
    prompt_builder=build_similarity_prompt,
    sort_order=29,
)
async def similarity(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Score similarity between multiple images."""

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
            "error": "Similarity requires at least 2 images",
        }

    aspects = inputs.get("aspects", ["content", "composition", "color", "style"])
    scale = inputs.get("scale", "percentage")
    max_image_dimension = inputs.get("max_image_dimension", 1024)
    temperature = inputs.get("temperature")
    max_tokens = inputs.get("max_tokens")

    prompt = inputs.get("prompt") or _build_prompt(aspects, scale)

    # Build context
    context_section = build_context_section(context, input_metadata)
    final_prompt = f"{context_section}{prompt}"

    # Override LLMConfig
    effective_config = llm_config
    if temperature is not None or max_tokens is not None:
        effective_config = dataclasses.replace(
            llm_config,
            temperature=temperature if temperature is not None else llm_config.temperature,
            max_tokens=max_tokens if max_tokens is not None else llm_config.max_tokens,
        )

    try:
        image_uris = [file_to_data_uri(f, max_dimension=max_image_dimension) for f in files]

        response = await vision(
            images=image_uris,
            prompt=final_prompt,
            config=effective_config,
        )

        parsed = parse_output(response, "json")

        return {
            "text": response,
            "value": parsed,
            "texts": [response],
            "values": [parsed],
            "results": [{"files": files, "text": response, "value": parsed}],
            "artifacts": [],
        }

    except Exception as e:
        logger.error(f"Similarity scoring failed: {e}")
        return {
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "error": str(e),
        }
