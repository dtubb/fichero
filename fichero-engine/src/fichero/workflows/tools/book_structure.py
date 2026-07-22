"""Book structure extraction over a flat page list.

Phase 1 of #1279 uses the embedded PDF outline / table of contents to build
hierarchical chapter / section / subsection ranges over page ``sequence``.
Pages remain where they are; the structure is a parallel table keyed by the
source document plus page-range bounds.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

from fichero.db import Database, db_manager
from fichero.models.knowledge import BookStructureNode
from fichero.models import DocType, Document
from fichero.workflows.registry import register_tool
from fichero.workflows.types import DataType, PortDef, State
from fichero.llm import LLMConfig
from fichero.workflows.tools.split_chapters import _heading_starts_from_pages, _page_texts_from_pdf

_NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+){1,2})\.?\s+(.{3,120})$")
_SECTION_HEADING_RE = re.compile(
    r"^(section|subsection)\s+(\d+(?:\.\d+){0,2})\.?\s+(.{3,120})$",
    re.IGNORECASE,
)


def _kind_for_level(level: int) -> str:
    return {1: "chapter", 2: "section", 3: "subsection"}.get(level, "section")


def _normalise_toc_entry(entry: Any) -> tuple[int, str, int] | None:
    """Return (level, title, page) for a PyMuPDF TOC row."""
    if not isinstance(entry, (list, tuple)) or len(entry) < 3:
        return None
    try:
        level = int(entry[0])
        title = str(entry[1]).strip()
        page = int(entry[2])
    except (TypeError, ValueError):
        return None
    if level < 1 or page < 1 or not title:
        return None
    return level, title, page


def build_book_structure_from_toc(
    toc: list[Any],
    *,
    source_document_id: str,
    page_count: int,
    source_page_labels: Sequence[str] | None = None,
) -> list[BookStructureNode]:
    """Build hierarchical book-structure nodes from a TOC outline."""
    rows: list[tuple[int, str, int]] = []
    for entry in toc:
        normalised = _normalise_toc_entry(entry)
        if normalised is not None:
            rows.append(normalised)

    if not rows:
        return []

    nodes: list[BookStructureNode] = []
    stack: list[BookStructureNode] = []
    for level, title, page in rows:
        while stack and stack[-1].level >= level:
            stack.pop()
        parent = stack[-1] if stack else None
        source_page_label = str(page)
        if source_page_labels and 1 <= page <= len(source_page_labels):
            source_page_label = source_page_labels[page - 1] or source_page_label
        node = BookStructureNode(
            source_document_id=source_document_id,
            title=title,
            level=level,
            kind=_kind_for_level(level),
            start_sequence=page,
            end_sequence=None,
            parent_structure_id=parent.id if parent else None,
            basis="toc",
            confidence=1.0,
            source_page_label=source_page_label,
            source_excerpt=title,
            metadata={"toc_entry": {"level": level, "title": title, "page": page}},
        )
        nodes.append(node)
        stack.append(node)

    for index, node in enumerate(nodes):
        end_sequence = page_count
        for next_node in nodes[index + 1 :]:
            if next_node.level <= node.level:
                end_sequence = next_node.start_sequence - 1
                break
        if end_sequence < node.start_sequence:
            end_sequence = node.start_sequence
        node.end_sequence = end_sequence

    return nodes


def extract_book_structure_from_pdf(
    pdf_path: str | Path,
    *,
    source_document_id: str,
) -> list[BookStructureNode]:
    """Read a PDF's outline/headings and convert them to structure rows."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("Book structure extraction requires PyMuPDF") from exc

    path = Path(pdf_path)
    doc = fitz.open(str(path))
    try:
        toc: list[Any] = []
        try:
            toc = list(doc.get_toc(simple=False))
        except TypeError:
            toc = list(doc.get_toc())
        page_count = doc.page_count if hasattr(doc, "page_count") else len(doc)
        page_labels = [
            (doc[i].get_label() or str(i + 1))
            for i in range(page_count)
        ]
        nodes = build_book_structure_from_toc(
            toc,
            source_document_id=source_document_id,
            page_count=page_count,
            source_page_labels=page_labels,
        )
        if nodes:
            return nodes
    finally:
        doc.close()

    pages = _page_texts_from_pdf(path)
    if not pages:
        return []
    starts = _heading_starts_from_pages(pages) + _section_starts_from_pages(pages)
    if not starts:
        return [
            BookStructureNode(
                source_document_id=source_document_id,
                title="Whole Book",
                level=1,
                kind="chapter",
                start_sequence=1,
                end_sequence=len(pages),
                basis="fallback",
                confidence=0.4,
                source_page_label="1",
                source_excerpt="Whole Book",
            )
        ]

    rows: list[tuple[int, str, int, str]] = []
    for title, page, basis in starts:
        level = _level_from_heading(title)
        rows.append((level, title, page, basis))
    return _build_nodes_from_heading_rows(
        rows,
        source_document_id=source_document_id,
        page_count=len(pages),
    )


