"""
Vision Tools Base Module

Extends llm_base.py with vision-specific functionality.
All vision tools inherit from here.

Provides:
- VISION_INPUT_PORTS (inherits BASE + adds files)
- VISION_CONFIG_SCHEMA (inherits BASE + adds vision_mode, max_image_dimension)
- Apple Vision OCR (on-device)
- Image encoding for LLM vision
- process_vision() - shared processing for all vision tools
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import base64
import dataclasses
from functools import lru_cache
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from fichero.llm import LLMConfig

from fichero.ocr_geometry import OCRGeometryResult, parse_vlm_geometry
from fichero.workflows.types import PortDef, DataType

# Pre-import macOS Vision/Quartz framework symbols at module load on the
# main thread. PyObjC's bridge resolves Foundation/Quartz symbols lazily
# the first time they're accessed; doing that from a worker thread (which
# is exactly what `loop.run_in_executor(None, apple_vision_ocr, ...)`
# does for parallel transcribe runs) races and intermittently raises
# `KeyError(<symbol>)`. Module-load resolution happens once on the main
# thread before any executor task can fire.
try:
    from Quartz import (  # noqa: F401  (imported for side-effect)
        CGImageSourceCreateWithURL,
        CGImageSourceCreateImageAtIndex,
        CGImageSourceCopyPropertiesAtIndex,
        CGBitmapContextCreate,
        CGBitmapContextCreateImage,
        CGColorSpaceCreateDeviceRGB,
        CGContextDrawPDFPage,
        CGPDFDocumentCreateWithURL,
        CGPDFDocumentGetPage,
        CGPDFDocumentGetNumberOfPages,
        CGPDFPageGetBoxRect,
        kCGPDFCropBox,
        kCGImageAlphaPremultipliedLast,
    )
    from Foundation import NSURL  # noqa: F401
except ImportError:
    # Non-macOS host (CI, Linux dev box) — Quartz isn't available.
    # apple_vision_ocr() raises a clean error at call time.
    pass

# Import from llm_base - the parent layer
from fichero.workflows.tools.llm_base import (
    # Port and config definitions
    BASE_INPUT_PORTS,
    BASE_CONFIG_SCHEMA,
    merge_config_schema,
    merge_ports,
    # Utilities
    LLMToolConfig,
    build_output_constraint,
    parse_output,
    build_context_section,
    build_reference_section,
    build_thinking_preamble,
    apply_reference_matching,
    ArtifactLookupError,
    find_existing_artifact,
    save_file_artifact as save_artifact,
    save_to_file as llm_save_to_file,
)
from fichero.workflows.tools._doc_lookup import (
    find_document_by_path,
    iter_document_lookup_paths,
    register_path_mapping,
    resolve_path_to_doc,
)
from fichero.workflows.circuit_breaker import (
    ProviderCircuitBreaker,
    ProviderRateLimitedError,
    call_with_breaker,
)

logger = logging.getLogger(__name__)


def _vision_backoff_settings() -> dict:
    """Exponential-backoff knobs for retryable provider quota errors (#2543).

    Overridable via env so an operator can tune behaviour for a huge run
    without code changes; defaults match circuit_breaker.py.
    """
    return {
        "max_retries": int(os.getenv("FICHERO_VISION_MAX_RETRIES", "4")),
        "base_delay": float(os.getenv("FICHERO_VISION_BACKOFF_BASE", "1.0")),
        "max_delay": float(os.getenv("FICHERO_VISION_BACKOFF_CAP", "30.0")),
        "jitter": float(os.getenv("FICHERO_VISION_BACKOFF_JITTER", "0.25")),
    }


def _vision_breaker_threshold() -> int:
    """Consecutive-quota-failure count that OPENS a provider's breaker (#2543)."""
    return int(os.getenv("FICHERO_VISION_BREAKER_THRESHOLD", "5"))


def _is_non_retriable_provider_error(message: str) -> bool:
    """Provider errors that should fail immediately without retries."""
    msg = (message or "").lower()
    return any(
        token in msg
        for token in (
            "key limit exceeded",
            "insufficient_quota",
            "insufficient quota",
            "quota",
            "invalid api key",
            "unauthorized",
            "authentication",
            "401",
            "402",
            "403",
        )
    )


def _log_vision_warning(message: str, file_path: str = None):
    """Log vision processing warnings to the activity log."""
    try:
        # Try to get activity tracker - this should work if we're in a workflow context
        from fichero.workflows.activity import get_activity_tracker
        from fichero.workflows.activity_types import ActivityType, ActivityLevel
        tracker = get_activity_tracker()
        if tracker:
            tracker.log(
                type=ActivityType.SYSTEM_WARNING,
                level=ActivityLevel.WARNING,
                message=message,
                metadata={"file_path": file_path} if file_path else {}
            )
    except Exception:
        # If activity tracker is not available, just log normally
        logger.warning(f"Vision processing warning: {message}")


# =============================================================================
# Vision-Specific Port and Config Schemas
# =============================================================================

# Vision input ports: files first, then all base ports
VISION_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="files",
            name="Files",
            port_type="input",
            data_type=DataType.FILES,
            required=True,
            description="Image files",
        ),
    ],
    BASE_INPUT_PORTS,
)

# Vision config: base config + vision-specific options
# NOTE: vision_mode is hidden by default because most vision tools only support LLM.
# Tools that support Apple Vision (like transcribe) should use custom UI to show it.
VISION_CONFIG_SCHEMA = merge_config_schema(
    BASE_CONFIG_SCHEMA,
    {
        "vision_mode": {
            "type": "string",
            "enum": ["auto", "apple", "llm"],
            "default": "auto",
            "description": (
                "Vision engine. 'auto' picks based on the resolved "
                "provider: apple → Apple Vision OCR; anything else → "
                "LLM vision path."
            ),
            "x-hidden": True,  # Hidden: most tools only support LLM
        },
        "max_image_dimension": {
            "type": "integer",
            "default": 2048,
            "description": "Max image size",
            "x-group": "primary",
        },
        # #1033 — born-digital PDFs already carry a selectable text
        # layer; the transcribe path uses it and skips vision OCR. Set
        # this when a PDF's own text layer is itself garbage and OCR is
        # genuinely needed.
        "force_ocr": {
            "type": "boolean",
            "default": False,
            "description": "Force OCR even when a PDF has a text layer",
            "x-group": "advanced",
        },
    },
)


# =============================================================================
# Vision Tool Configuration (extends LLMToolConfig)
# =============================================================================


@dataclass
class VisionToolConfig(LLMToolConfig):
    """Configuration for a vision tool.

    Extends LLMToolConfig with vision-specific options.
    """

    # Whether Apple Vision is supported for this tool
    supports_apple_vision: bool = False


@dataclass(slots=True)
class VisionOCRBox:
    """Normalized OCR geometry record."""

    text: str
    bbox: list[float]
    confidence: float | None = None
    page_index: int | None = None


@dataclass(slots=True)
class VisionOCRResult:
    """Apple Vision OCR text plus line/word geometry."""

    text: str
    line_boxes: list[VisionOCRBox]
    word_boxes: list[VisionOCRBox]


def _vision_value(obj: Any, name: str) -> Any:
    """Return an attribute value, calling it when Vision exposes a method."""
    if not hasattr(obj, name):
        return None
    value = getattr(obj, name)
    return value() if callable(value) else value


def _vision_bbox_from_rect(rect: Any) -> list[float] | None:
    """Coerce a Vision/Quartz rect into normalized [x, y, w, h]."""
    if rect is None:
        return None

    if isinstance(rect, dict):
        if {"x", "y", "width", "height"}.issubset(rect):
            return [
                float(rect["x"]),
                float(rect["y"]),
                float(rect["width"]),
                float(rect["height"]),
            ]
        origin = rect.get("origin")
        size = rect.get("size")
        if isinstance(origin, dict) and isinstance(size, dict):
            return [
                float(origin.get("x", 0.0)),
                float(origin.get("y", 0.0)),
                float(size.get("width", 0.0)),
                float(size.get("height", 0.0)),
            ]

    if isinstance(rect, (list, tuple)) and len(rect) >= 4:
        return [float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])]

    origin = getattr(rect, "origin", None)
    size = getattr(rect, "size", None)
    if origin is not None and size is not None:
        return [
            float(getattr(origin, "x", 0.0)),
            float(getattr(origin, "y", 0.0)),
            float(getattr(size, "width", 0.0)),
            float(getattr(size, "height", 0.0)),
        ]

    if all(hasattr(rect, attr) for attr in ("x", "y", "width", "height")):
        return [
            float(getattr(rect, "x")),
            float(getattr(rect, "y")),
            float(getattr(rect, "width")),
            float(getattr(rect, "height")),
        ]

    return None


def _vision_candidate_confidence(candidate: Any) -> float | None:
    confidence = _vision_value(candidate, "confidence")
    if confidence is None:
        return None
    try:
        return float(confidence)
    except (TypeError, ValueError):
        return None


def _vision_candidate_text(candidate: Any) -> str:
    text = _vision_value(candidate, "string")
    return text if isinstance(text, str) else ""


def _vision_candidate_bbox_for_range(candidate: Any, text_range: Any) -> Any:
    for method_name in (
        "boundingBoxForRange_error_",
        "boundingBoxForRange_",
        "boundingBoxForRange",
        "boundingBox_forRange_",
    ):
        method = getattr(candidate, method_name, None)
        if not callable(method):
            continue
        for args in ((text_range,), (text_range, None)):
            try:
                result = method(*args)
            except TypeError:
                continue
            if isinstance(result, tuple) and result:
                result = result[0]
            if result is not None:
                return result
    return None


def _vision_text_range(start: int, length: int) -> Any:
    try:
        from Foundation import NSMakeRange

        return NSMakeRange(start, length)
    except Exception:
        return (start, length)


def _vision_word_boxes(
    candidate: Any,
    text: str,
    *,
    page_index: int | None = None,
) -> list[VisionOCRBox]:
    """Build per-word geometry from a recognized text candidate."""
    boxes: list[VisionOCRBox] = []
    confidence = _vision_candidate_confidence(candidate)
    for match in re.finditer(r"\S+", text):
        bbox = _vision_candidate_bbox_for_range(
            candidate,
            _vision_text_range(match.start(), match.end() - match.start()),
        )
        bbox_list = _vision_bbox_from_rect(bbox)
        if bbox_list is None:
            continue
        boxes.append(
            VisionOCRBox(
                text=match.group(0),
                bbox=bbox_list,
                confidence=confidence,
                page_index=page_index,
            )
        )
    return boxes


