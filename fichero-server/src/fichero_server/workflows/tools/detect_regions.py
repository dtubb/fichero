"""
Detect Regions Tool

Bboxes-first (Daniel, 2026-08-11): every transcribe workflow gets bounding
boxes BEFORE the transcriber runs. This tool is that first pass — on-device
Apple Vision OCR with geometry (no LLM, no network), persisted per page as
a ``regions`` artifact whose ``ocr_geometry`` carries normalized top-left-
origin line/word boxes. The preview overlay reads the same OCRGeometryResult
shape it already reads from transcription artifacts, and downstream
transcribers can crop to or attribute spans against the detected regions
regardless of which provider transcribes.

Reuses process_vision's Apple branch wholesale — per-file bounded fan-out,
PDF page propagation, artifact upsert — by forcing an apple provider config;
the node's own llm_config is deliberately ignored (this step must stay
local and free even in an all-cloud workflow).
"""

from __future__ import annotations

import logging
from typing import Any

from fichero_server.workflows.types import State
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.llm_base import BASE_OUTPUT_PORTS
from fichero_server.workflows.tools.vision_base import (
    VISION_INPUT_PORTS,
    VisionToolConfig,
    process_vision,
)
from fichero_server.llm import LLMConfig

logger = logging.getLogger(__name__)

TOOL_CONFIG = VisionToolConfig(
    artifact_type="regions",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=True,
)

DETECT_REGIONS_CONFIG = {
    "language": {
        "type": "string",
        "default": "en",
        "description": (
            "Recognition locale hint for Apple Vision (an OCR hint, not a "
            "claim about the document)"
        ),
    },
}


@register_tool(
    name="detect_regions",
    parallelism="elementwise",
    display_name="Detect Regions",
    description=(
        "On-device text-region detection (Apple Vision): normalized line and "
        "word bounding boxes saved per page, before any transcription"
    ),
    category="vision",
    icon="rectangle.dashed.badge.record",
    color="purple",
    uses_llm=False,
    supports_batch=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=DETECT_REGIONS_CONFIG,
    config_defaults={"language": "en"},
    sort_order=4,
    tested=True,
)
async def detect_regions(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Detect text regions with Apple Vision and persist them as artifacts."""
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])

    result = await process_vision(
        files=files,
        documents=documents,
        # The Apple branch never sends a prompt to a model; kept explicit so
        # a future non-Apple fallback cannot silently inherit a transcription
        # prompt.
        prompt="",
        # Forced local provider — see module docstring.
        llm_config=LLMConfig(provider="apple", model="apple-vision"),
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        vision_mode="apple",
        language=inputs.get("language", "en"),
        max_image_dimension=inputs.get("max_image_dimension", 2048),
        force_ocr=True,
        temperature=None,
        max_tokens=None,
        output_format="text",
        output_options={},
        reference_values=None,
        match_mode="prefer",
        context=None,
        input_metadata=inputs.get("metadata"),
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=False,
    )

    # Pass the inputs through untouched so a transcriber chains directly
    # after this node: detect_regions annotates, it does not transform.
    result["files"] = files
    result["documents"] = documents
    return result
