"""
Translate Review tool (#926) — AI double-check of a draft translation.

Second pass of the multi-step translation workflow. Takes a draft
translation (via the required ``text`` port) plus the ORIGINAL source text
(via the ``context`` port), re-shows both to the LLM, and produces a
CORRECTED translation that is faithful to the source — catching
mistranslations, omissions, additions, and altered names/dates the
one-shot pass missed.

Mirrors the transcribe / transcribe_review split in the vision domain: a
distinct artifact_type ("translation_review") so the reviewed result has
its own cache slot and the inspector can show draft vs. reviewed.

Inherits from llm_base.py — transforms input text via ``process_text``.
``build_context_section`` renders the source under "Document text:" in the
system channel, and the draft translation is the user message; the review
prompt instructs the model to compare them.

The target/source language, model, and full prompt are user-editable
config — nothing hard-coded. See feedback_user_editable_not_hardcoded.
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
from fichero.workflows.tools.text_translate import DEFAULT_TARGET_LANGUAGE
from fichero.llm import LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = LLMToolConfig(
    artifact_type="translation_review",
    update_page_content=False,
    trigger_embedding=True,
    embedding_scope="translation",
    metadata_field="translation_review",
)

TEXT_TRANSLATE_REVIEW_CONFIG = {
    "target_language": {
        "type": "string",
        "default": DEFAULT_TARGET_LANGUAGE,
        "description": "Language the translation should be in (e.g. English)",
        "x-group": "primary",
    },
    "source_language": {
        "type": "string",
        "default": "auto",
        "description": "Source language of the original; 'auto' to detect",
        "x-group": "primary",
    },
}

TEXT_TRANSLATE_REVIEW_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Draft translation",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="The draft translation to review and correct.",
        )
    ],
    BASE_INPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================

def _build_prompt(target_language: str, source_language: str) -> str:
    """Build the review prompt from the user-editable config.

    The output guardrail (return only the corrected translation, verbatim
    when already correct) is always present so the second pass stays a
    correction step, not a rewrite.
    """
    target = (target_language or DEFAULT_TARGET_LANGUAGE).strip() or DEFAULT_TARGET_LANGUAGE
    src = (source_language or "auto").strip()
    src_clause = (
        f" (originally in {src})" if src and src.lower() != "auto" else ""
    )

    return f"""You are reviewing a draft {target} translation{src_clause} against its original source.

The ORIGINAL SOURCE TEXT appears in the Context section above (labelled
"Document text"). The draft translation to review is the input below.

Your job: compare the draft against the source, then produce a CORRECTED
translation in {target}.

Check for:
- Mistranslations and false friends.
- Omissions: source content the draft dropped.
- Additions: text the draft invented that is not in the source.
- Names, dates, and numbers altered, anglicised, or miscopied.
- Register and idiom that read unnaturally in {target}.

Rules:
- Output ONLY the corrected {target} translation. No commentary, no diff,
  no notes about what you changed, no preamble.
- If the draft is already accurate and faithful, return it unchanged
  verbatim. Do not paraphrase or reformat.
- Preserve paragraph structure and any [ilegible] / [uncertain] markers
  verbatim. Do not resolve or delete them."""


def build_text_translate_review_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI for live preview/editing)."""
    return _build_prompt(
        target_language=config.get("target_language", DEFAULT_TARGET_LANGUAGE),
        source_language=config.get("source_language", "auto"),
    )


# =============================================================================
# Tool
# =============================================================================

@register_tool(
    name="text_translate_review",
    display_name="Translate Review",
    description=(
        "Second-pass AI double-check of a draft translation against the "
        "original source: corrects mistranslations, omissions, and altered "
        "names. Target language, model, and prompt are editable."
    ),
    category="llm",
    icon="checkmark.seal.text.page",
    color="teal",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=TEXT_TRANSLATE_REVIEW_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(
        BASE_CONFIG_SCHEMA, TEXT_TRANSLATE_REVIEW_CONFIG
    ),
    default_prompt=_build_prompt(DEFAULT_TARGET_LANGUAGE, "auto"),
    prompt_builder=build_text_translate_review_prompt,
    sort_order=14,  # Right after text_translate (sort_order=13)
)
async def text_translate_review(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Review and correct a draft translation against the original source."""

    text = inputs.get("text", "")  # the draft translation
    documents = inputs.get("documents", [])
    context = inputs.get("context")  # the original source text
    input_metadata = inputs.get("metadata")

    # User-editable prompt: explicit override wins, else build from config.
    prompt = inputs.get("prompt") or build_text_translate_review_prompt(inputs)

    return await process_text(
        text=text,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        documents=documents,
        # Faithful correction, not creative rewrite — low temperature default.
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