def _vision_geometry_from_results(
    results: list[Any],
    *,
    page_index: int | None = None,
) -> VisionOCRResult:
    """Convert Vision observations into typed text + geometry records."""
    line_boxes: list[VisionOCRBox] = []
    word_boxes: list[VisionOCRBox] = []
    text_lines: list[str] = []

    for observation in results:
        candidates = observation.topCandidates_(1) if hasattr(observation, "topCandidates_") else []
        candidate = candidates[0] if candidates else None
        line_text = _vision_candidate_text(candidate) if candidate else ""
        line_bbox = _vision_bbox_from_rect(_vision_value(observation, "boundingBox"))
        confidence = _vision_candidate_confidence(candidate)

        if line_bbox is not None:
            line_boxes.append(
                VisionOCRBox(
                    text=line_text,
                    bbox=line_bbox,
                    confidence=confidence,
                    page_index=page_index,
                )
            )

        if line_text:
            text_lines.append(line_text)
            if candidate is not None:
                word_boxes.extend(
                    _vision_word_boxes(
                        candidate,
                        line_text,
                        page_index=page_index,
                    )
                )

    return VisionOCRResult(
        text="\n".join(text_lines),
        line_boxes=line_boxes,
        word_boxes=word_boxes,
    )


# =============================================================================
# Apple Vision OCR (macOS native)
# =============================================================================


def _render_pdf_page_to_cgimage(pdf_path: str, page_index: int = 0, dpi: int = 300):
    """Render a PDF page to a CGImage at the given DPI.

    CGImageSource cannot create CGImages from PDFs directly — PDFs are vector
    documents that must be rendered to a bitmap first.
    """
    from Quartz import (
        CGPDFDocumentCreateWithURL,
        CGPDFDocumentGetPage,
        CGPDFDocumentGetNumberOfPages,
        CGPDFPageGetBoxRect,
        kCGPDFMediaBox,
        CGBitmapContextCreate,
        CGBitmapContextCreateImage,
        CGContextDrawPDFPage,
        CGContextScaleCTM,
        kCGColorSpaceGenericRGB,
        CGColorSpaceCreateWithName,
        kCGImageAlphaPremultipliedLast,
    )
    from Foundation import NSURL

    url = NSURL.fileURLWithPath_(pdf_path)
    pdf_doc = CGPDFDocumentCreateWithURL(url)
    if not pdf_doc:
        raise ValueError(f"Could not open PDF: {pdf_path}")

    # PDF pages are 1-indexed; use C function (CGPDFDocumentRef is opaque)
    page = CGPDFDocumentGetPage(pdf_doc, page_index + 1)
    if not page:
        raise ValueError(f"PDF page {page_index + 1} not found in: {pdf_path}")

    # Get page dimensions at 72 DPI (PDF default) and scale to target DPI
    media_box = CGPDFPageGetBoxRect(page, kCGPDFMediaBox)
    scale = dpi / 72.0
    width = int(media_box.size.width * scale)
    height = int(media_box.size.height * scale)

    color_space = CGColorSpaceCreateWithName(kCGColorSpaceGenericRGB)
    ctx = CGBitmapContextCreate(
        None,
        width,
        height,
        8,
        width * 4,
        color_space,
        kCGImageAlphaPremultipliedLast,
    )
    if not ctx:
        raise ValueError(f"Failed to create bitmap context for PDF: {pdf_path}")

    # White background
    from Quartz import CGContextSetRGBFillColor, CGContextFillRect, CGRectMake

    CGContextSetRGBFillColor(ctx, 1.0, 1.0, 1.0, 1.0)
    CGContextFillRect(ctx, CGRectMake(0, 0, width, height))

    # Scale and draw the PDF page
    CGContextScaleCTM(ctx, scale, scale)
    CGContextDrawPDFPage(ctx, page)

    cg_image = CGBitmapContextCreateImage(ctx)
    if not cg_image:
        raise ValueError(f"Failed to render PDF page to image: {pdf_path}")

    return cg_image, CGPDFDocumentGetNumberOfPages(pdf_doc)


# Maximum image dimension (longest side) handed to Apple Vision. Larger
# images consume disproportionate memory + time without improving OCR
# accuracy beyond this resolution. Daniel: "really we don't want to send
# Apple Vision too large an image". (#796)
_VISION_MAX_DIMENSION = 4096


def _normalize_for_vision(
    image_path: str, force: bool = False,
) -> tuple[str, str | None]:
    """Pre-process an image for Apple Vision: convert to PNG via Pillow if
    it's a TIF (CoreGraphics' TIF support varies by codec — some multi-page
    or exotic-compression TIFs return nil from CGImageSourceCreateWithURL,
    which is exactly what bit Daniel on EAP1740_*.tif). Also downscale if
    longer side exceeds _VISION_MAX_DIMENSION. Pass ``force=True`` to
    always round-trip through PNG — used as a retry path when CoreGraphics
    fails on a JPEG that Pillow opens fine (CMYK, progressive, exotic
    EXIF/ICC).

    Returns (path_to_use, temp_path_to_delete). temp_path_to_delete is None
    when no conversion happened — caller should always pass it through to a
    cleanup step. (#796)
    """
    lower = image_path.lower()
    needs_format_convert = lower.endswith((".tif", ".tiff"))
    needs_resize = False

    try:
        from PIL import Image
        with Image.open(image_path) as img:
            longest = max(img.width, img.height)
            needs_resize = longest > _VISION_MAX_DIMENSION
            if not needs_format_convert and not needs_resize and not force:
                return (image_path, None)

            converted = img
            if needs_resize:
                ratio = _VISION_MAX_DIMENSION / longest
                new_size = (int(img.width * ratio), int(img.height * ratio))
                converted = img.resize(new_size, Image.LANCZOS)
                logger.info(
                    f"Apple Vision: downscaled {img.width}x{img.height} "
                    f"-> {new_size[0]}x{new_size[1]}"
                )
            # PNG round-trip via Pillow normalises any source format Pillow
            # can read into something CoreGraphics reliably opens.
            if converted.mode not in ("RGB", "RGBA", "L"):
                converted = converted.convert("RGB")
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            converted.save(tmp.name, format="PNG")
            return (tmp.name, tmp.name)
    except Exception as exc:
        logger.warning(
            f"Apple Vision: Pillow normalize failed for {image_path} ({exc}); "
            "falling back to original"
        )
        return (image_path, None)


