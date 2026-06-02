"""
Storage Routes

Thumbnail and file serving endpoints.
"""

import logging
import os
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Depends, Header, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from fichero.db import Database
from fichero.api.main import get_library_database
from fichero.models import Document, LibrarySnapshot, SnapshotInitiatorType
from fichero.storage import (
    snapshot_library,
    list_snapshots,
    restore_snapshot,
    delete_snapshot,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class DocumentDebugResponse(BaseModel):
    doc_id: str
    doc_name: str
    doc_path: str | None
    doc_path_exists: bool
    package_path: str
    package_exists: bool
    resolved_source: str | None
    source_exists: bool
    expected_thumb_path: str
    thumb_exists: bool
    cwd: str
    metadata: dict


def _inline_content_disposition(filename: str) -> str:
    """Build a Content-Disposition header safe for non-ASCII filenames."""
    ascii_fallback = (
        filename.encode("ascii", "replace").decode("ascii").replace('"', "")
    )
    encoded_filename = quote(filename, safe="")
    return f"inline; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_filename}"


def _edit_chain_mtime(db: Database, doc_id: str) -> float | None:
    """Return the edit-chain's last-updated time as an epoch float, or None.

    Used to invalidate cached thumbnail/display renditions when an image has
    been edited (#469 non-destructive edit chain). The chain is stored
    separately from the source, so a cached rendition generated *before* the
    most recent edit is stale even though the on-disk source is untouched.
    """
    from fichero.api.routes.image_editing import _get_chain

    chain = _get_chain(db, doc_id)
    if not chain or not chain.operations:
        return None
    updated = getattr(chain, "updated_at", None) or getattr(chain, "created_at", None)
    try:
        return updated.timestamp() if updated is not None else None
    except (AttributeError, TypeError):
        return None


def _edited_rendition_path(base_rendition: Path) -> Path:
    """Sibling path that holds the edit-baked copy of a thumbnail/display image.

    The base rendition stays a faithful copy of the *original* source (so revert
    is just "stop serving the edited sibling"). The edited copy is regenerated
    whenever the edit chain changes, which keeps the bake idempotent — we never
    re-apply ops onto an already-baked image.
    """
    return base_rendition.with_name(base_rendition.stem + "_edited" + base_rendition.suffix)


def _edited_rendition(db: Database, doc_id: str, base_rendition: Path, chain_mtime: float) -> Path | None:
    """Return a baked-with-edits copy of ``base_rendition``, generating if stale.

    Applies the page-1 edit chain (#469) onto a *fresh copy* of the original
    rendition and caches it alongside, keyed off the chain's last-updated time.
    Returns None on failure (caller then falls back to the original rendition).
    """
    try:
        from PIL import Image as _PILImage
    except ImportError:
        return None
    from fichero.api.routes.image_editing import _apply_saved_operations

    edited_path = _edited_rendition_path(base_rendition)

    # Reuse the cached edited copy when it is newer than both the source
    # rendition and the most recent edit.
    if (
        edited_path.exists()
        and edited_path.stat().st_mtime >= base_rendition.stat().st_mtime
        and edited_path.stat().st_mtime >= chain_mtime
    ):
        return edited_path

    try:
        with _PILImage.open(base_rendition) as img:
            img.load()
            edited = _apply_saved_operations(db, doc_id, 1, img)
            if edited.mode not in ("RGB", "L"):
                edited = edited.convert("RGB")
            edited.save(edited_path, "JPEG", quality=92)
        return edited_path
    except Exception as exc:  # noqa: BLE001 — never break image serving on edit-bake failure
        logger.warning("Failed to bake edit chain onto rendition %s: %s", doc_id, exc)
        return None


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

    # If the image has been edited (#469), the cached thumbnail was generated
    # from the untouched source and so shows the *original*. Serve an
    # edit-baked sibling instead, regenerated whenever the chain changes.
    # Cache-Control is no-cache so the client re-fetches after each edit; the
    # base rendition keeps the original, so revert just drops back to it.
    chain_mtime = _edit_chain_mtime(db, doc_id)
    if chain_mtime is not None:
        edited_path = _edited_rendition(db, doc_id, thumb_path, chain_mtime)
        if edited_path is not None and edited_path.exists():
            return FileResponse(
                edited_path,
                media_type="image/jpeg",
                headers={"Cache-Control": "no-cache"},
            )

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

    # Serve the edit-baked sibling when the image has been edited (#469), so the
    # browse viewer / inspector reflect edits while the base copy stays original
    # for revert. See get_thumbnail for the same pattern.
    chain_mtime = _edit_chain_mtime(db, doc_id)
    if chain_mtime is not None:
        edited_path = _edited_rendition(db, doc_id, display_path, chain_mtime)
        if edited_path is not None and edited_path.exists():
            return FileResponse(
                edited_path,
                media_type="image/jpeg",
                headers={"Cache-Control": "no-cache"},
            )

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
        logger.warning(
            f"resolve_source returned None for doc {doc_id}: path={doc.path}, has_bookmark={bool(doc.metadata.get('bookmark'))}"
        )
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
) -> DocumentDebugResponse:
    """Debug endpoint to check document paths and file access."""
    from fichero.storage import resolve_source, _thumb_path

    package_path = Path(x_fichero_library_path)
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    source_path = resolve_source(doc)
    thumb_path = _thumb_path(doc.id, package_path)

    return DocumentDebugResponse(
        doc_id=doc.id,
        doc_name=doc.name,
        doc_path=doc.path,
        doc_path_exists=Path(doc.path).exists() if doc.path else False,
        package_path=str(package_path),
        package_exists=package_path.exists(),
        resolved_source=str(source_path) if source_path else None,
        source_exists=source_path.exists() if source_path else False,
        expected_thumb_path=str(thumb_path),
        thumb_exists=thumb_path.exists(),
        cwd=os.getcwd(),
        metadata=doc.metadata,
    )


