"""Split diary pages into per-day entry nodes (Daniel 2026-08-14).

A diary book's pages carry one or MANY dated entries per page. This tool
reads each page's transcript, extracts the entries with a structured LLM
call, and persists one CHILD node per entry under the page:

- ``attributes = {"date": "YYYY-MM-DD"}`` with the ``diary_entry``
  prototype (created on first use with a date-ROLE declaration), so the
  library's Data view — timeline and calendar — renders them immediately;
- ``page_content`` = the entry's text;
- ``bbox`` = the union of the page's OCR line boxes whose character spans
  fall inside the entry's span of the transcript — the per-day region on
  the page image. No geometry artifact → no bbox, recorded honestly.

Date strings are normalized DETERMINISTICALLY through the historical-date
parser — the LLM proposes, ``parse_historical_date`` disposes; an entry
whose date cannot be parsed keeps the raw date text as its name and gets
NO date attribute (undated is a recorded fact, never a guess).

Re-running replaces this tool's previous children under the same page
(idempotent, like split_chapters).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from fichero_server.db import Database, db_manager
from fichero_server.histdate import parse_historical_date
from fichero_server.llm import LLMConfig, chat_structured
from fichero_server.models import Artifact, DocType, Document, Status
from fichero_server.models.knowledge import (
    ClassificationDimension,
    ClassificationValue,
)
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_DIARY_TOOL_KEY = "diary_entries_tool"
DEFAULT_PROTOTYPE_KEY = "diary_entry"

_SYSTEM = (
    "You segment historical diary transcripts into dated entries. "
    "Preserve the transcript text VERBATIM — never paraphrase, correct "
    "spelling, or drop lines. Every character of the transcript belongs to "
    "exactly one entry (leading matter before the first date belongs to the "
    "first entry)."
)

_PROMPT = """Split this diary page transcript into its dated entries.

Rules:
- One entry per date heading. A page may hold one entry or several.
- `date_text` is the date EXACTLY as written on the page (e.g. "Jan 8th",
  "8 de enero de 1942").
- `date_iso` is your best reading as YYYY-MM-DD, or null when the page
  gives too little to tell. The diary year context, if visible, applies.
- `text` is the entry's VERBATIM transcript text, including its heading.

Transcript:
{transcript}
"""


class DiaryEntry(BaseModel):
    date_text: str = Field(description="The date as written on the page")
    date_iso: str | None = Field(
        default=None, description="YYYY-MM-DD, or null when unreadable"
    )
    text: str = Field(description="The entry's verbatim transcript text")


class DiaryPageSplit(BaseModel):
    entries: list[DiaryEntry] = Field(default_factory=list)


def ensure_diary_prototype(db: Database, key: str) -> None:
    """Create the prototype with a date-ROLE declaration when absent — the
    declaration is what lights up the timeline/calendar renderers."""
    existing = db.query(
        ClassificationValue,
        dimension=ClassificationDimension.document_prototype,
        key=key,
    )
    if existing:
        return
    db.save(
        ClassificationValue(
            dimension=ClassificationDimension.document_prototype,
            key=key,
            label=key.replace("_", " ").title(),
            attributes={"date": {"type": "date", "role": "date"}},
        )
    )
    logger.info("diary_entries created missing prototype %r", key)


def _normalized_iso(entry: DiaryEntry) -> str | None:
    """Deterministic date: parse the on-page text first, the LLM's ISO
    reading second. Either must survive the historical-date parser."""
    for candidate in (entry.date_text, entry.date_iso):
        if not candidate:
            continue
        parsed = parse_historical_date(str(candidate))
        if parsed is None:
            continue
        iso = (parsed.meta or {}).get("converted_gregorian_iso")
        if iso:
            return str(iso)
    return None


def _geometry_boxes(db: Database, page: Document) -> tuple[str, list[Any]]:
    """The page's newest transcription geometry: (artifact content, boxes)."""
    artifacts = db.query(Artifact, document_id=page.id) or []
    dated = sorted(
        (a for a in artifacts if a.ocr_geometry and a.ocr_geometry.boxes),
        key=lambda a: (a.created_at is None, a.created_at),
    )
    if not dated:
        return "", []
    newest = dated[-1]
    return newest.ocr_geometry.text or newest.content or "", list(
        newest.ocr_geometry.boxes
    )


