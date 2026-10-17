"""A page whose found lines mostly have no reading is not "read" (#5758), tested to the spec
`source.onboard.auto.results-summary` (docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: a handwritten 5-page run found 114 lines, read 51, and said "Read 5 of 5 pages, 0 failed".
"""

from __future__ import annotations

from fichero_server.models import ContentRepresentation, DocType, Document, FileType
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import Segment, SegmentPass, bbox_and_tile_from_anchor
from fichero_server.recipes import run_view


def _page(db, lines: int, read: int) -> str:
    doc = Document(name="p.png", doc_type=DocType.file, file_type=FileType.image, path="/p.png")
    db.save(doc)
    pas = SegmentPass(document_id=doc.id, name="lines", provenance_kind=ProvenanceKind.workflow)
    db.save(pas)
    for i in range(lines):
        anchor = SourceAnchor(document_id=doc.id, rect=[0.1, 0.05 * i, 0.6, 0.04])
        x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
        seg = Segment(document_id=doc.id, pass_id=pas.id, kind="line", anchor=anchor, bbox_x=x, bbox_y=y,
                      bbox_w=w, bbox_h=h, tile=tile, doc_kind=f"{doc.id}:line",
                      provenance_kind=ProvenanceKind.workflow)
        db.save(seg)
        if i < read:
            db.save(ContentRepresentation(document_id=doc.id, segment_id=seg.id, kind="transcription",
                                          content="texto", source_anchor=anchor))
    return doc.id


def test_lines_without_a_reading_are_counted_and_the_page_is_not_read(db):
    whole, partial, none = _page(db, 3, 3), _page(db, 10, 3), _page(db, 0, 0)

    assert run_view.lines_unread(db, [whole, partial, none]) == 7
    assert run_view.pages_fully_read(db, [whole, partial, none]) == [whole]


def test_the_summary_words_say_how_many_lines_are_unread():
    s = run_view.RecipeRunSummary(job_id="j", state="done", finished=True, pages=5, pages_read=2, names=[],
                                  dates=0, statements=0, lines_unread=63, failed=[], pages_failed=0,
                                  skipped=[], not_run=[])
    said = run_view._lines(s, 0)
    assert "Read 2 of 5 pages" in said and any("63 lines have no reading" in w for w in said), said


def test_a_second_start_reads_again_every_page_with_unread_lines(db):
    from fichero_server.recipes.done import is_done

    card = {"job": "read-a-line", "model_override": None}
    whole, partial, unread = _page(db, 3, 3), _page(db, 10, 3), _page(db, 4, 0)

    assert is_done(db, card, whole) is True
    assert is_done(db, card, partial) is False
    assert is_done(db, card, unread) is False
