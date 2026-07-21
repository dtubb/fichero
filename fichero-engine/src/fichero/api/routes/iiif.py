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

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import Annotation, AnnotationKind
from fichero.models import Document, FileType
from fichero.security.path_security import allowed_source_roots, resolve_under_allowed_roots
from fichero.db.storage import get_display, get_thumbnail, resolve_source
from fichero.db.storage import settings as storage_settings
from fichero.utf16_offsets import utf16_range_to_codepoint_range

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


def _get_image_path(
    doc: Document, library_root: Path | None = None
) -> Path | None:
    """Get the image file path for a document."""
    if doc.file_type not in (FileType.image, FileType.pdf) and not doc.path:
        return None

    candidate = (
        get_display(doc, package_path=library_root)
        or get_thumbnail(doc, package_path=library_root)
        or resolve_source(doc, library_root=library_root)
    )
    if candidate is None:
        return None
    return resolve_under_allowed_roots(
        candidate,
        allowed_source_roots(library_root, storage_base=storage_settings.base_path),
    )


def _get_image_dimensions(image_path: Path) -> tuple[int, int]:
    """Get image dimensions."""
    from PIL import Image  # lazy (#3985): keep PIL off the engine boot path

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


def _iiif_base_url(document_id: str) -> str:
    return f"/api/iiif/iiif/{document_id}"


def _iiif_canvas_id(document_id: str) -> str:
    return f"{_iiif_base_url(document_id)}/canvas/1"


def _annotation_motivation(kind: AnnotationKind) -> str:
    return {
        AnnotationKind.highlight: "highlighting",
        AnnotationKind.note: "commenting",
        AnnotationKind.comment: "commenting",
        AnnotationKind.bookmark: "bookmarking",
        AnnotationKind.rating: "assessing",
    }.get(kind, "commenting")


def _annotation_exact_text(doc: Document, ann: Annotation) -> str | None:
    if (
        not doc.page_content
        or ann.char_start is None
        or ann.char_end is None
    ):
        return None
    cp_start, cp_end = utf16_range_to_codepoint_range(
        doc.page_content, ann.char_start, ann.char_end
    )
    return doc.page_content[cp_start:cp_end] or None


def _annotation_target(doc: Document, ann: Annotation) -> dict[str, Any]:
    selectors: list[dict[str, Any]] = []
    if ann.char_start is not None and ann.char_end is not None:
        selectors.append(
            {
                "type": "TextPositionSelector",
                "start": ann.char_start,
                "end": ann.char_end,
            }
        )
        if exact := _annotation_exact_text(doc, ann):
            selectors.append(
                {
                    "type": "TextQuoteSelector",
                    "exact": exact,
                }
            )
    if ann.bbox and len(ann.bbox) == 4:
        x, y, width, height = ann.bbox
        selectors.append(
            {
                "type": "FragmentSelector",
                "conformsTo": "http://www.w3.org/TR/media-frags/",
                "value": f"xywh=pct:{x * 100:g},{y * 100:g},{width * 100:g},{height * 100:g}",
            }
        )
    target: dict[str, Any] = {"source": _iiif_canvas_id(doc.id)}
    if selectors:
        target["selector"] = selectors[0] if len(selectors) == 1 else selectors
    return target


def build_document_annotation_page(db: Database, doc: Document) -> dict[str, Any]:
    annotations = _dedupe_annotations(
        db.query_in(Annotation, "document_id", [doc.id]),
        db.query_in(Annotation, "page_id", [doc.id]),
    )
    items: list[dict[str, Any]] = []
    for ann in annotations:
        body = None
        if ann.text:
            body = {
                "type": "TextualBody",
                "value": ann.text,
                "format": "text/plain",
            }
        items.append(
            {
                "id": f"/api/documents/{doc.id}/annotations/{ann.id}",
                "type": "Annotation",
                "motivation": _annotation_motivation(ann.kind),
                "body": body,
                "target": _annotation_target(doc, ann),
            }
        )
    return {
        "@context": "http://www.w3.org/ns/anno.jsonld",
        "id": f"/api/documents/{doc.id}/annotations.jsonld",
        "type": "AnnotationPage",
        "items": items,
    }


def _dedupe_annotations(*groups: list[Annotation]) -> list[Annotation]:
    seen: set[str] = set()
    rows: list[Annotation] = []
    for group in groups:
        for row in group:
            if row.id in seen:
                continue
            seen.add(row.id)
            rows.append(row)
    return rows


def build_iiif_manifest(db: Database, doc: Document) -> dict[str, Any]:
    image_path = _get_image_path(doc, db.path.parent)
    if not image_path:
        raise HTTPException(
            status_code=404, detail=f"No image available for document: {doc.id}"
        )
    width, height = _get_image_dimensions(image_path)
    base_url = _iiif_base_url(doc.id)
    manifest_url = f"{base_url}/manifest"
    annotation_page_url = f"/api/documents/{doc.id}/annotations.jsonld"
    canvas = {
        "id": _iiif_canvas_id(doc.id),
        "type": "Canvas",
        "label": {"en": [doc.name or "Canvas 1"]},
        "width": width,
        "height": height,
        "items": [
            {
                "id": f"{base_url}/page/1",
                "type": "AnnotationPage",
                "items": [
                    {
                        "id": f"{base_url}/painting/1",
                        "type": "Annotation",
                        "motivation": "painting",
                        "body": {
                            "id": f"{base_url}/full/full/0/default.jpg",
                            "type": "Image",
                            "format": "image/jpeg",
                            "width": width,
                            "height": height,
                            "service": [
                                {
                                    "id": base_url,
                                    "type": "ImageService2",
                                    "profile": "http://iiif.io/api/image/2/level1.json",
                                }
                            ],
                        },
                        "target": _iiif_canvas_id(doc.id),
                    }
                ],
            }
        ],
        "annotations": [{"id": annotation_page_url, "type": "AnnotationPage"}],
    }
    manifest = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "id": manifest_url,
        "type": "Manifest",
        "label": {"en": [doc.name or "Untitled"]},
        "items": [canvas],
    }
    description = getattr(doc, "description", None)
    if description:
        manifest["summary"] = {"en": [description]}
    return manifest


def _serve_iiif_image(
    image_path: Path,
    region: str,
    size: str,
    rotation: str,
    quality: str,
    fmt: str,
) -> Response:
    """Serve a IIIF image region."""
    from PIL import Image  # lazy (#3985): keep PIL off the engine boot path

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
    summary="IIIF Manifest",
    description="Returns IIIF Presentation API manifest for document.",
)
async def get_iiif_manifest(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    """Get IIIF manifest for document."""
    doc = _document_or_404(db, document_id)
    return build_iiif_manifest(db, doc)


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
    from PIL import Image  # lazy (#3985): keep PIL off the engine boot path

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
