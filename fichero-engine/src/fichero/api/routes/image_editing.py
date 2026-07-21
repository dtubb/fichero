"""Image editing API routes (#462, #463, #466, #467, #468).

Stores per-document non-destructive edit chains and renders previews on demand.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, ValidationError, field_validator

if TYPE_CHECKING:
    # Type-only: PIL is imported lazily in the render helpers (#3985), but the
    # `Image.Image` annotations still need the name to resolve for type checkers.
    from PIL import Image

from fichero.api.auth import action_context
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.api.routes.batch import BatchResponse, get_batch_manager
from fichero.api.routes.documents import _descendant_document_ids
from fichero.db import Database
from fichero.models import DocType, Document, FileType, ImageEditChain
from fichero.workflows.batch import BatchItemStatus, BatchStatus
from fichero.db.storage import resolve_source
# NOTE: apply_operation is imported inside the functions that render (#3985) and
# apply_fuzzy_clean inside the one handler that uses it
# (#3950). Importing any module in the tools package runs tools/__init__.py,
# which imports every tool and with them Quartz, MCP and langgraph.

router = APIRouter(prefix="/images", tags=["images"])


class ImageEditChainUpsert(BaseModel):
    operations: list[dict[str, Any]] = Field(default_factory=list)


class ImageEditChainResponse(BaseModel):
    document_id: str
    operations: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime


class CropOperationRequest(BaseModel):
    left: int = Field(ge=0)
    top: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    auto_orient: bool = True
    page: int = Field(1, ge=1)


class RotateOperationRequest(BaseModel):
    angle: float = Field(ge=-360.0, le=360.0)
    expand: bool = True
    page: int = Field(1, ge=1)


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


class FactorOperationRequest(BaseModel):
    factor: float = Field(1.0, ge=0.0, le=10.0)
    page: int = Field(1, ge=1)


class FuzzyCleanOperationRequest(BaseModel):
    despeckle_radius: int = Field(3, ge=1, le=25)
    background_clean: bool = True
    page: int = Field(1, ge=1)


class DenoiseOperationRequest(BaseModel):
    radius: int = Field(3, ge=3, le=5)
    page: int = Field(1, ge=1)


_OPERATION_MODELS = {
    "crop": CropOperationRequest, "rotate": RotateOperationRequest,
    "straighten": StraightenOperationRequest, "enhance": EnhanceOperationRequest,
    "remove_background": RemoveBackgroundOperationRequest, "segment": SegmentOperationRequest,
    "brightness": FactorOperationRequest, "contrast": FactorOperationRequest,
    "sharpen": FactorOperationRequest, "fuzzy_clean": FuzzyCleanOperationRequest,
    "denoise": DenoiseOperationRequest,
}
_PARAMETERLESS_OPERATIONS = {"flip_horizontal", "flip_vertical", "auto_levels", "grayscale", "auto_crop_border", "adaptive_binarize"}


def _validate_operations(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reject malformed edit chains before they become persisted state."""
    clean: list[dict[str, Any]] = []
    for operation in operations:
        name = str(operation.get("op", "")).strip().lower()
        params = operation.get("params", {})
        if not isinstance(params, dict):
            raise HTTPException(422, f"Invalid params for operation: {name or 'missing'}")
        model = _OPERATION_MODELS.get(name)
        if model is None and name not in _PARAMETERLESS_OPERATIONS:
            raise HTTPException(422, f"Unsupported image operation: {name or 'missing'}")
        try:
            if model is not None:
                model.model_validate({**params, "page": operation.get("page", 1)})
        except ValidationError as exc:
            raise HTTPException(422, detail=exc.errors()) from exc
        clean.append({key: value for key, value in operation.items() if key != "derived_path"})
    return clean


