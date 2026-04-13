"""
File storage management for Fichero.

Handles derived files (thumbnails), path resolution, and file organization.
Uses Pydantic Settings for configuration and explicit functions for operations.

Location: ~/Library/Application Support/com.tubb.fichero/
├── library.duckdb          # Database (managed by db.py)
├── vectors/                # LanceDB embeddings
└── thumbnails/             # Sharded thumbnail storage
    └── {id[:2]}/{id}.jpg   # 256 buckets for scale

Usage:
    from fichero.storage import settings, ensure_thumbnail, resolve_source

    # Get settings
    print(settings.thumb_dir)

    # Generate thumbnail (explicit, not hidden)
    path = ensure_thumbnail(doc)

    # Resolve source file
    source = resolve_source(doc)

    # Cleanup orphaned thumbnails
    cleanup_orphans(valid_doc_ids)
"""

from __future__ import annotations

import base64
import json
import logging
import shutil

import duckdb
from datetime import datetime, timedelta
from uuid import uuid4
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from fichero.models import LibrarySnapshot

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None  # type: ignore
    ImageOps = None  # type: ignore

if TYPE_CHECKING:
    from fichero.models import Document

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration (Pydantic Settings)
# =============================================================================


class StorageSettings(BaseSettings):
    """Storage configuration.

    Override via environment variables:
        FICHERO_BASE_PATH=/custom/path
        FICHERO_THUMB_SIZE=150,150
        FICHERO_QUALITY=90
    """

    model_config = SettingsConfigDict(env_prefix="FICHERO_")

    # Base path - can be overridden for testing
    base_path: Path = Path(
        "~/Library/Application Support/com.tubb.fichero"
    ).expanduser()

    # Thumbnail settings
    thumb_width: int = 200
    thumb_height: int = 200
    display_width: int = 1000
    display_height: int = 1000
    quality: int = 85

    # Thread pool size for background generation
    max_workers: int = 2

    @computed_field
    @property
    def thumb_dir(self) -> Path:
        """Directory for thumbnail storage."""
        return self.base_path / "thumbnails"

    @computed_field
    @property
    def db_path(self) -> Path:
        """Path to DuckDB database (legacy - per library)."""
        return self.base_path / "library.duckdb"

    @computed_field
    @property
    def app_db_path(self) -> Path:
        """Path to app-wide DuckDB database (providers, app settings)."""
        return self.base_path / "app.duckdb"

    @computed_field
    @property
    def global_library_path(self) -> Path:
        """Path to global library database (cross-library searches/chats/workflows)."""
        return self.base_path / "global.fichero"

    @computed_field
    @property
    def vectors_dir(self) -> Path:
        """Directory for LanceDB vectors."""
        return self.base_path / "vectors"

    @computed_field
    @property
    def snapshots_dir(self) -> Path:
        """Directory for library snapshots."""
        return self.base_path / "snapshots"

    @property
    def thumb_size(self) -> tuple[int, int]:
        """Thumbnail dimensions as tuple."""
        return (self.thumb_width, self.thumb_height)

    @property
    def display_size(self) -> tuple[int, int]:
        """Display image dimensions as tuple."""
        return (self.display_width, self.display_height)


# Global settings instance
settings = StorageSettings()


# =============================================================================
# Path Helpers
# =============================================================================


def _thumb_path(doc_id: str, package_path: Path | None = None) -> Path:
    """Get sharded thumbnail path.

    Uses first 2 chars of ID for sharding:
    thumbnails/a1/a1b2c3d4-e5f6-...jpg

    256 possible buckets = ~234 files each for 60k images.

    Args:
        doc_id: Document ID
        package_path: Path to .fichero package (if None, uses global base_path)
    """
    prefix = doc_id[:2].lower()
    if package_path:
        thumb_dir = package_path / "storage" / "thumbnails"
    else:
        thumb_dir = settings.thumb_dir
    return thumb_dir / prefix / f"{doc_id}.jpg"


def _display_path(doc_id: str, package_path: Path | None = None) -> Path:
    """Get path for display-size image.

    Args:
        doc_id: Document ID
        package_path: Path to .fichero package (if None, uses global base_path)
    """
    prefix = doc_id[:2].lower()
    if package_path:
        thumb_dir = package_path / "storage" / "thumbnails"
    else:
        thumb_dir = settings.thumb_dir
    return thumb_dir / prefix / f"{doc_id}_display.jpg"


