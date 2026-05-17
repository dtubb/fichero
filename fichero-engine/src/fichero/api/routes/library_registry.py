"""Known library registry persistence (#1131).

Endpoints for managing the backend's registry of known .fichero libraries.
The registry enables CLI operations like listing available libraries and
switching between them.

Endpoints:
  GET /api/registry                 — List all known libraries
  POST /api/registry/add            — Add a library path to registry
  POST /api/registry/update-access  — Mark library as accessed (for sorting)
  DELETE /api/registry/{path}       — Remove from registry
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import KnownLibrary, LibraryRegistryResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/registry", response_model=LibraryRegistryResponse)
def list_known_libraries(db: Database = Depends(get_library_database)) -> LibraryRegistryResponse:
    """List all known libraries in the registry.

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


@router.post("/registry/add", response_model=KnownLibrary)
def add_known_library(
    path: str,
    name: str | None = None,
    db: Database = Depends(get_library_database),
) -> KnownLibrary:
    """Add a library path to the known libraries registry.

    Args:
        path: Absolute path to the .fichero package (must be expanded already)
        name: Optional display name (defaults to package basename)
        db: Database instance injected by FastAPI

    Returns:
        The KnownLibrary record that was created or updated.

    Raises:
        400: If path is invalid or not a .fichero package
        500: If database operation fails
    """
    # Validate path
    pkg_path = Path(path).expanduser().resolve()
    if not pkg_path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")

    # Verify it's a .fichero package
    if not pkg_path.name.endswith(".fichero"):
        raise HTTPException(
            status_code=400,
            detail="Path must be a .fichero package (directory ending in .fichero)",
        )

    try:
        # Check if already registered
        existing = db.query(KnownLibrary, path=str(pkg_path))
        if existing:
            # Update last_accessed
            lib = existing[0]
            lib.last_accessed = datetime.now()
            db.save(lib)
            return lib

        # Create new registration
        if name is None:
            name = pkg_path.name  # e.g. "My Library.fichero" → "My Library.fichero"

        library = KnownLibrary(
            path=str(pkg_path),
            name=name,
            added_at=datetime.now(),
            last_accessed=datetime.now(),
        )
        db.save(library)
        return library
    except Exception as e:
        logger.error("Failed to add known library: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/registry/update-access")
def update_library_access(
    path: str,
    db: Database = Depends(get_library_database),
) -> KnownLibrary:
    """Mark a library as accessed (update last_accessed timestamp).

    Used by CLI to track which libraries the user works with, enabling
    sorting by recency in list operations.

    Args:
        path: Absolute path to the .fichero package
        db: Database instance injected by FastAPI

    Returns:
        The updated KnownLibrary record

    Raises:
        404: If the library is not in the registry
        500: If database operation fails
    """
    pkg_path = Path(path).expanduser().resolve()

    try:
        existing = db.query(KnownLibrary, path=str(pkg_path))
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Library not in registry: {path}",
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


@router.delete("/registry/{library_path}")
def remove_known_library(
    library_path: str,
    db: Database = Depends(get_library_database),
) -> dict:
    """Remove a library from the known libraries registry.

    The library path is URL-encoded in the route param. Returns empty
    response with 204 on success.

    Args:
        library_path: URL-encoded absolute path to the .fichero package
        db: Database instance injected by FastAPI

    Raises:
        404: If the library is not in the registry
        500: If database operation fails
    """
    # Decode the URL-encoded path
    path = unquote(library_path)
    pkg_path = Path(path).expanduser().resolve()

    try:
        existing = db.query(KnownLibrary, path=str(pkg_path))
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Library not in registry: {path}",
            )

        library = existing[0]
        db.delete(library)
        return {"status": "removed", "path": str(pkg_path)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to remove known library: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
