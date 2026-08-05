"""Provider-neutral OCR/transcription geometry contracts.

This module normalizes geometry returned by deterministic OCR engines
(Apple Vision, Google Vision, AWS Textract, Tesseract-style TSV) and by
prompted VLM JSON into one typed shape. It does not call providers.
"""

from __future__ import annotations

import csv
import json
from enum import StrEnum
from io import StringIO
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


OCRProviderKind = Literal[
    "apple_vision",
    "vlm_json",
    "google_vision",
    "google_document_ai",
    "aws_textract",
    "azure_document_intelligence",
    "tesseract_tsv",
    "paddleocr",
    "easyocr",
    "doctr",
    "pymupdf",
]


class OCRGeometryLevel(StrEnum):
    PAGE = "page"
    BLOCK = "block"
    LINE = "line"
    WORD = "word"
    REGION = "region"


class OCRCloudProviderBlocked(RuntimeError):
    """Raised when cloud OCR would violate local-only/no-cloud policy."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"OCR provider '{provider}' would upload content to a cloud service; "
            "disable local-only mode or choose a local/on-device OCR provider."
        )
        self.provider = provider


class OCRGeometryBox(BaseModel):
    """One normalized OCR/transcription geometry record."""

    model_config = ConfigDict(extra="forbid")

    text: str
    bbox: list[float] = Field(
        ...,
        description=(
            "Normalized [x, y, width, height] values in the range 0..1, "
            "top-left origin (y grows downward, matching image/W3C space)."
        ),
    )
    level: OCRGeometryLevel = OCRGeometryLevel.WORD
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    # Character span of this box's text inside the OWNING artifact's content
    # string (#4309). Keeping the box↔text link explicit is what lets a later
    # content edit re-map its segment instead of orphaning the geometry.
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    page_index: int | None = Field(default=None, ge=0)
    provider: str | None = None
    model: str | None = None
    coordinate_space: str = "normalized"
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("bbox")
    @classmethod
    def _validate_bbox(cls, value: list[float]) -> list[float]:
        if len(value) != 4:
            raise ValueError("bbox must have four values: [x, y, width, height]")
        coerced = [float(item) for item in value]
        x, y, width, height = coerced
        if width < 0 or height < 0:
            raise ValueError("bbox width and height must be non-negative")
        if any(item < 0.0 or item > 1.0 for item in coerced):
            raise ValueError("bbox values must be normalized to the range 0..1")
        if x + width > 1.000001 or y + height > 1.000001:
            raise ValueError("bbox extends outside the normalized page/image bounds")
        return coerced

    @field_validator("text", mode="before")
    @classmethod
    def _coerce_text(cls, value: object) -> str:
        return str(value or "")


class OCRGeometryResult(BaseModel):
    """Normalized OCR/transcription text plus geometry records."""

    model_config = ConfigDict(extra="forbid")

    text: str = ""
    provider: str
    model: str | None = None
    boxes: list[OCRGeometryBox] = Field(default_factory=list)
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text", mode="before")
    @classmethod
    def _coerce_text(cls, value: object) -> str:
        return str(value or "")


_CLOUD_OCR_PROVIDERS = {
    "google",
    "google_vision",
    "google_document_ai",
    "gcp",
    "aws",
    "amazon",
    "aws_textract",
    "textract",
    "azure",
    "azure_document_intelligence",
    "azure_form_recognizer",
}


def enforce_ocr_provider_policy(provider: str, *, local_only: bool) -> None:
    """Reject cloud OCR providers when local-only/no-cloud mode is active."""

    normalized = _provider_key(provider)
    if local_only and normalized in _CLOUD_OCR_PROVIDERS:
        raise OCRCloudProviderBlocked(provider)


def ocr_bbox_coverage(result: OCRGeometryResult) -> float:
    """Return the fraction of non-empty result lines/words that have geometry."""

    tokens = [token for token in result.text.split() if token]
    if not tokens:
        return 0.0
    boxed_tokens = sum(len(box.text.split()) for box in result.boxes if box.text)
    return min(1.0, boxed_tokens / len(tokens))


#: Key under which every producer records WHY a result has the boxes it has.
#: An empty box list is three different facts wearing one costume, and only
#: one of them means the page has no text on it (#4309/#4418).
GEOMETRY_STATUS_KEY = "geometry_status"

#: Key carrying the human-readable reason behind a non-``captured`` status.
GEOMETRY_REASON_KEY = "geometry_reason"


class OCRGeometryStatus(StrEnum):
    """Why a page's geometry looks the way it does.

    Distinguishing these is the same discipline as ``produced_nothing`` vs
    ``not_run`` elsewhere in the engine: a workflow that cannot produce
    geometry must SAY it could not, rather than omitting the field and letting
    a reader conclude the page is blank. For archival material the difference
    is material — "nothing was recognised here" is a claim about the page,
    "this engine cannot localise text" is a claim about the engine.
    """

    #: Boxes exist.
    CAPTURED = "captured"
    #: The engine ran, can localise, and localised nothing on this page.
    PRODUCED_NOTHING = "produced_nothing"
    #: The engine ran but cannot localise text at all (most LLM providers).
    NOT_SUPPORTED = "not_supported"
    #: Geometry capture was never attempted on this pass.
    NOT_RUN = "not_run"
    #: Geometry WAS requested and the engine answered with something that
    #: could not be read as geometry — unparseable JSON, no boxes, coordinates
    #: outside the page, or box text that does not appear in the transcription
    #: (#4553 follow-up). Distinct from NOT_SUPPORTED: the model was asked, it
    #: replied, and the reply was rejected. Mapping this onto any of the three
    #: above would claim something untrue about the engine or the page.
    MALFORMED = "malformed"


def geometry_unavailable(
    *,
    status: OCRGeometryStatus,
    provider: str,
    reason: str,
    model: str | None = None,
    text: str = "",
    source: str | None = None,
) -> OCRGeometryResult:
    """Record that a pass produced no geometry, and why.

    Returns a real, persistable record with zero boxes — NOT ``None``. The
    point is that "this provider does not localise text" survives to the
    reader, so the overlay can say so instead of rendering an empty page that
    implies nothing was recognised.
    """
    if status is OCRGeometryStatus.CAPTURED:
        raise ValueError(
            "geometry_unavailable is for the no-geometry cases; a captured "
            "result must carry its boxes"
        )
    return OCRGeometryResult(
        text=text,
        provider=provider,
        model=model,
        boxes=[],
        source=source,
        metadata={GEOMETRY_STATUS_KEY: str(status), GEOMETRY_REASON_KEY: reason},
    )


def geometry_status(result: OCRGeometryResult | None) -> OCRGeometryStatus:
    """Read a result's status, defaulting honestly.

    ``None`` means nothing was recorded, which is ``NOT_RUN`` — never
    ``PRODUCED_NOTHING``. Conflating the two is exactly the failure this enum
    exists to prevent.
    """
    if result is None:
        return OCRGeometryStatus.NOT_RUN
    if result.boxes:
        return OCRGeometryStatus.CAPTURED
    recorded = result.metadata.get(GEOMETRY_STATUS_KEY)
    if recorded:
        return OCRGeometryStatus(str(recorded))
    # A boxless result with no recorded status predates this contract. It is
    # not evidence the page is blank, so say the weaker true thing.
    return OCRGeometryStatus.NOT_RUN


def from_apple_vision_result(
    result: Any,
    *,
    provider: str = "apple_vision",
    model: str = "VNRecognizeTextRequest",
    source: str | None = None,
) -> OCRGeometryResult:
    """Map #1644 Apple Vision geometry dataclasses into the shared contract."""

    boxes: list[OCRGeometryBox] = []
    for level, values in (
        (OCRGeometryLevel.LINE, getattr(result, "line_boxes", []) or []),
        (OCRGeometryLevel.WORD, getattr(result, "word_boxes", []) or []),
    ):
        for item in values:
            boxes.append(
                OCRGeometryBox(
                    text=getattr(item, "text", ""),
                    bbox=list(getattr(item, "bbox")),
                    level=level,
                    confidence=getattr(item, "confidence", None),
                    page_index=getattr(item, "page_index", None),
                    char_start=getattr(item, "char_start", None),
                    char_end=getattr(item, "char_end", None),
                    provider=provider,
                    model=model,
                    source=source,
                )
            )
    return OCRGeometryResult(
        text=getattr(result, "text", ""),
        provider=provider,
        model=model,
        boxes=boxes,
        source=source,
    )