# =============================================================================
# Source Resolution
# =============================================================================


def resolve_source(doc: "Document") -> Path | None:
    """Resolve the source file for a document.

    Priority:
    1. macOS bookmark (survives moves/renames)
    2. doc.path
    3. metadata.source_path
    4. metadata.full_path
    5. metadata.local_path

    Args:
        doc: Document to resolve source for

    Returns:
        Path to existing file, or None if not found
    """
    # Try bookmark first (macOS)
    if bookmark_data := _get_bookmark(doc):
        try:
            from fichero.bookmarks import resolve_bookmark

            if path := resolve_bookmark(bookmark_data):
                return path
        except ImportError:
            pass  # bookmarks module not available

    # Fall back to paths
    if doc.path:
        p = Path(doc.path)
        if p.exists():
            return p

    # Check metadata fields
    if doc.metadata:
        for key in ["source_path", "full_path", "display_path", "local_path"]:
            if path_str := doc.metadata.get(key):
                p = Path(path_str)
                if p.exists():
                    return p

    return None


def _get_bookmark(doc: "Document") -> bytes | None:
    """Extract bookmark data from document metadata."""
    if not doc.metadata:
        return None
    b64 = doc.metadata.get("bookmark")
    if b64:
        try:
            return base64.b64decode(b64)
        except Exception:
            return None
    return None


# =============================================================================
# Thumbnail Generation
# =============================================================================


def ensure_thumbnail(
    doc: "Document", force: bool = False, package_path: Path | None = None
) -> Path | None:
    """Generate thumbnail if needed.

    Args:
        doc: Document to generate thumbnail for
        force: If True, regenerate even if exists
        package_path: Path to .fichero package (if None, uses global base_path)

    Returns:
        Path to thumbnail, or None on failure
    """
    if Image is None:
        logger.error("Pillow not installed - cannot generate thumbnails")
        return None

    path = _thumb_path(doc.id, package_path)
    source = resolve_source(doc)

    if not source:
        logger.warning(f"No source found for {doc.id}")
        return None

    # Check if regeneration needed
    if path.exists() and not force:
        # Auto-regenerate if source is newer
        if source.stat().st_mtime <= path.stat().st_mtime:
            return path
        logger.debug(f"Source newer than thumbnail, regenerating: {doc.id}")

    # Generate
    return _generate_image(source, path, settings.thumb_size)


def ensure_display(
    doc: "Document", force: bool = False, package_path: Path | None = None
) -> Path | None:
    """Generate display-size image if needed.

    Args:
        doc: Document to generate display image for
        force: If True, regenerate even if exists
        package_path: Path to .fichero package (if None, uses global base_path)

    Returns:
        Path to display image, or None on failure
    """
    if Image is None:
        return None

    path = _display_path(doc.id, package_path)
    source = resolve_source(doc)

    if not source:
        return None

    if path.exists() and not force:
        if source.stat().st_mtime <= path.stat().st_mtime:
            return path

    return _generate_image(source, path, settings.display_size)


def _generate_image(source: Path, dest: Path, size: tuple[int, int]) -> Path | None:
    """Generate a resized image.

    Args:
        source: Source image path
        dest: Destination path
        size: (width, height) tuple

    Returns:
        Path to generated image, or None on failure
    """
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Opening image: {source} (suffix: {source.suffix})")
        with Image.open(source) as img:
            logger.debug(f"Image opened successfully: mode={img.mode}, size={img.size}")

            # Handle EXIF rotation
            if ImageOps:
                img = ImageOps.exif_transpose(img)

            # Create thumbnail (modifies in place, maintains aspect ratio)
            img.thumbnail(size, Image.Resampling.LANCZOS)

            # Convert to RGB for JPEG (handles RGBA, P mode, etc.)
            if img.mode not in ("RGB", "L"):
                logger.debug(f"Converting from {img.mode} to RGB")
                img = img.convert("RGB")

            img.save(dest, "JPEG", quality=settings.quality)

        logger.info(f"Generated thumbnail: {dest} from {source.name}")
        return dest

    except Exception as e:
        logger.error(
            f"Image generation failed for {source.name} ({source.suffix}): {e}",
            exc_info=True,
        )
        return None


# =============================================================================
# Batch Generation (Background)
# =============================================================================

# Background executor (lazy-initialized)
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """Get or create the background executor."""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=settings.max_workers, thread_name_prefix="thumb"
            )
    return _executor


