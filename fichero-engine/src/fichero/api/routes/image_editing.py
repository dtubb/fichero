"""Image editing API routes (#462, #463).

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
from PIL import Image, ImageEnhance, ImageOps

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
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        return img.copy()


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

    if name == "grayscale":
        return ImageOps.grayscale(image).convert("RGB")

    raise HTTPException(status_code=400, detail=f"Unsupported operation: {name}")


def _write_derived_image(document_id: str, page: int, image: Image.Image) -> str:
    out_dir = (
        Path(tempfile.gettempdir())
        / "fichero-image-edits"
        / document_id
        / f"page-{page}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "latest.jpg"
    image.save(out_path, format="JPEG", quality=92)
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
    image.save(buffer, format="JPEG", quality=92)
    buffer.seek(0)
    return Response(content=buffer.getvalue(), media_type="image/jpeg")