def _try_pdf_text_layer(
    pdf_path: str,
    min_chars_per_page: int = 20,
) -> list[str] | None:
    """Extract per-page text from a PDF's embedded text layer.

    Returns a list of page texts when the PDF has a usable text layer,
    or None when extraction fails / produces empty / degenerate output
    (sign that the PDF is scanned + needs OCR).

    Per-page threshold: a page is considered to have a usable layer
    when its extracted text has at least `min_chars_per_page` non-space
    characters. We require every page to clear the bar — a single
    empty page in a born-digital PDF (chapter break, blank verso) is
    fine but a single page of text in an otherwise-scanned PDF means
    we should still run OCR over the whole thing for consistency.

    (#957 — born-digital PDFs were being run through Apple Vision OCR
    unnecessarily, costing ~1.5s/page and producing noisier output
    than the embedded text would.)
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF not installed; cannot check PDF text layer")
        return None

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        logger.warning("PyMuPDF could not open %s: %s", pdf_path, exc)
        return None

    try:
        per_page: list[str] = []
        for page in doc:
            try:
                text = page.get_text("text") or ""
            except Exception:
                text = ""
            per_page.append(text)
    finally:
        doc.close()

    # Every non-empty page should clear the threshold. A page with NO
    # text (blank verso) is fine — we just skip the threshold check
    # for it. But if EVERY page returns empty, the PDF is scanned.
    non_empty = [t for t in per_page if t.strip()]
    if not non_empty:
        return None
    if any(
        t.strip() and len(t.replace(" ", "").replace("\n", "")) < min_chars_per_page
        for t in per_page
    ):
        # At least one page has too-short text → mixed PDF (some pages
        # text, some scanned). Bail to OCR for uniformity.
        return None
    return per_page


def apple_vision_ocr(image_path: str, language: str = "en") -> str:
    """Extract text from image or PDF using macOS Vision framework.

    Uses VNRecognizeTextRequest for on-device OCR. For PDFs, renders each
    page to a bitmap first since CGImageSource can't create CGImages from PDFs.
    For TIFs and oversized images, normalizes via Pillow first (#796).
    """
    return apple_vision_ocr_with_geometry(image_path, language).text


def apple_vision_ocr_with_geometry(
    image_path: str,
    language: str = "en",
) -> VisionOCRResult:
    """Extract text and normalized Apple Vision geometry from image or PDF.

    This is the geometry-preserving helper API. The existing `apple_vision_ocr()`
    wrapper keeps returning plain text for compatibility. The next safe
    integration seam is `process_vision()`, which still consumes text-only
    results and can later attach `line_boxes` / `word_boxes` to the transcription
    artifact or records payload once that schema is ready.
    """
    cleanup_path: str | None = None
    try:
        from Quartz import (
            CGImageSourceCreateWithURL,
            CGImageSourceCreateImageAtIndex,
            CGImageSourceCopyPropertiesAtIndex,
        )
        from Foundation import NSURL

        # Verify file exists and is readable
        if not os.path.exists(image_path):
            raise ValueError(f"File not found: {image_path}")
        if not os.access(image_path, os.R_OK):
            raise ValueError(f"File not readable: {image_path}")

        # Check for iCloud/cloud storage dataless files
        try:
            stat_info = os.stat(image_path)
            if hasattr(stat_info, "st_flags") and (stat_info.st_flags & 0x40000000):
                raise ValueError(
                    f"File is stored in iCloud and not downloaded locally: {image_path}"
                )
            if stat_info.st_blocks == 0 and stat_info.st_size > 0:
                raise ValueError(
                    f"File appears to be a cloud placeholder: {image_path}"
                )
        except OSError:
            pass

        is_pdf = image_path.lower().endswith(".pdf")

        if is_pdf:
            # Render all PDF pages and OCR each one
            all_lines = []
            all_line_boxes: list[VisionOCRBox] = []
            all_word_boxes: list[VisionOCRBox] = []
            first_image, num_pages = _render_pdf_page_to_cgimage(image_path, 0)
            logger.info(f"PDF has {num_pages} pages, OCR-ing all pages")

            for page_idx in range(num_pages):
                if page_idx == 0:
                    cg_image = first_image
                else:
                    cg_image, _ = _render_pdf_page_to_cgimage(image_path, page_idx)

                page_geometry = _vision_ocr_cgimage_with_geometry(
                    cg_image,
                    language,
                    page_index=page_idx,
                )
                if page_geometry.text:
                    if num_pages > 1:
                        all_lines.append(f"--- Page {page_idx + 1} ---")
                    all_lines.append(page_geometry.text)
                all_line_boxes.extend(page_geometry.line_boxes)
                all_word_boxes.extend(page_geometry.word_boxes)

            return VisionOCRResult(
                text="\n\n".join(all_lines),
                line_boxes=all_line_boxes,
                word_boxes=all_word_boxes,
            )
        else:
            # Standard image path — ALWAYS Pillow-normalize first so
            # CoreGraphics gets a clean bounded PNG. JPEGs with CMYK,
            # progressive encoding, weird ICC/EXIF, or unusual chroma
            # subsampling intermittently fail CGImageSourceCreateWithURL
            # even though Pillow opens them fine. The Pillow round-trip
            # is ~50ms vs ~5-10s for OCR, so the cost is negligible. (#796)
            effective_path, cleanup_path = _normalize_for_vision(
                image_path, force=True,
            )

            url = NSURL.fileURLWithPath_(effective_path)
            image_source = CGImageSourceCreateWithURL(url, None)
            if not image_source:
                file_size = os.path.getsize(effective_path)
                raise ValueError(
                    f"CG could not open Pillow-normalized image "
                    f"(size: {file_size} bytes): {effective_path} "
                    f"(original: {image_path})"
                )

            props = CGImageSourceCopyPropertiesAtIndex(image_source, 0, None)
            if props:
                logger.debug(
                    f"Image: {props.get('PixelWidth', '?')}x"
                    f"{props.get('PixelHeight', '?')}"
                )

            cg_image = CGImageSourceCreateImageAtIndex(image_source, 0, None)
            if not cg_image:
                raise ValueError(
                    f"CGImage creation failed on Pillow-normalized image: "
                    f"{effective_path}"
                )

            return _vision_ocr_cgimage_with_geometry(cg_image, language)

    except ImportError as e:
        msg = f"Apple Vision not available: {e}"
        logger.error(msg)
        _log_vision_warning(msg)
        raise ValueError("Apple Vision OCR requires macOS with Vision framework")
    except Exception as e:
        msg = f"Apple Vision OCR failed: {e}"
        logger.error(msg)
        _log_vision_warning(msg, image_path)
        raise
    finally:
        if cleanup_path:
            try:
                os.remove(cleanup_path)
            except OSError:
                pass


def _vision_ocr_cgimage(cg_image, language: str = "en") -> str:
    return _vision_ocr_cgimage_with_geometry(cg_image, language).text


def _vision_ocr_cgimage_with_geometry(
    cg_image,
    language: str = "en",
    *,
    page_index: int | None = None,
) -> VisionOCRResult:
    """Run Vision OCR on a CGImage and return the recognized text.

    Retries with .Fast recognition level if Accurate returns empty, to handle
    degraded scans (low contrast, unusual layout, title pages) (#834).
    """
    import Vision

    lang_map = {
        "en": "en-US",
        "es": "es-ES",
        "fr": "fr-FR",
        "de": "de-DE",
        "pt": "pt-BR",
    }
    lang = lang_map.get(language, language)

    def _extract_text(request, recognition_level_name: str) -> VisionOCRResult | None:
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
            cg_image, None
        )  # pylint: disable=no-member
        success = handler.performRequests_error_([request], None)

        if not success:
            raise ValueError("Vision request failed")

        results = request.results()
        if not results:
            img_width = cg_image.width()
            img_height = cg_image.height()
            msg = (f"Vision OCR returned empty at {recognition_level_name} "
                   f"({img_width}x{img_height} pixels, lang={language})")
            logger.warning(msg)
            _log_vision_warning(msg)
            return None

        geometry = _vision_geometry_from_results(results, page_index=page_index)
        return geometry if geometry.text else None

    # Try Accurate first
    request = Vision.VNRecognizeTextRequest.alloc().init()  # pylint: disable=no-member
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)  # pylint: disable=no-member
    request.setRecognitionLanguages_([lang])

    geometry = _extract_text(request, "Accurate")
    if geometry is not None:
        return geometry

    # Retry with Fast if Accurate returned empty
    logger.info("Retrying with Fast recognition level")
    request = Vision.VNRecognizeTextRequest.alloc().init()  # pylint: disable=no-member
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelFast)  # pylint: disable=no-member
    request.setRecognitionLanguages_([lang])

    geometry = _extract_text(request, "Fast")
    if geometry is not None:
        return geometry

    # Both attempts returned empty
    msg = f"Vision OCR returned empty even at Fast level (lang={language})"
    logger.error(msg)
    _log_vision_warning(msg)
    return VisionOCRResult(text="", line_boxes=[], word_boxes=[])


async def apple_vision_ocr_async(image_path: str, language: str = "en") -> str:
    """Async wrapper for Apple Vision OCR."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, apple_vision_ocr, image_path, language)


@lru_cache(maxsize=4)
def _batch_render_pdf_pages_to_cgimages(pdf_path: str, dpi: int = 300):
    """Open a PDF document ONCE and render all pages to CGImages. (#2247)

    Returns (cgimages, num_pages). Individual page entries may be None if a
    page failed to render; callers should handle those gracefully.

    Compared to calling _render_pdf_page_to_cgimage per page, this avoids
    O(N) CGPDFDocumentCreateWithURL calls for an N-page document.
    """
    from Quartz import (  # noqa: PLC0415
        CGPDFDocumentCreateWithURL,
        CGPDFDocumentGetPage,
        CGPDFDocumentGetNumberOfPages,
        CGPDFPageGetBoxRect,
        kCGPDFMediaBox,
        CGBitmapContextCreate,
        CGBitmapContextCreateImage,
        CGContextDrawPDFPage,
        CGContextScaleCTM,
        kCGColorSpaceGenericRGB,
        CGColorSpaceCreateWithName,
        kCGImageAlphaPremultipliedLast,
        CGContextSetRGBFillColor,
        CGContextFillRect,
        CGRectMake,
    )
    from Foundation import NSURL  # noqa: PLC0415

    url = NSURL.fileURLWithPath_(pdf_path)
    pdf_doc = CGPDFDocumentCreateWithURL(url)
    if not pdf_doc:
        raise ValueError(f"Could not open PDF: {pdf_path}")

    num_pages = CGPDFDocumentGetNumberOfPages(pdf_doc)
    cg_images = []
    scale = dpi / 72.0

    for page_index in range(num_pages):
        page = CGPDFDocumentGetPage(pdf_doc, page_index + 1)
        if not page:
            cg_images.append(None)
            continue
        media_box = CGPDFPageGetBoxRect(page, kCGPDFMediaBox)
        width = int(media_box.size.width * scale)
        height = int(media_box.size.height * scale)
        color_space = CGColorSpaceCreateWithName(kCGColorSpaceGenericRGB)
        ctx = CGBitmapContextCreate(
            None, width, height, 8, width * 4, color_space,
            kCGImageAlphaPremultipliedLast,
        )
        if not ctx:
            cg_images.append(None)
            continue
        CGContextSetRGBFillColor(ctx, 1.0, 1.0, 1.0, 1.0)
        CGContextFillRect(ctx, CGRectMake(0, 0, width, height))
        CGContextScaleCTM(ctx, scale, scale)
        CGContextDrawPDFPage(ctx, page)
        cg_image = CGBitmapContextCreateImage(ctx)
        cg_images.append(cg_image if cg_image else None)

    # ponytail: small LRU for same-PDF fan-out; explicit render cache if
    # cross-run PDF reuse ever matters.
    return tuple(cg_images), num_pages


def _apple_ocr_pdf_pages(pdf_path: str, language: str = "en") -> list[str]:
    """OCR a PDF page by page, returning one text string per page (0-indexed).

    Used to propagate per-page content to page child documents after
    transcribing a PDF at the file level.

    Opens the PDF document exactly once via _batch_render_pdf_pages_to_cgimages
    to avoid O(N) parses for an N-page document. (#2247)
    """
    try:
        cg_images, num_pages = _batch_render_pdf_pages_to_cgimages(pdf_path)
    except Exception as e:
        logger.error(f"PDF page OCR failed: {e}")
        return []

    pages: list[str] = []
    for page_idx, cg_image in enumerate(cg_images):
        try:
            if cg_image is None:
                pages.append("")
                continue
            pages.append(_vision_ocr_cgimage(cg_image, language) or "")
        except Exception as e:
            msg = f"Page {page_idx} OCR failed: {e}"
            logger.warning(msg)
            _log_vision_warning(msg)
            pages.append("")
    return pages


def _apple_ocr_pdf_page(pdf_path: str, page_index: int, language: str = "en") -> str:
    """OCR one PDF page by zero-based page index."""
    try:
        cg_images, _ = _batch_render_pdf_pages_to_cgimages(pdf_path)
        cg_image = cg_images[page_index]
        if cg_image is None:
            raise ValueError(f"PDF page {page_index + 1} not found in: {pdf_path}")
        return _vision_ocr_cgimage(cg_image, language) or ""
    except Exception as e:
        msg = f"Page {page_index + 1} OCR failed: {e}"
        logger.warning(msg)
        _log_vision_warning(msg)
        return ""


async def apple_vision_ocr_pages_async(pdf_path: str, language: str = "en") -> list[str]:
    """Async per-page OCR for PDFs. Returns list[str] (one entry per page)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _apple_ocr_pdf_pages, pdf_path, language)


async def apple_vision_ocr_pdf_page_async(
    pdf_path: str,
    page_index: int,
    language: str = "en",
) -> str:
    """Async OCR for one PDF page by zero-based page index."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _apple_ocr_pdf_page,
        pdf_path,
        page_index,
        language,
    )


def normalize_vision_language(language: str | None) -> str:
    """Normalize legacy language hints to the locale strings Apple expects."""
    raw = (language or "").strip()
    if not raw:
        return "en-US"

    normalized = raw.replace("_", "-")
    lowered = normalized.lower()
    legacy_aliases = {
        "en": "en-US",
        "es": "es-ES",
        "fr": "fr-FR",
        "de": "de-DE",
        "it": "it-IT",
        "pt": "pt-BR",
        "ja": "ja-JP",
        "ko": "ko-KR",
    }
    if lowered in legacy_aliases:
        return legacy_aliases[lowered]

    if "-" in normalized:
        base, suffix = normalized.split("-", 1)
        if len(suffix) == 2:
            return f"{base.lower()}-{suffix.upper()}"
        return f"{base.lower()}-{suffix}"

    return lowered


def _build_page_records_for_file(
    library_path: str,
    parent_doc_id: str | None,
    file_text: str,
    per_page_texts: list[str] | None,
) -> list[dict]:
    """Return [{doc_id, text}, ...] keyed on page-child docs when present.

    Used by process_vision so downstream tools (extract_all) receive a
    typed records port carrying per-page provenance — extract_all stores
    KG claims and per-page artifacts on each page child's doc_id (#701,
    #837 follow-up). Falls back to a single record on the parent doc id
    when no page children exist (single-page files, non-PDFs).
    """
    if not parent_doc_id:
        return []

    if library_path:
        try:
            from fichero.db import db_manager
            from fichero.models import Document

            db = db_manager.get_database(library_path)
            page_docs = sorted(
                db.query(Document, parent_id=parent_doc_id),
                key=lambda d: d.sequence or 0,
            )
            if page_docs:
                records: list[dict] = []
                for page_doc in page_docs:
                    idx = (page_doc.sequence or 1) - 1
                    if per_page_texts and 0 <= idx < len(per_page_texts):
                        text = per_page_texts[idx]
                    else:
                        text = page_doc.page_content or ""
                    if text:
                        records.append({"doc_id": page_doc.id, "text": text})
                if records:
                    return records
        except Exception as e:
            logger.warning(
                f"Failed to build page records for {parent_doc_id}: {e}"
            )

    return [{"doc_id": parent_doc_id, "text": file_text or ""}] if file_text else []


def _page_index_from_document(doc: dict, metadata: dict) -> int | None:
    raw_page = doc.get("sequence")
    if raw_page is None:
        raw_page = metadata.get("page_number")
    try:
        page_number = int(raw_page)
    except (TypeError, ValueError):
        return None
    if page_number < 0:
        return None
    return page_number - 1 if page_number > 0 else 0


def _supports_return_boxes(llm_config: LLMConfig) -> bool:
    provider = (getattr(llm_config, "provider", "") or "").lower()
    model = (getattr(llm_config, "model", "") or "").lower()
    return provider == "google" and "gemini" in model


def _parse_return_boxes_payload(
    payload: str,
    *,
    llm_config: LLMConfig,
    page_index: int | None,
) -> OCRGeometryResult:
    geometry = parse_vlm_geometry(
        payload,
        provider=getattr(llm_config, "provider", "vlm_json") or "vlm_json",
        model=getattr(llm_config, "model", None),
    )
    if not geometry.boxes:
        raise ValueError("Gemini return_boxes response must include at least one box")
    boxes = [
        box.model_copy(
            update={
                "page_index": page_index if box.page_index is None else box.page_index,
            }
        )
        for box in geometry.boxes
    ]
    return geometry.model_copy(update={"boxes": boxes})


async def _propagate_to_page_children(
    parent_id: str,
    page_texts: list[str],
    library_path: str,
    artifact_type: str | None = None,
    llm_config: LLMConfig | None = None,
    page_geometries: list[OCRGeometryResult | None] | None = None,
) -> list[str] | None:
    """Write per-page OCR text to page child documents and re-embed each one.

    Call this after saving the combined transcript to the parent PDF document
    so that semantic search can surface individual pages instead of only the file.

    When `artifact_type` and `llm_config` are provided, ALSO save a per-page
    artifact row keyed on each page child's document_id (#701). That gives
    the V2 inspector something to render when you click a single page —
    previously page-children had `page_content` but no artifact rows, so
    the per-page panel was blank in V2. Returns the created per-page
    artifact IDs, or ``None`` when there are no page children.
    """
    created_artifact_ids: list[str] = []

    try:
        from fichero.db import db_manager
        from fichero.models import Artifact, Document, Status

        db = db_manager.get_database(library_path)
        page_docs = sorted(
            db.query(Document, parent_id=parent_id),
            key=lambda d: d.sequence or 0,
        )
        if not page_docs:
            return None

        for page_doc in page_docs:
            # sequence is 1-based; page_texts is 0-indexed
            page_idx = (page_doc.sequence or 1) - 1
            if page_idx >= len(page_texts):
                continue
            page_text = page_texts[page_idx]
            is_blank = not page_text or not page_text.strip()

            if not is_blank:
                if not isinstance(page_doc.metadata, dict):
                    page_doc.metadata = {}
                page_doc.page_content = page_text
                # In-progress, NOT completed: transcription is only the first
                # pipeline step. The workflow boundary flips this to completed
                # once ALL steps (NER / extract / KG) finish, so the page's
                # green check no longer appears mid-run (#1282). See
                # fichero.workflows.completion.complete_run_documents.
                page_doc.status = Status.processing
                db.save(page_doc)
                db.embed(page_doc)

            if artifact_type and llm_config is not None:
                try:
                    provider = getattr(llm_config, "provider", None) or "unknown"
                    model = getattr(llm_config, "model", None) or "unknown"
                    # Re-use an existing artifact if one already exists for
                    # this (page_doc, type, provider, model) — db.save()
                    # uses ON CONFLICT (id) which never fires for a freshly
                    # constructed Artifact() since it gets a new UUID each
                    # time, causing duplicates on re-run (#1067).
                    existing_arts = db.query(
                        Artifact,
                        document_id=page_doc.id,
                        artifact_type=artifact_type,
                    )
                    matched = [
                        a for a in existing_arts
                        if getattr(a, "provider", None) == provider
                        and getattr(a, "model", None) == model
                    ]
                    # Save even for blank pages so the inspector can
                    # distinguish "blank page" from "tool didn't run" (#1082).
                    artifact_content = page_text if not is_blank else ""
                    if matched:
                        art = matched[0]
                        art.content = artifact_content
                        art.ocr_geometry = (
                            page_geometries[page_idx]
                            if page_geometries and page_idx < len(page_geometries)
                            else None
                        )
                    else:
                        art = Artifact(
                            document_id=page_doc.id,
                            artifact_type=artifact_type,
                            content=artifact_content,
                            ocr_geometry=(
                                page_geometries[page_idx]
                                if page_geometries and page_idx < len(page_geometries)
                                else None
                            ),
                            provider=provider,
                            model=model,
                            version=1,
                            reviewed=False,
                        )
                    db.save(art)
                    created_artifact_ids.append(art.id)
                except Exception as artifact_err:
                    logger.warning(
                        "Failed to save per-page artifact for %s page %d: %s",
                        parent_id, page_idx + 1, artifact_err,
                    )

        logger.info(
            f"Propagated OCR to {len(page_docs)} page children of {parent_id}"
        )
        return created_artifact_ids
    except Exception as e:
        logger.warning(f"Failed to propagate OCR to page children of {parent_id}: {e}")
        return None


# =============================================================================
# Image Processing
# =============================================================================


def file_to_data_uri(file_path: str, max_dimension: int = 2048) -> str:
    """Convert image file to base64 data URI with optional resizing.

    Args:
        file_path: Path to image file
        max_dimension: Max width/height (0 = no resize)

    Returns:
        Base64 data URI
    """
    from PIL import Image

    path = Path(file_path)
    suffix = path.suffix.lower()

    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".bmp": "image/bmp",
    }
    mime_type = mime_types.get(suffix, "image/jpeg")

    if max_dimension > 0:
        try:
            img = Image.open(path)
            original_size = img.size

            if img.width > max_dimension or img.height > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                logger.debug(f"Resized {path.name}: {original_size} -> {img.size}")

            buffer = io.BytesIO()
            img_format = "JPEG" if mime_type == "image/jpeg" else "PNG"
            img.save(buffer, format=img_format, quality=95)
            data = base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception as e:
            logger.warning(f"Resize failed for {path.name}, using original: {e}")
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
    else:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{data}"


