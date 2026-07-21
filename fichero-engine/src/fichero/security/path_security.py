"""Shared filesystem confinement helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterable


ENGINE_TEMP_DERIVED_DIRS = (
    "fichero-image-edits",
    "fichero-rotated-images",
    "fichero-segmented-images",
    "fichero-split-images",
    "fichero-fuzzy-cleaned-images",
    "fichero-recombined-segments",
    "fichero-enhanced-images",
    "fichero-prepared-images",
    "fichero-background-removed-images",
)


def _resolved(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _path_within(root: Path | str, candidate: Path | str) -> bool:
    """Return True when candidate's real path is inside root's real path."""
    try:
        _resolved(candidate).relative_to(_resolved(root))
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _candidate_has_parent_ref(candidate: Path | str) -> bool:
    return ".." in Path(candidate).parts


def engine_temp_derived_roots() -> list[Path]:
    temp_root = Path(tempfile.gettempdir())
    return [temp_root / dirname for dirname in ENGINE_TEMP_DERIVED_DIRS]


def allowed_source_roots(
    library_root: Path | str | None = None,
    *,
    storage_base: Path | str | None = None,
    include_engine_temp: bool = True,
) -> list[Path]:
    """Roots the backend may serve as document source/derived files."""
    roots: list[Path] = []
    if library_root is not None:
        root = Path(library_root).expanduser()
        roots.extend(
            [
                root,
                root / "files",
                root / "storage",
                root / "artifacts",
                root / "cache",
            ]
        )
    if storage_base is not None:
        base = Path(storage_base).expanduser()
        roots.extend(
            [
                base / "files",
                base / "thumbnails",
                base / "artifacts",
                base / "cache",
            ]
        )
    if include_engine_temp:
        roots.extend(engine_temp_derived_roots())

    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        try:
            resolved = _resolved(root)
        except (OSError, RuntimeError):
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def path_within_any_root(
    candidate: Path | str,
    roots: Iterable[Path | str],
) -> bool:
    return any(_path_within(root, candidate) for root in roots)


def resolve_under_allowed_roots(
    candidate: Path | str,
    roots: Iterable[Path | str],
) -> Path | None:
    try:
        resolved = _resolved(candidate)
    except (OSError, RuntimeError):
        return None
    return resolved if path_within_any_root(resolved, roots) else None


def validate_stored_document_path(
    path: str | None,
    library_root: Path | str,
    *,
    storage_base: Path | str | None = None,
) -> None:
    """Reject stored document paths that can resolve outside trusted roots."""
    if not path:
        return

    candidate = Path(path).expanduser()
    if not candidate.is_absolute() and not _candidate_has_parent_ref(candidate):
        return

    if not candidate.is_absolute():
        candidate = Path(library_root).expanduser() / candidate

    roots = allowed_source_roots(
        library_root,
        storage_base=storage_base,
        include_engine_temp=True,
    )
    if not path_within_any_root(candidate, roots):
        raise ValueError("Document path must stay inside the library package")


def resolve_snapshot_record_path(snapshots_dir: Path | str, record_path: str) -> Path:
    """Resolve a snapshot record path and require it to stay in snapshots_dir."""
    candidate = Path(record_path)
    if candidate.is_absolute() or _candidate_has_parent_ref(candidate):
        raise ValueError("Snapshot record path must be relative to snapshots dir")
    resolved = _resolved(Path(snapshots_dir) / candidate)
    if not _path_within(snapshots_dir, resolved):
        raise ValueError("Snapshot record path escapes snapshots dir")
    return resolved
