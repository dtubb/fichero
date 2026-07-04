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

import hashlib
import json
import logging
import os
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from fichero.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero.api.auth import actor_from_request
from fichero.db import Database
from fichero.db_manager import db_manager
from fichero.library_paths import nfc_path
from fichero.models import (
    DocType,
    Document,
    KnownLibrary,
    LibraryRegistryResponse,
    UnicodeLibraryCollision,
    UnicodeLibraryCollisionIdentity,
    UnicodeLibraryCollisionResponse,
)
from fichero.storage import snapshot_library, settings

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


def _package_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(entry.stat().st_size for entry in path.rglob("*") if entry.is_file())


def _choose_merge_winner(left: Path, right: Path) -> tuple[Path, Path]:
    left_nfc = nfc_path(str(left))
    right_nfc = nfc_path(str(right))
    if str(left) == left_nfc and str(right) != right_nfc:
        return left, right
    if str(right) == right_nfc and str(left) != left_nfc:
        return right, left
    if _package_size_bytes(left) >= _package_size_bytes(right):
        return left, right
    return right, left


def _document_depth(doc: Document, docs_by_id: dict[str, Document]) -> int:
    depth = 0
    parent_id = doc.parent_id
    while parent_id:
        depth += 1
        parent = docs_by_id.get(parent_id)
        if parent is None:
            break
        parent_id = parent.parent_id
    return depth


def _relative_file_path(doc: Document) -> str | None:
    if not doc.path:
        return None
    raw = nfc_path(doc.path)
    if raw.startswith("files/"):
        return raw
    marker = "/files/"
    if marker in raw:
        return "files/" + raw.split(marker, 1)[1]
    return None


def _file_checksum(doc: Document, library_path: Path) -> str | None:
    if doc.checksum:
        return str(doc.checksum)
    rel_path = _relative_file_path(doc)
    if rel_path is None:
        return None
    source = library_path / rel_path
    if not source.exists():
        return None
    digest = hashlib.sha256()
    with source.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _folder_match(
    winner_docs: list[Document],
    doc: Document,
    mapped_parent_id: str | None,
) -> Document | None:
    if doc.doc_type != DocType.folder:
        return None
    for candidate in winner_docs:
        if (
            candidate.doc_type == doc.doc_type
            and candidate.name == doc.name
            and candidate.parent_id == mapped_parent_id
        ):
            return candidate
    return None


def _unique_destination_rel_path(
    winner_root: Path,
    rel_path: str,
    loser_label: str,
) -> str:
    original = Path(rel_path)
    stem = original.stem
    suffix = original.suffix
    counter = 0
    while True:
        suffix_part = f".from-{loser_label}" if counter == 0 else f".from-{loser_label}-{counter}"
        candidate = original.with_name(f"{stem}{suffix_part}{suffix}")
        if not (winner_root / candidate).exists():
            return nfc_path(candidate.as_posix())
        counter += 1


