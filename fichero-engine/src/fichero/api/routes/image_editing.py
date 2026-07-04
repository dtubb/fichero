"""Image editing API routes (#462, #463, #466, #467, #468).

Stores per-document non-destructive edit chains and renders previews on demand.
"""

from __future__ import annotations

import asyncio
import io
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from fichero.api.auth import action_context
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.models import DocType, Document, ImageEditChain
from fichero.storage import resolve_source
from fichero.workflows.tools.fuzzy_clean_images import apply_fuzzy_clean

router = APIRouter(prefix="/images", tags=["images"])


class ImageEditChainUpsert(BaseModel):
    operations: list[dict[str, Any]] = Field(default_factory=list)


class ImageEditChainResponse(BaseModel):
    document_id: str
    operations: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime


class CropOperationRequest(BaseModel):
    left: int
    top: int
    width: int
    height: int
    auto_orient: bool = True
    page: int = 1


class RotateOperationRequest(BaseModel):
    angle: float
    expand: bool = True
    page: int = 1


class StraightenOperationRequest(BaseModel):
    page: int = Field(1, ge=1)


class EnhanceOperationRequest(BaseModel):
    brightness: float = Field(1.0, ge=0.0)
    contrast: float = Field(1.0, ge=0.0)
    sharpen: float = Field(1.0, ge=0.0)
    auto_levels: bool = False
    page: int = Field(1, ge=1)


class RemoveBackgroundOperationRequest(BaseModel):
    method: str = Field("opencv", pattern="^(opencv|threshold|rembg)$")
    threshold: int = Field(28, ge=0, le=255)
    page: int = Field(1, ge=1)


class SegmentOperationRequest(BaseModel):
    method: str = Field("foreground", pattern="^(foreground|page)$")
    threshold: int = Field(28, ge=0, le=255)
    min_area: int = Field(100, ge=1)
    max_segments: int = Field(20, ge=1, le=200)
    page: int = Field(1, ge=1)


def _get_or_404_document(db: Database, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
    return doc


def _resolve_source_or_404(db: Database, doc: Document) -> Path:
    source_path = resolve_source(doc, library_root=db.path.parent)
    if not source_path:
        raise HTTPException(status_code=404, detail="Source file not available")
    return source_path


def _get_chain(db: Database, document_id: str) -> ImageEditChain | None:
    rows = list(db.query(ImageEditChain, document_id=document_id))
    return rows[0] if rows else None


def _load_source_image(path: Path, page: int = 1) -> Image.Image:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise HTTPException(
                status_code=500, detail="PyMuPDF is required for PDF preview rendering"
            ) from exc
        doc = fitz.open(str(path))
        if len(doc) == 0 or page < 1 or page > len(doc):
            raise HTTPException(status_code=400, detail="PDF has no pages")
        pdf_page = doc[page - 1]
        pix = pdf_page.get_pixmap(matrix=fitz.Matrix(2, 2))
        doc.close()
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    with Image.open(path) as img:
        # Honour EXIF orientation so the backend render matches what the
        # SwiftUI viewer (NSImage) and Finder/Preview show. Without this the
        # editor opened the image at a different orientation than the viewer
        # (#1529). exif_transpose also strips the orientation tag, so the
        # crop op's own exif_transpose (auto_orient) becomes a safe no-op.
        oriented = ImageOps.exif_transpose(img) or img
        if oriented.mode not in ("RGB", "L", "RGBA"):
            oriented = oriented.convert("RGB")
        return oriented.copy()


def _remove_background(image: Image.Image, params: dict[str, Any]) -> Image.Image:
    method = str(params.get("method", "opencv")).strip().lower()
    if method == "rembg":
        try:
            from rembg import remove
        except ImportError as exc:
            raise HTTPException(
                status_code=501, detail="rembg is not installed in this backend"
            ) from exc
        return remove(image.convert("RGBA"))

    if method == "opencv":
        try:
            import cv2  # type: ignore[import-not-found]
            import numpy as np
        except ImportError:
            method = "threshold"
        else:
            rgb = np.array(image.convert("RGB"))
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            _, mask = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )
            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            rgba = image.convert("RGBA")
            rgba.putalpha(Image.fromarray(mask))
            return rgba

    if method == "threshold":
        threshold = int(params.get("threshold", 28))
        rgba = image.convert("RGBA")
        rgb = image.convert("RGB")
        background = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
        diff = ImageChops.difference(rgb, background).convert("L")
        alpha = diff.point(lambda value: 255 if value > threshold else 0)
        rgba.putalpha(alpha)
        return rgba

    raise HTTPException(status_code=400, detail=f"Unsupported background method: {method}")


