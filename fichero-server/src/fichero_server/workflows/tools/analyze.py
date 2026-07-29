"""
Analyze Tool (Custom Vision)

Generic vision tool with user-defined prompt.
Inherits from vision_base.py - the flexible catch-all for any vision task.
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
    artifact_type="analysis",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="analysis",
)

# Analyze has no additional config - it uses all BASE + VISION config
# The prompt is required though
ANALYZE_CONFIG = {}  # Empty - all options inherited


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="analyze",
    display_name="Analyze",
    description="Custom vision analysis",
    category="vision",
    icon="sparkle.magnifyingglass",
    color="purple",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, ANALYZE_CONFIG),
    default_prompt="Analyze this image and describe what you see.",
    sort_order=15,
)
async def analyze(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Custom vision analysis with user-defined prompt."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get prompt - required for analyze
    prompt = inputs.get("prompt", "Analyze this image and describe what you see.")

    if not prompt:
        return {
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "error": "No prompt provided",
        }

    # Process with shared logic - analyze uses all inherited config
    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        # Vision-specific
        vision_mode="llm",  # Analyze always uses LLM
        max_image_dimension=inputs.get("max_image_dimension", 2048),
        # All inherited from BASE_CONFIG
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