# =============================================================================
# Library Snapshots
# =============================================================================


class SnapshotCreateResponse(BaseModel):
    snapshot: LibrarySnapshot


class SnapshotRestoreResponse(BaseModel):
    snapshot_id: str
    library_path: str
    duckdb_restored_path: str | None
    lance_restored_path: str | None
    note: str


class SnapshotDeleteResponse(BaseModel):
    deleted: bool
    snapshot_id: str


class SnapshotListResponse(BaseModel):
    snapshots: list[LibrarySnapshot]
    total: int


@router.post("/snapshots", response_model=LibrarySnapshot, tags=["snapshots"])
async def create_snapshot(
    library_path: str = Query(..., description="Path to the .fichero package"),
    reason: str = Query(default="", description="Reason for the snapshot"),
    initiator: SnapshotInitiatorType = Query(default=SnapshotInitiatorType.user),
    initiator_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    auto_expire_days: int | None = Query(default=None),
) -> LibrarySnapshot:
    """Create a point-in-time snapshot of a library.

    Exports the DuckDB database to Parquet files and copies the LanceDB
    vector directory. Snapshot data is stored in:
        ~/Library/Application Support/com.fichero.fichero/snapshots/{library_name}/{snapshot_id}/

    Use after bulk AI operations or before schema changes.
    """
    try:
        return snapshot_library(
            library_path=library_path,
            reason=reason,
            initiator=initiator.value,
            initiator_id=initiator_id,
            run_id=run_id,
            auto_expire_days=auto_expire_days,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshots", response_model=SnapshotListResponse, tags=["snapshots"])
async def get_snapshots(
    library_name: str | None = Query(default=None),
    include_expired: bool = Query(default=False),
) -> SnapshotListResponse:
    """List snapshots, newest first. Expired snapshots excluded by default."""
    snapshots = list_snapshots(
        library_name=library_name,
        include_expired=include_expired,
    )
    return SnapshotListResponse(snapshots=snapshots, total=len(snapshots))


@router.get(
    "/snapshots/{snapshot_id}", response_model=LibrarySnapshot, tags=["snapshots"]
)
async def get_snapshot(snapshot_id: str) -> LibrarySnapshot:
    """Get a single snapshot by ID."""
    snapshots = list_snapshots(include_expired=True)
    snapshot = next((s for s in snapshots if s.id == snapshot_id), None)
    if not snapshot:
        raise HTTPException(
            status_code=404, detail=f"Snapshot not found: {snapshot_id}"
        )
    return snapshot


@router.post(
    "/snapshots/{snapshot_id}/restore",
    response_model=SnapshotRestoreResponse,
    tags=["snapshots"],
)
async def restore_library_snapshot(snapshot_id: str) -> SnapshotRestoreResponse:
    """Restore a library from a snapshot.

    Restoration creates NEW database and vector files alongside the originals.
    The current library is NOT modified. After restoration, update
    X-Fichero-Library-Path to point to the restored library to use it.
    """
    try:
        result = restore_snapshot(snapshot_id)
        return SnapshotRestoreResponse(**result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/snapshots/{snapshot_id}",
    response_model=SnapshotDeleteResponse,
    tags=["snapshots"],
)
async def remove_snapshot(snapshot_id: str) -> SnapshotDeleteResponse:
    """Delete a snapshot and its data files."""
    deleted = delete_snapshot(snapshot_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Snapshot not found: {snapshot_id}"
        )
    return SnapshotDeleteResponse(deleted=True, snapshot_id=snapshot_id)


@router.patch(
    "/snapshots/{snapshot_id}/pin", response_model=LibrarySnapshot, tags=["snapshots"]
)
async def pin_snapshot(
    snapshot_id: str,
    pinned: bool = True,
) -> LibrarySnapshot:
    """Toggle pinned status. Pinned snapshots are not auto-deleted."""
    from fichero.storage import _load_all_snapshot_records, _save_snapshot_record

    snapshots = _load_all_snapshot_records()
    snapshot = next((s for s in snapshots if s.id == snapshot_id), None)
    if not snapshot:
        raise HTTPException(
            status_code=404, detail=f"Snapshot not found: {snapshot_id}"
        )

    snapshot.is_pinned = pinned
    _save_snapshot_record(snapshot)
    return snapshot
