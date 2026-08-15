"""Coverage for default library bootstrap rows."""

from fichero_server.core.timeutil import utc_now
from fichero_server.db.library_bootstrap import ensure_inbox_folder
from fichero_server.models import DocType


class _DB:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.saved = []

    def query(self, model, **filters):
        assert model.__name__ == "Document"
        return [row for row in self.rows if all(getattr(row, key) == value for key, value in filters.items())]

    def save(self, row):
        self.saved.append(row)


def test_ensure_inbox_is_idempotent_and_only_seeds_root_folder():
    db = _DB()
    first = ensure_inbox_folder(db)
    db.rows.append(first)
    second = ensure_inbox_folder(db)

    assert first is second
    assert first.name == "Inbox"
    assert first.parent_id is None
    assert first.doc_type is DocType.folder
    assert db.saved == [first]


def test_ensure_inbox_resurrects_soft_deleted_tombstone():
    """A tombstoned Inbox must come back, not block reseeding forever.

    2026-08-12: deleting the Inbox left a soft-deleted row that satisfied
    the idempotency lookup on every subsequent open — the library never
    got its Inbox back.
    """
    db = _DB()
    inbox = ensure_inbox_folder(db)
    inbox.deleted_at = utc_now()
    inbox.deleted_by = "user"
    db.rows.append(inbox)

    resurrected = ensure_inbox_folder(db)

    assert resurrected is inbox
    assert resurrected.deleted_at is None
    assert resurrected.deleted_by is None
    # Resurrection re-saves the SAME row — no same-shape twin is created.
    assert db.saved == [inbox, inbox]
