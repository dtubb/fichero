"""Make Region from Lines and Ungroup Region (`segment-editor.make-region-from-lines`, #6737).

`segment.group_lines` makes a region around the lines and moves them into it; `segment.ungroup_region` is the reverse.
Each is one audit row and the other's undo. Through the real actions and the real undo route.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import registry
from fichero_server.models import ActionAudit
from fichero_server.models.segments import Segment
from tests.unit.api.test_document_derived_text import _person
from tests.unit.api.test_segment_reparent import _page, _segment


def _group(db, rows):
    return registry.invoke(
        db, "segment.group_lines",
        {"segment_ids": [r.id for r in rows], "expected_versions": {r.id: db.get(Segment, r.id).version for r in rows}},
        _person(),
    )


def _undo(client, result):
    response = client.post(f"/api/actions/audit/{result.audit_id}/undo")
    assert response.status_code == 200, response.text


def _fresh(db, pass_row, doc):
    """Three lines on the page itself, no region around them."""
    return [_segment(db, doc, pass_row, "line", y=y) for y in (0.1, 0.2, 0.3)]


def test_three_lines_become_one_region_with_three_children_and_the_union_box(db, client):
    doc, pass_row, *_ = _page(db)
    lines = _fresh(db, pass_row, doc)

    result = _group(db, lines)

    region = db.get(Segment, result.result["region_id"])
    assert region.kind == "region" and region.parent_segment_id is None
    assert region.anchor.rect == pytest.approx([0.1, 0.1, 0.5, 0.24])
    assert [db.get(Segment, r.id).parent_segment_id for r in lines] == [region.id] * 3
    assert len([a for a in db.all(ActionAudit) if a.action_name == "segment.group_lines"]) == 1


def test_lines_inside_a_region_make_a_region_nested_in_it(db):
    _, _, region_one, _, line, other = _page(db)
    result = _group(db, [line, other])
    new = db.get(Segment, result.result["region_id"])
    assert new.parent_segment_id == region_one.id
    assert db.get(Segment, line.id).parent_segment_id == new.id


def test_lines_of_two_regions_are_refused_and_nothing_is_made(db):
    _, _, _, region_two, line, _ = _page(db)
    stray = _segment(db, db_doc(db, line), db_pass(db, line), "line", parent=region_two.id, y=0.55)
    before = len(db.all(Segment))
    with pytest.raises(HTTPException) as refused:
        _group(db, [line, stray])
    assert refused.value.status_code == 422
    assert len(db.all(Segment)) == before


def test_one_undo_takes_the_region_away_and_puts_the_lines_back(db, client):
    doc, pass_row, *_ = _page(db)
    lines = _fresh(db, pass_row, doc)
    result = _group(db, lines)
    region_id = result.result["region_id"]

    _undo(client, result)

    assert db.get(Segment, region_id).deleted_at is not None
    assert [db.get(Segment, r.id).parent_segment_id for r in lines] == [None] * 3


def test_ungroup_sends_the_lines_to_the_regions_parent_and_removes_it_and_undo_restores(db, client):
    _, _, region_one, _, line, other = _page(db)
    result = registry.invoke(
        db, "segment.ungroup_region",
        {"region_id": region_one.id, "expected_version": region_one.version}, _person(),
    )

    assert db.get(Segment, region_one.id).deleted_at is not None
    assert db.get(Segment, line.id).parent_segment_id is None
    assert db.get(Segment, other.id).parent_segment_id is None

    _undo(client, result)

    assert db.get(Segment, region_one.id).deleted_at is None
    assert db.get(Segment, line.id).parent_segment_id == region_one.id
    assert db.get(Segment, other.id).parent_segment_id == region_one.id


def db_doc(db, row):
    from fichero_server.models import Document

    return db.get(Document, row.document_id)


def db_pass(db, row):
    from fichero_server.models.segments import SegmentPass

    return db.get(SegmentPass, row.pass_id)


def test_the_lines_keep_their_reading_order_in_the_new_region_and_undo_and_ungroup_restore_it(db, client):
    from fichero_server.api.routes.document.reading_orders import AS_WRITTEN, entries_in_sequence
    from tests.unit.api.test_segment_reassign_by_drag import _children

    doc, pass_row, region_one, _, line, other = _page(db)
    stray = _segment(db, doc, pass_row, "line", parent=region_one.id, y=0.55)
    order_id = registry.invoke(
        db, "reading_order.create",
        {"document_id": doc.id, "pass_id": pass_row.id, "name": AS_WRITTEN, "seed_from_pass": True}, _person(),
    ).result["order_id"]
    before = _children(db, order_id, region_one.id)
    assert before == [line.id, other.id, stray.id]

    result = _group(db, [line, other, stray])
    new_id = result.result["region_id"]
    assert _children(db, order_id, new_id) == [line.id, other.id, stray.id], "order kept inside the new region"
    assert _children(db, order_id, region_one.id) == [new_id]

    _undo(client, result)
    assert _children(db, order_id, region_one.id) == before

    again = registry.invoke(
        db, "segment.ungroup_region",
        {"region_id": region_one.id, "expected_version": db.get(Segment, region_one.id).version}, _person(),
    )
    assert again.audit_id
    top = [row.segment_id for row in entries_in_sequence(db, order_id)]
    assert top.index(line.id) < top.index(other.id) < top.index(stray.id), "the lines stay in order on the page"
