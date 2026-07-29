"""
Faces Tool

Detects and describes people/faces in images.
Inherits from vision_base.py - uses output_format="json" for structured face data.
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
    artifact_type="faces",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="faces",
)

FACES_CONFIG = {
    "detail": {
        "type": "string",
        "enum": ["count", "basic", "detailed"],
        "default": "basic",
        "description": "Detection detail",
    },
    "include_expressions": {
        "type": "boolean",
        "default": True,
        "description": "Describe expressions",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(detail: str, include_expressions: bool) -> str:
    """Build the faces detection prompt."""
    if detail == "count":
        return """Count the number of people/faces visible in this image.

Return as JSON:
{"count": <number>, "confidence": "high/medium/low"}

Return ONLY valid JSON."""

    expression_text = ""
    if include_expressions:
        expression_text = ', "expression": "<facial expression>"'

    if detail == "detailed":
        return f"""Detect and describe all people visible in this image.

For each person, note:
- Approximate age range
- Gender presentation
- Hair and clothing description
- Position in image (left/center/right)
- Expression/mood

Return as JSON:
{{
    "count": <number>,
    "people": [
        {{"position": "<location>", "age_range": "<range>", "description": "<appearance>"{expression_text}}},
        ...
    ]
}}

Return ONLY valid JSON."""

    # basic
    return f"""Detect people/faces in this image.

Return as JSON:
{{
    "count": <number>,
    "people": [
        {{"position": "<left/center/right>", "description": "<brief description>"{expression_text}}},
        ...
    ]
}}

Return ONLY valid JSON."""


def build_faces_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    detail = config.get("detail", "basic")
    include_expressions = config.get("include_expressions", True)
    return _build_prompt(detail, include_expressions)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="faces",
    display_name="Faces",
    description="Detect and describe people",
    category="vision",
    icon="person.2",
    color="teal",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, FACES_CONFIG),
    default_prompt=_build_prompt("basic", True),
    prompt_builder=build_faces_prompt,
    sort_order=17,
)
async def faces(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Detect and describe people in images."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get faces-specific config
    detail = inputs.get("detail", "basic")
    include_expressions = inputs.get("include_expressions", True)

    # Build prompt
    prompt = inputs.get("prompt") or _build_prompt(detail, include_expressions)

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
        max_image_dimension=inputs.get("max_image_dimension", 2048),
        # JSON output for structured face data
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
        metadata_field=inputs.get("metadata_field") or "faces",
    )