class ImageSplitRequest(BaseModel):
    """Explicit source-image regions to expose as reversible child nodes."""

    bboxes: list[tuple[int, int, int, int]] | None = None

    @field_validator("bboxes")
    @classmethod
    def validate_bboxes(
        cls, bboxes: list[tuple[int, int, int, int]] | None
    ) -> list[tuple[int, int, int, int]] | None:
        if bboxes is None:
            return bboxes
        if not bboxes:
            raise ValueError("at least one bbox is required")
        for x, y, width, height in bboxes:
            if x < 0 or y < 0 or width <= 0 or height <= 0:
                raise ValueError("bbox coordinates must be non-negative with positive width and height")
        for index, (x, y, width, height) in enumerate(bboxes):
            for other_x, other_y, other_width, other_height in bboxes[index + 1 :]:
                if x < other_x + other_width and other_x < x + width and y < other_y + other_height and other_y < y + height:
                    raise ValueError("split bboxes must not overlap")
        return bboxes


class ImageSplitResponse(BaseModel):
    source_document_id: str
    children: list[Document]


class ImageUnsplitResponse(BaseModel):
    source_document_id: str
    deleted_child_ids: list[str]


class ImageBatchCropRequest(CropOperationRequest):
    document_ids: list[str] = Field(min_length=1)


class ImageCropResponse(BaseModel):
    source_document_id: str
    child: Document


class ImageBatchCropResponse(BaseModel):
    children: list[ImageCropResponse]


class BatchImageApplyRequest(BaseModel):
    folder_id: str
    operation: Literal["crop", "split"]
    bbox: tuple[int, int, int, int] | None = None
    bboxes: list[tuple[int, int, int, int]] | None = None


class BatchImageUndoResponse(BaseModel):
    batch_id: str
    deleted_child_ids: list[str]


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
    from PIL import Image, ImageOps  # lazy (#3985): keep PIL off the engine boot path

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


def _remove_black_background_opencv(image: Image.Image) -> Image.Image:
    """Port the archive contour-mask and crop path for black scanner borders."""
    from PIL import Image  # lazy (#3985): keep PIL off the engine boot path
    import cv2  # type: ignore[import-not-found]
    import numpy as np

    rgb = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if np.count_nonzero(gray < 80) / gray.size < 0.01:
        return image.convert("RGBA")
    _, binary = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image.convert("RGBA")
    areas = [cv2.contourArea(contour) for contour in contours]
    largest = max(areas)
    mask = np.zeros_like(binary)
    for contour, area in zip(contours, areas):
        if area >= largest * 0.2:
            cv2.drawContours(mask, [contour], -1, 255, thickness=-1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    mask = cv2.GaussianBlur(mask, (21, 21), 0)
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return image.convert("RGBA")
    rgba = image.convert("RGBA")
    rgba.putalpha(Image.fromarray(mask))
    return rgba.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def _remove_background(image: Image.Image, params: dict[str, Any]) -> Image.Image:
    from PIL import Image, ImageChops  # lazy (#3985): keep PIL off the engine boot path

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
            del cv2, np
            return _remove_black_background_opencv(image)

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
    from PIL import Image, ImageChops  # lazy (#3985): keep PIL off the engine boot path

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
    # lazy (#3985): keep PIL and image_ops (which imports PIL) off the boot path.
    # The PIL names are used by the source-compatibility branch kept below the
    # early return.
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    from fichero.image_ops import apply_operation

    return apply_operation(image, op)

    # Kept below temporarily for source compatibility while operations move to
    # fichero.image_ops; the return above is the sole runtime path.
    name = str(op.get("op", "")).strip().lower()
    params = op.get("params") or {}
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail=f"Invalid params for operation: {name}")

    if name == "rotate":
        angle = float(params.get("angle", 0))
        expand = bool(params.get("expand", True))
        return image.rotate(angle, expand=expand, resample=Image.Resampling.BICUBIC, fillcolor="white")

    if name == "straighten":
        angle = float(params.get("angle", 0))
        expand = bool(params.get("expand", True))
        return image.rotate(angle, expand=expand, resample=Image.Resampling.BICUBIC, fillcolor="white")

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
        # Imported here rather than at module scope: runs tools/__init__ (#3950).
        from fichero.workflows.tools.fuzzy_clean_images import apply_fuzzy_clean

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


