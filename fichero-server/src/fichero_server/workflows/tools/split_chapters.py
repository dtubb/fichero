"""Split a book PDF into chapter child documents."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fichero_server.db import Database, db_manager
from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document, Status
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_CHAPTER_RE = re.compile(
    r"^(?:chapter|chapitre|cap[ií]tulo)\s+([0-9]+|[ivxlcdm]+|[a-z]+)\b",
    re.IGNORECASE,
)
_ROMAN_RE = re.compile(r"^(?:[IVX]|I{1,3}|IV|V?I{0,3}|IX|X{1,2})$")
_SPLIT_TOOL_KEY = "split_chapters_tool"


@dataclass(frozen=True)
class PdfPageText:
    sequence: int
    text: str
    first_lines: tuple[str, ...]
    large_heading: str | None = None


@dataclass(frozen=True)
class ChapterRange:
    title: str
    start_page: int
    end_page: int
    basis: str


def _normalise_title(title: str) -> str:
    return " ".join(title.strip().split())


def _chapter_title_from_line(line: str) -> str | None:
    title = _normalise_title(line.strip(" .:-"))
    if not title:
        return None
    if _CHAPTER_RE.match(title):
        return title
    if _ROMAN_RE.match(title):
        return title
    return None


def _outline_with_pypdf(path: Path) -> list[tuple[str, int]]:
    """Read outline rows with pypdf/PyPDF2 when either is available."""
    try:
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:
            from PyPDF2 import PdfReader  # type: ignore
    except ImportError:
        return []

    try:
        reader = PdfReader(str(path))
        outline = getattr(reader, "outline", None)
        if outline is None:
            outline = getattr(reader, "outlines", [])
    except Exception as exc:
        logger.debug("pypdf outline read failed for %s: %s", path, exc)
        return []

    rows: list[tuple[str, int]] = []

    def walk(items: Any) -> None:
        for item in list(items or []):
            if isinstance(item, list):
                walk(item)
                continue
            title = _normalise_title(str(getattr(item, "title", "") or ""))
            if not title:
                continue
            try:
                page_number = int(reader.get_destination_page_number(item)) + 1
            except Exception:
                continue
            if page_number > 0:
                rows.append((title, page_number))

    try:
        walk(outline)
    except Exception as exc:
        logger.debug("pypdf outline flatten failed for %s: %s", path, exc)
        return []
    return rows


def _outline_with_pymupdf(path: Path) -> tuple[list[tuple[str, int]], int]:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("split_chapters requires PyMuPDF") from exc

    doc = fitz.open(str(path))
    try:
        page_count = doc.page_count if hasattr(doc, "page_count") else len(doc)
        rows: list[tuple[str, int]] = []
        for entry in doc.get_toc() or []:
            if not isinstance(entry, (list, tuple)) or len(entry) < 3:
                continue
            try:
                level = int(entry[0])
                title = _normalise_title(str(entry[1]))
                page = int(entry[2])
            except (TypeError, ValueError):
                continue
            if level == 1 and title and page > 0:
                rows.append((title, page))
        return rows, page_count
    finally:
        doc.close()


def _page_texts_from_pdf(path: Path) -> list[PdfPageText]:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("split_chapters requires PyMuPDF") from exc

    doc = fitz.open(str(path))
    pages: list[PdfPageText] = []
    try:
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            first_lines = tuple(
                line.strip()
                for line in text.splitlines()[:5]
                if line.strip()
            )
            pages.append(
                PdfPageText(
                    sequence=index,
                    text=text,
                    first_lines=first_lines,
                    large_heading=_large_heading_from_page(page),
                )
            )
    finally:
        doc.close()
    return pages


def _large_heading_from_page(page: Any) -> str | None:
    try:
        text_dict = page.get_text("dict")
    except Exception:
        return None

    spans: list[tuple[str, float, float]] = []
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = _normalise_title(str(span.get("text") or ""))
                size = float(span.get("size") or 0)
                y_pos = float(span.get("bbox", [0, 9999])[1])
                if text:
                    spans.append((text, size, y_pos))
    if not spans:
        return None

    top_spans = [span for span in spans if span[2] < 180]
    if not top_spans:
        return None
    average = sum(size for _, size, _ in spans) / len(spans)
    text, size, _ = max(top_spans, key=lambda item: item[1])
    if size >= average * 1.35 and 3 <= len(text) <= 90:
        return text
    return None


def _page_texts_from_children(
    db: Database,
    source_doc: Document,
    fallback_path: Path,
) -> list[PdfPageText]:
    page_docs = sorted(
        db.query(Document, parent_id=source_doc.id, doc_type=DocType.page),
        key=lambda doc: doc.sequence or 0,
    )
    if not page_docs:
        return _page_texts_from_pdf(fallback_path)

    pages: list[PdfPageText] = []
    for page in page_docs:
        text = page.page_content or ""
        first_lines = tuple(
            line.strip()
            for line in text.splitlines()[:5]
            if line.strip()
        )
        pages.append(
            PdfPageText(
                sequence=page.sequence or len(pages) + 1,
                text=text,
                first_lines=first_lines,
            )
        )
    return pages


def _ranges_from_starts(
    starts: list[tuple[str, int, str]],
    *,
    page_count: int,
) -> list[ChapterRange]:
    deduped: list[tuple[str, int, str]] = []
    seen_pages: set[int] = set()
    for title, page, basis in sorted(starts, key=lambda row: row[1]):
        if page < 1 or page > page_count or page in seen_pages:
            continue
        deduped.append((title, page, basis))
        seen_pages.add(page)

    ranges: list[ChapterRange] = []
    for index, (title, start, basis) in enumerate(deduped):
        end = page_count
        if index + 1 < len(deduped):
            end = deduped[index + 1][1] - 1
        if end >= start:
            ranges.append(ChapterRange(title=title, start_page=start, end_page=end, basis=basis))
    return ranges


def detect_chapter_ranges(pdf_path: str | Path) -> list[ChapterRange]:
    """Detect chapter ranges from outline, heading heuristics, or fallback."""
    path = Path(pdf_path)
    outline_rows, page_count = _outline_with_pymupdf(path)
    pypdf_rows = _outline_with_pypdf(path)
    if pypdf_rows:
        outline_rows = pypdf_rows
    if outline_rows:
        ranges = _ranges_from_starts(
            [(title, page, "outline") for title, page in outline_rows],
            page_count=page_count,
        )
        if ranges:
            return ranges

    pages = _page_texts_from_pdf(path)
    if pages:
        starts = _heading_starts_from_pages(pages)
        ranges = _ranges_from_starts(starts, page_count=len(pages))
        if ranges:
            return ranges
        return [ChapterRange("Whole Book", 1, len(pages), "fallback")]
    return [ChapterRange("Whole Book", 1, max(page_count, 1), "fallback")]


def _heading_starts_from_pages(pages: list[PdfPageText]) -> list[tuple[str, int, str]]:
    starts: list[tuple[str, int, str]] = []
    for page in pages:
        for line in page.first_lines:
            title = _chapter_title_from_line(line)
            if title:
                starts.append((title, page.sequence, "heading"))
                break
        else:
            if page.large_heading:
                starts.append((_normalise_title(page.large_heading), page.sequence, "large_heading"))
    return starts


def _resolve_source_document(inputs: dict[str, Any], state: State) -> Document | None:
    library_path = state.get("library_path") or inputs.get("library_path")
    if not library_path:
        return None
    db = db_manager.get_database(library_path)

    raw_documents = inputs.get("documents") or state.get("documents") or []
    documents = [doc for doc in raw_documents if isinstance(doc, dict)]
    selected_doc_ids = state.get("selected_doc_ids") or []

    candidate_ids: list[str] = []
    candidate_ids.extend(str(doc_id) for doc_id in selected_doc_ids if doc_id)
    for doc in documents:
        doc_id = doc.get("id")
        if isinstance(doc_id, str):
            candidate_ids.append(doc_id)

    for doc_id in dict.fromkeys(candidate_ids):
        doc = db.get(Document, doc_id)
        if doc is None:
            continue
        if doc.doc_type == DocType.page and doc.parent_id:
            parent = db.get(Document, doc.parent_id)
            if parent and parent.path:
                return parent
        if doc.path and doc.path.lower().endswith(".pdf"):
            return doc
    return None


def split_pdf_into_chapter_documents(
    db: Database,
    source_doc: Document,
    *,
    replace_existing: bool = True,
) -> list[Document]:
    """Persist one group child per detected chapter under ``source_doc``."""
    if not source_doc.path:
        raise ValueError("source_doc must have a PDF path")

    pdf_path = Path(source_doc.path)
    ranges = detect_chapter_ranges(pdf_path)
    pages = _page_texts_from_children(db, source_doc, pdf_path)
    page_text_by_sequence = {page.sequence: page.text for page in pages}

    if replace_existing:
        for child in db.query(Document, parent_id=source_doc.id):
            if (child.metadata or {}).get(_SPLIT_TOOL_KEY):
                db.delete(child)

    chapters: list[Document] = []
    for index, chapter in enumerate(ranges, start=1):
        content = "\n\n".join(
            page_text_by_sequence.get(page, "")
            for page in range(chapter.start_page, chapter.end_page + 1)
        ).strip()
        name = f"{source_doc.name} - {chapter.title}"
        chapter_doc = Document(
            parent_id=source_doc.id,
            doc_type=DocType.group,
            file_type=None,
            name=name,
            path=None,
            sequence=index,
            status=Status.completed,
            page_content=content or None,
            metadata={
                _SPLIT_TOOL_KEY: True,
                "source_document_id": source_doc.id,
                "source_document_name": source_doc.name,
                "chapter_title": chapter.title,
                "chapter_index": index,
                "page_range": {
                    "start": chapter.start_page,
                    "end": chapter.end_page,
                },
                "start_page": chapter.start_page,
                "end_page": chapter.end_page,
                "basis": chapter.basis,
            },
        )
        db.save(chapter_doc)
        chapters.append(chapter_doc)
    return chapters


@register_tool(
    name="split_chapters",
    display_name="Split Chapters",
    description="Split a book PDF into chapter documents using TOC and heading cues",
    category="source",
    icon="book.pages",
    color="green",
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
            id="documents",
            name="Chapter Documents",
            port_type="output",
            data_type=DataType.JSON,
            description="Created chapter child documents",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of chapters created",
        ),
    ],
    sort_order=4,
)
async def split_chapters(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Workflow tool wrapper for chapter splitting."""
    source_doc = _resolve_source_document(inputs, state)
    if source_doc is None or not source_doc.path:
        return {
            "documents": [],
            "count": 0,
            "text": "",
            "error": "No PDF source document found for chapter splitting",
        }

    library_path = state.get("library_path") or inputs.get("library_path")
    db = db_manager.get_database(library_path)
    chapters = split_pdf_into_chapter_documents(db, source_doc)
    lines = [
        f"- {doc.name} ({doc.metadata['start_page']}-{doc.metadata['end_page']})"
        for doc in chapters
    ]
    return {
        "documents": [doc.model_dump(mode="json") for doc in chapters],
        "value": [doc.model_dump(mode="json") for doc in chapters],
        "count": len(chapters),
        "text": "\n".join(lines),
        "cached": False,
    }