def _copy_file_between_libraries(
    loser_root: Path,
    winner_root: Path,
    source_rel_path: str,
    target_rel_path: str,
) -> None:
    source = loser_root / source_rel_path
    if not source.exists():
        raise FileNotFoundError(f"merge source file missing: {source}")
    target = winner_root / target_rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _unique_premerge_path(loser: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = loser.with_name(f"{loser.name}.premerge-{ts}")
    candidate = base
    counter = 1
    while candidate.exists():
        candidate = loser.with_name(f"{loser.name}.premerge-{ts}-{counter}")
        counter += 1
    return candidate


class UnicodeLibraryMergeParams(BaseModel):
    left_path: str
    right_path: str


def _write_merge_journal(
    winner_path: Path,
    *,
    winner_original: Path,
    loser_original: Path,
    loser_renamed: Path,
    winner_snapshot_id: str,
    loser_snapshot_id: str,
    dispositions: list[dict],
) -> str:
    journal_dir = winner_path / "storage" / "merge-journals"
    journal_dir.mkdir(parents=True, exist_ok=True)
    journal_path = journal_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}-{uuid4().hex[:8]}.json"
    journal_path.write_text(
        json.dumps(
            {
                "winner_original_path": str(winner_original),
                "winner_path": str(winner_path),
                "loser_original_path": str(loser_original),
                "loser_renamed_path": str(loser_renamed),
                "winner_snapshot_id": winner_snapshot_id,
                "loser_snapshot_id": loser_snapshot_id,
                "dispositions": dispositions,
                "deferred_follow_up_issue": 3094,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return str(journal_path)


def _snapshot_initiator_for_actor(actor: str | None) -> str:
    return actor if actor in {"user", "ai", "system"} else "system"


def _merge_library_documents_and_files(
    *,
    winner_path: Path,
    loser_path: Path,
) -> list[dict]:
    winner_db = Database(winner_path / "fichero.duckdb")
    loser_db = Database(loser_path / "fichero.duckdb")
    dispositions: list[dict] = []
    try:
        winner_docs = winner_db.all(Document)
        loser_docs = loser_db.all(Document)
        winner_docs_by_id = {doc.id: doc for doc in winner_docs}
        identity_index = {
            (_file_checksum(doc, winner_path), _relative_file_path(doc)): doc
            for doc in winner_docs
            if _relative_file_path(doc) is not None and _file_checksum(doc, winner_path) is not None
        }
        path_index: dict[str, list[Document]] = defaultdict(list)
        for doc in winner_docs:
            rel_path = _relative_file_path(doc)
            if rel_path is not None:
                path_index[rel_path].append(doc)

        loser_docs_by_id = {doc.id: doc for doc in loser_docs}
        id_map: dict[str, str] = {}
        for doc in sorted(loser_docs, key=lambda row: _document_depth(row, loser_docs_by_id)):
            mapped_parent_id = id_map.get(doc.parent_id) if doc.parent_id else None
            folder_match = _folder_match(winner_docs, doc, mapped_parent_id)
            if folder_match is not None:
                id_map[doc.id] = folder_match.id
                dispositions.append(
                    {
                        "source_document_id": doc.id,
                        "result_document_id": folder_match.id,
                        "disposition": "dedup_folder",
                    }
                )
                continue

            rel_path = _relative_file_path(doc)
            checksum = _file_checksum(doc, loser_path)
            if rel_path is not None and checksum is not None:
                identical = identity_index.get((checksum, rel_path))
                if identical is not None:
                    id_map[doc.id] = identical.id
                    dispositions.append(
                        {
                            "source_document_id": doc.id,
                            "result_document_id": identical.id,
                            "disposition": "dedupe_identical",
                            "relative_path": rel_path,
                            "checksum": checksum,
                        }
                    )
                    continue

            copied = doc.model_copy(deep=True)
            copied.id = uuid4().hex
            copied.parent_id = mapped_parent_id
            copied.metadata = dict(copied.metadata or {})
            disposition = "copy_document_only"

            if rel_path is not None and checksum is not None:
                target_rel_path = rel_path
                if path_index.get(rel_path):
                    target_rel_path = _unique_destination_rel_path(
                        winner_path,
                        rel_path,
                        loser_path.stem.replace(".fichero", ""),
                    )
                    disposition = "keep_both_conflicting_path"
                else:
                    disposition = "copy_with_file"
                _copy_file_between_libraries(
                    loser_path,
                    winner_path,
                    rel_path,
                    target_rel_path,
                )
                copied.path = target_rel_path
                copied.metadata["merge_provenance"] = {
                    "merged_from_library": str(loser_path),
                    "original_relative_path": rel_path,
                    "merged_relative_path": target_rel_path,
                }
                identity_index[(checksum, target_rel_path)] = copied
                path_index[target_rel_path].append(copied)

            winner_db.save(copied)
            winner_docs.append(copied)
            winner_docs_by_id[copied.id] = copied
            id_map[doc.id] = copied.id
            dispositions.append(
                {
                    "source_document_id": doc.id,
                    "result_document_id": copied.id,
                    "disposition": disposition,
                    "relative_path": copied.path,
                    "checksum": checksum,
                }
            )
        return dispositions
    finally:
        winner_db.close()
        loser_db.close()


@action(
    "library.unicode_merge",
    UnicodeLibraryMergeParams,
    domains=["library"],
    atomic=False,
)
def _action_unicode_merge_library(
    db: Database,
    params: UnicodeLibraryMergeParams,
    ctx: ActionContext,
) -> tuple[dict[str, object], ChangeSpec]:
    left = Path(params.left_path).expanduser()
    right = Path(params.right_path).expanduser()
    if left == right or not left.exists() or not right.exists():
        result = {
            "status": "noop",
            "reason": "library pair is no longer mergeable",
            "left_path": str(left),
            "right_path": str(right),
        }
        return result, ChangeSpec(
            domains=["library"],
            target_ids=[str(left), str(right)],
            before={"status": "mergeable-check"},
            after=result,
            emit_type=None,
        )

    winner_path, loser_path = _choose_merge_winner(left, right)
    winner_snapshot = snapshot_library(
        str(winner_path),
        reason=f"pre-merge snapshot vs {loser_path.name}",
        initiator=_snapshot_initiator_for_actor(ctx.actor),
        include_files=True,
    )
    loser_snapshot = snapshot_library(
        str(loser_path),
        reason=f"pre-merge snapshot into {winner_path.name}",
        initiator=_snapshot_initiator_for_actor(ctx.actor),
        include_files=True,
    )

    dispositions = _merge_library_documents_and_files(
        winner_path=winner_path,
        loser_path=loser_path,
    )
    db_manager.close_database(str(winner_path))
    db_manager.close_database(str(loser_path))

    loser_renamed = _unique_premerge_path(loser_path)
    os.replace(loser_path, loser_renamed)
    loser_registry_path = str(Path(nfc_path(str(loser_path))).resolve())
    for row in db.query(KnownLibrary, path=loser_registry_path):
        db.delete(row)

    journal_path = _write_merge_journal(
        winner_path,
        winner_original=winner_path,
        loser_original=loser_path,
        loser_renamed=loser_renamed,
        winner_snapshot_id=winner_snapshot.id,
        loser_snapshot_id=loser_snapshot.id,
        dispositions=dispositions,
    )
    result = {
        "status": "merged",
        "winner_path": str(winner_path),
        "loser_original_path": str(loser_path),
        "loser_renamed_path": str(loser_renamed),
        "winner_snapshot_id": winner_snapshot.id,
        "loser_snapshot_id": loser_snapshot.id,
        "journal_path": journal_path,
        "dispositions": dispositions,
        "deferred_follow_up_issue": 3094,
    }
    return result, ChangeSpec(
        domains=["library"],
        target_ids=[str(winner_path), str(loser_path)],
        before={
            "left_path": str(left),
            "right_path": str(right),
        },
        after=result,
        emit_type=None,
    )


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


@router.post("/registry/unicode-collisions/merge")
def confirm_unicode_library_merge(
    request: Request,
    body: UnicodeLibraryMergeParams,
    db: Database = Depends(get_global_database),
) -> dict[str, object]:
    """Explicit-confirm merge for a detected Unicode-collision pair."""
    if request.client and request.client.host not in {"127.0.0.1", "::1", "localhost", "testclient", "testserver"}:
        raise HTTPException(status_code=403, detail="loopback only")
    params = UnicodeLibraryMergeParams.model_validate(body)
    result = registry.invoke(
        db,
        "library.unicode_merge",
        params.model_dump(),
        ActionContext(actor=actor_from_request(request)),
    )
    return result.result


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
