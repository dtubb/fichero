"""A Tesseract .box file becomes character segments carrying their letters (#5174, ruled 2026-09-28).

WHY: the Cree syllabics in the test corpus come as page images with Tesseract box files -- one
character per line, `glyph left bottom right top page`, in pixels from the BOTTOM-left -- and no
format claimed them: the folder imported the images and the boxes went nowhere. If this
regresses, those characters are lost again, or land upside down (a box file's y runs up the
page; ours runs down).

The real file (CC-BY-4.0, fixtures/PROVENANCE.md), through `format.import` and a folder drop; what
it says is parsed here independently, by splitting its lines.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

import fichero_server.api.routes.document.format_import  # noqa: F401  (registers format.import)
import fichero_server.api.routes.ingest  # noqa: F401  (registers import.folder)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.formats import format_for
from fichero_server.models import DocType, Document, FileType
from fichero_server.models.segments import Segment

BOX = Path(__file__).resolve().parents[1] / "formats" / "fixtures" / "zenodo_cree_syllabics_02ad26d9.box"
WIDTH, HEIGHT = 1560, 2067          # the page image's size, from its PNG header (PROVENANCE.md)
BOOT = ActionContext(actor="historian", is_bootstrap=True)


def _file_says() -> list[tuple[str, list[float]]]:
    """(glyph, [x, y, w, h] as page fractions, top-left origin), straight from the file's lines."""
    out = []
    for line in BOX.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        glyph, left, bottom, right, top, _page = line.split(" ")
        left, bottom, right, top = int(left), int(bottom), int(right), int(top)
        out.append((glyph, [left / WIDTH, (HEIGHT - top) / HEIGHT, (right - left) / WIDTH, (top - bottom) / HEIGHT]))
    return out


def _page(db, width=None, height=None) -> Document:
    """A page as ingest makes it: its pixel size in metadata (`Document.width` reads it there)."""
    doc = Document(name="cree page", doc_type=DocType.file, file_type=FileType.image, path="/p/cree.png",
                   metadata={"width": width, "height": height} if width else {})
    db.save(doc)
    return doc


def _close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_the_bytes_say_box_and_other_text_is_not_claimed():
    assert format_for("anything.box", BOX.read_bytes()).name == "tesseract-box"
    assert format_for("x.box", "Inic ce capitulo vncā mitoa\n".encode()) is None or \
        format_for("x.box", "Inic ce capitulo vncā mitoa\n".encode()).name != "tesseract-box"


def test_every_box_arrives_as_a_character_with_its_letter_the_right_way_up(db):
    expected = _file_says()
    assert len(expected) == 327                                    # the premise, from the file
    doc = _page(db, width=WIDTH, height=HEIGHT)
    result = registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(BOX)}, BOOT).result
    rows = [s for s in db.query(Segment, pass_id=result["pass_id"]) if s.deleted_at is None]
    assert {s.kind for s in rows} == {"character"} and len(rows) == len(expected)
    from fichero_server.models import ContentRepresentation

    got = sorted(
        (next(r.content for r in db.query(ContentRepresentation, segment_id=s.id)),
         [s.bbox_x, s.bbox_y, s.bbox_w, s.bbox_h])
        for s in rows
    )
    for (glyph, box), (want_glyph, want_box) in zip(got, sorted(expected)):
        assert glyph == want_glyph and _close(box, want_box), (glyph, box, want_box)
    # The first line of the file, ᐅ at bottom 1974 / top 2038 of 2067: near the TOP of the page's
    # fractions would be wrong -- it sits 29 px from the image's top edge.
    first = next(b for g, b in expected if g == "ᐅ")
    assert _close([first[1]], [(HEIGHT - 2038) / HEIGHT])


def test_with_no_recorded_page_size_it_is_refused_by_name_and_nothing_is_written(db):
    doc = _page(db)
    before = len(db.all(Segment))
    with pytest.raises(HTTPException) as refusal:
        registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(BOX)}, BOOT)
    assert refusal.value.status_code == 422 and "size is not recorded" in refusal.value.detail
    assert len(db.all(Segment)) == before


def test_dropped_beside_its_image_it_becomes_that_pages_pass(db, tmp_path):
    from PIL import Image

    folder = tmp_path / "cree"
    folder.mkdir()
    Image.new("L", (WIDTH, HEIGHT), 255).save(folder / "02ad26d9.png")
    (folder / "02ad26d9.box").write_bytes(BOX.read_bytes())
    ctx = ActionContext(actor="historian", library_path=str(Path(db.path).parent), is_bootstrap=True)
    result = registry.invoke(db, "import.folder", {"path": str(folder)}, ctx).result
    assert result["interchange"]["imported_as_passes"] == ["02ad26d9.box"]
    documents = [db.get(Document, i) for i in result["document_ids"]]
    assert [d.name for d in documents if d] == ["02ad26d9.png"]    # the .box is not a document
    characters = [s for s in db.all(Segment) if s.document_id == documents[0].id and s.kind == "character"]
    assert len(characters) == 327
