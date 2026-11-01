"""#6308: the thumbnail, display and source routes name why an original cannot be read.

The reason is the one `export_service._why_image_unavailable` already tells, moved to a shared classifier
(`media.image_reason`; spec `engine.silent.originals-reason-is-one-of-three`); the 404 keeps `detail` a string and adds `reason`, a code.
"""

from __future__ import annotations

import os
import stat

import pytest

from fichero_server.models import DocType, Document, FileType

ROUTES = ["thumbnail", "display", "source"]


def _doc(db, path: str | None) -> Document:
    doc = Document(name="Folio 1", doc_type=DocType.page, file_type=FileType.image, path=path)
    db.save(doc)
    return doc


@pytest.mark.parametrize("route", ROUTES)
def test_a_file_that_is_gone_is_moved_or_deleted(client, db, tmp_path, route):
    doc = _doc(db, str(tmp_path / "gone.jpg"))
    r = client.get(f"/api/storage/{route}/{doc.id}")
    assert r.status_code == 404
    assert r.json()["reason"] == "moved_or_deleted"
    assert "moved or deleted" in r.json()["detail"]


@pytest.mark.parametrize("route", ROUTES)
def test_a_file_on_a_drive_that_is_not_there_says_the_drive_is_not_connected(client, db, route):
    doc = _doc(db, "/Volumes/NoSuchDriveForTest6308/Originals/a.jpg")
    r = client.get(f"/api/storage/{route}/{doc.id}")
    assert r.status_code == 404
    assert r.json()["reason"] == "volume_not_mounted"
    assert "NoSuchDriveForTest6308" in r.json()["detail"]


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a folder with no permissions")
def test_a_folder_the_engine_may_not_read_says_access_is_not_granted(client, db, tmp_path, route):
    folder = tmp_path / "locked"
    folder.mkdir()
    (folder / "a.jpg").write_bytes(b"x")
    folder.chmod(0)
    try:
        doc = _doc(db, str(folder / "a.jpg"))
        r = client.get(f"/api/storage/{route}/{doc.id}")
    finally:
        folder.chmod(stat.S_IRWXU)
    assert r.status_code == 404
    assert r.json()["reason"] == "access_not_granted"
    assert "grant access" in r.json()["detail"]


@pytest.mark.parametrize("route", ROUTES)
def test_a_page_with_no_recorded_file_says_so(client, db, route):
    doc = _doc(db, None)
    r = client.get(f"/api/storage/{route}/{doc.id}")
    assert r.status_code == 404
    assert r.json()["reason"] == "no_recorded_file"


def test_an_unknown_document_is_still_a_plain_404(client):
    r = client.get("/api/storage/thumbnail/does-not-exist")
    assert r.status_code == 404
    assert "reason" not in r.json()


def test_the_export_words_are_the_classifiers_words(tmp_path):
    from fichero_server.export_service import _why_image_unavailable
    from fichero_server.media.image_reason import classify_image_unavailable

    doc = Document(id="a", name="A", file_type=FileType.image, path=str(tmp_path / "gone.jpg"))
    assert _why_image_unavailable(doc) == classify_image_unavailable(doc)[1]


@pytest.mark.parametrize("route", ["thumbnail", "display"])
def test_a_readable_file_that_is_not_an_image_is_not_blamed_on_the_original(client, db, tmp_path, route):
    path = tmp_path / "notes.jpg"
    path.write_bytes(b"not an image")
    doc = _doc(db, str(path))
    r = client.get(f"/api/storage/{route}/{doc.id}")
    if r.status_code == 404:
        assert "reason" not in r.json()