def _render_preview(
    db: Database, document_id: str, apply_edits: bool, page: int
) -> tuple[bytes, str]:
    """Render one preview in a worker thread; cached renders are disposable."""
    from fichero.image_ops import apply_operation  # lazy (#3985): keep PIL off the boot path

    doc = _get_or_404_document(db, document_id)
    chain = _get_chain(db, document_id) if apply_edits else None
    version = chain.updated_at.isoformat() if chain else "raw"
    key = hashlib.sha256(f"{document_id}:{page}:{apply_edits}:{version}".encode()).hexdigest()
    preview_dir = db.path.parent / "storage" / "preview-cache" / document_id / f"page-{page}"
    cache_path = preview_dir / f"{key}.bin"
    media_path = preview_dir / f"{key}.type"
    if cache_path.exists() and media_path.exists():
        return cache_path.read_bytes(), media_path.read_text()

    image = _load_source_image(_resolve_source_or_404(db, doc), page=page)
    if chain:
        for op in chain.operations:
            if int(op.get("page", page)) == page:
                image = apply_operation(image, op)
    buffer = io.BytesIO()
    image_format, media_type = _image_response_format(image)
    image.save(buffer, format=image_format, **({"quality": 92} if image_format == "JPEG" else {}))
    preview_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(buffer.getvalue())
    media_path.write_text(media_type)
    # ponytail: four revisions/page; increase only if users visibly revisit more history.
    for stale in sorted(preview_dir.glob("*.bin"), key=lambda path: path.stat().st_mtime, reverse=True)[4:]:
        stale.unlink(missing_ok=True)
        stale.with_suffix(".type").unlink(missing_ok=True)
    return buffer.getvalue(), media_type


def _append_operation(
    db: Database, document_id: str, operation: dict[str, Any]
) -> ImageEditChain:
    operation.pop("derived_path", None)
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


def _split_children(db: Database, source_id: str) -> list[Document]:
    return [
        document
        for document in db.query(Document, parent_id=source_id)
        if document.deleted_at is None
        and isinstance(document.metadata, dict)
        and document.metadata.get("split_source_id") == source_id
    ]


def _archive_split_bboxes(image: Image.Image) -> list[tuple[int, int, int, int]]:
    """Port the archive OpenCV centre-gutter detector as non-destructive regions."""
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np
    except ImportError as exc:
        raise HTTPException(status_code=501, detail="OpenCV is required for auto split") from exc

    width, height = image.size
    aspect_ratio = width / height
    if aspect_ratio < 1.2 or width < 1000:
        raise HTTPException(status_code=422, detail="Image is not a split-page candidate")

    gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    centre = width // 2
    deviation = int(width * (0.1 if aspect_ratio > 1.6 else 0.2))
    start, end = centre - deviation, centre + deviation
    column_means = gray.mean(axis=0)
    split_x = start + int(np.argmin(column_means[start:end]))
    neighbours = np.concatenate(
        (column_means[max(start, split_x - 3) : split_x], column_means[split_x + 1 : min(end, split_x + 4)])
    )
    darkness_difference = float(neighbours.mean() - column_means[split_x]) if len(neighbours) else 0.0
    if darkness_difference <= (5.0 if aspect_ratio > 1.65 else 8.0):
        raise HTTPException(status_code=422, detail="No archive-style page gutter detected")
    return [(0, 0, split_x, height), (split_x, 0, width - split_x, height)]


def split_image_impl(
    db: Database, source_id: str, request: ImageSplitRequest
) -> list[Document]:
    """Create region child nodes without modifying the source image."""
    source = _get_or_404_document(db, source_id)
    if _split_children(db, source.id):
        raise HTTPException(status_code=409, detail="Source image already has split children")

    bboxes = request.bboxes
    if bboxes is None:
        source_path = _resolve_source_or_404(db, source)
        bboxes = _archive_split_bboxes(_load_source_image(source_path))

    children: list[Document] = []
    for index, bbox in enumerate(bboxes, start=1):
        child = Document(
            parent_id=source.id,
            doc_type=DocType.chunk,
            file_type=source.file_type,
            name=f"{source.name} region {index}",
            path=source.path,
            sequence=index,
            bbox=bbox,
            metadata={
                "derived_from": source.id,
                "split_source_id": source.id,
                "source_bbox": list(bbox),
                "view_kind": "image_region",
            },
            source_authority=source.source_authority,
            source_metadata=source.source_metadata,
            provenance_chain=source.provenance_chain.copy(),
            image_provenance=source.image_provenance,
        )
        db.save(child)
        children.append(child)
    return children


