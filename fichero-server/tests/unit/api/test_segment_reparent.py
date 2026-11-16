"""source.editor.order-list-drag-reorders-and-reparents (docs/contributor_manual/specs/source/segment-editor-crud.md, #6476).

`segment.reparent`: a line dragged into a region. One audited action, one undo step, all or nothing.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import registry
from fichero_server.models import ActionAudit
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import Segment, SegmentPass
from tests.unit.api.test_document_derived_text import _make_doc, _person


def _segment(db, doc, pass_row, kind, *, parent=None, y=0.1):
    row = Segment(
        document_id=doc.id, pass_id=pass_row.id, kind=kind, doc_kind=f"{doc.id}:{kind}",
        anchor=SourceAnchor(document_id=doc.id, rect=[0.1, y, 0.5, 0.04]),
        bbox_x=0.1, bbox_y=y, bbox_w=0.5, bbox_h=0.04, tile="",
        provenance_kind=ProvenanceKind.human, parent_segment_id=parent,
    )
    db.save(row)
    return row


def _page(db):
    doc = _make_doc(db)
    pass_row = SegmentPass(document_id=doc.id, name="by hand", provenance_kind=ProvenanceKind.human)
    db.save(pass_row)
    region_one = _segment(db, doc, pass_row, "region", y=0.0)
    region_two = _segment(db, doc, pass_row, "region", y=0.5)
    line = _segment(db, doc, pass_row, "line", parent=region_one.id, y=0.1)
    other = _segment(db, doc, pass_row, "line", parent=region_one.id, y=0.2)
    return doc, pass_row, region_one, region_two, line, other


def _reparent(db, rows, parent_id):
    return registry.invoke(
        db, "segment.reparent",
        {"segments": [{"segment_id": r.id, "expected_version": r.version} for r in rows],
         "parent_segment_id": parent_id},
        _person(),
    )


def test_a_line_moves_into_another_region_and_one_undo_puts_it_back(db, client):
    _, _, region_one, region_two, line, other = _page(db)

    _reparent(db, [line, other], region_two.id)

    assert db.get(Segment, line.id).parent_segment_id == region_two.id
    assert db.get(Segment, other.id).parent_segment_id == region_two.id
    audits = [a for a in db.all(ActionAudit) if a.action_name == "segment.reparent"]
    assert len(audits) == 1, "two lines, one audit row"
    assert client.post(f"/api/actions/audit/{audits[-1].id}/undo").status_code == 200
    assert db.get(Segment, line.id).parent_segment_id == region_one.id
    assert db.get(Segment, other.id).parent_segment_id == region_one.id, "one undo step restores both"


def test_the_route_moves_a_line_and_answers_the_audit_id(db, client):
    _, _, _, region_two, line, _ = _page(db)
    response = client.post(
        "/api/segments/reparent",
        json={"segments": [{"segment_id": line.id, "expected_version": line.version}],
              "parent_segment_id": region_two.id},
    )
    assert response.status_code == 200, response.text
    assert response.json()["audit_id"]
    assert db.get(Segment, line.id).parent_segment_id == region_two.id


def test_no_parent_lifts_a_line_out_to_the_page(db):
    _, _, _, _, line, _ = _page(db)
    _reparent(db, [line], None)
    assert db.get(Segment, line.id).parent_segment_id is None


def test_a_region_cannot_move_into_a_line_it_holds(db):
    _, _, region_one, _, line, _ = _page(db)
    with pytest.raises(HTTPException) as refused:
        _reparent(db, [region_one], line.id)
    assert refused.value.status_code == 422
    assert db.get(Segment, region_one.id).parent_segment_id is None


def test_a_segment_cannot_move_into_itself(db):
    _, _, _, _, line, _ = _page(db)
    with pytest.raises(HTTPException):
        _reparent(db, [line], line.id)


def test_a_parent_from_another_pass_is_refused_and_nothing_moves(db):
    doc, _, region_one, _, line, other = _page(db)
    second = SegmentPass(document_id=doc.id, name="another", provenance_kind=ProvenanceKind.human)
    db.save(second)
    elsewhere = _segment(db, doc, second, "region", y=0.7)
    with pytest.raises(Exception):
        _reparent(db, [line, other], elsewhere.id)
    assert db.get(Segment, line.id).parent_segment_id == region_one.id, "all or nothing"


def test_a_stale_line_refuses_the_whole_move(db):
    _, _, region_one, region_two, line, other = _page(db)
    stale = line.model_copy(update={"version": line.version - 1})
    with pytest.raises(Exception):
        _reparent(db, [stale, other], region_two.id)
    assert db.get(Segment, other.id).parent_segment_id == region_one.id