def _section_starts_from_pages(pages: list[Any]) -> list[tuple[str, int, str]]:
    starts: list[tuple[str, int, str]] = []
    for page in pages:
        for line in page.first_lines:
            normalized = " ".join(line.strip().split())
            if _NUMBERED_HEADING_RE.match(normalized) or _SECTION_HEADING_RE.match(normalized):
                starts.append((normalized, page.sequence, "heading"))
                break
    return starts


def _level_from_heading(title: str) -> int:
    stripped = title.strip()
    if stripped.lower().startswith(("chapter ", "chapitre ", "capítulo ", "capitulo ")):
        return 1
    section_match = _SECTION_HEADING_RE.match(stripped)
    if section_match:
        return 3 if section_match.group(1).lower() == "subsection" else 2
    first = stripped.split(maxsplit=1)[0].strip(".")
    if first.count(".") >= 2:
        return 3
    if first.count(".") == 1:
        return 2
    return 1


def _build_nodes_from_heading_rows(
    rows: list[tuple[int, str, int, str]],
    *,
    source_document_id: str,
    page_count: int,
) -> list[BookStructureNode]:
    nodes: list[BookStructureNode] = []
    stack: list[BookStructureNode] = []
    seen: set[tuple[int, str]] = set()
    for level, title, page, basis in sorted(rows, key=lambda row: (row[2], row[0])):
        if page < 1 or page > page_count or (page, title) in seen:
            continue
        seen.add((page, title))
        while stack and stack[-1].level >= level:
            stack.pop()
        parent = stack[-1] if stack else None
        node = BookStructureNode(
            source_document_id=source_document_id,
            title=title,
            level=level,
            kind=_kind_for_level(level),
            start_sequence=page,
            end_sequence=None,
            parent_structure_id=parent.id if parent else None,
            basis=basis,
            confidence=0.75 if basis == "heading" else 0.6,
            source_page_label=str(page),
            source_excerpt=title,
            metadata={"heading": {"title": title, "page": page}},
        )
        nodes.append(node)
        stack.append(node)

    for index, node in enumerate(nodes):
        end_sequence = page_count
        for next_node in nodes[index + 1 :]:
            if next_node.level <= node.level:
                end_sequence = next_node.start_sequence - 1
                break
        node.end_sequence = max(node.start_sequence, end_sequence)
    return nodes


def persist_book_structure(
    db: Database,
    nodes: list[BookStructureNode],
    *,
    replace_existing: bool = True,
) -> int:
    """Save structure rows into DuckDB, replacing prior rows if requested."""
    if not nodes:
        return 0

    source_document_id = nodes[0].source_document_id
    if replace_existing:
        for existing in db.query(BookStructureNode, source_document_id=source_document_id):
            db.delete(existing)

    for node in nodes:
        db.save(node)
    return len(nodes)


def render_book_structure_markdown(nodes: list[BookStructureNode]) -> str:
    """Render structure nodes as indented markdown."""
    if not nodes:
        return ""

    lines: list[str] = []
    for node in sorted(nodes, key=lambda n: (n.start_sequence, n.level, n.title.casefold())):
        indent = "  " * max(node.level - 1, 0)
        end = node.end_sequence if node.end_sequence is not None else node.start_sequence
        lines.append(f"{indent}- {node.kind.title()}: {node.title} ({node.start_sequence}-{end})")
    return "\n".join(lines)


