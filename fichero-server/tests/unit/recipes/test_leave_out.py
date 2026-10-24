"""Leave Out marks lines that are not writing, never deleting them (`designer.clean.leaves-out-non-text`, #6070).

Geometry here is invented: fractions of a page, nothing from any archive."""
from __future__ import annotations

from fichero_server.recipes import leave_out
from fichero_server.recipes.leave_out import BLEED, OFF_THE_PAGE, TOO_SMALL, decide

PAGE = [0.0, 0.0, 1.0, 1.0]


def _line(i, x=0.1, y=None, w=0.7, h=0.04, confidence=0.9):
    return {"id": f"l{i}", "x": x, "y": 0.05 + 0.08 * i if y is None else y, "w": w, "h": h, "confidence": confidence}


def _page(n=8):
    return [_line(i) for i in range(n)]


def test_ordinary_lines_and_short_real_ones_are_all_kept():
    lines = _page() + [_line(9, w=0.05, h=0.04)]  # a short real line (a folio number) is as thick as the rest
    assert decide(lines, page_box=PAGE) == {}


def test_a_speck_and_a_far_thinner_mark_are_too_small():
    lines = _page() + [{"id": "speck", "x": 0.5, "y": 0.5, "w": 0.005, "h": 0.005, "confidence": 0.9},
                       {"id": "thin", "x": 0.2, "y": 0.9, "w": 0.4, "h": 0.006, "confidence": 0.9}]
    assert decide(lines, page_box=PAGE) == {"speck": TOO_SMALL, "thin": TOO_SMALL}


def test_with_too_few_lines_only_a_speck_is_too_small():
    """Five lines are needed for a median: two lines of different thickness say nothing about which is writing."""
    assert decide([_line(0), _line(1, h=0.006)], page_box=PAGE) == {}
    assert decide([_line(0), {"id": "speck", "x": 0.5, "y": 0.5, "w": 0.004, "h": 0.004, "confidence": 0.9}]) == {"speck": TOO_SMALL}


def test_a_line_whose_centre_is_off_the_page_box_is_off_the_page():
    box = [0.05, 0.0, 0.95, 1.0]
    lines = _page() + [{"id": "bed", "x": 0.0, "y": 0.4, "w": 0.06, "h": 0.04, "confidence": 0.9}]
    assert decide(lines, page_box=box) == {"bed": OFF_THE_PAGE}
    assert decide(lines) == {}, "with no page box nothing is off the page"


def test_off_the_page_and_too_small_can_each_be_switched_off():
    lines = _page() + [{"id": "speck", "x": 0.5, "y": 0.5, "w": 0.005, "h": 0.005, "confidence": 0.9}]
    assert decide(lines, page_box=PAGE, too_small=False) == {}


def test_bleed_through_needs_both_low_confidence_and_low_contrast():
    faint = _line(9, confidence=0.05)
    sure = _line(8, confidence=0.9)
    low, high = (lambda ln: 0.05), (lambda ln: 0.6)
    assert decide([*_page(), faint], contrast_of=low) == {"l9": BLEED}
    assert decide([*_page(), faint], contrast_of=high) == {}, "unsure but clearly inked: it stays"
    assert decide([*_page(), sure], contrast_of=low) == {}, "faint but sure: it stays"
    assert decide([*_page(), faint]) == {}, "no image to measure under it: the rule does not fire"


def test_a_vertical_line_is_judged_by_its_thinner_side():
    columns = [{"id": f"c{i}", "x": 0.05 + 0.1 * i, "y": 0.1, "w": 0.04, "h": 0.7, "confidence": 0.9} for i in range(8)]
    assert decide(columns, page_box=PAGE) == {}


def test_the_stage_marks_without_deleting_and_a_second_run_marks_nothing_new(client, db):
    """Through the real store: the row stays, `is_furniture` is set, the reason is on it, and the run is repeatable."""
    from fichero_server.models import Document, DocType, FileType, Segment, Status

    doc = Document(name="page.jpg", doc_type=DocType.file, file_type=FileType.image, path="/path/page.jpg",
                   status=Status.completed, metadata={"page_box": [0.05, 0.0, 0.95, 1.0]})
    db.save(doc)
    made = []
    for ln in [*_page(), {"id": "bed", "x": 0.0, "y": 0.4, "w": 0.06, "h": 0.04, "confidence": 0.9}]:
        row = _segment(doc.id, ln)
        db.save(row)
        made.append(row)
    account = leave_out.leave_out_pages(db, [doc.id], "run-1")
    assert account["left_out"] == 1 and account["why"] == {OFF_THE_PAGE: 1} and account["pages"] == 1
    rows = {r.id: r for r in db.query(Segment, document_id=doc.id)}
    assert len(rows) == len(made), "nothing deleted"
    bed = rows[made[-1].id]
    assert bed.is_furniture and bed.deleted_at is None and bed.metadata["left_out"]["why"] == OFF_THE_PAGE
    assert not any(r.is_furniture for r in rows.values() if r.id != bed.id)
    assert leave_out.leave_out_pages(db, [doc.id], "run-2")["left_out"] == 0


def _segment(document_id, ln):
    from fichero_server.models import Segment
    from fichero_server.models.anchors import AnchorSpace, SourceAnchor
    from fichero_server.models.knowledge import ProvenanceKind

    return Segment(
        document_id=document_id, pass_id="pass-1", kind="line",
        anchor=SourceAnchor(document_id=document_id, space=AnchorSpace.normalized, rect=[ln["x"], ln["y"], ln["w"], ln["h"]]),
        bbox_x=ln["x"], bbox_y=ln["y"], bbox_w=ln["w"], bbox_h=ln["h"], tile="x0y0", doc_kind=f"{document_id}:line",
        confidence=ln["confidence"], provenance_kind=ProvenanceKind.workflow)
