"""Back-of-book index extractor."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from fichero_server.books.page_offset import page_offset_from_inputs, resolve_printed_page
from fichero_server.db import db_manager
from fichero_server.kg._common import slug_verb
from fichero_server.models.knowledge import ClaimType, EntityType, KnowledgeEntity
from fichero_server.llm import LLMConfig, chat_structured_with_fallback
from fichero_server.models import Artifact, Document
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools._entity_writer import save_claim, upsert_entity
from fichero_server.workflows.tools.catalogue import _resolve_write_target
from fichero_server.workflows.tools.llm_base import (
    BASE_CONFIG_SCHEMA,
    BASE_OUTPUT_PORTS,
    merge_config_schema,
    merge_ports,
)
from fichero_server.workflows.tools._workflow_change_emit import (
    emit_workflow_artifact_changes,
    emit_workflow_kg_changes,
)
from fichero_server.workflows.types import DataType, PortDef, State


_PAGE_TOKEN_RE = re.compile(
    r"(?P<start>\d+)\s*(?:[-–—]\s*(?P<end>\d+)|(?P<ff>\s*f{1,2}\.?)?)",
    re.IGNORECASE,
)


@dataclass
class IndexEntry:
    """Parsed back-of-book index entry."""

    term: str
    page_refs: list[int] = field(default_factory=list)
    subentries: list[str] = field(default_factory=list)
    index_source: str = ""


class _TopicStatement(BaseModel):
    text: str = Field(description="One grounded statement about the topic.")
    verb: str = Field(default="", description="Predicate verb or verb phrase.")
    object: str = Field(default="", description="Object or complement.")
    source_text: str = Field(description="Exact supporting quote from the page.")
    confidence: float = Field(default=0.65, ge=0.0, le=1.0)


class _TopicStatements(BaseModel):
    statements: list[_TopicStatement] = Field(default_factory=list)


_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Index Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=False,
            description="OCR/transcribed back-of-book index text.",
        ),
        PortDef(
            id="records",
            name="Index Records",
            port_type="input",
            data_type=DataType.ARRAY,
            required=False,
            description="Optional index page records [{doc_id, text}, ...].",
        ),
        PortDef(
            id="page_offset",
            name="Page Offset",
            port_type="input",
            data_type=DataType.NUMBER,
            required=False,
            default=0,
            description="PDF sequence minus printed page number.",
        ),
        PortDef(
            id="index_start_sequence",
            name="Index Start Sequence",
            port_type="input",
            data_type=DataType.NUMBER,
            required=False,
            description="First PDF page sequence containing the book index.",
        ),
        PortDef(
            id="index_end_sequence",
            name="Index End Sequence",
            port_type="input",
            data_type=DataType.NUMBER,
            required=False,
            description="Last PDF page sequence containing the book index.",
        ),
        PortDef(
            id="anchor_printed_page",
            name="Anchor Printed Page",
            port_type="input",
            data_type=DataType.NUMBER,
            required=False,
            description="Known printed page number for offset resolution.",
        ),
        PortDef(
            id="anchor_sequence",
            name="Anchor Sequence",
            port_type="input",
            data_type=DataType.NUMBER,
            required=False,
            description="PDF page sequence for the known printed page.",
        ),
    ],
    [],
)


_CONFIG_SCHEMA = {
    "max_pages_per_topic": {
        "type": "integer",
        "default": 4,
        "minimum": 1,
        "maximum": 20,
        "description": "Maximum referenced pages to inspect per topic.",
    },
    "ff_span": {
        "type": "integer",
        "default": 2,
        "minimum": 1,
        "maximum": 10,
        "description": "How many pages to expand an index 'ff.' reference.",
    },
}


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _expand_page_refs(raw: str, *, ff_span: int = 2) -> list[int]:
    """Parse page refs including ranges and `ff.` into printed pages."""

    pages: list[int] = []
    seen: set[int] = set()
    raw = raw.replace("\u2013", "-").replace("\u2014", "-")
    for match in _PAGE_TOKEN_RE.finditer(raw):
        start = int(match.group("start"))
        end_text = match.group("end")
        if end_text:
            end = int(end_text)
        elif (match.group("ff") or "").strip():
            end = start + max(1, ff_span)
        else:
            end = start
        if end < start:
            start, end = end, start
        for page in range(start, end + 1):
            if page not in seen:
                pages.append(page)
                seen.add(page)
    return pages


def parse_index_entries(text: str, *, ff_span: int = 2) -> list[IndexEntry]:
    """Parse common back-of-book index lines into entries.

    Supports `Term, 12-15, 20 ff.`, `Term: 12, 20`, and indented subentries.
    Indented subentries inherit the current parent term.
    """

    entries_by_term: dict[str, IndexEntry] = {}
    current_parent: str | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        is_subentry = raw_line[:1].isspace() and current_parent is not None
        line = " ".join(raw_line.strip().split())
        separator = ":" if ":" in line else ","
        if separator not in line:
            continue
        head, tail = line.split(separator, 1)
        term = head.strip(" .")
        pages = _expand_page_refs(tail.strip(), ff_span=ff_span)
        if not term or not pages:
            continue

        if is_subentry and current_parent:
            entry = entries_by_term.setdefault(current_parent, IndexEntry(current_parent))
            entry.subentries.append(term)
        else:
            current_parent = term
            entry = entries_by_term.setdefault(term, IndexEntry(term))

        for page in pages:
            if page not in entry.page_refs:
                entry.page_refs.append(page)
        entry.index_source = "\n".join(
            part for part in [entry.index_source, raw_line.strip()] if part
        )

    for entry in entries_by_term.values():
        entry.page_refs.sort()
        entry.subentries = sorted(set(entry.subentries))
    return list(entries_by_term.values())


def _index_text_from_inputs(db, parent_id: str, inputs: dict[str, Any]) -> str:
    records = inputs.get("records")
    if isinstance(records, list):
        parts = [
            str(record.get("text") or "")
            for record in records
            if isinstance(record, dict) and record.get("text")
        ]
        if parts:
            return "\n".join(parts)
    start_sequence = _coerce_int(inputs.get("index_start_sequence"))
    end_sequence = _coerce_int(inputs.get("index_end_sequence"))
    if start_sequence is not None and end_sequence is not None:
        if end_sequence < start_sequence:
            start_sequence, end_sequence = end_sequence, start_sequence
        children = db.query(Document, parent_id=parent_id)
        pages = [
            doc
            for doc in children
            if doc.sequence is not None
            and start_sequence <= doc.sequence <= end_sequence
            and doc.page_content
        ]
        pages.sort(key=lambda doc: doc.sequence or 0)
        if pages:
            return "\n".join(page.page_content or "" for page in pages)
    return str(inputs.get("text") or "")


def _page_label(page: Document, printed_page: int) -> str:
    metadata = page.metadata if isinstance(page.metadata, dict) else {}
    label = metadata.get("page_label") or metadata.get("printed_page_label")
    return str(label or printed_page)


async def _extract_topic_statements(
    *,
    topic: str,
    page_text: str,
    llm_config: LLMConfig,
) -> list[dict[str, Any]]:
    if not page_text.strip():
        return []
    system = (
        f"Topic: {topic}\n\n"
        "Extract only statements directly grounded in the page text. "
        "Each statement must include an exact supporting quote from the page. "
        "Skip generic mentions and claims not supported by the quote."
    )
    result = await chat_structured_with_fallback(
        prompt=page_text[:6000],
        schema=_TopicStatements,
        config=llm_config,
        system=system,
        include_schema_in_prompt=False,
        permissive_guardrails=True,
    )
    return [item.model_dump(mode="json") for item in result.statements]


def _write_topic_entity(db, entry: IndexEntry) -> str | None:
    entity_id = upsert_entity(
        db,
        entry.term,
        EntityType.concept,
        aliases=entry.subentries,
        description="Back-of-book index topic.",
    )
    if entity_id is None:
        return None
    entity = db.get(KnowledgeEntity, entity_id)
    if entity is not None:
        metadata = dict(entity.metadata or {})
        metadata["topic_source"] = "back_of_book_index"
        metadata["index_page_refs"] = entry.page_refs
        entity.metadata = metadata
        db.save(entity)
    return entity_id


@register_tool(
    name="book_index_extract",
    display_name="Extract Book Index Topics",
    description=(
        "Parse a back-of-book index into topic entities and grounded "
        "statements from the referenced pages."
    ),
    category="llm",
    icon="book.pages",
    color="teal",
    uses_llm=True,
    supports_batch=False,
    supports_structured_output=True,
    input_ports=_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, _CONFIG_SCHEMA),
    sort_order=35,
)
async def book_index_extract(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Parse index text, upsert topic entities, and write grounded claims."""

    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    parent = _resolve_write_target(selected_doc_ids, library_path)
    if parent is None or not library_path:
        return {"text": "", "value": [], "error": "No selected parent document"}

    db = db_manager.get_database(library_path)
    text = _index_text_from_inputs(db, parent.id, inputs)
    if not text.strip():
        return {"text": "", "value": [], "error": "No index text input"}

    ff_span = _coerce_int(inputs.get("ff_span")) or 2
    max_pages_per_topic = _coerce_int(inputs.get("max_pages_per_topic")) or 4
    entries = parse_index_entries(text, ff_span=ff_span)
    resolver = page_offset_from_inputs(
        page_offset=_coerce_int(inputs.get("page_offset")),
        anchor_printed_page=_coerce_int(inputs.get("anchor_printed_page")),
        anchor_sequence=_coerce_int(inputs.get("anchor_sequence")),
    )

    values: list[dict[str, Any]] = []
    markdown: list[str] = ["# Book Index Topics"]
    written_entity_ids: list[str] = []
    written_claim_ids: list[str] = []

    for entry in entries:
        entity_id = _write_topic_entity(db, entry)
        referenced_pages: list[dict[str, Any]] = []
        statements_written = 0
        if entity_id is None:
            value = {
                "term": entry.term,
                "entity_id": None,
                "subentries": entry.subentries,
                "page_refs": entry.page_refs,
                "pages": referenced_pages,
                "claims_written": statements_written,
            }
            values.append(value)
            markdown.append(
                f"- {entry.term}: {', '.join(str(p) for p in entry.page_refs)} "
                "(suppressed by curation rule)"
            )
            continue
        written_entity_ids.append(entity_id)

        for printed_page in entry.page_refs[:max_pages_per_topic]:
            page = resolve_printed_page(
                db,
                parent_id=parent.id,
                printed_page=printed_page,
                page_offset=resolver.offset,
            )
            if page is None:
                referenced_pages.append({"printed_page": printed_page, "resolved": False})
                continue
            referenced_pages.append(
                {
                    "printed_page": printed_page,
                    "document_id": page.id,
                    "sequence": page.sequence,
                    "resolved": True,
                }
            )
            statements = await _extract_topic_statements(
                topic=entry.term,
                page_text=page.page_content or "",
                llm_config=llm_config,
            )
            for statement in statements:
                source_text = str(statement.get("source_text") or "").strip()
                page_text = page.page_content or ""
                char_start = page_text.find(source_text) if source_text else -1
                char_end = char_start + len(source_text) if char_start >= 0 else None
                verb = str(statement.get("verb") or "mentions").strip() or "mentions"
                obj = str(statement.get("object") or entry.term).strip() or entry.term
                claim_text = str(statement.get("text") or "").strip()
                if not claim_text:
                    claim_text = f"{entry.term} {verb} {obj}."
                confidence = float(statement.get("confidence") or 0.65)
                claim_id = save_claim(
                    db,
                    claim_text,
                    page.id,
                    entity_ids=[entity_id],
                    source_excerpt=source_text or page_text[:500] or None,
                    source_page_label=_page_label(page, printed_page),
                    source_char_start=char_start if char_start >= 0 else None,
                    source_char_end=char_end,
                    claim_type=ClaimType.fact,
                    confidence=confidence,
                    metadata={
                        "topic": entry.term,
                        "index_page_refs": entry.page_refs,
                        "index_source": entry.index_source,
                        "writer": "book_index_extract",
                    },
                    subject_canonical=entry.term,
                    subject_entity_id=entity_id,
                    predicate_verb=verb,
                    object_phrase=obj,
                    svo_subject=entry.term,
                    svo_verb=slug_verb(verb),
                    svo_object=obj,
                    provider=getattr(llm_config, "provider", None),
                    model=getattr(llm_config, "model", None),
                    confidence_origin="llm",
                )
                if claim_id is not None:
                    statements_written += 1
                    written_claim_ids.append(claim_id)

        value = {
            "term": entry.term,
            "entity_id": entity_id,
            "subentries": entry.subentries,
            "page_refs": entry.page_refs,
            "pages": referenced_pages,
            "claims_written": statements_written,
        }
        values.append(value)
        markdown.append(
            f"- {entry.term}: {', '.join(str(p) for p in entry.page_refs)} "
            f"({statements_written} statements)"
        )

    artifact = Artifact(
        document_id=parent.id,
        artifact_type="book_index_topics",
        content="\n".join(markdown),
        data={"items": values},
        provider=getattr(llm_config, "provider", None),
        model=getattr(llm_config, "model", None),
        run_id=state.get("task_id"),
    )
    db.save(artifact)
    emit_workflow_artifact_changes(
        str(db.path.parent),
        artifact_ids=[artifact.id],
        document_ids=[parent.id],
    )
    if written_entity_ids or written_claim_ids:
        emit_workflow_kg_changes(
            str(db.path.parent),
            entity_ids=written_entity_ids,
            claim_ids=written_claim_ids,
        )

    return {"text": artifact.content, "value": values, "cached": False}
