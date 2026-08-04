"""Pins for folder-name collisions on folder ingest (live find 2026-08-04).

A Finder folder DROPPED onto the sidebar and a folder chosen via the import
menu run through the same ``ingest_folder``, so their collision behaviour
agrees by construction. What that behaviour IS was undocumented and unpinned:

* Re-ingesting the SAME folder (same source path) under the same parent
  REUSES the existing folder Document — a merge; unchanged files are then
  skipped by the checksum pre-index.
* Ingesting a DIFFERENT folder that merely shares the name creates a new
  sibling folder Document with the same name. Fichero folders are keyed by
  id, not by name, so duplicate-named siblings are legal (Finder-like: the
  sidebar shows both).

These tests pin both branches of the ``existing_roots`` check in
``ingest_folder`` so a refactor cannot silently flip a merge into a duplicate
or vice versa.
"""

from unittest.mock import MagicMock, patch

import pytest

from fichero_server.importers.ingest import ingest_folder
from fichero_server.models import DocType, Document, Status


@pytest.fixture()
def source_folder(tmp_path):
    folder = tmp_path / "Box 12"
    folder.mkdir()
    (folder / "page1.txt").write_text("uno", encoding="utf-8")
    return folder


def _mock_db(existing_roots):
    db = MagicMock()
    db.all.return_value = []
    db.get.return_value = None
    db.query.return_value = existing_roots
    saved = []

    def save(obj, auto_embed=False):
        saved.append(obj)

    db.save.side_effect = save
    db.saved_documents = saved
    return db


def _saved_folders(db):
    return [doc for doc in db.saved_documents if doc.doc_type == DocType.folder]


@patch("fichero_server.bookmarks.create_bookmark", return_value=None)
def test_reingesting_the_same_folder_reuses_its_folder_document(
    _bookmark, source_folder
):
    existing = Document(
        name=source_folder.name,
        path=str(source_folder.resolve()),
        doc_type=DocType.folder,
        status=Status.completed,
        parent_id=None,
    )
    db = _mock_db([existing])

    docs = ingest_folder(source_folder, db=db)

    # No second folder Document with the same name; children land under the
    # EXISTING folder's id — a merge, not a duplicate.
    assert _saved_folders(db) == []
    assert len(docs) == 1
    assert docs[0].parent_id == existing.id


@patch("fichero_server.bookmarks.create_bookmark", return_value=None)
def test_a_same_name_folder_from_a_different_path_becomes_a_sibling(
    _bookmark, source_folder
):
    existing = Document(
        name=source_folder.name,
        path="/somewhere/else/Box 12",
        doc_type=DocType.folder,
        status=Status.completed,
        parent_id=None,
    )
    db = _mock_db([existing])

    docs = ingest_folder(source_folder, db=db)

    created = _saved_folders(db)
    assert len(created) == 1
    assert created[0].name == existing.name
    assert created[0].id != existing.id
    assert len(docs) == 1
    assert docs[0].parent_id == created[0].id
