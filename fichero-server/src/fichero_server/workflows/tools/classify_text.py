"""
Classify Text Tool

Classifies text into user-defined categories.
Inherits from llm_base.py - uses output_format="choice" with reference_values.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero_server.workflows.types import State, PortDef, DataType
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.llm_base import (
    BASE_INPUT_PORTS,
    BASE_OUTPUT_PORTS,
    BASE_CONFIG_SCHEMA,
    merge_config_schema,
    merge_ports,
    LLMToolConfig,
    process_text,
)
from fichero_server.llm import LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = LLMToolConfig(
    artifact_type="classification",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field="classification",
)

DEFAULT_CATEGORIES = [
    "correspondence",
    "legal",
    "financial",
    "report",
    "memo",
    "minutes",
    "newspaper",
    "personal",
    "technical",
    "academic",
    "creative",
    "other",
]

CLASSIFY_TEXT_CONFIG = {
    "categories": {
        "type": "array",
        "items": {"type": "string"},
        "default": DEFAULT_CATEGORIES,
        "description": "Classification categories",
    },
    "multi_label": {
        "type": "boolean",
        "default": False,
        "description": "Allow multiple categories",
    },
}

CLASSIFY_TEXT_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Text to classify",
        )
    ],
    BASE_INPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(categories: list[str], multi_label: bool) -> str:
    """Build the text classification prompt."""
    categories_str = ", ".join(categories)

    if multi_label:
        return f"""Classify this text into one or more categories.

Available categories: {categories_str}

Select ALL categories that apply. Rank by relevance.

Return as JSON:
{{
    "categories": ["<primary category>", "<secondary if applicable>"],
    "confidence": <0.0-1.0 for primary>,
    "reasoning": "<brief explanation>"
}}

Return ONLY valid JSON."""
    else:
        return f"""Classify this text into exactly ONE category.

Available categories: {categories_str}

Choose the single best-fitting category.

Return ONLY the category name, nothing else."""


def build_classify_text_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    categories = config.get("categories", DEFAULT_CATEGORIES)
    multi_label = config.get("multi_label", False)
    return _build_prompt(categories, multi_label)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="classify_text",
    display_name="Classify Text",
    description="Classify text into categories",
    category="llm",
    icon="tag",
    color="teal",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=CLASSIFY_TEXT_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, CLASSIFY_TEXT_CONFIG),
    default_prompt=_build_prompt(DEFAULT_CATEGORIES, False),
    prompt_builder=build_classify_text_prompt,
    sort_order=14,
)
async def classify_text(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Classify text into categories."""

    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    categories = inputs.get("categories", DEFAULT_CATEGORIES)
    multi_label = inputs.get("multi_label", False)

    prompt = inputs.get("prompt") or _build_prompt(categories, multi_label)

    output_format = "json" if multi_label else "choice"

    return await process_text(
        text=text,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        documents=documents,
        temperature=inputs.get("temperature", 0.2),
        max_tokens=inputs.get("max_tokens", 512),
        output_format=inputs.get("output_format", output_format),
        output_options={},
        reference_values=inputs.get("reference_values") or {"category": categories},
        match_mode=inputs.get("match_mode", "strict"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "classification",
        chunk_size_chars=inputs.get("chunk_size_chars"),
    )
