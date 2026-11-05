"""Every document's id, stored path and trash mark, for Empty Trash's storage plan (`safety.trash.empty-says-what-will-go`). The SQL lives
here, behind one typed function, so `api/routes/document/trash_storage.py` holds none (the #1876 rule)."""
from __future__ import annotations

from typing import Any


def id_path_deleted(db: Any) -> list[tuple[str, Any, Any]]:
    """(id, path, deleted_at) of every document, trashed ones included."""
    return [tuple(r) for r in db.execute_fetchall("SELECT id, path, deleted_at FROM documents") or []]
