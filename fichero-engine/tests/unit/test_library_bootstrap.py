"""Coverage for default library bootstrap rows."""

from fichero.library_bootstrap import ensure_inbox_folder
from fichero.models import DocType


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