def ensure_thumbnails(
    docs: list["Document"],
    on_progress: Callable[[str, Path | None], None] | None = None,
) -> list[Future]:
    """Batch generate thumbnails in background threads.

    Args:
        docs: Documents to generate thumbnails for
        on_progress: Callback when each thumbnail is ready.
            Called with (doc_id, path) - path is None on failure.

    Returns:
        List of futures for tracking completion
    """
    executor = _get_executor()
    futures = []

    for doc in docs:
        if not _thumb_path(doc.id).exists():
            future = executor.submit(ensure_thumbnail, doc)
            if on_progress:
                # Capture doc.id for callback
                doc_id = doc.id
                future.add_done_callback(
                    lambda f, did=doc_id: on_progress(did, f.result())
                )
            futures.append(future)

    return futures


def ensure_displays(
    docs: list["Document"],
    on_progress: Callable[[str, Path | None], None] | None = None,
) -> list[Future]:
    """Batch generate display images in background threads."""
    executor = _get_executor()
    futures = []

    for doc in docs:
        if not _display_path(doc.id).exists():
            future = executor.submit(ensure_display, doc)
            if on_progress:
                doc_id = doc.id
                future.add_done_callback(
                    lambda f, did=doc_id: on_progress(did, f.result())
                )
            futures.append(future)

    return futures


# =============================================================================
# Cleanup
# =============================================================================


def cleanup_orphans(valid_doc_ids: set[str]) -> int:
    """Remove thumbnails for documents that no longer exist.

    Args:
        valid_doc_ids: Set of document IDs that still exist

    Returns:
        Number of files removed
    """
    removed = 0
    thumb_dir = settings.thumb_dir

    if not thumb_dir.exists():
        return 0

    for shard in thumb_dir.iterdir():
        if not shard.is_dir():
            continue

        for thumb_file in shard.iterdir():
            if not thumb_file.is_file():
                continue

            # Extract doc ID from filename
            doc_id = thumb_file.stem.replace("_display", "")

            if doc_id not in valid_doc_ids:
                try:
                    thumb_file.unlink()
                    removed += 1
                except OSError as e:
                    logger.warning(f"Failed to remove {thumb_file}: {e}")

        # Remove empty shard directories
        if not any(shard.iterdir()):
            try:
                shard.rmdir()
            except OSError:
                pass

    if removed > 0:
        logger.info(f"Cleaned up {removed} orphaned thumbnails")

    return removed


def clear_all() -> int:
    """Remove all thumbnails. Use with caution.

    Returns:
        Number of files removed
    """

    thumb_dir = settings.thumb_dir
    if not thumb_dir.exists():
        return 0

    count = sum(1 for _ in thumb_dir.rglob("*.jpg"))

    shutil.rmtree(thumb_dir)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Cleared {count} thumbnails")
    return count


# =============================================================================
# Stats
# =============================================================================


def stats(package_path: Path | None = None) -> dict:
    """Get storage statistics.

    Args:
        package_path: Package path for library-specific stats.
                     If None, uses global thumb_dir (backward compat).

    Returns:
        Dict with count, size_mb, shards
    """
    if package_path:
        thumb_dir = package_path / "storage" / "thumbnails"
    else:
        thumb_dir = settings.thumb_dir

    if not thumb_dir.exists():
        return {"count": 0, "size_mb": 0.0, "shards": 0}

    count = 0
    size = 0

    for f in thumb_dir.rglob("*.jpg"):
        count += 1
        size += f.stat().st_size

    return {
        "count": count,
        "size_mb": round(size / (1024 * 1024), 2),
        "shards": sum(1 for d in thumb_dir.iterdir() if d.is_dir()),
    }


async def save_uploaded_file(file) -> Path:
    """Save an uploaded FastAPI file to a temporary location.

    Args:
        file: FastAPI UploadFile object

    Returns:
        Path to saved temporary file

    Note:
        The caller is responsible for cleanup of the temp file.
        Use this with ingest_file(mode=IngestMode.COPY) which will
        copy the file to library storage.
    """
    # Create temp file with same extension as uploaded file
    suffix = Path(file.filename).suffix if file.filename else ""

    # Create temp file (not auto-deleted, caller must clean up)
    fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix="fichero_upload_")
    temp_path = Path(temp_path)

    try:
        # Read uploaded file content
        content = await file.read()

        # Write to temp file
        with open(fd, "wb") as f:
            f.write(content)

        logger.debug(f"Saved upload to temp: {temp_path}")
        return temp_path

    except Exception as e:
        # Clean up on error
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise e


