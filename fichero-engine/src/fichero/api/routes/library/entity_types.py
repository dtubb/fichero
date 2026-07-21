"""Per-library entity type customization (#874).

Endpoints for managing which entity types are enabled for extraction in each library.
Enables each library to define its own taxonomy without code changes.

Endpoints:
  GET /api/libraries/{lib}/entity-types          — List entity types for a library
  POST /api/libraries/{lib}/entity-types         — Add an entity type to a library
  DELETE /api/libraries/{lib}/entity-types/{key} — Remove an entity type from a library
"""

from __future__ import annotations

import logging
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request

from fichero.security import authz
from fichero.api.main import _is_allowed_library_path
from fichero.db import Database, DatabaseManager, db_manager
from fichero.knowledge_models import LibraryEntityType
from fichero.models import LibraryEntityTypeListResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_db_manager() -> DatabaseManager:
    """Dependency: return the global database manager."""
    return db_manager


def _get_library_db(
    request: Request,
    lib_encoded: str,
    db_mgr: DatabaseManager,
    *,
    write: bool,
) -> Database:
    """Resolve, validate, authorize, and return a library database."""
    lib_path = unquote(lib_encoded)
    if not _is_allowed_library_path(lib_path):
        raise HTTPException(
            status_code=403,
            detail="Library path is not in an allowed location or not a .fichero package.",
        )

    user = getattr(getattr(request, "state", None), "user", None)
    try:
        if write:
            authz.assert_can_write(user, lib_path)
        else:
            authz.assert_can_read(user, lib_path)
    except authz.AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    try:
        return db_mgr.get_database(lib_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Library not found: {lib_path}") from e


@router.get(
    "/libraries/{lib:path}/entity-types",
    response_model=LibraryEntityTypeListResponse,
    tags=["library"],
)
def list_library_entity_types(
    request: Request,
    lib: str,
    db_mgr: DatabaseManager = Depends(_get_db_manager),
) -> LibraryEntityTypeListResponse:
    """List entity types enabled for a library.

    Args:
        lib: URL-encoded library path

    Returns:
        List of LibraryEntityType entries for this library.
    """
    lib_path = unquote(lib)
    db = _get_library_db(request, lib, db_mgr, write=False)
    try:
        items = db.query(LibraryEntityType, library_id=lib_path)
        return LibraryEntityTypeListResponse(items=items, count=len(items))
    except Exception as e:
        logger.error("Failed to list entity types for library %s: %s", lib_path, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/libraries/{lib:path}/entity-types",
    response_model=LibraryEntityType,
    tags=["library"],
)
def add_library_entity_type(
    request: Request,
    lib: str,
    entity_type_key: str,
    enabled: bool = True,
    db_mgr: DatabaseManager = Depends(_get_db_manager),
) -> LibraryEntityType:
    """Add an entity type to a library's enabled set.

    Args:
        lib: URL-encoded library path
        entity_type_key: Machine-readable entity type key from ClassificationValue
        enabled: Whether this type is active for extraction (default: True)

    Returns:
        The created LibraryEntityType entry.
    """
    lib_path = unquote(lib)
    db = _get_library_db(request, lib, db_mgr, write=True)
    try:
        # Check if already exists
        matches = db.query(
            LibraryEntityType,
            library_id=lib_path,
            entity_type_key=entity_type_key,
        )
        if matches:
            existing = matches[0]
            # Update enabled status if re-adding
            existing.enabled = enabled
            db.save(existing)
            return existing

        # Create new entry
        item = LibraryEntityType(
            library_id=lib_path,
            entity_type_key=entity_type_key,
            enabled=enabled,
        )
        db.save(item)
        return item
    except Exception as e:
        logger.error(
            "Failed to add entity type %s to library %s: %s",
            entity_type_key,
            lib_path,
            e,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete(
    "/libraries/{lib:path}/entity-types/{entity_type_key}",
    status_code=204,
    tags=["library"],
)
def remove_library_entity_type(
    request: Request,
    lib: str,
    entity_type_key: str,
    db_mgr: DatabaseManager = Depends(_get_db_manager),
) -> None:
    """Remove an entity type from a library's enabled set.

    Args:
        lib: URL-encoded library path
        entity_type_key: Machine-readable entity type key to remove
    """
    lib_path = unquote(lib)
    db = _get_library_db(request, lib, db_mgr, write=True)
    try:
        matches = db.query(
            LibraryEntityType,
            library_id=lib_path,
            entity_type_key=entity_type_key,
        )
        if not matches:
            raise HTTPException(
                status_code=404,
                detail=f"Entity type {entity_type_key} not found for library",
            )
        db.delete(matches[0])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to remove entity type %s from library %s: %s",
            entity_type_key,
            lib_path,
            e,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e
