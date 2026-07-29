"""
Classify Tool

Categorizes images/documents by type (photograph, letter, receipt, etc.)
Inherits from vision_base.py - uses output_format="choice" for constrained output.
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
    artifact_type="classification",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="doc_type",
)

DEFAULT_CATEGORIES = [
    "photograph",
    "letter",
    "receipt",
    "invoice",
    "diagram",
    "map",
    "handwriting",
    "screenshot",
    "artwork",
    "form",
    "certificate",
    "newspaper",
    "book_page",
    "presentation",
    "other",
]

CLASSIFY_CONFIG = {
    "categories": {
        "type": "array",
        "items": {"type": "string"},
        "default": DEFAULT_CATEGORIES,
        "description": "Document categories",
    },
    "multi_label": {
        "type": "boolean",
        "default": False,
        "description": "Allow multiple categories",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(categories: list[str], multi_label: bool) -> str:
    """Build the classification prompt."""
    categories_str = ", ".join(f'"{c}"' for c in categories)

    if multi_label:
        return f"""Classify this image/document. Select ALL applicable categories.

Categories: {categories_str}

Return a comma-separated list of matching categories."""
    else:
        return f"""Classify this image/document into exactly ONE category.

Categories: {categories_str}

Respond with exactly one category name from the list above."""


def build_classify_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    categories = config.get("categories", DEFAULT_CATEGORIES)
    multi_label = config.get("multi_label", False)
    return _build_prompt(categories, multi_label)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="classify",
    display_name="Classify",
    description="Categorize document type",
    category="vision",
    icon="square.grid.3x3.topleft.filled",
    color="green",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, CLASSIFY_CONFIG),
    default_prompt=_build_prompt(DEFAULT_CATEGORIES, False),
    prompt_builder=build_classify_prompt,
    sort_order=13,
)
async def classify(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Classify images/documents by type."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get classify-specific config
    categories = inputs.get("categories", DEFAULT_CATEGORIES)
    multi_label = inputs.get("multi_label", False)

    # Build prompt
    prompt = inputs.get("prompt") or _build_prompt(categories, multi_label)

    # Use output_format and reference_values to constrain output
    output_format = "list" if multi_label else "choice"

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
        max_image_dimension=inputs.get("max_image_dimension", 1024),
        # Use choice/list format to constrain output
        temperature=inputs.get("temperature", 0.3),  # Low temp for classification
        max_tokens=inputs.get("max_tokens"),
        output_format=inputs.get("output_format", output_format),
        output_options={
            "choices": categories,
            "max_items": len(categories),
        },
        reference_values={"categories": categories},
        match_mode=inputs.get("match_mode", "strict"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "doc_type",
    )
