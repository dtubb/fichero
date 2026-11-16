"""catalogue.export.word-transcript-per-folder (#6287): one .docx per folder, in one call, and as a kept export."""
import io
import zipfile

import pytest

from fichero_server import kept_export
from fichero_server.export_service import export_word_transcripts
from tests.unit.export.helpers import folder, page


def _box(db):
    box = folder(db, "Caja", proto=None)
    a = folder(db, "Doc A", box.id, seq=1)
    b = folder(db, "Doc A", box.id, seq=2)  # the same name: ` 2`
    folder(db, "Vacía", box.id, seq=3)  # no pages: no file
    page(db, "IMG_001.jpg", a.id, seq=1).page_content = None
    for f, text in ((a, "Texto A uno."), (b, "Texto B uno.")):
        p = page(db, "IMG_100.jpg", f.id, seq=5)
        p.page_content = text
        db.save(p)
    page(db, "IMG_101.jpg", a.id, attrs={"material": "blank"}, seq=6)
    return box


def _read(path):
    with zipfile.ZipFile(path) as z:
        return {n: zipfile.ZipFile(io.BytesIO(z.read(n))).read("word/document.xml").decode() for n in z.namelist()}


def test_one_docx_per_folder_with_pages_named_by_the_folder(db, tmp_path):
    box = _box(db)
    result = export_word_transcripts(db, tmp_path / "t.zip", box.id)
    files = _read(result.output_path)
    assert sorted(files) == ["Doc A 2.docx", "Doc A.docx"]
    assert "Texto A uno." in files["Doc A.docx"] and "Texto B uno." in files["Doc A 2.docx"]
    assert "Texto A uno." not in files["Doc A 2.docx"]


def test_each_file_has_no_images_a_break_per_page_and_the_blank_list(db, tmp_path):
    box = _box(db)
    xml = _read(export_word_transcripts(db, tmp_path / "t.zip", box.id).output_path)["Doc A.docx"]
    assert "<w:tbl>" not in xml and 'w:type="page"' in xml
    assert "Páginas en blanco: IMG_101" in xml and "No text content available" not in xml.split("Páginas")[1]


def test_an_existing_zip_is_refused_without_overwrite(db, tmp_path):
    box = _box(db)
    export_word_transcripts(db, tmp_path / "t.zip", box.id)
    with pytest.raises(FileExistsError):
        export_word_transcripts(db, tmp_path / "t.zip", box.id)


def test_the_route_per_folder_returns_the_zip(client, db, tmp_path):
    box = _box(db)
    out = tmp_path / "r.zip"
    r = client.post("/api/export/word", json={"target_id": box.id, "output_path": str(out), "per": "folder"})
    assert r.status_code == 200, r.text
    assert r.json()["files"] == ["Doc A.docx", "Doc A 2.docx"] and sorted(_read(out)) == sorted(r.json()["files"])


def test_the_kept_format_writes_one_file_per_folder_and_refuses_per_page(db):
    with pytest.raises(kept_export.KeptExportRefused, match="not one per page"):
        kept_export.keep(db, "/tmp", "word-transcript", "page")
    box = _box(db)
    export = {"id": "e", "folder": "/x", "format": "word-transcript", "per": "document"}
    units = kept_export._units(db, export)
    assert sorted(u.filename for u in units) == ["Doc A 2.docx", "Doc A.docx"] and box.id
