"""
Transcribe Tool

Extracts text from images using vision LLM or Apple Vision (on-device OCR).
Inherits from vision_base.py - only defines transcribe-specific config and prompt.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
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
    LEVEL_PROJECT,
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
    # The one tool whose answer IS the page's text: a digital PDF extracted at
    # ingest needs no second OCR pass.
    accepts_extracted_text=True,
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
        "description": (
            "Ask the model for word/line bounding boxes (Gemini only; other "
            "providers transcribe without geometry and say so)"
        ),
    },
    "regions_first": {
        "type": "boolean",
        # OFF unless asked (#5523): it is a second, Apple Vision reading of the
        # page, stored beside the chosen reader's -- on a Spanish hand it read
        # Cyrillic. A run makes only the readings it was asked for.
        "default": False,
        "description": (
            "Also detect text regions on-device (Apple Vision) BEFORE transcribing, "
            "saving per-page bounding boxes as a regions artifact (an extra Apple "
            "Vision reading of the page). Off unless you ask for it."
        ),
    },
    "update_page_content": {
        "type": "boolean",
        "default": True,
        "description": "Index for search",
    },
    "lines_read_by": {
        "type": "string",
        "enum": ["kraken", "model"],
        "default": "kraken",
        "description": (
            "When vision_mode='kraken' and no kraken_model is named: 'model' has this "
            "step's vision model read each line Kraken found, a few lines per call, so "
            "the transcript carries Kraken's own line geometry. Exported as PAGE XML, "
            "that is a training set for a Kraken reader (distilling the model into it)."
        ),
    },
    "read_granularity": {
        "type": "string",
        "enum": ["lines", "region", "page"],
        "description": (
            "With lines_read_by='model': how the model is asked, as a bake-off measured it (a line, a region or the "
            "whole page a request). Unset: a few lines a call."
        ),
        "x-group": "advanced",
    },
    "kraken_model": {
        "type": "string",
        "default": "",
        "description": (
            "When vision_mode='kraken', the Kraken recognition model to READ "
            "each line (a catalog id like 'kraken-mccatmus', or a .mlmodel path). "
            "Empty = segment only (baselines, no text). Install from Settings -> "
            "AI -> Local Inference."
        ),
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _project_language(state: Any) -> str | None:
    """The project's own language: the project-fact row when one was written, else what Set Up saved
    (`answers.languages`, the first), so a page that states none is read as the project says (es, not 'auto'); None
    when the project says nothing or the library cannot be read."""
    library = state.get("library_path", "") if state else ""
    if not library:
        return None
    try:
        from fichero_server.db import db_manager
        from fichero_server.models.source_declarations import project_facts

        fact = project_facts(db_manager.get_database(library)).language
        if fact:
            return fact
        from fichero_server.recipes.project import read_project_setup

        languages = ((read_project_setup(Path(library)).get("answers") or {}).get("languages")) or []
        return str(languages[0]) if languages else None
    except Exception:  # noqa: BLE001 -- no project language is the old behaviour
        return None


def _language_source_of(resolution: LanguageResolution, requested: str | None, project_language: str | None) -> str:
    """"page" only when this page decided its own language AND it differs from the run's (the node's request, else the
    project's); a refusal of the run's language holds for every page, a refusal of a page's own for that page alone
    (review 359, 362). A page stating the project's language counts as the run's."""
    asked = str(requested or "").strip()
    if asked.lower() in ("", "auto", "unknown", "und"):
        asked = ""
    if asked or resolution.level == LEVEL_PROJECT or not resolution.language:
        return "run"
    run = normalize_vision_language(project_language) if project_language else None
    return "page" if normalize_vision_language(resolution.language) != run else "run"


def _resolve_transcribe_language(
    requested: str | None,
    documents: list[Any] | None,
    project_language: str | None = None,
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
        return resolve_language(requested=requested, policy=policy, detect=False, project_language=project_language)

    resolutions = [
        resolve_language(requested=requested, document=doc, policy=policy, detect=False,
                         project_language=project_language)
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
    "image_width": 2048,
    "image_height": 1536,
    "text": "transcribed text here",
    "boxes": [
        {"text": "...", "bbox": [0.07, 0.13, 0.37, 0.06], "level": "line"}
    ]
}

Bounding box rules:
- "image_width" and "image_height" are the pixel dimensions of the image
  you analyzed. Always include them.
- bbox is [x, y, width, height] as FRACTIONS OF THE IMAGE, each between 0
  and 1. Do NOT use pixels.
- The origin is the TOP-LEFT corner: x grows right, y grows DOWN.
- "level" is "line" or "word".
- Every box's "text" must appear in the transcription above it.
- Return at least one box for every line of visible text. A reply with an
  empty "boxes" list is not an acceptable answer for a page that has text.
- Output the JSON as RAW TEXT only. Do NOT wrap it in Markdown code fences
  (no ``` and no ```json), and write no prose, heading, or explanation
  before or after the JSON object.
"""

    return prompt


