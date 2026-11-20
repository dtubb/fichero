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
    from fichero_server.security import path_security

    monkeypatch.setattr(storage, "resolve_source", lambda doc, library_root=None: None)
    monkeypatch.setattr(path_security, "resolve_document_source_path", lambda *a, **k: None)

    said = relink.missing_originals(db, {page.id})

    assert said is not None and said["ids"] == [page.id]


def test_a_file_the_bookmark_finds_is_not_missing_though_its_recorded_path_is_gone(db, tmp_path, monkeypatch):
    found = tmp_path / "moved" / "renamed.jpg"
    found.parent.mkdir()
    found.write_bytes(b"x")
    page = _page(db, tmp_path / "old" / "p.jpg")
    monkeypatch.setattr(storage, "resolve_source", lambda doc, library_root=None: found)

    assert relink.missing_originals(db, {page.id}) is None


def test_a_folder_relink_of_three_moved_files_relinks_three_and_leaves_none_missing(client, db, tmp_path):
    old = tmp_path / "old"
    pages = []
    for i in range(3):
        f = old / f"deep{i}" / f"f{i}.jpg"
        f.parent.mkdir(parents=True)
        f.write_bytes(b"data" * (i + 1))
        doc = Document(name=f.name, doc_type=DocType.file, file_type=FileType.image, path=str(f),
                       metadata={"file_size": f.stat().st_size})
        db.save(doc)
        pages.append(doc)
    new = tmp_path / "Historical Archives"
    new.mkdir()
    for i in range(3):  # moved flat, nothing of the old folders kept
        (old / f"deep{i}" / f"f{i}.jpg").rename(new / f"f{i}.jpg")

    assert client.get("/api/documents/missing-originals").json()["pages"] == 3
    done = client.post("/api/documents/relink-originals", json={"new_root": str(new)})

    assert done.status_code == 200, done.text
    assert len(done.json()["matched"]) == 3
    assert client.get("/api/documents/missing-originals").json() is None


def test_two_successive_moves_are_both_followed_because_each_find_saves_a_fresh_bookmark(db, tmp_path, monkeypatch):
    import base64

    from fichero_server import bookmarks

    a, b, c = (tmp_path / n / "p.jpg" for n in "abc")
    for p in (a, b, c):
        p.parent.mkdir()
    a.write_bytes(b"x")
    where: dict[bytes, object] = {b"bm-a": a}  # a bookmark finds the file where IT last saw it move to
    monkeypatch.setattr(bookmarks, "is_available", lambda: True)
    monkeypatch.setattr(bookmarks, "resolve_bookmark", lambda data: where.get(data))
    monkeypatch.setattr(bookmarks, "refresh_bookmark", lambda path, old=None: b"bm-" + path.parent.name.encode())
    page = Document(name="p.jpg", doc_type=DocType.file, file_type=FileType.image, path=str(a),
                    metadata={"bookmark": base64.b64encode(b"bm-a").decode(), "source_path": str(a)})
    db.save(page)

    a.rename(b)
    where[b"bm-a"] = b
    assert relink.follow_bookmark(db, db.get(Document, page.id)) == b
    assert db.get(Document, page.id).path == str(b)

    b.rename(c)
    where[b"bm-b"] = c  # the old bookmark still says b; only the fresh one knows c
    assert relink.follow_bookmark(db, db.get(Document, page.id)) == c
    saved = db.get(Document, page.id)
    assert saved.path == str(c) and saved.metadata["source_path"] == str(c)
    assert base64.b64decode(saved.metadata["bookmark"]) == b"bm-c"
