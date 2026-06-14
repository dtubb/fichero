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
        description="Normalized [x, y, width, height] values in the range 0..1.",
    )
    level: OCRGeometryLevel = OCRGeometryLevel.WORD
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
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
