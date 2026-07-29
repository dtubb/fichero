"""OCR cleanup workflow tool — dehyphenate, rejoin columns, strip library stamps."""

from __future__ import annotations

import re
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State

# ── stamp patterns ─────────────────────────────────────────────────────────────
# Common library ownership stamps and watermarks found in scanned documents.
_STAMP_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE | re.MULTILINE)
    for p in [
        r"^\s*LIBRARY OF CONGRESS\s*$",
        r"^\s*BIBLIOTH[EÈ]QUE\s.*$",
        r"^\s*BRITISH LIBRARY\s*$",
        r"^\s*BODLEIAN LIBRARY\s*$",
        r"^\s*UNIVERSITY LIBRARY\s*$",
        r"^\s*PUBLIC LIBRARY\s*$",
        r"^\s*NATIONAL LIBRARY\s.*$",
        r"^\s*RETURNED\s*$",
        r"^\s*OVERDUE\s*$",
        r"^\s*DISCARD(?:ED)?\s*$",
        r"^\s*WITHDRAWN\s*$",
        r"^\s*EX LIBRIS\s.*$",
        r"^\s*PROPERTY OF\s.*$",
        r"^\s*Date\s+Due\s*$",
        r"^\s*DUE DATE.*$",
        r"^\s*[A-Z]{3}\s+\d{1,2}\s+\d{4}\s*$",   # "SEP 12 1987"
        r"^\s*[A-Z]{3}\s+\d{1,2}\s+'?\d{2}\s*$",  # "MAR 3 '92"
        r"^\s*\d{1,2}\s+[A-Z]{3}\s+\d{2,4}\s*$",  # "12 JAN 1994"
    ]
]

# ── config schema ──────────────────────────────────────────────────────────────
OCR_CLEANUP_CONFIG = {
    "dehyphenate": {
        "type": "boolean",
        "default": True,
        "description": "Join words split by end-of-line hyphens",
    },
    "rejoin_columns": {
        "type": "boolean",
        "default": True,
        "description": "Heuristically rejoin short lines from multi-column OCR layout",
    },
    "strip_stamps": {
        "type": "boolean",
        "default": True,
        "description": "Remove common library ownership stamps and date stamps",
    },
    "min_line_length": {
        "type": "integer",
        "default": 60,
        "description": (
            "Lines shorter than this are candidates for column-rejoin "
            "(only applies when rejoin_columns is true)"
        ),
    },
}

# ── helpers ────────────────────────────────────────────────────────────────────

_SENTENCE_END = re.compile(r"[.!?:;]\s*$")
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")


def _dehyphenate(text: str) -> str:
    """Join hyphenated line-break splits: 'exam-\\nple' → 'example'."""
    return _HYPHEN_BREAK.sub(r"\1\2", text)


def _strip_stamps(text: str) -> str:
    for pat in _STAMP_PATTERNS:
        text = pat.sub("", text)
    # Collapse runs of blank lines left by stamp removal
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _rejoin_columns(text: str, min_line_length: int) -> str:
    """Heuristically rejoin lines that look like broken multi-column OCR text.

    A line is a rejoin candidate when it is shorter than *min_line_length*,
    does not end with sentence-boundary punctuation, and is followed by a
    non-blank line.  When the condition holds the next line is appended with
    a space instead of a newline.  Blank lines are always preserved as
    paragraph separators.
    """
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].rstrip()
        # Blank lines are always kept as paragraph separators
        if not stripped:
            i += 1
            continue
        if (
            len(stripped) < min_line_length
            and not _SENTENCE_END.search(stripped)
            and i + 1 < len(lines)
            and lines[i + 1].strip()  # next line is not blank
        ):
            # Merge into the next element so subsequent passes can chain
            lines[i + 1] = stripped + " " + lines[i + 1].lstrip()
            lines[i] = ""  # blank out this line
        i += 1
    return "\n".join(line for line in lines if line != "" or True)


# ── tool ───────────────────────────────────────────────────────────────────────


@register_tool(
    name="ocr_cleanup",
    display_name="OCR Cleanup",
    description=(
        "Fix common OCR artefacts: dehyphenate line-break splits, "
        "rejoin multi-column text, strip library ownership stamps."
    ),
    category="transform",
    icon="wand.and.stars.inverse",
    color="teal",
    uses_llm=False,
    supports_batch=True,
    input_ports=[
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Raw OCR text to clean.",
        ),
    ],
    output_ports=[
        PortDef(
            id="text",
            name="Text",
            port_type="output",
            data_type=DataType.TEXT,
            description="Cleaned text.",
        ),
    ],
    config_schema=OCR_CLEANUP_CONFIG,
    sort_order=26,
)
async def ocr_cleanup(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Fix common OCR artefacts in post-Vision text."""
    config = inputs.get("_config") or {}
    text: str = inputs.get("text") or ""

    if not text:
        return {"text": ""}

    dehyphenate: bool = bool(config.get("dehyphenate", True))
    rejoin_cols: bool = bool(config.get("rejoin_columns", True))
    strip_stamps: bool = bool(config.get("strip_stamps", True))
    min_line_length: int = int(config.get("min_line_length", 60))

    if strip_stamps:
        text = _strip_stamps(text)
    if dehyphenate:
        text = _dehyphenate(text)
    if rejoin_cols:
        text = _rejoin_columns(text, min_line_length)

    return {"text": text.strip()}
