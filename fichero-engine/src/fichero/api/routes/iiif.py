"""IIIF API Routes (dev tier, backend-first 0.1.0 slice).

Embedded IIIF Image Server API — serves local images via IIIF Image API v2.1.
References: https://iiif.io/api/image/2.1/
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from PIL import Image

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import Document, FileType
from fichero.storage import _path_within, get_display, get_thumbnail, resolve_source

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/iiif", tags=["iiif"])


# =============================================================================
# IIIF Constants
# =============================================================================

IIIF_API_VERSION = "2.1"
IIIF_CONTEXT = "http://iiif.io/api/image/2/context.json"


# =============================================================================
# IIIF Image Information Response
# =============================================================================


class ImageServiceProfile(BaseModel):
    """IIIF Image API service profile."""

    formats: list[str] = Field(default_factory=lambda: ["jpg", "png"])
    qualities: list[str] = Field(default_factory=lambda: ["default", "color", "gray"])
    supports: list[str] = Field(default_factory=list)


class ImageInfoResponse(BaseModel):
    """IIIF Image Information Response (info.json)."""

    model_config = ConfigDict(populate_by_name=True)

    context: str = IIIF_CONTEXT
    id: str = Field(..., alias="@id")
    protocol: str = "http://iiif.io/api/image"
    width: int
    height: int
    tiles: list[dict[str, Any]] | None = None
    profile: list[Any] = Field(default_factory=list)


# =============================================================================
# IIIF Manifest Models
# =============================================================================


class IIIFCanvas(BaseModel):
    """IIIF Canvas for presentation."""

    id: str
    type: str = "Canvas"
    label: str
    width: int
    height: int
    items: list[dict[str, Any]] = Field(default_factory=list)


class IIIFManifest(BaseModel):
    """IIIF Presentation API Manifest."""

    model_config = ConfigDict(populate_by_name=True)

    context: str = "http://iiif.io/api/presentation/2/context.json"
    id: str = Field(..., alias="@id")
    type: str = "sc:Manifest"
    label: str
    description: str | None = None
    sequences: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# Helper Functions
# =============================================================================


def _get_image_path(
    doc: Document, library_root: Path | None = None
) -> Path | None:
    """Get the image file path for a document."""
    if doc.file_type not in (FileType.image, FileType.pdf) and not doc.path:
        return None

    image_path = (
        get_display(doc, package_path=library_root)
        or get_thumbnail(doc, package_path=library_root)
        or resolve_source(doc, library_root=library_root)
    )
    if image_path is None:
        return None
    if library_root is not None and not _path_within(library_root, image_path):
        logger.warning("Refusing IIIF image path outside library root: %s", image_path)
        return None
    return image_path


def _get_image_dimensions(image_path: Path) -> tuple[int, int]:
    """Get image dimensions."""
    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception as exc:
        logger.error(f"Failed to get image dimensions: {exc}")
        return (1024, 1024)  # Default fallback


def _document_or_404(db: Database, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or getattr(doc, "deleted_at", None) is not None:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
    return doc


def _serve_iiif_image(
    image_path: Path,
    region: str,
    size: str,
    rotation: str,
    quality: str,
    fmt: str,
) -> Response:
    """Serve a IIIF image region."""
    try:
        with Image.open(image_path) as img:
            width, height = img.size

            # Handle region (simplified: "full" or "x,y,w,h")
            if region == "full":
                crop_box = (0, 0, width, height)
            elif "," in region:
                try:
                    x, y, w, h = [int(v) for v in region.split(",")]
                    crop_box = (x, y, x + w, y + h)
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid region: {region}")
            else:
                crop_box = (0, 0, width, height)

            # Handle size (simplified: "full" or "w," or ",h" or "w,h")
            if size == "full":
                new_size = (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1])
            elif "," in size:
                parts = size.split(",")
                if parts[0]:
                    new_w = int(parts[0])
                    new_h = int(new_w * (crop_box[3] - crop_box[1]) / (crop_box[2] - crop_box[0]))
                    new_size = (new_w, new_h)
                elif parts[1]:
                    new_h = int(parts[1])
                    new_w = int(new_h * (crop_box[2] - crop_box[0]) / (crop_box[3] - crop_box[1]))
                    new_size = (new_w, new_h)
                else:
                    new_size = (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1])
            else:
                try:
                    new_size = (int(size), int(size))
                except ValueError:
                    new_size = (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1])

            # Handle rotation
            try:
                angle = int(rotation)
            except ValueError:
                angle = 0

            # Handle quality
            if quality == "gray":
                img = img.convert("L").convert("RGB")
            elif quality in ("default", "color"):
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

            # Apply transformations
            img = img.crop(crop_box)
            if angle != 0:
                img = img.rotate(angle, expand=True)
            if new_size != img.size:
                img = img.resize(new_size, Image.LANCZOS)

            # Output format
            fmt_upper = fmt.upper()
            if fmt_upper not in ("JPEG", "PNG", "WEBP"):
                fmt_upper = "JPEG"

            buffer = io.BytesIO()
            img.save(buffer, format=fmt_upper)
            buffer.seek(0)

            fmt_lower = fmt.lower()
            media_type = f"image/{fmt_lower}"
            if fmt_lower == "jpg":
                media_type = "image/jpeg"

            return Response(content=buffer.getvalue(), media_type=media_type)

    except Exception as exc:
        logger.error(f"IIIF image processing failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Image processing failed: {exc}")


# =============================================================================
# IIIF API Endpoints
# =============================================================================


@router.get(
    "/{identifier}/info.json",
    response_model=ImageInfoResponse,
    summary="IIIF Image Information",
    description="Returns IIIF Image API information (info.json).",
)
async def get_image_info(
    identifier: str,
    db: Database = Depends(get_library_database),
) -> ImageInfoResponse:
    """Get IIIF image information."""
    doc = _document_or_404(db, identifier)

    image_path = _get_image_path(doc, db.path.parent)
    if not image_path:
        raise HTTPException(
            status_code=404, detail=f"No image available for document: {identifier}"
        )

    width, height = _get_image_dimensions(image_path)

    # Build base URL
    base_url = f"/api/iiif/{identifier}"

    return ImageInfoResponse(
        context=IIIF_CONTEXT,
        id=base_url,
        protocol="http://iiif.io/api/image",
        width=width,
        height=height,
        tiles=[
            {"width": 256, "height": 256, "scaleFactors": [1, 2, 4, 8]}
        ],
        profile=[
            "http://iiif.io/api/image/2/level1.json",
            {
                "formats": ["jpg", "png"],
                "qualities": ["default", "color", "gray"],
                "supports": [
                    "regionByPx",
                    "sizeByW",
                    "sizeByH",
                    "sizeByWh",
                ],
            },
        ],
    )


@router.get(
    "/{identifier}/{region}/{size}/{rotation}/{quality}.{format}",
    summary="IIIF Image Request",
    description="Serve image region via IIIF Image API. Reference: https://iiif.io/api/image/2.1/",
)
async def serve_iiif_image(
    identifier: str,
    region: str,
    size: str,
    rotation: str,
    quality: str,
    format: str,
    db: Database = Depends(get_library_database),
) -> Response:
    """Serve IIIF image tile/region."""
    doc = _document_or_404(db, identifier)

    image_path = _get_image_path(doc, db.path.parent)
    if not image_path:
        raise HTTPException(
            status_code=404, detail=f"No image available for document: {identifier}"
        )

    fmt_lower = format.lower()
    if fmt_lower == "jpg":
        fmt_lower = "jpeg"

    return _serve_iiif_image(image_path, region, size, rotation, quality, fmt_lower)


@router.get(
    "/manifest/{document_id}",
    response_model=IIIFManifest,
    summary="IIIF Manifest",
    description="Returns IIIF Presentation API manifest for document.",
)
async def get_iiif_manifest(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> IIIFManifest:
    """Get IIIF manifest for document."""
    doc = _document_or_404(db, document_id)

    image_path = _get_image_path(doc, db.path.parent)
    if not image_path:
        raise HTTPException(
            status_code=404, detail=f"No image available for document: {document_id}"
        )

    width, height = _get_image_dimensions(image_path)

    # Build manifest
    base_url = f"/api/iiif/{document_id}"
    manifest_url = f"/api/iiif/manifest/{document_id}"

    canvas = IIIFCanvas(
        id=f"{base_url}/canvas/1",
        label=doc.name or "Canvas 1",
        width=width,
        height=height,
        items=[
            {
                "type": "AnnotationPage",
                "items": [
                    {
                        "type": "Annotation",
                        "motivation": "painting",
                        "body": {
                            "type": "Image",
                            "id": f"{base_url}/full/full/0/default.jpg",
                            "format": "image/jpeg",
                            "width": width,
                            "height": height,
                            "service": {
                                "type": "ImageService2",
                                "profile": "http://iiif.io/api/image/2/level1.json",
                                "id": base_url,
                            },
                        },
                        "target": f"{base_url}/canvas/1",
                    }
                ],
            }
        ],
    )

    sequence = {
        "type": "Sequence",
        "canvases": [canvas.model_dump()],
    }

    return IIIFManifest(
        context="http://iiif.io/api/presentation/2/context.json",
        id=manifest_url,
        label=doc.name or "Untitled",
        description=doc.description,
        sequences=[sequence],
    )


@router.get(
    "/image/{document_id}",
    summary="Direct Image Access",
    description="Direct access to document image (non-IIIF, for convenience).",
)
async def get_document_image(
    document_id: str,
    width: int | None = Query(default=None, ge=50, le=4096),
    height: int | None = Query(default=None, ge=50, le=4096),
    db: Database = Depends(get_library_database),
) -> Response:
    """Get document image with optional resize."""
    doc = _document_or_404(db, document_id)

    image_path = _get_image_path(doc, db.path.parent)
    if not image_path:
        raise HTTPException(
            status_code=404, detail=f"No image available for document: {document_id}"
        )

    # If no resize requested, return original
    if width is None and height is None:
        return FileResponse(image_path)

    # Resize requested
    try:
        with Image.open(image_path) as img:
            orig_width, orig_height = img.size

            # Calculate new size
            if width and height:
                new_size = (width, height)
            elif width:
                ratio = width / orig_width
                new_size = (width, int(orig_height * ratio))
            else:  # height
                ratio = height / orig_height
                new_size = (int(orig_width * ratio), height)

            img = img.resize(new_size, Image.LANCZOS)

            buffer = io.BytesIO()
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(buffer, format="JPEG")
            buffer.seek(0)

            return Response(content=buffer.getvalue(), media_type="image/jpeg")

    except Exception as exc:
        logger.error(f"Image resize failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Image processing failed: {exc}")
