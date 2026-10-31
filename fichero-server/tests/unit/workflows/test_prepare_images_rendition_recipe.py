"""The recipe's prepared image is a rendition in the library, in the source's format (`prep.prepared-image-attached-as-rendition`,
#5386).

WHY: a prepared page lived only in $TMPDIR (and as a PNG 2.4x its JPEG source), so the library pointed at nothing the
person could switch to. The rendition row points inside the library, the file is there, and the original is untouched.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from fichero_server.models import DocType, Document, FileType, Rendition


def _faded(path: Path, fmt: str) -> None:
    rng = np.random.default_rng(2)
    arr = np.clip(190 + rng.normal(0, 4, (200, 300, 3)), 0, 255).astype("uint8")  # grey spread well under 100
    arr[90:100, 40:260] = 150
    Image.fromarray(arr).save(path, format=fmt)


def _doc(db, path: Path) -> Document:
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    return doc


def test_a_jpeg_page_is_prepared_into_a_jpeg_rendition_in_the_library(db, tmp_path):
    from fichero_server.recipes.prepare import prepare_pages

    source = tmp_path / "page.jpg"
    _faded(source, "JPEG")
    before = source.read_bytes()
    doc = _doc(db, source)

    account = prepare_pages(db, [doc.id], "run-1")

    (row,) = db.query(Rendition, document_id=doc.id)
    stored = Path(db.path).parent / row.path
    assert account["prepared"] == 1 and row.role == "prepared" and not row.is_primary
    assert stored.is_file() and stored.suffix == ".jpg" and str(stored).startswith(str(Path(db.path).parent))
    with Image.open(stored) as made:
        assert made.format == "JPEG"
    assert source.read_bytes() == before, "the original is never written to"


def test_a_png_page_is_prepared_into_a_png_rendition(db, tmp_path):
    from fichero_server.recipes.prepare import prepare_pages

    source = tmp_path / "page.png"
    _faded(source, "PNG")
    doc = _doc(db, source)
    prepare_pages(db, [doc.id], "run-1")
    (row,) = db.query(Rendition, document_id=doc.id)
    assert (Path(db.path).parent / row.path).suffix == ".png"
