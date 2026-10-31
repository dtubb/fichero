"""POST /api/export/word transcript options (#6287): include_images."""

import zipfile

from fichero_server.api.routes.ingest.export import WordExportRequest
from fichero_server.models import DocType, Document, FileType


def _folder_with_image(db, *, image_exists=True):
    folder = Document(id="w6287-folder", name="Box", doc_type=DocType.folder)
    image_path = db.path.parent / "files" / "scan.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    if image_exists:
        image_path.write_bytes(b"jpg bytes")
    page = Document(
        id="w6287-page",
        name="Page 1",
        parent_id=folder.id,
        doc_type=DocType.file,
        file_type=FileType.image,
        path=str(image_path),
        page_content="Page transcription.",
    )
    db.save(folder)
    db.save(page)
    return folder


def _export(client, folder, out, **extra):
    r = client.post(
        "/api/export/word",
        json={"target_id": folder.id, "output_path": str(out), **extra},
    )
    assert r.status_code == 200, r.text
    with zipfile.ZipFile(out) as docx:
        return docx.namelist(), docx.read("word/document.xml").decode()


def test_request_model_default_includes_images():
    assert WordExportRequest(output_path="x.docx").include_images is True


def test_default_and_true_embed_images(client, db, tmp_path):
    folder = _folder_with_image(db)
    names, _ = _export(client, folder, tmp_path / "a.docx")
    assert any(n.startswith("word/media/") for n in names)
    names, _ = _export(client, folder, tmp_path / "b.docx", include_images=True)
    assert any(n.startswith("word/media/") for n in names)


def test_images_off_has_no_media_and_no_note(client, db, tmp_path):
    folder = _folder_with_image(db)
    names, xml = _export(client, folder, tmp_path / "c.docx", include_images=False)
    assert not any(n.startswith("word/media/") for n in names)
    assert "Page transcription." in xml
    assert "Image not included" not in xml


def test_images_off_never_touches_a_missing_scan(client, db, tmp_path, monkeypatch):
    folder = _folder_with_image(db, image_exists=False)

    def boom(*a, **k):
        raise AssertionError("image source must not be resolved")

    monkeypatch.setattr("fichero_server.export_service._docx_image_source", boom)
    names, xml = _export(client, folder, tmp_path / "d.docx", include_images=False)
    assert not any(n.startswith("word/media/") for n in names)
    assert "Image not included" not in xml