#: Marker recorded in ``OCRGeometryResult.metadata`` so "this page has no text
#: layer" is distinguishable from "this page was never processed" and from
#: "recognition ran and found nothing" (#4418). All three would otherwise look
#: identical — an empty box list — and only one of them means the overlay
#: should say geometry is unavailable rather than showing an empty page.
PDF_TEXT_LAYER_FLAG = "pdf_text_layer_present"


def from_pymupdf_page(
    page: Any,
    *,
    page_index: int | None = None,
    model: str | None = None,
    source: str | None = "pdf_text_layer",
) -> OCRGeometryResult:
    """Read a PDF page's existing text layer as geometry — no model involved.

    A PDF with a text layer already carries the answer: every word and its
    rectangle, in page space, produced when the file was made. ``get_text()``
    with no argument flattens that to a string and the rectangles are dropped
    at the moment of extraction (#4418). ``get_text("words")`` returns the
    identical text WITH its geometry, at no extra cost.

    So for born-digital PDFs — and every scan someone has already OCR'd
    elsewhere — regions need no model, no workflow and no new pipeline.

    Coordinates are normalised to the 0..1, top-left-origin space every other
    producer in this module targets. That is deliberate and load-bearing: the
    image-preparation workflows produce SEVERAL renditions of one page
    (original, enhanced, deskewed, split), so geometry tied to any one
    rendition's pixels is wrong against all the others. Page-relative
    fractions survive every rendition and every zoom level.

    ``text`` is the word stream joined in reading order, and each box's
    ``char_start``/``char_end`` index into exactly that string — the model
    documents spans as offsets into "the OWNING artifact's content", so
    building both here keeps them consistent by construction rather than by
    hoping a separately-extracted string happens to match.

    A page with no text layer returns a result with NO boxes and
    ``metadata[PDF_TEXT_LAYER_FLAG] = False``. That is the honest answer for a
    scan: geometry is unavailable, which is not the same as recognising
    nothing.
    """
    rect = getattr(page, "rect", None)
    page_width = float(getattr(rect, "width", 0.0) or 0.0)
    page_height = float(getattr(rect, "height", 0.0) or 0.0)
    if page_width <= 0 or page_height <= 0:
        raise ValueError(
            "from_pymupdf_page: page has no usable dimensions "
            f"({page_width}x{page_height}) — cannot normalise geometry"
        )

    words = list(page.get_text("words") or [])

    boxes: list[OCRGeometryBox] = []
    parts: list[str] = []
    cursor = 0
    for word in words:
        # PyMuPDF word tuples: (x0, y0, x1, y1, text, block, line, word_no).
        # Already top-left origin, already page space.
        if len(word) < 5:
            continue
        x0, y0, x1, y1 = (float(word[0]), float(word[1]), float(word[2]), float(word[3]))
        text = str(word[4] or "")
        if not text:
            continue

        if parts:
            parts.append(" ")
            cursor += 1
        char_start = cursor
        parts.append(text)
        cursor += len(text)

        # Clamp before normalising: a rect may sit a hair outside the page box
        # (rotation, negative-origin MediaBox), and the model rejects anything
        # outside 0..1 — correctly, but a fraction of a point should not lose
        # the whole word's geometry.
        left = min(max(x0, 0.0), page_width)
        top = min(max(y0, 0.0), page_height)
        right = min(max(x1, 0.0), page_width)
        bottom = min(max(y1, 0.0), page_height)
        boxes.append(
            OCRGeometryBox(
                text=text,
                bbox=[
                    left / page_width,
                    top / page_height,
                    max(right - left, 0.0) / page_width,
                    max(bottom - top, 0.0) / page_height,
                ],
                level=OCRGeometryLevel.WORD,
                # No confidence: the text layer is not a recognition result.
                # Inventing 1.0 would claim a certainty this is not measuring.
                confidence=None,
                char_start=char_start,
                char_end=cursor,
                page_index=page_index,
                provider="pymupdf",
                model=model,
                source=source,
            )
        )

    return OCRGeometryResult(
        text="".join(parts),
        provider="pymupdf",
        model=model,
        boxes=boxes,
        source=source,
        metadata={
            PDF_TEXT_LAYER_FLAG: bool(boxes),
            GEOMETRY_STATUS_KEY: str(
                OCRGeometryStatus.CAPTURED
                if boxes
                else OCRGeometryStatus.PRODUCED_NOTHING
            ),
            GEOMETRY_REASON_KEY: (
                "pdf text layer read"
                if boxes
                else "this PDF page has no text layer to read"
            ),
            "page_width": page_width,
            "page_height": page_height,
        },
    )


