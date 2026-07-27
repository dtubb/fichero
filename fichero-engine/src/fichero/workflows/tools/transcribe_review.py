"""
Transcribe Review tool — second-pass QA of an existing transcription.

Takes the original image + a prior transcription (via the `context` input
port) and re-shows them to a vision LLM with instructions to compare,
identify errors, and produce a corrected version. Distinct
artifact_type ("transcription_review") so the result doesn't share a
cache slot with the first-pass transcription and so the inspector can
display original vs. reviewed side-by-side if desired.

Use case: paleography (handwritten Spanish, Latin), low-quality scans,
ambiguous-script documents where one-shot transcription is unreliable.
The model genuinely catches errors on a second look that it missed
under one-shot pressure — especially abbreviation expansions, marginalia
it skipped, and characters it confused (rn vs m, c vs e in cursive).

Inherits from vision_base.py — only defines review-specific config and
prompt.
"""

from __future__ import annotations

from typing import Any

from fichero.llm import LLMConfig
from fichero.workflows.registry import register_tool
from fichero.workflows.types import State
from fichero.workflows.tools.llm_base import BASE_OUTPUT_PORTS, merge_config_schema
from fichero.workflows.tools.vision_base import (
    VISION_CONFIG_SCHEMA,
    VISION_INPUT_PORTS,
    VisionToolConfig,
    process_vision,
)


# =============================================================================
# Tool Configuration
# =============================================================================


REVIEW_CONFIG = {
    "language": {
        "type": "string",
        "default": "auto",
        "description": "Language hint for the reviewer (es / en / auto)",
        "x-group": "primary",
    },
    "skip_if_artifact_exists": {
        "type": "boolean",
        "default": True,
        "description": "Reuse a matching prior review artifact",
        "x-group": "advanced",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


_DEFAULT_REVIEW_PROMPT = """You are reviewing a prior transcription of a manuscript image.

Your job: compare the prior transcription against the image, identify
errors, and produce a CORRECTED transcription.

Common error patterns to look for:
- Abbreviations the prior pass missed or expanded incorrectly (Vmd, dho/dha, q̄, tpo, mrd, qta).
- Confused glyphs in cursive scripts: c↔e, rn↔m, u↔n, long-s mistaken for f, t↔l.
- Marginalia, stamps, signatures, or rubrics the prior pass skipped.
- Crossed-out text the prior pass either ignored or transcribed without marking.
- Inserted words above the line the prior pass dropped.
- Modernised spellings the prior pass introduced ('haver' silently turned into 'haber').
- Numbers and dates: digit confusions (1/7, 0/o, 5/6 in old hands).
- Names misread because the model fell back on a more familiar spelling.

Rules:
- Output ONLY the corrected transcription. No commentary, no diff, no
  notes about what you changed, no preamble.
- Preserve original orthography of the manuscript, including accents and
  diacritics, verbatim. Do NOT modernise.
- Keep [ilegible], [uncertain], [tachado: ...], [rúbrica], [sin texto]
  conventions.
- If the prior transcription is already correct, return it unchanged
  verbatim. Do not paraphrase or reformat.
- Do not invent text that is not visibly present.

The prior transcription appears in the Context section above. The image
follows."""


def build_transcribe_review_prompt(config: dict) -> str:
    """Expose the prompt to the workflow editor UI."""
    return config.get("prompt", _DEFAULT_REVIEW_PROMPT)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="transcribe_review",
    display_name="Transcribe Review",
    description="Second-pass QA of a prior transcription against the image",
    category="vision",
    icon="checkmark.seal",
    color="purple",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=False,
    tested=True,  # part of the validated HTR transcription chain
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, REVIEW_CONFIG),
    config_defaults={
        "vision_mode": "llm",
        "language": "auto",
        "update_page_content": True,
        "save_to_db": True,
    },
    default_prompt=_DEFAULT_REVIEW_PROMPT,
    prompt_builder=build_transcribe_review_prompt,
    sort_order=11,  # Right after transcribe (sort_order=10)
)
async def transcribe_review(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Re-check an image against its prior transcription and emit a corrected version."""

    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    prior_text = inputs.get("context")  # Prior transcription flows in via this port
    if isinstance(prior_text, list) and prior_text and all(
        isinstance(records, list) for records in prior_text
    ):
        prior_text = [
            "\n\n---\n\n".join(
                str(records[index].get("text", ""))
                for records in prior_text
                if index < len(records) and isinstance(records[index], dict)
            )
            for index in range(len(files))
        ]
    elif isinstance(prior_text, list) and all(
        isinstance(record, dict) for record in prior_text
    ):
        prior_text = [str(record.get("text", "")) for record in prior_text]
    elif isinstance(prior_text, list) and len(prior_text) != len(files):
        prior_text = "\n\n---\n\n".join(str(text) for text in prior_text)
    input_metadata = inputs.get("metadata")

    update_page_content = inputs.get("update_page_content", True)
    prompt = inputs.get("prompt") or _DEFAULT_REVIEW_PROMPT

    tool_config = VisionToolConfig(
        artifact_type="transcription_review",
        update_page_content=update_page_content,
        trigger_embedding=update_page_content,
        supports_apple_vision=False,
        skip_if_artifact_exists=inputs.get("skip_if_artifact_exists", True),
    )

    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=tool_config,
        force_ocr=True,
        context=prior_text,
        input_metadata=input_metadata,
        thinking_mode=inputs.get("thinking_mode", "medium"),
    )
