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
    if existing:
        return existing[0]

    inbox = Document(
        name=INBOX_NAME,
        parent_id=None,
        doc_type=DocType.folder,
    )
    db.save(inbox)
    logger.info("Seeded default Inbox folder: %s", inbox.id)
    return inbox
