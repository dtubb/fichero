"""
Questions Tool

Generates questions from text (study, quiz, comprehension).
Inherits from llm_base.py - returns list of questions.
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
    artifact_type="questions",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field="questions",
)

QUESTIONS_CONFIG = {
    "question_type": {
        "type": "string",
        "enum": ["factual", "analytical", "discussion", "comprehension", "mixed"],
        "default": "mixed",
        "description": "Question type",
    },
    "count": {
        "type": "integer",
        "default": 10,
        "description": "Number of questions",
    },
}

QUESTIONS_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Source text",
        )
    ],
    BASE_INPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(question_type: str, count: int) -> str:
    """Build the question generation prompt."""
    type_instructions = {
        "factual": "Generate factual recall questions (who, what, when, where). These should have clear, specific answers found in the text.",
        "analytical": "Generate analytical questions that require reasoning, comparison, or inference from the text.",
        "discussion": "Generate open-ended discussion questions that encourage deeper thinking about themes and implications.",
        "comprehension": "Generate reading comprehension questions that test understanding of the main ideas and details.",
        "mixed": "Generate a mix of factual, analytical, and discussion questions.",
    }

    instruction = type_instructions.get(question_type, type_instructions["mixed"])

    return f"""Generate {count} questions based on this text.

{instruction}

Rules:
- Questions should be answerable from the provided text
- Vary difficulty levels
- Cover different aspects/sections of the text
- Be specific and clear

Return as JSON:
{{
    "questions": [
        {{
            "question": "<the question>",
            "type": "<factual/analytical/discussion>",
            "difficulty": "<easy/medium/hard>"
        }}
    ]
}}

Return ONLY valid JSON."""


def build_questions_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    question_type = config.get("question_type", "mixed")
    count = config.get("count", 10)
    return _build_prompt(question_type, count)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="questions",
    display_name="Questions",
    description="Generate questions from text",
    category="llm",
    icon="questionmark.bubble",
    color="orange",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=QUESTIONS_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, QUESTIONS_CONFIG),
    default_prompt=_build_prompt("mixed", 10),
    prompt_builder=build_questions_prompt,
    sort_order=13,
)
async def questions(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Generate questions from text."""

    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    question_type = inputs.get("question_type", "mixed")
    count = inputs.get("count", 10)

    prompt = inputs.get("prompt") or _build_prompt(question_type, count)

    return await process_text(
        text=text,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        documents=documents,
        temperature=inputs.get("temperature", 0.5),
        max_tokens=inputs.get("max_tokens", 2048),
        output_format=inputs.get("output_format", "json"),
        output_options={},
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field"),
    )
