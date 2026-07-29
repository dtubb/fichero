"""Text reflow/cleanup tool — join soft-wrapped lines and preserve paragraph structure."""

from __future__ import annotations

import re
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State

# ── heuristic patterns ─────────────────────────────────────────────────────────

_SENTENCE_END = re.compile(r"[.!?:;…]\s*$")
_HYPHEN_BREAK = re.compile(r"(\w)-\s*\n\s*(\w)")
_HYPHEN_WITH_SPACE = re.compile(r"(\w)-\s+([a-z])")
_LEADING_WHITESPACE = re.compile(r"^(\s+)")


def _is_paragraph_boundary(line: str, next_line: str | None = None) -> bool:
    """Check if a line ends a paragraph (sentence-end, blank, indented, or very short)."""
    stripped = line.rstrip()

    # Blank lines always end paragraphs
    if not stripped:
        return True

    # Sentence-ending punctuation (with potential trailing whitespace)
    if _SENTENCE_END.search(stripped):
        return True

    # Very short lines (< 40 chars) suggest a natural break
    if len(stripped) < 40:
        return True

    # If next line exists and is indented, current line ends paragraph
    if next_line is not None:
        if _LEADING_WHITESPACE.match(next_line.lstrip()) and next_line.strip():
            return True

    return False


def _dehyphenate(text: str) -> str:
    """Join hyphenated line-break splits: 'exam-\\nple' → 'example' and 'exam- ple' → 'example'."""
    # First handle hyphens with newlines and surrounding whitespace
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    # Then handle hyphens with spaces (from joined lines)
    text = _HYPHEN_WITH_SPACE.sub(r"\1\2", text)
    return text


def _should_join_lines(current_line: str, next_line: str) -> bool:
    """Determine if two lines should be joined (soft-wrap heuristic).

    Join if current line:
    - Is not a blank line
    - Does NOT end with sentence-boundary punctuation
    - Is not very short (unless it's a continuation)
    - The next line is not blank
    """
    if not current_line.strip():
        return False

    if not next_line.strip():
        return False

    stripped_current = current_line.rstrip()

    # Don't join if current line ends with sentence punctuation
    if _SENTENCE_END.search(stripped_current):
        return False

    # Don't join if current line is too short (likely intentional break)
    if len(stripped_current) < 20:
        return False

    return True


def _reflow_text(text: str, preserve_indentation: bool = True) -> str:
    """Join soft-wrapped lines within paragraphs while preserving paragraph breaks.

    Logic:
    1. Split text into lines
    2. For each line, check if it should join with the next line
    3. A line joins if it doesn't end a paragraph (no sentence-end, not blank, etc.)
    4. Preserve blank lines as hard paragraph breaks
    5. De-hyphenate words split by line breaks
    """
    if not text.strip():
        return ""

    lines = text.split("\n")
    result = []
    i = 0

    while i < len(lines):
        current_line = lines[i]
        stripped_current = current_line.rstrip()

        # Preserve blank lines
        if not stripped_current:
            result.append("")
            i += 1
            continue

        # Accumulate lines that should be joined
        accumulated = [stripped_current]
        j = i + 1

        while j < len(lines):
            next_line = lines[j]
            stripped_next = next_line.rstrip()

            # Stop at blank line (hard paragraph break)
            if not stripped_next:
                break

            # Check if we should join this line
            if _should_join_lines(accumulated[-1], stripped_next):
                accumulated.append(stripped_next)
                j += 1
            else:
                # This line starts a new paragraph
                break

        # Join accumulated lines with a space
        joined = " ".join(accumulated)
        result.append(joined)
        i = j

    # De-hyphenate at the end (now that lines are joined)
    final_text = "\n".join(result)
    final_text = _dehyphenate(final_text)

    return final_text


# ── ai-pass refinement ────────────────────────────────────────────────────────

_REFLOW_AI_INSTRUCTIONS = """You are a text refinement specialist for OCR and hard-wrapped documents.

The user has provided text that has already been reflowed (soft-wrapped lines joined, paragraph breaks preserved).

Your task: Review the reflowed text for any remaining issues:
1. Incomplete word joins (e.g., "extra ordinary" should be "extraordinary")
2. Awkward spacing or formatting artifacts
3. Obvious OCR errors that contradict common sense
4. Inconsistent hyphenation or word breaks

Make minimal, targeted corrections only. Preserve:
- Paragraph structure and blank lines
- Original spelling and vocabulary (don't "fix" archaic or regional terms)
- Any [ilegible] / [uncertain] markers, exactly as written
- Quotations and emphasized text as-is
- Proper nouns and unusual capitalization

Return the refined text only, with no explanations."""


async def _refine_with_llm(text: str, llm_config: LLMConfig) -> str:
    """Optional AI pass to refine reflowed text (catches edge cases the heuristics miss)."""
    if not llm_config or not llm_config.provider:
        return text

    try:
        from fichero_server.llm import call_llm_with_cache

        response = await call_llm_with_cache(
            prompt=f"{_REFLOW_AI_INSTRUCTIONS}\n\n---\n\n{text}",
            llm_config=llm_config,
            cache_key=f"text_reflow_refine_{hash(text) % (10**9)}",
        )
        return response.strip() if response else text
    except Exception:
        # If LLM call fails, return the heuristic result
        return text


# ── config schema ──────────────────────────────────────────────────────────────

TEXT_REFLOW_CONFIG = {
    "use_ai_refinement": {
        "type": "boolean",
        "default": False,
        "description": (
            "Optional: Call LLM to refine reflowed text and catch edge-case word joins. "
            "Disabled by default; programmatic reflow is sufficient for most cases."
        ),
    },
}

# ── tool ───────────────────────────────────────────────────────────────────────


@register_tool(
    name="text_reflow",
    display_name="Text Reflow",
    description=(
        "Join soft-wrapped lines within paragraphs, preserve paragraph structure, "
        "and de-hyphenate words split across line breaks. "
        "Optional AI refinement pass available for edge-case word joins."
    ),
    category="transform",
    icon="text.alignleft",
    color="purple",
    uses_llm=True,
    supports_batch=True,
    input_ports=[
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Hard-wrapped OCR or scanned text to reflow.",
        ),
    ],
    output_ports=[
        PortDef(
            id="text",
            name="Text",
            port_type="output",
            data_type=DataType.TEXT,
            description="Reflowed text with preserved paragraph structure.",
        ),
    ],
    config_schema=TEXT_REFLOW_CONFIG,
    sort_order=27,
)
async def text_reflow(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Reflow hard-wrapped text while preserving paragraph breaks.

    Default: pure programmatic heuristics (fast, no LLM required).
    Optional: AI refinement pass to catch edge-case word joins (disabled by default).
    """
    text: str = inputs.get("text") or ""

    if not text:
        return {"text": ""}

    # Programmatic reflow (always)
    reflowed = _reflow_text(text)

    # Optional AI refinement pass
    config = inputs.get("_config") or {}
    use_ai = bool(config.get("use_ai_refinement", False))

    if use_ai and llm_config:
        reflowed = await _refine_with_llm(reflowed, llm_config)

    return {"text": reflowed.strip()}
