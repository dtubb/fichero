"""Annotation cropping helpers for workflow input (#914 extension).

When a user highlights 10% of a 100MB image, the AI shouldn't see the
whole image — just the highlighted region. These helpers crop a
document's content to the bounds of an Annotation row so workflow
tools (Transcribe, Catalogue, anything vision-driven) can iterate
over user-marked regions instead of full pages.

Three crop modes:

- ``crop_image`` — PIL crop of an image file to a bbox
- ``crop_pdf_page`` — PyMuPDF pixmap of a PDF page bounded by bbox
- ``crop_text`` — char_start/char_end substring of a document's
  page_content

Each helper takes an Annotation + the source Document and returns
the cropped bytes/text plus enough metadata for the calling tool
to know what it's processing.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from fichero_server.models.knowledge import Annotation
    from fichero_server.models import Document

from fichero_server.core.utf16_offsets import utf16_range_to_codepoint_range

logger = logging.getLogger(__name__)


def crop_text(
    document: "Document",
    annotation: "Annotation",
) -> str | None:
    """Return the substring of document.page_content for this annotation.

    Converts UTF-16 offsets (sent by the Swift frontend) to Python
    code-point offsets before slicing (#3262).

    Returns the annotation.text itself if char offsets aren't set —
    a free-floating note has its own body. Returns None when there's
    nothing to extract.
    """
    if annotation.char_start is not None and annotation.char_end is not None:
        body = document.page_content or ""
        if body:
            # Convert UTF-16 offsets (from Swift frontend) to Python
            # code-point offsets before slicing (#3262).
            cp_start, cp_end = utf16_range_to_codepoint_range(
                body, annotation.char_start, annotation.char_end
            )
            return body[cp_start:cp_end]
    return annotation.text or None


def crop_image(
    image_path: str | Path,
    annotation: "Annotation",
) -> bytes | None:
    """Crop a 2D image to the annotation's bbox; return PNG bytes.

    Returns None when bbox is missing or PIL can't open the file.
    Useful for huge photographic plates / maps / scans where the
    annotated region is much smaller than the full image.
    """
    if not annotation.bbox or len(annotation.bbox) != 4:
        return None
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        logger.warning("Pillow not available; image crop disabled")
        return None
    path = Path(image_path)
    if not path.exists():
        return None
    try:
        with Image.open(path) as img:
            x, y, w, h = annotation.bbox
            iw, ih = img.size
            # Denormalize from [0,1] fractions to pixel coordinates.
            px = int(x * iw)
            py = int(y * ih)
            pw = int(w * iw)
            ph = int(h * ih)
            crop = img.crop((px, py, px + pw, py + ph))
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            return buf.getvalue()
    except Exception as exc:
        logger.warning("crop_image failed for %s: %s", path, exc)
        return None


def crop_pdf_page(
    pdf_path: str | Path,
    annotation: "Annotation",
    dpi: int = 144,
) -> bytes | None:
    """Render a PDF page region (bounded by annotation.bbox) as PNG bytes.

    Looks up the page number from ``annotation.page_label`` (parsed
    out of strings like "Page 14" → 13 zero-indexed). When no bbox
    is set, renders the whole page. Returns None on failure.

    Default DPI 144 — good balance between vision-OCR quality and
    request payload size. Caller can raise for archival-quality
    scans or drop for thumbnails.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover
        logger.warning("PyMuPDF not available; PDF crop disabled")
        return None
    path = Path(pdf_path)
    if not path.exists():
        return None

    page_idx = annotation.page_index if annotation.page_index is not None else _parse_page_index(annotation.page_label)
    try:
        doc = fitz.open(str(path))
        if page_idx is None or page_idx < 0 or page_idx >= doc.page_count:
            page = doc[0]
        else:
            page = doc[page_idx]
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        if annotation.bbox and len(annotation.bbox) == 4:
            x, y, w, h = annotation.bbox
            rect = page.rect
            # Denormalize from [0,1] fractions to PDF point coordinates.
            px = x * rect.width
            py = y * rect.height
            pw = w * rect.width
            ph = h * rect.height
            clip = fitz.Rect(px, py, px + pw, py + ph)
            pixmap = page.get_pixmap(matrix=matrix, clip=clip)
        else:
            pixmap = page.get_pixmap(matrix=matrix)
        png_bytes = pixmap.tobytes("png")
        doc.close()
        return png_bytes
    except Exception as exc:
        logger.warning("crop_pdf_page failed for %s: %s", path, exc)
        return None


def _parse_page_index(page_label: str | None) -> int | None:
    """Extract a 0-indexed page number from 'Page 14' / '14' / 'p.14' / etc.

    Returns None when no number is recoverable.
    """
    if not page_label:
        return None
    import re

    match = re.search(r"\d+", str(page_label))
    if not match:
        return None
    n = int(match.group(0))
    return max(0, n - 1)


def annotation_crops_for_document(
    document: "Document",
    annotations: list["Annotation"],
) -> list[dict]:
    """Apply the right crop helper for each annotation; return a list
    of ``{annotation_id, crop_kind, content}`` entries.

    Use case: catalogue / transcribe iterates annotations and feeds
    only the cropped content to the LLM/vision tool. Skip kinds that
    don't carry useful crop data (rating-only annotations).
    """
    results: list[dict] = []
    for ann in annotations:
        # Pure-rating annotations don't crop — they're metadata.
        if ann.kind.value == "rating":
            continue

        # Image / PDF path: prefer bbox crop when present.
        if ann.bbox and document.path:
            suffix = Path(document.path).suffix.lower()
            if suffix == ".pdf":
                png = crop_pdf_page(document.path, ann)
                if png:
                    results.append({
                        "annotation_id": ann.id,
                        "crop_kind": "pdf_region_png",
                        "content": png,
                    })
                    continue
            elif suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic"}:
                png = crop_image(document.path, ann)
                if png:
                    results.append({
                        "annotation_id": ann.id,
                        "crop_kind": "image_region_png",
                        "content": png,
                    })
                    continue

        # Text path: char range OR annotation text fallback.
        text = crop_text(document, ann)
        if text:
            results.append({
                "annotation_id": ann.id,
                "crop_kind": "text",
                "content": text,
            })

    return results
