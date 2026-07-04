"""Known library registry persistence (#1131, #1661).

Endpoints for managing the backend's registry of known .fichero libraries.
The registry enables CLI operations like listing available libraries and
switching between them, and the SwiftUI sidebar's "Close Library" action.

The registry is GLOBAL — it records every .fichero package the app/CLI has
opened, independent of which library is currently active. It is therefore
stored in the engine's global library database (``settings.global_library_path``)
and these endpoints do NOT require an ``X-Fichero-Library-Path`` header.

Endpoints:
  GET /api/registry                 — List all known libraries
  POST /api/registry/add            — Add a library path to registry
  POST /api/registry/update-access  — Mark library as accessed (for sorting)
  DELETE /api/registry/{path}       — Remove from registry (idempotent)
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request

from fichero.db import Database
from fichero.db_manager import db_manager
from fichero.library_paths import nfc_path
from fichero.models import (
    KnownLibrary,
    LibraryRegistryResponse,
    UnicodeLibraryCollision,
    UnicodeLibraryCollisionIdentity,
    UnicodeLibraryCollisionResponse,
)
from fichero.storage import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _escape_visible(value: str) -> str:
    return value.encode("unicode_escape").decode("ascii")


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(entry.stat().st_size for entry in path.rglob("*") if entry.is_file())


def _document_count(package_path: Path) -> int:
    from fichero.models import Document

    if not (package_path / "fichero.duckdb").exists():
        return 0
    try:
        db = db_manager.get_database(package_path)
        return sum(
            1
            for doc in db.all(Document)
            if getattr(doc, "deleted_at", None) is None
        )
    except Exception:
        return 0


def _identity_report(raw_path: str) -> UnicodeLibraryCollisionIdentity:
    package_path = Path(raw_path).expanduser()
    resolved_name = package_path.name
    modified_at = None
    try:
        stat = os.stat(package_path)
        modified_at = datetime.fromtimestamp(stat.st_mtime)
    except OSError:
        pass
    return UnicodeLibraryCollisionIdentity(
        raw_path=raw_path,
        raw_path_escaped=_escape_visible(raw_path),
        name=resolved_name,
        name_escaped=_escape_visible(resolved_name),
        document_count=_document_count(package_path),
        duckdb_size_bytes=(package_path / "fichero.duckdb").stat().st_size
        if (package_path / "fichero.duckdb").exists()
        else 0,
        files_size_bytes=_dir_size(package_path / "files"),
        modified_at=modified_at,
    )


def _same_inode(left: str, right: str) -> bool:
    try:
        left_stat = os.stat(Path(left).expanduser())
        right_stat = os.stat(Path(right).expanduser())
    except OSError:
        return False
    return (
        left_stat.st_dev == right_stat.st_dev
        and left_stat.st_ino == right_stat.st_ino
    )


def _build_collision(left: str, right: str) -> UnicodeLibraryCollision:
    left_identity = _identity_report(left)
    right_identity = _identity_report(right)
    left_path = Path(left).expanduser()
    return UnicodeLibraryCollision(
        left=left_identity,
        right=right_identity,
        nfc_path=nfc_path(left),
        nfc_name=nfc_path(left_path.name),
        collision_case="case_a_same_inode"
        if _same_inode(left, right)
        else "case_b_distinct_packages",
    )


def _registry_collision_paths(libraries: list[KnownLibrary]) -> list[tuple[str, str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for library in libraries:
        grouped[nfc_path(library.path)].append(library.path)
    pairs: list[tuple[str, str]] = []
    for paths in grouped.values():
        unique = sorted({path for path in paths if path})
        if len(unique) < 2:
            continue
        for index, left in enumerate(unique):
            for right in unique[index + 1 :]:
                pairs.append((left, right))
    return pairs


def _sibling_collision_paths(libraries: list[KnownLibrary]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen_parents: set[Path] = set()
    for library in libraries:
        package_path = Path(library.path).expanduser()
        parent = package_path.parent
        if parent in seen_parents or not parent.exists():
            continue
        seen_parents.add(parent)
        grouped: dict[str, list[str]] = defaultdict(list)
        for sibling in parent.glob("*.fichero"):
            grouped[nfc_path(sibling.name)].append(str(sibling))
        for siblings in grouped.values():
            unique = sorted({path for path in siblings if path})
            if len(unique) < 2:
                continue
            for index, left in enumerate(unique):
                for right in unique[index + 1 :]:
                    pairs.append((left, right))
    return pairs


def _detect_unicode_library_collisions(libraries: list[KnownLibrary]) -> list[UnicodeLibraryCollision]:
    collisions: list[UnicodeLibraryCollision] = []
    seen_pairs: set[tuple[str, str]] = set()
    for left, right in _registry_collision_paths(libraries) + _sibling_collision_paths(libraries):
        if left == right or nfc_path(left) != nfc_path(right):
            continue
        pair = tuple(sorted((left, right)))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        collisions.append(_build_collision(left, right))
    collisions.sort(key=lambda collision: (collision.nfc_name, collision.left.raw_path))
    return collisions


def get_global_database() -> Database:
    """FastAPI dependency: return the engine's GLOBAL library database.

    The known-library registry is app-wide, not scoped to any one library,
    so it lives in the global library package (``global.fichero``) and is
    reachable with no ``X-Fichero-Library-Path`` header. The package and its
    DuckDB file are created on first access by the DatabaseManager.
    """
    return db_manager.get_database(str(settings.global_library_path))


@router.get("/registry", response_model=LibraryRegistryResponse)
def list_known_libraries(
    db: Database = Depends(get_global_database),
) -> LibraryRegistryResponse:
    """List all known libraries in the global registry.

    Returns libraries sorted by last_accessed descending, with most
    recently accessed libraries first for CLI "recent" list UX.
    """
    try:
        libraries = db.all(KnownLibrary)
        # Sort by last_accessed descending (most recent first)
        libraries = sorted(
            libraries,
            key=lambda lib: lib.last_accessed or datetime.now(),
            reverse=True,
        )
        return LibraryRegistryResponse(libraries=libraries, count=len(libraries))
    except Exception as e:
        logger.error("Failed to list known libraries: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/registry/unicode-collisions", response_model=UnicodeLibraryCollisionResponse)
def list_unicode_library_collisions(
    db: Database = Depends(get_global_database),
) -> UnicodeLibraryCollisionResponse:
    """Report Unicode-normalization collisions across known libraries."""
    try:
        libraries = db.all(KnownLibrary)
        collisions = _detect_unicode_library_collisions(libraries)
        return UnicodeLibraryCollisionResponse(collisions=collisions, count=len(collisions))
    except Exception as e:
        logger.error("Failed to scan library Unicode collisions: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/registry/add", response_model=KnownLibrary)
def add_known_library(
    request: Request,
    path: str,
    name: str | None = None,
    db: Database = Depends(get_global_database),
) -> KnownLibrary:
    """Add a library path to the global known-libraries registry.

    Args:
        path: Absolute path to the .fichero package (must be expanded already)
        name: Optional display name (defaults to package basename)
        db: Global registry database injected by FastAPI

    Returns:
        The KnownLibrary record that was created or updated.

    Raises:
        400: If path is invalid or not a .fichero package
        500: If database operation fails
    """
    # Validate path
    normalized_path = nfc_path(path)
    pkg_path = Path(normalized_path).expanduser().resolve()
    if not pkg_path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {normalized_path}")

    # Verify it's a .fichero package
    if not pkg_path.name.endswith(".fichero"):
        raise HTTPException(
            status_code=400,
            detail="Path must be a .fichero package (directory ending in .fichero)",
        )

    try:
        # Check if already registered
        stored_path = nfc_path(str(pkg_path))
        existing = db.query(KnownLibrary, path=stored_path)
        if existing:
            # Update last_accessed
            lib = existing[0]
            lib.last_accessed = datetime.now()
            db.save(lib)
            library = lib
        else:
            # Create new registration
            if name is None:
                name = Path(stored_path).name

            library = KnownLibrary(
                path=stored_path,
                name=nfc_path(name),
                added_at=datetime.now(),
                last_accessed=datetime.now(),
            )
            db.save(library)

        try:
            db_manager.get_database(stored_path)
        except Exception as exc:
            logger.warning("Inbox seeding skipped for %s: %s", pkg_path, exc)

        return library
    except Exception as e:
        logger.error("Failed to add known library: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/registry/update-access")
def update_library_access(
    path: str,
    db: Database = Depends(get_global_database),
) -> KnownLibrary:
    """Mark a library as accessed (update last_accessed timestamp).

    Used by CLI to track which libraries the user works with, enabling
    sorting by recency in list operations.

    Args:
        path: Absolute path to the .fichero package
        db: Global registry database injected by FastAPI

    Returns:
        The updated KnownLibrary record

    Raises:
        404: If the library is not in the registry
        500: If database operation fails
    """
    normalized_path = nfc_path(path)
    pkg_path = Path(normalized_path).expanduser().resolve()
    stored_path = nfc_path(str(pkg_path))

    try:
        existing = db.query(KnownLibrary, path=stored_path)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Library not in registry: {normalized_path}",
            )

        library = existing[0]
        library.last_accessed = datetime.now()
        db.save(library)
        return library
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update library access: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/registry/{library_path:path}")
def remove_known_library(
    library_path: str,
    db: Database = Depends(get_global_database),
) -> dict:
    """Remove a library from the global known-libraries registry.

    The library path is URL-encoded in the route param (handles spaces).
    Idempotent: removing a path that isn't registered is a no-op that still
    returns 200, so the SwiftUI "Close Library" action and the CLI can close
    a library without worrying about stale state.

    Args:
        library_path: URL-encoded absolute path to the .fichero package
        db: Global registry database injected by FastAPI

    Raises:
        500: If the database operation fails
    """
    # Decode the URL-encoded path (handles spaces and other reserved chars)
    path = nfc_path(unquote(library_path))
    pkg_path = Path(path).expanduser().resolve()
    stored_path = nfc_path(str(pkg_path))

    try:
        existing = db.query(KnownLibrary, path=stored_path)
        if not existing:
            # Idempotent no-op — the library is already absent from the registry.
            logger.info("Library not in registry (no-op remove): %s", pkg_path)
            return {"status": "not_registered", "path": stored_path}

        for library in existing:
            db.delete(library)
        return {"status": "removed", "path": stored_path}
    except Exception as e:
        logger.error("Failed to remove known library: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
