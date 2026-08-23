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
from fichero_server.db.node_levels import resolve_workflow_targets
from fichero_server.histdate import parse_historical_date
from fichero_server.llm import LLMConfig, chat_structured
from fichero_server.models.anchors import NodeRegion, RegionConfidence
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
  (The heading is stripped before storage — never repeat the date again
  inside the body.)
- Writing belongs to the heading ABOVE it, never the one below: when a
  heading has no writing under it, that day's `text` is just the heading
  line. NEVER move an earlier day's writing under a later day's heading.

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


def _geometry_boxes(db: Database, page: Document) -> tuple[str, list[Any], str | None]:
    """The page's newest transcription geometry: (content, boxes, provider).

    The provider is returned because it decides how much the resulting region
    is WORTH. Apple Vision detects boxes from the pixels; a VLM is ASKED for
    them and answers — `detect_regions` says so itself ("VLM boxes are claimed,
    not measured"). Collapsing both into `measured` would make a model's guess
    indistinguishable from a measurement, which is the exact distinction
    `RegionConfidence` exists to preserve.
    """
    artifacts = db.query(Artifact, document_id=page.id) or []
    dated = sorted(
        (a for a in artifacts if a.ocr_geometry and a.ocr_geometry.boxes),
        key=lambda a: (a.created_at is None, a.created_at),
    )
    if not dated:
        return "", [], None
    newest = dated[-1]
    return (
        newest.ocr_geometry.text or newest.content or "",
        list(newest.ocr_geometry.boxes),
        newest.provider or newest.ocr_geometry.provider,
    )


def _body_without_date_heading(text: str, date_text: str) -> str:
    """The entry's prose without its date heading repeated as line one.

    The heading is STRUCTURED data — it is the node's name and the
    ``date_text`` metadata — so echoing it in page_content reads the same
    date twice everywhere the entry renders (Daniel 2026-08-15). Extraction
    stays verbatim (the heading is needed to locate the char span for the
    bbox); only the stored body drops it, and only when the FIRST line is
    recognizably the heading — never a guess deeper in the text.
    """
    lines = text.splitlines()
    if not lines:
        return text.strip()
    raw_first = lines[0]
    first = " ".join(raw_first.split()).strip().rstrip(".,:;").lower()
    heading = " ".join(date_text.split()).strip().rstrip(".,:;").lower()
    if heading and (first == heading or first.startswith(heading) or heading.startswith(first)):
        return "\n".join(lines[1:]).strip()
    # A PRINTED heading with OCR noise ("TUESDAY, JANUARY § 7") rarely
    # equals date_text — recognize it structurally: short, set in caps,
    # naming a month plus a day number or weekday (2026-08-15 night; the
    # same rule the client applies at display time for older entries).
    letters = [c for c in raw_first if c.isalpha()]
    if len(raw_first) <= 60 and letters and sum(c.isupper() for c in letters) * 10 >= len(letters) * 9:
        tokens = {tok for tok in "".join(c if c.isalnum() else " " for c in first).split()}
        months = {m for m in ("january february march april may june july august "
                              "september october november december").split()}
        weekdays = {d for d in ("monday tuesday wednesday thursday friday saturday "
                                "sunday").split()}
        if tokens & months and (tokens & weekdays or any(tok.isdigit() and len(tok) <= 2 for tok in tokens)):
            return "\n".join(lines[1:]).strip()
    return text.strip()


#: Punctuation the ledger's PRINTED date headers vary on between the page and
#: the OCR of the page: the stationery prints "SUNDAY. JANUARY 8. 1933" while
#: transcripts write "SUNDAY, JANUARY 8, 1933" — same heading, different
#: separators. Dropped on BOTH sides of the heading match, never for body text.
_HEADING_PUNCTUATION = ".,;:"


