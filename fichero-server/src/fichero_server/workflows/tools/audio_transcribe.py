"""
Audio Transcribe Tool

Transcribes audio files to text using local Whisper, Apple Speech, or remote providers.
Inherits from audio_base.py - only defines transcribe-specific config and prompt.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero_server.workflows.types import State
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.llm_base import BASE_OUTPUT_PORTS, merge_config_schema
from fichero_server.workflows.tools.audio_base import (
    AUDIO_INPUT_PORTS,
    AUDIO_CONFIG_SCHEMA,
    AudioToolConfig,
    process_audio,
)
from fichero_server.llm import LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = AudioToolConfig(
    artifact_type="transcription",
    update_page_content=True,
    trigger_embedding=True,
    supports_apple_speech=True,
    supports_local_whisper=True,
    metadata_field="transcription",
)

# Transcribe-specific config (added to AUDIO_CONFIG_SCHEMA)
TRANSCRIBE_CONFIG = {
    "timestamps": {
        "type": "boolean",
        "default": False,
        "description": "Include timestamps in output",
        "x-group": "advanced",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(language: str) -> str:
    """Build the transcription prompt."""
    return f"Transcribe this audio accurately in {language}. Preserve formatting and punctuation."


def build_audio_transcribe_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    language = config.get("language", "en")
    return _build_prompt(language)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="audio_transcribe",
    display_name="Transcribe Audio",
    description="Transcribe audio files to text using Whisper, Apple Speech, or cloud providers",
    category="audio",
    icon="waveform",
    color="purple",
    uses_llm=True,  # Only when audio_mode="llm"
    supports_batch=True,
    input_ports=AUDIO_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(AUDIO_CONFIG_SCHEMA, TRANSCRIBE_CONFIG),
    default_prompt=_build_prompt("en"),
    prompt_builder=build_audio_transcribe_prompt,
    sort_order=21,
)
async def audio_transcribe(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Transcribe audio files to text."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get audio-specific config
    audio_mode = inputs.get("audio_mode", "local_whisper")
    language = inputs.get("language", "en")
    whisper_model_size = inputs.get("whisper_model_size", "base")

    # Build prompt (used for LLM mode)
    prompt = inputs.get("prompt") or _build_prompt(language)

    # Process with shared audio logic
    return await process_audio(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        # Audio-specific
        audio_mode=audio_mode,
        language=language,
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
        metadata_field=inputs.get("metadata_field") or "transcription",
    )
