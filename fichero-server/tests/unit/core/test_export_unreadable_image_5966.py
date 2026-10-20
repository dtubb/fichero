"""An image an export cannot read fails only its page, says why, and is listed (#5966, `source.export.unreadable-image-fails-only-its-page`)."""
from __future__ import annotations

import unicodedata
from pathlib import Path

from fichero_server.export_service import export_markdown_folder, export_word_docx
from fichero_server.models import DocType, Document, FileType

LONG = ("1930. Luis Enrique Bernal contra Nicanor Córdoba y Juan Francisco Moreno (cesionario de Rito E. Flores), "
        "cobro por $608,00 pesos.1.JPG")


def _library(db, image_path: str):
    root = Document(id="root-5966", name="Archivo", doc_type=DocType.folder)
    text = Document(id="text-5966", name="Folio", parent_id=root.id, doc_type=DocType.file, file_type=FileType.text,
                    page_content="Texto del folio.")
    image = Document(id="image-5966", name="Photo One", parent_id=root.id, doc_type=DocType.file,
                     file_type=FileType.image, path=image_path)
    for row in (root, text, image):
        db.save(row)
    return root


def test_a_missing_image_fails_only_its_page_and_is_listed(db, tmp_path):
    root = _library(db, "files/missing.jpg")
    result = export_markdown_folder(db, tmp_path / "export", target_id=root.id)
    names = {Path(f.path).name for f in result.files}
    assert any(n.startswith("folio") for n in names), "the other page was written"
    note = (tmp_path / "export" / "NOT-INCLUDED.md").read_text()
    assert "Photo One" in note and "not found" in note


def test_the_words_tell_a_missing_file_from_one_the_engine_may_not_read(tmp_path):
    from fichero_server.export_service import _why_image_unavailable

    absent = Document(id="a", name="A", file_type=FileType.image, path=str(tmp_path / "gone.jpg"))
    assert "not found" in _why_image_unavailable(absent)
    nopath = Document(id="b", name="B", file_type=FileType.image)
    assert "no recorded file" in _why_image_unavailable(nopath)


def test_a_word_export_writes_the_rest_and_says_where_the_image_would_be(db, tmp_path):
    root = _library(db, "files/missing.jpg")
    out = tmp_path / "export.docx"
    export_word_docx(db, out, target_id=root.id)
    assert out.exists()
    import zipfile

    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    assert "Texto del folio" in xml and "not found" in xml


def test_a_linked_source_with_accents_dollar_parentheses_and_a_long_name_resolves_in_either_normalisation(db, tmp_path):
    from fichero_server.db.storage import resolve_source

    folder = tmp_path / unicodedata.normalize("NFD", LONG[:-4])
    folder.mkdir()
    on_disk = folder / unicodedata.normalize("NFD", LONG)
    on_disk.write_bytes(b"\xff\xd8\xff\xe0 jpeg")
    for form in ("NFC", "NFD"):
        stored = str(folder / unicodedata.normalize(form, LONG))
        doc = Document(id=f"d-{form}", name=LONG, file_type=FileType.image, path=stored)
        assert resolve_source(doc, library_root=tmp_path / "lib.fichero") is not None, form
