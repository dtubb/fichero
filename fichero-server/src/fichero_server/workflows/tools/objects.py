"""
Objects Tool

Detects and identifies objects in images with positions.
Inherits from vision_base.py - returns JSON with object list.
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
    artifact_type="objects",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="objects",
)

OBJECTS_CONFIG = {
    "detail_level": {
        "type": "string",
        "enum": ["count", "basic", "detailed"],
        "default": "basic",
        "description": "Detail level",
    },
    "include_positions": {
        "type": "boolean",
        "default": True,
        "description": "Include positions",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(detail_level: str, include_positions: bool) -> str:
    """Build the object detection prompt."""
    position_text = ""
    if include_positions:
        position_text = ', "position": "<top-left/top-center/top-right/center-left/center/center-right/bottom-left/bottom-center/bottom-right>"'

    detail_instructions = {
        "count": """Count all distinct objects in this image.

Return as JSON:
{
    "total_objects": <number>,
    "categories": [
        {"type": "<object type>", "count": <number>}
    ]
}""",
        "basic": f"""Identify all objects in this image.

For each object, provide:
- type (what it is)
- count (how many){
            '''
- position (where in the image)'''
            if include_positions
            else ""
        }

Return as JSON:
{{
    "objects": [
        {{"type": "<object type>", "count": <number>{position_text}}}
    ],
    "total_objects": <number>
}}""",
        "detailed": f"""Identify and describe all objects in this image in detail.

For each object, provide:
- type (what it is)
- description (appearance, condition, notable features)
- size (relative: small/medium/large)
- count (how many){
            '''
- position (where in the image)'''
            if include_positions
            else ""
        }

Return as JSON:
{{
    "objects": [
        {{"type": "<object type>", "description": "<details>", "size": "<small/medium/large>", "count": <number>{
            position_text
        }}}
    ],
    "total_objects": <number>,
    "scene_description": "<brief overall scene>"
}}""",
    }

    base = detail_instructions.get(detail_level, detail_instructions["basic"])
    return f"{base}\n\nReturn ONLY valid JSON."


def build_objects_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    detail_level = config.get("detail_level", "basic")
    include_positions = config.get("include_positions", True)
    return _build_prompt(detail_level, include_positions)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="objects",
    display_name="Objects",
    description="Detect and identify objects",
    category="vision",
    icon="cube",
    color="teal",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, OBJECTS_CONFIG),
    default_prompt=_build_prompt("basic", True),
    prompt_builder=build_objects_prompt,
    sort_order=21,
)
async def objects(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Detect and identify objects in images."""

    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    detail_level = inputs.get("detail_level", "basic")
    include_positions = inputs.get("include_positions", True)

    prompt = inputs.get("prompt") or _build_prompt(detail_level, include_positions)

    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        vision_mode="llm",
        max_image_dimension=inputs.get("max_image_dimension", 2048),
        temperature=inputs.get("temperature", 0.3),
        max_tokens=inputs.get("max_tokens", 4096),
        output_format=inputs.get("output_format", "json"),
        output_options={},
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field"),
    )