def _entry_spans(content: str, entries: list[DiaryEntry]) -> list[tuple[int, int] | None]:
    """Locate each entry's character span in the geometry content by its
    leading words, in order. ponytail: prefix search with normalized
    whitespace; an entry whose prefix is not found gets no span (and so no
    bbox) — recorded, never guessed."""
    spans: list[tuple[int, int] | None] = []
    haystack = content
    cursor = 0
    starts: list[int | None] = []
    for entry in entries:
        prefix = " ".join(entry.text.split())[:24]
        found: int | None = None
        if prefix:
            probe = prefix
            while len(probe) >= 8:
                index = haystack.find(probe, cursor)
                if index >= 0:
                    found = index
                    cursor = index + 1
                    break
                probe = probe[: len(probe) - 4]
        starts.append(found)
    for position, start in enumerate(starts):
        if start is None:
            spans.append(None)
            continue
        next_start = next(
            (s for s in starts[position + 1:] if s is not None), len(haystack)
        )
        spans.append((start, max(next_start, start + 1)))
    return spans


def _page_pixel_size(page: Document) -> tuple[int, int] | None:
    """The page image's pixel dimensions from its metadata — the scale that
    turns normalized OCR geometry into ``Document.bbox`` pixel ints."""
    for source in (page.metadata or {}, page.source_metadata or {}):
        width, height = source.get("width"), source.get("height")
        try:
            width_px, height_px = int(width), int(height)
        except (TypeError, ValueError):
            continue
        if width_px > 0 and height_px > 0:
            return width_px, height_px
    return None


def _bbox_union(
    boxes: list[Any],
    span: tuple[int, int] | None,
    pixel_size: tuple[int, int] | None,
) -> tuple[int, int, int, int] | None:
    """Union of the normalized [x, y, w, h] line boxes whose char span
    overlaps the entry span, scaled to page pixels (``Document.bbox`` is
    pixel ints). No page dimensions → no bbox, recorded honestly."""
    if span is None or pixel_size is None:
        return None
    xs0: list[float] = []
    ys0: list[float] = []
    xs1: list[float] = []
    ys1: list[float] = []
    for box in boxes:
        start = getattr(box, "char_start", None)
        end = getattr(box, "char_end", None)
        bbox = getattr(box, "bbox", None)
        if start is None or end is None or not bbox or len(bbox) != 4:
            continue
        if end <= span[0] or start >= span[1]:
            continue
        xs0.append(bbox[0])
        ys0.append(bbox[1])
        xs1.append(bbox[0] + bbox[2])
        ys1.append(bbox[1] + bbox[3])
    if not xs0:
        return None
    x0, y0 = min(xs0), min(ys0)
    width_px, height_px = pixel_size
    return (
        round(x0 * width_px),
        round(y0 * height_px),
        round((max(xs1) - x0) * width_px),
        round((max(ys1) - y0) * height_px),
    )