def parse_vlm_geometry(
    payload: str | dict[str, Any],
    *,
    provider: str = "vlm_json",
    model: str | None = None,
    page_width: float | None = None,
    page_height: float | None = None,
) -> OCRGeometryResult:
    """Parse prompted VLM JSON boxes, including common Qwen-style shapes."""

    data = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(data, dict):
        raise ValueError("VLM OCR geometry payload must be a JSON object")
    width = _first_number(data, "image_width", "width", "page_width") or page_width
    height = _first_number(data, "image_height", "height", "page_height") or page_height
    boxes = [
        _box_from_vlm_item(item, provider=provider, model=model, page_width=width, page_height=height)
        for item in _box_items(data)
    ]
    return OCRGeometryResult(
        text=str(data.get("text") or _join_box_text(boxes)),
        provider=provider,
        model=model,
        boxes=boxes,
        metadata={"format": "vlm_json"},
    )


def parse_google_vision_response(
    response: dict[str, Any],
    *,
    provider: str = "google_vision",
    model: str | None = "text_detection",
    page_width: float | None = None,
    page_height: float | None = None,
) -> OCRGeometryResult:
    """Parse a Google Vision textAnnotations-style fixture."""

    annotations = response.get("textAnnotations") or response.get("text_annotations") or []
    if not isinstance(annotations, list):
        raise ValueError("Google Vision response textAnnotations must be a list")
    full_text = ""
    boxes: list[OCRGeometryBox] = []
    for index, annotation in enumerate(annotations):
        if not isinstance(annotation, dict):
            continue
        text = str(annotation.get("description") or "")
        if index == 0:
            full_text = text
            continue
        bbox = _bbox_from_google_poly(
            annotation.get("boundingPoly") or annotation.get("bounding_poly"),
            page_width=page_width,
            page_height=page_height,
        )
        boxes.append(
            OCRGeometryBox(
                text=text,
                bbox=bbox,
                level=OCRGeometryLevel.WORD,
                provider=provider,
                model=model,
            )
        )
    return OCRGeometryResult(
        text=full_text or _join_box_text(boxes),
        provider=provider,
        model=model,
        boxes=boxes,
        metadata={"format": "google_text_annotations"},
    )


