"""Coverage for duplicate-cluster organization validation helpers."""

from __future__ import annotations

import asyncio

import pytest

from fichero_server.models import DocType, Document
from fichero_server.workflows.tools import organize_same_documents as tool


def test_cluster_folder_name_is_stable():
    assert tool._cluster_folder_name(3) == "Same Document 3"


def test_existing_cluster_folder_matches_parent_type_and_name():
    wanted = Document(id="folder-1", name="Same Document 1", parent_id="root", doc_type=DocType.folder)
    other = Document(id="file-1", name="Same Document 1", parent_id="root", doc_type=DocType.file)

    class DB:
        def query(self, _model, **filters):
            assert filters == {"parent_id": "root", "doc_type": DocType.folder}
            return [wanted, other]

    assert tool._existing_cluster_folder(DB(), "root", "Same Document 1") is wanted


@pytest.mark.parametrize(
    ("state", "inputs", "message"),
    [
        ({}, {}, "library path"),
        ({"library_path": "/tmp/lib", "selected_doc_ids": []}, {}, "exactly one"),
    ],
)
def test_organize_rejects_missing_workflow_scope(state, inputs, message):
    with pytest.raises(ValueError, match=message):
        asyncio.run(tool.organize_same_documents(inputs, state, object()))