async def split_page_into_entries(
    db: Database,
    page: Document,
    llm_config: LLMConfig,
    *,
    prototype_key: str = DEFAULT_PROTOTYPE_KEY,
) -> list[Document]:
    """Extract, then persist one child node per entry under ``page``."""
    transcript = (page.page_content or "").strip()
    if not transcript:
        raise ValueError(f"page {page.id} has no transcript to split")

    result = await chat_structured(
        _PROMPT.format(transcript=transcript),
        DiaryPageSplit,
        llm_config,
        system=_SYSTEM,
        use_case="diary_entries",
    )
    entries = [entry for entry in result.entries if entry.text.strip()]
    if not entries:
        return []

    ensure_diary_prototype(db, prototype_key)

    geometry_content, boxes = _geometry_boxes(db, page)
    pixel_size = _page_pixel_size(page)
    spans = (
        _entry_spans(geometry_content, entries)
        if geometry_content and boxes
        else [None] * len(entries)
    )

    # Idempotent re-run: this tool's previous children go, others stay.
    for child in db.query(Document, parent_id=page.id) or []:
        if (child.metadata or {}).get(_DIARY_TOOL_KEY):
            db.delete(child)

    created: list[Document] = []
    for index, entry in enumerate(entries, start=1):
        iso = _normalized_iso(entry)
        bbox = _bbox_union(boxes, spans[index - 1], pixel_size)
        node = Document(
            parent_id=page.id,
            doc_type=DocType.file,
            file_type=None,
            node_kind="entry",
            name=iso or entry.date_text.strip() or f"Entry {index}",
            path=None,
            sequence=index,
            status=Status.completed,
            page_content=entry.text,
            bbox=bbox,
            prototype_key=prototype_key,
            attributes={"date": iso} if iso else {},
            metadata={
                _DIARY_TOOL_KEY: True,
                "source_document_id": page.id,
                "source_document_name": page.name,
                "date_text": entry.date_text,
                "date_parsed": iso is not None,
                "bbox_basis": "ocr_geometry" if bbox else ("no_page_dimensions" if pixel_size is None else "none"),
            },
        )
        db.save(node)
        created.append(node)
    return created


@register_tool(
    name="diary_entries",
    display_name="Split Diary Entries",
    description=(
        "Split each page's transcript into per-day entry nodes with a date "
        "attribute and the day's bounding box — the timeline/calendar feed"
    ),
    category="llm",
    icon="calendar.day.timeline.left",
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
            description="Transcribed pages to split into diary entries",
        ),
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=False,
            description=(
                "Ordering dependency on the transcription node — the splitter "
                "reads each page's stored transcript, this port just makes it "
                "run after transcription lands"
            ),
        ),
    ],
    output_ports=[
        PortDef(
            id="documents",
            name="Entry Documents",
            port_type="output",
            data_type=DataType.JSON,
            description="Created per-day entry child documents",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of entries created",
        ),
        PortDef(
            id="text",
            name="Summary",
            port_type="output",
            data_type=DataType.TEXT,
            description="One line per created entry",
        ),
    ],
    sort_order=5,
)
async def diary_entries(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Workflow tool wrapper: split every input page into entry nodes."""
    library_path = state.get("library_path") or inputs.get("library_path")
    db = db_manager.get_database(library_path)
    prototype_key = str(
        inputs.get("prototype_key") or DEFAULT_PROTOTYPE_KEY
    ).strip() or DEFAULT_PROTOTYPE_KEY

    raw_documents = inputs.get("documents") or state.get("documents") or []
    created: list[Document] = []
    lines: list[str] = []
    errors: list[str] = []
    for raw in raw_documents:
        doc_id = raw.get("id") if isinstance(raw, dict) else None
        page = db.get(Document, doc_id) if doc_id else None
        if page is None:
            errors.append(f"document {doc_id!r} not found")
            continue
        try:
            entries = await split_page_into_entries(
                db, page, llm_config, prototype_key=prototype_key
            )
        except ValueError as exc:
            errors.append(str(exc))
            continue
        created.extend(entries)
        for node in entries:
            marker = "▣" if node.bbox else "·"
            lines.append(f"{marker} {node.name} — {page.name}")

    summary = "\n".join(lines) if lines else "No entries created"
    if errors:
        summary += "\n" + "\n".join(f"! {message}" for message in errors)
    return {
        "documents": [doc.model_dump(mode="json") for doc in created],
        "value": [doc.model_dump(mode="json") for doc in created],
        "count": len(created),
        "text": summary,
        "error": "; ".join(errors) if errors and not created else None,
        "cached": False,
    }
