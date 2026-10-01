"""`source.lineeditor.estimated-words` (#5212): a word with text but no shape is still placed.

A word its file placed nowhere is kept on a whole-page anchor marked `shape: unstated`, so no
surface could draw it. The engine now estimates its place: every word of its line takes its share
of the line's box by its share of the line's characters (spaces included), along the line's
direction, and only the shapeless ones are given theirs. Served marked `geometry: estimated`,
written into PAGE XML marked, left out of ALTO and hOCR (which cannot mark it) with the word named,
and NEVER stored: if this breaks, an estimate becomes a measurement nobody made.

The case is a real file: the NZZ page of 10 July 1784 (Transkribus), whose last word on one line,
"bringt", has `<Coords points=""/>` while its six siblings are measured.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.api.routes.document.segments import _with_texts
from fichero_server.formats import read_page, write_page
from fichero_server.models import Segment
from fichero_server.models.segments import segment_read_from_row
from fichero_server.models.word_spans import estimated_span, word_fractions
from fichero_server.page_export import page_from_library
from tests.unit.api.test_page_text_follows_the_file import _import

NZZ = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus" / "transkribus_german-fraktur_nzz-17840710.page.xml"


def test_each_word_takes_its_share_of_the_line_spaces_included():
    assert word_fractions(["ab", "cde", "f"]) == [(0.0, 0.25), (0.375, 0.75), (0.875, 1.0)]
    assert word_fractions([]) == []
    assert word_fractions(["", ""]) == [(0.0, 0.0), (0.0, 0.0)]
    # A word with no text takes no characters and no space: its neighbours share the line.
    assert word_fractions(["ab", "", "cd"]) == [(0.0, 0.4), (0.6, 0.6), (0.6, 1.0)]


@pytest.mark.parametrize(("direction", "expected"), [
    (None, [0.4, 0.2, 0.3, 0.1]),       # left to right from the left edge
    ("rtl", [0.3, 0.2, 0.3, 0.1]),      # right to left from the right edge
    ("ttb", [0.1, 0.2375, 0.8, 0.0375]),  # down a column from the top
])
def test_the_share_runs_in_the_lines_direction(direction, expected):
    got = estimated_span([0.1, 0.2, 0.8, 0.1], 0.375, 0.75, direction)
    assert got == pytest.approx(expected)


@pytest.fixture
def nzz(db):
    doc_id = _import(db, NZZ)
    rows = [s for s in db.all(Segment) if s.document_id == doc_id and s.deleted_at is None]
    reads = _with_texts(db, rows, [segment_read_from_row(r) for r in rows])
    by_text = {r.text: r for r in reads if r.kind == "word"}
    return db, doc_id, rows, reads, by_text


def test_the_shapeless_word_is_served_at_the_end_of_its_line(nzz):
    db, _doc_id, rows, reads, by_text = nzz
    word = by_text["bringt"]
    assert word.metadata["geometry"] == "estimated"
    line = next(r for r in rows if r.id == word.parent_segment_id)
    lx, ly, lw, lh = line.anchor.rect
    x, y, w, h = word.anchor.rect
    # The last 6 of the line's 46 characters, spaces included, at the right end of the line's box.
    assert (y, h) == pytest.approx((ly, lh))
    assert x + w == pytest.approx(lx + lw)
    assert w == pytest.approx(lw * 6 / 46)
    # Measured words are not estimated, and keep their own boxes.
    measured = [r for r in reads if r.parent_segment_id == line.id and r.id != word.id]
    assert measured and all("geometry" not in r.metadata for r in measured)


def test_the_estimate_is_never_stored(nzz):
    db, _doc_id, _rows, _reads, by_text = nzz
    stored = db.get(Segment, by_text["bringt"].id)
    assert stored.metadata.get("shape") == "unstated"
    assert "geometry" not in stored.metadata
    assert list(stored.anchor.rect) == [0, 0, 1, 1]


def test_page_xml_marks_it_and_a_re_import_gives_it_back_shapeless(nzz):
    db, doc_id, _rows, _reads, _by_text = nzz
    page, _choices = page_from_library(db, doc_id)
    data, report = write_page("pagexml", page)
    assert data.count(b"fichero {geometry:estimated;}") == 1
    assert "words placed by estimate" in report.lost
    back = [s for s in read_page("pagexml", data).segments if s.readings and s.readings[0][1] == "bringt"]
    assert len(back) == 1 and back[0].rect is None and back[0].polygon is None


@pytest.mark.parametrize("fmt", ["alto", "hocr"])
def test_alto_and_hocr_leave_it_out_and_name_the_word(nzz, fmt):
    db, doc_id, _rows, _reads, by_text = nzz
    page, _choices = page_from_library(db, doc_id)
    data, report = write_page(fmt, page)
    assert by_text["bringt"].id in str(report.as_dict())  # the word is named
    root = etree.fromstring(data) if fmt == "alto" else etree.HTML(data)
    if fmt == "alto":
        word = next(el for el in root.iter() if etree.QName(el).localname == "String" and el.get("CONTENT") == "bringt")
        assert word.get("HPOS") is None
    else:
        word = next(el for el in root.iter() if (el.text or "").strip() == "bringt")
        assert "bbox" not in (word.get("title") or "")
