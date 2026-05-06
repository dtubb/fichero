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
import json
import logging
from datetime import datetime
from typing import Any

from fichero.db import db_manager
from fichero.llm import LLMConfig, chat_with_fallback
from fichero.models import Artifact
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.catalogue import _resolve_container_doc
from fichero.workflows.tools.extractors import (
    _SECTIONS,
    _split_into_pages,
    _strip_fences,
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


def _build_combined_prompt(output_language: str) -> str:
    """One prompt asking for all six entity types in a single JSON
    response. Each section's per-section instruction is reused so the
    behaviour matches the individual extractors when run alone.
    """
    section_blocks: list[str] = []
    for section in _SECTIONS:
        # Skip the archive-specific extractors that aren't in the
        # default preset (rivers / mines / properties / legal_references).
        if section["name"] in {
            "rivers_extract",
            "mines_extract",
            "properties_extract",
            "legal_references_extract",
        }:
            continue
        item = section["item_shape"].replace("__LANG__", output_language)
        block = (
            f'"{section["schema_key"]}": [{item}]\n'
            f'  // {section["instruction"]}\n'
        )
        section_blocks.append(block)

    schema = "{\n  " + "  ".join(section_blocks) + "}"

    return (
        f"You are an expert archivist extracting structured entities "
        f"from a document. Return ONE JSON object matching the schema "
        f"below. Cover every occurrence in the source. Only include "
        f"facts the text supports — do not speculate or invent.\n\n"
        f"Write prose fields in {output_language}. Strip the "
        f"// comments from your output. Return valid JSON only, no "
        f"prose outside JSON, no code fences.\n\n"
        f"Schema:\n{schema}"
    )


async def extract_all(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Combined extractor — one LLM call per page returns all 6 types."""
    text = inputs.get("text") or ""
    if not text:
        return {"text": "", "value": {}, "error": "No text input"}

    from fichero.lang_detect import resolve_output_language
    output_language = resolve_output_language(
        inputs.get("output_language"), text, default="English"
    )

    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    container = _resolve_container_doc(selected_doc_ids, library_path)

    # Per-page chunks via records (preferred) or text-split fallback.
    records_input = inputs.get("records") or []
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
    prompt = _build_combined_prompt(output_language)

    chunk_errors: list[str] = []
    # Per-page error tracking — when a chunk fails, we write an
    # `extraction_error` artifact on the page doc so the user can see
    # WHY a page came back empty (small models on dialect-heavy text
    # often error or return malformed JSON; previously this was
    # swallowed silently). #800, #829.
    page_errors: list[str | None] = [None] * len(chunks)

    async def _extract_one(idx: int, chunk_text: str) -> dict[str, list]:
        # Sub-chunk if the page exceeds the small-model window.
        if len(chunk_text) > _MAX_CHUNK_CHARS:
            sub_chunks = [
                chunk_text[i:i + _MAX_CHUNK_CHARS]
                for i in range(0, len(chunk_text), _MAX_CHUNK_CHARS)
            ]
            # Sub-chunks share the parent's page index for error
            # attribution; pass -1 so they don't overwrite top-level
            # page_errors entries on partial failure.
            sub_results = await asyncio.gather(
                *[_extract_one(-1, s) for s in sub_chunks]
            )
            merged: dict[str, list] = {}
            for sr in sub_results:
                for k, v in sr.items():
                    merged.setdefault(k, []).extend(v)
            return merged

        # Split rules (system) from source (user) so Apple Intelligence
        # routes them to its Instructions vs Prompt channels — the model
        # is trained to obey instructions and treat prompts as untrusted
        # input, which both reduces example-bleed and improves rule
        # adherence (#815).
        try:
            # chat_with_fallback transparently retries with $large when
            # Apple Intelligence's on-device guardrail refuses scholarly
            # text containing literary profanity, court-record vocabulary,
            # historical slurs, etc. Keeps the local-first default but
            # escapes to the user's frontier provider when needed (#838).
            response = await chat_with_fallback(
                chunk_text,
                config=llm_config,
                system=prompt,
            )
        except Exception as exc:
            msg = f"LLM call failed: {exc}"
            logger.error(f"extract_all {msg}")
            chunk_errors.append(str(exc))
            if idx >= 0:
                page_errors[idx] = f"LLM call failed: {exc}"
            return {}

        try:
            parsed = json.loads(_strip_fences(response))
        except json.JSONDecodeError as exc:
            logger.warning(f"extract_all: JSON parse failed ({exc})")
            chunk_errors.append(f"JSON parse failed: {exc}")
            if idx >= 0:
                page_errors[idx] = f"JSON parse failed: {exc}"
            return {}

        if not isinstance(parsed, dict):
            if idx >= 0:
                page_errors[idx] = "LLM response not a JSON object"
            return {}
        # Filter to schema_keys we know about; ignore extras.
        known_keys = {s["schema_key"] for s in _SECTIONS}
        return {k: (v or []) for k, v in parsed.items() if k in known_keys}

    chunk_results: list[dict[str, list]] = await asyncio.gather(
        *[_extract_one(i, c) for i, c in enumerate(chunks)]
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
                        db.save(Artifact(
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
                        db.save(Artifact(
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
    if not value and chunk_errors:
        actionable = next(
            (e for e in chunk_errors
             if any(k in e.lower() for k in ("quota", "limit", "401", "403", "402"))),
            chunk_errors[0],
        )
        result["error"] = (
            f"Extract All: {len(chunk_errors)}/{len(chunks)} "
            f"LLM calls failed — {actionable}"
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
    default_prompt=_build_combined_prompt("English"),
    sort_order=5,
)(extract_all)
