"""Library snapshot management.

Creates, lists, restores, and deletes point-in-time snapshots of Fichero libraries.
Each snapshot exports DuckDB tables to Parquet and copies the LanceDB vector directory.

Snapshot metadata is stored as JSON alongside snapshot data:
    ~/Library/Application Support/com.tubb.fichero/snapshots/{library_name}/{snapshot_id}/
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import duckdb

from fichero.storage import settings  # settings from core storage module

if TYPE_CHECKING:
    from fichero.models import LibrarySnapshot

logger = logging.getLogger(__name__)


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


def _snapshot_records_path() -> Path:
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