def _reader_is_apple_vision(vision_mode: str, llm_config: LLMConfig) -> bool:
    """True when this step's reader is Apple Vision (`vision_mode` apple, or auto on the apple
    provider) -- `process_vision`'s own rule for `auto`."""
    if vision_mode == "apple":
        return True
    return vision_mode == "auto" and (getattr(llm_config, "provider", "") or "").lower() == "apple"


def _pages_with_lines(documents: list, files: list, library_path: str) -> list[str | None]:
    """Per file, the id of its page when that page already has lines (a working pass), else None."""
    from fichero_server.db import db_manager
    from fichero_server.db.manager import LibraryNotFoundError
    from fichero_server.llm.working_lines import working_lines

    ids = [d.get("id") if isinstance(d, dict) else None for d in (documents or [])[: len(files)]]
    ids += [None] * (len(files) - len(ids))
    if not library_path or not any(ids):
        return [None] * len(files)
    try:
        db = db_manager.get_database(library_path)
    except LibraryNotFoundError:  # no library on disk, so no page has lines: read page-level
        return [None] * len(files)
    return [i if i and working_lines(db, i) is not None else None for i in ids]


def _drop_empty_readings(library_path: str, results: list[dict]) -> set[str]:
    """The empty transcription a failed line pass saved for a page, so the page-level read leaves just one."""
    from fichero_server.db import db_manager
    from fichero_server.models import Artifact

    db = db_manager.get_database(library_path)
    dropped = set()
    for r in results:
        stub = db.get(Artifact, r["artifact_id"]) if r.get("artifact_id") and not (r.get("text") or "").strip() else None
        if stub is not None and not (stub.content or "").strip():
            db.delete(stub)
            dropped.add(stub.id)
    return dropped


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
    parallelism="elementwise",
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
        "regions_first": False,
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
    project_language = _project_language(state)
    resolution = _resolve_transcribe_language(inputs.get("language"), documents, project_language)
    language = resolution.language or UNKNOWN
    return_boxes = inputs.get("return_boxes", False)
    update_page_content = inputs.get("update_page_content", True)

    # Bboxes FIRST (Daniel, 2026-08-11): detect text regions on-device before
    # any transcription. Under per-file fan-out this runs per page — true
    # page-level regions-then-text with no graph changes. Detection failure
    # must never cost a transcription: log loudly and continue (the regions
    # artifact is an enhancement; the text is the contract).
    #
    # ONLY when the step asks for it (#5523). It was on by default, so every
    # Transcribe -- failed ones too -- also stored an Apple Vision reading of the
    # page nobody chose (it read a Spanish hand as Cyrillic). And never when the
    # reader IS Apple Vision: that reading is the transcription itself, and a
    # second copy is not a reading anyone asked for.
    # Never on a segment's picture (#5604): regions found on a cut-out would be written onto the page.
    from fichero_server.workflows.selection import segment_target_of  # noqa: PLC0415

    on_segments = any(segment_target_of(doc) for doc in (documents or []))
    if inputs.get("regions_first", False) and files and not on_segments and not _reader_is_apple_vision(
        vision_mode, llm_config
    ):
        from fichero_server.workflows.tools.detect_regions import (  # noqa: PLC0415
            detect_regions as _detect_regions,
        )

        try:
            await _detect_regions(
                inputs={"files": files, "documents": documents},
                state=state,
                llm_config=llm_config,
            )
        except Exception as regions_err:
            logger.warning(
                "regions_first: detection failed for %d file(s), continuing "
                "with transcription: %s",
                len(files),
                regions_err,
            )

    # Build prompt
    prompt = inputs.get("prompt") or _build_prompt(language, return_boxes)

    # Once a page has lines, every reader's output ties to them (`source.read.once-lines-exist-every-reading-ties-to-a-line`,
    # #5721): Apple Vision and a vision model read each line (its own picture) onto the page's working pass, as Kraken
    # does, instead of holding the whole page as text with no segment. A page that has text and is not asked to be read
    # again is still passed through, as before. shortcut: all the run's pages or none; a mixed run reads page-level.
    force_ocr = inputs.get("force_ocr", bool(inputs.get("prompt")) or not update_page_content)
    save_to_db = inputs.get("save_to_db", True)
    library_path = state.get("library_path", "")
    lines_read_by = inputs.get("lines_read_by") or "kraken"
    onto_lines = False
    page_vision_mode = page_lines_read_by = None
    page_level = vision_mode != "kraken" and save_to_db and files and not on_segments
    if page_level:
        have_lines = await asyncio.to_thread(_pages_with_lines, documents, files, library_path)
        has_text = any(isinstance(d, dict) and (d.get("page_content") or "").strip() for d in documents or [])
        if all(have_lines) and (force_ocr or not has_text):
            onto_lines = True
            page_vision_mode, page_lines_read_by = vision_mode, lines_read_by
            lines_read_by = "apple" if _reader_is_apple_vision(vision_mode, llm_config) else "model"
            vision_mode = "kraken"

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
    read = dict(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=tool_config,
        # Vision-specific
        vision_mode=vision_mode,
        # When vision_mode="kraken", read each segmented line with this Kraken
        # recognition model and save the transcript tied to its baselines.
        kraken_recognition_model=inputs.get("kraken_model"),
        lines_read_by=lines_read_by,
        read_granularity=inputs.get("read_granularity") or None,
        # Apple Vision needs a concrete recognition locale and has no "unknown"
        # — it keeps its historical en-US fallback. That is an OCR hint, not a
        # claim about the document, and unlike the prompt above it does not
        # instruct a model to read Spanish as English.
        language=normalize_vision_language(resolution.language),
        # The page's own language can be refused for that page alone; the project's or the node's holds for every page.
        language_source=_language_source_of(resolution, inputs.get("language"), project_language),
        max_image_dimension=inputs.get("max_image_dimension", 2048),
        force_ocr=force_ocr,
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
        save_to_db=save_to_db,
        save_to_file_flag=inputs.get("save_to_file", False),
        return_boxes=return_boxes,
        metadata_field=inputs.get("metadata_field"),
        # #4496: the prompt above forbids commentary and the model ignores it.
        # This inspects the OUTPUT — strips delimited reasoning, and RAISES on
        # commentary so the file fails loudly instead of storing "Step-by-step
        # reasoning:" in an artifact typed `transcription`.
        postprocess_text=sanitize_transcription,
    )
    result = await process_vision(**read)
    if onto_lines:
        # A page whose lines came back with no reading (the model did not answer line by line) keeps its page text, as
        # before, rather than losing it; the tie job then ties it to the lines. Only those files are read again.
        empty = {r.get("file") for r in result.get("results") or [] if not (r.get("text") or "").strip()}
        again = [i for i, f in enumerate(files) if f in empty]
        if again:
            dropped = await asyncio.to_thread(_drop_empty_readings, library_path, result["results"])
            redo = await process_vision(**{**read, "files": [files[i] for i in again],
                                           "documents": [documents[i] for i in again if i < len(documents or [])],
                                           "vision_mode": page_vision_mode, "lines_read_by": page_lines_read_by})
            by_file = {r.get("file"): r for r in redo.get("results") or []}
            result["results"] = [by_file.get(r.get("file"), r) for r in result.get("results") or []]
            result["artifacts"] = [a for a in result.get("artifacts", []) if a not in dropped] + redo.get("artifacts", [])
            result["error"] = result.get("error") or redo.get("error")
            if len(again) == len(files):
                result, onto_lines = redo, False
            result.setdefault("notes", []).extend(
                f"{Path(files[i]).name}: the model did not read line by line; read the page whole" for i in again)
    notes = result.setdefault("notes", [])
    if onto_lines:
        notes.append(f"read each of the page's lines ({'Apple Vision' if lines_read_by == 'apple' else 'the model'} on "
                     "each line's picture) and tied the words to them, not the page as one text")
    elif page_level and library_path and not result.get("error"):
        for file, page_id in zip(files, await asyncio.to_thread(_pages_with_lines, documents, files, library_path)):
            if page_id is None:
                notes.append(f"{Path(file).name}: no lines on this page, so its reading is the page's text, tied to no line")
    return result
