"""A same-named .txt beside an image becomes that page's transcription (#5174, ruled 2026-09-28).

WHY: the Florentine Codex folder in the test corpus is page images with the edition's text for
each page beside it, `Florentine_Codex_book12_1r.jpg` + `..._1r.txt`, and no layout. Before this
the .txt imported as a separate text document, so the page had no text and the text had no page.
The ruling: one reading, no boxes -- the text is anchored to the page with its shape unstated,
because the file says nothing about where on the page it is. If this regresses the text leaves
the page again, or a box is invented for it.

Only a .txt whose STEM is an image's pairs: a folder's other .txt files (notes, YOLO labels, a
`classes.txt`) are left exactly as before.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fichero_server.api.routes.ingest  # noqa: F401  (registers import.folder)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.importers.interchange_pairing import plan_pairs
from fichero_server.models import ContentRepresentation, Document
from fichero_server.models.segments import Segment

NAHUATL = (
    Path.home() / "Fichero Test Corpus"
    / "Nahuatl - Florentine Codex, Book 12 (transcription beside image, no layout)"
    / "Florentine_Codex_book12_1r.txt"
)


def _drop(db, folder: Path) -> dict:
    ctx = ActionContext(actor="historian", library_path=str(Path(db.path).parent), is_bootstrap=True)
    return registry.invoke(db, "import.folder", {"path": str(folder)}, ctx).result


def _image(path: Path) -> None:
    from PIL import Image

    Image.new("L", (400, 600), 255).save(path)


def _the_pages_text(db, result: dict, image_name: str) -> tuple[Document, list[Segment]]:
    documents = [db.get(Document, i) for i in result["document_ids"]]
    [page] = [d for d in documents if d and d.name == image_name]
    return page, [s for s in db.all(Segment) if s.document_id == page.id and s.deleted_at is None]


def test_the_text_becomes_one_reading_on_its_page_with_no_box(db, tmp_path):
    folder = tmp_path / "codex"
    folder.mkdir()
    _image(folder / "f1r.png")
    text = "In aiamo vallaci españoles, oc matlacxivitl,\ncentlamātli tetzavitl achto nez."
    (folder / "f1r.txt").write_text(text + "\n", encoding="utf-8")

    result = _drop(db, folder)

    assert result["interchange"]["imported_as_passes"] == ["f1r.txt"]
    names = [db.get(Document, i).name for i in result["document_ids"] if db.get(Document, i)]
    assert names == ["f1r.png"]                                   # the .txt is not a document
    page, rows = _the_pages_text(db, result, "f1r.png")
    [segment] = rows                                              # ONE reading, not one per line
    assert segment.metadata.get("shape") == "unstated"            # no box invented
    [reading] = db.query(ContentRepresentation, segment_id=segment.id)
    assert reading.content == text
    assert "centlamātli tetzavitl" in document_text(db, page.id).text


def test_a_txt_with_no_image_of_its_stem_stays_an_ordinary_file(tmp_path):
    _image(tmp_path / "f1r.png")
    notes = tmp_path / "notes.txt"
    notes.write_text("remember to check folio 2\n", encoding="utf-8")
    labels = tmp_path / "f1r-labels.txt"
    labels.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    plan = plan_pairs([tmp_path / "f1r.png", notes, labels])

    assert plan.pairs == {} and plan.unpaired == {}               # not named, not paired


def test_yolo_labels_named_after_their_image_are_not_read_as_a_transcription(tmp_path):
    _image(tmp_path / "f1r.png")
    labels = tmp_path / "f1r.txt"
    labels.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    plan = plan_pairs([tmp_path / "f1r.png", labels])

    assert plan.formats.get(labels) != "plain-text"


def test_the_florentine_codex_page_arrives_whole(db, tmp_path):
    """The real file: four editions of folio 1r (two Nahuatl, a Spanish, an English), 2,982 bytes.
    CC BY-NC-ND, so it is the local corpus's and not vendored; it runs where that folder exists.
    The image is a stand-in of the same stem -- the 11 MB scan adds nothing the pairing reads."""
    if not NAHUATL.exists():
        pytest.skip(f"{NAHUATL.name} is in the local corpus only")
    folder = tmp_path / "florentine"
    folder.mkdir()
    _image(folder / "Florentine_Codex_book12_1r.jpg")
    (folder / NAHUATL.name).write_bytes(NAHUATL.read_bytes())

    result = _drop(db, folder)

    page, [segment] = _the_pages_text(db, result, "Florentine_Codex_book12_1r.jpg")
    [reading] = db.query(ContentRepresentation, segment_id=segment.id)
    assert reading.content == NAHUATL.read_text(encoding="utf-8").strip()
    assert "Inic ce capitulo vncā mitoa" in document_text(db, page.id).text
