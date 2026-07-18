"""
Translate Text Tool (#926)

Translate a document's extracted/transcribed text from its source language
into the user's preferred language (for example, Spanish → English; configurable
per workflow). Pure-text-in / pure-text-out, cacheable, idempotent — it saves
a distinct ``translation`` artifact so the raw, cleaned, and translated
representations of a document coexist and downstream tools pick whichever
they want.

Inherits from llm_base.py — transforms input text via ``process_text``. The
translation behaviour is driven entirely by user-editable config:

  * ``target_language`` / ``source_language`` — the languages, free text so
    they are not enum-baked (#874). 'auto' source lets the model detect it.
  * ``preserve_names`` — keep proper names / archival citations verbatim.
  * The full prompt is overridable via the BASE_CONFIG_SCHEMA ``prompt``
    field, and the model via ``provider_name`` / ``model_name``.

Nothing here is a hard-coded, non-editable string literal: the target
language and the default prompt are only defaults. See
feedback_user_editable_not_hardcoded.

Pairs with text_translate_review (the AI double-check second pass) and with
clean_text / ocr_cleanup (#925) which normally run before translation.
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
    artifact_type="translation",
    update_page_content=False,
    trigger_embedding=True,
    embedding_scope="translation",
    metadata_field="translation",
)

# Default target is English, but it is a plain
# string default the user can change per workflow — never an enum or literal
# baked into the call site.
DEFAULT_TARGET_LANGUAGE = "English"

TEXT_TRANSLATE_CONFIG = {
    "target_language": {
        "type": "string",
        "default": DEFAULT_TARGET_LANGUAGE,
        "description": "Language to translate INTO (e.g. English, Spanish, French)",
        "x-group": "primary",
    },
    "source_language": {
        "type": "string",
        "default": "auto",
        "description": "Source language; 'auto' lets the model detect it",
        "x-group": "primary",
    },
    "preserve_names": {
        "type": "boolean",
        "default": True,
        "description": (
            "Keep proper names, place names, institutions, and archival "
            "citations in their original form rather than translating them"
        ),
    },
}

TEXT_TRANSLATE_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Source-language text to translate.",
        )
    ],
    BASE_INPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================

def _build_prompt(
    target_language: str,
    source_language: str,
    preserve_names: bool,
) -> str:
    """Build the translation prompt from the user-editable config.

    The fidelity guardrails (no summarizing, no omissions, no additions) are
    always present so translation never drifts into paraphrase.
    """
    target = (target_language or DEFAULT_TARGET_LANGUAGE).strip() or DEFAULT_TARGET_LANGUAGE
    src = (source_language or "auto").strip()
    from_clause = (
        f"from {src} " if src and src.lower() != "auto" else ""
    )

    rules: list[str] = [
        f"- Produce a faithful, accurate translation into {target}. Convey the "
        "full meaning of the source — do NOT summarize, omit, paraphrase away, "
        "or add information.",
        "- Preserve the document structure: keep paragraph breaks, lists, and "
        "line layout.",
    ]
    if preserve_names:
        rules.append(
            "- Keep proper names, place names, institutions, and archival "
            "citations in their original form — do not anglicise or translate "
            "them."
        )
    rules.extend(
        [
            "- If a passage is illegible or marked [ilegible] / [uncertain], "
            "carry the marker across unchanged and do not replace it with a guess.",
            f"- Output ONLY the {target} translation, with no preamble, notes, "
            "or the original text.",
        ]
    )
    rule_block = "\n".join(rules)

    return f"""Translate the following text {from_clause}into {target}.

Rules:
{rule_block}"""


def build_text_translate_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI for live preview/editing)."""
    return _build_prompt(
        target_language=config.get("target_language", DEFAULT_TARGET_LANGUAGE),
        source_language=config.get("source_language", "auto"),
        preserve_names=bool(config.get("preserve_names", True)),
    )


# =============================================================================
# Tool
# =============================================================================

@register_tool(
    name="text_translate",
    display_name="Translate Text",
    description=(
        "Translate extracted or transcribed text into the user's preferred "
        "language. Target language, source language, and model are all "
        "editable on the node."
    ),
    category="llm",
    icon="character.book.closed",
    color="teal",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=TEXT_TRANSLATE_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, TEXT_TRANSLATE_CONFIG),
    default_prompt=_build_prompt(DEFAULT_TARGET_LANGUAGE, "auto", True),
    prompt_builder=build_text_translate_prompt,
    sort_order=13,
)
async def text_translate(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Translate source-language text into the configured target language."""

    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # User-editable prompt: explicit override wins, else build from config.
    prompt = inputs.get("prompt") or build_text_translate_prompt(inputs)

    return await process_text(
        text=text,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        documents=documents,
        # Translation must be faithful, not creative — low temperature default.
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
