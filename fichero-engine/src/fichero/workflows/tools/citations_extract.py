"""Citation extractor workflow tool.

Finds a bibliography section, parses bibliography entries, detects inline
citations, resolves them to entries, and writes citation KG rows.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from fichero.db import Database, db_manager
from fichero.models.knowledge import ClaimType, EntityType, KnowledgeEntity
from fichero.llm import LLMConfig, chat_structured_with_fallback
from fichero.models import DocType, Document
from fichero.workflows.registry import register_tool
from fichero.workflows.tools._entity_writer import save_claim, upsert_entity
from fichero.workflows.tools._workflow_change_emit import (
    emit_workflow_citation_changes,
    emit_workflow_kg_changes,
)
from fichero.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_BIB_HEADING_RE = re.compile(
    r"^\s*(references|bibliography|works cited)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_YEAR_RE = re.compile(r"\b(18|19|20)\d{2}[a-z]?\b")
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_NUMBERED_ENTRY_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.)])\s+(.+)$", re.DOTALL)
_AUTHOR_YEAR_PAREN_RE = re.compile(
    r"\((?P<author>[A-Z][A-Za-z'`-]+(?:\s+et\s+al\.)?)"
    r"(?:,\s*|\s+)(?P<year>(?:18|19|20)\d{2}[a-z]?)\)"
)
_AUTHOR_YEAR_TEXT_RE = re.compile(
    r"\b(?P<author>[A-Z][A-Za-z'`-]+(?:\s+et\s+al\.)?)\s+"
    r"\((?P<year>(?:18|19|20)\d{2}[a-z]?)\)"
)
_NUMERIC_CITE_RE = re.compile(r"\[(?P<number>\d{1,3})\]")
_FOOTNOTE_LINE_RE = re.compile(
    r"^\s*(?P<number>\d{1,3})[.)]?\s+(?P<rest>.+?(?:\b(?:18|19|20)\d{2}[a-z]?\b.+))$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class PageRecord:
    doc_id: str
    text: str
    page_label: str | None = None


@dataclass(frozen=True)
class BibliographyEntry:
    index: int
    raw_text: str
    authors: list[str]
    year: str
    title: str = ""
    journal_or_publisher: str = ""
    doi: str = ""
    url: str = ""

    @property
    def canonical_name(self) -> str:
        author = first_author_key(self.authors, fallback=self.raw_text)
        return f"{author}-{self.year}" if self.year else author

    def as_metadata(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "raw_text": self.raw_text,
            "authors": self.authors,
            "year": self.year,
            "title": self.title,
            "journal_or_publisher": self.journal_or_publisher,
            "doi": self.doi,
            "url": self.url,
            "canonical_name": self.canonical_name,
        }


@dataclass(frozen=True)
class InlineCitation:
    raw_text: str
    author_key: str | None
    year: str | None
    number: int | None
    page_doc_id: str
    page_label: str | None
    char_start: int
    char_end: int


class _CitationFields(BaseModel):
    authors: list[str] = Field(
        default_factory=list,
        description="Authors in display order. Use 'Last, First' when possible.",
    )
    year: str = Field(default="", description="Publication year, e.g. 1998.")
    title: str = Field(default="", description="Article, chapter, or book title.")
    journal_or_publisher: str = Field(
        default="",
        description="Journal, booktitle, publisher, or venue if present.",
    )
    doi: str = Field(default="", description="DOI without URL prefix if present.")
    url: str = Field(default="", description="URL if present.")


def first_author_key(authors: list[str], *, fallback: str = "") -> str:
    source = authors[0] if authors else fallback
    source = source.strip()
    if "," in source:
        source = source.split(",", 1)[0]
    token = re.split(r"\s+", source)[0] if source else "Unknown"
    return re.sub(r"[^A-Za-z0-9_-]", "", token) or "Unknown"


def find_bibliography_section(text: str) -> tuple[str, str]:
    """Return (body, bibliography_text), or ('text', '') when absent."""
    matches = list(_BIB_HEADING_RE.finditer(text))
    if not matches:
        return text, ""
    heading = matches[-1]
    return text[: heading.start()], text[heading.end():].strip()


def split_bibliography_entries(bibliography_text: str) -> list[str]:
    """Split a bibliography section into likely citation entries."""
    if not bibliography_text.strip():
        return []
    lines = [line.rstrip() for line in bibliography_text.splitlines()]
    entries: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                entries.append(" ".join(current).strip())
                current = []
            continue
        starts_entry = bool(_YEAR_RE.search(stripped)) and (
            not current
            or bool(_NUMBERED_ENTRY_RE.match(stripped))
            or bool(re.match(r"^[A-Z][A-Za-z'`-]+,\s+", stripped))
        )
        if current and starts_entry:
            entries.append(" ".join(current).strip())
            current = [stripped]
        else:
            current.append(stripped)
    if current:
        entries.append(" ".join(current).strip())
    return entries


def parse_bibliography_entry_regex(raw_text: str, index: int) -> BibliographyEntry:
    text = " ".join(raw_text.split())
    numbered = _NUMBERED_ENTRY_RE.match(text)
    if numbered:
        number = numbered.group(1) or numbered.group(2)
        index = int(number)
        text = numbered.group(3).strip()

    year_match = _YEAR_RE.search(text)
    year = year_match.group(0) if year_match else ""
    doi_match = _DOI_RE.search(text)
    url_match = _URL_RE.search(text)

    before_year = text[: year_match.start()].strip(" .") if year_match else text
    authors_text = before_year.split(".", 1)[0].strip()
    authors = [
        part.strip()
        for part in re.split(r"\s+(?:and|&)\s+|;\s*", authors_text)
        if part.strip()
    ]

    title = ""
    journal = ""
    if year_match:
        after_year = text[year_match.end():].strip(" .")
        parts = [part.strip() for part in after_year.split(".") if part.strip()]
        if parts:
            title = parts[0].strip("\"'")
        if len(parts) > 1:
            journal = parts[1]

    return BibliographyEntry(
        index=index,
        raw_text=raw_text,
        authors=authors,
        year=year,
        title=title,
        journal_or_publisher=journal,
        doi=doi_match.group(0).rstrip(".,") if doi_match else "",
        url=url_match.group(0).rstrip(".,") if url_match else "",
    )


async def parse_bibliography_entry(
    raw_text: str,
    index: int,
    llm_config: LLMConfig,
) -> BibliographyEntry:
    """Parse one entry with regex plus a conservative structured LLM pass."""
    fallback = parse_bibliography_entry_regex(raw_text, index)
    system = (
        "Parse one bibliography entry into structured citation fields. "
        "Use only information present in the entry. Leave unknown fields empty."
    )
    try:
        result = await chat_structured_with_fallback(
            prompt=raw_text[:2500],
            schema=_CitationFields,
            config=llm_config,
            system=system,
            include_schema_in_prompt=False,
            permissive_guardrails=True,
        )
    except Exception as exc:
        logger.debug("citation entry LLM parse failed; using regex fallback: %s", exc)
        return fallback

    authors = [author.strip() for author in result.authors if author.strip()]
    return BibliographyEntry(
        index=fallback.index,
        raw_text=raw_text,
        authors=authors or fallback.authors,
        year=result.year.strip() or fallback.year,
        title=result.title.strip() or fallback.title,
        journal_or_publisher=(
            result.journal_or_publisher.strip() or fallback.journal_or_publisher
        ),
        doi=result.doi.strip() or fallback.doi,
        url=result.url.strip() or fallback.url,
    )


def detect_inline_citations(pages: list[PageRecord]) -> list[InlineCitation]:
    citations: list[InlineCitation] = []
    for page in pages:
        for pattern in (_AUTHOR_YEAR_PAREN_RE, _AUTHOR_YEAR_TEXT_RE):
            for match in pattern.finditer(page.text):
                citations.append(
                    InlineCitation(
                        raw_text=match.group(0),
                        author_key=match.group("author").replace(" et al.", ""),
                        year=match.group("year"),
                        number=None,
                        page_doc_id=page.doc_id,
                        page_label=page.page_label,
                        char_start=match.start(),
                        char_end=match.end(),
                    )
                )
        for match in _NUMERIC_CITE_RE.finditer(page.text):
            citations.append(
                InlineCitation(
                    raw_text=match.group(0),
                    author_key=None,
                    year=None,
                    number=int(match.group("number")),
                    page_doc_id=page.doc_id,
                    page_label=page.page_label,
                    char_start=match.start(),
                    char_end=match.end(),
                )
            )
    return sorted(citations, key=lambda cite: (cite.page_doc_id, cite.char_start))


def detect_footnote_citations(pages: list[PageRecord]) -> list[InlineCitation]:
    """Detect bibliography-like footnote lines on body pages.

    This is heuristic by design: numbered line + a year token.
    """
    citations: list[InlineCitation] = []
    for page in pages:
        for match in _FOOTNOTE_LINE_RE.finditer(page.text):
            number = int(match.group("number"))
            raw = match.group(0).strip()
            citations.append(
                InlineCitation(
                    raw_text=raw,
                    author_key=None,
                    year=None,
                    number=number,
                    page_doc_id=page.doc_id,
                    page_label=page.page_label,
                    char_start=match.start(),
                    char_end=match.end(),
                )
            )
    return citations


def resolve_inline_citation(
    citation: InlineCitation,
    entries: list[BibliographyEntry],
) -> BibliographyEntry | None:
    if citation.number is not None:
        by_index = {entry.index: entry for entry in entries}
        return by_index.get(citation.number)
    if citation.author_key and citation.year:
        target_author = citation.author_key.casefold()
        target_year = citation.year[:4]
        for entry in entries:
            if entry.year[:4] != target_year:
                continue
            if first_author_key(entry.authors, fallback=entry.raw_text).casefold() == target_author:
                return entry
    return None


def _page_label(doc: Document) -> str | None:
    metadata = doc.metadata if isinstance(doc.metadata, dict) else {}
    label = metadata.get("page_label") or metadata.get("printed_page_label")
    if label:
        return str(label)
    if doc.sequence is not None:
        return str(doc.sequence)
    return None


def _page_records_for_document(db: Database, doc: Document) -> list[PageRecord]:
    page_children = sorted(
        db.query(Document, parent_id=doc.id, doc_type=DocType.page),
        key=lambda item: item.sequence or 0,
    )
    if page_children:
        return [
            PageRecord(
                doc_id=page.id,
                text=page.page_content or "",
                page_label=_page_label(page),
            )
            for page in page_children
        ]
    return [PageRecord(doc_id=doc.id, text=doc.page_content or "", page_label=_page_label(doc))]


def _resolve_source_document(inputs: dict[str, Any], state: State) -> Document | None:
    library_path = state.get("library_path") or inputs.get("library_path")
    if not library_path:
        return None
    db = db_manager.get_database(library_path)

    raw_documents = inputs.get("documents") or state.get("documents") or []
    candidate_ids = list(state.get("selected_doc_ids") or [])
    for raw in raw_documents:
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            candidate_ids.append(raw["id"])

    for doc_id in dict.fromkeys(candidate_ids):
        doc = db.get(Document, str(doc_id))
        if doc is None:
            continue
        return doc
    return None


async def extract_citations_for_document(
    db: Database,
    source_doc: Document,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    pages = _page_records_for_document(db, source_doc)
    document_ids: set[str] = {source_doc.id}
    full_text = "\n\n".join(page.text for page in pages)
    body_text, bibliography_text = find_bibliography_section(full_text)
    if not bibliography_text:
        return {"entries": [], "inline_citations": [], "claims": []}

    raw_entries = split_bibliography_entries(bibliography_text)
    entries = [
        await parse_bibliography_entry(raw_entry, index, llm_config)
        for index, raw_entry in enumerate(raw_entries, start=1)
    ]
    body_pages = _body_pages_before_bibliography(pages, body_text)
    inline_citations = detect_inline_citations(body_pages)
    inline_citations.extend(detect_footnote_citations(body_pages))
    inline_citations = sorted(
        inline_citations,
        key=lambda cite: (cite.page_doc_id, cite.char_start, cite.number or 0),
    )
    claims: list[dict[str, Any]] = []
    written_entity_ids: list[str] = []
    written_claim_ids: list[str] = []
    seen_claim_keys: set[tuple[str, str]] = set()
    for inline in inline_citations:
        entry = resolve_inline_citation(inline, entries)
        if entry is None:
            continue
        claim_key = (inline.page_doc_id, entry.canonical_name)
        if claim_key in seen_claim_keys:
            continue
        seen_claim_keys.add(claim_key)
        entity_id = upsert_entity(
            db,
            entry.canonical_name,
            EntityType.citation,
            aliases=[entry.title] if entry.title else [],
            description=entry.raw_text,
        )
        if entity_id is None:
            continue
        written_entity_ids.append(entity_id)
        entity = db.get(KnowledgeEntity, entity_id)
        if entity is not None:
            metadata = dict(entity.metadata or {})
            metadata["citation_entry"] = entry.as_metadata()
            entity.metadata = metadata
            db.save(entity)

        claim_id = save_claim(
            db,
            f"{source_doc.name} cites {entry.canonical_name}",
            source_document_id=inline.page_doc_id,
            entity_ids=[entity_id],
            source_excerpt=inline.raw_text,
            source_page_label=inline.page_label,
            source_char_start=inline.char_start,
            source_char_end=inline.char_end,
            claim_type=ClaimType.fact,
            confidence=0.8,
            metadata={
                "citation_entry": entry.as_metadata(),
                "inline_citation": {
                    "raw_text": inline.raw_text,
                    "author_key": inline.author_key,
                    "year": inline.year,
                    "number": inline.number,
                },
                "writer": "citations_extract",
            },
            subject_canonical=source_doc.name,
            predicate_verb="cites",
            object_phrase=entry.canonical_name,
            provider=llm_config.provider,
            model=llm_config.model,
        )
        if claim_id is not None:
            written_claim_ids.append(claim_id)
            document_ids.add(inline.page_doc_id)
            claims.append({"id": claim_id, "entity_id": entity_id, "entry": entry.as_metadata()})
    return {
        "entries": [entry.as_metadata() for entry in entries],
        "inline_citations": [
            {
                "raw_text": cite.raw_text,
                "page_doc_id": cite.page_doc_id,
                "page_label": cite.page_label,
                "author_key": cite.author_key,
                "year": cite.year,
                "number": cite.number,
            }
            for cite in inline_citations
        ],
        "claims": claims,
        "entity_ids": written_entity_ids,
        "claim_ids": written_claim_ids,
        "document_ids": sorted(document_ids),
    }


def _body_pages_before_bibliography(
    pages: list[PageRecord],
    body_text: str,
) -> list[PageRecord]:
    remaining = len(body_text)
    selected: list[PageRecord] = []
    for page in pages:
        if remaining <= 0:
            break
        page_text = page.text[:remaining]
        selected.append(
            PageRecord(
                doc_id=page.doc_id,
                text=page_text,
                page_label=page.page_label,
            )
        )
        remaining -= len(page.text) + 2
    return selected


@register_tool(
    name="citations_extract",
    display_name="Extract Citations",
    description="Extract bibliography entries and inline citation links",
    category="llm",
    icon="quote.bubble",
    color="indigo",
    uses_llm=True,
    supports_batch=False,
    supports_structured_output=True,
    input_ports=[
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            required=False,
            description="Document metadata from the source selector",
        ),
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=False,
            description="Optional document text.",
        ),
    ],
    output_ports=[
        PortDef(
            id="citations",
            name="Citations",
            port_type="output",
            data_type=DataType.JSON,
            description="Parsed bibliography and resolved inline citations",
        ),
        PortDef(
            id="text",
            name="Summary",
            port_type="output",
            data_type=DataType.TEXT,
            description="Human-readable citation extraction summary",
        ),
    ],
    sort_order=36,
)
async def citations_extract(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    library_path = state.get("library_path") or inputs.get("library_path")
    if not library_path:
        return {"citations": {}, "text": "", "error": "No library_path in workflow state"}
    db = db_manager.get_database(library_path)
    source_doc = _resolve_source_document(inputs, state)
    if source_doc is None:
        return {"citations": {}, "text": "", "error": "No source document selected"}

    result = await extract_citations_for_document(db, source_doc, llm_config)
    if result.get("entity_ids") or result.get("claim_ids"):
        emit_workflow_kg_changes(
            str(db.path.parent),
            entity_ids=result.get("entity_ids") or [],
            claim_ids=result.get("claim_ids") or [],
            document_ids=result.get("document_ids") or [],
        )
    if result.get("document_ids"):
        emit_workflow_citation_changes(
            str(db.path.parent),
            citation_ids=[],
            document_ids=result.get("document_ids") or [],
        )
    lines = [
        f"{len(result['entries'])} bibliography entries",
        f"{len(result['claims'])} resolved inline citations",
    ]
    return {
        "citations": result,
        "value": result,
        "text": "\n".join(lines),
        "cached": False,
    }
