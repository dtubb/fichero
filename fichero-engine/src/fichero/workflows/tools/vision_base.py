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
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from fichero.llm import LLMConfig

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
    find_existing_artifact,
    save_artifact as llm_save_artifact,
    save_to_file as llm_save_to_file,
)

logger = logging.getLogger(__name__)


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
            first_image, num_pages = _render_pdf_page_to_cgimage(image_path, 0)
            logger.info(f"PDF has {num_pages} pages, OCR-ing all pages")

            for page_idx in range(num_pages):
                if page_idx == 0:
                    cg_image = first_image
                else:
                    cg_image, _ = _render_pdf_page_to_cgimage(image_path, page_idx)

                page_text = _vision_ocr_cgimage(cg_image, language)
                if page_text:
                    if num_pages > 1:
                        all_lines.append(f"--- Page {page_idx + 1} ---")
                    all_lines.append(page_text)

            return "\n\n".join(all_lines)
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

            return _vision_ocr_cgimage(cg_image, language)

    except ImportError as e:
        logger.error(f"Apple Vision not available: {e}")
        raise ValueError("Apple Vision OCR requires macOS with Vision framework")
    except Exception as e:
        logger.error(f"Apple Vision OCR failed: {e}")
        raise
    finally:
        if cleanup_path:
            try:
                os.remove(cleanup_path)
            except OSError:
                pass


def _vision_ocr_cgimage(cg_image, language: str = "en") -> str:
    """Run Vision OCR on a CGImage and return the recognized text."""
    import Vision

    request = Vision.VNRecognizeTextRequest.alloc().init()  # pylint: disable=no-member
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)  # pylint: disable=no-member

    lang_map = {
        "en": "en-US",
        "es": "es-ES",
        "fr": "fr-FR",
        "de": "de-DE",
        "pt": "pt-BR",
    }
    request.setRecognitionLanguages_([lang_map.get(language, language)])

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        cg_image, None
    )  # pylint: disable=no-member
    success = handler.performRequests_error_([request], None)

    if not success:
        raise ValueError("Vision request failed")

    results = request.results()
    if not results:
        return ""

    lines = []
    for observation in results:
        if hasattr(observation, "topCandidates_"):
            candidates = observation.topCandidates_(1)
            if candidates:
                lines.append(candidates[0].string())

    return "\n".join(lines)


async def apple_vision_ocr_async(image_path: str, language: str = "en") -> str:
    """Async wrapper for Apple Vision OCR."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, apple_vision_ocr, image_path, language)


def _apple_ocr_pdf_pages(pdf_path: str, language: str = "en") -> list[str]:
    """OCR a PDF page by page, returning one text string per page (0-indexed).

    Used to propagate per-page content to page child documents after
    transcribing a PDF at the file level.
    """
    try:
        first_image, num_pages = _render_pdf_page_to_cgimage(pdf_path, 0)
    except Exception as e:
        logger.error(f"PDF page OCR failed: {e}")
        return []

    pages: list[str] = []
    for page_idx in range(num_pages):
        try:
            cg_image = first_image if page_idx == 0 else _render_pdf_page_to_cgimage(pdf_path, page_idx)[0]
            pages.append(_vision_ocr_cgimage(cg_image, language) or "")
        except Exception as e:
            logger.warning(f"Page {page_idx} OCR failed: {e}")
            pages.append("")
    return pages


async def apple_vision_ocr_pages_async(pdf_path: str, language: str = "en") -> list[str]:
    """Async per-page OCR for PDFs. Returns list[str] (one entry per page)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _apple_ocr_pdf_pages, pdf_path, language)


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


