"""A page with lines but no readings is not read (#6264), tested to the spec `source.recipe.read-resumes-per-line`
(docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: on the M1 Air (b18), Start on a 31-page document read 12 pages; the other 19 had lines from an earlier run and
their readings taken back, were counted as read, and the names step then left each out ("no line of its working
pass has a reading"). The done check reads what the reader reads: a reading taken back is no reading.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fichero_server.models import ContentRepresentation
from fichero_server.recipes.done import is_done, split_done
from tests.unit.recipes.test_unread_lines_not_read_5758 import _page

CARD = {"job": "read-a-line", "model_override": None}


def _taken_back(db, page):
    for reading in db.query(ContentRepresentation, document_id=page):
        reading.retracted_at = datetime.now(timezone.utc)
        db.save(reading)


def test_a_page_with_lines_and_no_readings_is_not_read_and_one_with_readings_is(db):
    lines_only, read = _page(db, 4, 0), _page(db, 4, 4)
    assert is_done(db, CARD, lines_only) is False and is_done(db, CARD, read) is True
    assert split_done(db, CARD, [lines_only, read]) == ([lines_only], 1)


def test_a_page_whose_readings_were_taken_back_is_read_again(db):
    page = _page(db, 4, 4)
    _taken_back(db, page)
    assert is_done(db, CARD, page) is False
    assert split_done(db, CARD, [page]) == ([page], 0)


def test_a_page_with_lines_and_empty_readings_is_not_read_and_one_with_text_is(db):
    """A line whose reading carries no text (empty content) has no reading text: the page is unread (#6264)."""
    from fichero_server.models import Document, DocType, FileType
    from fichero_server.models.anchors import SourceAnchor
    from fichero_server.models.segments import Segment, SegmentPass, ProvenanceKind, bbox_and_tile_from_anchor

    def _page_with_content(doc_name, n, content):
        doc = Document(name=doc_name, doc_type=DocType.file, file_type=FileType.image, path="/" + doc_name)
        db.save(doc)
        pas = SegmentPass(document_id=doc.id, name="lines", provenance_kind=ProvenanceKind.workflow)
        db.save(pas)
        for i in range(n):
            anchor = SourceAnchor(document_id=doc.id, rect=[0.1, 0.9 * i / n, 0.6, 0.5 / n])
            x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
            seg = Segment(document_id=doc.id, pass_id=pas.id, kind="line", anchor=anchor, bbox_x=x, bbox_y=y,
                          bbox_w=w, bbox_h=h, tile=tile, doc_kind=f"{doc.id}:line",
                          provenance_kind=ProvenanceKind.workflow)
            db.save(seg)
            db.save(ContentRepresentation(document_id=doc.id, segment_id=seg.id, kind="transcription",
                                          content=content, source_anchor=anchor))
        return doc.id

    empty = _page_with_content("e.png", 4, "")
    text = _page_with_content("t.png", 4, "texto")
    assert is_done(db, CARD, empty) is False
    assert is_done(db, CARD, text) is True
    assert split_done(db, CARD, [empty]) == ([empty], 0)
    assert split_done(db, CARD, [text]) == ([], 1)

