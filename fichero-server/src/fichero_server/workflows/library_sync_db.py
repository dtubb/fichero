"""DB-image export for library sync — the openable-clone slice.

A cloned library is only useful if it has a ``fichero.duckdb`` to open. This
module produces a *consistent* single-file copy of the source DB and exposes it
as one ``kind="db"`` sync object (design ``hpc-remote-library-sync.md`` §1/§2.1).

Consistency reuses the exact primitive ``snapshot_library`` uses: quiesce the
managed DB (``db_manager.quiesce_database(checkpoint=True, close=False)``) so the
on-disk file is checkpointed, then copy the file. No Parquet export/restore is
needed — the copied ``.duckdb`` is directly openable.

HARD (per lane owner): quiescing touches the source DB. Run ONLY against
libraries the engine can safely quiesce — throwaway/temp packages in tests,
never a library another engine session is actively using.
"""

from __future__ import annotations

from pathlib import Path
import shutil

from fichero_server.workflows.library_sync import SyncObject
from fichero_server.workflows.library_sync_io import hash_file

# The DB image lands at the package root as the openable database file, so a
# landed clone opens with no restore step.
DB_IMAGE_REL = "fichero.duckdb"
_CACHE_DIRNAME = ".sync-image"


def _db_path(library_root: Path) -> Path:
    return library_root / "fichero.duckdb"


def image_cache_path(library_root: Path) -> Path:
    """Where the consistent DB copy is cached (outside ``files/``, so the file
    walk never lists it)."""
    return library_root / _CACHE_DIRNAME / "fichero.duckdb"


def build_db_image(library_root: Path) -> SyncObject | None:
    """Produce/refresh the consistent DB image and return it as a sync object.

    Returns ``None`` for a library with no ``fichero.duckdb`` yet. The image is
    cached and rebuilt only when the live DB is newer than the cached copy —
    ``ponytail: mtime-based staleness; upgrade to a generation/content key if a
    same-mtime in-place write ever slips through`` — and its ``(sha256, size)``
    is cached in a sidecar so repeated manifest calls don't re-hash a large DB.
    """
    src = _db_path(library_root)
    if not src.is_file():
        return None
    cache = image_cache_path(library_root)
    sha_sidecar = cache.with_name(cache.name + ".sha256")

    stale = (
        not cache.exists()
        or not sha_sidecar.exists()
        or src.stat().st_mtime_ns > cache.stat().st_mtime_ns
    )
    if stale:
        # Local import: db_manager pulls in the engine DB stack — keep this
        # module importable (for hashing/paths) without that cost until needed.
        from fichero_server.db.manager import db_manager

        db_manager.quiesce_database(library_root, checkpoint=True, close=False)
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_name(cache.name + ".tmp")
        shutil.copy2(src, tmp)
        tmp.replace(cache)
        sha, size = hash_file(cache)
        sha_sidecar.write_text(f"{sha} {size}", encoding="utf-8")
    else:
        raw = sha_sidecar.read_text(encoding="utf-8").split()
        sha, size = raw[0], int(raw[1])

    return SyncObject(
        rel=DB_IMAGE_REL,
        sha256=sha,
        size=size,
        kind="db",
        mtime_ns=cache.stat().st_mtime_ns,
    )