def shutdown() -> None:
    """Shutdown background executor. Call on app exit."""
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False)
            _executor = None


# =============================================================================
# Convenience - Document Path Properties
# =============================================================================


def expected_thumbnail_path(doc_id: str, package_path: Path | None = None) -> Path:
    """Get expected thumbnail path (may not exist yet).

    Args:
        doc_id: Document ID
        package_path: Package path for library-specific path.
                     If None, uses global thumb_dir (backward compat).

    Returns:
        Path to expected thumbnail location
    """
    return _thumb_path(doc_id, package_path)


def expected_display_path(doc_id: str, package_path: Path | None = None) -> Path:
    """Get expected display image path (may not exist yet).

    Args:
        doc_id: Document ID
        package_path: Package path for library-specific path.
                     If None, uses global thumb_dir (backward compat).

    Returns:
        Path to expected display image location
    """
    return _display_path(doc_id, package_path)


def has_thumbnail(doc_id: str, package_path: Path | None = None) -> bool:
    """Check if thumbnail exists on disk.

    Args:
        doc_id: Document ID
        package_path: Package path for library-specific check.
                     If None, uses global thumb_dir (backward compat).

    Returns:
        True if thumbnail file exists
    """
    return _thumb_path(doc_id, package_path).exists()


def has_display(doc_id: str, package_path: Path | None = None) -> bool:
    """Check if display image exists on disk.

    Args:
        doc_id: Document ID
        package_path: Package path for library-specific check.
                     If None, uses global thumb_dir (backward compat).

    Returns:
        True if display image file exists
    """
    return _display_path(doc_id, package_path).exists()


def get_thumbnail(doc: "Document", package_path: Path | None = None) -> Path | None:
    """Get thumbnail path if it exists, else None.

    Does NOT generate - use ensure_thumbnail() for that.

    Args:
        doc: Document to get thumbnail for
        package_path: Path to .fichero package (if None, uses global base_path)
    """
    path = _thumb_path(doc.id, package_path)
    return path if path.exists() else None


def get_display(doc: "Document", package_path: Path | None = None) -> Path | None:
    """Get display image path if it exists, else None.

    Args:
        doc: Document to get display image for
        package_path: Path to .fichero package (if None, uses global base_path)
    """
    path = _display_path(doc.id, package_path)
    return path if path.exists() else None


# =============================================================================
# Library Snapshots
# =============================================================================


