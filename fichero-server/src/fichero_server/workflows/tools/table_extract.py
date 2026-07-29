"""
Table Extract Tool

Specialized table extraction from images.
Inherits from vision_base.py - returns structured table data.
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
    artifact_type="table",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="table",
)

TABLE_CONFIG = {
    "output_style": {
        "type": "string",
        "enum": ["json_rows", "json_columns", "csv", "markdown"],
        "default": "json_rows",
        "description": "Table output format",
    },
    "include_headers": {
        "type": "boolean",
        "default": True,
        "description": "Detect header row",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(output_style: str, include_headers: bool) -> str:
    """Build the table extraction prompt."""
    header_text = (
        "The first row contains column headers."
        if include_headers
        else "There may not be a distinct header row."
    )

    style_instructions = {
        "json_rows": f"""Extract the table data from this image.

{header_text}

Return as JSON with row-based structure:
{{
    "headers": ["col1", "col2", ...],
    "rows": [
        ["value1", "value2", ...],
        ...
    ],
    "row_count": <number>,
    "column_count": <number>
}}

Return ONLY valid JSON.""",
        "json_columns": f"""Extract the table data from this image.

{header_text}

Return as JSON with column-based structure:
{{
    "columns": {{
        "<column_name>": ["value1", "value2", ...],
        ...
    }},
    "row_count": <number>,
    "column_count": <number>
}}

Return ONLY valid JSON.""",
        "csv": f"""Extract the table data from this image as CSV format.

{header_text}

Rules:
- Use comma as separator
- Quote fields containing commas or newlines
- First row should be headers if visible
- One row per line

Return ONLY the CSV content, no code fences or explanations.""",
        "markdown": f"""Extract the table data from this image as a Markdown table.

{header_text}

Use proper Markdown table syntax:
| Header 1 | Header 2 | ... |
|----------|----------|-----|
| Value 1  | Value 2  | ... |

Return ONLY the Markdown table, no explanations.""",
    }

    return style_instructions.get(output_style, style_instructions["json_rows"])


def build_table_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    output_style = config.get("output_style", "json_rows")
    include_headers = config.get("include_headers", True)
    return _build_prompt(output_style, include_headers)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="table_extract",
    display_name="Table",
    description="Extract tables from images",
    category="vision",
    icon="tablecells",
    color="brown",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, TABLE_CONFIG),
    default_prompt=_build_prompt("json_rows", True),
    prompt_builder=build_table_prompt,
    sort_order=26,
)
async def table_extract(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Extract table data from images."""

    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    output_style = inputs.get("output_style", "json_rows")
    include_headers = inputs.get("include_headers", True)

    prompt = inputs.get("prompt") or _build_prompt(output_style, include_headers)

    # Use text output for CSV/markdown, json for structured
    default_format = "text" if output_style in ("csv", "markdown") else "json"

    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        vision_mode="llm",
        max_image_dimension=inputs.get("max_image_dimension", 2048),
        temperature=inputs.get("temperature", 0.1),
        max_tokens=inputs.get("max_tokens", 4096),
        output_format=inputs.get("output_format", default_format),
        output_options={},
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field"),
    )
