"""
Transcribe Tool

Extracts text from images using vision LLM or Apple Vision (on-device OCR).
Inherits from vision_base.py - only defines transcribe-specific config and prompt.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero_server.workflows.types import State
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools._doc_lookup import documents_from_state_outputs
from fichero_server.workflows.tools.llm_base import BASE_OUTPUT_PORTS, merge_config_schema
from fichero_server.workflows.tools.transcription_output import sanitize_transcription
from fichero_server.workflows.tools.vision_base import (
    VISION_INPUT_PORTS,
    VISION_CONFIG_SCHEMA,
    VisionToolConfig,
    normalize_vision_language,
    process_vision,
)
from fichero_server.llm import LLMConfig
from fichero_server.llm.language_policy import (
    UNKNOWN,
    LanguageResolution,
    configured_policy,
    resolve_language,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = VisionToolConfig(
    artifact_type="transcription",
    update_page_content=True,
    trigger_embedding=True,
    supports_apple_vision=True,
    metadata_field="transcription",
)

# Transcribe-specific config (added to VISION_CONFIG_SCHEMA)
TRANSCRIBE_CONFIG = {
    "language": {
        "type": "string",
        # `auto` defers to the library's language policy and the document's own
        # recorded language (#2092). It used to default to `en-US`, which meant
        # every transcription asserted English unless a user went looking for
        # this field — the setting existed but the default overrode it.
        "default": "auto",
        "description": "Language locale, or 'auto' to follow the library's language policy",
    },
    "return_boxes": {
        "type": "boolean",
        "default": False,
        "description": "Text positions",
    },
    "update_page_content": {
        "type": "boolean",
        "default": True,
        "description": "Index for search",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _resolve_transcribe_language(
    requested: str | None,
    documents: list[Any] | None,
) -> LanguageResolution:
    """Decide what language this transcription run is in (#2092).

    Transcription used to hardcode ``en-US``: the config default was ``en-US``
    and ``normalize_vision_language("")`` also returns ``en-US``, so the
    library's language policy had no effect on the very first step of the
    chain. On a Spanish-language colonial archive that does not read as
    slightly-degraded output — the model is told the page is English and
    produces confident English-shaped readings of Spanish text.

    ``process_vision`` transcribes a batch under ONE prompt, so this resolves at
    batch level. When the selected documents do not agree on a language the
    answer is UNKNOWN rather than the majority: a prompt that asserts Spanish
    over an English page is the same error in the other direction, and the
    batch-level guess is the part we cannot justify. Per-page language means
    running the node per page, which the graph already supports.
    """
    policy = configured_policy()
    docs = list(documents or [])

    if not docs:
        return resolve_language(requested=requested, policy=policy, detect=False)

    resolutions = [
        resolve_language(requested=requested, document=doc, policy=policy, detect=False)
        for doc in docs
    ]
    distinct = {r.language for r in resolutions if r.is_known}
    if len(distinct) == 1 and all(r.is_known for r in resolutions):
        return resolutions[0]
    if len(distinct) > 1:
        return LanguageResolution(
            language=None,
            status=UNKNOWN,
            source="policy",
            basis=(
                "the selected documents are in different languages "
                f"({', '.join(sorted(str(item) for item in distinct))}); transcribe "
                "them separately to give each its own language"
            ),
        )
    return resolutions[0]


def _build_prompt(language: str, return_boxes: bool) -> str:
    """Build the transcription prompt.

    Archival principle: transcribe what is on the page, nothing more. The
    extractors and catalogue downstream do the interpretation; this tool's
    only job is to produce the raw text faithfully. Letting the model add
    "notes" or "summaries" pollutes downstream extraction with hallucinated
    or duplicated content.
    """
    # `auto` / empty means no language was established. Say so, rather than
    # asserting one: "Language: en-US" over a Spanish page is an instruction to
    # misread it (#2092). Telling the model to follow the source is the honest
    # instruction and the better one on unlabelled archival material.
    if not language or language.strip().lower() in {"auto", UNKNOWN}:
        language_line = (
            "Language: transcribe in the language of the source. Do not "
            "translate, and do not assume the document is in English."
        )
    else:
        language_line = f"Language: {normalize_vision_language(language)}"

    prompt = f"""Transcribe the text visible on this image.

{language_line}

Rules:
- Output ONLY the transcription. No headings, no preamble, no commentary,
  no summary, no notes, no explanations, no observations about quality or
  legibility, no descriptions of seals or images, no language about the
  difficulty of the handwriting.
- Preserve original layout, line breaks, and paragraph structure.
- Preserve original spelling and capitalisation, including ALL CAPS
  headers if they appear that way.
- Preserve orthography exactly as written, including all diacritics
  and accent marks (e.g., keep "Chocó" as "Chocó", never "Choco";
  keep "Ramón" as "Ramón", never "Ramon").
- Do not strip accents, tildes, cedillas, or umlauts. If a mark is
  visible, keep it.
- Include every visible text element — headers, body, marginalia, stamps,
  signatures (transcribe the signed name as written), printed labels,
  handwritten annotations.
- For text you cannot confidently read, use explicit uncertainty markers:
  [ilegible] for unreadable text and [uncertain] for plausible-but-low-
  confidence readings. Place the marker inline at the uncertain span.
  Do not guess. Do not fill in.
- Do NOT invent dates, numbers, names, or words that are not legibly
  present. Do not normalise dates ("23/7/1999" stays "23/7/1999", not
  "1999-07-23").
- Do NOT repeat any portion of the transcription. Output each visible
  passage exactly once.
- If the image contains no legible text, output the single token
  [sin texto].
"""

    if return_boxes:
        # Coordinates are asked for NORMALIZED, not in pixels (#4309). The
        # prompt used to ask for pixels while the parser was called without
        # page dimensions, so `_coerce_normalized_bbox` raised
        # "pixel bbox values require page_width and page_height" on exactly
        # the shape the prompt requested — the request and the reader wanted
        # different coordinate spaces, and any compliant model failed.
        #
        # Asking for 0..1 is also the better contract: a page exists as an
        # original scan, an enhanced copy, a deskewed copy and a thumbnail,
        # and pixels of whichever rendition happened to be sent are wrong
        # against all the others. Fractions of the page survive every one.
        prompt += """
Additionally, return bounding box coordinates as JSON:
{
    "text": "transcribed text here",
    "boxes": [
        {"text": "...", "bbox": [0.07, 0.13, 0.37, 0.06], "level": "line"}
    ]
}

Bounding box rules:
- bbox is [x, y, width, height] as FRACTIONS OF THE IMAGE, each between 0
  and 1. Do NOT use pixels.
- The origin is the TOP-LEFT corner: x grows right, y grows DOWN.
- "level" is "line" or "word".
- Every box's "text" must appear in the transcription above it.
"""

    return prompt


def build_transcribe_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    # `auto` is passed through, not normalised to a locale — the preview then
    # shows the same "language of the source" wording the run will use (#2092).
    language = config.get("language", "auto")
    return_boxes = config.get("return_boxes", False)
    return _build_prompt(language, return_boxes)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="transcribe",
    display_name="Transcribe",
    description="Extract text from images (OCR)",
    category="vision",
    icon="text.viewfinder",
    color="blue",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    tested=True,  # part of the validated HTR transcription chain
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, TRANSCRIBE_CONFIG),
    config_defaults={
        "vision_mode": "auto",
        "language": "auto",
        "return_boxes": False,
        "update_page_content": True,
        "save_to_db": True,
    },
    default_prompt=_build_prompt("auto", False),
    prompt_builder=build_transcribe_prompt,
    sort_order=10,
)
async def transcribe(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Extract text from images using vision AI."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    # #4298: when the graph wires only the `files` port (older stored workflow
    # copies), recover the aligned documents from upstream node outputs so a
    # page-scoped run stays scoped to that ONE page instead of falling into
    # the whole-PDF branch (which processes and bills every page).
    documents = inputs.get("documents") or documents_from_state_outputs(state, files)
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get transcribe-specific config
    vision_mode = inputs.get("vision_mode", "auto")
    # #2092: was `normalize_vision_language(inputs.get("language", "en"))`,
    # i.e. English unless the node said otherwise, with the library's language
    # policy never consulted. Now the node value is a REQUEST that the policy
    # resolves; an explicit locale on the node still wins.
    resolution = _resolve_transcribe_language(inputs.get("language"), documents)
    language = resolution.language or UNKNOWN
    return_boxes = inputs.get("return_boxes", False)
    update_page_content = inputs.get("update_page_content", True)

    # Build prompt
    prompt = inputs.get("prompt") or _build_prompt(language, return_boxes)

    # Override tool config if user disabled page_content update
    tool_config = TOOL_CONFIG
    if not update_page_content:
        tool_config = VisionToolConfig(
            artifact_type="transcription",
            update_page_content=False,
            trigger_embedding=False,
            supports_apple_vision=True,
        )

    # Process with shared logic - pass all inherited config
    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=tool_config,
        # Vision-specific
        vision_mode=vision_mode,
        # Apple Vision needs a concrete recognition locale and has no "unknown"
        # — it keeps its historical en-US fallback. That is an OCR hint, not a
        # claim about the document, and unlike the prompt above it does not
        # instruct a model to read Spanish as English.
        language=normalize_vision_language(resolution.language),
        max_image_dimension=inputs.get("max_image_dimension", 2048),
        force_ocr=inputs.get(
            "force_ocr",
            bool(inputs.get("prompt")) or not update_page_content,
        ),
        # Inherited from BASE_CONFIG
        temperature=inputs.get("temperature"),
        max_tokens=inputs.get("max_tokens"),
        output_format=inputs.get("output_format", "text"),
        output_options={
            "choices": inputs.get("choices"),
            "max_words": inputs.get("max_words"),
            "max_items": inputs.get("max_items"),
        },
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        thinking_mode=inputs.get("thinking_mode", "off"),
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        return_boxes=return_boxes,
        metadata_field=inputs.get("metadata_field"),
        # #4496: the prompt above forbids commentary and the model ignores it.
        # This inspects the OUTPUT — strips delimited reasoning, and RAISES on
        # commentary so the file fails loudly instead of storing "Step-by-step
        # reasoning:" in an artifact typed `transcription`.
        postprocess_text=sanitize_transcription,
    )
