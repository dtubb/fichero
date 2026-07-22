"""
Storage Routes

Thumbnail and file serving endpoints.
"""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from fichero.db import Database
from fichero.db.app import get_app_db
from fichero.api.change_stream import emit_change
from fichero.api.library_header import require_library_path
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.models import ActionAudit, Document, LibrarySnapshot, SnapshotInitiatorType
from fichero.core.perf import perf_span
from fichero.db.storage import (
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


class NotFoundResponse(BaseModel):
    detail: str


def _record_snapshot_audit(
    *,
    action_name: str,
    actor: str,
    library_path: str,
    params: dict,
    after: dict | None = None,
) -> ActionAudit:
    audit = ActionAudit(
        action_name=action_name,
        actor=actor,
        target_ids=[library_path],
        params=params,
        after=after,
        created_at=datetime.now(),
    )
    get_app_db().save_action_audit(audit)
    return audit


def _emit_snapshot_change(library_path: str, *, event_type: str, actor: str) -> None:
    emit_change(
        library_path,
        type=event_type,
        actor=actor,
        origin_user=actor,
    )


def _normalize_document_id(doc_id: str) -> str:
    """Accept both bare ids and ``doc:``-prefixed sidebar ids."""
    return doc_id.removeprefix("doc:")


def _document_or_404(db: Database, doc_id: str) -> Document:
    normalized_id = _normalize_document_id(doc_id)
    doc = db.get(Document, normalized_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return doc


def _inline_content_disposition(filename: str) -> str:
    """Build a Content-Disposition header safe for non-ASCII filenames."""
    ascii_fallback = (
        filename.encode("ascii", "replace").decode("ascii").replace('"', "")
    )
    encoded_filename = quote(filename, safe="")
    return f"inline; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_filename}"


@router.get(
    "/thumbnail/{doc_id}",
    responses={
        200: {
            "content": {
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}}
            },
            "description": "Thumbnail image bytes",
        },
        404: {"model": NotFoundResponse, "description": "Document or thumbnail not found"},
    },
)
async def get_thumbnail(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Depends(require_library_path),
):
    """
    Get thumbnail image for a document.

    Returns 404 if document not found or no thumbnail available.
    On a cache miss, also schedules generation of the companion display image
    so both formats exist after the first access (#2217).
    """
    with perf_span(
        "library.thumbnail.endpoint",
        logger=logger,
        doc_id=doc_id,
    ) as perf:
        package_path = Path(x_fichero_library_path)
        doc = _document_or_404(db, doc_id)

        from fichero.db.storage import get_thumbnail, ensure_thumbnail, get_display, ensure_display

        thumb_path = get_thumbnail(doc, package_path=package_path, db=db)
        perf["cache_state"] = "hit" if thumb_path else "miss"

        if not thumb_path:
            thumb_path = await asyncio.to_thread(
                ensure_thumbnail, doc, package_path=package_path, db=db
            )
            perf["cache_state"] = "generated" if thumb_path else "unavailable"
            # Warm the companion display image so both formats exist after the
            # first access — avoids the asymmetry where only the requested format
            # is created lazily (#2216/#2217).
            if thumb_path and not get_display(doc, package_path, db=db):
                background_tasks.add_task(
                    asyncio.to_thread, ensure_display, doc,
                    package_path=package_path, db=db,
                )

        if not thumb_path or not thumb_path.exists():
            raise HTTPException(status_code=404, detail="Thumbnail not available")

        perf["thumbnail_path"] = thumb_path.name
        return FileResponse(
            thumb_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "max-age=86400"},
        )


@router.get(
    "/display/{doc_id}",
    responses={
        200: {
            "content": {
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}}
            },
            "description": "Display image bytes",
        },
        404: {"model": NotFoundResponse, "description": "Document or display image not found"},
    },
)
async def get_display_image(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Depends(require_library_path),
):
    """
    Get display-size image for a document.

    Larger than thumbnail, suitable for preview display.
    On a cache miss, also schedules generation of the companion thumbnail
    so both formats exist after the first access (#2216).
    """
    package_path = Path(x_fichero_library_path)
    doc = _document_or_404(db, doc_id)

    from fichero.db.storage import get_display, ensure_display, get_thumbnail, ensure_thumbnail

    # Try to get existing display image (with package path for library isolation)
    display_path = get_display(doc, package_path, db=db)

    # If no display image, try to generate one
    if not display_path:
        display_path = await asyncio.to_thread(
            ensure_display, doc, package_path=package_path, db=db
        )
        # Warm the companion thumbnail so both formats exist after the first
        # access — avoids the asymmetry where only the requested format is
        # created lazily (#2216/#2217).
        if display_path and not get_thumbnail(doc, package_path=package_path, db=db):
            background_tasks.add_task(
                asyncio.to_thread, ensure_thumbnail, doc,
                package_path=package_path, db=db,
            )

    if not display_path or not display_path.exists():
        raise HTTPException(status_code=404, detail="Display image not available")

    return FileResponse(
        display_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=86400"},
    )


