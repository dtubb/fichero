"""
Transcribe Tool

Extracts text from images using vision LLM or Apple Vision (on-device OCR).
Inherits from vision_base.py - only defines transcribe-specific config and prompt.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero.workflows.types import State
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.llm_base import BASE_OUTPUT_PORTS, merge_config_schema
from fichero.workflows.tools.vision_base import (
    VISION_INPUT_PORTS,
    VISION_CONFIG_SCHEMA,
    VisionToolConfig,
    process_vision,
)
from fichero.llm import LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = VisionToolConfig(
    artifact_type="transcription",
    update_page_content=True,
    trigger_embedding=True,
    supports_apple_vision=True,
    metadata_field="transcription",
)

# Transcribe-specific config (added to VISION_CONFIG_SCHEMA)
TRANSCRIBE_CONFIG = {
    "language": {
        "type": "string",
        "default": "en",
        "description": "Language",
    },
    "return_boxes": {
        "type": "boolean",
        "default": False,
        "description": "Text positions",
    },
    "update_page_content": {
        "type": "boolean",
        "default": True,
        "description": "Index for search",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(language: str, return_boxes: bool) -> str:
    """Build the transcription prompt."""
    prompt = f"""Extract and transcribe all text from this image.

Language: {language}

Instructions:
- Preserve the original text layout and structure
- Include all visible text, including headers, labels, and annotations
- If text is handwritten, transcribe as accurately as possible
- If text is unclear, indicate with [unclear]
- Maintain paragraph breaks and list formatting
"""

    if return_boxes:
        prompt += """
Additionally, provide bounding box coordinates for each text region in JSON format:
{
    "text": "transcribed text here",
    "boxes": [
        {"text": "...", "x": 0, "y": 0, "width": 100, "height": 20},
        ...
    ]
}
"""
    else:
        prompt += "\nOutput only the transcribed text."

    return prompt


def build_transcribe_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    language = config.get("language", "en")
    return_boxes = config.get("return_boxes", False)
    return _build_prompt(language, return_boxes)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="transcribe",
    display_name="Transcribe",
    description="Extract text from images (OCR)",
    category="vision",
    icon="text.viewfinder",
    color="blue",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, TRANSCRIBE_CONFIG),
    config_defaults={
        "vision_mode": "apple",
        "language": "en",
        "return_boxes": False,
        "update_page_content": True,
        "save_to_db": True,
    },
    default_prompt=_build_prompt("en", False),
    prompt_builder=build_transcribe_prompt,
    sort_order=10,
)
async def transcribe(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Extract text from images using vision AI."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get transcribe-specific config
    vision_mode = inputs.get("vision_mode", "apple")
    language = inputs.get("language", "en")
    return_boxes = inputs.get("return_boxes", False)
    update_page_content = inputs.get("update_page_content", True)

    # Build prompt
    prompt = inputs.get("prompt") or _build_prompt(language, return_boxes)

    # Override tool config if user disabled page_content update
    tool_config = TOOL_CONFIG
    if not update_page_content:
        tool_config = VisionToolConfig(
            artifact_type="transcription",
            update_page_content=False,
            trigger_embedding=False,
            supports_apple_vision=True,
        )

    # Process with shared logic - pass all inherited config
    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=tool_config,
        # Vision-specific
        vision_mode=vision_mode,
        language=language,
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
        metadata_field=inputs.get("metadata_field"),
    )
