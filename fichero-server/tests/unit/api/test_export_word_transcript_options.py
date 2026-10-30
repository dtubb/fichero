"""catalogue.export.word-transcript-options (#6287): images off, a page break per page, blank pages listed once."""
import zipfile

from fichero_server.models import DocType, Document, FileType


def _folder_with_pages(db, tmp_path):
    folder = Document(id="tw-folder", name="Doc uno", doc_type=DocType.folder)
    image = db.path.parent / "files" / "a.jpg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"jpg bytes")
    db.save(folder)
    for n, (text, attrs) in enumerate([("Texto uno.", {}), ("", {"material": "blank"}), ("", {"material": "blank"}),
                                       ("", {"material": "blank"}), ("Texto dos.", {})], start=17):
        db.save(Document(id=f"tw-{n}", name=f"IMG_{n:03d}.jpg", parent_id=folder.id, doc_type=DocType.file,
                         file_type=FileType.image, path=str(image), page_content=text, attributes=attrs, sequence=n))
    return folder


def _xml(client, folder, tmp_path, **options):
    out = tmp_path / "t.docx"
    r = client.post("/api/export/word", json={"target_id": folder.id, "output_path": str(out),
                                              "include_knowledge_graph": False, **options})
    assert r.status_code == 200, r.text
    with zipfile.ZipFile(out) as docx:
        return docx.read("word/document.xml").decode(), set(docx.namelist())


def test_the_defaults_are_the_readers_export_unchanged(client, db, tmp_path):
    xml, names = _xml(client, _folder_with_pages(db, tmp_path), tmp_path)
    assert "<w:tbl>" in xml and "word/media/image1.jpg" in names
    assert 'w:type="page"' not in xml and "Páginas en blanco" not in xml


def test_images_off_prints_neither_image_nor_note(client, db, tmp_path):
    xml, names = _xml(client, _folder_with_pages(db, tmp_path), tmp_path, include_images=False)
    assert "<w:tbl>" not in xml and not any(n.startswith("word/media") for n in names)
    assert "Image not included" not in xml and "Texto uno." in xml and "IMG_017.jpg" in xml


def test_a_page_break_comes_before_each_page(client, db, tmp_path):
    xml, _ = _xml(client, _folder_with_pages(db, tmp_path), tmp_path, include_images=False, page_break_per_page=True)
    assert xml.count('<w:br w:type="page"/>') == 5


def test_blank_pages_are_listed_once_at_the_end_as_ranges(client, db, tmp_path):
    xml, _ = _xml(client, _folder_with_pages(db, tmp_path), tmp_path, include_images=False,
                  page_break_per_page=True, blank_pages_listed_once=True)
    assert xml.count("No text content available.") == 0
    assert xml.count("Páginas en blanco: IMG_018\u2013IMG_020") == 1
    assert xml.count('<w:br w:type="page"/>') == 2  # the two read pages only
    assert xml.index("Texto dos.") < xml.index("Páginas en blanco")