@router.get(
    "/source/{doc_id}",
    responses={
        200: {
            "content": {
                "*/*": {"schema": {"type": "string", "format": "binary"}}
            },
            "description": "Original source file bytes",
            # Declared so the GENERATED client can read it (#3726). The handler has
            # always sent this header, but an undeclared response header is dropped
            # by swift-openapi-generator — which is why the Swift preview download
            # had to stay on raw URLSession to learn the file's real name.
            "headers": {
                "Content-Disposition": {
                    "description": (
                        "inline; filename=... (RFC 5987 filename* when non-ASCII). "
                        "The client names the cached preview file from this, and the "
                        "extension selects the QuickLook renderer."
                    ),
                    "schema": {"type": "string"},
                }
            },
        },
        404: {"model": NotFoundResponse, "description": "Document or source file not found"},
    },
)
async def get_source_file(
    doc_id: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Depends(require_library_path),
):
    """
    Get the original source file for a document.

    Returns 404 if source is not accessible (e.g., external file moved).
    """
    doc = _document_or_404(db, doc_id)

    from fichero.db.storage import resolve_source

    source_path = resolve_source(doc, library_root=db.path.parent)

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
    x_fichero_library_path: str = Depends(require_library_path),
):
    """Get storage statistics for a library."""
    from fichero.db.storage import stats

    package_path = Path(x_fichero_library_path)
    return stats(package_path)


class RegenerateMissingResponse(BaseModel):
    generated: int
    skipped: int
    failed: int
    doc_ids: list[str]


@router.post("/regenerate-missing", response_model=RegenerateMissingResponse)
async def regenerate_missing_thumbnails(
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
) -> RegenerateMissingResponse:
    """Regenerate thumbnails for all documents that are missing one.

    Scans the library for docs without a cached thumbnail and renders each
    one synchronously. Idempotent — already-cached thumbs are skipped.
    Returns counts of generated / skipped / failed docs (#2218).
    """
    from fichero.db.storage import get_thumbnail, ensure_thumbnail
    from fichero.models import Document

    package_path = Path(x_fichero_library_path)
    docs: list[Document] = db.all(Document)

    generated_ids: list[str] = []
    skipped = 0
    failed = 0

    for doc in docs:
        if get_thumbnail(doc, package_path=package_path, db=db):
            skipped += 1
            continue
        try:
            result = await asyncio.to_thread(
                ensure_thumbnail, doc, package_path=package_path, db=db
            )
            if result:
                generated_ids.append(doc.id)
            else:
                skipped += 1
        except Exception:
            logger.exception("regenerate-missing: failed for doc %s", doc.id)
            failed += 1

    return RegenerateMissingResponse(
        generated=len(generated_ids),
        skipped=skipped,
        failed=failed,
        doc_ids=generated_ids,
    )


@router.get("/debug/{doc_id}")
async def debug_document_paths(
    doc_id: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Depends(require_library_path),
) -> DocumentDebugResponse:
    """Debug endpoint to check document paths and file access."""
    from fichero.db.storage import resolve_source, _thumb_path

    package_path = Path(x_fichero_library_path)
    doc = _document_or_404(db, doc_id)

    source_path = resolve_source(doc, library_root=db.path.parent)
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
    duckdb_backup_path: str | None = None
    lance_backup_path: str | None = None
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
    actor = initiator.value
    params = {
        "library_path": library_path,
        "reason": reason,
        "initiator": actor,
        "initiator_id": initiator_id,
        "run_id": run_id,
        "auto_expire_days": auto_expire_days,
    }
    try:
        _record_snapshot_audit(
            action_name="snapshot.create.intent",
            actor=actor,
            library_path=library_path,
            params=params,
        )
        _emit_snapshot_change(library_path, event_type="snapshot.create.intent", actor=actor)
        snapshot = snapshot_library(
            library_path=library_path,
            reason=reason,
            initiator=initiator.value,
            initiator_id=initiator_id,
            run_id=run_id,
            auto_expire_days=auto_expire_days,
        )
        _record_snapshot_audit(
            action_name="snapshot.create.outcome",
            actor=actor,
            library_path=library_path,
            params=params,
            after=snapshot.model_dump(mode="json"),
        )
        _emit_snapshot_change(library_path, event_type="snapshot.created", actor=actor)
        return snapshot
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

    Restoration swaps the captured database and vector files back into the
    original library package. The pre-restore files are retained with a
    .pre-restore suffix.
    """
    try:
        snapshot = next(
            (row for row in list_snapshots(include_expired=True) if row.id == snapshot_id),
            None,
        )
        if snapshot is None:
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")
        actor = snapshot.initiator.value
        params = {"snapshot_id": snapshot_id, "library_path": snapshot.library_path}
        _record_snapshot_audit(
            action_name="snapshot.restore.intent",
            actor=actor,
            library_path=snapshot.library_path,
            params=params,
        )
        _emit_snapshot_change(
            snapshot.library_path,
            event_type="snapshot.restore.intent",
            actor=actor,
        )
        result = restore_snapshot(snapshot_id)
        _record_snapshot_audit(
            action_name="snapshot.restore.outcome",
            actor=actor,
            library_path=snapshot.library_path,
            params=params,
            after=result,
        )
        _emit_snapshot_change(
            snapshot.library_path,
            event_type="snapshot.restored",
            actor=actor,
        )
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
    from fichero.db.storage import _load_all_snapshot_records, _save_snapshot_record

    snapshots = _load_all_snapshot_records()
    snapshot = next((s for s in snapshots if s.id == snapshot_id), None)
    if not snapshot:
        raise HTTPException(
            status_code=404, detail=f"Snapshot not found: {snapshot_id}"
        )

    snapshot.is_pinned = pinned
    _save_snapshot_record(snapshot)
    return snapshot