def snapshot_library(
    library_path: str,
    reason: str = "",
    initiator: str = "user",
    initiator_id: str | None = None,
    run_id: str | None = None,
    auto_expire_days: int | None = None,
) -> "LibrarySnapshot":
    """Create a point-in-time snapshot of a library.

    Exports DuckDB tables to Parquet and copies the LanceDB vector directory.
    Snapshot metadata is stored in app.duckdb and the data lives in:
        ~/Library/Application Support/com.tubb.fichero/snapshots/{library_name}/{snapshot_id}/

    Args:
        library_path: Path to the .fichero package
        reason: Human-readable reason for the snapshot
        initiator: Who created this — "user", "ai", or "system"
        initiator_id: Optional agent_id or user_id
        run_id: Optional AI run_id for auto-created snapshots
        auto_expire_days: If set, snapshot auto-deletes after this many days

    Returns:
        LibrarySnapshot record with paths and sizes

    Raises:
        FileNotFoundError: If library_path doesn't exist
        RuntimeError: If DuckDB export or LanceDB copy fails
    """
    from fichero.models import LibrarySnapshot, SnapshotInitiatorType

    library_path_p = Path(library_path)
    if not library_path_p.exists():
        raise FileNotFoundError(f"Library not found: {library_path}")

    library_name = library_path_p.stem  # "MyLibrary" from "MyLibrary.fichero"
    snapshot_id = str(uuid4())

    # Snapshot directory: snapshots/{library_name}/{snapshot_id}/
    snapshot_root = settings.snapshots_dir / library_name / snapshot_id
    duckdb_export_dir = snapshot_root / "duckdb_export"
    lance_copy_dir = snapshot_root / "lance_copy"

    snapshot_root.mkdir(parents=True, exist_ok=True)
    duckdb_export_dir.mkdir(parents=True, exist_ok=True)
    lance_copy_dir.mkdir(parents=True, exist_ok=True)

    # 1. Export DuckDB to Parquet
    duckdb_size = 0
    db_path = library_path_p / "fichero.duckdb"
    if db_path.exists():
        try:
            export_conn = duckdb.connect(str(db_path), read_only=True)
            # Get list of tables
            tables = export_conn.execute("SHOW TABLES").fetchall()
            for (table_name,) in tables:
                out_path = duckdb_export_dir / f"{table_name}.parquet"
                export_conn.execute(
                    f"COPY {table_name} TO '{out_path}' (FORMAT parquet)"
                )
                duckdb_size += out_path.stat().st_size
            export_conn.close()
            logger.info(
                f"Exported DuckDB ({duckdb_size / 1024 / 1024:.1f} MB) to {duckdb_export_dir}"
            )
        except Exception as e:
            raise RuntimeError(f"DuckDB export failed: {e}") from e
    else:
        logger.warning(f"No DuckDB found at {db_path}, skipping export")

    # 2. Copy LanceDB vectors
    lance_size = 0
    lance_src = library_path_p / "lance"
    if lance_src.exists():
        try:
            shutil.copytree(lance_src, lance_copy_dir, dirs_exist_ok=True)
            lance_size = sum(
                f.stat().st_size for f in lance_copy_dir.rglob("*") if f.is_file()
            )
            logger.info(
                f"Copied LanceDB ({lance_size / 1024 / 1024:.1f} MB) to {lance_copy_dir}"
            )
        except Exception as e:
            raise RuntimeError(f"LanceDB copy failed: {e}") from e
    else:
        logger.info("No LanceDB directory found, skipping vector export")

    # Count files
    file_count = sum(1 for _ in snapshot_root.rglob("*") if _.is_file())

    # Build snapshot record
    expires_at = None
    if auto_expire_days is not None:
        expires_at = datetime.now() + timedelta(days=auto_expire_days)

    snapshot = LibrarySnapshot(
        id=snapshot_id,
        library_path=str(library_path),
        library_name=library_name,
        reason=reason,
        initiator=SnapshotInitiatorType(initiator),
        initiator_id=initiator_id,
        run_id=run_id,
        snapshot_path=str(snapshot_root),
        duckdb_path=str(duckdb_export_dir.relative_to(settings.snapshots_dir)),
        lance_path=str(lance_copy_dir.relative_to(settings.snapshots_dir)),
        file_count=file_count,
        duckdb_size_bytes=duckdb_size,
        lance_size_bytes=lance_size,
        expires_at=expires_at,
    )

    # Save snapshot metadata
    _save_snapshot_record(snapshot)

    # Enforce retention policy
    _enforce_retention(library_name)

    logger.info(
        f"Created snapshot {snapshot_id} for {library_name}: {file_count} files"
    )
    return snapshot


def list_snapshots(
    library_name: str | None = None,
    include_expired: bool = False,
) -> list["LibrarySnapshot"]:
    """List snapshots, optionally filtered by library.

    Args:
        library_name: If set, only return snapshots for this library
        include_expired: If False (default), filter out expired snapshots

    Returns:
        List of LibrarySnapshot records, newest first
    """
    snapshots = _load_all_snapshot_records()

    if library_name:
        snapshots = [s for s in snapshots if s.library_name == library_name]

    if not include_expired:
        now = datetime.now()
        snapshots = [s for s in snapshots if s.expires_at is None or s.expires_at > now]

    snapshots.sort(key=lambda s: s.created_at, reverse=True)
    return snapshots