def unsplit_image_impl(db: Database, source_id: str) -> list[Document]:
    """Soft-delete only the derived region children, preserving their source."""
    _get_or_404_document(db, source_id)
    children = _split_children(db, source_id)
    if not children:
        raise HTTPException(status_code=404, detail="Source image has no split children")
    deleted_at = datetime.now()
    for child in children:
        child.deleted_at = deleted_at
        child.updated_at = deleted_at
        db.save(child)
    return children


def _validate_crop_bounds(db: Database, source_id: str, request: CropOperationRequest) -> Document:
    source = _get_or_404_document(db, source_id)
    image = _load_source_image(_resolve_source_or_404(db, source), page=request.page)
    if (
        request.left < 0
        or request.top < 0
        or request.width <= 0
        or request.height <= 0
        or request.left + request.width > image.width
        or request.top + request.height > image.height
    ):
        raise HTTPException(status_code=422, detail="Crop bbox is outside source image bounds")
    return source


def crop_image_child_impl(
    db: Database, source_id: str, request: CropOperationRequest
) -> Document:
    """Reuse the crop edit-chain on a derived child, never on its source."""
    source = _validate_crop_bounds(db, source_id, request)
    bbox = (request.left, request.top, request.width, request.height)
    child = Document(
        parent_id=source.id,
        doc_type=DocType.chunk,
        file_type=source.file_type,
        name=f"{source.name} crop",
        path=source.path,
        bbox=bbox,
        metadata={
            "derived_from": source.id,
            "crop_source_id": source.id,
            "source_bbox": list(bbox),
            "view_kind": "image_crop",
        },
        source_authority=source.source_authority,
        source_metadata=source.source_metadata,
        provenance_chain=source.provenance_chain.copy(),
        image_provenance=source.image_provenance,
    )
    db.save(child)
    crop_image_impl(db, child.id, request)
    return child


def _folder_images(db: Database, folder_id: str) -> list[Document]:
    folder = _get_or_404_document(db, folder_id)
    if folder.doc_type != DocType.folder:
        raise HTTPException(status_code=422, detail="Batch source must be a folder")
    ids = _descendant_document_ids(db, folder.id)
    return [
        document
        for document_id in ids
        if (document := db.get(Document, document_id))
        and document.deleted_at is None
        and document.file_type == FileType.image
    ]


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
    operations = _validate_operations(operations)
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


