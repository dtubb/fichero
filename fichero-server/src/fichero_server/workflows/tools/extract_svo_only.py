"""Register step-3 SVO claim extraction for already-imported documents.

This workflow node mirrors the discrete step-1/step-2 stages:
select the already-imported page/file documents, recover the step-1
transcription artifacts plus the step-2 persisted entity rows, run only
the shared per-entity SVO claim extractor, and persist KnowledgeClaim
rows through the canonical KG write path.

It intentionally does NOT merge/deduplicate entities, create catalogue
artifacts, or run later KG graph stages. Those belong to follow-up
stages under #1757.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field

from fichero_server.db import db_manager
from fichero_server.knowledge.dedupe import normalize_name
from fichero_server.knowledge.spacy_svo import predicate_problem
from fichero_server.knowledge.svo_cleanup import (
    collapse_dated_claims,
    collapse_near_duplicate_claims,
)
from fichero_server.knowledge.svo_quality import (
    MAX_VERB_WORDS,
    claim_rejection,
    trim_predicate,
    ungrounded_span,
)
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity
from fichero_server.llm import (
    LLMConfig,
    ProviderQuotaError,
    chat_structured_with_fallback,
)
from fichero_server.llm.language_policy import (
    UNKNOWN,
    configured_policy,
    prompt_language,
    resolve_language,
)
from fichero_server.models import Document
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.extract_all import (
    _EntityOnly,
    _annotate_pronoun_source,
    _build_entity_items_for_section,
    _date_is_on_the_page,
)
from fichero_server.workflows.tools.extract_entities_only import (
    _ENTITY_TYPES,
    _ENTITY_TYPES_CONFIG,
    _records_for_documents,
    _requested_sections,
)
from fichero_server.workflows.tools.extractors import (
    _SECTION_SCHEMAS,
    _SECTIONS,
    _build_section_prompt,
    _write_kg_rows,
)
from fichero_server.workflows.tools.import_artifacts import _coerce_documents
from fichero_server.workflows.tools.progress import emit_progress_event
from fichero_server.workflows.tools.sources import files_tool
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_SECTION_BY_KEY = {
    section["schema_key"]: section
    for section in _SECTIONS
    # Entity-backed sections plus "dates": dates are claim-only
    # (entity_type None) and are extracted by the direct dates pass below,
    # not the per-entity loop.
    if section.get("schema_key") in _ENTITY_TYPES
    or section.get("schema_key") == "dates"
}
_SECTION_KEY_BY_ENTITY_TYPE = {
    entity_type: section_key for section_key, entity_type in _ENTITY_TYPES.items()
}


class _PageClaimItem(BaseModel):
    """One SVO claim from the page-level pass — the subject is CHOSEN, not given."""

    subject: str = Field(
        default="",
        description=(
            "The AGENT of the action — the entity that performs or owns it. "
            "Must be one of the entities listed in the instructions, copied as "
            "written. A person performs actions; a place is a location, never "
            "the agent of a person's action; an organization owns/operates."
        ),
    )
    subject_type: str = Field(
        default="", description="person | place | organization | river | event | mine"
    )
    verb: str = Field(
        default="",
        description=(
            "Predicate verb/verb phrase copied from the page (include "
            "prepositions); the subject is implicit — do not repeat it."
        ),
    )
    object: str = Field(
        default="",
        description="Rest of the predicate — a minimal noun phrase copied from the page.",
    )
    source_text: str = Field(
        default="", description="The exact span from the page this claim is read from."
    )
    epistemic_status: str = Field(default="tentative")
    claim_type: str = Field(default="")
    date: str = Field(
        default="",
        description="YYYY-MM-DD / YYYY-MM / YYYY, ONLY when the page states one for this claim.",
    )
    place: str = Field(
        default="",
        description="Where it happened, copied from the page, ONLY when the page names it.",
    )


class _PageClaims(BaseModel):
    items: list[_PageClaimItem] = Field(default_factory=list)


def _build_page_claim_instructions(
    output_language: str,
    entities_by_section: dict[str, list[_EntityOnly]],
    document_context: str | None = None,
) -> str:
    """Instructions for ONE page-level SVO pass over the whole page.

    Replaces the per-entity Stage-2 loop, which asked for claims about each
    entity separately and so copied a sentence's predicate onto every nearby
    entity — a cross-product of duplicates with wrong subjects (a place cast as
    the agent of a person's verb). Here the model reads the page once and, for
    each fact, picks the single correct AGENT from the known entities.
    """
    context_block = ""
    if document_context and document_context.strip():
        context_block = (
            f"Document context: {document_context.strip()}\n"
            "First-person statements ('I', 'me', 'my') refer to the document's "
            "author named in the context above — never to another entity "
            "mentioned nearby.\n\n"
        )
    lines = []
    for section_key, entities in entities_by_section.items():
        names = sorted({e.name for e in entities if e.name})
        if names:
            lines.append(f"  {section_key.rstrip('s')}: " + "; ".join(names))
    entity_block = "\n".join(lines) or "  (none identified)"
    return (
        f"{context_block}"
        f"Read the whole page and extract subject-verb-object claims — one row "
        f"per distinct fact.\n\n"
        f"THE SUBJECT IS THE AGENT. For each fact the subject is the ONE entity "
        f"that performs or owns the action. A person performs actions; a place "
        f"is where something happens, NEVER the agent of a person's action; an "
        f"organization owns or operates things. Do NOT attach the same predicate "
        f"to more than one entity — if a sentence says a person works a mine in "
        f"a town, the PERSON is the subject, not the town and not the mine's "
        f"owner.\n\n"
        f"The subject MUST be one of these already-identified entities, copied "
        f"as written:\n{entity_block}\n\n"
        f"If a fact's true agent is not in this list, omit the fact rather than "
        f"forcing a wrong subject. Never use a pronoun as a subject.\n\n"
        f"COPY, DO NOT COMPOSE. The verb and object must be spans found on the "
        f"page word for word, in the source's language and spelling — no "
        f"translation, no modernisation, no smoothing. The verb is the MINIMAL "
        f"verb phrase (at most {MAX_VERB_WORDS} words); the object is the "
        f"minimal completing noun phrase, never a whole clause.\n\n"
        f"One assertion per claim, and DO NOT repeat a claim. Write any "
        f"commentary in {output_language}; the verb and object stay in the "
        f"source's language. Only include facts directly supported by the page."
    )


async def _extract_page_claims(
    page_text: str,
    llm_config: LLMConfig,
    instructions: str,
    extraction_sem: asyncio.Semaphore,
) -> list[dict]:
    """ONE page-level SVO pass → claim dicts each carrying its own subject."""
    if not (page_text or "").strip():
        return []
    try:
        async with extraction_sem:
            result = await chat_structured_with_fallback(
                prompt=page_text,
                schema=_PageClaims,
                config=llm_config,
                system=instructions,
                include_schema_in_prompt=False,
                permissive_guardrails=True,
            )
        return [item.model_dump() for item in (getattr(result, "items", None) or [])]
    except ProviderQuotaError:
        raise
    except Exception as exc:
        logger.warning("extract_svo_only: page SVO extraction failed: %s", exc)
        return []


def _page_label(document: Document) -> str | None:
    metadata = dict(document.metadata or {})
    page_label = metadata.get("page_label")
    if page_label is None and metadata.get("page_number") is not None:
        page_label = str(metadata["page_number"])
    if page_label is None and document.sequence is not None:
        page_label = str(document.sequence)
    return str(page_label) if page_label not in (None, "") else None


def _entities_for_records(records: list[dict[str, Any]], db) -> dict[str, dict[str, list[_EntityOnly]]]:
    record_doc_ids = {str(record["doc_id"]) for record in records if record.get("doc_id")}
    entities_by_doc: dict[str, dict[str, list[_EntityOnly]]] = {
        doc_id: defaultdict(list) for doc_id in record_doc_ids
    }

    for entity in db.query(KnowledgeEntity):
        section_key = _SECTION_KEY_BY_ENTITY_TYPE.get(entity.entity_type)
        if section_key is None:
            continue
        for doc_id in set(entity.source_document_ids or []):
            if doc_id not in entities_by_doc:
                continue
            entities_by_doc[doc_id][section_key].append(
                _EntityOnly(
                    name=entity.canonical_name,
                    aliases=list(entity.aliases or []),
                    entity_type=section_key.rstrip("s"),
                )
            )

    for per_doc in entities_by_doc.values():
        for entities in per_doc.values():
            entities.sort(key=lambda entity: entity.name.casefold())

    return entities_by_doc


@register_tool(
    name="extract_svo_only",
    display_name="Extract SVO Claims",
    description="Extract and persist SVO KnowledgeClaim rows only from existing entities and transcription artifacts",
    category="llm",
    icon="arrow.triangle.branch",
    color="orange",
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
            description="Created/reused claim counts",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of selected atomic documents processed",
        ),
    ],
    sort_order=37,
    config_schema={
        **_ENTITY_TYPES_CONFIG,
        "document_context": {
            "type": "string",
            "title": "Document Context",
            "description": (
                "Corpus framing the text cannot supply, e.g. 'The personal "
                "diary of N.C. Marshall, an American engineer in Colombia.' "
                "First-person statements are attributed to the author named "
                "here. Blank = derived from each document's author metadata "
                "when present."
            ),
            "default": "",
        }
    },
)
async def extract_svo_only(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Run the shared Stage-2 SVO extractor and persist claim rows only."""
    library_path = state.get("library_path", "")
    if not library_path:
        return {
            "summary": {
                "documents_processed": 0,
                "entities_processed": 0,
                "claims_extracted": 0,
                "claims_created": 0,
                "claims_reused": 0,
            },
            "count": 0,
        }

    db = db_manager.get_database(library_path)
    raw_documents = list(inputs.get("documents") or [])
    if not raw_documents:
        fallback = await files_tool(
            inputs={},
            state=state,
            llm_config=LLMConfig(provider="", model=""),
        )
        raw_documents = list(fallback.get("documents") or [])

    documents = _coerce_documents(raw_documents, db, library_path)
    records = _records_for_documents(documents, db)
    if not records:
        return {
            "summary": {
                "documents_processed": 0,
                "entities_processed": 0,
                "claims_extracted": 0,
                "claims_created": 0,
                "claims_reused": 0,
            },
            "count": 0,
        }

    entities_by_doc = _entities_for_records(records, db)
    selected_doc_ids = {record["doc_id"] for record in records}
    claims_before = sum(
        1
        for claim in db.query(KnowledgeClaim)
        if claim.source_document_id in selected_doc_ids
    )

    # #2092. This used to be `_build_per_entity_claim_instructions(
    # inputs.get("output_language", "auto"))` — the raw config value, never
    # resolved, so the default put the literal word "auto" into the prompt
    # ("Write in auto.") and the library's language policy had no effect on SVO
    # extraction at all. Resolved PER DOCUMENT now, which is what makes
    # "language of the document" mean something on a mixed corpus.
    requested_sections = _requested_sections(inputs.get("entity_types"))
    policy = configured_policy()
    languages_used: dict[str, int] = defaultdict(int)

    progress_callback = inputs.get("__progress_callback")
    max_in_flight = int(os.environ.get("FICHERO_EXTRACT_MAX_IN_FLIGHT", "3"))
    extraction_sem = asyncio.Semaphore(max_in_flight)

    entities_processed = 0
    claims_extracted = 0

    for index, record in enumerate(records):
        doc_id = record["doc_id"]
        doc_name = record.get("doc_name") or doc_id or f"document-{index + 1}"
        page_entities = entities_by_doc.get(doc_id) or {}

        resolution = resolve_language(
            requested=inputs.get("output_language"),
            document=documents[record["index"]],
            text=record["text"] or "",
            policy=policy,
        )
        languages_used[resolution.language or UNKNOWN] += 1
        instruction_key = prompt_language(resolution)
        # Corpus framing (user, 2026-08-20): the node's `document_context`
        # config, else the document's own author metadata — so a diary's "I"
        # resolves to its diarist instead of a nearby name.
        document = documents[record["index"]]
        doc_meta = dict(getattr(document, "metadata", None) or {})
        document_context = (
            str(inputs.get("document_context") or "").strip()
            or (f"Written by {doc_meta['author']}." if doc_meta.get("author") else "")
        )
        # WHO the page's first person is (#4671). A diary's "otorgamos"/"I"
        # legitimately belongs to its diarist, so the grammar check must not
        # reject a first-person verb when the subject IS that person — only
        # when a nearby name has been stamped onto someone else's "we".
        speaker = str(doc_meta.get("author") or "").strip()

        await emit_progress_event(
            progress_callback,
            "file_start",
            "",
            f"Extract SVO {doc_name}",
            index + 1,
            len(records),
            message=f"Extracting step-3 SVO claims for {doc_name}",
        )

        # Dates are claim-only (entity_type None — no canonical entity row),
        # so the per-entity loop below can never yield a date claim. Extract
        # them directly per record, the way extract_all's combined pass did,
        # so the timeline probe contract (#1470: time_start/time_end/
        # date_values on date claims) survives the Catalogue chain (2026-09-03).
        dates_section = _SECTION_BY_KEY.get("dates")
        if (
            dates_section is not None
            and "dates" in requested_sections
            and (record["text"] or "").strip()
        ):
            try:
                async with extraction_sem:
                    dates_result = await chat_structured_with_fallback(
                        prompt=record["text"],
                        schema=_SECTION_SCHEMAS["dates"],
                        config=llm_config,
                        system=_build_section_prompt(
                            dates_section, instruction_key
                        ),
                        include_schema_in_prompt=False,
                        permissive_guardrails=True,
                    )
                date_items = [
                    item.model_dump()
                    for item in (getattr(dates_result, "items", None) or [])
                ]
            except ProviderQuotaError:
                raise
            except Exception as exc:
                # Mirror the per-entity soft-fail semantics: one bad call
                # loses one record's dates, not the whole stage.
                logger.warning(
                    "extract_svo_only: date extraction failed for %s: %s",
                    doc_name,
                    exc,
                )
                date_items = []
            if date_items:
                # Date claims skip the per-entity loop (entity_type None), so
                # they never met the near-dup collapse the entity path runs. A
                # model repeating "1830 | firmó la escritura" left both rows.
                # Collapse within each date so a repeat of one date's statement
                # folds while two different dates stay distinct.
                date_before = len(date_items)
                date_items = collapse_dated_claims(date_items)
                if len(date_items) != date_before:
                    logger.info(
                        "SVO date cleanup for %s: %d in → %d kept "
                        "(%d near-dup collapsed)",
                        doc_name,
                        date_before,
                        len(date_items),
                        date_before - len(date_items),
                    )
                claims_extracted += len(date_items)
                _write_kg_rows(
                    db,
                    dates_section,
                    date_items,
                    doc_id,
                    page_label=_page_label(documents[record["index"]]),
                    source_excerpt=record["text"][:500] if record["text"] else None,
                    provider=getattr(llm_config, "provider", None),
                    model=getattr(llm_config, "model", None),
                    grounding_text=record["text"],
                )

        # Page-at-a-time SVO (was: one _extract_claims_for_entity call per
        # entity, which copied each sentence's predicate onto EVERY nearby entity
        # — a cross-product of duplicates with wrong subjects, e.g. a place or an
        # owner cast as the agent of a person's verb). One pass now; the model
        # picks the single correct AGENT for each fact, and we route it to that
        # entity. Distinct facts, one subject each → cross-product + dups gone at
        # the source.
        entity_by_norm: dict[str, tuple[str, _EntityOnly]] = {}
        for section_key, entities in page_entities.items():
            if section_key not in requested_sections or _SECTION_BY_KEY.get(section_key) is None:
                continue
            for entity in entities:
                entity_by_norm.setdefault(normalize_name(entity.name), (section_key, entity))

        if entity_by_norm and (record["text"] or "").strip():
            page_instructions = _build_page_claim_instructions(
                instruction_key,
                {
                    section_key: entities
                    for section_key, entities in page_entities.items()
                    if section_key in requested_sections
                },
                document_context or None,
            )
            page_claims = await _extract_page_claims(
                record["text"], llm_config, page_instructions, extraction_sem
            )

            claims_by_entity: dict[str, list[dict]] = defaultdict(list)
            for page_claim in page_claims:
                hit = entity_by_norm.get(normalize_name(page_claim.get("subject", "")))
                if hit is None:
                    # Subject is not one of the page's entities: a hallucinated
                    # or cross-product subject — drop it.
                    continue
                _section_key, entity = hit
                verb, obj = trim_predicate(
                    page_claim.get("verb", ""), page_claim.get("object", "")
                )
                # Same per-claim gate the per-entity path used: grounded against
                # the page text, then the deterministic grammar gate.
                if claim_rejection(entity.name, verb, obj, record["text"]) is not None:
                    continue
                if predicate_problem(entity.name, verb, record["text"], speaker=speaker):
                    continue
                # Scope is claim-only and MUST be grounded: an inferred date or
                # place is a guess wearing a fact's clothes (the timeline plots
                # it, the map pins it). Keep the claim, drop an ungrounded scope.
                # date_normalized is what makes an event a timeline row (#4667).
                place = (page_claim.get("place") or "").strip()
                if place and ungrounded_span(place, record["text"]):
                    place = ""
                date = (page_claim.get("date") or "").strip()
                if date and not _date_is_on_the_page(date, record["text"]):
                    date = ""
                claims_by_entity[entity.name].append(
                    {
                        "name": entity.name,
                        "verb": verb,
                        "object": obj,
                        "source_text": _annotate_pronoun_source(
                            page_claim.get("source_text", ""), entity.name
                        ),
                        "epistemic_status": page_claim.get("epistemic_status", ""),
                        "claim_type": page_claim.get("claim_type", ""),
                        "date_normalized": date,
                        "claim_location": place,
                    }
                )

            for _norm_key, (section_key, entity) in entity_by_norm.items():
                claim_list = claims_by_entity.get(entity.name)
                if not claim_list:
                    continue
                entities_processed += 1
                # Belt-and-suspenders near-dup collapse per subject (the page
                # pass shouldn't repeat, but a model still can).
                claim_list = collapse_near_duplicate_claims(entity.name, claim_list)
                claims_extracted += len(claim_list)
                items = _build_entity_items_for_section(entity, section_key, claim_list)
                if not items:
                    continue
                _write_kg_rows(
                    db,
                    _SECTION_BY_KEY[section_key],
                    items,
                    doc_id,
                    page_label=_page_label(documents[record["index"]]),
                    source_excerpt=record["text"][:500] if record["text"] else None,
                    provider=getattr(llm_config, "provider", None),
                    model=getattr(llm_config, "model", None),
                    grounding_text=record["text"],
                )

        await emit_progress_event(
            progress_callback,
            "file_complete",
            "",
            f"Extract SVO {doc_name}",
            index + 1,
            len(records),
            message=f"Extracted step-3 SVO claims for {doc_name}",
        )

    claims_after = sum(
        1
        for claim in db.query(KnowledgeClaim)
        if claim.source_document_id in selected_doc_ids
    )
    claims_created = max(0, claims_after - claims_before)
    summary = {
        "documents_processed": len(records),
        "entities_processed": entities_processed,
        "claims_extracted": claims_extracted,
        "claims_created": claims_created,
        "claims_reused": max(0, claims_extracted - claims_created),
        # Which language each document was actually extracted in, including how
        # many resolved to `unknown`. Reported rather than swallowed: a run that
        # silently processed 40 Spanish pages as English is indistinguishable
        # from a good run unless the run says what it did (#2092).
        "languages_used": dict(languages_used),
    }
    return {"summary": summary, "count": len(records)}