def parse_aws_textract_response(
    response: dict[str, Any],
    *,
    provider: str = "aws_textract",
    model: str | None = "detect_document_text",
) -> OCRGeometryResult:
    """Parse an AWS Textract Blocks fixture."""

    blocks = response.get("Blocks") or response.get("blocks") or []
    if not isinstance(blocks, list):
        raise ValueError("AWS Textract response Blocks must be a list")
    boxes: list[OCRGeometryBox] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = str(block.get("BlockType") or block.get("block_type") or "").upper()
        if kind not in {"LINE", "WORD"}:
            continue
        geometry = block.get("Geometry") or block.get("geometry") or {}
        bbox_raw = geometry.get("BoundingBox") or geometry.get("bounding_box")
        if not isinstance(bbox_raw, dict):
            raise ValueError("AWS Textract text block is missing Geometry.BoundingBox")
        boxes.append(
            OCRGeometryBox(
                text=str(block.get("Text") or block.get("text") or ""),
                bbox=[
                    float(bbox_raw.get("Left", bbox_raw.get("left", 0.0))),
                    float(bbox_raw.get("Top", bbox_raw.get("top", 0.0))),
                    float(bbox_raw.get("Width", bbox_raw.get("width", 0.0))),
                    float(bbox_raw.get("Height", bbox_raw.get("height", 0.0))),
                ],
                level=OCRGeometryLevel.LINE if kind == "LINE" else OCRGeometryLevel.WORD,
                confidence=_confidence_0_1(block.get("Confidence") or block.get("confidence")),
                page_index=_zero_based_page(block.get("Page") or block.get("page")),
                provider=provider,
                model=model,
            )
        )
    return OCRGeometryResult(
        text=_join_line_or_word_text(boxes),
        provider=provider,
        model=model,
        boxes=boxes,
        metadata={"format": "aws_textract_blocks"},
    )


