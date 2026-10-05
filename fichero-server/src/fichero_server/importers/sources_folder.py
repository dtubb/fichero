"""The project's Sources folder: where new material lands when an import names no folder (#5413).

Ruled 2026-10-04 (`sidebar.project.has-a-sources-folder`): every project has a folder named
Sources. A new project is created with it, an existing project gains it the next time it opens,
and an import that names no other folder lands in it. Nothing already in a project is moved.
The engine creates and chooses the folder; the app only shows it.

One rule, three callers: the library open (`DatabaseManager.get_database`, which also runs for
a new project) and every import impl in `api/routes/ingest/core.py`, through
`import_parent_id`.

Which folder IS Sources: a live, top-level folder named exactly "Sources" (the oldest, if a
person made two). A project that already has one keeps it -- no duplicate is ever made.

The open makes it ONCE per project and records that it did (`LibrarySetting`
`sources_folder.created`). It never re-makes one a person deleted: the Inbox this replaces was
re-seeded on every open and kept coming back after a delete (ruling 2026-08-31). An import that
names no folder, on the other hand, needs somewhere to land, so it makes the folder again.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SOURCES_FOLDER_NAME = "Sources"

#: Set once the open has given this project its Sources folder.
_CREATED_SETTING_ID = "sources_folder.created"


def find_sources_folder(db: Any):
    """The project's Sources folder, or None: a live top-level folder named "Sources"."""
    from fichero_server.models import DocType, Document

    candidates = [
        doc
        for doc in db.query(Document, parent_id=None, name=SOURCES_FOLDER_NAME)
        if doc.doc_type == DocType.folder and getattr(doc, "deleted_at", None) is None
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda doc: (doc.created_at, doc.id))


def ensure_sources_folder(db: Any) -> tuple[str, bool]:
    """The id of the project's Sources folder, making it if there is none. Returns (id, made)."""
    from fichero_server.models import DocType, Document, Status
    from fichero_server.models.knowledge import LibrarySetting

    existing = find_sources_folder(db)
    if existing is not None:
        made = False
        folder_id = existing.id
    else:
        folder = Document(
            name=SOURCES_FOLDER_NAME,
            doc_type=DocType.folder,
            status=Status.completed,
            parent_id=None,
        )
        db.save(folder)
        logger.info("Made the project's Sources folder (%s)", folder.id)
        made = True
        folder_id = folder.id
    if db.get(LibrarySetting, _CREATED_SETTING_ID) is None:
        db.save(LibrarySetting(id=_CREATED_SETTING_ID, value=folder_id))
    return folder_id, made


def ensure_sources_folder_on_open(db: Any) -> None:
    """Give a project its Sources folder the first time it opens; never again after that."""
    from fichero_server.models.knowledge import LibrarySetting

    if db.get(LibrarySetting, _CREATED_SETTING_ID) is not None:
        return
    ensure_sources_folder(db)


def import_parent_id(db: Any, parent_id: str | None) -> str:
    """Where an import lands: the folder it names, else the project's Sources folder.

    A Sources folder made here (the person deleted the one the open made) is announced on the
    change stream like any other new document, so the sidebar shows it without a reload.
    """
    if parent_id:
        return parent_id
    folder_id, made = ensure_sources_folder(db)
    if made:
        try:
            from fichero_server.api.change_stream import emit_change

            emit_change(
                str(Path(db.path).parent),
                type="document.created",
                document_ids=[folder_id],
            )
        except Exception as exc:  # pragma: no cover - best-effort, like every emit
            logger.debug("Sources folder emit failed (ignored): %s", exc)
    return folder_id
