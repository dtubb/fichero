"""#6130 (`source.read.blank-page-is-not-a-failed-read`): a page that comes back empty because nothing is on it is a blank
page, not a failed read. Owner's Test 17 run: 3 of 20 pages 'failed: most lines came back empty: the reader may not
suit this hand'; some were probably covers or the backs of leaves."""
from __future__ import annotations

from PIL import Image, ImageDraw

from fichero_server.models import Document
from fichero_server.models.segments import Segment
from fichero_server.recipes import run_view, sorting
from fichero_server.recipes.done import NOTHING_FOR_PAGE, failed_reads
from tests.unit.recipes.test_unread_lines_not_read_5758 import _page


def _empty_read_page(db, tmp_path, name: str, inked: bool) -> str:
    """A page with 6 found lines, none read (each unread with the failed-read reason), over a real image."""
    image = Image.new("L", (400, 600), 255)
    if inked:
        draw = ImageDraw.Draw(image)
        for row in range(24):  # thin strokes like handwriting (a solid bar is read as paper by the ink measure)
            for x in range(40, 360, 8):
                draw.line([x, 40 + row * 22, x + 3, 49 + row * 22], fill=30, width=2)
    path = tmp_path / f"{name}.png"
    image.save(path)
    page = _page(db, 6, 0)
    doc = db.get(Document, page)
    doc.path = str(path)
    db.save(doc)
    for seg in db.query(Segment, document_id=page):
        seg.metadata = {**(seg.metadata or {}), "unread_reason": NOTHING_FOR_PAGE}
        db.save(seg)
    return page


def test_a_blank_page_is_marked_blank_and_is_not_a_failure(db, tmp_path):
    page = _empty_read_page(db, tmp_path, "cover", inked=False)

    assert failed_reads(db, [page], mark_blank=True) == []
    attrs = db.get(Document, page).attributes
    assert attrs[sorting.KIND] == sorting.BLANK and attrs[sorting.SET_BY] == sorting.BY_SORTING
    assert run_view.pages_read_nothing(db, [page]) == 0, "nor does the summary count it"


def test_a_page_with_ink_that_comes_back_empty_still_fails_with_the_hand_words(db, tmp_path):
    page = _empty_read_page(db, tmp_path, "written", inked=True)

    failed = failed_reads(db, [page], mark_blank=True)
    assert failed == [(page, NOTHING_FOR_PAGE)]
    assert sorting.KIND not in (db.get(Document, page).attributes or {}), "an inked page is never marked blank"


def test_a_page_a_person_called_blank_is_no_failure_either(db, tmp_path):
    page = _empty_read_page(db, tmp_path, "back", inked=True)
    doc = db.get(Document, page)
    doc.attributes = {sorting.KIND: sorting.BLANK, sorting.SET_BY: sorting.BY_PERSON}
    db.save(doc)

    assert failed_reads(db, [page]) == []