def _pdf_page_to_data_uri(file_path: str, page_index: int = 0, max_dimension: int = 2048) -> str:
    """Render a single PDF page to a PNG and return a base64 data URI.

    Reuses the cached Quartz batch render so the LLM vision path receives a
    proper raster image instead of raw PDF bytes.
    Falls back to a simple PIL open attempt on non-macOS hosts (CI / Linux).

    Args:
        file_path: Path to the PDF file.
        page_index: Zero-based page index to render.
        max_dimension: Max width/height for the output image (0 = no resize).

    Returns:
        A ``data:image/png;base64,...`` URI for the rendered page.

    Raises:
        ValueError: If the page cannot be rendered.
    """
    try:
        # Primary path: reuse the cached batch render for the source PDF.
        cg_images, _ = _batch_render_pdf_pages_to_cgimages(file_path)
        cg_image = cg_images[page_index]
        if cg_image is None:
            raise ValueError(f"PDF page {page_index + 1} not found in: {file_path}")
        return _cgimage_to_png_data_uri(cg_image, max_dimension=max_dimension)

    except Exception as quartz_err:
        # Non-macOS host (CI / Linux): Quartz not available.
        # Attempt a PIL fallback — not visually identical but better than
        # sending raw PDF bytes to the LLM.
        logger.warning(
            "Quartz PDF renderer unavailable (%s); falling back to PIL for page %d of %s",
            quartz_err,
            page_index,
            Path(file_path).name,
        )
        try:
            from PIL import Image
            img = Image.open(file_path)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            data = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/png;base64,{data}"
        except Exception as pil_err:
            raise ValueError(
                f"Cannot render PDF page {page_index} to image: "
                f"Quartz error: {quartz_err}; PIL error: {pil_err}"
            ) from pil_err