async def _propagate_to_page_children(
    parent_id: str,
    page_texts: list[str],
    library_path: str,
    artifact_type: str | None = None,
    llm_config: LLMConfig | None = None,
) -> None:
    """Write per-page OCR text to page child documents and re-embed each one.

    Call this after saving the combined transcript to the parent PDF document
    so that semantic search can surface individual pages instead of only the file.

    When `artifact_type` and `llm_config` are provided, ALSO save a per-page
    artifact row keyed on each page child's document_id (#701). That gives
    the V2 inspector something to render when you click a single page —
    previously page-children had `page_content` but no artifact rows, so
    the per-page panel was blank in V2.
    """
    try:
        from fichero.db import db_manager
        from fichero.models import Artifact, Document, Status

        db = db_manager.get_database(library_path)
        page_docs = sorted(
            db.query(Document, parent_id=parent_id),
            key=lambda d: d.sequence or 0,
        )
        if not page_docs:
            return

        for page_doc in page_docs:
            # sequence is 1-based; page_texts is 0-indexed
            page_idx = (page_doc.sequence or 1) - 1
            if page_idx >= len(page_texts) or not page_texts[page_idx]:
                continue
            page_text = page_texts[page_idx]
            if not isinstance(page_doc.metadata, dict):
                page_doc.metadata = {}
            page_doc.page_content = page_text
            page_doc.status = Status.completed
            db.save(page_doc)
            db.embed(page_doc)

            if artifact_type and llm_config is not None:
                try:
                    provider = getattr(llm_config, "provider", None) or "unknown"
                    model = getattr(llm_config, "model", None) or "unknown"
                    artifact = Artifact(
                        document_id=page_doc.id,
                        artifact_type=artifact_type,
                        content=page_text,
                        provider=provider,
                        model=model,
                        version=1,
                        reviewed=False,
                    )
                    db.save(artifact)
                except Exception as artifact_err:
                    logger.warning(
                        "Failed to save per-page artifact for %s page %d: %s",
                        parent_id, page_idx + 1, artifact_err,
                    )

        logger.info(
            f"Propagated OCR to {len(page_docs)} page children of {parent_id}"
        )
    except Exception as e:
        logger.warning(f"Failed to propagate OCR to page children of {parent_id}: {e}")


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


# =============================================================================
# Database Operations (wraps llm_base.save_artifact for file-based saving)
# =============================================================================


