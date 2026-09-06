"""On-disk I/O for library sync — turn a ``.fichero`` package into a manifest.

The pure diff/resume core lives in ``workflows/library_sync.py`` (no I/O). This
module is the thin filesystem layer that produces a :class:`SyncManifest` from a
real package on disk and lands a received object back into one — the two points
where sync actually touches files.

Kept deliberately small and dependency-free (stdlib ``hashlib``/``pathlib``
only) so it is testable against a temp directory with no engine, no DB
connection, and no network. The DB image (a Parquet bundle produced by
``db/storage_snapshots.py``) is added by the caller as a ``kind="db"`` object;
this module handles the bulk: the content-addressed originals under ``files/``.

Design: ``agent-work/design/hpc-remote-library-sync.md`` §2.1.
"""

from __future__ import annotations

from pathlib import Path
import hashlib

from fichero_server.workflows.library_sync import (
    LibrarySyncError,
    SyncManifest,
    SyncObject,
    build_manifest_from_listing,
)

# Subdirectories that are derivable caches, not source data — never listed in a
# manifest by default (they regenerate on the target; design §1, decision D2).
_DERIVED_DIRS = frozenset({"vectors", "lance", "thumbnails", "thumbs", "display"})

_CHUNK = 1 << 20  # 1 MiB — bounded read so hashing a large file stays cheap.


def hash_file(path: Path) -> tuple[str, int]:
    """Return ``(sha256_hexdigest, size_bytes)`` for a file, read in chunks.

    Streaming keeps peak memory flat regardless of file size — a 2 GB PDF hashes
    in 1 MiB bites, not one 2 GB read.
    """
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            block = handle.read(_CHUNK)
            if not block:
                break
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def iter_file_objects(package_root: Path) -> list[SyncObject]:
    """List the syncable original files under ``<package>/files/`` (design §2.1).

    Walks ``files/`` recursively, hashing each regular file into a
    :class:`SyncObject` with a library-relative ``rel`` (POSIX-style, e.g.
    ``files/00/ab….jpg``). Derived-cache directories are skipped. Symlinks are
    ignored (a sync must transfer content, never a dangling link). Returns an
    empty list if ``files/`` does not exist yet (a brand-new library).
    """
    files_dir = package_root / "files"
    if not files_dir.is_dir():
        return []
    objects: list[SyncObject] = []
    for path in sorted(files_dir.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        # Skip anything nested under a derived-cache dir name.
        if _DERIVED_DIRS.intersection(part.lower() for part in path.parts):
            continue
        sha, size = hash_file(path)
        rel = path.relative_to(package_root).as_posix()
        mtime_ns = path.stat().st_mtime_ns
        objects.append(
            SyncObject(rel=rel, sha256=sha, size=size, kind="file", mtime_ns=mtime_ns)
        )
    return objects


def build_package_manifest(
    *,
    package_root: Path,
    library_id: str,
    generation: int,
    db_object: SyncObject | None = None,
    produced_at: str = "",
) -> SyncManifest:
    """Build a full sync manifest for a package on disk (design §2.1).

    Lists the originals under ``files/`` and, if the caller has already exported
    the DB image (via ``snapshot_library``), folds in that single ``kind="db"``
    object. The DB export is the caller's job because it needs an engine
    connection to quiesce DuckDB — this module stays connection-free.
    """
    if not package_root.is_dir():
        raise LibrarySyncError(f"package_root is not a directory: {package_root}")
    objects = iter_file_objects(package_root)
    if db_object is not None:
        objects.append(db_object)
    return build_manifest_from_listing(
        library_id=library_id,
        generation=generation,
        objects=objects,
        produced_at=produced_at,
    )


def land_object(package_root: Path, obj: SyncObject, data: bytes) -> Path:
    """Write a received object into the package atomically, verifying its hash.

    Lands ``data`` at ``<package>/<obj.rel>`` via a ``tmp``+rename so a partial
    write is never visible (design §2.3). The content is re-hashed and MUST
    match ``obj.sha256`` — a mismatch raises :class:`LibrarySyncError` rather
    than landing corrupt bytes (prefer-raise, never a silent bad object; the
    resume loop will re-fetch it). Returns the final path.
    """
    actual = hashlib.sha256(data).hexdigest()
    if actual != obj.sha256:
        raise LibrarySyncError(
            f"hash mismatch landing {obj.rel!r}: expected {obj.sha256}, got {actual}"
        )
    target = package_root / obj.rel
    # Confine the write to the package — a manifest is untrusted input over the
    # wire, and a `..` in rel must never escape the package root.
    resolved = target.resolve()
    root = package_root.resolve()
    if root not in resolved.parents and resolved != root:
        raise LibrarySyncError(f"object rel escapes package root: {obj.rel!r}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    tmp = resolved.with_name(resolved.name + ".synctmp")
    tmp.write_bytes(data)
    tmp.replace(resolved)
    return resolved
