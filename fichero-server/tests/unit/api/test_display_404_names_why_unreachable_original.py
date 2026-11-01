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
    assert r.status_code == 404
    assert "reason" not in r.json()


@pytest.mark.parametrize("route", ROUTES)
def test_a_readable_file_the_engine_refuses_is_access_not_granted(client, db, tmp_path, route):
    """The path is a file this process can read, but it names `..`, so `resolve_source` refuses it (confinement)."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.jpg").write_bytes(b"x")
    doc = _doc(db, str(tmp_path / "sub" / ".." / "a.jpg"))
    r = client.get(f"/api/storage/{route}/{doc.id}")
    assert r.status_code == 404
    assert r.json()["reason"] == "access_not_granted"


@pytest.mark.parametrize("route", ROUTES)
def test_a_pdf_page_on_a_drive_that_is_gone_says_the_drive_is_not_connected(client, db, route):
    parent = Document(name="Letter", doc_type=DocType.file, file_type=FileType.pdf,
                      path="/Volumes/NoSuchDriveForTest6308/Originals/letter.pdf")
    db.save(parent)
    page = Document(name="Letter p1", doc_type=DocType.page, file_type=None, parent_id=parent.id, sequence=1,
                    metadata={"pdf_path": parent.path})  # as ingest saves a PDF page: no path of its own
    db.save(page)
    r = client.get(f"/api/storage/{route}/{page.id}")
    assert r.status_code == 404
    assert r.json()["reason"] == "volume_not_mounted"


@pytest.mark.parametrize("route", ROUTES)
def test_a_page_whose_path_is_in_its_metadata_is_classified_by_that_path(client, db, route):
    doc = Document(name="Folio 1", doc_type=DocType.page, file_type=FileType.image,
                   metadata={"source_path": "/Volumes/NoSuchDriveForTest6308/Originals/a.jpg"})
    db.save(doc)
    r = client.get(f"/api/storage/{route}/{doc.id}")
    assert r.status_code == 404
    assert r.json()["reason"] == "volume_not_mounted"


@pytest.mark.parametrize("route", ROUTES)
def test_a_path_that_loops_is_unreadable(client, db, tmp_path, route):
    loop = tmp_path / "loop.jpg"
    loop.symlink_to(loop)
    doc = _doc(db, str(loop))
    r = client.get(f"/api/storage/{route}/{doc.id}")
    assert r.status_code == 404
    assert r.json()["reason"] == "unreadable"


@pytest.mark.parametrize("route", ROUTES)
def test_the_classifier_runs_off_the_event_loop(client, db, tmp_path, monkeypatch, route):
    import asyncio

    from fichero_server.media import image_reason

    seen: list[bool] = []
    real = image_reason.classify_image_unavailable

    def spy(*args, **kwargs):
        try:
            asyncio.get_running_loop()
            seen.append(True)
        except RuntimeError:
            seen.append(False)
        return real(*args, **kwargs)

    monkeypatch.setattr(image_reason, "classify_image_unavailable", spy)
    doc = _doc(db, str(tmp_path / "gone.jpg"))
    assert client.get(f"/api/storage/{route}/{doc.id}").status_code == 404
    assert seen == [False]


def test_a_path_that_cannot_be_statted_is_unreadable_not_an_error():
    from fichero_server.media.image_reason import UNREADABLE, classify_image_unavailable

    for path in ("/tmp/a\0b.jpg", "~nosuchuser6308/a.jpg"):
        doc = Document(id="a", name="A", file_type=FileType.image, path=path)
        code, words = classify_image_unavailable(doc)
        assert code == UNREADABLE and "nosuchuser" not in words and "\0" not in words


def _locked(tmp_path):
    folder = tmp_path / "locked"
    folder.mkdir()
    (folder / "a.jpg").write_bytes(b"x")
    folder.chmod(0)
    return folder


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("case", ["locked", "gone", "volume", "loop"])
@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a folder with no permissions")
def test_no_local_path_reaches_the_response_body(client, db, tmp_path, route, case):
    folder = None
    if case == "locked":
        folder = _locked(tmp_path)
        recorded = str(folder / "a.jpg")
    elif case == "gone":
        recorded = str(tmp_path / "secret-folder-6308" / "gone.jpg")
    elif case == "volume":
        recorded = "/Volumes/NoSuchDriveForTest6308/secret-folder-6308/a.jpg"
    else:
        loop = tmp_path / "secret-loop-6308.jpg"
        loop.symlink_to(loop)
        recorded = str(loop)
    try:
        doc = _doc(db, recorded)
        r = client.get(f"/api/storage/{route}/{doc.id}")
    finally:
        if folder is not None:
            folder.chmod(stat.S_IRWXU)
    assert r.status_code == 404 and "reason" in r.json()
    for fragment in (str(tmp_path), "secret-", "locked", "a.jpg", "gone.jpg"):
        assert fragment not in r.text


@pytest.fixture
def quiet(client):
    """The same app and library, but a server error comes back as a 500 instead of raising in the test."""
    from fastapi.testclient import TestClient

    from fichero_server.api.main import app

    return TestClient(app, headers=dict(client.headers), raise_server_exceptions=False)


@pytest.mark.parametrize("route", ROUTES)
def test_a_home_folder_of_a_user_that_does_not_exist_is_unreadable_not_a_500(quiet, db, route):
    doc = _doc(db, "~nosuchuser6308/a.jpg")
    r = quiet.get(f"/api/storage/{route}/{doc.id}")
    assert r.status_code == 404
    assert r.json()["reason"] == "unreadable"
    assert "nosuchuser" not in r.text


def _page_under(db, parent_path: str, parent_type: FileType | None = None):
    parent = Document(name="Folder", doc_type=DocType.folder if parent_type is None else DocType.file,
                      file_type=parent_type, path=parent_path)
    db.save(parent)
    page = Document(name="Page", doc_type=DocType.page, file_type=None, parent_id=parent.id, sequence=1)
    db.save(page)
    return page


@pytest.mark.parametrize("route", ROUTES)
def test_a_page_under_a_folder_that_has_a_file_still_has_no_recorded_file(client, db, tmp_path, route):
    (tmp_path / "a.pdf").write_bytes(b"x")
    page = _page_under(db, str(tmp_path / "a.pdf"))
    r = client.get(f"/api/storage/{route}/{page.id}")
    assert r.status_code == 404
    assert r.json()["reason"] == "no_recorded_file"


@pytest.mark.parametrize("route", ROUTES)
def test_a_page_under_a_folder_on_a_gone_drive_is_not_blamed_on_the_drive(client, db, route):
    page = _page_under(db, "/Volumes/NoSuchDriveForTest6308/x")
    r = client.get(f"/api/storage/{route}/{page.id}")
    assert r.status_code == 404
    assert r.json()["reason"] == "no_recorded_file"
