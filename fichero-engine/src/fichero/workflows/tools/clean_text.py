"""
Clean Up Text Tool

Cleans extracted or transcribed text with an LLM: fixes OCR
misrecognitions, normalizes whitespace and line breaks, rejoins
hyphenated line splits, and strips page headers/footers, page numbers,
and scanning artefacts — while preserving the original meaning and
wording.

Inherits from llm_base.py — transforms input text. The cleanup
behaviour is driven entirely by user-editable config:

  * Per-aspect toggles compose the default instruction (`fix_ocr`,
    `normalize_whitespace`, `fix_hyphenation`, `strip_artifacts`).
  * The full prompt is overridable via the BASE_CONFIG_SCHEMA `prompt`
    field, and the model via `provider_name` / `model_name`.

Nothing here is a hard-coded, non-editable string literal: the default
prompt is only a default. See feedback_user_editable_not_hardcoded.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.llm_base import (
    BASE_INPUT_PORTS,
    BASE_OUTPUT_PORTS,
    BASE_CONFIG_SCHEMA,
    merge_config_schema,
    merge_ports,
    LLMToolConfig,
    process_text,
)
from fichero.llm import LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = LLMToolConfig(
    artifact_type="clean_text",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field="clean_text",
)

CLEAN_TEXT_CONFIG = {
    "fix_ocr": {
        "type": "boolean",
        "default": True,
        "description": "Fix obvious OCR misrecognitions (e.g. rn→m, 0→o)",
    },
    "normalize_whitespace": {
        "type": "boolean",
        "default": True,
        "description": "Collapse stray whitespace and runs of blank lines",
    },
    "fix_hyphenation": {
        "type": "boolean",
        "default": True,
        "description": "Rejoin words split across line breaks by hyphens",
    },
    "strip_artifacts": {
        "type": "boolean",
        "default": True,
        "description": (
            "Remove page headers/footers, page numbers, and scanning "
            "stamps that are not part of the document body"
        ),
    },
}

CLEAN_TEXT_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Extracted or transcribed text to clean.",
        )
    ],
    BASE_INPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================

def _build_prompt(
    fix_ocr: bool,
    normalize_whitespace: bool,
    fix_hyphenation: bool,
    strip_artifacts: bool,
) -> str:
    """Build the cleanup prompt from the enabled aspect toggles.

    Each toggle contributes one instruction line. The meaning-preservation
    guardrails are always present so cleanup never rewrites or summarizes.
    """
    aspects: list[str] = []
    if fix_ocr:
        aspects.append(
            "- Correct obvious OCR misrecognitions (e.g. 'rn'→'m', '0'→'o', "
            "'l'→'I') only when the intended word is unambiguous."
        )
    if fix_hyphenation:
        aspects.append(
            "- Rejoin words split across line breaks by a trailing hyphen "
            "(e.g. 'exam-\\nple' → 'example')."
        )
    if normalize_whitespace:
        aspects.append(
            "- Normalize whitespace: collapse repeated spaces, trim trailing "
            "spaces, and reduce runs of blank lines to a single blank line. "
            "Keep paragraph breaks."
        )
    if strip_artifacts:
        aspects.append(
            "- Remove text that is not part of the document body: running "
            "page headers/footers, standalone page numbers, and library or "
            "date stamps."
        )

    if not aspects:
        # Every aspect disabled — still a meaningful (minimal) clean-up:
        # tidy whitespace without touching content.
        aspects.append("- Tidy obvious whitespace issues only.")

    aspect_block = "\n".join(aspects)

    return f"""Clean up the following text. Apply ONLY these fixes:

{aspect_block}

Preserve the original meaning, wording, spelling, capitalisation, and the
order of the content. Do NOT summarize, paraphrase, translate, reorder, or
add any new information or commentary.

Output ONLY the cleaned text, with no preamble or explanation."""


def build_clean_text_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI for live preview/editing)."""
    return _build_prompt(
        fix_ocr=bool(config.get("fix_ocr", True)),
        normalize_whitespace=bool(config.get("normalize_whitespace", True)),
        fix_hyphenation=bool(config.get("fix_hyphenation", True)),
        strip_artifacts=bool(config.get("strip_artifacts", True)),
    )


# =============================================================================
# Tool
# =============================================================================

@register_tool(
    name="clean_text",
    display_name="Clean Up Text",
    description=(
        "Clean extracted or transcribed text: fix OCR noise, normalize "
        "whitespace and hyphenation, strip page headers/footers and "
        "scanning artefacts — preserving the original meaning."
    ),
    category="llm",
    icon="wand.and.sparkles",
    color="mint",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=CLEAN_TEXT_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, CLEAN_TEXT_CONFIG),
    default_prompt=_build_prompt(True, True, True, True),
    prompt_builder=build_clean_text_prompt,
    sort_order=12,
)
async def clean_text(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Clean up extracted/transcribed text via an LLM."""

    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # User-editable prompt: explicit override wins, else build from toggles.
    prompt = inputs.get("prompt") or build_clean_text_prompt(inputs)

    return await process_text(
        text=text,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        documents=documents,
        # Cleanup must be conservative — low temperature by default.
        temperature=inputs.get("temperature", 0.2),
        max_tokens=inputs.get("max_tokens", 4096),
        output_format=inputs.get("output_format", "text"),
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field"),
    )