@router.post("/batch-apply", response_model=BatchResponse)
async def batch_apply_image_operation(
    request: BatchImageApplyRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> BatchResponse:
    """Apply one reversible crop or split spec to every image under a folder."""
    images = _folder_images(db, request.folder_id)
    if not images:
        raise HTTPException(status_code=422, detail="Folder has no image documents")
    if request.operation == "crop":
        if request.bbox is None:
            raise HTTPException(status_code=422, detail="Crop batch requires bbox")
        operation_request: CropOperationRequest | ImageSplitRequest = CropOperationRequest(
            left=request.bbox[0], top=request.bbox[1], width=request.bbox[2], height=request.bbox[3]
        )
    else:
        operation_request = ImageSplitRequest(bboxes=request.bboxes)

    inputs = [
        {"source_id": image.id, "operation": request.operation, "child_ids": []}
        for image in images
    ]
    created = await asyncio.to_thread(
        registry.invoke,
        db,
        "batch.create",
        {"workflow_id": "image.batch_apply", "items": inputs, "max_concurrent": 1},
        ctx,
    )
    manager = get_batch_manager()
    batch = await manager.get_batch(created.result["batch_id"])
    if batch is None:
        raise HTTPException(status_code=500, detail="Batch persistence failed")
    batch.status = BatchStatus.RUNNING
    batch.started_at = datetime.now(timezone.utc)
    manager.activity_tracker.batch_started(
        batch_id=batch.batch_id,
        workflow_id=batch.workflow_id,
        total_items=batch.total_items,
        max_concurrent=batch.max_concurrent,
    )

    for item, image in zip(batch.items, images, strict=True):
        item.status = BatchItemStatus.RUNNING
        item.started_at = datetime.now(timezone.utc)
        manager.activity_tracker.batch_item_started(
            batch_id=batch.batch_id,
            thread_id=item.thread_id,
            item_index=item.item_index,
            workflow_id=batch.workflow_id,
        )
        try:
            action_name = "image.crop_child" if request.operation == "crop" else "image.split"
            result = await asyncio.to_thread(
                registry.invoke,
                db,
                action_name,
                {
                    "source_id": image.id,
                    **operation_request.model_dump(mode="json"),
                },
                ctx,
            )
            item.inputs["child_ids"] = (
                [result.result["child"]["id"]]
                if request.operation == "crop"
                else [child["id"] for child in result.result["children"]]
            )
            item.status = BatchItemStatus.COMPLETED
            item.completed_at = datetime.now(timezone.utc)
            manager.activity_tracker.batch_item_completed(
                batch_id=batch.batch_id,
                thread_id=item.thread_id,
                item_index=item.item_index,
                duration_ms=0,
                workflow_id=batch.workflow_id,
            )
        except Exception as exc:
            item.status = BatchItemStatus.FAILED
            item.error = str(exc)
            item.completed_at = datetime.now(timezone.utc)
            manager.activity_tracker.batch_item_failed(
                batch_id=batch.batch_id,
                thread_id=item.thread_id,
                item_index=item.item_index,
                error=item.error,
                workflow_id=batch.workflow_id,
            )
        await manager._save_batch(batch)

    batch.status = (
        BatchStatus.PARTIAL_FAILURE
        if batch.failed_items and batch.completed_items
        else BatchStatus.FAILED
        if batch.failed_items
        else BatchStatus.COMPLETED
    )
    batch.completed_at = datetime.now(timezone.utc)
    await manager._save_batch(batch)
    manager.activity_tracker.batch_completed(
        batch_id=batch.batch_id,
        workflow_id=batch.workflow_id,
        total_items=batch.total_items,
        completed_items=batch.completed_items,
        failed_items=batch.failed_items,
        duration_ms=0,
        status=batch.status.value,
    )
    return BatchResponse.from_batch(batch, include_items=True)


@router.post("/batch-apply/{batch_id}/undo", response_model=BatchImageUndoResponse)
async def undo_batch_image_operation(
    batch_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> BatchImageUndoResponse:
    """Reverse every completed derived child recorded by an image batch."""
    batch = await get_batch_manager().get_batch(batch_id)
    if batch is None or batch.workflow_id != "image.batch_apply":
        raise HTTPException(status_code=404, detail="Image batch not found")
    child_ids = [
        child_id
        for item in batch.items
        for child_id in item.inputs.get("child_ids", [])
    ]
    for child_id in child_ids:
        child = db.get(Document, child_id)
        if child and child.deleted_at is None:
            await asyncio.to_thread(
                registry.invoke, db, "document.delete", {"doc_id": child_id}, ctx
            )
    return BatchImageUndoResponse(batch_id=batch_id, deleted_child_ids=child_ids)


@router.post("/crops/batch", response_model=ImageBatchCropResponse)
async def batch_crop_images(
    request: ImageBatchCropRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ImageBatchCropResponse:
    """Apply one crop region to many images as independent derived children."""
    source_ids = list(dict.fromkeys(request.document_ids))
    for source_id in source_ids:
        _validate_crop_bounds(db, source_id, request)
    children = []
    for source_id in source_ids:
        result = await asyncio.to_thread(
            registry.invoke,
            db,
            "image.crop_child",
            {"source_id": source_id, **request.model_dump(mode="json")},
            ctx,
        )
        children.append(ImageCropResponse.model_validate(result.result))
    return ImageBatchCropResponse(children=children)


@router.post("/{document_id}/crop", response_model=ImageCropResponse)
async def crop_image_child(
    document_id: str,
    request: CropOperationRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ImageCropResponse:
    """Crop an image into a non-destructive derived child node."""
    result = await asyncio.to_thread(
        registry.invoke,
        db,
        "image.crop_child",
        {"source_id": document_id, **request.model_dump(mode="json")},
        ctx,
    )
    return ImageCropResponse.model_validate(result.result)


@router.post("/{document_id}/uncrop", response_model=ImageCropResponse)
async def uncrop_image_child(
    document_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ImageCropResponse:
    """Soft-delete one crop child through the existing reversible document action."""
    child = _get_or_404_document(db, document_id)
    source_id = (child.metadata or {}).get("crop_source_id")
    if not source_id:
        raise HTTPException(status_code=404, detail="Crop child not found")
    await asyncio.to_thread(registry.invoke, db, "document.delete", {"doc_id": child.id}, ctx)
    return ImageCropResponse(source_document_id=source_id, child=child)


@router.post("/{document_id}/split", response_model=ImageSplitResponse)
async def split_image(
    document_id: str,
    request: ImageSplitRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ImageSplitResponse:
    """Create non-destructive derived region children for an image source."""
    result = await asyncio.to_thread(
        registry.invoke,
        db,
        "image.split",
        {"source_id": document_id, **request.model_dump(mode="json")},
        ctx,
    )
    return ImageSplitResponse.model_validate(result.result)


@router.post("/{document_id}/unsplit", response_model=ImageUnsplitResponse)
async def unsplit_image(
    document_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ImageUnsplitResponse:
    """Reverse a split by soft-deleting its derived children only."""
    result = await asyncio.to_thread(
        registry.invoke,
        db,
        "image.unsplit",
        {"source_id": document_id},
        ctx,
    )
    return ImageUnsplitResponse.model_validate(result.result)


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
    content, media_type = await asyncio.to_thread(
        _render_preview, db, document_id, apply_edits, page
    )
    return Response(content=content, media_type=media_type)


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


class SplitImageActionParams(ImageSplitRequest):
    source_id: str


class UnsplitImageActionParams(BaseModel):
    source_id: str


class CropChildActionParams(CropOperationRequest):
    source_id: str


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


def _invert_unsplit_image(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return ("document.restore", {"documents": before.get("children", [])})


@action(
    "image.split",
    SplitImageActionParams,
    domains=["image", "document"],
    undoable=True,
    invert=lambda _before, after, _ctx: (
        ("image.unsplit", {"source_id": after["source_id"]}) if after else None
    ),
)
def _action_split_image(
    db: Database, params: SplitImageActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    children = split_image_impl(db, params.source_id, params)
    result = ImageSplitResponse(source_document_id=params.source_id, children=children)
    return result.model_dump(mode="json"), ChangeSpec(
        domains=["image", "document"],
        target_ids=[params.source_id, *[child.id for child in children]],
        after={"source_id": params.source_id, "child_ids": [child.id for child in children]},
        emit_type="image.split",
        document_ids=[params.source_id, *[child.id for child in children]],
    )


@action(
    "image.unsplit",
    UnsplitImageActionParams,
    domains=["image", "document"],
    undoable=True,
    invert=_invert_unsplit_image,
)
def _action_unsplit_image(
    db: Database, params: UnsplitImageActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    snapshots = [
        child.model_dump(mode="json") for child in _split_children(db, params.source_id)
    ]
    children = unsplit_image_impl(db, params.source_id)
    result = ImageUnsplitResponse(
        source_document_id=params.source_id,
        deleted_child_ids=[child.id for child in children],
    )
    return result.model_dump(mode="json"), ChangeSpec(
        domains=["image", "document"],
        target_ids=[params.source_id, *result.deleted_child_ids],
        before={"children": snapshots},
        emit_type="image.unsplit",
        document_ids=[params.source_id, *result.deleted_child_ids],
    )


@action(
    "image.crop_child",
    CropChildActionParams,
    domains=["image", "document"],
    undoable=True,
    invert=lambda _before, after, _ctx: (
        ("document.delete", {"doc_id": after["child_id"]}) if after else None
    ),
)
def _action_crop_image_child(
    db: Database, params: CropChildActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    child = crop_image_child_impl(db, params.source_id, params)
    result = ImageCropResponse(source_document_id=params.source_id, child=child)
    return result.model_dump(mode="json"), ChangeSpec(
        domains=["image", "document"],
        target_ids=[params.source_id, child.id],
        after={"child_id": child.id},
        emit_type="image.cropped",
        document_ids=[params.source_id, child.id],
    )
