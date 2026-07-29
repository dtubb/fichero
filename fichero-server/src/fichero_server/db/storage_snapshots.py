"""Library snapshot management.

Creates, lists, restores, and deletes point-in-time snapshots of Fichero libraries.
Each snapshot exports DuckDB tables to Parquet and copies the LanceDB vector directory.

Snapshot metadata is stored as JSON alongside snapshot data:
    ~/Library/Application Support/com.fichero.fichero/snapshots/{library_name}/{snapshot_id}/
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import duckdb

from fichero_server.db.library_paths import nfc_path
from fichero_server.security.path_security import resolve_snapshot_record_path
from fichero_server.db.storage import settings  # settings from core storage module

if TYPE_CHECKING:
    from fichero_server.models import LibrarySnapshot

logger = logging.getLogger(__name__)

DEFAULT_RETAINED_SNAPSHOTS = 10


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() and path.is_file() else 0


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return _file_size(path)
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _write_manifest(snapshot_root: Path, manifest: dict) -> None:
    (snapshot_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _quiesce_library_database(library_path: Path, *, close: bool) -> None:
    """Drain/checkpoint manager-owned DuckDB work before file-level operations."""
    from fichero_server.db.manager import db_manager

    db_manager.quiesce_database(library_path, checkpoint=True, close=close)


def _load_known_library_config(library_path: Path):
    """Return the registered KnownLibrary row for a package, if any."""
    from fichero_server.db import Database
    from fichero_server.models import KnownLibrary

    registry_db_path = settings.global_library_path / "fichero.duckdb"
    if not registry_db_path.exists():
        return None

    registry_db = Database(registry_db_path)
    try:
        matches = registry_db.query(
            KnownLibrary,
            path=nfc_path(str(library_path.resolve())),
        )
        return matches[0] if matches else None
    finally:
        registry_db.conn.close()


def _list_scheduled_libraries():
    """Return known libraries that opted into periodic snapshots."""
    from fichero_server.db import Database
    from fichero_server.models import KnownLibrary

    registry_db_path = settings.global_library_path / "fichero.duckdb"
    if not registry_db_path.exists():
        return []

    registry_db = Database(registry_db_path)
    try:
        libraries = registry_db.all(KnownLibrary)
    finally:
        registry_db.conn.close()

    return [lib for lib in libraries if lib.snapshot_interval_seconds > 0]


def _resolve_offsite_dir(
    library_path: Path,
    offsite_dir: str | Path | None,
) -> Path | None:
    if offsite_dir is not None:
        raw_value = str(offsite_dir).strip()
        return Path(raw_value).expanduser() if raw_value else None

    try:
        known_library = _load_known_library_config(library_path)
    except Exception:
        logger.exception("Could not load backup config for %s", library_path)
        return None

    if known_library is None or not known_library.snapshot_offsite_path:
        return None
    return Path(known_library.snapshot_offsite_path).expanduser()


def _copy_snapshot_offsite(
    snapshot_root: Path,
    library_name: str,
    snapshot_id: str,
    offsite_dir: Path,
) -> str:
    """Mirror a completed snapshot into a user-configured filesystem path."""
    target_root = offsite_dir / library_name / snapshot_id
    target_root.parent.mkdir(parents=True, exist_ok=True)
    if target_root.exists():
        shutil.rmtree(target_root)
    shutil.copytree(snapshot_root, target_root)
    return str(target_root)


def snapshot_library(
    library_path: str,
    reason: str = "",
    initiator: str = "user",
    initiator_id: str | None = None,
    run_id: str | None = None,
    auto_expire_days: int | None = None,
    max_snapshots: int = DEFAULT_RETAINED_SNAPSHOTS,
    offsite_dir: str | Path | None = None,
    include_files: bool = False,
) -> "LibrarySnapshot":
    """Create a point-in-time snapshot of a library.

    Exports DuckDB tables to Parquet and copies the LanceDB vector directory.
    Snapshot metadata is stored in app.duckdb and the data lives in:
        ~/Library/Application Support/com.fichero.fichero/snapshots/{library_name}/{snapshot_id}/

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
    from fichero_server.models import LibrarySnapshot, SnapshotInitiatorType

    library_path_p = Path(nfc_path(library_path))
    if not library_path_p.exists():
        raise FileNotFoundError(f"Library not found: {library_path}")

    library_name = nfc_path(library_path_p.stem)  # "MyLibrary" from "MyLibrary.fichero"
    snapshot_id = str(uuid4())

    created_at = datetime.now()

    # Snapshot directory: snapshots/{library_name}/{snapshot_id}/
    snapshot_root = settings.snapshots_dir / library_name / snapshot_id
    duckdb_export_dir = snapshot_root / "duckdb_export"
    duckdb_file_dir = snapshot_root / "duckdb_file"
    vectors_copy_dir = snapshot_root / "vectors_copy"
    lance_copy_dir = snapshot_root / "lance_copy"
    files_copy_dir = snapshot_root / "files_copy"

    snapshot_root.mkdir(parents=True, exist_ok=True)
    duckdb_export_dir.mkdir(parents=True, exist_ok=True)
    duckdb_file_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy the DuckDB file as the restore source and keep the existing
    # Parquet export as a portable diagnostic sidecar for older callers.
    duckdb_size = 0
    db_path = library_path_p / "fichero.duckdb"
    if db_path.exists():
        try:
            _quiesce_library_database(library_path_p, close=False)
            duckdb_copy_path = duckdb_file_dir / "fichero.duckdb"
            shutil.copy2(db_path, duckdb_copy_path)
            duckdb_size = duckdb_copy_path.stat().st_size

            export_conn = duckdb.connect(str(db_path), read_only=True)
            # Get list of tables
            tables = export_conn.execute("SHOW TABLES").fetchall()
            for (table_name,) in tables:
                out_path = duckdb_export_dir / f"{table_name}.parquet"
                safe_out_path = str(out_path).replace("'", "''")
                export_conn.execute(
                    f"COPY {_quote_identifier(table_name)} TO '{safe_out_path}' (FORMAT parquet)"
                )
            export_conn.close()
            logger.info(
                "Copied DuckDB (%0.1f MB) to %s",
                duckdb_size / 1024 / 1024,
                duckdb_copy_path,
            )
        except Exception as e:
            raise RuntimeError(f"DuckDB snapshot failed: {e}") from e
    else:
        logger.warning(f"No DuckDB found at {db_path}, skipping export")

    # 2. Copy LanceDB vectors. Current libraries use "vectors"; older comments
    # and snapshots used "lance", so preserve both when present.
    lance_size = 0
    copied_embeddings: dict[str, str] = {}
    for dirname, target_dir in (("vectors", vectors_copy_dir), ("lance", lance_copy_dir)):
        embedding_src = library_path_p / dirname
        if not embedding_src.exists():
            continue
        try:
            shutil.copytree(embedding_src, target_dir, dirs_exist_ok=True)
            copied_embeddings[dirname] = str(target_dir.relative_to(settings.snapshots_dir))
            lance_size += _dir_size(target_dir)
            logger.info("Copied %s embeddings to %s", dirname, target_dir)
        except Exception as e:
            raise RuntimeError(f"LanceDB copy failed: {e}") from e
    if not copied_embeddings:
        logger.info("No LanceDB directory found, skipping vector export")

    primary_lance_path = copied_embeddings.get("vectors") or copied_embeddings.get("lance")
    if primary_lance_path is None:
        # Keep the model field stable even for libraries with no embeddings.
        vectors_copy_dir.mkdir(parents=True, exist_ok=True)
        primary_lance_path = str(vectors_copy_dir.relative_to(settings.snapshots_dir))

    files_size = 0
    files_path = None
    if include_files:
        originals_dir = library_path_p / "files"
        files_copy_dir.mkdir(parents=True, exist_ok=True)
        if originals_dir.exists():
            shutil.copytree(originals_dir, files_copy_dir, dirs_exist_ok=True)
        files_size = _dir_size(files_copy_dir)
        files_path = str(files_copy_dir.relative_to(settings.snapshots_dir))

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
        duckdb_path=str(duckdb_file_dir.relative_to(settings.snapshots_dir)),
        lance_path=primary_lance_path,
        files_path=files_path,
        includes_files=include_files,
        offsite_path=None,
        file_count=file_count,
        duckdb_size_bytes=duckdb_size,
        lance_size_bytes=lance_size,
        files_size_bytes=files_size,
        created_at=created_at,
        expires_at=expires_at,
    )

    manifest = {
        "id": snapshot_id,
        "created_at": created_at.isoformat(),
        "library_path": str(library_path_p),
        "library_name": library_name,
        "reason": reason,
        "initiator": initiator,
        "initiator_id": initiator_id,
        "run_id": run_id,
        "paths": {
            "duckdb": snapshot.duckdb_path,
            "duckdb_export": str(duckdb_export_dir.relative_to(settings.snapshots_dir)),
            "embeddings": copied_embeddings,
            "files": files_path,
            "offsite": None,
        },
        "sizes": {
            "duckdb_size_bytes": duckdb_size,
            "lance_size_bytes": lance_size,
            "files_size_bytes": files_size,
            "total_size_bytes": duckdb_size + lance_size + files_size,
        },
        "includes_files": include_files,
        "file_count": file_count,
    }
    _write_manifest(snapshot_root, manifest)
    snapshot.file_count = sum(1 for _ in snapshot_root.rglob("*") if _.is_file())

    resolved_offsite_dir = _resolve_offsite_dir(library_path_p, offsite_dir)
    if resolved_offsite_dir is not None:
        try:
            snapshot.offsite_path = _copy_snapshot_offsite(
                snapshot_root,
                library_name,
                snapshot_id,
                resolved_offsite_dir,
            )
            manifest["paths"]["offsite"] = snapshot.offsite_path
            _write_manifest(snapshot_root, manifest)
        except Exception as exc:
            logger.warning(
                "Offsite snapshot mirror failed for %s to %s: %s",
                library_path_p,
                resolved_offsite_dir,
                exc,
            )

    # Save snapshot metadata
    _save_snapshot_record(snapshot)

    # Enforce retention policy
    _enforce_retention(library_name, max_snapshots=max_snapshots)

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

    Restores the captured DuckDB file and LanceDB vectors into the original
    library package. Current files are first moved aside with a
    .pre-restore-{timestamp} suffix so restore never deletes the user's
    pre-restore data.

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

    lib_path = Path(snapshot.library_path)
    if not lib_path.exists():
        raise FileNotFoundError(f"Library not found: {lib_path}")

    # Drain/checkpoint and drop cached connections before swapping files.
    # Existing open OS handles may still read the old inode, but new
    # DatabaseManager calls will reopen the restored files.
    try:
        _quiesce_library_database(lib_path, close=True)
    except Exception as exc:
        raise RuntimeError(f"Could not quiesce database before restore: {exc}") from exc

    try:
        db_src_dir = resolve_snapshot_record_path(
            settings.snapshots_dir, snapshot.duckdb_path
        )
        lance_src = resolve_snapshot_record_path(
            settings.snapshots_dir, snapshot.lance_path
        )
    except ValueError as exc:
        raise FileNotFoundError(str(exc)) from exc
    db_src = db_src_dir / "fichero.duckdb" if db_src_dir.is_dir() else db_src_dir
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    current_db_path = lib_path / "fichero.duckdb"
    restored_db_path = current_db_path if db_src.exists() else None
    db_backup_path = None
    db_backup_candidate = None
    tmp_db_path = None
    if db_src.exists():
        tmp_db_path = lib_path / f".fichero.duckdb.restore-{ts}.tmp"
        db_backup_candidate = lib_path / f"fichero.duckdb.pre-restore-{ts}"
        shutil.copy2(db_src, tmp_db_path)

    restored_lance_path = None
    lance_backup_path = None
    lance_backup_candidate = None
    tmp_lance_path = None
    current_lance_path = lib_path / "vectors"
    if lance_src.exists():
        tmp_lance_path = lib_path / f".vectors.restore-{ts}.tmp"
        lance_backup_candidate = lib_path / f"vectors.pre-restore-{ts}"
        if tmp_lance_path.exists():
            shutil.rmtree(tmp_lance_path)
        shutil.copytree(lance_src, tmp_lance_path)

    restored_files_path = None
    files_backup_path = None
    files_backup_candidate = None
    tmp_files_path = None
    current_files_path = lib_path / "files"
    if snapshot.includes_files:
        if not snapshot.files_path:
            raise FileNotFoundError(
                f"Snapshot {snapshot_id} does not include a files/ copy"
            )
        try:
            files_src = resolve_snapshot_record_path(
                settings.snapshots_dir, snapshot.files_path
            )
        except ValueError as exc:
            raise FileNotFoundError(str(exc)) from exc
        if not files_src.exists():
            raise FileNotFoundError(
                f"Snapshot {snapshot_id} is missing files/ data at {files_src}"
            )
        tmp_files_path = lib_path / f".files.restore-{ts}.tmp"
        files_backup_candidate = lib_path / f"files.pre-restore-{ts}"
        if tmp_files_path.exists():
            shutil.rmtree(tmp_files_path)
        shutil.copytree(files_src, tmp_files_path)

    try:
        if tmp_db_path is not None:
            assert db_backup_candidate is not None
            assert restored_db_path is not None
            if current_db_path.exists():
                os.replace(current_db_path, db_backup_candidate)
                db_backup_path = db_backup_candidate
            os.replace(tmp_db_path, current_db_path)
            logger.info(
                "Restored DuckDB snapshot %s to %s", snapshot_id, current_db_path
            )

        if tmp_lance_path is not None:
            assert lance_backup_candidate is not None
            if current_lance_path.exists():
                os.replace(current_lance_path, lance_backup_candidate)
                lance_backup_path = lance_backup_candidate
            os.replace(tmp_lance_path, current_lance_path)
            restored_lance_path = current_lance_path
            logger.info(
                "Restored LanceDB snapshot %s to %s", snapshot_id, current_lance_path
            )

        if tmp_files_path is not None:
            assert files_backup_candidate is not None
            if current_files_path.exists():
                os.replace(current_files_path, files_backup_candidate)
                files_backup_path = files_backup_candidate
            os.replace(tmp_files_path, current_files_path)
            restored_files_path = current_files_path
            logger.info(
                "Restored files snapshot %s to %s", snapshot_id, current_files_path
            )
    except Exception:
        if tmp_db_path is not None and tmp_db_path.exists():
            tmp_db_path.unlink()
        if tmp_lance_path is not None and tmp_lance_path.exists():
            shutil.rmtree(tmp_lance_path)
        if tmp_files_path is not None and tmp_files_path.exists():
            shutil.rmtree(tmp_files_path)
        if db_backup_path is not None and db_backup_path.exists() and current_db_path.exists():
            current_db_path.unlink()
        if db_backup_path is not None and db_backup_path.exists():
            os.replace(db_backup_path, current_db_path)
        if (
            lance_backup_path is not None
            and lance_backup_path.exists()
            and current_lance_path.exists()
        ):
            shutil.rmtree(current_lance_path)
        if lance_backup_path is not None and lance_backup_path.exists():
            os.replace(lance_backup_path, current_lance_path)
        if (
            files_backup_path is not None
            and files_backup_path.exists()
            and current_files_path.exists()
        ):
            shutil.rmtree(current_files_path)
        if files_backup_path is not None and files_backup_path.exists():
            os.replace(files_backup_path, current_files_path)
        raise

    return {
        "snapshot_id": snapshot_id,
        "library_path": snapshot.library_path,
        "duckdb_restored_path": str(restored_db_path) if restored_db_path else None,
        "lance_restored_path": str(restored_lance_path)
        if restored_lance_path
        else None,
        "duckdb_backup_path": str(db_backup_path) if db_backup_path else None,
        "lance_backup_path": str(lance_backup_path) if lance_backup_path else None,
        "files_restored_path": str(restored_files_path) if restored_files_path else None,
        "files_backup_path": str(files_backup_path) if files_backup_path else None,
        "note": "Restored snapshot into the library package. Pre-restore files were kept with .pre-restore suffixes.",
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
    from fichero_server.models import LibrarySnapshot, SnapshotInitiatorType

    records_path = _snapshot_records_path()
    if not records_path.exists():
        return []

    try:
        data = json.loads(records_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        # An unreadable/corrupt registry is NOT the same as "no snapshots" —
        # silently returning [] masks data loss (the #2430 class of bug, #2507).
        # Log it loudly; callers still get a resilient empty list.
        logger.warning(
            "Could not read snapshot registry at %s: %s", records_path, exc
        )
        return []

    snapshots = []
    for raw in data:
        raw["initiator"] = SnapshotInitiatorType(raw.get("initiator", "user"))
        try:
            snapshots.append(LibrarySnapshot(**raw))
        except Exception as exc:
            # Skip a corrupted record, but say which one — dropping it silently
            # hides the data problem from the user (#2507).
            logger.warning(
                "Skipping corrupted snapshot record %s: %s",
                raw.get("id", "<unknown>"),
                exc,
            )
            continue
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


def _enforce_retention(
    library_name: str,
    *,
    max_snapshots: int = DEFAULT_RETAINED_SNAPSHOTS,
) -> int:
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

    snapshots = [
        s
        for s in _load_all_snapshot_records()
        if s.library_name == library_name and not s.is_pinned
    ]
    snapshots.sort(key=lambda s: s.created_at, reverse=True)
    if max_snapshots > 0:
        for s in snapshots[max_snapshots:]:
            try:
                delete_snapshot(s.id)
                deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete retained snapshot {s.id}: {e}")

    return deleted


def auto_snapshot_before_risky_operation(
    library_path: str | Path,
    *,
    reason: str,
    initiator: str = "system",
    include_files: bool = False,
) -> "LibrarySnapshot | None":
    """Best-effort helper for callers to run before destructive operations."""
    try:
        return snapshot_library(
            str(library_path),
            reason=reason,
            initiator=initiator,
            auto_expire_days=14,
            include_files=include_files,
        )
    except Exception as exc:
        logger.warning(
            "Auto-snapshot skipped before risky operation for %s: %s",
            library_path,
            exc,
        )
        return None


def has_scheduled_snapshots_enabled() -> bool:
    """True when at least one known library opted into periodic snapshots."""
    try:
        return any(_list_scheduled_libraries())
    except Exception:
        logger.exception("Could not inspect scheduled snapshot configuration")
        return False


def run_due_scheduled_snapshots(
    *,
    now: datetime | None = None,
) -> list["LibrarySnapshot"]:
    """Create any periodic snapshots that are currently due."""
    current_time = now or datetime.now()
    created: list["LibrarySnapshot"] = []

    for library in _list_scheduled_libraries():
        library_path = Path(nfc_path(library.path)).expanduser()
        if library_path.suffix != ".fichero":
            logger.warning("Skipping scheduled snapshot for non-library path: %s", library_path)
            continue
        if not library_path.exists():
            logger.warning("Skipping scheduled snapshot for missing library: %s", library_path)
            continue

        latest_snapshot = next(
            iter(
                list_snapshots(
                    library_name=nfc_path(library_path.stem),
                    include_expired=True,
                )
            ),
            None,
        )
        if latest_snapshot is not None:
            next_due_at = latest_snapshot.created_at + timedelta(
                seconds=library.snapshot_interval_seconds
            )
            if next_due_at > current_time:
                continue

        try:
            created.append(
                snapshot_library(
                    str(library_path),
                    reason="scheduled periodic snapshot",
                    initiator="system",
                    max_snapshots=max(library.snapshot_retention_count, 0),
                    offsite_dir=library.snapshot_offsite_path,
                )
            )
        except Exception:
            logger.exception("Scheduled snapshot failed for %s", library_path)

    return created


async def periodic_snapshot_loop(
    *,
    poll_interval_seconds: float | None = None,
) -> None:
    """Background loop that runs due scheduled snapshots until cancelled."""
    interval = poll_interval_seconds
    if interval is None:
        interval = getattr(settings, "scheduled_snapshot_poll_interval_seconds", 60.0)
    interval = max(float(interval), 0.01)

    while True:
        run_due_scheduled_snapshots()
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Periodic snapshot loop cancelled")
            raise


def start_periodic_snapshot_task() -> asyncio.Task[None] | None:
    """Create the background periodic snapshot task when any library opted in."""
    if not has_scheduled_snapshots_enabled():
        return None
    return asyncio.create_task(periodic_snapshot_loop())


async def stop_periodic_snapshot_task(task: asyncio.Task[None] | None) -> None:
    """Cancel and await the periodic snapshot task."""
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
