"""
Convert a Kreuzberg ``ExtractionResult`` into a list of structured artifact
payloads.

Kreuzberg extracts more than just primary text: tables, slide-deck text,
image OCR/descriptions, audio/video transcripts, etc.  Historically Fichero
discarded everything except ``result.content``.  This module preserves the
extras as dicts ready to be persisted as ``Artifact`` rows.

Each payload has the shape::

    {
        "artifact_type": str,   # e.g. "kreuzberg_table"
        "content": str | None,  # human-readable text (optional)
        "data": dict | None,    # structured payload (optional)
    }

The caller (``ingest._save_kreuzberg_artifacts``) maps these onto
``fichero_server.models.Artifact`` rows attached to a Document.

Kreuzberg API attributes vary across versions, so every access is guarded
with ``getattr`` / ``hasattr`` and defensively normalised.  This keeps the
helper additive: if Kreuzberg adds new fields we silently skip them; if a
field disappears we don't crash.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# Artifact-type constants — kept here so tests and callers share a single
# source of truth and we don't typo a string somewhere.
KREUZBERG_TABLE = "kreuzberg_table"
KREUZBERG_TRANSCRIPT = "kreuzberg_transcript"
KREUZBERG_SLIDE_TEXT = "kreuzberg_slide_text"
KREUZBERG_IMAGE_DESCRIPTION = "kreuzberg_image_description"
KREUZBERG_KEYWORDS = "kreuzberg_keywords"
KREUZBERG_ANNOTATIONS = "kreuzberg_annotations"


def extract_artifact_payloads(result: Any) -> list[dict[str, Any]]:
    """Return a list of artifact payload dicts for a Kreuzberg result.

    Each entry is ``{"artifact_type": str, "content": str | None,
    "data": dict | None}``.  Empty/missing fields are skipped so we never
    create empty artifact rows.
    """
    payloads: list[dict[str, Any]] = []

    if result is None:
        return payloads

    payloads.extend(_tables_to_payloads(getattr(result, "tables", None)))
    payloads.extend(_pages_to_slide_payloads(getattr(result, "pages", None), result))
    payloads.extend(_images_to_description_payloads(getattr(result, "images", None)))
    payloads.extend(_transcript_payloads(result))
    payloads.extend(_keywords_payload(getattr(result, "extracted_keywords", None)))
    payloads.extend(_annotations_payload(getattr(result, "annotations", None)))

    return payloads


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------


def _tables_to_payloads(tables: Iterable[Any] | None) -> list[dict[str, Any]]:
    if not tables:
        return []
    out: list[dict[str, Any]] = []
    for idx, table in enumerate(tables):
        cells = _safe_attr(table, "cells")
        markdown = _safe_attr(table, "markdown")
        page_number = _safe_attr(table, "page_number")
        if not cells and not markdown:
            continue
        out.append(
            {
                "artifact_type": KREUZBERG_TABLE,
                "content": markdown if isinstance(markdown, str) else None,
                "data": {
                    "table_index": idx,
                    "page_number": page_number,
                    "cells": cells,
                    "markdown": markdown,
                },
            }
        )
    return out


def _pages_to_slide_payloads(
    pages: Iterable[Any] | None, result: Any
) -> list[dict[str, Any]]:
    """Capture per-page/per-slide text when the format is slide-like.

    Kreuzberg uses the ``pages`` list for PPTX (one entry per slide) just as
    it does for PDFs.  We only emit slide_text artifacts when the format is
    slide-y — otherwise per-page text is already stored as PDF page Documents
    via ``_create_pdf_page_children``.
    """
    if not pages:
        return []

    metadata = getattr(result, "metadata", None) or {}
    fmt = None
    if isinstance(metadata, dict):
        fmt = metadata.get("format_type") or metadata.get("format")

    # Only treat as slides for presentation formats.
    if fmt not in ("pptx", "presentation"):
        return []

    out: list[dict[str, Any]] = []
    for idx, page in enumerate(pages):
        # PageContent is a TypedDict (plain dict) in kreuzberg.
        if isinstance(page, dict):
            page_number = page.get("page_number", idx + 1)
            content = page.get("content") or ""
        else:
            page_number = _safe_attr(page, "page_number", idx + 1)
            content = _safe_attr(page, "content", "") or ""
        if not content.strip():
            continue
        out.append(
            {
                "artifact_type": KREUZBERG_SLIDE_TEXT,
                "content": content,
                "data": {
                    "slide_number": page_number,
                    "page_index": idx,
                },
            }
        )
    return out


def _images_to_description_payloads(
    images: Iterable[Any] | None,
) -> list[dict[str, Any]]:
    if not images:
        return []
    out: list[dict[str, Any]] = []
    for idx, image in enumerate(images):
        # ExtractedImage is a TypedDict (plain dict).
        if isinstance(image, dict):
            description = image.get("description")
            ocr_result = image.get("ocr_result")
        else:
            description = _safe_attr(image, "description")
            ocr_result = _safe_attr(image, "ocr_result")

        ocr_text = None
        if ocr_result is not None:
            ocr_text = _safe_attr(ocr_result, "content")

        if not description and not ocr_text:
            continue

        content_parts = [p for p in (description, ocr_text) if p]
        out.append(
            {
                "artifact_type": KREUZBERG_IMAGE_DESCRIPTION,
                "content": "\n\n".join(content_parts) if content_parts else None,
                "data": {
                    "image_index": idx,
                    "page_number": (
                        image.get("page_number")
                        if isinstance(image, dict)
                        else _safe_attr(image, "page_number")
                    ),
                    "description": description,
                    "ocr_text": ocr_text,
                },
            }
        )
    return out


def _transcript_payloads(result: Any) -> list[dict[str, Any]]:
    """Capture audio/video transcripts.

    Kreuzberg currently exposes transcripts via ``result.content`` for audio
    formats, with the format flagged in metadata.  We additionally check a
    few attribute names that older/newer versions may use, so we don't lose
    transcripts if the API shifts.
    """
    metadata = getattr(result, "metadata", None) or {}
    fmt = None
    if isinstance(metadata, dict):
        fmt = metadata.get("format_type") or metadata.get("format")

    transcript: str | None = None
    if fmt in ("audio", "video", "transcription"):
        # Primary text IS the transcript for these formats — capture it as
        # an artifact so downstream consumers can find it even after the
        # primary text gets replaced by an edited version.
        content = getattr(result, "content", None)
        if isinstance(content, str) and content.strip():
            transcript = content

    # Also pick up explicit transcript fields if a future Kreuzberg version
    # adds them.
    for attr in ("transcript", "transcription"):
        candidate = getattr(result, attr, None)
        if isinstance(candidate, str) and candidate.strip():
            transcript = candidate

    if not transcript:
        return []

    return [
        {
            "artifact_type": KREUZBERG_TRANSCRIPT,
            "content": transcript,
            "data": {"format_type": fmt} if fmt else None,
        }
    ]


def _keywords_payload(keywords: Iterable[Any] | None) -> list[dict[str, Any]]:
    if not keywords:
        return []
    items: list[dict[str, Any]] = []
    for kw in keywords:
        text = _safe_attr(kw, "text")
        score = _safe_attr(kw, "score")
        if not text:
            continue
        items.append({"text": text, "score": score})
    if not items:
        return []
    return [
        {
            "artifact_type": KREUZBERG_KEYWORDS,
            "content": ", ".join(i["text"] for i in items),
            "data": {"keywords": items},
        }
    ]


def _annotations_payload(annotations: Iterable[Any] | None) -> list[dict[str, Any]]:
    if not annotations:
        return []
    items: list[dict[str, Any]] = []
    for ann in annotations:
        items.append(
            {
                "annotation_type": _safe_attr(ann, "annotation_type"),
                "content": _safe_attr(ann, "content"),
                "page_number": _safe_attr(ann, "page_number"),
            }
        )
    if not items:
        return []
    return [
        {
            "artifact_type": KREUZBERG_ANNOTATIONS,
            "content": None,
            "data": {"annotations": items},
        }
    ]


def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        value = getattr(obj, name, default)
    except Exception:
        return default
    return value