def _normalized_with_offsets(
    content: str, *, drop_punctuation: bool = False
) -> tuple[str, list[int]]:
    """Whitespace-collapsed copy of ``content`` plus, per normalized char,
    its RAW offset — so a match in the normalized text maps back to the
    geometry's own coordinates. With ``drop_punctuation`` the heading
    separators vanish too (see ``_HEADING_PUNCTUATION``)."""
    chars: list[str] = []
    offsets: list[int] = []
    previous_space = True
    for index, ch in enumerate(content):
        if ch.isspace() or (drop_punctuation and ch in _HEADING_PUNCTUATION):
            if previous_space:
                continue
            chars.append(" ")
            offsets.append(index)
            previous_space = True
        else:
            chars.append(ch)
            offsets.append(index)
            previous_space = False
    return "".join(chars), offsets


def _entry_spans(content: str, entries: list[DiaryEntry]) -> list[tuple[int, int] | None]:
    """Locate each entry's character span in the geometry content by its
    leading words, in order. The search runs over a whitespace-NORMALIZED
    copy mapped back to raw offsets (2026-08-17): the prefix is normalized,
    so searching the raw content meant any entry whose opening words cross
    a line break silently got no span — and so no bbox ("some pages have
    word level bounding boxes, many don't"). An entry whose prefix is
    genuinely absent still gets None — recorded, never guessed."""
    spans: list[tuple[int, int] | None] = []
    haystack, offsets = _normalized_with_offsets(content)
    # Heading search runs punctuation-blind on BOTH sides (2026-08-23): the
    # stationery prints "SUNDAY. JANUARY 8. 1933", transcripts write commas,
    # and the strict match lost the anchor over a period.
    bare_haystack, bare_offsets = _normalized_with_offsets(content, drop_punctuation=True)
    # Case-blind too: the stationery sets headings in CAPS, the transcript
    # writes "Wednesday, January 11" — the second-largest miss class on the
    # real corpus after punctuation.
    bare_haystack = bare_haystack.casefold()
    cursor = 0
    bare_cursor = 0
    starts: list[int | None] = []
    for entry in entries:
        found: int | None = None
        # The PRINTED date heading first (2026-08-23, "not all the entries
        # have them"): entry text is split from the LLM vision transcript,
        # but the geometry is OCR — and on handwritten pages the OCR mangles
        # every cursive line ("Watching laboratory…" came back "dealing
        # elenty else use t"), so a body-prefix match failed for 128 of 201
        # entries. The typeset date header is the one line OCR reads
        # reliably, and structurally an entry IS the band from its heading
        # to the next — so the heading is the anchor, the prefix the
        # fallback.
        heading = " ".join(
            ch for ch in entry.date_text.split() if ch
        )
        heading = " ".join(
            "".join(c for c in heading if c not in _HEADING_PUNCTUATION).split()
        ).casefold()[:24]
        if heading:
            probe = heading
            while len(probe) >= 8:
                index = bare_haystack.find(probe, bare_cursor)
                if index >= 0:
                    found = bare_offsets[index]
                    bare_cursor = index + 1
                    break
                probe = probe[: len(probe) - 4]
        if found is None:
            prefix = " ".join(entry.text.split())[:24]
            if prefix:
                probe = prefix
                while len(probe) >= 8:
                    index = haystack.find(probe, cursor)
                    if index >= 0:
                        found = offsets[index]
                        cursor = index + 1
                        break
                    probe = probe[: len(probe) - 4]
        starts.append(found)
    for position, start in enumerate(starts):
        if start is None:
            spans.append(None)
            continue
        # RAW length, not normalized (2026-08-23): starts are raw offsets,
        # and the normalized haystack is shorter — the old default cut the
        # LAST entry's span short of the page's trailing boxes.
        next_start = next(
            (s for s in starts[position + 1:] if s is not None), len(content)
        )
        spans.append((start, max(next_start, start + 1)))
    return spans


#: Providers whose boxes are DETECTED from pixels rather than claimed by a
#: model. Apple Vision measures; a VLM is asked and answers.
_MEASURING_PROVIDERS = {"apple", "apple-vision", "vision"}


