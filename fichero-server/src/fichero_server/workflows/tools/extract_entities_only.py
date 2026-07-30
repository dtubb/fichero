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
import os
from typing import Any, Iterator

from fichero_server.db import db_manager
from fichero_server.models.knowledge import KnowledgeEntity
from fichero_server.llm import LLMConfig, chat_structured_with_fallback
from fichero_server.models import Artifact, Document
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools._entity_writer import upsert_entity
from fichero_server.workflows.tools.extract_all import (
    _EntitiesOnly,
    _build_entity_only_instructions,
    _entities_only_is_empty,
    _entity_schema_in_prompt,
)
from fichero_server.workflows.tools.extractors import _SECTIONS
from fichero_server.workflows.tools.import_artifacts import _coerce_documents
from fichero_server.workflows.tools.progress import emit_progress_event
from fichero_server.workflows.tools.sources import files_tool
from fichero_server.workflows.tools._workflow_change_emit import emit_workflow_kg_changes
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_TRANSCRIPTION_ARTIFACT = "transcription"
_ENTITY_TYPES = {
    section["schema_key"]: section["entity_type"]
    for section in _SECTIONS
    if section.get("schema_key") in {"people", "places", "organizations", "events"}
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
    metadata = dict(document.metadata or {})
    raw_transcription = metadata.get("transcription")
    if isinstance(raw_transcription, str) and raw_transcription.strip():
        return raw_transcription.strip()

    if isinstance(document.page_content, str) and document.page_content.strip():
        return document.page_content.strip()

    for artifact in db.query(
        Artifact,
        document_id=document.id,
        artifact_type=_TRANSCRIPTION_ARTIFACT,
    ):
        if isinstance(artifact.content, str) and artifact.content.strip():
            return artifact.content.strip()
    return ""


def _iter_records(documents: list[Document], db) -> Iterator[dict[str, Any]]:
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
    """
    for index, document in enumerate(documents):
        text = _transcription_text(document, db)
        if not text:
            continue
        yield {
            "index": index,
            "doc_id": document.id,
            "doc_name": document.name,
            "text": text,
        }


def _records_for_documents(documents: list[Document], db) -> list[dict[str, Any]]:
    """Materialise every record up front.

    Only for callers that must traverse the record set more than once —
    ``extract_svo_only`` cross-references entities by document, computes the
    selected-id set, and only then extracts, so a single-pass generator does
    not fit it. Prefer :func:`_iter_records` everywhere else: this holds the
    whole selection's text resident for the life of the call, which is the
    memory shape #4379 was about.
    """
    return list(_iter_records(documents, db))


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
)
async def extract_entities_only(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Run the shared Stage-1 entity extractor and persist entity rows only."""
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
    records = _iter_records(documents, db)
    first_record = next(records, None)
    if first_record is None:
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
    records = itertools.chain([first_record], records)

    instructions = _build_entity_only_instructions(inputs.get("output_language", "auto"))
    progress_callback = inputs.get("__progress_callback")
    max_in_flight = int(os.environ.get("FICHERO_EXTRACT_MAX_IN_FLIGHT", "3"))
    extraction_sem = asyncio.Semaphore(max_in_flight)
    known_entity_ids = {entity.id for entity in db.query(KnowledgeEntity)}

    mentions_processed = 0
    created = 0
    reused = 0
    suppressed = 0
    # Progress totals the SELECTION, not the record count: streaming means the
    # number of documents that turn out to have text is unknown until the run
    # ends, and the selection size is the honest denominator for a progress
    # bar anyway. `documents_processed` below still counts only real work.
    total = len(documents)
    processed = 0

    for index, record in enumerate(records):
        processed += 1
        doc_name = record.get("doc_name") or record.get("doc_id") or f"document-{index + 1}"
        await emit_progress_event(
            progress_callback,
            "file_start",
            "",
            f"Extract Entities {doc_name}",
            processed,
            total,
            message=f"Extracting step-2 entities for {doc_name}",
        )

        async with extraction_sem:
            extraction = await chat_structured_with_fallback(
                prompt=record["text"],
                schema=_EntitiesOnly,
                config=llm_config,
                system=instructions,
                include_schema_in_prompt=_entity_schema_in_prompt(llm_config),
                permissive_guardrails=True,
            )
        if _entities_only_is_empty(extraction) and len(record["text"].strip()) > 200:
            logger.warning(
                "extract_entities_only: empty entity result for %s (%d chars)",
                doc_name,
                len(record["text"].strip()),
            )

        written_entity_ids: list[str] = []
        for section_key, entity_type in _ENTITY_TYPES.items():
            for entity in getattr(extraction, section_key, []):
                canonical_name = str(entity.name or "").strip()
                if not canonical_name:
                    continue
                mentions_processed += 1
                entity_id = upsert_entity(
                    db,
                    canonical_name=canonical_name,
                    entity_type=entity_type,
                    aliases=list(getattr(entity, "aliases", []) or []),
                    source_document_id=record["doc_id"],
                )
                if entity_id is None:
                    suppressed += 1
                    continue
                written_entity_ids.append(entity_id)
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

        await emit_progress_event(
            progress_callback,
            "file_complete",
            "",
            f"Extract Entities {doc_name}",
            processed,
            total,
            message=f"Extracted step-2 entities for {doc_name}",
        )

    summary = {
        "documents_processed": processed,
        "entity_mentions_processed": mentions_processed,
        "entities_created": created,
        "entities_reused": reused,
        "entities_suppressed": suppressed,
    }
    return {"summary": summary, "count": processed}
