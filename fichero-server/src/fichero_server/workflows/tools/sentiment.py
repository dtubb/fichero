"""
Sentiment Tool

Analyzes text sentiment/emotional tone.
Inherits from llm_base.py - uses output_format="choice" or "json".
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
    artifact_type="sentiment",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field="sentiment",
)

SENTIMENT_CONFIG = {
    "granularity": {
        "type": "string",
        "enum": ["binary", "ternary", "five_point", "detailed"],
        "default": "ternary",
        "description": "Sentiment scale",
    },
    "include_emotions": {
        "type": "boolean",
        "default": False,
        "description": "Include specific emotions",
    },
}

SENTIMENT_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Text to analyze",
        )
    ],
    BASE_INPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(granularity: str, include_emotions: bool) -> str:
    """Build the sentiment analysis prompt."""
    scale_instructions = {
        "binary": "Classify as: positive or negative",
        "ternary": "Classify as: positive, neutral, or negative",
        "five_point": "Classify as: very_positive, positive, neutral, negative, or very_negative",
        "detailed": "Provide a detailed sentiment analysis with scores",
    }

    scale = scale_instructions.get(granularity, scale_instructions["ternary"])

    if granularity == "detailed" or include_emotions:
        emotions_text = ""
        if include_emotions:
            emotions_text = """
    "emotions": ["<detected emotions: joy, sadness, anger, fear, surprise, disgust, trust, anticipation>"],"""

        return f"""Analyze the sentiment/emotional tone of this text.

{scale}

Return as JSON:
{{
    "sentiment": "<overall sentiment>",
    "confidence": <0.0-1.0>,{emotions_text}
    "tone": "<formal/informal/neutral>",
    "subjectivity": "<objective/subjective/mixed>"
}}

Return ONLY valid JSON."""
    else:
        choices = {
            "binary": ["positive", "negative"],
            "ternary": ["positive", "neutral", "negative"],
            "five_point": [
                "very_positive",
                "positive",
                "neutral",
                "negative",
                "very_negative",
            ],
        }
        options = ", ".join(choices.get(granularity, choices["ternary"]))
        return f"""Analyze the sentiment of this text.

{scale}

Return ONLY one of: {options}"""


def build_sentiment_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    granularity = config.get("granularity", "ternary")
    include_emotions = config.get("include_emotions", False)
    return _build_prompt(granularity, include_emotions)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="sentiment",
    display_name="Sentiment",
    description="Analyze text sentiment",
    category="llm",
    icon="face.smiling",
    color="yellow",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=SENTIMENT_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, SENTIMENT_CONFIG),
    default_prompt=_build_prompt("ternary", False),
    prompt_builder=build_sentiment_prompt,
    sort_order=11,
)
async def sentiment(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Analyze text sentiment."""

    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    granularity = inputs.get("granularity", "ternary")
    include_emotions = inputs.get("include_emotions", False)

    prompt = inputs.get("prompt") or _build_prompt(granularity, include_emotions)

    # Use json for detailed, choice for simple
    default_format = (
        "json" if (granularity == "detailed" or include_emotions) else "choice"
    )

    # Build reference values for choice mode
    ref_values = None
    if default_format == "choice":
        choices = {
            "binary": ["positive", "negative"],
            "ternary": ["positive", "neutral", "negative"],
            "five_point": [
                "very_positive",
                "positive",
                "neutral",
                "negative",
                "very_negative",
            ],
        }
        ref_values = {"sentiment": choices.get(granularity, choices["ternary"])}

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
        output_format=inputs.get("output_format", default_format),
        output_options={},
        reference_values=inputs.get("reference_values") or ref_values,
        match_mode=inputs.get("match_mode", "strict"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "sentiment",
    )
