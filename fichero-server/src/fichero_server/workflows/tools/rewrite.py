"""
Rewrite Tool

Rewrites text in different styles, tones, or lengths.
Inherits from llm_base.py - transforms input text.
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
    artifact_type="rewrite",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field="rewrite",
)

REWRITE_CONFIG = {
    "style": {
        "type": "string",
        "enum": [
            "formal",
            "casual",
            "academic",
            "concise",
            "expanded",
            "simplified",
            "technical",
        ],
        "default": "concise",
        "description": "Writing style",
    },
    "target_language": {
        "type": "string",
        "default": "",
        "description": "Translate to language",
    },
}

REWRITE_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Text to rewrite",
        )
    ],
    BASE_INPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(style: str, target_language: str) -> str:
    """Build the rewrite prompt."""
    style_instructions = {
        "formal": "Rewrite in a formal, professional tone. Use proper grammar and avoid contractions.",
        "casual": "Rewrite in a casual, conversational tone. Keep it friendly and approachable.",
        "academic": "Rewrite in an academic style. Use precise language, cite-ready structure, and objective tone.",
        "concise": "Rewrite to be as concise as possible. Remove redundancy, keep only essential information.",
        "expanded": "Expand the text with more detail, examples, and explanation while keeping the same meaning.",
        "simplified": "Simplify the language. Use shorter sentences, common words, and clear structure.",
        "technical": "Rewrite in a technical style. Use precise terminology and structured format.",
    }

    instruction = style_instructions.get(style, style_instructions["concise"])

    language_text = ""
    if target_language:
        language_text = f"\n\nWrite the output in {target_language}."

    return f"""{instruction}

Preserve the original meaning and all key information.
Do not add new information or interpretation.{language_text}

Output ONLY the rewritten text, no explanations."""


def build_rewrite_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    style = config.get("style", "concise")
    target_language = config.get("target_language", "")
    return _build_prompt(style, target_language)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="rewrite",
    display_name="Rewrite",
    description="Rewrite text in different styles",
    category="llm",
    icon="arrow.triangle.2.circlepath",
    color="indigo",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=REWRITE_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, REWRITE_CONFIG),
    default_prompt=_build_prompt("concise", ""),
    prompt_builder=build_rewrite_prompt,
    sort_order=10,
)
async def rewrite(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Rewrite text in a different style."""

    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    style = inputs.get("style", "concise")
    target_language = inputs.get("target_language", "")

    prompt = inputs.get("prompt") or _build_prompt(style, target_language)

    return await process_text(
        text=text,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        documents=documents,
        temperature=inputs.get("temperature", 0.5),
        max_tokens=inputs.get("max_tokens", 4096),
        output_format=inputs.get("output_format", "text"),
        output_options={
            "max_words": inputs.get("max_words"),
        },
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field"),
        chunk_size_chars=inputs.get("chunk_size_chars"),
    )
