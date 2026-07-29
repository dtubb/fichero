"""
Video Describe Tool

Describes video content visually and transcribes audio track.
Combines frame sampling (vision LLM) with audio transcription (Whisper).
Inherits from video_base.py - only defines describe-specific config and prompt.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero_server.workflows.types import State
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.llm_base import BASE_OUTPUT_PORTS, merge_config_schema
from fichero_server.workflows.tools.video_base import (
    VIDEO_INPUT_PORTS,
    VIDEO_CONFIG_SCHEMA,
    VideoToolConfig,
    process_video,
)
from fichero_server.llm import LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = VideoToolConfig(
    artifact_type="video_description",
    update_page_content=True,
    trigger_embedding=True,
    extract_audio=True,
    metadata_field="description",
)

# Describe-specific config (added to VIDEO_CONFIG_SCHEMA)
VIDEO_DESCRIBE_CONFIG = {
    "detail_level": {
        "type": "string",
        "enum": ["brief", "detailed", "comprehensive"],
        "default": "detailed",
        "description": "Detail level for visual description",
        "x-group": "primary",
    },
    "focus": {
        "type": "string",
        "description": "Focus area for description",
        "x-group": "primary",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(detail_level: str, focus: str) -> str:
    """Build the video description prompt."""
    detail_instructions = {
        "brief": "Provide a brief summary of what happens in the video.",
        "detailed": "Provide a detailed description of the video content, including scenes, actions, and notable elements.",
        "comprehensive": "Provide a comprehensive description including all visible elements, scene transitions, actions, objects, people, text overlays, and any notable visual or contextual details.",
    }

    prompt = f"""Describe the content of this video.

{detail_instructions.get(detail_level, detail_instructions["detailed"])}
"""

    if focus:
        prompt += f"\nFocus particularly on: {focus}"

    return prompt


def build_video_describe_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    detail_level = config.get("detail_level", "detailed")
    focus = config.get("focus", "")
    return _build_prompt(detail_level, focus)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="video_describe",
    display_name="Describe Video",
    description="Describe video content visually and transcribe audio track",
    category="video",
    icon="video",
    color="indigo",
    uses_llm=True,
    supports_batch=True,
    input_ports=VIDEO_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VIDEO_CONFIG_SCHEMA, VIDEO_DESCRIBE_CONFIG),
    default_prompt=_build_prompt("detailed", ""),
    prompt_builder=build_video_describe_prompt,
    sort_order=31,
)
async def video_describe(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Describe video content visually and transcribe audio."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get video-specific config
    extract_audio = inputs.get("extract_audio", True)
    frame_sample_rate = inputs.get("frame_sample_rate", 1)
    max_frames = inputs.get("max_frames", 10)
    max_image_dimension = inputs.get("max_image_dimension", 1024)
    whisper_model_size = inputs.get("whisper_model_size", "base")

    # Get describe-specific config
    detail_level = inputs.get("detail_level", "detailed")
    focus = inputs.get("focus", "")

    # Build prompt
    prompt = inputs.get("prompt") or _build_prompt(detail_level, focus)

    # Process with shared video logic
    return await process_video(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        # Video-specific
        extract_audio=extract_audio,
        frame_sample_rate=frame_sample_rate,
        max_frames=max_frames,
        max_image_dimension=max_image_dimension,
        whisper_model_size=whisper_model_size,
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
