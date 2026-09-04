"""
Table Extract Tool

Specialized table extraction from images.
Inherits from vision_base.py - returns structured table data.
"""

from __future__ import annotations

import logging
import re
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
    # Same class as analyze (2026-09-03): table_extract output is
    # prompt-shaped (Extract Table vs Accounts → Spreadsheet ask for very
    # different tables), but skip-if-done matches on artifact_type only, so
    # one preset's table silently satisfied the other. The node cache still
    # dedupes identical re-runs via the config-keyed cache key.
    skip_if_artifact_exists=False,
)

TABLE_CONFIG = {
    "output_style": {
        "type": "string",
        "enum": ["csv", "json_rows", "json_columns", "markdown"],
        # CSV by default: a ledger page extracted as a table is something you
        # paste into a spreadsheet. json_rows keeps the structure for a future
        # grid renderer and stays one config change away.
        "default": "csv",
        "description": "Table output format",
    },
    "include_headers": {
        "type": "boolean",
        "default": True,
        "description": "Detect header row",
    },
}


# =============================================================================
# "There is no table here" — a first-class answer
# =============================================================================

# The sentinel the model is told to emit for a page with no table. Checked
# case-insensitively against the whole (fence-stripped) reply, so a model that
# answers with nothing else cannot be mistaken for one that answered with data.
NO_TABLE_SENTINEL = "NO TABLE"

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n(.*?)\n?```\s*$", re.DOTALL)

# Instructions appended to every style prompt. Without them the prompt only
# ever COMMANDS extraction, and a model handed a page with no table has no way
# to say so — it answers the question it was asked, with whatever is closest to
# a table on the page.
_NO_TABLE_RULES = f"""
If the image contains no table, output exactly {NO_TABLE_SENTINEL} and nothing
else. That is a correct and complete answer — never invent rows to fill the
reply.

A table is data laid out in rows and columns as part of the DOCUMENT. It is not
a measuring ruler or scale bar laid beside the page, a colour calibration
chart, a strip of page or folio numbers, a margin, or any other photographic
furniture that belongs to the act of scanning rather than to the document."""


def with_no_table_rules(prompt: str) -> str:
    """Append the "there may be no table" rules to any prompt, once.

    Applied to a CUSTOM prompt too, not just the built-in ones. 'Accounts →
    Spreadsheet (CSV)' ships its own paleographer-flavoured prompt and would
    otherwise be the one table preset with no way to answer "nothing here" —
    which is exactly the preset most likely to meet a page of prose. Same shape
    as the translate fidelity block: a rule that must hold for every run rides
    with every prompt rather than being remembered per preset.
    """
    text = (prompt or "").rstrip()
    if NO_TABLE_SENTINEL in text:
        return text
    return f"{text}\n{_NO_TABLE_RULES}"


def _strip_fence(text: str) -> str:
    """Drop a whole-output code fence, which models add despite instructions."""
    match = _FENCE_RE.match((text or "").strip())
    return match.group(1).strip() if match else (text or "").strip()


def _looks_like_a_measuring_scale(rows: list[str]) -> bool:
    """True for a single column of consecutive integers — i.e. a ruler.

    The failure this exists for (2026-09-04 local-model sweep): run Extract
    Table on a manuscript page that has no table, with a centimetre ruler lying
    in the scan margin, and the model returned a table of 0,1,2 … 30. It read
    the ruler. The perception is reasonable; the output is fabricated data
    entering an archive whose entire value is that its contents are attested.

    ponytail: a deliberately narrow signature — one column, at least six rows,
    every value an integer, each one greater than the last. A real one-column
    tally (the Marshall dredge counts) is not consecutive and is not caught. If
    fabrication shows up in a shape this misses, the answer is a better prompt
    or a provenance check against the page's own text, not more arithmetic here.
    """
    if len(rows) < 6:
        return False

    values: list[int] = []
    for row in rows:
        cells = [cell.strip().strip('"') for cell in row.split(",")]
        cells = [cell for cell in cells if cell]
        if len(cells) != 1:
            return False
        try:
            values.append(int(cells[0]))
        except ValueError:
            return False

    return all(later == earlier + 1 for earlier, later in zip(values, values[1:]))


def validate_extracted_table(text: str, output_style: str) -> str:
    """Refuse to save a table the page does not have (#R-12).

    Raises rather than returning empty, because `process_vision` treats a raise
    from this hook as a per-file refusal WITH ITS REASON and saves nothing —
    the same seam Convert uses to refuse malformed SVG (#4329). A folder where
    three pages in ten carry tables therefore yields three tables and seven
    recorded "no table here", instead of ten tables of which seven are fiction.
    """
    out = _strip_fence(text)

    if not out:
        raise ValueError(
            "Extract Table produced no output for this page; refusing to save "
            "an empty table."
        )

    if out.upper() == NO_TABLE_SENTINEL:
        raise ValueError(
            "No table on this page. Extract Table reads data laid out in rows "
            "and columns; this page has none, so nothing was saved."
        )

    if output_style == "csv":
        rows = [line for line in out.splitlines() if line.strip()]
        if _looks_like_a_measuring_scale(rows):
            raise ValueError(
                "Extract Table returned a single column of consecutive numbers "
                "— the signature of a measuring ruler or scale bar photographed "
                "beside the document, not of a table in it. Refusing to save "
                "fabricated rows. If this page really does hold a numbered "
                "column, transcribe it instead."
            )

    return out


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
- Wrap EVERY field in double quotes, without exception. A ledger column full
  of dates and comma'd lists produces ragged rows the moment quoting is
  optional, and the model is the only place that can get it right — nothing
  downstream can recover the column boundaries afterwards.
- Escape a literal double quote inside a field by doubling it ("")
- Every row must have exactly the same number of fields as the header row;
  emit "" for an empty cell rather than dropping it
- First row is the header row if one is visible
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

    instruction = style_instructions.get(output_style, style_instructions["json_rows"])
    return with_no_table_rules(instruction)


def build_table_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    output_style = config.get("output_style", "csv")
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
    # The same fact TOOL_CONFIG already states as supports_apple_vision=False,
    # said where the PREFLIGHT can read it (Daniel, 2026-09-01: "Apple Vision
    # → CSV failed"). This tool asks a model to lay a page out as CSV/HTML/
    # Markdown; Apple Vision performs OCR and ignores the prompt, so on the
    # keyless factory default the run was dispatched, priced and only then
    # refused. Refusing before it starts is the same verdict, cheaper.
    requires_generative_model=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, TABLE_CONFIG),
    default_prompt=_build_prompt("csv", True),
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

    output_style = inputs.get("output_style", "csv")
    include_headers = inputs.get("include_headers", True)

    # A custom prompt gets the rules too — see with_no_table_rules.
    prompt = with_no_table_rules(
        inputs.get("prompt") or _build_prompt(output_style, include_headers)
    )

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
        postprocess_text=lambda t: validate_extracted_table(t, output_style),
    )