def _estimate_straighten_angle(image: Image.Image) -> float:
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np
    except ImportError:
        return 0.0

    rgb = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    min_length = max(80, gray.shape[1] // 5)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=100,
        minLineLength=min_length,
        maxLineGap=12,
    )
    if lines is None:
        return 0.0

    angles: list[float] = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if -15.0 <= angle <= 15.0:
            angles.append(angle)

    if not angles:
        return 0.0
    return float(np.median(angles))


def _foreground_segments(
    image: Image.Image, threshold: int, min_area: int, max_segments: int
) -> list[dict[str, Any]]:
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, background).convert("L")
    mask = diff.point(lambda value: 255 if value > threshold else 0)
    pixels = mask.load()
    width, height = mask.size
    visited: set[tuple[int, int]] = set()
    segments: list[dict[str, Any]] = []

    for y in range(height):
        for x in range(width):
            if (x, y) in visited or pixels[x, y] == 0:
                continue

            stack = [(x, y)]
            visited.add((x, y))
            min_x = max_x = x
            min_y = max_y = y
            area = 0

            while stack:
                px, py = stack.pop()
                area += 1
                min_x = min(min_x, px)
                max_x = max(max_x, px)
                min_y = min(min_y, py)
                max_y = max(max_y, py)

                for nx, ny in (
                    (px - 1, py),
                    (px + 1, py),
                    (px, py - 1),
                    (px, py + 1),
                ):
                    if (
                        nx < 0
                        or ny < 0
                        or nx >= width
                        or ny >= height
                        or (nx, ny) in visited
                        or pixels[nx, ny] == 0
                    ):
                        continue
                    visited.add((nx, ny))
                    stack.append((nx, ny))

            if area >= min_area:
                segments.append(
                    {
                        "bbox": [min_x, min_y, max_x - min_x + 1, max_y - min_y + 1],
                        "area": area,
                        "segment_type": "foreground",
                    }
                )

    segments.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
    return segments[:max_segments]


def _segment_image(image: Image.Image, params: dict[str, Any]) -> list[dict[str, Any]]:
    method = str(params.get("method", "foreground")).strip().lower()
    if method == "page":
        return [
            {
                "bbox": [0, 0, image.width, image.height],
                "area": image.width * image.height,
                "segment_type": "page",
            }
        ]
    if method == "foreground":
        return _foreground_segments(
            image,
            threshold=int(params.get("threshold", 28)),
            min_area=int(params.get("min_area", 100)),
            max_segments=int(params.get("max_segments", 20)),
        )
    raise HTTPException(status_code=400, detail=f"Unsupported segment method: {method}")


def _apply_saved_operations(
    db: Database, document_id: str, page: int, image: Image.Image
) -> Image.Image:
    chain = _get_chain(db, document_id)
    if not chain:
        return image

    edited = image
    for op in chain.operations:
        op_page = int(op.get("page", page))
        if op_page != page:
            continue
        edited = _apply_operation(edited, op)
    return edited


