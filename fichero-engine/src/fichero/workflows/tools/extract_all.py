"""
Combined entity extractor — one LLM call per page returns all six entity
types (people, places, organizations, dates, events, keywords) as a
single JSON payload.

Replaces the six separate extractor nodes (people_extract, places_extract,
…) for the speed-optimised default Catalogue preset. On Apple Intelligence
this is the single biggest win: 6× fewer LLM calls per page, same output
shape going into the rest of the pipeline (writes per-type KG claims +
per-page artifacts that the existing folder_cleanup tools consume).

Per-page records flow honored: when the upstream Aggregate node passes
records=[{doc_id, text}, ...], we save claims+artifacts to each page
doc_id. Falls back to container.id when records absent (legacy path).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from fichero.db import db_manager
from fichero.llm import LLMConfig, chat_structured_with_fallback
from fichero.models import Artifact, Document, DocType, FileType
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.catalogue import _resolve_write_target
from fichero.workflows.tools.extractors import (
    _SECTIONS,
    _split_into_pages,
    _render_section_markdown,
    _write_kg_rows,
)
from fichero.workflows.tools.llm_base import (
    BASE_CONFIG_SCHEMA,
    BASE_OUTPUT_PORTS,
    merge_config_schema,
    merge_ports,
)
from fichero.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)


# Sub-chunk budget — small on-device models (Apple Intelligence's ~4K
# token window) can't accept a full page of dense OCR; 3K chars leaves
# room for the combined-prompt overhead.
_MAX_CHUNK_CHARS = 3000


_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Aggregated text to extract from.",
        ),
        PortDef(
            id="records",
            name="Records",
            port_type="input",
            data_type=DataType.ARRAY,
            required=False,
            description=(
                "Optional per-page records [{doc_id, text}, ...] from "
                "an upstream Aggregate node. When present, claims + "
                "artifacts save to PAGE doc_id (page-level KG)."
            ),
        ),
    ],
    [],
)


_LANGUAGE_CONFIG = {
    "output_language": {
        "type": "string",
        "default": "auto",
        "description": (
            "Output language. 'auto' detects from the source text "
            "(English / Spanish today)."
        ),
    },
}


# SVO predicate fields shared across every entity-bearing section in
# the combined extract_all call. Mirrors the per-section schemas in
# extractors.py (`_SVO_VERB_FIELD` / `_SVO_OBJECT_FIELD`) so the
# combined call now produces structurally-identical output to the
# single-section path. (#1113 — without this the combined call left
# claim.predicate_verb / object_phrase NULL on every row.)
_VERB = Field(
    default="",
    description=(
        "Predicate verb or verb phrase. The entity name is the implicit "
        "subject — do NOT repeat it. Examples: 'is', 'was', 'served as', "
        "'wrote', 'founded', 'is located in'."
    ),
)
_OBJ = Field(
    default="",
    description=(
        "Rest of the predicate after the verb — a noun phrase or "
        "clause. Examples: 'the alcalde of Popayán', 'a gold-mining "
        "region in the Chocó', 'the deed of sale'."
    ),
)


class _Person(BaseModel):
    name: str
    verb: str = _VERB
    object: str = _OBJ


class _Place(BaseModel):
    name: str
    alternative_spellings: list[str] = Field(default_factory=list)
    verb: str = _VERB
    object: str = _OBJ


class _Organization(BaseModel):
    name: str
    alternative_spellings: list[str] = Field(default_factory=list)
    verb: str = _VERB
    object: str = _OBJ


class _DateItem(BaseModel):
    date: str = Field(description="as written in the document")
    date_normalized: str = Field(
        description="YYYY-MM-DD (range YYYY-MM-DD/YYYY-MM-DD; month-only YYYY-MM; year-only YYYY)"
    )
    verb: str = _VERB
    object: str = _OBJ


class _Event(BaseModel):
    event: str = Field(description="Title Case noun phrase naming the event")
    date: str | None = Field(default=None, description="YYYY-MM-DD when stated, else null")
    verb: str = _VERB
    object: str = _OBJ


class _Extraction(BaseModel):
    """Schema for the combined extract_all call. Maps 1:1 onto the six
    section keys downstream tools (folder_cleanup, catalogue) expect."""

    people: list[_Person] = Field(default_factory=list)
    places: list[_Place] = Field(default_factory=list)
    organizations: list[_Organization] = Field(default_factory=list)
    dates: list[_DateItem] = Field(default_factory=list)
    events: list[_Event] = Field(default_factory=list)
    keywords: list[str] = Field(
        default_factory=list,
        description="descriptive keywords capturing themes, subjects, time periods, and concepts",
    )


def _build_instructions(output_language: str) -> str:
    """System instructions for the structured-output call. The schema
    itself is enforced at decode time (DynamicGenerationSchema on Apple,
    response_format=json_schema on LangChain providers); these
    instructions cover the things the schema can't express:
    - the language for prose fields
    - the don't-invent / cover-every-occurrence policy
    - per-section prose conventions reused from the individual extractors.
    """
    section_lines: list[str] = []
    for section in _SECTIONS:
        if section["name"] in {
            "rivers_extract",
            "mines_extract",
            "properties_extract",
            "legal_references_extract",
        }:
            continue
        section_lines.append(
            f"- {section['schema_key']}: {section['instruction']}"
        )
    section_block = "\n".join(section_lines)

    return (
        f"You are an expert archivist extracting structured entities "
        f"from a document. Cover every occurrence in the source. Only "
        f"include facts the text supports — do not speculate or invent. "
        f"Write prose fields in {output_language}.\n\n"
        f"Section-specific guidance:\n{section_block}"
    )


# Error-message fragments that mark a failure as systemic — it won't
# resolve by continuing, so every remaining chunk fails identically.
# Covers the canonical 0.0.2 case (no $large configured → the
# Apple-Intelligence fallback re-raises the same guardrail/decode error
# on every page) plus billing/network failures.
_SYSTEMIC_SIGNATURES = (
    "401", "403", "402",
    "quota", "rate limit", "rate_limit",
    "not configured", "no $large", "$large",
    "connection", "unreachable", "timed out", "timeout",
    "api key", "unauthorized", "forbidden",
)

# Fraction of chunks that must fail before we treat the run as systemically
# broken rather than partially degraded.
_SYSTEMIC_FAIL_FRACTION = 0.8


def _record_text(record: Any) -> str:
    if not isinstance(record, dict):
        return ""
    text = record.get("text")
    return text.strip() if isinstance(text, str) else ""


def _normalize_records(records: Any) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        text = _record_text(record)
        if not text:
            continue
        normalized.append({
            "index": record.get("index", index) if isinstance(record, dict) else index,
            "doc_id": str(record.get("doc_id") or "") if isinstance(record, dict) else "",
            "text": text,
        })
    return normalized


def _records_from_selected_documents(state: State) -> list[dict[str, Any]]:
    """Recover selected PDF/page text when upstream transcription is empty."""
    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    if not library_path or not selected_doc_ids:
        return []

    try:
        db = db_manager.get_database(library_path)
    except Exception as exc:
        logger.warning("extract_all: could not open library for text recovery: %s", exc)
        return []

    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_doc(doc: Document) -> None:
        if doc.id in seen:
            return
        seen.add(doc.id)
        text = (doc.page_content or "").strip()
        if text:
            records.append({
                "index": len(records),
                "doc_id": doc.id,
                "text": text,
            })

    def visit(doc: Document) -> None:
        if doc.doc_type == DocType.folder:
            for child in db.query(Document, parent_id=doc.id):
                visit(child)
            return
        if doc.file_type == FileType.pdf:
            pages = db.query(Document, parent_id=doc.id, doc_type=DocType.page)
            if pages:
                for page in sorted(pages, key=lambda p: p.sequence or 0):
                    add_doc(page)
                return
        add_doc(doc)

    for doc_id in selected_doc_ids:
        doc = db.get(Document, doc_id)
        if doc is not None:
            visit(doc)
    return records


def _recover_text_and_records(
    inputs: dict[str, Any], state: State,
) -> tuple[str, list[dict[str, Any]]]:
    """Return usable extraction text + per-page records from all known sources."""
    records = _normalize_records(inputs.get("records"))
    raw_text = inputs.get("text")
    text = raw_text.strip() if isinstance(raw_text, str) else ""
    if not text and records:
        text = "\n\n".join(record["text"] for record in records)
    if text:
        return text, records

    outputs = state.get("outputs", {}) or {}
    for node_id in ("transcribe", "aggregate", "files-source"):
        node_output = outputs.get(node_id)
        if not isinstance(node_output, dict):
            continue
        records = _normalize_records(node_output.get("records"))
        if records:
            return "\n\n".join(record["text"] for record in records), records
        node_text = node_output.get("text")
        if isinstance(node_text, str) and node_text.strip():
            return node_text.strip(), []

    parallel_records: list[dict[str, Any]] = []
    parallel = state.get("parallel_results", {}) or {}
    for results in parallel.values():
        if not isinstance(results, list):
            continue
        for item in sorted(
            (r for r in results if isinstance(r, dict)),
            key=lambda r: r.get("index", 0),
        ):
            if not item.get("success"):
                continue
            result = item.get("result")
            if not isinstance(result, dict):
                continue
            page_records = _normalize_records(result.get("page_records"))
            if page_records:
                parallel_records.extend(page_records)
                continue
            node_text = result.get("text")
            if isinstance(node_text, str) and node_text.strip():
                parallel_records.append({
                    "index": item.get("index", len(parallel_records)),
                    "doc_id": "",
                    "text": node_text.strip(),
                })
    if parallel_records:
        return "\n\n".join(record["text"] for record in parallel_records), parallel_records

    selected_records = _records_from_selected_documents(state)
    if selected_records:
        return "\n\n".join(record["text"] for record in selected_records), selected_records
    return "", []


def _classify_systemic_error(
    errors: list[str], n_chunks: int
) -> str | None:
    """Decide whether a batch of chunk errors is *systemic* (#1060).

    Returns the representative cause string when the failure won't resolve
    by continuing — caller should set result["error"] so the builder
    raises SystemicErrorDetected and aborts the run. Returns None for
    genuinely-partial failures (a minority of sparse pages), which stay
    warn-and-continue.

    Two systemic signals:
    - an explicit infra signature (401/403, quota, "$large not configured",
      connection) present in any error, once at least half the chunks failed;
    - a high fraction of chunks failing, or nearly all chunks failing with
      the *same* message (the $large-unconfigured / provider-down pattern,
      where every page re-raises an identical error).
    """
    if not errors or n_chunks <= 0:
        return None

    fail_fraction = len(errors) / n_chunks
    infra_hit = next(
        (e for e in errors
         if any(sig in e.lower() for sig in _SYSTEMIC_SIGNATURES)),
        None,
    )
    most_common, count = Counter(errors).most_common(1)[0]
    repetitive = count / n_chunks >= _SYSTEMIC_FAIL_FRACTION

    if (
        fail_fraction >= _SYSTEMIC_FAIL_FRACTION
        or repetitive
        or (infra_hit and fail_fraction >= 0.5)
    ):
        return infra_hit or most_common
    return None


async def extract_all(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Combined extractor — one LLM call per page returns all 6 types."""
    text, recovered_records = _recover_text_and_records(inputs, state)
    if not text:
        return {"text": "", "value": {}, "error": "No text input"}

    from fichero.lang_detect import resolve_output_language
    output_language = resolve_output_language(
        inputs.get("output_language"), text, default="English"
    )

    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    # Use the write-target helper so single-file selections still get
    # KG entities/claims persisted on the file itself (#1105). Variable
    # kept as `container` for diff-friendliness.
    container = _resolve_write_target(selected_doc_ids, library_path)

    # Per-page chunks via records (preferred) or text-split fallback.
    records_input = recovered_records
    page_doc_ids: list[str | None] = []
    if records_input and isinstance(records_input, list):
        chunks = []
        for rec in records_input:
            if not isinstance(rec, dict):
                continue
            chunks.append(str(rec.get("text") or ""))
            page_doc_ids.append(str(rec.get("doc_id") or "") or None)
        if not chunks:
            chunks = _split_into_pages(text)
            page_doc_ids = [None] * len(chunks)
    else:
        chunks = _split_into_pages(text)
        page_doc_ids = [None] * len(chunks)

    is_per_page = any(pid for pid in page_doc_ids)
    instructions = _build_instructions(output_language)

    chunk_errors: list[str] = []
    # Per-page error tracking — when a chunk fails, we write an
    # `extraction_error` artifact on the page doc so the user can see
    # WHY a page came back empty (#800, #829).
    page_errors: list[str | None] = [None] * len(chunks)
    # Per-LLM-call wall-clock timings (#1037) — extract_all on a 15-page
    # PDF can run 20+ minutes; without per-call timing a slow run is
    # indistinguishable from a stuck one. Includes sub-chunk calls.
    chunk_timings: list[float] = []

    # Concurrency throttle for Apple Intelligence calls (#962 follow-up).
    # Apple Intelligence is a single-instance on-device model; firing
    # asyncio.gather() over 15+ chunks lets concurrent fm-bridge processes
    # compete for grammar-decoder state and thrash the local sampler,
    # which produces the "terminated generation early — Failed to
    # deserialize a Generable type" symptom on a non-trivial fraction of
    # chunks (Daniel reported 2/15 fails on tubb2020shift Preface).
    #
    # Cap at 3 concurrent — enough to keep the GPU busy without
    # serializing-by-default, but well below the thrash threshold.
    # Cloud-model chunks aren't affected by this because LangChain's
    # async paths don't hit fm-bridge; the semaphore still acquires
    # but the contention is on the upstream provider's rate limit,
    # not our local GPU. Make it tunable via env for future profiling.
    import os
    max_in_flight = int(os.environ.get("FICHERO_EXTRACT_MAX_IN_FLIGHT", "3"))
    extraction_sem = asyncio.Semaphore(max_in_flight)

    async def _extract_one(idx: int, chunk_text: str) -> dict[str, list]:
        # Sub-chunk if the page exceeds the small-model window. Apple
        # Intelligence's on-device window is ~4K tokens; chunks above
        # _MAX_CHUNK_CHARS get split and merged section-by-section.
        if len(chunk_text) > _MAX_CHUNK_CHARS:
            sub_chunks = [
                chunk_text[i:i + _MAX_CHUNK_CHARS]
                for i in range(0, len(chunk_text), _MAX_CHUNK_CHARS)
            ]
            sub_results = await asyncio.gather(
                *[_extract_one(-1, s) for s in sub_chunks]
            )
            merged: dict[str, list] = {}
            for sr in sub_results:
                for k, v in sr.items():
                    merged.setdefault(k, []).extend(v)
            return merged

        # Grammar-constrained call. On Apple Intelligence this routes
        # through fm-bridge's structured mode; on frontier providers
        # through LangChain's with_structured_output. Either way the
        # decoder cannot emit invalid JSON — the entire prompt-and-parse
        # failure class (Unterminated string, single-quoted JSON, prose
        # before/after the object) is gone (#799/#819 / #838 follow-up).
        # chat_structured_with_fallback escapes to $large on Apple's
        # on-device guardrail refusal, keeping the local-first default.
        call_start = time.monotonic()
        try:
            async with extraction_sem:
                extraction = await chat_structured_with_fallback(
                    prompt=chunk_text,
                    schema=_Extraction,
                    config=llm_config,
                    system=instructions,
                    # Apple Intelligence has a ~4K window; the schema is
                    # already enforced at decode time, so the auto-injected
                    # schema dump in the prompt is wasted tokens. Our system
                    # instructions cover behavior; let the grammar carry the
                    # shape (#843).
                    include_schema_in_prompt=False,
                    permissive_guardrails=True,
                )
        except Exception as exc:
            elapsed = time.monotonic() - call_start
            chunk_timings.append(elapsed)
            msg = f"structured LLM call failed: {exc}"
            logger.error(
                f"extract_all chunk {idx} failed after {elapsed:.1f}s "
                f"({len(chunk_text)} chars) — {msg}"
            )
            chunk_errors.append(str(exc))
            if idx >= 0:
                page_errors[idx] = msg
            return {}

        elapsed = time.monotonic() - call_start
        chunk_timings.append(elapsed)
        logger.info(
            f"extract_all chunk {idx} extracted in {elapsed:.1f}s "
            f"({len(chunk_text)} chars)"
        )

        # Pydantic instance → dict for the existing per-section pipeline
        # (KG writer, markdown renderer). Use mode="json" so URL-ish
        # primitives roundtrip as strings.
        return {
            "people": [p.model_dump(mode="json") for p in extraction.people],
            "places": [p.model_dump(mode="json") for p in extraction.places],
            "organizations": [
                o.model_dump(mode="json") for o in extraction.organizations
            ],
            "dates": [d.model_dump(mode="json") for d in extraction.dates],
            "events": [e.model_dump(mode="json") for e in extraction.events],
            "keywords": list(extraction.keywords),
        }

    chunk_results: list[dict[str, list]] = await asyncio.gather(
        *[_extract_one(i, c) for i, c in enumerate(chunks)]
    )

    # Per-run timing summary (#1037) — tells slow-but-working apart from
    # stuck, and points at the slowest chunk for follow-up profiling.
    if chunk_timings:
        total_s = sum(chunk_timings)
        logger.info(
            f"extract_all: {len(chunk_timings)} LLM calls over "
            f"{len(chunks)} chunks — total {total_s:.1f}s, "
            f"slowest {max(chunk_timings):.1f}s, "
            f"avg {total_s / len(chunk_timings):.1f}s"
        )

    # Build per-section per-chunk lists for downstream save / markdown.
    per_section_chunks: dict[str, list[list[Any]]] = {
        s["schema_key"]: [] for s in _SECTIONS
    }
    for cr in chunk_results:
        for section in _SECTIONS:
            key = section["schema_key"]
            per_section_chunks[key].append(cr.get(key, []))

    # Write errors and KG saves whenever we have a container/library —
    # even if every chunk failed, the per-page extraction_error
    # artifacts are valuable for diagnosis. The successful-data saves
    # below are guarded by `any(chunk_results)`.
    if container and library_path:
        try:
            db = db_manager.get_database(library_path)
            # Append-only artifact writes funnel through the
            # single-writer queue (#1000 Phase 2). KG entity/claim
            # writes (_write_kg_rows) stay direct — they're
            # read-modify-write and need immediate consistency for the
            # upsert dedup, so they can't be queued async.
            db_writer = db_manager.get_db_writer(library_path)
            for section in _SECTIONS:
                key = section["schema_key"]
                # Skip sections that aren't in the default preset's
                # combined output (we filtered them in the prompt too).
                if section["name"] in {
                    "rivers_extract",
                    "mines_extract",
                    "properties_extract",
                    "legal_references_extract",
                }:
                    continue
                section_chunks = per_section_chunks.get(key, [])
                # KG write — per-page provenance.
                for page_idx, (chunk_text, items, page_doc_id) in enumerate(
                    zip(chunks, section_chunks, page_doc_ids)
                ):
                    if not items:
                        continue
                    page_label = f"Page {page_idx + 1}" if len(chunks) > 1 else None
                    excerpt = chunk_text[:500] if chunk_text else None
                    target_doc_id = page_doc_id or container.id
                    _write_kg_rows(
                        db, section, items, target_doc_id,
                        page_label=page_label, source_excerpt=excerpt,
                        provider=getattr(llm_config, "provider", None),
                        model=getattr(llm_config, "model", None),
                    )

                # Per-page artifact saves so the inspector + cache see
                # the right shape.
                if is_per_page:
                    for chunk_text, items, page_doc_id in zip(
                        chunks, section_chunks, page_doc_ids
                    ):
                        if not page_doc_id or not items:
                            continue
                        page_md = _render_section_markdown(section, items)
                        db_writer.save(Artifact(
                            document_id=page_doc_id,
                            artifact_type=section["artifact"],
                            content=page_md,
                            data={"items": items},
                            provider=getattr(llm_config, "provider", None),
                            model=getattr(llm_config, "model", None),
                            run_id=state.get("task_id"),
                        ))
                else:
                    # Container-level fallback.
                    flat = [item for ic in section_chunks for item in ic]
                    if flat:
                        db_writer.save(Artifact(
                            document_id=container.id,
                            artifact_type=section["artifact"],
                            content=_render_section_markdown(section, flat),
                            data={"items": flat},
                            provider=getattr(llm_config, "provider", None),
                            model=getattr(llm_config, "model", None),
                            run_id=state.get("task_id"),
                        ))
            # Per-page extraction_error artifacts: write one for each
            # page whose chunk failed, so the inspector can show WHY a
            # page came back empty (instead of indistinguishable from
            # "model genuinely found nothing"). #800, #829.
            if is_per_page:
                for page_idx, (err, page_doc_id) in enumerate(
                    zip(page_errors, page_doc_ids)
                ):
                    if not err or not page_doc_id:
                        continue
                    db.save(Artifact(
                        document_id=page_doc_id,
                        artifact_type="extraction_error",
                        content=(
                            f"Page {page_idx + 1}: extraction failed.\n"
                            f"{err}\n\n"
                            "Try re-running with a different model, or "
                            "split the page if it's unusually large."
                        ),
                        data={
                            "page_index": page_idx,
                            "error": err,
                            "tool": "extract_all",
                        },
                        provider=getattr(llm_config, "provider", None),
                        model=getattr(llm_config, "model", None),
                        run_id=state.get("task_id"),
                    ))
            # Drain the queued artifact writes before this node returns
            # — downstream folder-cleanup nodes read these artifacts.
            db_writer.flush()
            container.updated_at = datetime.now()
            db.save(container)
        except Exception as exc:
            logger.error(f"extract_all: KG/artifact save failed: {exc}")

    # Aggregate everything into the value/text payload.
    value: dict[str, list] = {}
    for section in _SECTIONS:
        key = section["schema_key"]
        flat = [item for c in per_section_chunks.get(key, []) for item in c]
        if flat:
            value[key] = flat

    text_parts: list[str] = []
    for section in _SECTIONS:
        if section["name"] in {
            "rivers_extract", "mines_extract",
            "properties_extract", "legal_references_extract",
        }:
            continue
        items = value.get(section["schema_key"], [])
        text_parts.append(_render_section_markdown(section, items))
    markdown = "\n\n".join(text_parts)

    result: dict[str, Any] = {"text": markdown, "value": value, "cached": False}
    # Fail-fast on systemic errors (#1060). When a high fraction of
    # chunks fail — or they all fail with the same signature ($large
    # unconfigured, 401/403, quota, provider unreachable) — continuing is
    # pointless: every remaining page fails identically and the run
    # grinds out an empty "successful" catalogue. Setting result["error"]
    # makes the builder raise SystemicErrorDetected and abort the run
    # with the real cause (builder.py converts a tool's "error" key into
    # a hard abort). Genuinely-partial failures (a minority of sparse
    # pages) stay warn-and-continue — the per-page extraction_error
    # artifacts written above tell the user which pages to re-run.
    if chunk_errors:
        systemic_cause = _classify_systemic_error(chunk_errors, len(chunks))
        if systemic_cause:
            result["error"] = (
                f"Extract All: {len(chunk_errors)}/{len(chunks)} LLM calls "
                f"failed with a systemic error — {systemic_cause}"
            )
        else:
            logger.warning(
                f"extract_all: {len(chunk_errors)}/{len(chunks)} chunks "
                f"failed (partial extraction continued)"
            )
    return result


register_tool(
    name="extract_all",
    display_name="Extract All Entities",
    description=(
        "Single-pass extraction of people, places, organisations, dates, "
        "events, and keywords. One LLM call per page returns all six "
        "types as JSON — 6× fewer calls than the per-type extractors, "
        "same downstream shape (KG claims + per-page artifacts)."
    ),
    category="llm",
    icon="square.grid.2x2",
    color="purple",
    uses_llm=True,
    supports_batch=False,
    supports_structured_output=True,
    input_ports=_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, _LANGUAGE_CONFIG),
    default_prompt=_build_instructions("English"),
    sort_order=5,
)(extract_all)
