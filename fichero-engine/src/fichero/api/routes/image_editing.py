"""Image editing API routes (#462, #463, #466, #467).

Stores per-document non-destructive edit chains and renders previews on demand.
"""

from __future__ import annotations

import io
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from PIL import Image, ImageChops, ImageEnhance, ImageOps

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import Document, ImageEditChain
from fichero.storage import resolve_source

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
    page: int = 1


class RotateOperationRequest(BaseModel):
    angle: float
    expand: bool = True
    page: int = 1


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


def _get_or_404_document(db: Database, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
    return doc


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
        if img.mode not in ("RGB", "L", "RGBA"):
            img = img.convert("RGB")
        return img.copy()


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


def _apply_operation(image: Image.Image, op: dict[str, Any]) -> Image.Image:
    name = str(op.get("op", "")).strip().lower()
    params = op.get("params") or {}
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail=f"Invalid params for operation: {name}")

    if name == "rotate":
        angle = float(params.get("angle", 0))
        expand = bool(params.get("expand", True))
        return image.rotate(angle, expand=expand)

    if name == "crop":
        left = int(params.get("left", 0))
        top = int(params.get("top", 0))
        width = int(params.get("width", image.width))
        height = int(params.get("height", image.height))
        if width <= 0 or height <= 0:
            raise HTTPException(status_code=400, detail="Crop width/height must be > 0")
        right = min(left + width, image.width)
        bottom = min(top + height, image.height)
        if left < 0 or top < 0 or right <= left or bottom <= top:
            raise HTTPException(status_code=400, detail="Crop bounds are invalid")
        return image.crop((left, top, right, bottom))

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

    if name == "remove_background":
        return _remove_background(image, params)

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
    db: Database = Depends(get_library_database),
) -> ImageEditChainResponse:
    _get_or_404_document(db, document_id)
    chain = _get_chain(db, document_id)
    if chain:
        chain.operations = request.operations
        chain.updated_at = datetime.now()
    else:
        chain = ImageEditChain(document_id=document_id, operations=request.operations)
    db.save(chain)
    return ImageEditChainResponse(
        document_id=document_id,
        operations=chain.operations,
        updated_at=chain.updated_at,
    )


@router.post("/{document_id}/operations/crop", response_model=ImageEditChainResponse)
async def crop_image(
    document_id: str,
    request: CropOperationRequest,
    db: Database = Depends(get_library_database),
) -> ImageEditChainResponse:
    doc = _get_or_404_document(db, document_id)
    source_path = resolve_source(doc)
    if not source_path:
        raise HTTPException(status_code=404, detail="Source file not available")

    base = _load_source_image(source_path, page=request.page)
    op = {
        "op": "crop",
        "page": request.page,
        "params": {
            "left": request.left,
            "top": request.top,
            "width": request.width,
            "height": request.height,
        },
    }
    derived = _apply_operation(base, op)
    op["derived_path"] = _write_derived_image(document_id, request.page, derived)
    op["created_at"] = datetime.now().isoformat()

    chain = _append_operation(db, document_id, op)
    return ImageEditChainResponse(
        document_id=document_id,
        operations=chain.operations,
        updated_at=chain.updated_at,
    )


@router.post("/{document_id}/operations/rotate", response_model=ImageEditChainResponse)
async def rotate_image(
    document_id: str,
    request: RotateOperationRequest,
    db: Database = Depends(get_library_database),
) -> ImageEditChainResponse:
    doc = _get_or_404_document(db, document_id)
    source_path = resolve_source(doc)
    if not source_path:
        raise HTTPException(status_code=404, detail="Source file not available")

    base = _load_source_image(source_path, page=request.page)
    op = {
        "op": "rotate",
        "page": request.page,
        "params": {
            "angle": request.angle,
            "expand": request.expand,
        },
    }
    derived = _apply_operation(base, op)
    op["derived_path"] = _write_derived_image(document_id, request.page, derived)
    op["created_at"] = datetime.now().isoformat()

    chain = _append_operation(db, document_id, op)
    return ImageEditChainResponse(
        document_id=document_id,
        operations=chain.operations,
        updated_at=chain.updated_at,
    )


@router.post("/{document_id}/operations/enhance", response_model=ImageEditChainResponse)
async def enhance_image(
    document_id: str,
    request: EnhanceOperationRequest,
    db: Database = Depends(get_library_database),
) -> ImageEditChainResponse:
    doc = _get_or_404_document(db, document_id)
    source_path = resolve_source(doc)
    if not source_path:
        raise HTTPException(status_code=404, detail="Source file not available")

    base = _load_source_image(source_path, page=request.page)
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
    derived = _apply_operation(base, op)
    op["derived_path"] = _write_derived_image(document_id, request.page, derived)
    op["created_at"] = datetime.now().isoformat()

    chain = _append_operation(db, document_id, op)
    return ImageEditChainResponse(
        document_id=document_id,
        operations=chain.operations,
        updated_at=chain.updated_at,
    )


@router.post("/{document_id}/operations/remove-background", response_model=ImageEditChainResponse)
async def remove_background_image(
    document_id: str,
    request: RemoveBackgroundOperationRequest,
    db: Database = Depends(get_library_database),
) -> ImageEditChainResponse:
    doc = _get_or_404_document(db, document_id)
    source_path = resolve_source(doc)
    if not source_path:
        raise HTTPException(status_code=404, detail="Source file not available")

    base = _load_source_image(source_path, page=request.page)
    op = {
        "op": "remove_background",
        "page": request.page,
        "params": {
            "method": request.method,
            "threshold": request.threshold,
        },
    }
    derived = _apply_operation(base, op)
    op["derived_path"] = _write_derived_image(document_id, request.page, derived)
    op["created_at"] = datetime.now().isoformat()

    chain = _append_operation(db, document_id, op)
    return ImageEditChainResponse(
        document_id=document_id,
        operations=chain.operations,
        updated_at=chain.updated_at,
    )


@router.delete("/{document_id}/edits", status_code=204)
async def delete_edit_chain(
    document_id: str, db: Database = Depends(get_library_database)
) -> None:
    _get_or_404_document(db, document_id)
    chain = _get_chain(db, document_id)
    if chain:
        db.delete(chain)


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
    source_path = resolve_source(doc)
    if not source_path:
        raise HTTPException(status_code=404, detail="Source file not available")

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