def _apply_operation(image: Image.Image, op: dict[str, Any]) -> Image.Image:
    name = str(op.get("op", "")).strip().lower()
    params = op.get("params") or {}
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail=f"Invalid params for operation: {name}")

    if name == "rotate":
        angle = float(params.get("angle", 0))
        expand = bool(params.get("expand", True))
        return image.rotate(angle, expand=expand)

    if name == "straighten":
        angle = float(params.get("angle", 0))
        expand = bool(params.get("expand", True))
        return image.rotate(angle, expand=expand)

    if name == "crop":
        auto_orient = bool(params.get("auto_orient", True))
        crop_base = ImageOps.exif_transpose(image) if auto_orient else image
        left = int(params.get("left", 0))
        top = int(params.get("top", 0))
        width = int(params.get("width", crop_base.width))
        height = int(params.get("height", crop_base.height))
        if width <= 0 or height <= 0:
            raise HTTPException(status_code=400, detail="Crop width/height must be > 0")
        right = min(left + width, crop_base.width)
        bottom = min(top + height, crop_base.height)
        if left < 0 or top < 0 or right <= left or bottom <= top:
            raise HTTPException(status_code=400, detail="Crop bounds are invalid")
        return crop_base.crop((left, top, right, bottom))

    if name == "flip_horizontal":
        return ImageOps.mirror(image)

    if name == "flip_vertical":
        return ImageOps.flip(image)

    if name == "brightness":
        factor = float(params.get("factor", 1.0))
        return ImageEnhance.Brightness(image).enhance(factor)

    if name == "contrast":
        factor = float(params.get("factor", 1.0))
        return ImageEnhance.Contrast(image).enhance(factor)

    if name == "sharpen":
        factor = float(params.get("factor", 1.0))
        return ImageEnhance.Sharpness(image).enhance(factor)

    if name == "auto_levels":
        return ImageOps.autocontrast(image)

    if name == "enhance":
        enhanced = image
        if bool(params.get("denoise", False)):
            enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))
        if bool(params.get("auto_levels", False)):
            enhanced = ImageOps.autocontrast(enhanced)
        enhanced = ImageEnhance.Brightness(enhanced).enhance(
            float(params.get("brightness", 1.0))
        )
        enhanced = ImageEnhance.Contrast(enhanced).enhance(
            float(params.get("contrast", 1.0))
        )
        enhanced = ImageEnhance.Sharpness(enhanced).enhance(
            float(params.get("sharpen", 1.0))
        )
        return enhanced

    if name == "fuzzy_clean":
        return apply_fuzzy_clean(
            image,
            despeckle_radius=int(params.get("despeckle_radius", 3)),
            background_clean=bool(params.get("background_clean", True)),
        )

    if name == "remove_background":
        return _remove_background(image, params)

    if name == "segment":
        return image

    if name == "grayscale":
        return ImageOps.grayscale(image).convert("RGB")

    raise HTTPException(status_code=400, detail=f"Unsupported operation: {name}")


def _image_response_format(image: Image.Image) -> tuple[str, str]:
    if image.mode == "RGBA" or "transparency" in image.info:
        return "PNG", "image/png"
    return "JPEG", "image/jpeg"


def _write_derived_image(document_id: str, page: int, image: Image.Image) -> str:
    image_format, _ = _image_response_format(image)
    out_dir = (
        Path(tempfile.gettempdir())
        / "fichero-image-edits"
        / document_id
        / f"page-{page}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "png" if image_format == "PNG" else "jpg"
    out_path = out_dir / f"latest.{suffix}"
    save_kwargs = {"quality": 92} if image_format == "JPEG" else {}
    image.save(out_path, format=image_format, **save_kwargs)
    return str(out_path)


def _append_operation(
    db: Database, document_id: str, operation: dict[str, Any]
) -> ImageEditChain:
    chain = _get_chain(db, document_id)
    if chain:
        chain.operations.append(operation)
        chain.updated_at = datetime.now()
    else:
        chain = ImageEditChain(document_id=document_id, operations=[operation])
    db.save(chain)
    return chain


def _create_segment_documents(
    db: Database,
    doc: Document,
    page: int,
    segments: list[dict[str, Any]],
) -> list[str]:
    child_ids: list[str] = []
    for index, segment in enumerate(segments, start=1):
        bbox = segment["bbox"]
        child = Document(
            parent_id=doc.id,
            doc_type=DocType.chunk,
            file_type=doc.file_type,
            name=f"{doc.name} segment {index}",
            path=doc.path,
            sequence=index,
            bbox=(int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])),
            metadata={
                "source_document_id": doc.id,
                "source_page": page,
                "segment_type": segment.get("segment_type", "foreground"),
                "segment_area": segment.get("area"),
                "view_kind": "image_segment",
            },
            source_authority=doc.source_authority,
            source_metadata=doc.source_metadata,
            provenance_chain=doc.provenance_chain.copy(),
            image_provenance=doc.image_provenance,
        )
        db.save(child)
        child_ids.append(child.id)
    return child_ids


# ---------------------------------------------------------------------------
# Extracted mutation logic (`*_impl`) — the proven business logic each route
# already ran, lifted into plain functions so BOTH the route handler AND the
# audited action (EPIC #1848 / #2014) drive the *same* code (iterate-not-
# replace). The action layer wraps these; it never re-derives them.
# ---------------------------------------------------------------------------


