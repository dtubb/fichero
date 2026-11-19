"""One test for "is the original there", shared by the missing-originals sheet and the thumbnail (#6733).

Live 2026-11-19: the Locate Originals sheet said "Every linked original is where the project says." while the
thumbnails said "Original unavailable". The sheet asked `path.exists()`; the thumbnail asks `resolve_source`.
"""

from __future__ import annotations

from fichero_server.db import storage
from fichero_server.importers import relink
from fichero_server.models import DocType, Document, FileType


def _page(db, path) -> Document:
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    return doc


def test_a_file_that_exists_but_the_thumbnail_cannot_open_is_missing_for_the_sheet_too(db, tmp_path, monkeypatch):
    here = tmp_path / "elsewhere" / "p.jpg"
    here.parent.mkdir()
    here.write_bytes(b"x")
    page = _page(db, here)
    monkeypatch.setattr(storage, "resolve_source", lambda doc, library_root=None: None)

    said = relink.missing_originals(db, {page.id})

    assert said is not None and said["ids"] == [page.id]


def test_a_file_the_bookmark_finds_is_not_missing_though_its_recorded_path_is_gone(db, tmp_path, monkeypatch):
    found = tmp_path / "moved" / "renamed.jpg"
    found.parent.mkdir()
    found.write_bytes(b"x")
    page = _page(db, tmp_path / "old" / "p.jpg")
    monkeypatch.setattr(storage, "resolve_source", lambda doc, library_root=None: found)

    assert relink.missing_originals(db, {page.id}) is None