def parse_tesseract_tsv(
    tsv_text: str,
    *,
    page_width: float,
    page_height: float,
    provider: str = "tesseract_tsv",
    model: str | None = None,
) -> OCRGeometryResult:
    """Parse Tesseract TSV output into normalized word boxes."""

    rows = csv.DictReader(StringIO(tsv_text), delimiter="\t")
    boxes: list[OCRGeometryBox] = []
    for row in rows:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        boxes.append(
            OCRGeometryBox(
                text=text,
                bbox=_normalize_xywh(
                    [
                        _float(row.get("left")),
                        _float(row.get("top")),
                        _float(row.get("width")),
                        _float(row.get("height")),
                    ],
                    page_width=page_width,
                    page_height=page_height,
                ),
                level=OCRGeometryLevel.WORD,
                confidence=_confidence_0_1(row.get("conf")),
                page_index=_zero_based_page(row.get("page_num")),
                provider=provider,
                model=model,
                coordinate_space="tesseract_tsv_pixels",
            )
        )
    return OCRGeometryResult(
        text=_join_box_text(boxes),
        provider=provider,
        model=model,
        boxes=boxes,
        metadata={"format": "tesseract_tsv"},
    )


# =============================================================================
# Addressing — resolving a piece of text to the region it came from
# =============================================================================
#
# This is the seam #4418 and #4405 both name, and it is deliberately ONE
# implementation. A region, a text span and a claim all address the same thing
# through ``char_start``/``char_end`` into the owning artifact's content; a
# second addressing scheme would mean two answers to "where did this line come
# from", which for archival material is worse than none.


class SpanRegion(BaseModel):
    """Where a span of transcribed text sits on the page."""

    model_config = ConfigDict(extra="forbid")

    char_start: int
    char_end: int
    #: Union of every contributing box, as normalized [x, y, width, height].
    bbox: list[float]
    #: The boxes that produced the union, so a caller can highlight per word
    #: instead of one blunt rectangle when the geometry supports it.
    boxes: list[OCRGeometryBox]
    level: OCRGeometryLevel


def attach_char_spans(result: OCRGeometryResult) -> OCRGeometryResult:
    """Anchor boxes that arrived without spans into the result's own text.

    Apple Vision and the PDF text layer build text and spans together, so they
    are consistent by construction. A prompted VLM returns boxes and a
    transcription as separate things, so the link has to be established — and
    without it those boxes are un-addressable: they can be drawn on the page
    but no line of the transcript can be resolved to them.

    Matching walks forward through the text, so a word repeated on the page
    anchors to its own occurrence rather than always to the first. A box whose
    text cannot be found is left unanchored rather than pointed somewhere
    plausible — a wrong region is a wrong claim about the page.
    """
    text = result.text or ""
    if not text:
        return result
    cursor = 0
    updated: list[OCRGeometryBox] = []
    for box in result.boxes:
        if box.char_start is not None and box.char_end is not None:
            updated.append(box)
            continue
        needle = box.text
        if not needle:
            updated.append(box)
            continue
        found = text.find(needle, cursor)
        if found < 0:
            # Fall back to a search from the start before giving up: box order
            # need not match reading order.
            found = text.find(needle)
        if found < 0:
            updated.append(box)
            continue
        end = found + len(needle)
        cursor = end
        updated.append(box.model_copy(update={"char_start": found, "char_end": end}))
    return result.model_copy(update={"boxes": updated})


def boxes_for_span(
    result: OCRGeometryResult,
    char_start: int,
    char_end: int,
    *,
    level: OCRGeometryLevel | None = None,
) -> list[OCRGeometryBox]:
    """Return the boxes whose text overlaps ``[char_start, char_end)``.

    Boxes with no recorded span cannot be placed against the text and are
    excluded rather than guessed at.
    """
    if char_end <= char_start:
        return []
    matches = [
        box
        for box in result.boxes
        if box.char_start is not None
        and box.char_end is not None
        and box.char_start < char_end
        and box.char_end > char_start
        and (level is None or box.level == level)
    ]
    return sorted(matches, key=lambda box: (box.char_start or 0, box.char_end or 0))