def set_operations_impl(
    db: Database, document_id: str, operations: list[dict[str, Any]]
) -> ImageEditChain:
    """Replace a document's entire edit chain (the PUT /edits body)."""
    _get_or_404_document(db, document_id)
    chain = _get_chain(db, document_id)
    if chain:
        chain.operations = operations
        chain.updated_at = datetime.now()
    else:
        chain = ImageEditChain(document_id=document_id, operations=operations)
    db.save(chain)
    return chain


def clear_operations_impl(db: Database, document_id: str) -> list[dict[str, Any]]:
    """Delete a document's edit chain. Returns the operations that were cleared
    (so the audited action can record + invert them)."""
    _get_or_404_document(db, document_id)
    chain = _get_chain(db, document_id)
    cleared = list(chain.operations) if chain else []
    if chain:
        db.delete(chain)
    return cleared


def _render_and_append(
    db: Database,
    document_id: str,
    source_path: Path,
    op: dict[str, Any],
    page: int,
) -> ImageEditChain:
    """Render ``op`` against the source image, stamp the derived preview path +
    timestamp, and append it to the chain. Shared by crop/rotate/enhance/
    remove_background so the render→append sequence lives in one place."""
    base = _load_source_image(source_path, page=page)
    derived = _apply_operation(base, op)
    op["derived_path"] = _write_derived_image(document_id, page, derived)
    op["created_at"] = datetime.now().isoformat()
    return _append_operation(db, document_id, op)


def crop_image_impl(
    db: Database, document_id: str, request: CropOperationRequest
) -> ImageEditChain:
    doc = _get_or_404_document(db, document_id)
    source_path = _resolve_source_or_404(db, doc)
    op = {
        "op": "crop",
        "page": request.page,
        "params": {
            "left": request.left,
            "top": request.top,
            "width": request.width,
            "height": request.height,
            "auto_orient": request.auto_orient,
        },
    }
    return _render_and_append(db, document_id, source_path, op, request.page)


def rotate_image_impl(
    db: Database, document_id: str, request: RotateOperationRequest
) -> ImageEditChain:
    doc = _get_or_404_document(db, document_id)
    source_path = _resolve_source_or_404(db, doc)
    op = {
        "op": "rotate",
        "page": request.page,
        "params": {"angle": request.angle, "expand": request.expand},
    }
    return _render_and_append(db, document_id, source_path, op, request.page)


def straighten_image_impl(
    db: Database, document_id: str, request: StraightenOperationRequest
) -> ImageEditChain:
    doc = _get_or_404_document(db, document_id)
    source_path = _resolve_source_or_404(db, doc)
    base = _load_source_image(source_path, page=request.page)
    angle = _estimate_straighten_angle(base)
    op = {
        "op": "straighten",
        "page": request.page,
        "params": {"angle": angle, "expand": True},
    }
    derived = _apply_operation(base, op)
    op["derived_path"] = _write_derived_image(document_id, request.page, derived)
    op["created_at"] = datetime.now().isoformat()
    return _append_operation(db, document_id, op)


def enhance_image_impl(
    db: Database, document_id: str, request: EnhanceOperationRequest
) -> ImageEditChain:
    doc = _get_or_404_document(db, document_id)
    source_path = _resolve_source_or_404(db, doc)
    op = {
        "op": "enhance",
        "page": request.page,
        "params": {
            "brightness": request.brightness,
            "contrast": request.contrast,
            "sharpen": request.sharpen,
            "auto_levels": request.auto_levels,
        },
    }
    return _render_and_append(db, document_id, source_path, op, request.page)


def remove_background_image_impl(
    db: Database, document_id: str, request: RemoveBackgroundOperationRequest
) -> ImageEditChain:
    doc = _get_or_404_document(db, document_id)
    source_path = _resolve_source_or_404(db, doc)
    op = {
        "op": "remove_background",
        "page": request.page,
        "params": {"method": request.method, "threshold": request.threshold},
    }
    return _render_and_append(db, document_id, source_path, op, request.page)


def segment_image_impl(
    db: Database, document_id: str, request: SegmentOperationRequest
) -> tuple[ImageEditChain, list[str]]:
    """Segment the (saved-edits-applied) image, create child chunk documents,
    and append the ``segment`` op. Returns ``(chain, child_document_ids)``."""
    doc = _get_or_404_document(db, document_id)
    source_path = _resolve_source_or_404(db, doc)
    base = _apply_saved_operations(
        db, document_id, request.page, _load_source_image(source_path, page=request.page)
    )
    params = {
        "method": request.method,
        "threshold": request.threshold,
        "min_area": request.min_area,
        "max_segments": request.max_segments,
    }
    segments = _segment_image(base, params)
    child_ids = _create_segment_documents(db, doc, request.page, segments)
    op = {
        "op": "segment",
        "page": request.page,
        "params": params,
        "segments": segments,
        "child_document_ids": child_ids,
    }
    op["derived_path"] = _write_derived_image(document_id, request.page, base)
    op["created_at"] = datetime.now().isoformat()
    chain = _append_operation(db, document_id, op)
    return chain, child_ids


