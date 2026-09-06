"""Pull-only library-sync routes (keystone, read slice).

Serves a library's sync manifest and its individual objects so a peer can CLONE
a library with checkpointed resume — design
``agent-work/design/hpc-remote-library-sync.md`` §2.2.

HARD invariant (connection-transport-invariants / hold-security-contract-conflicts):
these routes are **no more permissive than the existing sharing surface**. They
reuse ``get_library_database`` verbatim — the same dependency every read route
uses — so the fail-closed loopback/HTTPS/device-token/``LibraryRole`` machinery
gates them unchanged. A caller who cannot already read this library over the
sharing surface cannot read it here. No new auth, no unauthenticated path.

Read-only in this slice: manifest + object GETs. Push (write role) is a later
slice. The DB image is not exported here yet (that needs the engine's snapshot
quiesce); this slice syncs the ``files/`` originals — enough to demonstrate the
manifest → diff → resume → land mechanics end to end.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.db.migrations.schema import read_library_uuid
from fichero_server.workflows.library_sync_io import build_package_manifest

router = APIRouter()


class SyncObjectModel(BaseModel):
    """One syncable object in a manifest (typed for OpenAPI codegen)."""

    rel: str
    sha256: str
    size: int
    kind: str
    mtime_ns: int


class SyncManifestResponse(BaseModel):
    """A library's syncable objects at one generation (design §2.1)."""

    library_id: str
    generation: int
    produced_at: str
    objects: list[SyncObjectModel]


def _library_root(db: Database) -> Path:
    """The .fichero package directory for this library (``…/Lib.fichero``)."""
    return Path(db.path).parent


def _resolved_library_id(db: Database) -> str:
    """Move-stable library UUID, falling back to the path only if unminted.

    The identity migration mints the UUID at open, so the fallback is defensive
    (a library opened by an older engine that has not re-migrated yet).
    """
    uuid = read_library_uuid(db.conn)
    if uuid:
        return uuid
    # Defensive fallback — mirrors audit_chain's derivation so a not-yet-migrated
    # library still has a stable-per-path id rather than crashing the manifest.
    import hashlib

    return hashlib.sha256(str(_library_root(db)).encode("utf-8")).hexdigest()


@router.get("/library/sync/manifest", response_model=SyncManifestResponse)
def get_sync_manifest(
    db: Database = Depends(get_library_database),
) -> SyncManifestResponse:
    """Return the current sync manifest for the library (read role required).

    Files-only in this slice (no DB image yet). ``generation`` is the max file
    mtime_ns — cheap, monotonic-ish, and stable while the library is unchanged,
    so a clone can pin one generation and resume against it across restarts.
    """
    root = _library_root(db)
    library_id = _resolved_library_id(db)
    manifest = build_package_manifest(
        package_root=root,
        library_id=library_id,
        generation=0,  # replaced below with the max-mtime generation
    )
    generation = max((o.mtime_ns for o in manifest.objects), default=0)
    return SyncManifestResponse(
        library_id=library_id,
        generation=generation,
        produced_at=manifest.produced_at,
        objects=[SyncObjectModel(**o.to_dict()) for o in manifest.objects],
    )


@router.get("/library/sync/object")
def get_sync_object(
    rel: str = Query(..., description="Library-relative object path from the manifest"),
    db: Database = Depends(get_library_database),
) -> FileResponse:
    """Stream one syncable object by its manifest-relative path (read role).

    The client re-hashes on landing (``land_object`` verifies ``sha256``), so
    the server streams without re-hashing — cheap, and integrity is enforced at
    the destination where a mismatch triggers a re-fetch on resume. Only
    ``files/`` originals are syncable objects; the rel is confined to the
    package (an untrusted rel with ``..`` never escapes), matching the read the
    existing document/rendition routes already permit for this role.
    """
    root = _library_root(db).resolve()
    if not rel.startswith("files/"):
        raise HTTPException(status_code=400, detail="Only files/ objects are syncable")
    target = (root / rel).resolve()
    if root not in target.parents:
        raise HTTPException(status_code=400, detail="Object path escapes the library")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Object not found")
    return FileResponse(path=str(target), media_type="application/octet-stream")
