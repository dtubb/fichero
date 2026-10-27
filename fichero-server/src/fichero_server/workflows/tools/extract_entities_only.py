"""Register step-2 entity extraction for already-imported documents.

This workflow node mirrors the discrete step-1 import-artifacts stage:
select the already-imported page/file documents, recover the step-1
transcription artifacts, run only the shared entity-name extractor, and
persist KnowledgeEntity rows via the existing upsert path.

It intentionally does NOT write claims, catalogue artifacts, merge rows,
or later KG graph stages. Those belong to follow-up stages under #1757.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import sys
import time
import traceback
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Iterator

from fichero_server.db import db_manager
from fichero_server.execution.cancellation import WorkflowCancelled, cancellation_requested
from fichero_server.models.knowledge import KnowledgeEntity
from fichero_server.llm import LLMConfig, chat_structured_with_fallback
from fichero_server.loaders.rtf_text import to_plain_text
from fichero_server.llm.language_policy import (
    UNKNOWN,
    configured_policy,
    prompt_language,
    resolve_language,
)
from fichero_server.models import Artifact, Document
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools._entity_writer import _ENTITY_UPSERT_LOCK, run_attribution, upsert_entity
from fichero_server.workflows.tools.extract_all import (
    _EntitiesOnly,
    _build_entity_only_instructions,
    _entities_only_is_empty,
    _entity_schema_in_prompt,
)
from fichero_server.workflows.tools.extractors import _SECTIONS, name_spans, write_mentions
from fichero_server.workflows.tools.import_artifacts import _coerce_documents
from fichero_server.workflows.tools._together import ahead_of_run, extract_width
from fichero_server.workflows.tools.progress import emit_progress_event
from fichero_server.workflows.tools.sources import files_tool
from fichero_server.workflows.tools._workflow_change_emit import emit_workflow_kg_changes
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

#: How long one page's names may take (#6236), for its model or spaCy call and again for writing its names. Pages take
#: 1-4 s; past this the page is skipped with a worded stall and left un-noted, so Run again on what was missed offers it.
#: The writing stops between names. ponytail: a spaCy call past it can't be stopped (one nlp() call in a worker thread);
#: it is one page's pipeline, measured under 0.1 s, so the thread ends soon after; a killable spaCy process if not.
NAMES_PAGE_SECONDS = 300.0


def _stalled(doc_name: str, what: str) -> str:
    """The stall's words, and every thread's stack in the log, so the spin names itself (#6236)."""
    logger.warning("extract_entities_only: %s on %s passed %s s; threads:\n%s", what, doc_name, NAMES_PAGE_SECONDS,
                   "\n".join(f"thread {ident}:\n{''.join(traceback.format_stack(frame))}"
                             for ident, frame in sys._current_frames().items()))
    return (f"names on page {doc_name} took over {NAMES_PAGE_SECONDS:g} s; skipped, as {what} did not finish in "
            f"that time, so Run again on what was missed offers it")

_TRANSCRIPTION_ARTIFACT = "transcription"
#: Why a selected document was left out of a run: it has no text to read names from.
NO_TEXT = ("no text: no line of its working pass has a reading, and it has no page text or "
           "transcription")
_ENTITY_TYPES = {
    section["schema_key"]: section["entity_type"]
    for section in _SECTIONS
    # Dates are claim-only (entity_type None — no canonical entity row), so
    # they are NOT upserted here; stage 3 extracts date claims directly.
    if section.get("schema_key") in {"people", "places", "organizations", "events"}
}


# Which sections a run is asked for (#4667). Default: everything, i.e. what
# every existing preset already gets. A preset that wants a timeline asks for
# "events,dates" and gets a run that is both faster and quieter — no places,
# no organizations, no per-person claim loop over a page it will never plot.
#
# Named explicitly rather than inferred: "extract just events" that silently
# also wrote date claims would be a surprise, and "extract just events" that
# silently did NOT would produce a timeline with no time axis.
_ALL_SECTION_KEYS = ("people", "places", "organizations", "events", "dates")


# Local NER providers run on-device and are NOT language models — they must go
# to the spaCy NER path, not the LLM chat factory. A run-level model override of
# "spacy/es_core_news_sm" set llm_config.provider="spacy", which then reached
# chat_structured_with_fallback and died with "Unknown LLM provider: 'spacy'"
# (Daniel, live). Detected here and routed to get_ner_provider instead.
_LOCAL_NER_PROVIDERS = frozenset({"spacy", "spacy_ner", "transformers"})

# spaCy's fichero entity types → the section keys this stage upserts. `concept`,
# `date` and `money` have no entity-row section here (dates are claim-only), so
# they are dropped, exactly as the LLM path drops everything but these four.
_NER_TYPE_TO_SECTION = {
    "person": "people",
    "location": "places",
    "organization": "organizations",
    "event": "events",
}


@contextmanager
def _one_page_of_writes(db):
    """A page's names are written in one short transaction, and each name's vector once, after it commits (#6236,
    #6212). Never one transaction for the step: 55k new rows in one ran an 8 GB Mac out of memory. A new row is
    still a plain INSERT (`Database.save`), so the next name on the page matches it as before. The upsert lane is
    taken before the transaction's gate, the order a single upsert takes them in, so the two never cross."""
    with _ENTITY_UPSERT_LOCK, db.defer_embeddings(), db.transaction():
        yield
    db.flush_deferred_embeddings()


def _is_local_ner_provider(provider: object) -> bool:
    return str(provider or "").strip().lower() in _LOCAL_NER_PROVIDERS


def _requested_sections(raw: object) -> set[str]:
    """Parse the ``entity_types`` config into a set of section keys.

    Empty, missing, or "all" means every section. Unknown names are ignored
    rather than raising: a preset naming a section we retired should run the
    ones we still have, not fail the whole stage.
    """
    if raw is None:
        return set(_ALL_SECTION_KEYS)
    if isinstance(raw, str):
        parts = [part.strip().casefold() for part in raw.replace(";", ",").split(",")]
    elif isinstance(raw, (list, tuple, set)):
        parts = [str(part).strip().casefold() for part in raw]
    else:
        return set(_ALL_SECTION_KEYS)
    names = {part for part in parts if part}
    if not names or "all" in names:
        return set(_ALL_SECTION_KEYS)
    return {name for name in names if name in _ALL_SECTION_KEYS} or set(_ALL_SECTION_KEYS)


_ENTITY_TYPES_CONFIG = {
    "entity_types": {
        "type": "string",
        "title": "Sections",
        "description": (
            "Comma-separated sections to extract: people, places, "
            "organizations, events, dates. Blank or 'all' extracts every "
            "section. 'events,dates' is the timeline shape."
        ),
        "default": "all",
    },
    # Shared with extract_svo_only, which also spreads this dict into its own
    # config_schema — one field, both tools' node editors surface it. Same
    # shape as `llm_base.BASE_CONFIG_SCHEMA`'s "prompt".
    "prompt": {
        "type": "string",
        "description": "Custom extraction instructions",
        "x-group": "primary",
    },
}


def _normalize_raw_documents(raw_documents: Any) -> list[Any]:
    """Coerce workflow payloads into the list shape _coerce_documents expects.

    Some callers hand us a singleton dict/model instead of the usual
    Files.documents list. Treat that as one selected document rather than
    iterating the mapping keys and losing the selection.
    """
    if raw_documents is None:
        return []
    if isinstance(raw_documents, list):
        return raw_documents
    if isinstance(raw_documents, tuple):
        return list(raw_documents)
    return [raw_documents]


def _transcription_text(document: Document, db) -> str:
    """The document's transcription as PROSE — never as markup (#4666).

    A transcription edited in the app is stored as inline RTF source whenever
    the user applied any formatting (``ArtifactRichTextCodec``'s storage
    contract), and the reader strips that at display time
    (``api/routes/system/views.py``). Extraction did not: it read the same
    field raw, so a 17th-century Spanish page reached the model as

        {\\rtf1\\ansi\\ansicpg1252 … \\cf0 … se\\'f1or y deste puerto …

    The model dutifully echoed the escapes back, and "se\\'f1or" was persisted
    into the knowledge graph as the archive's own word for "señor". Every
    caller of this helper hands its result to an LLM, so the conversion belongs
    here, at the one boundary they share, rather than in each of them.
    """
    # And never as abbreviation markup either (#5651): `dha$.dicha` reaches the model as `dicha`. Each
    # line's expanded reading where it has one, else the text with the corpus's markup read
    # (`segment_readings.text_for_names`).
    from fichero_server.api.routes.document.segment_readings import (  # noqa: PLC0415
        document_text,
        text_for_names,
    )

    # The page's text is its working pass's lines, each line's counting reading (`source.point.text-is-
    # derived`): the one derived-text path every surface reads. A page whose words live only there (an
    # imported page archive, a page read line by line) has no `page_content` until the cache is filled,
    # and was skipped as if it were blank. The stored fields below are the fallback for a page with no
    # pass.
    derived = document_text(db, document.id).text
    if derived and derived.strip():
        return text_for_names(db, document.id, derived.strip()).strip()

    metadata = dict(document.metadata or {})
    raw_transcription = metadata.get("transcription")
    if isinstance(raw_transcription, str) and raw_transcription.strip():
        return text_for_names(db, document.id, to_plain_text(raw_transcription).strip()).strip()

    if isinstance(document.page_content, str) and document.page_content.strip():
        return text_for_names(db, document.id, to_plain_text(document.page_content).strip()).strip()

    for artifact in db.query(
        Artifact,
        document_id=document.id,
        artifact_type=_TRANSCRIPTION_ARTIFACT,
    ):
        if isinstance(artifact.content, str) and artifact.content.strip():
            return text_for_names(db, document.id, to_plain_text(artifact.content).strip()).strip()
    return ""


def _iter_records(
    documents: list[Document], db, left_out: list[dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield one extraction record at a time, reading each document's text
    only when the extraction loop is ready for it (#4379).

    This used to build a list: it walked EVERY selected document, pulled the
    full transcription (page_content, metadata, or the transcription
    artifact), and returned one list of records — and only then started
    extracting, one record at a time under a semaphore. Concurrency was
    bounded; input residency was not. Peak memory was the whole corpus's text
    held for the entire run, no matter how carefully the calls were paced,
    which is the shape that gets a process shed under memory pressure on a
    machine that is already swapping. A named-entity run over a real corpus
    could not survive its own duration.

    A generator makes the resident text a bounded prefix instead of the whole
    selection, so peak no longer scales with corpus size.

    ponytail: the upstream source node still hands this tool fully-hydrated
    `Document` rows, so the selection's own `page_content` is resident before
    the tool starts — this bounds the extraction copy, not the source
    hydration. Bounding that too means teaching the source/files node to emit
    document ids and hydrate lazily, which is a cross-tool change to the
    workflow source contract and is deliberately not in this fix.

    A document with no text at all is never skipped in silence: it is appended to ``left_out`` with
    the reason, so a run that read nothing cannot report itself done.
    """
    for index, document in enumerate(documents):
        text = _transcription_text(document, db)
        if not text:
            if left_out is not None:
                left_out.append({"document_id": document.id, "name": document.name, "why": NO_TEXT})
            logger.warning("extract_entities_only: %s left out: %s", document.name or document.id, NO_TEXT)
            continue
        yield {
            "index": index,
            "doc_id": document.id,
            "doc_name": document.name,
            "text": text,
        }


def _records_for_documents(
    documents: list[Document], db, left_out: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Materialise every record up front.

    Only for callers that must traverse the record set more than once —
    ``extract_svo_only`` cross-references entities by document, computes the
    selected-id set, and only then extracts, so a single-pass generator does
    not fit it. Prefer :func:`_iter_records` everywhere else: this holds the
    whole selection's text resident for the life of the call, which is the
    memory shape #4379 was about.
    """
    return list(_iter_records(documents, db, left_out))


@register_tool(
    name="extract_entities_only",
    display_name="Extract Entities",
    description="Extract and persist entity rows only from existing transcription artifacts",
    category="llm",
    icon="person.text.rectangle",
    color="purple",
    uses_llm=True,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            required=False,
            description="Selected document metadata, typically from Files.documents",
        ),
        PortDef(
            id="barrier",
            name="Barrier (sync)",
            port_type="input",
            data_type=DataType.ANY,
            required=False,
            description="Optional dependency-only input used by chained presets.",
        ),
    ],
    output_ports=[
        PortDef(
            id="summary",
            name="Summary",
            port_type="output",
            data_type=DataType.JSON,
            description="Created/reused entity counts",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of selected atomic documents processed",
        ),
    ],
    sort_order=36,
    config_schema=_ENTITY_TYPES_CONFIG,
)
async def extract_entities_only(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Run the shared Stage-1 entity extractor and persist entity rows only."""
    from fichero_server.checking.tie_text import line_spans
    library_path = state.get("library_path", "")
    if not library_path:
        return {
            "summary": {
                "documents_processed": 0,
                "entity_mentions_processed": 0,
                "entities_created": 0,
                "entities_reused": 0,
                "entities_suppressed": 0,
            },
            "count": 0,
        }

    db = db_manager.get_database(library_path)
    raw_documents = _normalize_raw_documents(inputs.get("documents"))
    if not raw_documents:
        fallback = await files_tool(
            inputs={},
            state=state,
            llm_config=LLMConfig(provider="", model=""),
        )
        raw_documents = _normalize_raw_documents(fallback.get("documents"))

    documents = _coerce_documents(raw_documents, db, library_path)
    if not documents and raw_documents:
        fallback = await files_tool(
            inputs={},
            state=state,
            llm_config=LLMConfig(provider="", model=""),
        )
        fallback_documents = _normalize_raw_documents(fallback.get("documents"))
        if fallback_documents != raw_documents:
            documents = _coerce_documents(fallback_documents, db, library_path)
    # Bounded lookahead of exactly ONE record, so "did anything have text?"
    # can be answered without reading the whole selection (#4379).
    # Every document with no text is named, with why, in the summary (`left_out`): the step must never
    # say done with nothing done.
    left_out: list[dict[str, Any]] = []
    records = _iter_records(documents, db, left_out)
    first_record = next(records, None)
    if first_record is None:
        shown = "; ".join(f"{e['name'] or e['document_id']} ({e['why']})" for e in left_out[:3])
        more = f"; and {len(left_out) - 3} more" if len(left_out) > 3 else ""
        return {
            # A run that read nothing fails, saying why: "completed" over 0 pages read as success (#5521).
            "error": (f"no names found: none of the {len(documents)} selected pages has a reading to find them in: "
                      f"{shown}{more}" if documents else "no names found: no page was selected"),
            "summary": {
                "documents_processed": 0,
                "entity_mentions_processed": 0,
                "entities_created": 0,
                "entities_reused": 0,
                "entities_suppressed": 0,
                "documents_left_out": len(left_out),
                "left_out": left_out,
            },
            "count": 0,
        }
    records = itertools.chain([first_record], records)

    # #2092. Was `_build_entity_only_instructions(inputs.get("output_language",
    # "auto"))` — the unresolved config value, so the default wrote "Write in
    # auto." into the system prompt and the library's language policy never
    # reached entity extraction. Resolved per document; instructions are cached
    # per language so a single-language corpus still builds one string.
    requested_sections = _requested_sections(inputs.get("entity_types"))
    policy = configured_policy()
    # A user-supplied prompt replaces the per-language built instruction
    # outright (same override-or-default contract as analyze/entities/
    # transcribe) rather than being resolved per document language — an
    # explicit override is a deliberate instruction, not something the
    # language policy should still be allowed to swap out from under it.
    prompt_override = str(inputs.get("prompt") or "").strip() or None
    instructions_by_language: dict[str, str] = {}
    languages_used: dict[str, int] = defaultdict(int)
    from fichero_server.models.source_declarations import project_facts

    project_language = project_facts(db).language

    progress_callback = inputs.get("__progress_callback")
    max_in_flight = extract_width(llm_config)  # the step's cloud width for a hosted model, 3 for one served here
    extraction_sem = asyncio.Semaphore(max_in_flight)
    known_entity_ids = {entity.id for entity in db.query(KnowledgeEntity)}

    # spaCy (and any local NER provider) skips the LLM entirely — this is the
    # fix for "Unknown LLM provider: 'spacy'".
    use_local_ner = _is_local_ner_provider(getattr(llm_config, "provider", None))
    ner_provider = None
    if use_local_ner:
        from fichero_server.workflows.ner.providers import get_ner_provider

        ner_provider = get_ner_provider(
            getattr(llm_config, "provider", None), getattr(llm_config, "model", None)
        )

    asserted_by = run_attribution(getattr(llm_config, "provider", None), getattr(llm_config, "model", None),
                                  state.get("task_id"))
    mentions_processed = 0
    mentions_on_lines = 0
    created = 0
    reused = 0
    suppressed = 0
    # Progress totals the SELECTION, not the record count: streaming means the
    # number of documents that turn out to have text is unknown until the run
    # ends, and the selection size is the honest denominator for a progress
    # bar anyway. `documents_processed` below still counts only real work.
    total = len(documents)
    processed = 0

    async def start(item: tuple[int, dict[str, Any]]) -> dict[str, Any]:
        """What this page asks a model, started with the next pages' and awaited in page order
        (`runtime.cloud-extractors.pages-together`, #5955): its language and instructions, and, for a model, its
        call. The loop below writes what comes back."""
        _index, record = item
        resolution = resolve_language(
            requested=inputs.get("output_language"),
            document=documents[record["index"]],
            text=record["text"] or "",
            policy=policy,
            project_language=project_language,  # the project's, unless the page is clearly another (#5708)
        )
        languages_used[resolution.language or UNKNOWN] += 1
        instruction_key = prompt_language(resolution)
        instructions = instructions_by_language.get(instruction_key)
        if instructions is None:
            instructions = prompt_override or _build_entity_only_instructions(
                instruction_key
            )
            instructions_by_language[instruction_key] = instructions

        extraction = None
        if not use_local_ner:
            async with extraction_sem:
                try:
                    extraction = await asyncio.wait_for(chat_structured_with_fallback(
                        prompt=record["text"],
                        schema=_EntitiesOnly,
                        config=llm_config,
                        system=instructions,
                        include_schema_in_prompt=_entity_schema_in_prompt(llm_config),
                        permissive_guardrails=True,
                    ), NAMES_PAGE_SECONDS)
                except TimeoutError:
                    return {"resolution": resolution, "stalled": "the names model"}
        return {"resolution": resolution, "extraction": extraction}

    run_id = state.get("task_id", "")
    async for (index, record), pre in ahead_of_run(enumerate(records), start, max_in_flight):
        # The run's Stop takes effect between pages (`activity.run.stop-reaches-its-step`): the pages gone over keep their
        # names and their note (`page_finished`), and a start again goes on from the next.
        if cancellation_requested(run_id):
            raise WorkflowCancelled(run_id)
        doc_name = record.get("doc_name") or record.get("doc_id") or f"document-{index + 1}"
        await emit_progress_event(
            progress_callback,
            "file_start",
            "",
            f"Extract Entities {doc_name}",
            processed + 1,
            total,
            message=f"Extracting step-2 entities for {doc_name}",
        )

        resolution, extraction = pre["resolution"], pre.get("extraction")
        # (canonical_name, entity_type, aliases) to upsert, from whichever
        # extractor this run selected. The upsert loop below is shared.
        # The fourth element is where the name is written in the text (#5488): the local NER model's own
        # spans, or None for a language model's name, which is then found in the text as written.
        mentions: list[tuple[str, Any, list[str], list[tuple[int, int]] | None]] = []
        text = record["text"]
        spans = []
        if use_local_ner and "stalled" not in pre:
            try:
                spans = await asyncio.wait_for(ner_provider.extract(
                    record["text"], language=resolution.language
                ), NAMES_PAGE_SECONDS)
            except TimeoutError:
                pre = {**pre, "stalled": "spaCy"}
        if "stalled" in pre:
            left_out.append({"document_id": record["doc_id"], "name": doc_name,
                             "why": _stalled(doc_name, pre["stalled"])})
            continue
        processed += 1
        if use_local_ner:
            for span in spans:
                section_key = _NER_TYPE_TO_SECTION.get(str(span.type))
                if section_key is None or section_key not in requested_sections:
                    continue
                entity_type = _ENTITY_TYPES.get(section_key)
                if entity_type is None:
                    continue
                written = (span.metadata or {}).get("spans") or (
                    [span.source_offsets] if span.source_offsets else [])
                mentions.append((
                    str(span.name or "").strip(), entity_type, list(span.aliases or []),
                    [(int(s), int(e)) for s, e in written if 0 <= int(s) < int(e) <= len(text)],
                ))
            if not mentions and len(record["text"].strip()) > 200:
                logger.warning(
                    "extract_entities_only: spaCy NER found no entities for %s (%d chars)",
                    doc_name,
                    len(record["text"].strip()),
                )
        else:
            if _entities_only_is_empty(extraction) and len(record["text"].strip()) > 200:
                logger.warning(
                    "extract_entities_only: empty entity result for %s (%d chars)",
                    doc_name,
                    len(record["text"].strip()),
                )
            for section_key, entity_type in _ENTITY_TYPES.items():
                if section_key not in requested_sections:
                    continue
                for entity in getattr(extraction, section_key, []):
                    mentions.append(
                        (
                            str(entity.name or "").strip(),
                            entity_type,
                            list(getattr(entity, "aliases", []) or []),
                            None,
                        )
                    )

        written_entity_ids: list[str] = []
        lines = line_spans(db, record["doc_id"], text) if mentions else []
        # The writing has the page's time limit too, checked between names, so it stops for real: it runs here, on
        # the step's own thread, and holds the DB writer while it does (#6236's spin was here, not in the model).
        writing_until = time.monotonic() + NAMES_PAGE_SECONDS
        stalled_writing = False
        with _one_page_of_writes(db):
            for canonical_name, entity_type, aliases, written in mentions:
                if not canonical_name:
                    continue
                if time.monotonic() > writing_until:
                    stalled_writing = True
                    break
                mentions_processed += 1
                entity_id = upsert_entity(
                    db,
                    canonical_name=canonical_name,
                    entity_type=entity_type,
                    aliases=aliases,
                    source_document_id=record["doc_id"],
                    asserted_by=asserted_by,
                )
                if entity_id is None:
                    suppressed += 1
                    continue
                written_entity_ids.append(entity_id)
                # Each place the name is written is a mention, on its line when the page is tied (#5488).
                mentions_on_lines += write_mentions(
                    db, entity_id, record["doc_id"], text,
                    written if written is not None else name_spans(text, [canonical_name, *aliases]),
                    lines, name=canonical_name, page_label=None,
                )
                if entity_id in known_entity_ids:
                    reused += 1
                else:
                    known_entity_ids.add(entity_id)
                    created += 1

        if written_entity_ids:
            emit_workflow_kg_changes(
                str(db.path.parent),
                entity_ids=written_entity_ids,
                claim_ids=[],
                document_ids=[record["doc_id"]],
            )

        if stalled_writing:
            processed -= 1
            left_out.append({"document_id": record["doc_id"], "name": doc_name,
                             "why": _stalled(doc_name, "writing its names")})
            continue

        from fichero_server.recipes.done import page_finished

        page_finished(db, state.get("task_id"), record["doc_id"])  # this page is done, names or none, whatever happens next
        await emit_progress_event(
            progress_callback,
            "file_complete",
            "",
            f"Extract Entities {doc_name}",
            processed,
            total,
            message=f"Extracted step-2 entities for {doc_name}",
        )

    stalls = [e["why"] for e in left_out if "took over" in e["why"]]
    summary = {
        "documents_processed": processed,
        "entity_mentions_processed": mentions_processed,
        # Names written on a line of a page tied to its lines (#5488).
        "mentions_on_lines": mentions_on_lines,
        "entities_created": created,
        "entities_reused": reused,
        "entities_suppressed": suppressed,
        # Per-document language actually used, `unknown` included (#2092).
        "languages_used": dict(languages_used),
        # The selected documents with no text, each with why: never skipped in silence.
        "documents_left_out": len(left_out),
        "left_out": left_out,
    }
    if stalls and not processed:  # every page stalled: a run that read nothing fails, saying why (#5521)
        return {"error": f"no names found: {stalls[0]}" + (f"; and {len(stalls) - 1} more" if len(stalls) > 1 else ""),
                "summary": summary, "count": 0}
    return {"summary": summary, "count": processed}