@router.get("/{document_id}/edits", response_model=ImageEditChainResponse)
async def get_edit_chain(
    document_id: str, db: Database = Depends(get_library_database)
) -> ImageEditChainResponse:
    _get_or_404_document(db, document_id)
    chain = _get_chain(db, document_id)
    if not chain:
        return ImageEditChainResponse(
            document_id=document_id, operations=[], updated_at=datetime.now()
        )
    return ImageEditChainResponse(
        document_id=document_id,
        operations=chain.operations,
        updated_at=chain.updated_at,
    )


@router.put("/{document_id}/edits", response_model=ImageEditChainResponse)
async def put_edit_chain(
    document_id: str,
    request: ImageEditChainUpsert,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ImageEditChainResponse:
    result = await asyncio.to_thread(
        registry.invoke,
        db,
        "image.set_operations",
        {"document_id": document_id, "operations": request.operations},
        ctx,
    )
    return ImageEditChainResponse.model_validate(result.result)


@router.post("/{document_id}/operations/crop", response_model=ImageEditChainResponse)
async def crop_image(
    document_id: str,
    request: CropOperationRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ImageEditChainResponse:
    result = await asyncio.to_thread(
        registry.invoke,
        db,
        "image.crop",
        {"document_id": document_id, **request.model_dump(mode="json")},
        ctx,
    )
    return ImageEditChainResponse.model_validate(result.result)


@router.post("/{document_id}/operations/rotate", response_model=ImageEditChainResponse)
async def rotate_image(
    document_id: str,
    request: RotateOperationRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ImageEditChainResponse:
    result = await asyncio.to_thread(
        registry.invoke,
        db,
        "image.rotate",
        {"document_id": document_id, **request.model_dump(mode="json")},
        ctx,
    )
    return ImageEditChainResponse.model_validate(result.result)


@router.post("/{document_id}/operations/straighten", response_model=ImageEditChainResponse)
async def straighten_image(
    document_id: str,
    request: StraightenOperationRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ImageEditChainResponse:
    result = await asyncio.to_thread(
        registry.invoke,
        db,
        "image.straighten",
        {"document_id": document_id, **request.model_dump(mode="json")},
        ctx,
    )
    return ImageEditChainResponse.model_validate(result.result)


@router.post("/{document_id}/operations/enhance", response_model=ImageEditChainResponse)
async def enhance_image(
    document_id: str,
    request: EnhanceOperationRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ImageEditChainResponse:
    result = await asyncio.to_thread(
        registry.invoke,
        db,
        "image.enhance",
        {"document_id": document_id, **request.model_dump(mode="json")},
        ctx,
    )
    return ImageEditChainResponse.model_validate(result.result)


@router.post("/{document_id}/operations/remove-background", response_model=ImageEditChainResponse)
async def remove_background_image(
    document_id: str,
    request: RemoveBackgroundOperationRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ImageEditChainResponse:
    result = await asyncio.to_thread(
        registry.invoke,
        db,
        "image.remove_background",
        {"document_id": document_id, **request.model_dump(mode="json")},
        ctx,
    )
    return ImageEditChainResponse.model_validate(result.result)


@router.post("/{document_id}/operations/segment", response_model=ImageEditChainResponse)
async def segment_image(
    document_id: str,
    request: SegmentOperationRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ImageEditChainResponse:
    result = await asyncio.to_thread(
        registry.invoke,
        db,
        "image.segment",
        {"document_id": document_id, **request.model_dump(mode="json")},
        ctx,
    )
    return ImageEditChainResponse.model_validate(result.result)


@router.delete("/{document_id}/edits", status_code=204)
async def delete_edit_chain(
    document_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> None:
    await asyncio.to_thread(
        registry.invoke,
        db,
        "image.clear_operations",
        {"document_id": document_id},
        ctx,
    )


@router.get("/{document_id}/preview")
async def preview_image(
    document_id: str,
    apply_edits: bool = Query(
        True, description="When true, apply the saved edit chain before rendering"
    ),
    page: int = Query(1, ge=1, description="PDF page number (1-indexed)"),
    db: Database = Depends(get_library_database),
) -> Response:
    doc = _get_or_404_document(db, document_id)
    source_path = _resolve_source_or_404(db, doc)

    image = _load_source_image(source_path, page=page)
    if apply_edits:
        chain = _get_chain(db, document_id)
        if chain:
            for op in chain.operations:
                op_page = int(op.get("page", page))
                if op_page != page:
                    continue
                image = _apply_operation(image, op)

    buffer = io.BytesIO()
    image_format, media_type = _image_response_format(image)
    save_kwargs = {"quality": 92} if image_format == "JPEG" else {}
    image.save(buffer, format=image_format, **save_kwargs)
    buffer.seek(0)
    return Response(content=buffer.getvalue(), media_type=media_type)


# ---------------------------------------------------------------------------
# Action layer registration (EPIC #1848 / #2014) — image-editing mutations
# ---------------------------------------------------------------------------
#
# Every mutating image-editing route gets a registered, audited action that
# WRAPS the proven `*_impl` above (iterate-not-replace — the algorithm is the
# route's, never re-derived). The original typed routes stay untouched and
# green; the action is the *additional* uniform path that chat tools / App
# Intents / tests drive via POST /api/actions/invoke.
#
# The edit chain IS the document's image-edit state, so before/after = the op
# list. That makes the chain mutations cheaply reversible: every undoable image
# action inverts to `image.set_operations` with the *before* op list — a single
# inverse that restores whatever the chain looked like before the mutation
# (append → drop the appended op; replace → restore the old list; clear →
# restore the cleared list). `image.segment` is the exception: it also creates
# child chunk Documents, which restoring the chain would NOT delete, so it is
# undoable=False rather than offering a lying undo.

from fichero.actions.registry import action, ActionContext, ChangeSpec, registry  # noqa: E402

IMAGE_EDIT_EMIT_TYPE = "image.edits_changed"


class SetImageOperationsParams(BaseModel):
    """Params for image.set_operations — replace the whole edit chain."""

    document_id: str
    operations: list[dict[str, Any]] = Field(default_factory=list)


class ClearImageOperationsParams(BaseModel):
    """Params for image.clear_operations — delete the whole edit chain."""

    document_id: str


class CropImageActionParams(CropOperationRequest):
    document_id: str


class RotateImageActionParams(RotateOperationRequest):
    document_id: str


class StraightenImageActionParams(StraightenOperationRequest):
    document_id: str


class EnhanceImageActionParams(EnhanceOperationRequest):
    document_id: str


class RemoveBackgroundImageActionParams(RemoveBackgroundOperationRequest):
    document_id: str


class SegmentImageActionParams(SegmentOperationRequest):
    document_id: str


def _chain_ops_snapshot(db: Database, document_id: str) -> list[dict[str, Any]]:
    """A JSON-able copy of the current chain's operations (empty if no chain)."""
    chain = _get_chain(db, document_id)
    return [dict(op) for op in chain.operations] if chain else []


def _chain_payload(document_id: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
    """before/after audit payload: which document + the op list at that moment."""
    return {"document_id": document_id, "operations": operations}


def _chain_result(chain: ImageEditChain) -> dict[str, Any]:
    """ActionResult.result mirrors the route's ImageEditChainResponse shape."""
    return ImageEditChainResponse(
        document_id=chain.document_id,
        operations=chain.operations,
        updated_at=chain.updated_at,
    ).model_dump(mode="json")


def _invert_image_chain(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Inverse of any chain mutation: set_operations back to the before-list."""
    if not before:
        return None
    document_id = before.get("document_id")
    if not document_id:
        return None
    return (
        "image.set_operations",
        {"document_id": document_id, "operations": before.get("operations", [])},
    )


def _image_chain_spec(
    document_id: str,
    before_ops: list[dict[str, Any]],
    after_ops: list[dict[str, Any]],
    *,
    domains: list[str] | None = None,
    emit_type: str = IMAGE_EDIT_EMIT_TYPE,
    extra_document_ids: list[str] | None = None,
) -> ChangeSpec:
    return ChangeSpec(
        domains=domains or ["image"],
        target_ids=[document_id],
        before=_chain_payload(document_id, before_ops),
        after=_chain_payload(document_id, after_ops),
        emit_type=emit_type,
        document_ids=[document_id, *(extra_document_ids or [])],
    )


@action(
    "image.set_operations",
    SetImageOperationsParams,
    domains=["image"],
    undoable=True,
    invert=_invert_image_chain,
)
def _action_set_operations(
    db: Database, params: SetImageOperationsParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_ops = _chain_ops_snapshot(db, params.document_id)
    chain = set_operations_impl(db, params.document_id, list(params.operations))
    after_ops = [dict(op) for op in chain.operations]
    return _chain_result(chain), _image_chain_spec(
        params.document_id, before_ops, after_ops
    )


@action(
    "image.clear_operations",
    ClearImageOperationsParams,
    domains=["image"],
    undoable=True,
    invert=_invert_image_chain,
)
def _action_clear_operations(
    db: Database, params: ClearImageOperationsParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_ops = _chain_ops_snapshot(db, params.document_id)
    cleared = clear_operations_impl(db, params.document_id)
    return (
        {"document_id": params.document_id, "cleared": len(cleared)},
        _image_chain_spec(params.document_id, before_ops, []),
    )


@action(
    "image.crop",
    CropImageActionParams,
    domains=["image"],
    undoable=True,
    invert=_invert_image_chain,
)
def _action_crop(
    db: Database, params: CropImageActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_ops = _chain_ops_snapshot(db, params.document_id)
    chain = crop_image_impl(db, params.document_id, params)
    after_ops = [dict(op) for op in chain.operations]
    return _chain_result(chain), _image_chain_spec(
        params.document_id, before_ops, after_ops
    )


@action(
    "image.rotate",
    RotateImageActionParams,
    domains=["image"],
    undoable=True,
    invert=_invert_image_chain,
)
def _action_rotate(
    db: Database, params: RotateImageActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_ops = _chain_ops_snapshot(db, params.document_id)
    chain = rotate_image_impl(db, params.document_id, params)
    after_ops = [dict(op) for op in chain.operations]
    return _chain_result(chain), _image_chain_spec(
        params.document_id, before_ops, after_ops
    )


@action(
    "image.straighten",
    StraightenImageActionParams,
    domains=["image"],
    undoable=True,
    invert=_invert_image_chain,
)
def _action_straighten(
    db: Database, params: StraightenImageActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_ops = _chain_ops_snapshot(db, params.document_id)
    chain = straighten_image_impl(db, params.document_id, params)
    after_ops = [dict(op) for op in chain.operations]
    return _chain_result(chain), _image_chain_spec(
        params.document_id, before_ops, after_ops
    )


@action(
    "image.enhance",
    EnhanceImageActionParams,
    domains=["image"],
    undoable=True,
    invert=_invert_image_chain,
)
def _action_enhance(
    db: Database, params: EnhanceImageActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_ops = _chain_ops_snapshot(db, params.document_id)
    chain = enhance_image_impl(db, params.document_id, params)
    after_ops = [dict(op) for op in chain.operations]
    return _chain_result(chain), _image_chain_spec(
        params.document_id, before_ops, after_ops
    )


@action(
    "image.remove_background",
    RemoveBackgroundImageActionParams,
    domains=["image"],
    undoable=True,
    invert=_invert_image_chain,
)
def _action_remove_background(
    db: Database, params: RemoveBackgroundImageActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_ops = _chain_ops_snapshot(db, params.document_id)
    chain = remove_background_image_impl(db, params.document_id, params)
    after_ops = [dict(op) for op in chain.operations]
    return _chain_result(chain), _image_chain_spec(
        params.document_id, before_ops, after_ops
    )


@action(
    "image.segment",
    SegmentImageActionParams,
    domains=["image", "document"],
    undoable=False,
)
def _action_segment(
    db: Database, params: SegmentImageActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    # Not undoable: segment appends an op AND creates child chunk Documents.
    # Restoring the chain alone would orphan those children, so we don't pretend
    # to invert it. before/after still record the chain delta for the audit.
    before_ops = _chain_ops_snapshot(db, params.document_id)
    chain, child_ids = segment_image_impl(db, params.document_id, params)
    after_ops = [dict(op) for op in chain.operations]
    return _chain_result(chain), _image_chain_spec(
        params.document_id,
        before_ops,
        after_ops,
        domains=["image", "document"],
        emit_type="image.segmented",
        extra_document_ids=child_ids,
    )
