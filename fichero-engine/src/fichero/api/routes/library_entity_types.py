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

from fastapi import APIRouter, Depends, HTTPException

from fichero.db import Database, DatabaseManager, db_manager
from fichero.knowledge_models import LibraryEntityType
from fichero.models import LibraryEntityTypeListResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_db_manager() -> DatabaseManager:
    """Dependency: return the global database manager."""
    return db_manager


def _get_library_db(lib_encoded: str, db_manager: DatabaseManager) -> Database:
    """Resolve library path from URL parameter and return its database."""
    lib_path = unquote(lib_encoded)
    try:
        return db_manager.get_database(lib_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Library not found: {lib_path}") from e


@router.get(
    "/libraries/{lib}/entity-types",
    response_model=LibraryEntityTypeListResponse,
    tags=["library"],
)
def list_library_entity_types(
    lib: str,
    db_manager: DatabaseManager = Depends(_get_db_manager),
) -> LibraryEntityTypeListResponse:
    """List entity types enabled for a library.

    Args:
        lib: URL-encoded library path

    Returns:
        List of LibraryEntityType entries for this library.
    """
    db = _get_library_db(lib, db_manager)
    try:
        items = db.query(LibraryEntityType).filter(
            LibraryEntityType.library_id == lib
        ).all()
        return LibraryEntityTypeListResponse(items=items, count=len(items))
    except Exception as e:
        logger.error("Failed to list entity types for library %s: %s", lib, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/libraries/{lib}/entity-types",
    response_model=LibraryEntityType,
    tags=["library"],
)
def add_library_entity_type(
    lib: str,
    entity_type_key: str,
    enabled: bool = True,
    db_manager: DatabaseManager = Depends(_get_db_manager),
) -> LibraryEntityType:
    """Add an entity type to a library's enabled set.

    Args:
        lib: URL-encoded library path
        entity_type_key: Machine-readable entity type key from ClassificationValue
        enabled: Whether this type is active for extraction (default: True)

    Returns:
        The created LibraryEntityType entry.
    """
    db = _get_library_db(lib, db_manager)
    try:
        # Check if already exists
        existing = db.query(LibraryEntityType).filter(
            LibraryEntityType.library_id == lib,
            LibraryEntityType.entity_type_key == entity_type_key,
        ).first()
        if existing:
            # Update enabled status if re-adding
            existing.enabled = enabled
            db.session.add(existing)
            db.session.commit()
            db.session.refresh(existing)
            return existing

        # Create new entry
        item = LibraryEntityType(
            library_id=lib,
            entity_type_key=entity_type_key,
            enabled=enabled,
        )
        db.session.add(item)
        db.session.commit()
        db.session.refresh(item)
        return item
    except Exception as e:
        logger.error(
            "Failed to add entity type %s to library %s: %s",
            entity_type_key,
            lib,
            e,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete(
    "/libraries/{lib}/entity-types/{entity_type_key}",
    status_code=204,
    tags=["library"],
)
def remove_library_entity_type(
    lib: str,
    entity_type_key: str,
    db_manager: DatabaseManager = Depends(_get_db_manager),
) -> None:
    """Remove an entity type from a library's enabled set.

    Args:
        lib: URL-encoded library path
        entity_type_key: Machine-readable entity type key to remove
    """
    db = _get_library_db(lib, db_manager)
    try:
        item = db.query(LibraryEntityType).filter(
            LibraryEntityType.library_id == lib,
            LibraryEntityType.entity_type_key == entity_type_key,
        ).first()
        if not item:
            raise HTTPException(
                status_code=404,
                detail=f"Entity type {entity_type_key} not found for library",
            )
        db.session.delete(item)
        db.session.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to remove entity type %s from library %s: %s",
            entity_type_key,
            lib,
            e,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e