def book_structure_tree(nodes: list[BookStructureNode]) -> list[dict[str, Any]]:
    """Serialize flat structure rows as nested JSON for Document.structure."""
    by_id: dict[str, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for node in sorted(nodes, key=lambda item: (item.start_sequence, item.level, item.title.casefold())):
        payload: dict[str, Any] = {
            "id": node.id,
            "title": node.title,
            "kind": node.kind,
            "level": node.level,
            "page_range": {
                "start": node.start_sequence,
                "end": node.end_sequence or node.start_sequence,
            },
            "basis": node.basis,
            "confidence": node.confidence,
            "source_page_label": node.source_page_label,
            "children": [],
        }
        by_id[node.id] = payload
        if node.parent_structure_id and node.parent_structure_id in by_id:
            by_id[node.parent_structure_id]["children"].append(payload)
        else:
            roots.append(payload)
    return roots


def _resolve_source_document(
    inputs: dict[str, Any],
    state: State,
) -> Document | None:
    library_path = state.get("library_path") or inputs.get("library_path")
    if not library_path:
        return None
    db = db_manager.get_database(library_path)

    raw_documents = inputs.get("documents") or state.get("documents") or []
    documents = [doc for doc in raw_documents if isinstance(doc, dict)]
    selected_doc_ids = state.get("selected_doc_ids") or []

    candidate_ids: list[str] = []
    if selected_doc_ids:
        candidate_ids.extend(selected_doc_ids)
    for doc in documents:
        doc_id = doc.get("id")
        if isinstance(doc_id, str):
            candidate_ids.append(doc_id)

    seen: set[str] = set()
    for doc_id in candidate_ids:
        if doc_id in seen:
            continue
        seen.add(doc_id)
        doc = db.get(Document, doc_id)
        if doc is None:
            continue
        if doc.doc_type == DocType.page and doc.parent_id:
            parent = db.get(Document, doc.parent_id)
            if parent and parent.path:
                return parent
        if doc.path and doc.path.lower().endswith(".pdf"):
            return doc
        if doc.doc_type == DocType.folder:
            stack = list(db.query(Document, parent_id=doc.id))
            while stack:
                child = stack.pop(0)
                if child.path and child.path.lower().endswith(".pdf"):
                    return child
                if child.doc_type == DocType.folder:
                    stack.extend(db.query(Document, parent_id=child.id))
    return None


@register_tool(
    name="book_structure",
    display_name="Book Structure",
    description="Extract chapter/section/subsection ranges from a book PDF outline",
    category="source",
    icon="list.bullet.indent",
    color="gray",
    uses_llm=False,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            required=False,
            description="Document metadata from the source selector",
        ),
    ],
    output_ports=[
        PortDef(
            id="structure",
            name="Structure",
            port_type="output",
            data_type=DataType.JSON,
            description="Hierarchical structure nodes",
        ),
    ],
    sort_order=4,
)
async def book_structure(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Workflow tool wrapper around the TOC parser."""
    source_doc = _resolve_source_document(inputs, state)
    if source_doc is None or not source_doc.path:
        return {
            "text": "",
            "value": [],
            "error": "No PDF source document found for book structure extraction",
        }

    nodes = extract_book_structure_from_pdf(
        source_doc.path,
        source_document_id=source_doc.id,
    )
    if not nodes:
        return {
            "text": "",
            "value": [],
            "warning": "No embedded table of contents found",
        }

    library_path = state.get("library_path", "")
    if library_path:
        db = db_manager.get_database(library_path)
        persist_book_structure(db, nodes)
        source_doc.structure = book_structure_tree(nodes)
        db.save(source_doc)

    return {
        "text": render_book_structure_markdown(nodes),
        "value": [node.model_dump(mode="json") for node in nodes],
        "cached": False,
    }
