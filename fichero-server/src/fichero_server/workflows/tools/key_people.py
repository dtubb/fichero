"""
Key People Tool

Identifies the most important people from text/entities.
Maps to the "key_people_and_tags" step in catalogue pipelines.
Inherits from llm_base.py - returns JSON with people and roles.
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
    artifact_type="key_people",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field="key_people",
)

KEY_PEOPLE_CONFIG = {
    "max_people": {
        "type": "integer",
        "default": 10,
        "description": "Max people to identify",
    },
    "include_context": {
        "type": "boolean",
        "default": True,
        "description": "Include role/context",
    },
}

KEY_PEOPLE_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Source text or entity data",
        )
    ],
    BASE_INPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(max_people: int, include_context: bool) -> str:
    """Build the key people prompt."""
    context_text = ""
    if include_context:
        context_text = """
For each person, include:
- Their role or title if mentioned
- Their importance to the narrative (what they did)
- Relationships to other key people"""

    return f"""Identify the {max_people} most important people mentioned in this text.

Rank them by importance to the overall narrative/content.
{context_text}

Return as JSON:
{{
    "key_people": [
        {{
            "name": "<full name>",
            "role": "<title or role>",
            "importance": "<why they are important>",
            "alternative_names": ["<any other names/spellings used>"]
        }}
    ],
    "total_people_found": <total people mentioned in text>
}}

Return ONLY valid JSON."""


def build_key_people_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    max_people = config.get("max_people", 10)
    include_context = config.get("include_context", True)
    return _build_prompt(max_people, include_context)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="key_people",
    display_name="Key People",
    description="Identify important people",
    category="llm",
    icon="person.3",
    color="blue",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=KEY_PEOPLE_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, KEY_PEOPLE_CONFIG),
    default_prompt=_build_prompt(10, True),
    prompt_builder=build_key_people_prompt,
    sort_order=8,
)
async def key_people(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Identify most important people from text."""

    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    max_people = inputs.get("max_people", 10)
    include_context = inputs.get("include_context", True)

    prompt = inputs.get("prompt") or _build_prompt(max_people, include_context)

    return await process_text(
        text=text,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        documents=documents,
        temperature=inputs.get("temperature", 0.2),
        max_tokens=inputs.get("max_tokens", 2048),
        output_format=inputs.get("output_format", "json"),
        output_options={},
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "key_people",
    )
