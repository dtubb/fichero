"""
Storage Routes

Thumbnail and file serving endpoints.
"""

import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import FileResponse

from fichero.db import Database
from fichero.api.main import get_library_database
from fichero.models import Document

logger = logging.getLogger(__name__)
router = APIRouter()


def _inline_content_disposition(filename: str) -> str:
    """Build a Content-Disposition header safe for non-ASCII filenames."""
    ascii_fallback = filename.encode("ascii", "replace").decode("ascii").replace('"', "")
    encoded_filename = quote(filename, safe="")
    return f"inline; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_filename}"


@router.get("/thumbnail/{doc_id}")
async def get_thumbnail(
    doc_id: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
):
    """
    Get thumbnail image for a document.

    Returns 404 if document not found or no thumbnail available.
    """
    package_path = Path(x_fichero_library_path)
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    from fichero.storage import get_thumbnail, ensure_thumbnail

    # Try to get existing thumbnail (with package path for library isolation)
    thumb_path = get_thumbnail(doc, package_path)

    # If no thumbnail, try to generate one
    if not thumb_path:
        thumb_path = ensure_thumbnail(doc, package_path=package_path)

    if not thumb_path or not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not available")

    return FileResponse(
        thumb_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=86400"},
    )


@router.get("/display/{doc_id}")
async def get_display_image(
    doc_id: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
):
    """
    Get display-size image for a document.

    Larger than thumbnail, suitable for preview display.
    """
    package_path = Path(x_fichero_library_path)
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    from fichero.storage import get_display, ensure_display

    # Try to get existing display image (with package path for library isolation)
    display_path = get_display(doc, package_path)

    # If no display image, try to generate one
    if not display_path:
        display_path = ensure_display(doc, package_path=package_path)

    if not display_path or not display_path.exists():
        raise HTTPException(status_code=404, detail="Display image not available")

    return FileResponse(
        display_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=86400"},
    )


@router.get("/source/{doc_id}")
async def get_source_file(
    doc_id: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
):
    """
    Get the original source file for a document.

    Returns 404 if source is not accessible (e.g., external file moved).
    """
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    from fichero.storage import resolve_source

    source_path = resolve_source(doc)

    if not source_path:
        logger.warning(f"resolve_source returned None for doc {doc_id}: path={doc.path}, has_bookmark={bool(doc.metadata.get('bookmark'))}")
        raise HTTPException(status_code=404, detail="Source file not available")

    if not source_path.exists():
        logger.warning(f"Source path resolved but doesn't exist: {source_path}")
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

    # Include RFC 5987 filename* to support Unicode names while keeping ASCII fallback.
    content_disposition = _inline_content_disposition(source_path.name)
    return FileResponse(
        source_path,
        media_type=media_type,
        headers={"Content-Disposition": content_disposition},
    )


@router.get("/stats")
async def storage_stats(
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
):
    """Get storage statistics for a library."""
    from fichero.storage import stats

    package_path = Path(x_fichero_library_path)
    return stats(package_path)


@router.get("/debug/{doc_id}")
async def debug_document_paths(
    doc_id: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
):
    """Debug endpoint to check document paths and file access."""
    from fichero.storage import resolve_source, _thumb_path
    import os

    package_path = Path(x_fichero_library_path)
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    source_path = resolve_source(doc)
    thumb_path = _thumb_path(doc.id, package_path)

    return {
        "doc_id": doc.id,
        "doc_name": doc.name,
        "doc_path": doc.path,
        "doc_path_exists": Path(doc.path).exists() if doc.path else False,
        "package_path": str(package_path),
        "package_exists": package_path.exists(),
        "resolved_source": str(source_path) if source_path else None,
        "source_exists": source_path.exists() if source_path else False,
        "expected_thumb_path": str(thumb_path),
        "thumb_exists": thumb_path.exists(),
        "cwd": os.getcwd(),
        "metadata": doc.metadata,
    }
