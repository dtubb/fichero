"""The root Inbox is a system folder — delete/move/rename are refused.

2026-08-12: a sidebar delete removed the Inbox itself, and the tombstone
then blocked reseeding (see test_library_bootstrap). The guard uses the
Inbox SHAPE (root folder named "Inbox"), not ``attributes.read_only`` —
read_only would also reject filing INTO the Inbox.
"""

import pytest
from fastapi import HTTPException

from fichero_server.api.routes.document.documents import _reject_if_root_inbox
from fichero_server.models import DocType, Document


def _doc(**kwargs) -> Document:
    defaults = {"name": "Inbox", "parent_id": None, "doc_type": DocType.folder}
    defaults.update(kwargs)
    return Document(**defaults)


class TestRootInboxGuard:
    def test_root_inbox_is_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _reject_if_root_inbox(_doc(), "deleted")
        assert exc.value.status_code == 403
        assert "system folder" in exc.value.detail

    def test_nested_inbox_folder_is_allowed(self):
        assert _reject_if_root_inbox(_doc(parent_id="some-parent"), "deleted") is None

    def test_root_non_folder_named_inbox_is_allowed(self):
        assert _reject_if_root_inbox(_doc(doc_type=DocType.file), "deleted") is None

    def test_other_root_folders_are_allowed(self):
        assert _reject_if_root_inbox(_doc(name="Projects"), "deleted") is None
