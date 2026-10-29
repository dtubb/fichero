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

import re
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import State
from fichero_server.workflows.tools._doc_lookup import documents_from_state_outputs
from fichero_server.workflows.tools.llm_base import BASE_OUTPUT_PORTS, merge_config_schema
from fichero_server.workflows.tools.transcription_output import sanitize_transcription
from fichero_server.workflows.tools.vision_base import (
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
    "lens": {
        "type": "string",
        "description": "The pass this review makes (abbreviations, orthography, names-and-dates): with no prompt set, its prompt is built from the project and its profile; recorded with the corrections",
        "x-group": "advanced",
    },
    "review_mode": {
        "type": "string",
        "enum": ["in-turn", "compare", "both"],
        "default": "in-turn",
        "description": "A second review's way with the first (#6257): in-turn reviews the first's result; compare reviews the reading the first started from, on its own; both is given that reading and the first's version and settles them, marking what it cannot as uncertain",
        "x-group": "advanced",
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


#: Asked of the model whatever prompt a node carries (the Review the Reading preset has its own, three): a page's
#: lines are shown as `<segment id> | x y w h | maker | text`, and a correction is only tied back to its line when the
#: answer names it (`source.job.review-asks-one-answer-line-per-segment-id`).
ANSWER_BY_ID = (
    "The prior transcription is a list of lines, each as `<segment id> | box | maker | confidence | text` "
    "(confidence is how sure the machine was). Answer with exactly one "
    "line per listed line, in the same order, as `<segment id> | <certain, uncertain or unreadable> | <corrected "
    "text>`, optionally followed by ` | note: <short note>` saying why you changed or doubt a line: keep every id; give a line you cannot read as `unreadable` with its text as shown, never invented; and "
    "never merge, split, drop or add a line."
)
#: A line that starts with a segment id (a uuid, hex): the lines as shown, and an earlier pass's answer by id, which the
#: next pass of a preset is given as its context.
_SHOWN_LINE = re.compile(r"^[0-9a-f]{32} \| ", re.MULTILINE)


def shows_segment_lines(prior_text: Any) -> bool:
    """Whether the context given to the model lists a page's lines by segment id."""
    shown = prior_text if isinstance(prior_text, list) else [prior_text or ""]
    return any(_SHOWN_LINE.search(str(text)) for text in shown)


def line_notes(answer: str) -> dict[str, str]:
    """The short note the review gave after a line, by segment id: `<id> | <flag> | <text> | note: <note>` (#5724)."""
    from fichero_server.llm.working_lines import answer_line

    notes = {}
    for line in answer.splitlines():
        segment_id, _flag, _text, note = answer_line(line)
        if note and _SHOWN_LINE.match(line.strip()[:35]):
            notes[segment_id] = note
    return notes


def unreadable_lines(answer: str) -> list[str]:
    """The lines the review flagged `unreadable`, by segment id: marked as lines the model could not read (#5724)."""
    from fichero_server.llm.working_lines import answer_line

    return [segment_id for segment_id, flag, _t, _n in map(answer_line, answer.splitlines())
            if flag == "unreadable" and _SHOWN_LINE.match(segment_id + " | ")]


def build_transcribe_review_prompt(config: dict) -> str:
    """Expose the prompt to the workflow editor UI. A node with a `lens` and no prompt is built at run time from
    the project; the editor shows what the generic profile would send."""
    if config.get("prompt"):
        return config["prompt"]
    if config.get("lens"):
        from fichero_server.recipes.review_profiles import review_prompt

        return review_prompt(config["lens"], None)[0]
    return _DEFAULT_REVIEW_PROMPT


def _with_line_scripts(prior_text: Any, documents: list, files: list, library_path: str) -> Any:
    """Each page's context, with its lines' own scripts and directions said when the page mixes them (#5728)."""
    if not library_path or not documents or not (isinstance(prior_text, list) or len(files) == 1):
        return prior_text
    from fichero_server.db import db_manager
    from fichero_server.db.manager import LibraryNotFoundError
    from fichero_server.llm.working_lines import working_lines
    from fichero_server.recipes.review_profiles import line_scripts

    try:
        db = db_manager.get_database(library_path)
    except LibraryNotFoundError:
        return prior_text
    texts = list(prior_text) if isinstance(prior_text, list) else [prior_text]
    for index, doc in enumerate(documents[:len(texts)]):
        doc_id = doc.get("id") if isinstance(doc, dict) else getattr(doc, "id", None)
        rows = working_lines(db, str(doc_id)) if doc_id else None
        said = line_scripts([(r.id, r.script, r.direction) for r in rows.lines]) if rows else ""
        if said:
            texts[index] = f"{texts[index] or ''}\n\n{said}".strip()
    return texts if isinstance(prior_text, list) else texts[0]


#: ponytail: the image's share of the prefill, as a Qwen2.5-VL processor counts it (one token per 28x28 patch, at most
#: its default max_pixels' 1280); a card field per model if another family counts differently.
_PATCH, _MOST_IMAGE_TOKENS = 28 * 28, 1280


def _image_tokens(path: Any) -> int:
    from PIL import Image

    try:
        with Image.open(path) as img:
            return min(_MOST_IMAGE_TOKENS, img.width * img.height // _PATCH + 1)
    except (OSError, ValueError, TypeError):
        return _MOST_IMAGE_TOKENS  # not readable here: count the most an image can take


def _within_budget(prior_text: Any, model: str, prompt: str = "", files: list | None = None) -> tuple[Any, list[str]]:
    """Each page's listed lines, in reading order, up to the model's prefill budget (its card's `prefill_tokens`,
    #5648), after the prompt and the page image are counted; a page over it is told how many lines were left out,
    and the step's notes say so too. A model with no stated budget is sent everything."""
    import logging

    from fichero_server.recipes import cards

    budget = cards.prefill_tokens_for(model) if model else None
    if not budget or not prior_text:
        return prior_text, []
    texts = list(prior_text) if isinstance(prior_text, list) else [prior_text]
    said = []
    for index, text in enumerate(texts):
        rows = str(text or "").split("\n")
        listed = [i for i, row in enumerate(rows) if _SHOWN_LINE.match(row)]
        image = files[index] if files and index < len(files) else None
        # the prompt, the context's own words and the image come first; the lines fill what is left
        used = (len(prompt) + sum(len(r) for i, r in enumerate(rows) if i not in set(listed))) // 4 + (
            _image_tokens(image) if image else 0)
        keep: list[int] = []
        for i in listed:
            used += len(rows[i]) // 4 + 1  # ponytail: ~4 characters a token; a tokenizer per model if this misjudges
            if used > budget and keep:
                break
            keep.append(i)
        if len(keep) == len(listed):
            continue
        left = len(listed) - len(keep)
        message = (f"{left} of the page's {len(listed)} lines were left out to fit the model's budget of {budget} "
                   "tokens; they are not reviewed in this pass")
        dropped = set(listed[len(keep):])
        texts[index] = "\n".join(row for i, row in enumerate(rows) if i not in dropped) + f"\n\n({message}.)"
        logging.getLogger(__name__).warning("review context: %s", message)
        said.append(message)
    return (texts if isinstance(prior_text, list) else texts[0]), said


def _only_unsure(prior_text: Any, below: float, model: str) -> tuple[Any, list[str], tuple[int, int]]:
    """Variant A, Kraken then a cloud model (`source.recipe.kraken-then-cloud-unsure-lines`): of each page's listed lines
    only those whose stated certainty is under `below` stay in what the model is sent; a line at or above it is not
    sent, so the answer names no such line and its reading is untouched. A line with no stated certainty is sent: it
    cannot be called sure. Returns the context, the note for the step ("N of M lines sent to <model>"), and (N, M)."""
    texts = list(prior_text) if isinstance(prior_text, list) else [prior_text or ""]
    sent = total = 0
    for index, text in enumerate(texts):
        rows = str(text or "").split("\n")
        keep = []
        for row in rows:
            if not _SHOWN_LINE.match(row):
                keep.append(row)
                continue
            total += 1
            fields = row.split(" | ", 4)
            try:
                sure = float(fields[3])
            except (IndexError, ValueError):
                sure = None  # "-": the machine stated none
            if sure is None or sure < below:
                sent += 1
                keep.append(row)
        texts[index] = "\n".join(keep)
    note = f"{sent} of {total} lines are under {below:g} sure; the others are not re-read"
    return (texts if isinstance(prior_text, list) else texts[0]), [note], (sent, total)


async def _review_whole_page(inputs: dict[str, Any], state: State, llm_config: LLMConfig, prior_text: Any,
                             prompt: str, files: list, documents: list, input_metadata: Any,
                             update_page_content: bool) -> dict[str, Any]:
    """The review as it always was: the model is shown the page and its lines' text."""
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
        # #4496: the review nodes were the worst offenders — t4, the FINAL
        # pass, scored CER 5.41 by storing reasoning as the reviewed
        # transcription, with `update_page_content=True` writing it to the page
        # as well. Strip delimited reasoning; raise on anything still
        # commentary-shaped so the run goes red.
        postprocess_text=sanitize_transcription,
    )


def _answered_by(db: Any, document_id: str, provider: str, model: str) -> set[str]:
    """The lines of a page that already carry a reading from a review by this same model (a re-run does not ask them
    again, or pay for them again)."""
    from fichero_server.models import Artifact, ContentRepresentation

    made = {a.id for a in db.query(Artifact, document_id=document_id, artifact_type="transcription_review")
            if (a.provider, a.model) == (provider, model)}
    return {r.segment_id for r in db.query(ContentRepresentation, document_id=document_id)
            if r.segment_id and r.derived_from_artifact_id in made and not getattr(r, "retracted_at", None)}


async def _review_unsure_lines(prior_text: Any, documents: list, files: list, llm_config: LLMConfig, state: State,
                               inputs: dict[str, Any]) -> dict[str, Any]:
    """Variant A (`source.recipe.kraken-then-cloud-unsure-lines`): the model is sent each unsure line's own crop with
    Kraken's text and the language, never the page (`re_ask_lines.re_ask`, the line cut the line reader uses). A page
    with no unsure line makes no call. A line the model gives nothing for keeps Kraken's text, and the note says so.
    The answers are saved as the page's review artifact; `_onto_lines` puts them on the lines as for any review."""
    from PIL import Image

    from fichero_server.api.routes.document.segment_readings import counting_texts
    from fichero_server.db import db_manager
    from fichero_server.llm.line_reader import LINES_PER_CALL
    from fichero_server.llm.re_ask_lines import re_ask
    from fichero_server.llm.working_lines import in_pixels, working_lines
    from fichero_server.models import Artifact, Document
    from fichero_server.recipes.cards import lines_per_request_for

    library_path = state.get("library_path", "")
    db = db_manager.get_database(library_path)
    model = f"{llm_config.provider}/{llm_config.model}"
    language = inputs.get("language")
    pages = list(prior_text) if isinstance(prior_text, list) else [prior_text]
    result: dict[str, Any] = {"text": "", "value": None, "texts": [], "values": [], "results": [], "artifacts": [],
                              "output_files": [], "page_records": [], "notes": [], "lines_sent": 0}
    total_lines = already = 0
    for index, file_path in enumerate(files):
        doc = documents[index] if index < len(documents) else None
        doc_id = doc.get("id") if isinstance(doc, dict) else getattr(doc, "id", None)
        shown = {row[:32] for row in str(pages[index] if index < len(pages) else "").split("\n")
                 if _SHOWN_LINE.match(row)}
        rows = working_lines(db, str(doc_id)) if doc_id else None
        total_lines += len(rows.lines) if rows is not None else 0
        if rows is None or not shown:
            result["results"].append({"file": file_path, "text": "", "value": None, "lines": "no line under the bar"})
            continue
        page = db.get(Document, str(doc_id))
        texts = counting_texts(db, rows.lines)
        with Image.open(page.path) as img:
            width, height = rows.page_size(img)
        # a forced re-run (`skip_if_artifact_exists` False) asks every unsure line again
        done = (_answered_by(db, str(doc_id), llm_config.provider, llm_config.model)
                if inputs.get("skip_if_artifact_exists", True) else set())
        already += len(shown & done)
        asked = [{"id": r.id, "text": texts.get(r.id, ""), "polygon": in_pixels(r, width, height)["polygon"]}
                 for r in rows.lines if r.id in shown and r.id not in done]
        if not asked:
            result["results"].append({"file": file_path, "text": "", "value": None,
                                      "lines": "every unsure line was already answered by this model"})
            continue
        got, missing = await re_ask(page.path, asked, "", llm_config, frame=rows.frame,
                                    batch=lines_per_request_for(str(llm_config.model)) or LINES_PER_CALL,
                                    language=language)
        name = getattr(page, "name", None) or doc_id
        for line_id in list(got):  # the same guard as a whole-page review: commentary is not a line (#4496)
            try:
                got[line_id] = sanitize_transcription(got[line_id])
            except Exception as err:
                del got[line_id]
                missing.append(line_id)
                result["notes"].append(f"{name}: {model}'s answer for line {line_id} was not a reading ({err}); "
                                       "the line keeps its first reader's text")
        result["lines_sent"] += len(asked)
        if missing:
            result["notes"].append(f"{name}: {model} gave no reading for {len(missing)} of {len(asked)} lines "
                                   f"({', '.join(missing)}); they keep their first reader's text")
        content = "\n".join(f"{r['id']} | {got[r['id']]}" for r in asked if r["id"] in got)
        if not content:
            result["results"].append({"file": file_path, "text": "", "value": None, "lines": "no line answered"})
            continue
        art = Artifact(document_id=str(doc_id), artifact_type="transcription_review", content=content,
                       provider=llm_config.provider, model=llm_config.model, version=1, reviewed=False)
        db.save(art)
        result["artifacts"].append(art.id)
        result["texts"].append(content)
        result["page_records"].append({"doc_id": str(doc_id), "text": content})
        result["results"].append({"file": file_path, "text": content, "value": content, "artifact_id": art.id})
    if already:
        result["notes"].append(f"{already} unsure line(s) were already answered by {model} and were not asked again")
    result["notes"].append(f"{result['lines_sent']} of {total_lines} lines sent to {model}")
    return result


def _project_prompt(lens: str, library_path: str) -> tuple[str, str]:
    """The prompt for `lens` built from the project's setup answers and the profile they choose
    (`source.job.review-is-built-from-the-project-and-a-profile`), and which profile that was."""
    from pathlib import Path

    from fichero_server.db import db_manager
    from fichero_server.recipes.project import read_project_setup
    from fichero_server.recipes.review_profiles import review_prompt

    answers = read_project_setup(Path(db_manager.get_database(library_path).path).parent)["answers"] if library_path else None
    return review_prompt(lens, answers)


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
    requires_generative_model=True,  # its whole-page config (supports_apple_vision=False) is built at run time
    supports_batch=True,
    supports_structured_output=False,
    tested=True,  # part of the validated HTR transcription chain
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, REVIEW_CONFIG),
    config_defaults={
        "vision_mode": "llm",
        "language": "auto",
        # The page's text is constructed from the lines the review writes readings onto, never a blob of its own
        # (`source.model.page-text-is-constructed-from-the-segments`, #5486).
        "update_page_content": False,
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
    # #4298: recover aligned documents from upstream node outputs when the
    # `documents` port is unwired, so a page-scoped review stays scoped to
    # that ONE page instead of the whole PDF.
    documents = inputs.get("documents") or documents_from_state_outputs(state, files)
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
    if not prior_text:
        # STANDALONE review (2026-08-26, "run a paleographer update on an
        # artifact"): with no upstream transcription wired in, review the
        # document's EXISTING text — page_content first, else its latest
        # transcription artifact. This is what lets "transcribe with one
        # model today, review with another tomorrow" exist as two separate
        # user acts instead of one welded pipeline.
        # One builder for a page's context (#5026): the page's lines, else its text, else its
        # newest transcription -- what `_existing_transcription_context` sent, and the lines too.
        from fichero_server.tool_context import with_page_context

        prior_text = with_page_context(None, documents, files, state.get("library_path", ""), confidence=True,
                                       review_mode=inputs.get("review_mode") or "in-turn")
    prior_text = _with_line_scripts(prior_text, documents, files, state.get("library_path", ""))
    input_metadata = inputs.get("metadata")

    update_page_content = inputs.get("update_page_content", False)
    prompt, profile_said = inputs.get("prompt"), None
    if not prompt and inputs.get("lens"):
        prompt, profile_said = _project_prompt(inputs["lens"], state.get("library_path", ""))
    prompt = prompt or _DEFAULT_REVIEW_PROMPT
    if shows_segment_lines(prior_text):
        prompt = f"{prompt}\n\n{ANSWER_BY_ID}"
    if state.get("library_path"):  # the project's confirmed names go to every review, whatever prompt the node carries
        from fichero_server.db import db_manager
        from fichero_server.db.manager import LibraryNotFoundError
        from fichero_server.recipes.known_names import instruction

        try:
            names = instruction(db_manager.get_database(state["library_path"]))
        except LibraryNotFoundError:  # no library on disk, so no confirmed names
            names = None
        if names:
            prompt = f"{prompt}\n\n{names}"

    counted: tuple[int, int] | None = None
    said_sent: list[str] = []
    cut: list[str] = []
    below = inputs.get("only_below_confidence")
    if below is not None and shows_segment_lines(prior_text):
        prior_text, said_sent, counted = _only_unsure(
            prior_text, float(below), f"{llm_config.provider}/{llm_config.model}")
        result = await _review_unsure_lines(prior_text, documents, files, llm_config, state, inputs)
    else:
        prior_text, cut = _within_budget(prior_text, str(getattr(llm_config, "model", "") or ""), prompt, files)
        result = await _review_whole_page(inputs, state, llm_config, prior_text, prompt, files, documents,
                                          input_metadata, update_page_content)
    if profile_said:
        result.setdefault("notes", []).append(profile_said)
    result.setdefault("notes", []).extend(said_sent + cut)
    if counted is not None:
        result.setdefault("lines_sent", counted[0])
        result["lines_total"] = counted[1]
    library_path = state.get("library_path", "")
    if library_path and result.get("artifacts"):
        import asyncio

        unresolved = await asyncio.to_thread(_onto_lines, result, library_path, state.get("task_id"),
                                             inputs.get("lens"))
        if unresolved:
            await _re_ask_pages(result, unresolved, library_path, state.get("task_id"), llm_config)
    return result


def _onto_lines(result: dict[str, Any], library_path: str, run_id: str | None, lens: str | None = None) -> list[str]:
    """The review's corrections become the page's text (#5654, `source.job.correct-onto-lines`): each
    saved review is put onto its page's lines as readings (`working_lines.correct_lines`), and what was
    done is said per page in the step's notes and its per-file result (`lines`). A review that cannot be
    matched to the lines stays the page's `transcription_review` artifact, and says "not tied to lines".
    Returns the artifacts whose answer left lines out, for `_re_ask_pages` (#5720)."""
    from fichero_server.db import db_manager
    from fichero_server.llm.working_lines import NOT_TIED, correct_lines
    from fichero_server.models import Artifact, Document

    db = db_manager.get_database(library_path)
    by_artifact = {r.get("artifact_id"): r for r in result.get("results") or [] if isinstance(r, dict)}
    notes = result.setdefault("notes", [])
    unresolved: list[str] = []
    for artifact_id in result.get("artifacts") or []:
        artifact = db.get(Artifact, artifact_id) if artifact_id else None
        if artifact is None or artifact.artifact_type != "transcription_review":
            continue  # a review of a segment is already a reading of it (`segment.<type>`)
        # the corrections name this artifact, so it is where the lens that made them and each line's note are kept
        notes_by_line, unread = line_notes(artifact.content or ""), unreadable_lines(artifact.content or "")
        if lens or notes_by_line or unread:
            artifact.data = {**(artifact.data or {}), **({"lens": lens} if lens else {}),
                             **({"line_notes": notes_by_line} if notes_by_line else {}),
                             **({"unreadable_lines": unread} if unread else {})}
            db.save(artifact)
        _made, said = correct_lines(db, document_id=artifact.document_id, text=artifact.content or "",
                                    artifact_id=artifact.id, run_id=run_id, library_path=library_path)
        page = db.get(Document, artifact.document_id)
        notes.append(f"{getattr(page, 'name', None) or artifact.document_id}: {said}")
        if artifact_id in by_artifact:
            by_artifact[artifact_id]["lines"] = said
        if said.startswith(NOT_TIED) and "the review gave" in said:
            unresolved.append(artifact_id)
    return unresolved


async def _re_ask_pages(result: dict[str, Any], artifact_ids: list[str], library_path: str, run_id: str | None,
                        llm_config) -> None:
    """A page whose answer left lines out has those lines asked again, cut from the page, and the whole page
    tied by id (`source.job.correct-re-asks-per-line-when-it-does-not-tie`, #5720). A line still without an
    answer fails THAT page's step, naming the model and the lines; nothing is written for the page."""
    import asyncio

    from PIL import Image

    from fichero_server.api.routes.document.segment_readings import counting_texts
    from fichero_server.db import db_manager
    from fichero_server.llm.line_reader import LINES_PER_CALL
    from fichero_server.llm.re_ask_lines import re_ask
    from fichero_server.llm.working_lines import correct_lines, in_pixels, working_lines
    from fichero_server.models import Artifact, Document
    from fichero_server.recipes.cards import lines_per_request_for

    db = db_manager.get_database(library_path)
    by_artifact = {r.get("artifact_id"): r for r in result.get("results") or [] if isinstance(r, dict)}
    notes = result.setdefault("notes", [])
    for artifact_id in artifact_ids:
        artifact = db.get(Artifact, artifact_id)
        page = db.get(Document, artifact.document_id)
        name = getattr(page, "name", None) or artifact.document_id
        rows = working_lines(db, artifact.document_id)
        row_results = by_artifact.get(artifact_id)
        if rows is None or row_results is None:
            continue
        texts = counting_texts(db, rows.lines)
        answered: dict[str, str] = {}
        for line in (artifact.content or "").splitlines():
            head, _bar, rest = line.partition("|")
            if _bar and head.strip() in {r.id for r in rows.lines}:
                answered[head.strip()] = rest.strip()
        left = [r for r in rows.lines if r.id not in answered]
        with Image.open(page.path) as img:
            width, height = rows.page_size(img)
        asked = [{"id": r.id, "text": texts.get(r.id, ""), "polygon": in_pixels(r, width, height)["polygon"]}
                 for r in left]
        got, missing = await re_ask(page.path, asked, artifact.content or "", llm_config, frame=rows.frame,
                                batch=lines_per_request_for(str(getattr(llm_config, "model", ""))) or LINES_PER_CALL)
        if missing:
            model = f"{llm_config.provider}/{llm_config.model}"
            why = (f"{model} gave no reading for {len(missing)} of the page's {len(rows.lines)} lines "
                   f"({', '.join(missing)}) when asked again line by line; the page's readings are unchanged")
            row_results["error"] = f"review of {name} failed: {why}"
            row_results["lines"] = why
            notes.append(f"{name}: {why}")
            continue
        answered.update(got)
        text = "\n".join(f"{r.id} | {answered[r.id]}" for r in rows.lines)
        _made, said = await asyncio.to_thread(
            correct_lines, db, document_id=artifact.document_id, text=text, artifact_id=artifact.id,
            run_id=run_id, library_path=library_path)
        notes.append(f"{name}: {said}")
        row_results["lines"] = said