def _cgimage_to_png_data_uri(cg_image, max_dimension: int = 2048) -> str:
    """Convert a Quartz CGImage into a PNG data URI."""
    from Quartz import CGImageGetWidth, CGImageGetHeight
    from PIL import Image

    width = CGImageGetWidth(cg_image)
    height = CGImageGetHeight(cg_image)

    try:
        # PyObjC ≥ 9: CGImage exposes a bytes buffer directly.
        from Quartz import CGDataProviderCopyData, CGImageGetDataProvider
        provider = CGImageGetDataProvider(cg_image)
        raw_bytes = bytes(CGDataProviderCopyData(provider))
        img = Image.frombytes("RGBA", (width, height), raw_bytes)
    except Exception:
        # Fallback: write to a temp PNG via ImageIO and re-open.
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        from Quartz import (
            CGImageDestinationCreateWithURL,
            CGImageDestinationAddImage,
            CGImageDestinationFinalize,
            kUTTypePNG,
        )
        from Foundation import NSURL
        url = NSURL.fileURLWithPath_(tmp_path)
        dest = CGImageDestinationCreateWithURL(url, kUTTypePNG, 1, None)
        CGImageDestinationAddImage(dest, cg_image, None)
        CGImageDestinationFinalize(dest)
        img = Image.open(tmp_path).copy()
        Path(tmp_path).unlink(missing_ok=True)

    if max_dimension > 0 and (img.width > max_dimension or img.height > max_dimension):
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{data}"


# =============================================================================
# Database Operations
# =============================================================================
#
# `save_artifact` here is `llm_base.save_file_artifact` (imported as that name
# above) — the single shared file-oriented wrapper around the canonical
# `llm_base.save_artifact`. Vision (and audio/video/extract) no longer each
# re-declare a wrapper; the per-page document-resolution contract lives in
# exactly one place. The import alias is kept so every call site below and the
# test patch target `vision_base.save_artifact` continue to resolve unchanged.


# =============================================================================
# Main Processing Function
# =============================================================================