def restore_snapshot(snapshot_id: str) -> dict:
    """Restore a library from a snapshot.

    Restores DuckDB Parquet files back into a new .duckdb file and copies
    LanceDB vectors back. The current library files are NOT overwritten —
    restoration creates new files with a .restored-{timestamp} suffix.

    Args:
        snapshot_id: ID of the snapshot to restore

    Returns:
        Dict with paths to restored db and lance directories

    Raises:
        FileNotFoundError: If snapshot_id not found
    """
    snapshots = _load_all_snapshot_records()
    snapshot = next((s for s in snapshots if s.id == snapshot_id), None)

    if not snapshot:
        raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")

    # duckdb_path and lance_path are relative to snapshots_dir
    db_src = settings.snapshots_dir / snapshot.duckdb_path
    lance_src = settings.snapshots_dir / snapshot.lance_path

    # Restore DuckDB
    restored_db_path = None
    if db_src.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        lib_path = Path(snapshot.library_path)
        restored_db_path = lib_path.parent / f"{lib_path.stem}.restored-{ts}.duckdb"
        restore_conn = duckdb.connect(str(restored_db_path))
        for parquet_file in sorted(db_src.glob("*.parquet")):
            table_name = parquet_file.stem
            restore_conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table_name} AS SELECT * FROM '{parquet_file}'"
            )
        restore_conn.close()
        logger.info(f"Restored DuckDB to {restored_db_path}")

    # Restore LanceDB
    restored_lance_path = None
    if lance_src.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        lib_path = Path(snapshot.library_path)
        restored_lance_path = lib_path.parent / f"{lib_path.stem}.lance.restored-{ts}"
        shutil.copytree(lance_src, restored_lance_path, dirs_exist_ok=True)
        logger.info(f"Restored LanceDB to {restored_lance_path}")

    return {
        "snapshot_id": snapshot_id,
        "library_path": snapshot.library_path,
        "duckdb_restored_path": str(restored_db_path) if restored_db_path else None,
        "lance_restored_path": str(restored_lance_path)
        if restored_lance_path
        else None,
        "note": "Restored files are created alongside originals. Update X-Fichero-Library-Path to use restored library.",
    }


def delete_snapshot(snapshot_id: str) -> bool:
    """Delete a snapshot and its data files.

    Args:
        snapshot_id: ID of the snapshot to delete

    Returns:
        True if deleted, False if not found
    """
    snapshots = _load_all_snapshot_records()
    snapshot = next((s for s in snapshots if s.id == snapshot_id), None)

    if not snapshot:
        return False

    # Remove data files — duckdb_path is "library_name/snapshot_id/duckdb_export"
    snapshot_data_dir = settings.snapshots_dir / snapshot.duckdb_path
    # The snapshot root is the parent of the duckdb_export dir
    snapshot_root = snapshot_data_dir.parent
    if snapshot_root.exists():
        shutil.rmtree(snapshot_root)
        logger.info(f"Deleted snapshot files: {snapshot_root}")

    # Remove record
    _delete_snapshot_record(snapshot_id)
    return True


def _snapshot_records_path() -> "Path":
    """Path to the snapshot metadata JSON file."""
    return settings.snapshots_dir / ".snapshot_records.json"


def _load_all_snapshot_records() -> list["LibrarySnapshot"]:
    """Load all snapshot records from the JSON registry."""


    from fichero.models import LibrarySnapshot, SnapshotInitiatorType

    records_path = _snapshot_records_path()
    if not records_path.exists():
        return []

    try:
        data = json.loads(records_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    snapshots = []
    for raw in data:
        raw["initiator"] = SnapshotInitiatorType(raw.get("initiator", "user"))
        try:
            snapshots.append(LibrarySnapshot(**raw))
        except Exception:
            continue  # Skip corrupted records
    return snapshots


def _save_snapshot_record(snapshot: "LibrarySnapshot") -> None:
    """Save a snapshot record to the JSON registry."""


    records_path = _snapshot_records_path()
    records_path.parent.mkdir(parents=True, exist_ok=True)

    snapshots = _load_all_snapshot_records()
    # Replace existing record with same id, or append
    snapshots = [s for s in snapshots if s.id != snapshot.id]
    snapshots.append(snapshot)

    records_path.write_text(
        json.dumps([s.model_dump(mode="json") for s in snapshots], indent=2)
    )


def _delete_snapshot_record(snapshot_id: str) -> None:
    """Delete a snapshot record from the JSON registry."""


    snapshots = _load_all_snapshot_records()
    snapshots = [s for s in snapshots if s.id != snapshot_id]
    records_path = _snapshot_records_path()

    if snapshots:
        records_path.write_text(
            json.dumps([s.model_dump(mode="json") for s in snapshots], indent=2)
        )
    elif records_path.exists():
        records_path.unlink()


def _enforce_retention(library_name: str) -> int:
    """Delete expired snapshots for a library, respecting pinned status.

    Args:
        library_name: Library to enforce retention for

    Returns:
        Number of snapshots deleted
    """
    snapshots = _load_all_snapshot_records()
    snapshots = [s for s in snapshots if s.library_name == library_name]
    now = datetime.now()

    deleted = 0
    for s in snapshots:
        if s.is_pinned:
            continue
        if s.expires_at is not None and s.expires_at <= now:
            try:
                delete_snapshot(s.id)
                deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete expired snapshot {s.id}: {e}")

    return deleted