def _region_confidence(provider: str | None) -> RegionConfidence:
    """How much an entry region derived from these boxes is worth.

    Unknown provenance is treated as NOMINAL rather than measured: the safe
    default is to under-claim. A region wrongly marked `measured` tells a
    reader the fold was verified when nobody verified it, and that is the
    failure this vocabulary was introduced to stop.
    """
    if provider and provider.strip().casefold() in _MEASURING_PROVIDERS:
        return RegionConfidence.measured
    return RegionConfidence.nominal


def _region_union(
    boxes: list[Any],
    span: tuple[int, int] | None,
    provider: str | None = None,
) -> NodeRegion | None:
    """Union of the OCR line boxes overlapping the entry's char span.

    The entry node's ``parent_id`` IS the page, so where the entry sits on that
    page is exactly ``region_in_parent`` — the one field for that fact.

    This used to scale the union DOWN into ``Document.bbox`` pixel ints, which
    needed the page's pixel dimensions and returned None without them. The OCR
    boxes are already normalized, so the conversion only ever lost information:
    entries whose page carried no width/height in metadata were given no
    geometry at all despite the geometry being right there. Keeping it
    normalized removes the conversion, the helper that fed it, and that entire
    failure mode.
    """
    if span is None:
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
    try:
        return NodeRegion(
            rect=[x0, y0, max(xs1) - x0, max(ys1) - y0],
            # The union of MEASURED OCR line boxes — not a nominal guess at
            # where an entry might fall.
            confidence=_region_confidence(provider),
            # Name the source in the method, so a region carries WHERE its
            # numbers came from and not merely how they were combined.
            method=f"diary-entry-word-union:{(provider or 'unknown').strip().casefold()}",
        )
    except ValueError:
        # Malformed OCR geometry must not cost us the entry. The node is the
        # transcript; the region is a convenience. Losing the node would lose
        # the text, and guessing a rect would be the defect this program
        # removes — so: node yes, region no, recorded in `bbox_basis`.
        logger.warning("diary entry OCR union rejected for span %s", span)
        return None


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

    geometry_content, boxes, geometry_provider = _geometry_boxes(db, page)
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
        region = _region_union(boxes, spans[index - 1], geometry_provider)
        body = _body_without_date_heading(entry.text, entry.date_text)
        node = Document(
            parent_id=page.id,
            doc_type=DocType.file,
            file_type=None,
            node_kind="entry",
            name=iso or entry.date_text.strip() or f"Entry {index}",
            path=None,
            sequence=index,
            status=Status.completed,
            page_content=body,
            region_in_parent=region,
            prototype_key=prototype_key,
            attributes={"date": iso} if iso else {},
            metadata={
                _DIARY_TOOL_KEY: True,
                "source_document_id": page.id,
                "source_document_name": page.name,
                "date_text": entry.date_text,
                "date_parsed": iso is not None,
                # "no_page_dimensions" is gone: a normalized region never
                # needed the page's pixel size, so that outcome cannot occur.
                "bbox_basis": "ocr_geometry" if region else "none",
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
    # Resolve containers to the pages inside them (2026-08-22). Handed an
    # OPENING, this tool used to treat the spread as a page: it transcribed two
    # pages as one blob and anchored every entry to the spread's frame. A
    # container is not a unit of work.
    pages = resolve_workflow_targets(db, raw_documents)
    created: list[Document] = []
    lines: list[str] = []
    errors: list[str] = []
    if not pages and raw_documents:
        errors.append(f"{len(raw_documents)} selected document(s) resolved to no pages")
    for page in pages:
        try:
            entries = await split_page_into_entries(
                db, page, llm_config, prototype_key=prototype_key
            )
        except ValueError as exc:
            errors.append(str(exc))
            continue
        created.extend(entries)
        for node in entries:
            marker = "▣" if node.region_in_parent else "·"
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
