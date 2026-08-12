"""Library bootstrap helpers shared by create/open flows."""

from __future__ import annotations

import logging

from fichero_server.models import DocType, Document

logger = logging.getLogger(__name__)

INBOX_NAME = "Inbox"


def ensure_inbox_folder(db) -> Document:
    """Ensure the library has a root-level Inbox folder.

    Idempotent by the same shape Swift root-drop routing looks up:
    ``name == "Inbox" && parent_id is None && doc_type == folder``.
    """
    existing = list(
        db.query(
            Document,
            name=INBOX_NAME,
            parent_id=None,
            doc_type=DocType.folder,
        )
    )
    live = [doc for doc in existing if getattr(doc, "deleted_at", None) is None]
    if live:
        return live[0]
    if existing:
        # A soft-deleted Inbox tombstone otherwise satisfies this lookup
        # forever, so a library whose Inbox was deleted never got it back
        # (2026-08-12). Resurrect the row rather than seeding a same-shape
        # twin the Trash could later restore into a name collision.
        inbox = existing[0]
        inbox.deleted_at = None
        inbox.deleted_by = None
        db.save(inbox)
        logger.info("Resurrected soft-deleted Inbox folder: %s", inbox.id)
        return inbox

    inbox = Document(
        name=INBOX_NAME,
        parent_id=None,
        doc_type=DocType.folder,
    )
    db.save(inbox)
    logger.info("Seeded default Inbox folder: %s", inbox.id)
    return inbox