async def process_vision(
    files: list[str],
    documents: list[dict],
    prompt: str,
    llm_config: LLMConfig,
    library_path: str,
    task_id: str | None,
    tool_config: VisionToolConfig,
    *,
    # Vision-specific (from VISION_CONFIG_SCHEMA)
    vision_mode: str = "llm",
    language: str = "en",
    max_image_dimension: int = 2048,
    force_ocr: bool = False,
    # LLM parameters (from BASE_CONFIG_SCHEMA)
    temperature: float | None = None,
    max_tokens: int | None = None,
    # Output format (from BASE_CONFIG_SCHEMA)
    output_format: str = "text",
    output_options: dict | None = None,
    # Reference values (from BASE_CONFIG_SCHEMA)
    reference_values: dict[str, list] | None = None,
    match_mode: str = "prefer",
    # Context (from BASE_CONFIG_SCHEMA)
    context: str | None = None,
    input_metadata: dict | None = None,
    # Thinking mode (from BASE_CONFIG_SCHEMA)
    thinking_mode: str = "off",
    # Storage (from BASE_CONFIG_SCHEMA)
    save_to_db: bool = True,
    save_to_file_flag: bool = False,
    return_boxes: bool = False,
    metadata_field: str | None = None,
    custom_metadata: dict | None = None,
) -> dict[str, Any]:
    """Process images with vision AI.

    This is the shared core function for all vision tools.
    Supports all BASE_CONFIG options plus vision-specific options.
        output_options: Format-specific options
        reference_values: Known values to match against
        match_mode: How to use reference values
        context: Previous text/transcription
        input_metadata: Existing metadata to include in prompt
        save_to_db: Whether to save results
        metadata_field: Override metadata field
        custom_metadata: Additional metadata to save

    Returns:
        Dict with text, value, texts, values, results, artifacts, error
    """
    from fichero.llm import vision, LLMConfig

    language = normalize_vision_language(language)

    if isinstance(files, str):
        files = [files]

    if not files:
        logger.warning("process_vision: no input files — all selected IDs may be stale/invalid")
        return {
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "output_files": [],
            "page_records": [],
        }

    # vision_mode="auto" picks the engine from the resolved provider:
    # apple → Apple Vision OCR (free, local, OCR-only); anything else
    # → LLM vision path (sends image as data URI to a vision-capable
    # LLM). Lets one preset work for users on Apple OR cloud vision.
    if vision_mode == "auto":
        provider = (getattr(llm_config, "provider", "") or "").lower()
        vision_mode = "apple" if provider == "apple" else "llm"

    # Override LLMConfig with user values if provided
    effective_config = llm_config
    if temperature is not None or max_tokens is not None:
        effective_config = dataclasses.replace(
            llm_config,
            temperature=temperature
            if temperature is not None
            else llm_config.temperature,
            max_tokens=max_tokens if max_tokens is not None else llm_config.max_tokens,
        )

    # Build path -> document_id mapping
    path_to_doc = {}
    if documents:
        for doc in documents:
            if isinstance(doc, dict) and doc.get("path"):
                for path_key in iter_document_lookup_paths(doc["path"]):
                    register_path_mapping(path_to_doc, path_key, doc.get("id"))
    # Per-page fan-out (#891) pairs files[i] with documents[i] — for a
    # parent PDF expanded into N page children, every file_path is the
    # parent path and the unique info lives in the document dict (its
    # own .id and .page_content). Path-keyed lookup collapses those, so
    # build the existing-text + page-id maps by index instead.
    existing_text_by_index: list[str] = []
    page_doc_id_by_index: list[str | None] = []
    page_index_by_index: list[int | None] = []
    page_doc_dict_by_index: list[dict | None] = []
    if documents:
        for index, doc in enumerate(documents):
            if isinstance(doc, dict):
                metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
                raw_transcription = metadata.get("transcription")
                doc_id = doc.get("id")
                if (
                    (not isinstance(raw_transcription, str) or not raw_transcription.strip())
                    and library_path
                    and doc_id
                ):
                    try:
                        from fichero.db import db_manager
                        from fichero.models import Document

                        db = db_manager.get_database(library_path)
                        live_doc = db.get(Document, str(doc_id))
                        live_metadata = live_doc.metadata if live_doc else {}
                        if isinstance(live_metadata, dict):
                            raw_transcription = live_metadata.get("transcription")
                            # Refresh text_length from live record; the payload
                            # metadata may be from an older snapshot.
                            if live_metadata.get("text_length") is not None:
                                metadata = {**metadata, "text_length": live_metadata["text_length"]}
                    except Exception as exc:
                        logger.debug(
                            "process_vision: could not reload transcription "
                            "metadata for %s: %s",
                            doc_id,
                            exc,
                        )
                pc = doc.get("page_content")
                expected_text_length = metadata.get("text_length")
                transcription_text = (
                    raw_transcription.strip()
                    if isinstance(raw_transcription, str)
                    else ""
                )
                # Trigger PDF text-layer fallback when the stored transcription
                # is shorter than expected (truncated) OR completely absent while
                # text_length indicates the page has real content.
                raw_is_truncated = (
                    isinstance(expected_text_length, int)
                    and expected_text_length > len(transcription_text) + 50
                )
                if raw_is_truncated and index < len(files):
                    file_path = str(files[index])
                    page_index = _page_index_from_document(doc, metadata)
                    if file_path.lower().endswith(".pdf") and page_index is not None:
                        page_texts = _try_pdf_text_layer(file_path)
                        if page_texts and page_index < len(page_texts):
                            layer_text = page_texts[page_index]
                            logger.info(
                                "process_vision: transcription for doc %s "
                                "has %d chars (expected ~%d) — replacing with "
                                "PDF text layer page %d (%d chars)",
                                doc_id,
                                len(transcription_text),
                                expected_text_length or 0,
                                page_index + 1,
                                len(layer_text),
                            )
                            raw_transcription = layer_text
                # Page content can be overwritten by later narrative/catalogue
                # tools. For transcribe passthrough, prefer the raw extracted
                # PDF/OCR text stored in metadata so Extract All Entities sees
                # the source page, not a previous summary.
                existing = (
                    raw_transcription
                    if isinstance(raw_transcription, str) and raw_transcription.strip()
                    else pc if isinstance(pc, str) and pc.strip()
                    else ""
                )
                existing_text_by_index.append(existing)
                page_doc_id_by_index.append(doc_id)
                page_doc_dict_by_index.append(doc if doc_id else None)
                page_index = (
                    _page_index_from_document(doc, metadata)
                    if doc.get("parent_id")
                    else None
                )
                page_index_by_index.append(page_index)
            else:
                existing_text_by_index.append("")
                page_doc_id_by_index.append(None)
                page_index_by_index.append(None)
                page_doc_dict_by_index.append(None)
    logger.debug(
        f"process_vision: {len(files)} files, {len(documents)} documents, "
        f"{len(path_to_doc)} path mappings, "
        f"{sum(1 for t in existing_text_by_index if t)} with pre-extracted text"
    )

    # Build context section
    context_section = build_context_section(context, input_metadata)

    # Build reference section
    ref_section = build_reference_section(reference_values, match_mode)

    # Build output constraint
    output_constraint = build_output_constraint(output_format, output_options)

    # Build thinking preamble
    thinking_preamble = build_thinking_preamble(thinking_mode)

    # Combine prompt
    final_prompt = (
        f"{thinking_preamble}{context_section}{prompt}{ref_section}{output_constraint}"
    )

    results = []
    texts = []
    values = []
    artifact_ids = []
    output_files = []
    page_records: list[dict] = []

    # Text-format extensions whose content is already plain text — no
    # vision call needed. Mirrors loaders/document_loader.py:TEXT_FORMATS
    # so Transcribe behaves like ingest for these files. Without this,
    # Catalogue (Mixed) on a folder containing .md crashes the vision
    # API with "cannot identify image file". See #884.
    text_format_suffixes = {
        ".txt", ".md", ".markdown", ".rst", ".html", ".htm", ".xml", ".csv",
    }

    # #2543: one circuit breaker per RUN, shared across all the concurrent
    # per-file tasks below (asyncio.gather). After K consecutive quota/
    # rate-limit failures for a provider it OPENS, so the remaining files for
    # that provider fail fast instead of hammering a dead provider for ~99k
    # calls. The breaker's internal state is asyncio.Lock-guarded so it is safe
    # under the bounded-concurrent gather. `_vision_backoff` holds the
    # exponential-backoff knobs reused for the retryable path.
    _vision_breaker = ProviderCircuitBreaker(threshold=_vision_breaker_threshold())
    _vision_backoff = _vision_backoff_settings()

    # Per-file processing is extracted into a coroutine so the node can run the
    # files BOUNDED-CONCURRENTLY (#2539) instead of strictly one-at-a-time.
    # Each call uses its OWN local accumulators and returns them; the driver
    # below merges the per-file outcomes back in input order so
    # results/texts/values/records/artifacts stay index-aligned to `files`
    # (asyncio.gather preserves argument order). The big try/except keeps the
    # existing per-file ERROR ISOLATION: one file failing records its error and
    # never aborts the siblings or the node.
    async def _process_file(file_index: int, file_path: str) -> dict:
        results: list = []
        texts: list = []
        values: list = []
        artifact_ids: list = []
        output_files: list = []
        page_records: list[dict] = []

        def _outcome() -> dict:
            return {
                "results": results,
                "texts": texts,
                "values": values,
                "artifact_ids": artifact_ids,
                "output_files": output_files,
                "page_records": page_records,
            }

        # #2543: route every vision/LLM call for this file through the shared
        # per-provider circuit breaker + exponential backoff. `make_coro` is a
        # zero-arg callable returning a fresh awaitable so retries re-issue the
        # request. On a retryable (429/quota/rate-limit) error it backs off and
        # retries; once K consecutive failures OPEN the breaker for this
        # provider, this and every subsequent file for that provider raise
        # ProviderRateLimitedError WITHOUT calling the provider. The shared
        # vision semaphore is released during each backoff sleep (handled inside
        # call_with_breaker) so a backed-off file never pins a concurrency slot.
        _vision_provider = getattr(effective_config, "provider", "") or "unknown"

        async def _vision_resilient(make_coro):
            return await call_with_breaker(
                make_coro,
                provider=_vision_provider,
                breaker=_vision_breaker,
                semaphore=_vision_sem,
                label=Path(file_path).name,
                **_vision_backoff,
            )

        try:
            # Pre-extracted text fast path. If the document record for
            # this file already has non-empty page_content (because
            # ingest extracted it via Kreuzberg / PDFTextLoader at
            # import time), there is no reason to re-OCR. Treat the
            # existing text as the transcription. Covers digital PDFs,
            # DOCX, EPUB, etc. — anything Kreuzberg can extract on
            # ingest. Index-paired with documents[file_index] so
            # per-page fan-out works (page children share parent path).
            # #884 follow-up + #891.
            existing_text = (
                existing_text_by_index[file_index]
                if file_index < len(existing_text_by_index)
                else ""
            )
            # Compute per-page index first so we can gate the doc-id fallback.
            requested_page_index = (
                page_index_by_index[file_index]
                if file_index < len(page_index_by_index)
                else None
            )
            # Prefer the page-doc's own id when present (per-page fan
            # out passes the page child as documents[i]); fall back to
            # the path-based lookup for callers that don't use the
            # per-index pattern.  In per-page mode, NEVER fall back to
            # resolve_path_to_doc: file_path is the parent PDF's path,
            # so the fallback would silently route to the parent.  If
            # the page id is missing, skip and warn instead. (#2430)
            _page_doc_id = (
                page_doc_id_by_index[file_index]
                if file_index < len(page_doc_id_by_index)
                else None
            )
            if requested_page_index is not None and not _page_doc_id:
                logger.warning(
                    "Per-page mode: missing page doc id for file_index=%d "
                    "file=%s — skipping artifact to avoid routing to parent PDF",
                    file_index,
                    file_path,
                )
                results.append({"file": file_path, "text": "", "value": None})
                texts.append("")
                values.append(None)
                return _outcome()
            doc_id_for_file = _page_doc_id or resolve_path_to_doc(path_to_doc, file_path)
            if return_boxes:
                if vision_mode != "llm":
                    raise ValueError(
                        "return_boxes is only supported on the Gemini LLM vision path"
                    )
                if not _supports_return_boxes(effective_config):
                    raise ValueError(
                        "return_boxes requires provider=google with a Gemini model"
                    )
            # Pre-loaded page-doc dict (eliminates db.get re-fetch in save_artifact, #2430)
            _preloaded_doc = (
                page_doc_dict_by_index[file_index]
                if file_index < len(page_doc_dict_by_index)
                else None
            )
            if existing_text:
                logger.info(
                    f"Pre-extracted text passthrough: {Path(file_path).name} "
                    f"({len(existing_text)} chars, doc_id={doc_id_for_file})"
                )
                results.append(
                    {"file": file_path, "text": existing_text, "value": existing_text}
                )
                texts.append(existing_text)
                values.append(existing_text)
                page_records.extend(
                    _build_page_records_for_file(
                        library_path,
                        doc_id_for_file,
                        existing_text,
                        None,
                    )
                )
                if save_to_db and library_path:
                    artifact_id = await save_artifact(
                        file_path=file_path,
                        content=existing_text,
                        document_id=doc_id_for_file,
                        library_path=library_path,
                        llm_config=effective_config,
                        task_id=task_id,
                        tool_config=tool_config,
                        metadata_field=metadata_field,
                        custom_metadata=custom_metadata,
                        document=_preloaded_doc,
                    )
                    if artifact_id:
                        artifact_ids.append(artifact_id)
                return _outcome()

            # Text-file fast path: read directly and treat as the
            # "transcription" output. We still save the artifact and
            # update page_content downstream so Extract All Entities
            # gets text input. Skips Apple Vision / LLM vision entirely.
            suffix = Path(file_path).suffix.lower()
            if suffix in text_format_suffixes:
                try:
                    file_text = Path(file_path).read_text(
                        encoding="utf-8", errors="replace"
                    )
                except OSError as e:
                    logger.warning(
                        f"Text-file fast path: cannot read {file_path}: {e}"
                    )
                    file_text = ""
                logger.info(
                    f"Text-format passthrough ({suffix}): {Path(file_path).name}"
                )
                results.append({"file": file_path, "text": file_text, "value": file_text})
                texts.append(file_text)
                values.append(file_text)
                page_records.extend(
                    _build_page_records_for_file(
                        library_path,
                        doc_id_for_file,
                        file_text,
                        None,
                    )
                )
                # Persist as an artifact so downstream nodes that read
                # artifacts (not page_content) still see the text.
                if save_to_db and library_path and file_text:
                    artifact_id = await save_artifact(
                        file_path=file_path,
                        content=file_text,
                        document_id=doc_id_for_file,
                        library_path=library_path,
                        llm_config=effective_config,
                        task_id=task_id,
                        tool_config=tool_config,
                        metadata_field=metadata_field,
                        custom_metadata=custom_metadata,
                        document=_preloaded_doc,
                    )
                    if artifact_id:
                        artifact_ids.append(artifact_id)
                return _outcome()

            per_page_texts: list[str] | None = None
            per_page_geometries: list[OCRGeometryResult | None] | None = None
            page_geometry: OCRGeometryResult | None = None

            # PDF text-layer short-circuit (#957, #1033, #1064). A born-digital
            # PDF (InDesign export, LaTeX, Word→PDF) already carries a
            # selectable text layer; re-deriving it with vision OCR is wasted
            # compute and usually noisier than the native text. Computed UP
            # FRONT — before the skip-if-artifact cache — because the embedded
            # text layer is the authoritative source and must beat a stale
            # cached OCR artifact (#1064: a pre-#1033 Apple Vision artifact was
            # shielding this short-circuit and serving garbage on every run).
            # `force_ocr` overrides it for a PDF whose own text layer is garbage.
            pdf_layer_used = False
            _llm_multipage = False  # set True when LLM path processes all PDF pages
            image_uri: str | None = None  # set in LLM single-page path; guard retry (#2241)
            if (
                not force_ocr
                and tool_config.supports_apple_vision
                and vision_mode != "llm"  # LLM mode must render+call LLM, not use text layer
                and file_path.lower().endswith(".pdf")
            ):
                layer = _try_pdf_text_layer(file_path)
                if layer is not None:
                    if (
                        requested_page_index is not None
                        and 0 <= requested_page_index < len(layer)
                    ):
                        per_page_texts = [layer[requested_page_index]]
                    else:
                        per_page_texts = layer
                    pdf_layer_used = True
                    logger.info(
                        "PDF text layer present — skipped vision OCR "
                        "for %s (%s)",
                        Path(file_path).name,
                        f"page {requested_page_index + 1}"
                        if requested_page_index is not None
                        else f"{len(per_page_texts)} pages",
                    )
                    parts = []
                    for offset, t in enumerate(per_page_texts):
                        if t:
                            page_number = (
                                requested_page_index + 1
                                if requested_page_index is not None
                                else offset + 1
                            )
                            if len(per_page_texts) > 1:
                                parts.append(f"--- Page {page_number} ---")
                            parts.append(t)
                    text = "\n\n".join(parts)
                    parsed = text

            # Skip-if-done: use the existing artifact if one already exists
            # for this (document, artifact_type) and the tool config allows it.
            # Avoids re-OCRing files already processed by a previous workflow
            # run, making Catalogue idempotent when composed with Transcribe.
            # Skipped for a born-digital PDF (pdf_layer_used) — its fresh text
            # layer beats any cached artifact, including stale OCR garbage (#1064).
            if (
                not pdf_layer_used
                and tool_config.skip_if_artifact_exists
                and save_to_db
                and library_path
            ):
                # Key the cache on provider+model so a re-run with a different
                # model (e.g. qwen-vl-3.5 → qwen-vl-3.6v) produces a new
                # artifact instead of silently reusing the old model's output.
                # Apple Vision has no provider/model, so falls back to the
                # unkeyed match (any transcription artifact for this doc).
                cache_provider = getattr(llm_config, "provider", None) if vision_mode != "apple" else None
                cache_model = getattr(llm_config, "model", None) if vision_mode != "apple" else None
                try:
                    existing = find_existing_artifact(
                        document_id=doc_id_for_file,
                        file_path=file_path,
                        artifact_type=tool_config.artifact_type,
                        library_path=library_path,
                        provider=cache_provider,
                        model=cache_model,
                    )
                except ArtifactLookupError as exc:
                    # Skip-if-done cache read FAILED — we cannot prove a cached
                    # transcription exists, so do NOT silently skip-as-hit nor
                    # treat it as a clean miss. Log loud and fall through to the
                    # real OCR/LLM path (visible re-run on an unknown). (#2511)
                    logger.error(
                        "Skip-if-done cache check FAILED for %s — re-running "
                        "(could not consult cache, not assuming miss): %s",
                        Path(file_path).name,
                        exc,
                    )
                    existing = None
                cached_text = getattr(existing, "content", None) if existing else None
                if isinstance(cached_text, str) and cached_text:
                    logger.info(
                        f"Skip-if-done: reusing cached {tool_config.artifact_type} "
                        f"artifact for {Path(file_path).name}"
                    )
                    results.append(
                        {"file": file_path, "text": cached_text, "value": cached_text, "cached": True}
                    )
                    texts.append(cached_text)
                    values.append(cached_text)
                    artifact_ids.append(existing.id)
                    page_records.extend(
                        _build_page_records_for_file(
                            library_path,
                            doc_id_for_file,
                            cached_text,
                            None,
                        )
                    )
                    return _outcome()

            # Process with Apple Vision or LLM (the PDF text-layer
            # short-circuit ran above, before the skip-if-artifact cache).
            if pdf_layer_used:
                # Born-digital PDF text layer: this is not OCR, so stamp the
                # saved artifact with a provenance label that distinguishes it
                # from Apple Vision OCR.
                save_config = LLMConfig(provider="pdf_text", model="pdf-text-layer")
            elif vision_mode == "apple" and tool_config.supports_apple_vision:
                logger.info(f"Apple Vision: {Path(file_path).name}")
                if file_path.lower().endswith(".pdf"):
                    # No usable text layer (checked above) → OCR
                    # page-by-page so we can propagate per-page content
                    # to page child documents after saving the parent.
                    if requested_page_index is not None:
                        text = await apple_vision_ocr_pdf_page_async(
                            file_path,
                            requested_page_index,
                            language,
                        )
                        per_page_texts = [text]
                    else:
                        per_page_texts = await apple_vision_ocr_pages_async(
                            file_path,
                            language,
                        )
                        parts = []
                        for i, t in enumerate(per_page_texts):
                            if t:
                                if len(per_page_texts) > 1:
                                    parts.append(f"--- Page {i + 1} ---")
                                parts.append(t)
                        text = "\n\n".join(parts)
                else:
                    text = await apple_vision_ocr_async(file_path, language)
                # Apple Vision doesn't use LLM params, parse as text
                parsed = text
            else:
                logger.info(f"LLM Vision: {Path(file_path).name}")
                # Check if we should use HF Inference API for thinking models
                from fichero.llm import (
                    is_thinking_model,
                    vision_inference_api,
                    parse_thinking_response,
                )

                # #2215 — whole-PDF, no per-page fan-out: process every page
                # so per_page_texts is populated and _propagate_to_page_children
                # can write each page's text to its page child document.
                # When the workflow has already expanded to page children
                # (requested_page_index is not None), fall through to the
                # single-page path which writes directly to the page child doc.
                if file_path.lower().endswith(".pdf") and requested_page_index is None:
                    _llm_multipage = True
                    try:
                        import fitz as _fitz
                        _fd = _fitz.open(file_path)
                        _llm_num_pages = len(_fd)
                        _fd.close()
                    except Exception:
                        try:
                            _, _llm_num_pages = _render_pdf_page_to_cgimage(file_path, 0)
                        except Exception:
                            _llm_num_pages = 1
                    logger.info(
                        "LLM Vision PDF: processing all %d pages of %s",
                        _llm_num_pages,
                        Path(file_path).name,
                    )
                    _llm_page_texts: list[str] = []
                    _llm_page_geometries: list[OCRGeometryResult | None] = []
                    for _page_idx in range(_llm_num_pages):
                        try:
                            _page_uri = _pdf_page_to_data_uri(
                                file_path,
                                page_index=_page_idx,
                                max_dimension=max_image_dimension,
                            )
                            if is_thinking_model(effective_config.model):
                                _raw = await _vision_resilient(
                                    lambda: vision_inference_api(
                                        images=[_page_uri],
                                        prompt=final_prompt,
                                        model=effective_config.model,
                                        api_key=effective_config.api_key,
                                        temperature=effective_config.temperature,
                                        max_tokens=effective_config.max_tokens,
                                    )
                                )
                                _ans, _thk = parse_thinking_response(_raw)
                                if _thk:
                                    logger.info("Thinking (page %d): %s...", _page_idx, _thk[:100])
                                _llm_page_texts.append(str(_ans or ""))
                            else:
                                _pt = await _vision_resilient(
                                    lambda: vision(
                                        images=[_page_uri],
                                        prompt=final_prompt,
                                        config=effective_config,
                                    )
                                )
                                _payload = _pt if isinstance(_pt, str) else ""
                                if return_boxes:
                                    _geometry = _parse_return_boxes_payload(
                                        _payload,
                                        llm_config=effective_config,
                                        page_index=_page_idx,
                                    )
                                    _llm_page_geometries.append(_geometry)
                                    _llm_page_texts.append(_geometry.text)
                                else:
                                    _llm_page_geometries.append(None)
                                    _llm_page_texts.append(_payload)
                        except ProviderRateLimitedError:
                            # #2543: breaker is OPEN for this provider — abort
                            # the per-page loop and fail this file fast rather
                            # than silently emitting empty pages. Propagates to
                            # the per-file handler, which records the loud error.
                            raise
                        except Exception as _pe:
                            logger.warning(
                                "LLM Vision: page %d of %s failed: %s",
                                _page_idx, Path(file_path).name, _pe,
                            )
                            _llm_page_texts.append("")
                            _llm_page_geometries.append(None)
                    per_page_texts = _llm_page_texts
                    per_page_geometries = _llm_page_geometries
                    _parts: list[str] = []
                    for _i, _t in enumerate(per_page_texts):
                        if _t:
                            if _llm_num_pages > 1:
                                _parts.append(f"--- Page {_i + 1} ---")
                            _parts.append(_t)
                    text = "\n\n".join(_parts)
                    parsed = parse_output(text, output_format, output_options)
                else:
                    # Single page (per-page fan-out) or non-PDF.
                    # #670: PDFs must be rendered to a raster PNG before being
                    # sent to the vision LLM.  file_to_data_uri only handles
                    # standard image formats; passing a raw PDF produces either
                    # a crash, a mis-labelled MIME type, or unreadable bytes.
                    if file_path.lower().endswith(".pdf"):
                        _pdf_page_idx = requested_page_index  # not None: per-page fan-out
                        logger.info(
                            "LLM Vision PDF: rendering page %d of %s",
                            _pdf_page_idx,
                            Path(file_path).name,
                        )
                        image_uri = _pdf_page_to_data_uri(
                            file_path,
                            page_index=_pdf_page_idx,
                            max_dimension=max_image_dimension,
                        )
                    else:
                        image_uri = file_to_data_uri(
                            file_path, max_dimension=max_image_dimension
                        )

                    if is_thinking_model(effective_config.model):
                        # Use Inference API for thinking models
                        logger.info(
                            f"Using HF Inference API for thinking model: {effective_config.model}"
                        )
                        try:
                            text = await _vision_resilient(
                                lambda: vision_inference_api(
                                    images=[image_uri],
                                    prompt=final_prompt,
                                    model=effective_config.model,
                                    api_key=effective_config.api_key,
                                    temperature=effective_config.temperature,
                                    max_tokens=effective_config.max_tokens,
                                )
                            )

                            # Parse thinking response
                            answer, thinking = parse_thinking_response(text)

                            # Log thinking process if present
                            if thinking:
                                logger.info(f"Model thinking process: {thinking[:200]}...")

                            # Use answer for further processing
                            parsed = parse_output(answer, output_format, output_options)

                        except Exception as e:
                            logger.error(f"HF Inference API failed: {e}")
                            raise
                    else:
                        # Use standard LangChain router for regular models
                        text = await _vision_resilient(
                            lambda: vision(
                                images=[image_uri],
                                prompt=final_prompt,
                                config=effective_config,
                            )
                        )
                        # Parse output according to format
                        parsed = parse_output(text, output_format, output_options)
                    if return_boxes:
                        page_geometry = _parse_return_boxes_payload(
                            text,
                            llm_config=effective_config,
                            page_index=requested_page_index,
                        )
                        text = page_geometry.text
                        parsed = parse_output(text, output_format, output_options)

            # Apply reference matching
            if reference_values:
                parsed = apply_reference_matching(parsed, reference_values)

            # Empty-response retry. Vision LLMs occasionally return ""
            # under provider load (rate-limit hiccup), safety-filter
            # refusal, or timeout; one quick retry recovers most of
            # them. If still empty after retry, fail this file rather
            # than save a useless empty Transcription artifact and
            # cascade into downstream tools (#837 follow-up).
            # `[sin texto]` is the prompt's explicit no-text token and
            # is a real result — don't retry that one.
            # Skip for _llm_multipage: per-page failures were logged individually;
            # re-sending only page 0 would not help a multi-page failure.
            if not (text or "").strip() and vision_mode != "apple" and not _llm_multipage and image_uri is not None:
                logger.warning(
                    f"Vision LLM returned empty for {Path(file_path).name}; "
                    f"retrying once before declaring failure"
                )
                try:
                    text = await _vision_resilient(
                        lambda: vision(
                            images=[image_uri],
                            prompt=final_prompt,
                            config=effective_config,
                        )
                    )
                    parsed = parse_output(text, output_format, output_options)
                    if reference_values:
                        parsed = apply_reference_matching(parsed, reference_values)
                except ProviderRateLimitedError:
                    # #2543: breaker opened during the empty-response retry —
                    # fail this file fast instead of saving an empty result.
                    raise
                except Exception as retry_exc:
                    logger.warning(
                        f"Retry failed for {Path(file_path).name}: {retry_exc}"
                    )

            if not (text or "").strip():
                msg = (
                    f"Vision LLM returned empty response for "
                    f"{Path(file_path).name} (after retry). Likely a "
                    f"provider safety refusal or sustained timeout; no "
                    f"transcription artifact saved."
                )
                logger.warning(msg)
                _log_vision_warning(msg, file_path)
                results.append(
                    {"file": file_path, "text": "", "value": "", "error": msg}
                )
                texts.append("")
                values.append(None)
                return _outcome()

            result = {"file": file_path, "text": text, "value": parsed}

            # Save to database
            if save_to_db and library_path:
                # Set proper provider/model labels for local processing
                save_config = effective_config
                if pdf_layer_used:
                    save_config = LLMConfig(provider="pdf_text", model="pdf-text-layer")
                elif vision_mode == "apple":
                    # LLMConfig is already imported at the top of process_vision
                    # (closure scope); a local re-import here would shadow it and
                    # break the pdf_text branch above (referenced-before-assign).
                    save_config = LLMConfig(provider="apple", model="apple-vision")

                # #2249/#2395: when per_page_texts is populated (whole-PDF path) and
                # the current doc is the parent (path_to_doc has its path, so
                # page children haven't been expanded yet by sources.py), route
                # per-page texts directly to page-child artifacts and skip
                # writing the concatenated transcript to the parent artifact.
                # Falls back to the parent artifact when no page children exist
                # (PDFs not yet ingested with per-page expansion).
                # Guard: only trigger whole-PDF propagation when ALL pages were
                # processed (requested_page_index is None). In per-page fan-out
                # mode (requested_page_index is set), per_page_texts has exactly
                # one element but it belongs to the focused page — running
                # _propagate_to_page_children would write that page's text to
                # page child #1 (index 0) regardless of the actual page, clobbering
                # sibling content. Instead fall through to save_artifact with
                # doc_id_for_file (the page child's own ID). (#2395/#2396)
                _whole_pdf_parent = None
                if per_page_texts and requested_page_index is None:
                    _whole_pdf_parent = resolve_path_to_doc(path_to_doc, file_path)
                    if (
                        not _whole_pdf_parent
                        and library_path
                        and len(per_page_texts) > 1
                    ):
                        # #2523 backstop: the per-page `documents` port was not
                        # wired into this node (path_to_doc is empty), so the
                        # parent can't be found in the map. Resolve it straight
                        # from the DB by path so the whole-PDF guard below fires
                        # (split per-page / fail loud) instead of letting
                        # save_artifact route the combined transcript onto the
                        # parent PDF. Single-page PDFs are left alone — there the
                        # parent IS the page and saving onto it is correct.
                        try:
                            from fichero.db import db_manager as _dbm
                            from fichero.models import Document as _Document

                            _parent = find_document_by_path(
                                _dbm.get_database(library_path),
                                _Document,
                                file_path,
                            )
                            if _parent is not None:
                                _whole_pdf_parent = _parent.id
                        except Exception as _resolve_exc:
                            logger.warning(
                                "Whole-PDF backstop: could not resolve parent for "
                                "%s by path: %s",
                                file_path,
                                _resolve_exc,
                            )
                if _whole_pdf_parent:
                    page_artifact_ids = await _propagate_to_page_children(
                        _whole_pdf_parent,
                        per_page_texts,
                        library_path,
                        artifact_type=tool_config.artifact_type,
                        llm_config=save_config,
                        page_geometries=per_page_geometries,
                    )
                    if page_artifact_ids is None and len(per_page_texts) > 1:
                        # Multi-page PDF with NO page children. Per #2430 /
                        # Daniel's one-page-at-a-time rule we must NEVER write the
                        # concatenated whole-PDF transcript onto the parent. Try
                        # to split on the spot, then re-propagate per-page.
                        try:
                            from fichero.db import db_manager as _dbm
                            from fichero.ingest import _create_pdf_page_children
                            from fichero.models import Document as _Document

                            _db = _dbm.get_database(library_path)
                            _parent_doc = _db.get(_Document, _whole_pdf_parent)
                            if _parent_doc is not None:
                                _create_pdf_page_children(
                                    _parent_doc, Path(file_path), _db, auto_embed=False
                                )
                        except Exception as _split_exc:
                            logger.error(
                                "Whole-PDF guard: on-the-spot split failed for "
                                "%s: %s",
                                file_path,
                                _split_exc,
                            )
                        page_artifact_ids = await _propagate_to_page_children(
                            _whole_pdf_parent,
                            per_page_texts,
                            library_path,
                            artifact_type=tool_config.artifact_type,
                            llm_config=save_config,
                            page_geometries=per_page_geometries,
                        )
                        if page_artifact_ids is None:
                            # Still unsplittable. FAIL LOUD rather than write a
                            # combined --- Page N --- blob onto the parent PDF
                            # (#2430, no-silent-fallback).
                            raise ValueError(
                                f"Per-page transcription guard: PDF "
                                f"{Path(file_path).name} has {len(per_page_texts)} "
                                f"pages but could not be split into page children; "
                                f"refusing to write a combined transcript onto the "
                                f"parent (one-page-at-a-time, #2430)."
                            )
                        artifact_ids.extend(page_artifact_ids)
                    elif page_artifact_ids is None:
                        # Genuinely single-page PDF (per_page_texts has one entry):
                        # the parent IS the page, so saving the transcript onto it
                        # is correct — no combined blob, no granularity bug.
                        artifact_id = await save_artifact(
                            file_path=file_path,
                            content=text,
                            document_id=doc_id_for_file,
                            library_path=library_path,
                            llm_config=save_config,
                            task_id=task_id,
                            tool_config=tool_config,
                            ocr_geometry=page_geometry,
                            metadata_field=metadata_field,
                            custom_metadata=custom_metadata,
                            document=_preloaded_doc,
                        )
                        if artifact_id:
                            result["artifact_id"] = artifact_id
                            artifact_ids.append(artifact_id)
                        else:
                            logger.warning(f"save_artifact returned None for {file_path}")
                    elif isinstance(page_artifact_ids, list):
                        artifact_ids.extend(page_artifact_ids)
                else:
                    artifact_id = await save_artifact(
                        file_path=file_path,
                        content=text,
                        document_id=doc_id_for_file,
                        library_path=library_path,
                        llm_config=save_config,
                        task_id=task_id,
                        tool_config=tool_config,
                        ocr_geometry=page_geometry,
                        metadata_field=metadata_field,
                        custom_metadata=custom_metadata,
                        document=_preloaded_doc,
                    )
                    if artifact_id:
                        result["artifact_id"] = artifact_id
                        artifact_ids.append(artifact_id)
                    else:
                        logger.warning(f"save_artifact returned None for {file_path}")

            # Save to file
            if save_to_file_flag and library_path:
                output_path = await llm_save_to_file(
                    content=text,
                    data=parsed if isinstance(parsed, dict) else None,
                    library_path=library_path,
                    document_id=doc_id_for_file,
                    file_path=file_path,
                    tool_config=tool_config,
                    output_format=output_format,
                )
                if output_path:
                    output_files.append(output_path)
                    result["output_file"] = output_path

            results.append(result)
            texts.append(text)
            values.append(parsed)
            page_records.extend(
                _build_page_records_for_file(
                    library_path,
                    doc_id_for_file,
                    text,
                    per_page_texts,
                )
            )

        except ProviderRateLimitedError as e:
            # #2543: the per-provider circuit breaker is OPEN — record a loud,
            # unmistakable per-file error so the run surfaces WHY it stopped
            # transcribing instead of silently burning the remaining files.
            err = str(e)
            msg = (
                f"Vision processing skipped for {Path(file_path).name}: {err}"
            )
            logger.error(msg)
            _log_vision_warning(msg, file_path)
            results.append(
                {"file": file_path, "text": "", "value": None, "error": err}
            )
            texts.append("")
            values.append(None)
        except Exception as e:
            err = str(e)
            if _is_non_retriable_provider_error(err):
                msg = f"Vision processing failed for {Path(file_path).name} with non-retriable provider/auth/quota error: {err}"
                logger.error(msg)
                _log_vision_warning(msg, file_path)
            else:
                msg = f"Vision processing failed for {Path(file_path).name}: {e}"
                logger.error(msg)
                _log_vision_warning(msg, file_path)
            results.append(
                {"file": file_path, "text": "", "value": None, "error": err}
            )
            texts.append("")
            values.append(None)

        return _outcome()

    # Run the per-file coroutines BOUNDED-CONCURRENTLY (#2539). Each task
    # acquires the shared vision semaphore (builder._get_vision_semaphore,
    # capped at VISION_FAN_OUT_CONCURRENCY) around its WHOLE body — exactly as
    # builder.py wraps each fan-out tool call — so the peak number of
    # simultaneously in-flight vision/LLM calls stays capped even though every
    # file is scheduled. asyncio.gather preserves argument order, so merging the
    # outcomes below keeps results/texts/values/records/artifacts index-aligned
    # to `files`. Files are scheduled in bounded windows so a huge `files` list
    # never materialises an unbounded number of coroutines at once (peak overlap
    # is still the semaphore cap, not the window size).
    from fichero.workflows.builder import (
        VISION_FAN_OUT_CONCURRENCY,
        _get_vision_semaphore,
    )

    _vision_sem = _get_vision_semaphore()

    async def _run_one(file_index: int, file_path: str) -> dict:
        try:
            async with _vision_sem:
                return await _process_file(file_index, file_path)
        except Exception as exc:  # defensive: _process_file already isolates
            # per-file errors via its own try/except, but never let an
            # unexpected escape abort the sibling files.
            err = str(exc)
            logger.error(
                "Vision per-file task crashed for %s: %s",
                Path(file_path).name,
                err,
            )
            return {
                "results": [
                    {"file": file_path, "text": "", "value": None, "error": err}
                ],
                "texts": [""],
                "values": [None],
                "artifact_ids": [],
                "output_files": [],
                "page_records": [],
            }

    _schedule_window = max(VISION_FAN_OUT_CONCURRENCY * 8, 32)
    for _start in range(0, len(files), _schedule_window):
        _chunk = files[_start : _start + _schedule_window]
        _outcomes = await asyncio.gather(
            *(
                _run_one(_start + _offset, _file_path)
                for _offset, _file_path in enumerate(_chunk)
            )
        )
        for _outcome in _outcomes:
            results.extend(_outcome["results"])
            texts.extend(_outcome["texts"])
            values.extend(_outcome["values"])
            artifact_ids.extend(_outcome["artifact_ids"])
            output_files.extend(_outcome["output_files"])
            page_records.extend(_outcome["page_records"])

    # Check for errors
    errors = [r.get("error") for r in results if r.get("error")]
    error_msg = None
    if errors:
        if len(files) == 1:
            error_msg = errors[0]
        else:
            error_msg = f"{len(errors)}/{len(files)} failed: {errors[0]}"

    # For single file, return the value directly; for multiple, return list
    single_value = values[0] if len(values) == 1 else values

    return {
        "text": "\n\n".join(texts),
        "value": single_value,
        "texts": texts,
        "values": values,
        "results": results,
        # Canonical records port for workflow edges (e.g.
        # transcribe.records -> extract_all.records). Keep the legacy
        # page_records key for callers that read it directly.
        "records": page_records,
        "artifacts": artifact_ids,
        "output_files": output_files,
        "page_records": page_records,
        "error": error_msg,
    }
