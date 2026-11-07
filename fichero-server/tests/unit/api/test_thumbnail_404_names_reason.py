"""#6308: when the original IS readable, a 404 from the thumbnail and display routes still says which of two things it is.

`not_generated_yet` (thumbnail only: the inline-generation permits are taken, so the request is shed and the client retries)
and `no_picture` (the original is readable but no picture could be made from it). The unreadable-original reasons are in
`test_display_404_names_why_unreachable_original.py`. The source route's readable-original reason (`no_source`) is here too.
"""

from __future__ import annotations

import threading

import pytest

from fichero_server.models import DocType, Document, FileType


def _readable_but_not_an_image(db, tmp_path) -> Document:
    path = tmp_path / "notes.jpg"
    path.write_bytes(b"not an image")
    doc = Document(name="Folio 1", doc_type=DocType.page, file_type=FileType.image, path=str(path))
    db.save(doc)
    return doc


@pytest.mark.parametrize("route", ["thumbnail", "display"])
def test_a_readable_original_that_gives_no_picture_says_no_picture(client, db, tmp_path, route):
    doc = _readable_but_not_an_image(db, tmp_path)
    r = client.get(f"/api/storage/{route}/{doc.id}")
    assert r.status_code == 404
    assert r.json()["reason"] == "no_picture"
    assert "no picture" in r.json()["detail"]
    assert str(tmp_path) not in r.text and "notes.jpg" not in r.text


def test_a_thumbnail_shed_for_want_of_a_permit_says_not_generated_yet(client, db, tmp_path, monkeypatch):
    from fichero_server.api.routes.system import storage

    monkeypatch.setattr(storage, "_inline_thumbnail_permits", threading.BoundedSemaphore(0))
    doc = _readable_but_not_an_image(db, tmp_path)
    r = client.get(f"/api/storage/thumbnail/{doc.id}")
    assert r.status_code == 404
    assert r.json()["reason"] == "not_generated_yet"
    assert "not yet generated" in r.json()["detail"]


def test_an_unreadable_original_is_still_named_before_the_permit_is_asked(client, db, tmp_path):
    doc = Document(name="Folio 1", doc_type=DocType.page, file_type=FileType.image, path=str(tmp_path / "gone.jpg"))
    db.save(doc)
    r = client.get(f"/api/storage/thumbnail/{doc.id}")
    assert r.json()["reason"] == "moved_or_deleted"


def test_a_source_404_with_a_readable_original_says_no_source(client, db, test_package):
    """#6308: /source names the reason too — a PDF page has no file of its own, but its parent PDF is readable."""
    pdf_path = test_package / "files" / "letter.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 (test)")
    parent = Document(name="Letter", doc_type=DocType.file, file_type=FileType.pdf, path="files/letter.pdf")
    db.save(parent)
    page = Document(name="Letter p1", doc_type=DocType.page, file_type=None, parent_id=parent.id, sequence=1)
    db.save(page)
    r = client.get(f"/api/storage/source/{page.id}")
    assert r.status_code == 404
    assert r.json()["reason"] == "no_source"
    assert "source" in r.json()["detail"].lower()
