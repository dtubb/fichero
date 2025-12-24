"""
Storage Routes

Thumbnail and file serving endpoints.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from fichero.db import db
from fichero.models import Document

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/thumbnail/{doc_id}")
async def get_thumbnail(doc_id: str):
    """
    Get thumbnail image for a document.

    Returns 404 if document not found or no thumbnail available.
    """
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    from fichero.storage import get_thumbnail, ensure_thumbnail

    # Try to get existing thumbnail
    thumb_path = get_thumbnail(doc)

    # If no thumbnail, try to generate one
    if not thumb_path:
        thumb_path = ensure_thumbnail(doc)

    if not thumb_path or not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not available")

    return FileResponse(
        thumb_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=86400"},
    )


@router.get("/display/{doc_id}")
async def get_display_image(doc_id: str):
    """
    Get display-size image for a document.

    Larger than thumbnail, suitable for preview display.
    """
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    from fichero.storage import get_display, ensure_display

    # Try to get existing display image
    display_path = get_display(doc)

    # If no display image, try to generate one
    if not display_path:
        display_path = ensure_display(doc)

    if not display_path or not display_path.exists():
        raise HTTPException(status_code=404, detail="Display image not available")

    return FileResponse(
        display_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=86400"},
    )


@router.get("/source/{doc_id}")
async def get_source_file(doc_id: str):
    """
    Get the original source file for a document.

    Returns 404 if source is not accessible (e.g., external file moved).
    """
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    from fichero.storage import resolve_source

    source_path = resolve_source(doc)

    if not source_path or not source_path.exists():
        raise HTTPException(status_code=404, detail="Source file not available")

    # Determine media type from file extension
    suffix = source_path.suffix.lower()
    media_types = {
        # Images
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".bmp": "image/bmp",
        ".heic": "image/heic",
        ".svg": "image/svg+xml",
        # Documents
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".rtf": "application/rtf",
        ".html": "text/html",
        ".htm": "text/html",
        # Office
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".ppt": "application/vnd.ms-powerpoint",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        # Audio
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".aac": "audio/aac",
        ".m4a": "audio/mp4",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        # Video
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        # Ebooks
        ".epub": "application/epub+zip",
        ".mobi": "application/x-mobipocket-ebook",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    # Set filename in Content-Disposition so Quick Look knows the extension
    filename = source_path.name
    return FileResponse(
        source_path,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/stats")
async def storage_stats():
    """Get storage statistics."""
    from fichero.storage import stats

    return stats()
