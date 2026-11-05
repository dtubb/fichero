"""What Empty Trash removes from disk and from the notes, worked out before anything goes (`safety.trash.empty-removes-everything-and-only-that`, #5243).

Only the library's OWN files are ever removed: a copied-in original under ``<library>/files/`` and the derived images under
``<library>/storage/thumbnails/`` named for a trashed document. A linked original (an absolute path outside the library, the
user's own file), a path that escapes the library by ``..`` or a symlink, and a file a live document also uses are all left
alone. The plan is read before the purge and carried out after it, so the confirm dialog's numbers are what then goes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TrashStoragePlan:
    files: list[Path] = field(default_factory=list)
    bytes: int = 0
    note_ids: list[str] = field(default_factory=list)


def _owned_original(path_value: object, root: Path) -> Path | None:
    """The copied-in file ``path_value`` names, or None when it is linked, outside the library or not a file."""
    if not path_value:
        return None
    candidate = Path(str(path_value)).expanduser()
    if candidate.is_absolute():
        text = str(candidate)
        if "/files/" not in text:
            return None  # a linked original: the user's own file
        candidate = root / "files" / text.split("/files/", 1)[1]
    else:
        candidate = root / candidate
    files_root = (root / "files").resolve()
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(files_root) or not resolved.is_file():
        return None
    return resolved


def _derived_images(doc_id: str, root: Path) -> list[Path]:
    """The thumbnail and display images made for a document: named by its id, under the library's own thumbnail folder."""
    folder = root / "storage" / "thumbnails" / doc_id[:2].lower()
    if not doc_id or not folder.is_dir():
        return []
    return [p for p in folder.glob(f"{doc_id}*") if p.is_file() and not p.is_symlink()]


def plan_trash_storage(db: Any) -> TrashStoragePlan:
    """The files and notes Empty Trash would remove: those of every trashed document, less any file a live one also uses."""
    from fichero_server.knowledge.trash_visibility import hidden_note_ids, trashed_document_ids
    from fichero_server.models.knowledge import Note

    root = Path(db.path).parent
    trashed = trashed_document_ids(db)
    plan = TrashStoragePlan()
    if not trashed:
        return plan
    live: set[Path] = set()
    mine: set[Path] = set()
    from fichero_server.db.document_paths import id_path_deleted  # noqa: PLC0415

    for doc_id, path_value, deleted_at in id_path_deleted(db):
        owned = _owned_original(path_value, root)
        if owned is None:
            continue
        (mine if deleted_at is not None and doc_id in trashed else live).add(owned)
    originals = sorted(mine - live)
    derived = [p for doc_id in sorted(trashed) for p in _derived_images(doc_id, root)]
    plan.files = originals + derived
    plan.bytes = sum(p.stat().st_size for p in plan.files if p.exists())
    plan.note_ids = sorted(hidden_note_ids(db, db.query(Note), trashed))
    return plan


def remove_planned_files(files: list[Path]) -> tuple[int, int]:
    """Delete the planned files; returns (removed, bytes). A file already gone is not an error; any other failure is logged
    and leaves that file (the rows are already purged, so the next Empty Trash finds it no more: it is reported)."""
    removed = freed = 0
    for path in files:
        try:
            size = path.stat().st_size
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            logger.warning("Empty Trash could not remove %s: %s", path.name, exc)
            continue
        removed += 1
        freed += size
    return removed, freed
