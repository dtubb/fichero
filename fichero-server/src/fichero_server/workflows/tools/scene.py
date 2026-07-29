"""
Scene Tool

Classifies the scene/environment type of an image.
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
    artifact_type="scene",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="scene",
)

DEFAULT_SCENES = [
    "indoor",
    "outdoor_urban",
    "outdoor_nature",
    "studio",
    "aerial",
    "underwater",
    "abstract",
    "document",
    "screenshot",
]

SCENE_CONFIG = {
    "scenes": {
        "type": "array",
        "items": {"type": "string"},
        "default": DEFAULT_SCENES,
        "description": "Scene categories",
    },
    "include_details": {
        "type": "boolean",
        "default": True,
        "description": "Include scene details",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(scenes: list[str], include_details: bool) -> str:
    """Build the scene classification prompt."""
    scenes_str = ", ".join(scenes)

    if include_details:
        return f"""Classify the scene/environment in this image.

Choose ONE primary scene type from: {scenes_str}

Also describe:
- Lighting conditions (natural/artificial, bright/dim)
- Time of day if applicable (dawn/day/dusk/night)
- Weather if visible
- Setting details

Return as JSON:
{{
    "scene": "<primary scene type>",
    "lighting": "<lighting description>",
    "time_of_day": "<if applicable>",
    "weather": "<if visible>",
    "details": "<brief setting description>"
}}

Return ONLY valid JSON."""
    else:
        return f"""Classify the scene/environment in this image.

Choose ONE from: {scenes_str}

Return ONLY the scene type, nothing else."""


def build_scene_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    scenes = config.get("scenes", DEFAULT_SCENES)
    include_details = config.get("include_details", True)
    return _build_prompt(scenes, include_details)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="scene",
    display_name="Scene",
    description="Classify scene environment",
    category="vision",
    icon="photo.on.rectangle",
    color="green",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, SCENE_CONFIG),
    default_prompt=_build_prompt(DEFAULT_SCENES, True),
    prompt_builder=build_scene_prompt,
    sort_order=22,
)
async def scene(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Classify the scene/environment in images."""

    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    scenes = inputs.get("scenes", DEFAULT_SCENES)
    include_details = inputs.get("include_details", True)

    prompt = inputs.get("prompt") or _build_prompt(scenes, include_details)

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
        reference_values=inputs.get("reference_values") or {"scene": scenes},
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "scene",
    )