async def save_artifact(
    file_path: str,
    content: str,
    document_id: str | None,
    library_path: str,
    llm_config: LLMConfig,
    task_id: str | None,
    tool_config: VisionToolConfig,
    *,
    metadata_field: str | None = None,
    custom_metadata: dict | None = None,
) -> str | None:
    """Save vision result to database.

    Wraps llm_base.save_artifact with file_path-based document lookup.
    """
    return await llm_save_artifact(
        document_id=document_id,
        file_path=file_path,
        content=content,
        data=None,
        library_path=library_path,
        llm_config=llm_config,
        task_id=task_id,
        tool_config=tool_config,
        metadata_field=metadata_field,
        custom_metadata=custom_metadata,
    )


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

    if isinstance(files, str):
        files = [files]

    if not files:
        return {
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "output_files": [],
            "page_records": [],
            "error": "No input files provided",
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
                path_to_doc[doc["path"]] = doc.get("id")
    # Per-page fan-out (#891) pairs files[i] with documents[i] — for a
    # parent PDF expanded into N page children, every file_path is the
    # parent path and the unique info lives in the document dict (its
    # own .id and .page_content). Path-keyed lookup collapses those, so
    # build the existing-text + page-id maps by index instead.
    existing_text_by_index: list[str] = []
    page_doc_id_by_index: list[str | None] = []
    if documents:
        for doc in documents:
            if isinstance(doc, dict):
                pc = doc.get("page_content")
                existing_text_by_index.append(
                    pc if isinstance(pc, str) and pc.strip() else ""
                )
                page_doc_id_by_index.append(doc.get("id"))
            else:
                existing_text_by_index.append("")
                page_doc_id_by_index.append(None)
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

    for file_index, file_path in enumerate(files):
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
            # Prefer the page-doc's own id when present (per-page fan
            # out passes the page child as documents[i]); fall back to
            # the path-based lookup for callers that don't use the
            # per-index pattern.
            doc_id_for_file = (
                page_doc_id_by_index[file_index]
                if file_index < len(page_doc_id_by_index)
                else None
            ) or path_to_doc.get(file_path)
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
                    )
                    if artifact_id:
                        artifact_ids.append(artifact_id)
                continue

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
                        path_to_doc.get(file_path),
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
                        document_id=path_to_doc.get(file_path),
                        library_path=library_path,
                        llm_config=effective_config,
                        task_id=task_id,
                        tool_config=tool_config,
                        metadata_field=metadata_field,
                        custom_metadata=custom_metadata,
                    )
                    if artifact_id:
                        artifact_ids.append(artifact_id)
                continue

            per_page_texts: list[str] | None = None

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
            if (
                not force_ocr
                and tool_config.supports_apple_vision
                and file_path.lower().endswith(".pdf")
            ):
                layer = _try_pdf_text_layer(file_path)
                if layer is not None:
                    per_page_texts = layer
                    pdf_layer_used = True
                    logger.info(
                        "PDF text layer present — skipped vision OCR "
                        "for %s (%d pages)",
                        Path(file_path).name, len(per_page_texts),
                    )
                    parts = []
                    for i, t in enumerate(per_page_texts):
                        if t:
                            if len(per_page_texts) > 1:
                                parts.append(f"--- Page {i + 1} ---")
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
                existing = find_existing_artifact(
                    document_id=path_to_doc.get(file_path),
                    file_path=file_path,
                    artifact_type=tool_config.artifact_type,
                    library_path=library_path,
                    provider=cache_provider,
                    model=cache_model,
                )
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
                            path_to_doc.get(file_path),
                            cached_text,
                            None,
                        )
                    )
                    continue

            # Process with Apple Vision or LLM (the PDF text-layer
            # short-circuit ran above, before the skip-if-artifact cache).
            if pdf_layer_used:
                # text / parsed / per_page_texts already set above.
                pass
            elif vision_mode == "apple" and tool_config.supports_apple_vision:
                logger.info(f"Apple Vision: {Path(file_path).name}")
                if file_path.lower().endswith(".pdf"):
                    # No usable text layer (checked above) → OCR
                    # page-by-page so we can propagate per-page content
                    # to page child documents after saving the parent.
                    per_page_texts = await apple_vision_ocr_pages_async(file_path, language)
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
                image_uri = file_to_data_uri(
                    file_path, max_dimension=max_image_dimension
                )

                # Check if we should use HF Inference API for thinking models
                from fichero.llm import (
                    is_thinking_model,
                    vision_inference_api,
                    parse_thinking_response,
                )

                if is_thinking_model(effective_config.model):
                    # Use Inference API for thinking models
                    logger.info(
                        f"Using HF Inference API for thinking model: {effective_config.model}"
                    )
                    try:
                        text = await vision_inference_api(
                            images=[image_uri],
                            prompt=final_prompt,
                            model=effective_config.model,
                            api_key=effective_config.api_key,
                            temperature=effective_config.temperature,
                            max_tokens=effective_config.max_tokens,
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
                    text = await vision(
                        images=[image_uri],
                        prompt=final_prompt,
                        config=effective_config,
                    )
                    # Parse output according to format
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
            if not (text or "").strip() and vision_mode != "apple":
                logger.warning(
                    f"Vision LLM returned empty for {Path(file_path).name}; "
                    f"retrying once before declaring failure"
                )
                try:
                    text = await vision(
                        images=[image_uri],
                        prompt=final_prompt,
                        config=effective_config,
                    )
                    parsed = parse_output(text, output_format, output_options)
                    if reference_values:
                        parsed = apply_reference_matching(parsed, reference_values)
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
                results.append(
                    {"file": file_path, "text": "", "value": "", "error": msg}
                )
                texts.append("")
                values.append(None)
                continue

            result = {"file": file_path, "text": text, "value": parsed}

            # Save to database
            if save_to_db and library_path:
                # Set proper provider/model labels for local processing
                save_config = effective_config
                if vision_mode == "apple":
                    from fichero.llm import LLMConfig

                    save_config = LLMConfig(provider="Apple", model="Vision")

                artifact_id = await save_artifact(
                    file_path=file_path,
                    content=text,
                    document_id=path_to_doc.get(file_path),
                    library_path=library_path,
                    llm_config=save_config,
                    task_id=task_id,
                    tool_config=tool_config,
                    metadata_field=metadata_field,
                    custom_metadata=custom_metadata,
                )
                if artifact_id:
                    result["artifact_id"] = artifact_id
                    artifact_ids.append(artifact_id)

                    # Propagate per-page OCR to page child documents so semantic
                    # search can surface individual pages, not only the parent PDF.
                    # Pass artifact_type + llm_config so the helper also saves a
                    # per-page artifact row — V2 inspector clicks on a single
                    # page child should see that page's transcription panel
                    # (#701).
                    if per_page_texts and len(per_page_texts) > 1:
                        parent_id = path_to_doc.get(file_path)
                        if parent_id:
                            await _propagate_to_page_children(
                                parent_id,
                                per_page_texts,
                                library_path,
                                artifact_type=tool_config.artifact_type,
                                llm_config=save_config,
                            )
                else:
                    logger.warning(f"save_artifact returned None for {file_path}")

            # Save to file
            if save_to_file_flag and library_path:
                output_path = await llm_save_to_file(
                    content=text,
                    data=parsed if isinstance(parsed, dict) else None,
                    library_path=library_path,
                    document_id=path_to_doc.get(file_path),
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
                    path_to_doc.get(file_path),
                    text,
                    per_page_texts,
                )
            )

        except Exception as e:
            logger.error(f"Vision processing failed for {file_path}: {e}")
            results.append(
                {"file": file_path, "text": "", "value": None, "error": str(e)}
            )
            texts.append("")
            values.append(None)

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
        "artifacts": artifact_ids,
        "output_files": output_files,
        "page_records": page_records,
        "error": error_msg,
    }
