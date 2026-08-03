"""
LLM prompt-building and output-parsing helpers.

Pure text-transformation utilities used by process_text() in llm_base.py:
- Output format constraints and parsing
- Reference value matching
- Context and thinking-mode preambles
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Output Format Handling
# =============================================================================


def build_output_constraint(
    output_format: str,
    output_options: dict | None = None,
) -> str:
    """Build output format instructions for the prompt.

    Args:
        output_format: One of: text, boolean, choice, number, words, list, json
        output_options: Format-specific options:
            - choices: list of valid options (for "choice")
            - max_words: word limit (for "words")
            - max_items: list length (for "list")
            - schema: JSON schema description (for "json")

    Returns:
        Instruction string to append to prompt
    """
    options = output_options or {}

    if output_format == "boolean":
        return "\n\nRespond with exactly: yes or no"

    elif output_format == "choice":
        choices = options.get("choices", [])
        if choices:
            choices_str = ", ".join(f'"{c}"' for c in choices)
            return f"\n\nRespond with exactly one of: {choices_str}"
        return ""

    elif output_format == "number":
        return "\n\nRespond with a single number only."

    elif output_format == "words":
        max_words = options.get("max_words", 50)
        return f"\n\nLimit your response to {max_words} words or fewer."

    elif output_format == "list":
        max_items = options.get("max_items", 10)
        separator = options.get("separator", ",")
        return f"\n\nReturn a {separator}-separated list of up to {max_items} items."

    elif output_format == "json":
        schema = options.get("schema", "")
        if schema:
            return f"\n\nReturn valid JSON matching: {schema}"
        return "\n\nReturn valid JSON only."

    # Default: no constraint
    return ""


def parse_output(
    text: str, output_format: str, output_options: dict | None = None
) -> Any:
    """Parse output according to format.

    Returns the appropriate Python type based on format.
    """
    text = text.strip()
    options = output_options or {}

    if output_format == "boolean":
        lower = text.lower()
        if lower in ("yes", "true", "1"):
            return True
        elif lower in ("no", "false", "0"):
            return False
        return text  # Return original if can't parse

    elif output_format == "number":
        try:
            # Remove common prefixes/suffixes
            cleaned = text.strip("$%").replace(",", "")
            if "." in cleaned:
                return float(cleaned)
            return int(cleaned)
        except ValueError:
            return text

    elif output_format == "list":
        separator = options.get("separator", ",")
        # Split by separator and clean up
        items = [item.strip() for item in text.split(separator)]
        return [item for item in items if item]

    elif output_format == "json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            # Try array
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return text

    # Default: return as-is
    return text


# =============================================================================
# Reference Value Matching
# =============================================================================


def build_reference_section(
    reference_values: dict[str, list] | None = None,
    match_mode: str = "prefer",
) -> str:
    """Build reference value instructions for the prompt.

    Args:
        reference_values: Dict of field names to lists of known values
            e.g., {"names": ["John Smith", "Jane Doe"], "categories": ["A", "B"]}
        match_mode: How to use reference values:
            - "prefer": Prefer these values but allow new ones
            - "strict": Only use these values
            - "inform": Just for context, don't constrain

    Returns:
        Instruction string to add to prompt
    """
    if not reference_values:
        return ""

    sections = []

    for field_name, values in reference_values.items():
        if not values:
            continue

        values_str = ", ".join(f'"{v}"' for v in values[:20])  # Limit to 20
        if len(values) > 20:
            values_str += f" (and {len(values) - 20} more)"

        if match_mode == "strict":
            sections.append(
                f"For {field_name}, only use these exact values: {values_str}"
            )
        elif match_mode == "prefer":
            sections.append(
                f"For {field_name}, prefer these known values if they match: {values_str}"
            )
        else:  # inform
            sections.append(f"Known {field_name} for reference: {values_str}")

    if not sections:
        return ""

    return "\n\nReference values:\n" + "\n".join(f"- {s}" for s in sections)


def match_to_reference(
    value: str,
    reference_values: list[str],
    fuzzy: bool = True,
) -> str | None:
    """Match a value to reference values.

    Args:
        value: The value to match
        reference_values: List of known values
        fuzzy: Whether to use fuzzy matching

    Returns:
        Matched reference value, or None if no match
    """
    if not reference_values:
        return None

    value_lower = value.lower().strip()
    # An empty value has nothing to match — bail out before fuzzy matching,
    # where "" would be a substring of every reference and spuriously match
    # the first one.
    if not value_lower:
        return None

    # Exact match first
    for ref in reference_values:
        if ref.lower().strip() == value_lower:
            return ref

    if not fuzzy:
        return None

    # Fuzzy matching: check if value is contained in or contains a reference.
    # Skip empty references for the same reason ("" is a substring of anything).
    for ref in reference_values:
        ref_lower = ref.lower().strip()
        if ref_lower and (value_lower in ref_lower or ref_lower in value_lower):
            return ref

    return None


def apply_reference_matching(
    result: Any,
    reference_values: dict[str, list] | None,
    fuzzy: bool = True,
) -> Any:
    """Apply reference value matching to a result.

    If result is a dict, tries to match string values against reference lists.
    If result is a list, tries to match each item.

    Args:
        result: The result to process
        reference_values: Dict of field names to reference lists
        fuzzy: Whether to use fuzzy matching

    Returns:
        Result with matched values where applicable
    """
    if not reference_values:
        return result

    if isinstance(result, dict):
        matched = {}
        for key, value in result.items():
            if key in reference_values and isinstance(value, str):
                match = match_to_reference(value, reference_values[key], fuzzy)
                matched[key] = match if match else value
            elif key in reference_values and isinstance(value, list):
                matched[key] = [
                    match_to_reference(v, reference_values[key], fuzzy) or v
                    for v in value
                    if isinstance(v, str)
                ]
            else:
                matched[key] = value
        return matched

    elif isinstance(result, list):
        # Try to match against any reference list
        all_refs = []
        for refs in reference_values.values():
            all_refs.extend(refs)

        return [
            match_to_reference(v, all_refs, fuzzy) or v
            for v in result
            if isinstance(v, str)
        ]

    elif isinstance(result, str):
        # Try to match against all reference values
        for refs in reference_values.values():
            match = match_to_reference(result, refs, fuzzy)
            if match:
                return match

    return result


# =============================================================================
# Context Building
# =============================================================================


THINKING_MODES = ("off", "short", "medium", "long")

# The reasoning tag every thinking-mode preamble asks for. Delimited so a
# downstream stripper can remove it exactly (#4496); the same tag
# `parse_thinking_response` and `transcription_output.strip_reasoning` match.
_THINK_TAG = "think"

_THINKING_DEPTH = {
    "short": (
        "briefly consider the key aspects of this task — a few sentences of "
        "analysis"
    ),
    "medium": (
        "think through this task step by step: consider the context, identify "
        "the key information, and reason about the best approach"
    ),
    "long": (
        "perform a thorough analysis — consider multiple perspectives, evaluate "
        "the evidence carefully, identify potential issues or ambiguities, and "
        "reason through each aspect systematically, taking as much space as you "
        "need"
    ),
}


def build_thinking_preamble(thinking_mode: str = "off") -> str:
    """Build a thinking-mode instruction to prepend to the prompt.

    Thinking mode encourages the model to reason before answering. Higher
    levels produce more thorough reasoning at the cost of more tokens.

    **The reasoning must be delimited** (#4496). This preamble used to end
    "Show your reasoning, then provide your answer", with no delimiter — and it
    is prepended to prompts whose own rules say "output ONLY the transcription.
    No headings, preamble, or commentary". The framework asked for exactly what
    the tool forbade, produced undelimited prose, and nothing downstream could
    tell the two apart. The paleography ensemble then stored 4,518 characters
    beginning "Step-by-step reasoning:" in an artifact typed `transcription`,
    on every node, green.

    Asking for `<think>...</think>` costs the model nothing and makes the
    reasoning machine-separable, so `strip_reasoning` can remove it exactly
    rather than a heuristic guessing where prose stops.

    Raises:
        ValueError: for a mode outside ``THINKING_MODES``. This used to return
            "" — silently no reasoning at all. The paleography ensemble asked
            for ``thinking_mode: "high"`` on its two review nodes and got
            nothing, which is why the nodes declaring the *deepest* thinking
            were the *least* polluted. A config value that does nothing must
            not read as a config value that works.
    """
    if thinking_mode == "off":
        return ""

    depth = _THINKING_DEPTH.get(thinking_mode)
    if depth is None:
        raise ValueError(
            f"Unknown thinking_mode {thinking_mode!r}; expected one of "
            f"{', '.join(THINKING_MODES)}"
        )

    return (
        f"Before answering, {depth}.\n"
        f"Put ALL of that reasoning inside <{_THINK_TAG}>...</{_THINK_TAG}> tags. "
        f"After the closing </{_THINK_TAG}> tag, output your answer and nothing "
        f"else — no reasoning, no headings, no preamble, no commentary, no notes "
        f"about what you decided.\n\n"
    )


def build_context_section(
    context: str | None = None,
    input_metadata: dict | None = None,
    previous_outputs: dict | None = None,
) -> str:
    """Build context section for prompt.

    Args:
        context: Previous text/transcription
        input_metadata: Existing metadata to include
        previous_outputs: Dict of previous tool outputs (e.g., {"transcribe": "...", "describe": "..."})

    Returns:
        Context section to prepend to prompt
    """
    parts = []

    if input_metadata:
        meta_str = json.dumps(input_metadata, indent=2)
        parts.append(f"Document metadata:\n{meta_str}")

    if previous_outputs:
        for tool_name, output in previous_outputs.items():
            if output:
                parts.append(f"Previous {tool_name} result:\n{output}")

    if context:
        parts.append(f"Document text:\n{context}")

    if not parts:
        return ""

    return f"""Context:
{chr(10).join(parts)}

---

"""
