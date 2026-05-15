"""Library bootstrap route.

``POST /api/library`` — create a fresh ``.fichero`` package on disk and
initialize its DuckDB schema. Built for the CLI bootstrap loop
(``fichero library create -> import -> run workflows``) so a tester can
spin up a brand-new library from the terminal without going through
SwiftUI's NSDocument flow.

The path is validated against the same allowlist used everywhere else
(``_is_allowed_library_path`` in :mod:`fichero.api.main`) — we don't
let arbitrary filesystem paths through, even though this endpoint
"creates" a directory.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from fichero.db import db_manager
from fichero.models import LibraryCreateRequest, LibraryCreateResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/library", response_model=LibraryCreateResponse)
def create_library(request: LibraryCreateRequest) -> LibraryCreateResponse:
    """Create a new ``.fichero`` package (or report it already exists).

    Behaviour:
      * Validates ``request.path`` against the allowlist (403 on miss).
      * If the package directory already contains a ``fichero.duckdb``,
        returns ``created=False`` without touching the filesystem.
      * Otherwise creates the package directory plus ``files/`` and
        ``vectors/`` subdirs, then triggers schema initialization by
        calling ``db_manager.get_database(path)`` (which also runs all
        migrations and seeds default workflows).
    """
    # Local import to avoid a circular dependency at module load time —
    # api.main imports the routes package, and importing api.main here
    # would close that loop.
    from fichero.api.main import _is_allowed_library_path

    raw = request.path
    if not _is_allowed_library_path(raw):
        raise HTTPException(
            status_code=403,
            detail=(
                "Library path is not in an allowed location or not a "
                ".fichero package."
            ),
        )

    package = Path(raw).expanduser().resolve()
    duckdb_path = package / "fichero.duckdb"

    already_existed = package.exists() and duckdb_path.exists()

    if not already_existed:
        try:
            package.mkdir(parents=True, exist_ok=True)
            (package / "files").mkdir(exist_ok=True)
            # SwiftUI's NSDocument bootstrap calls this dir "lance"; keep
            # parity so anything that introspects the package works the
            # same regardless of who created it. The task requested
            # "vectors/" — we create both to be friendly to either name
            # without breaking the existing on-disk convention.
            (package / "lance").mkdir(exist_ok=True)
            (package / "vectors").mkdir(exist_ok=True)
        except OSError as exc:
            logger.error("Failed to create library directory %s: %s", package, exc)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create library directory: {exc}",
            ) from exc

    try:
        # Idempotent — if the DB already exists it just re-opens it.
        # Triggers all migrations + workflow seeding on first creation.
        db_manager.get_database(package)
    except Exception as exc:  # pragma: no cover - exercised live, not in unit
        logger.error("Failed to initialize library DB at %s: %s", package, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize library database: {exc}",
        ) from exc

    return LibraryCreateResponse(
        path=str(package),
        created=not already_existed,
        tables_initialized=True,
    )