def union_bbox(boxes: list[OCRGeometryBox]) -> list[float] | None:
    """Smallest normalized rect containing every box, or ``None`` if empty."""
    if not boxes:
        return None
    left = min(box.bbox[0] for box in boxes)
    top = min(box.bbox[1] for box in boxes)
    right = max(box.bbox[0] + box.bbox[2] for box in boxes)
    bottom = max(box.bbox[1] + box.bbox[3] for box in boxes)
    return [left, top, max(right - left, 0.0), max(bottom - top, 0.0)]


def region_for_span(
    result: OCRGeometryResult,
    char_start: int,
    char_end: int,
    *,
    level: OCRGeometryLevel | None = None,
) -> SpanRegion | None:
    """Resolve a span of the artifact's text to its region on the page.

    Prefers the FINEST granularity available: word boxes give a tight region,
    line boxes a coarse one. Apple Vision and the PDF text layer disagree on
    which levels they produce, so a caller that demanded one level would work
    against one source and silently fail against the other.

    Returns ``None`` when the span cannot be placed — an unplaceable span is
    not a span at the origin.
    """
    if level is not None:
        boxes = boxes_for_span(result, char_start, char_end, level=level)
        resolved_level = level
    else:
        boxes = boxes_for_span(result, char_start, char_end, level=OCRGeometryLevel.WORD)
        resolved_level = OCRGeometryLevel.WORD
        if not boxes:
            for fallback in (
                OCRGeometryLevel.LINE,
                OCRGeometryLevel.BLOCK,
                OCRGeometryLevel.REGION,
                OCRGeometryLevel.PAGE,
            ):
                boxes = boxes_for_span(result, char_start, char_end, level=fallback)
                if boxes:
                    resolved_level = fallback
                    break
    bbox = union_bbox(boxes)
    if bbox is None:
        return None
    return SpanRegion(
        char_start=char_start,
        char_end=char_end,
        bbox=bbox,
        boxes=boxes,
        level=resolved_level,
    )


def line_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of each line of ``text``, newline excluded."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for line in text.split("\n"):
        spans.append((cursor, cursor + len(line)))
        cursor += len(line) + 1
    return spans


def region_for_line(
    result: OCRGeometryResult,
    line_index: int,
    *,
    text: str | None = None,
) -> SpanRegion | None:
    """Resolve line ``line_index`` of the transcription to its page region.

    ``text`` defaults to the result's own text; pass the artifact's content
    when the artifact is the authority (post-edit, the two can differ, and the
    artifact is what the historian is reading).
    """
    spans = line_spans(text if text is not None else result.text)
    if line_index < 0 or line_index >= len(spans):
        return None
    start, end = spans[line_index]
    if end <= start:
        return None
    return region_for_span(result, start, end)


def span_at_point(
    result: OCRGeometryResult,
    x: float,
    y: float,
    *,
    level: OCRGeometryLevel | None = None,
) -> OCRGeometryBox | None:
    """The reverse direction: which box covers a normalized page point.

    Bidirectional by construction — select a region and get its text span back,
    select a span and get its region. Same records, read two ways, so the two
    directions cannot drift apart.
    """
    candidates = [
        box
        for box in result.boxes
        if (level is None or box.level == level)
        and box.bbox[0] <= x <= box.bbox[0] + box.bbox[2]
        and box.bbox[1] <= y <= box.bbox[1] + box.bbox[3]
    ]
    if not candidates:
        return None
    # Smallest containing box wins: a word inside a line is the more precise
    # answer, and both legitimately contain the point.
    return min(candidates, key=lambda box: box.bbox[2] * box.bbox[3])


def _provider_key(provider: str) -> str:
    return str(provider or "").strip().lower().replace("-", "_")


