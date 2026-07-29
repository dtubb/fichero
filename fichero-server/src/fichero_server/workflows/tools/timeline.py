"""
Timeline Tool

Creates a chronological timeline from text/entities.
Maps to the "timeline" step in catalogue pipelines.
Inherits from llm_base.py - returns JSON with dated events.
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
    artifact_type="timeline",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field="timeline",
)

TIMELINE_CONFIG = {
    "date_format": {
        "type": "string",
        "enum": ["iso", "natural", "year_only"],
        "default": "iso",
        "description": "Date format",
    },
    "max_events": {
        "type": "integer",
        "default": 50,
        "description": "Max events",
    },
}

TIMELINE_INPUT_PORTS = merge_ports(
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


def _build_prompt(date_format: str, max_events: int) -> str:
    """Build the timeline prompt."""
    format_text = {
        "iso": "Use ISO format (YYYY-MM-DD) when possible. Use YYYY-MM or YYYY if day/month unknown.",
        "natural": "Use natural language dates (e.g., 'March 15, 1847', 'Summer 1920').",
        "year_only": "Use only years (YYYY format).",
    }.get(date_format, "Use ISO format (YYYY-MM-DD) when possible.")

    return f"""Create a chronological timeline of events from the provided text.

Instructions:
- Identify all datable events, actions, or occurrences
- Order them chronologically
- Maximum {max_events} events
- {format_text}
- Describe each event concisely (one sentence)
- Do NOT include page numbers

Return as JSON:
{{
    "timeline": [
        {{
            "date": "<date in specified format>",
            "event": "<concise event description>"
        }}
    ],
    "date_range": {{
        "earliest": "<earliest date>",
        "latest": "<latest date>"
    }},
    "total_events": <number>
}}

Return ONLY valid JSON."""


def build_timeline_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    date_format = config.get("date_format", "iso")
    max_events = config.get("max_events", 50)
    return _build_prompt(date_format, max_events)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="timeline",
    display_name="Timeline",
    description="Create chronological timeline",
    category="llm",
    icon="calendar.day.timeline.left",
    color="blue",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=TIMELINE_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, TIMELINE_CONFIG),
    default_prompt=_build_prompt("iso", 50),
    prompt_builder=build_timeline_prompt,
    sort_order=7,
)
async def timeline(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Create chronological timeline from text."""

    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    date_format = inputs.get("date_format", "iso")
    max_events = inputs.get("max_events", 50)

    prompt = inputs.get("prompt") or _build_prompt(date_format, max_events)

    return await process_text(
        text=text,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        documents=documents,
        temperature=inputs.get("temperature", 0.2),
        max_tokens=inputs.get("max_tokens", 4096),
        output_format=inputs.get("output_format", "json"),
        output_options={},
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "timeline",
    )
