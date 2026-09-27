"""A text-only page imports with its text and is never refused (acceptance defect 3).

A TEI edition with no geometry (the DDbDP papyri: no `<facsimile>`; the Digital Genji: lines whose
`<lb>` names no zone) was refused by `format.import` with "segments lie outside a page of unstated
size" -- a sentence about shapes, for segments that have none. The transcription was lost.

The rule pinned: a segment whose file states no place is anchored to its page, marked
`shape: unstated`, and exported with no shape; a segment whose shape lies OUTSIDE the page is
still refused (`test_import_into_library.py`), because that is a different fact.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.formats import read_page, write_page
from fichero_server.models import Segment
from fichero_server.page_export import page_from_library
from tests.unit.api.test_page_text_follows_the_file import _import

CORPUS = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus"
TEXT_ONLY = [CORPUS / "digitalgenji_japanese-vertical_kouigenji-01.tei.xml",
             *sorted(CORPUS.glob("ddbdp_*.tei.xml"))]
#: A phrase from each file, read by eye from the file itself.
PHRASES = {
    "digitalgenji_japanese-vertical_kouigenji-01.tei.xml": "いつれの御時にか",
    "ddbdp_greek-papyrus_p.cair.zen.4.59742.tei.xml": "ληνοῦ κεχωνημένα",
}


@pytest.mark.parametrize("path", TEXT_ONLY, ids=lambda p: p.name)
def test_it_imports_with_its_text(db, path):
    source = read_page("tei", path.read_bytes())
    assert all(s.rect is None and s.polygon is None for s in source.segments), "not a text-only file"
    doc_id = _import(db, path)
    rows = [s for s in db.all(Segment) if s.document_id == doc_id]
    assert len(rows) == len(source.segments)
    assert {s.metadata.get("shape") for s in rows} == {"unstated"}
    text = document_text(db, doc_id).text
    # Every segment's text is on the page. A segment with several readings (an `<app>`'s `<lem>`
    # and `<rdg>`) shows ONE of them -- which one counts is a separate question, not this test's.
    with_text = [s for s in source.segments if s.readings]
    assert with_text and all(any(t in text for _kind, t in s.readings) for s in with_text)
    if path.name in PHRASES:
        assert PHRASES[path.name] in text


@pytest.mark.parametrize("path", TEXT_ONLY, ids=lambda p: p.name)
def test_its_export_invents_no_shape(db, path):
    doc_id = _import(db, path)
    page, _choices = page_from_library(db, doc_id)
    assert all(s.rect is None and s.polygon is None for s in page.segments)
    data, _report = write_page("tei", page)
    assert b"<zone" not in data


@pytest.mark.parametrize("path", sorted(CORPUS.glob("ddbdp_*.tei.xml")), ids=lambda p: p.name)
def test_no_line_loses_its_text_to_a_one_word_variant(db, path):
    """An `<app>` varying ONE word of a line (P.Flor. 2 133: `<lem>ἰδώτων</lem><rdg>ἰδόντων</rdg>`)
    used to become a rival reading of the WHOLE line; in a strict project two disagreeing readings
    count as none, and four lines of the papyrus vanished from its text. The variant is kept with
    its position and named by the export's loss report instead."""
    from lxml import etree

    doc_id = _import(db, path)
    derived = document_text(db, doc_id)
    assert [s.segment_id for s in derived.spans if s.representation_id is None] == []
    apps = [a for a in etree.parse(str(path)).getroot().iter("{http://www.tei-c.org/ns/1.0}app")]
    page, _choices = page_from_library(db, doc_id)
    kept = [v for s in page.segments for v in s.foreign.get("tei-app", [])]
    rdgs = [r for a in apps for r in a.iter("{http://www.tei-c.org/ns/1.0}rdg")
            if "".join(r.itertext()).strip() and not any(
                x.tag == "{http://www.tei-c.org/ns/1.0}del" for x in a.iterancestors())]
    assert len(kept) == len(rdgs)
    _data, report = write_page("tei", page)
    assert len([loss for loss in report.losses if loss.what == "variant readings"]) == len(rdgs)
