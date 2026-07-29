"""
Keywords Tool

Extracts keywords/key phrases from text.
Inherits from llm_base.py - returns list of keywords.
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
    artifact_type="keywords",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field="keywords",
)

KEYWORDS_CONFIG = {
    "max_keywords": {
        "type": "integer",
        "default": 15,
        "description": "Max keywords",
    },
    "scope": {
        "type": "string",
        "enum": ["broad", "narrow", "technical"],
        "default": "broad",
        "description": "Keyword scope",
    },
}

KEYWORDS_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Text to extract keywords from",
        )
    ],
    BASE_INPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(max_keywords: int, scope: str) -> str:
    """Build the keyword extraction prompt."""
    scope_instructions = {
        "broad": "Include a mix of general topics, specific terms, and themes.",
        "narrow": "Focus on the most specific, distinctive terms unique to this text.",
        "technical": "Focus on technical terminology, domain-specific jargon, and specialized concepts.",
    }

    instruction = scope_instructions.get(scope, scope_instructions["broad"])

    return f"""Extract the {max_keywords} most important keywords or key phrases from this text.

{instruction}

Rules:
- Use lowercase unless proper nouns
- Include both single words and short phrases (2-3 words)
- Order by importance/relevance
- Avoid generic stopwords
- Separate with semicolons

Return keywords as a semicolon-separated list.
Example: keyword1; key phrase two; keyword3; ..."""


def build_keywords_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    max_keywords = config.get("max_keywords", 15)
    scope = config.get("scope", "broad")
    return _build_prompt(max_keywords, scope)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="keywords",
    display_name="Keywords",
    description="Extract keywords from text",
    category="llm",
    icon="textformat.abc",
    color="green",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=KEYWORDS_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, KEYWORDS_CONFIG),
    default_prompt=_build_prompt(15, "broad"),
    prompt_builder=build_keywords_prompt,
    sort_order=12,
)
async def keywords(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Extract keywords from text."""

    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    max_keywords = inputs.get("max_keywords", 15)
    scope = inputs.get("scope", "broad")

    prompt = inputs.get("prompt") or _build_prompt(max_keywords, scope)

    return await process_text(
        text=text,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        documents=documents,
        temperature=inputs.get("temperature", 0.3),
        max_tokens=inputs.get("max_tokens", 512),
        output_format=inputs.get("output_format", "list"),
        output_options={
            "max_items": inputs.get("max_items") or max_keywords,
        },
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "keywords",
    )