def _box_items(data: dict[str, Any]) -> list[Any]:
    for key in ("boxes", "bboxes", "regions", "words", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    raise ValueError("VLM OCR geometry payload must include a boxes list")


def _box_from_vlm_item(
    item: Any,
    *,
    provider: str,
    model: str | None,
    page_width: float | None,
    page_height: float | None,
) -> OCRGeometryBox:
    if not isinstance(item, dict):
        raise ValueError("VLM OCR geometry boxes must be objects")
    raw_bbox: Any
    coordinate_space = "normalized"
    if "bbox" in item:
        raw_bbox = item["bbox"]
    elif "bbox_2d" in item:
        raw_bbox = _xyxy_to_xywh(item["bbox_2d"])
        coordinate_space = "pixel_xyxy"
    elif {"x", "y", "width", "height"}.issubset(item):
        raw_bbox = [item["x"], item["y"], item["width"], item["height"]]
    else:
        raise ValueError("VLM OCR geometry box is missing bbox coordinates")

    width = _first_number(item, "image_width", "page_width") or page_width
    height = _first_number(item, "image_height", "page_height") or page_height
    bbox = _coerce_normalized_bbox(raw_bbox, page_width=width, page_height=height)
    return OCRGeometryBox(
        text=str(item.get("text") or item.get("label") or ""),
        bbox=bbox,
        level=OCRGeometryLevel(str(item.get("level") or "word").lower()),
        confidence=_confidence_0_1(item.get("confidence") or item.get("score")),
        page_index=_zero_based_page(item.get("page") or item.get("page_index"), already_zero_based="page_index" in item),
        provider=provider,
        model=model,
        coordinate_space=coordinate_space if width and height else "normalized",
    )


def _bbox_from_google_poly(
    poly: Any,
    *,
    page_width: float | None,
    page_height: float | None,
) -> list[float]:
    if not isinstance(poly, dict):
        raise ValueError("Google Vision annotation is missing boundingPoly")
    normalized = poly.get("normalizedVertices") or poly.get("normalized_vertices")
    if isinstance(normalized, list) and normalized:
        xs = [_float(vertex.get("x")) for vertex in normalized if isinstance(vertex, dict)]
        ys = [_float(vertex.get("y")) for vertex in normalized if isinstance(vertex, dict)]
        return _xyxy_to_xywh([min(xs), min(ys), max(xs), max(ys)])

    vertices = poly.get("vertices") or []
    if not (page_width and page_height):
        raise ValueError("Google pixel vertices require page_width and page_height")
    xs = [_float(vertex.get("x")) for vertex in vertices if isinstance(vertex, dict)]
    ys = [_float(vertex.get("y")) for vertex in vertices if isinstance(vertex, dict)]
    return _normalize_xywh(
        _xyxy_to_xywh([min(xs), min(ys), max(xs), max(ys)]),
        page_width=page_width,
        page_height=page_height,
    )


def _coerce_normalized_bbox(
    bbox: Any,
    *,
    page_width: float | None,
    page_height: float | None,
) -> list[float]:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValueError("bbox must be a four-item list")
    values = [float(value) for value in bbox]
    if all(0.0 <= value <= 1.0 for value in values):
        return values
    if page_width and page_height:
        return _normalize_xywh(values, page_width=page_width, page_height=page_height)
    raise ValueError("pixel bbox values require page_width and page_height")


def _normalize_xywh(
    bbox: list[float],
    *,
    page_width: float,
    page_height: float,
) -> list[float]:
    if page_width <= 0 or page_height <= 0:
        raise ValueError("page_width and page_height must be positive")
    return [
        bbox[0] / page_width,
        bbox[1] / page_height,
        bbox[2] / page_width,
        bbox[3] / page_height,
    ]


def _xyxy_to_xywh(bbox: Any) -> list[float]:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValueError("bbox_2d must be [x1, y1, x2, y2]")
    x1, y1, x2, y2 = [float(value) for value in bbox]
    return [x1, y1, x2 - x1, y2 - y1]


def _confidence_0_1(value: Any) -> float | None:
    if value in (None, ""):
        return None
    confidence = float(value)
    if confidence > 1.0:
        confidence = confidence / 100.0
    return max(0.0, min(1.0, confidence))


def _zero_based_page(value: Any, *, already_zero_based: bool = False) -> int | None:
    if value in (None, ""):
        return None
    page = int(value)
    return page if already_zero_based else max(0, page - 1)


def _first_number(data: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return float(value)
    return None


def _float(value: Any) -> float:
    return float(value or 0.0)


def _join_box_text(boxes: list[OCRGeometryBox]) -> str:
    return " ".join(box.text for box in boxes if box.text).strip()


def _join_line_or_word_text(boxes: list[OCRGeometryBox]) -> str:
    lines = [box.text for box in boxes if box.level == OCRGeometryLevel.LINE and box.text]
    return "\n".join(lines) if lines else _join_box_text(boxes)
