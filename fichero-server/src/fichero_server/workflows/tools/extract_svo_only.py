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

from fichero_server.db import db_manager
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity
from fichero_server.llm import LLMConfig
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
    _build_entity_items_for_section,
    _build_per_entity_claim_instructions,
    _extract_claims_for_entity,
)
from fichero_server.workflows.tools.extract_entities_only import (
    _ENTITY_TYPES,
    _records_for_documents,
)
from fichero_server.workflows.tools.extractors import _SECTIONS, _write_kg_rows
from fichero_server.workflows.tools.import_artifacts import _coerce_documents
from fichero_server.workflows.tools.progress import emit_progress_event
from fichero_server.workflows.tools.sources import files_tool
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_SECTION_BY_KEY = {
    section["schema_key"]: section
    for section in _SECTIONS
    if section.get("schema_key") in _ENTITY_TYPES
}
_SECTION_KEY_BY_ENTITY_TYPE = {
    entity_type: section_key for section_key, entity_type in _ENTITY_TYPES.items()
}


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
    policy = configured_policy()
    instructions_by_language: dict[str, str] = {}
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
        claim_instructions = instructions_by_language.get(instruction_key)
        if claim_instructions is None:
            claim_instructions = _build_per_entity_claim_instructions(instruction_key)
            instructions_by_language[instruction_key] = claim_instructions

        await emit_progress_event(
            progress_callback,
            "file_start",
            "",
            f"Extract SVO {doc_name}",
            index + 1,
            len(records),
            message=f"Extracting step-3 SVO claims for {doc_name}",
        )

        for section_key, entities in page_entities.items():
            section = _SECTION_BY_KEY.get(section_key)
            if section is None:
                continue
            for entity in entities:
                entities_processed += 1
                claims = await _extract_claims_for_entity(
                    record["text"],
                    entity.name,
                    section_key.rstrip("s"),
                    llm_config,
                    claim_instructions,
                    extraction_sem,
                )
                claims_extracted += len(claims)
                if not claims:
                    continue
                items = _build_entity_items_for_section(entity, section_key, claims)
                if not items:
                    continue
                _write_kg_rows(
                    db,
                    section,
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
