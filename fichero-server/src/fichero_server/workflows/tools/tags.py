"""
Tags Tool

Generates keyword tags for images using vision LLM.
Inherits from vision_base.py - only defines tags-specific config and prompt.
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
    artifact_type="tags",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="tags",  # Store tags in metadata
)

# Tags-specific config (added to VISION_CONFIG_SCHEMA)
TAGS_CONFIG = {
    "tag_count": {
        "type": "integer",
        "default": 10,
        "description": "Number of tags",
    },
    "categories": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Tag categories",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================

DEFAULT_PROMPT = """Generate keyword tags for this image.

Instructions:
- Return 5-15 relevant keywords/tags
- Include: subjects, objects, colors, mood, style, setting
- Use lowercase, single words or short phrases
- Separate tags with commas
- Be specific (e.g., "golden retriever" not just "dog")

Output format: tag1, tag2, tag3, ..."""


def _build_prompt(tag_count: int, categories: list[str]) -> str:
    """Build the tags prompt."""
    cat_text = ""
    if categories:
        cat_text = f"\nFocus on these categories: {', '.join(categories)}"

    return f"""Generate keyword tags for this image.

Instructions:
- Return {tag_count} relevant keywords/tags
- Include: subjects, objects, colors, mood, style, setting{cat_text}
- Use lowercase, single words or short phrases
- Separate tags with commas
- Be specific (e.g., "golden retriever" not just "dog")

Output format: tag1, tag2, tag3, ..."""


def build_tags_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    tag_count = config.get("tag_count", 10)
    categories = config.get("categories", [])
    return _build_prompt(tag_count, categories)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="tags",
    display_name="Tags",
    description="Generate keyword tags",
    category="vision",
    icon="tag",
    color="orange",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, TAGS_CONFIG),
    default_prompt=DEFAULT_PROMPT,
    prompt_builder=build_tags_prompt,
    sort_order=12,
)
async def tags(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Generate keyword tags for images."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get tags-specific config
    tag_count = inputs.get("tag_count", 10)
    categories = inputs.get("categories", [])

    # Build prompt
    prompt = inputs.get("prompt") or _build_prompt(tag_count, categories)

    # Process with shared logic - output_format=list for tags
    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        # Vision-specific
        vision_mode="llm",  # Tags always uses LLM
        max_image_dimension=inputs.get("max_image_dimension", 1024),  # Smaller for tags
        # Inherited from BASE_CONFIG - default to list format for tags
        temperature=inputs.get("temperature"),
        max_tokens=inputs.get("max_tokens"),
        output_format=inputs.get("output_format", "list"),  # Default to list
        output_options={
            "choices": inputs.get("choices"),
            "max_words": inputs.get("max_words"),
            "max_items": inputs.get("max_items") or tag_count,
        },
        reference_values=inputs.get("reference_values"),  # Match against known tags
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "tags",
    )
