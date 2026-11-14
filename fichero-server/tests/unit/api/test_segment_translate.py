"""Group move: every selected segment moves by the same offset, outline, shapes and baseline with its box.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.group-drag` (dragging one of several
selected segments moves all of them by the same offset, one action, one undo; polygons and baselines move with the
box) and `segment-editor.nudge` (the arrow keys move the whole selection, the same call).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import registry
from fichero_server.models.segments import Segment
from tests.unit.api.test_document_derived_text import _person
from tests.unit.api.test_regenerate_outline import _page

pytestmark = pytest.mark.source_model


def _line(client, doc, pass_id, y):
    response = client.post("/api/segments", json={
        "document_id": doc.id, "pass_id": pass_id, "kind": "line",
        "anchor": {"document_id": doc.id, "polygon": [[0.1, y], [0.6, y], [0.6, y + 0.05], [0.1, y + 0.05]]},
        "baseline": [[0.1, y + 0.04], [0.6, y + 0.04]],
    })
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _translate(db, ids, dx, dy):
    return registry.invoke(
        db, "segment.translate",
        {"segments": [{"segment_id": sid, "expected_version": db.get(Segment, sid).version} for sid in ids],
         "dx": dx, "dy": dy},
        _person(),
    )


def test_every_selected_segment_moves_by_the_same_offset_with_its_outline_and_baseline(db, client):
    doc, pass_id = _page(db, client, [])
    a, b = _line(client, doc, pass_id, 0.2), _line(client, doc, pass_id, 0.3)

    _translate(db, [a, b], 0.05, 0.1)

    for sid, y in ((a, 0.2), (b, 0.3)):
        row = db.get(Segment, sid)
        assert row.anchor.polygon[0] == pytest.approx([0.15, y + 0.1])
        assert row.baseline[1] == pytest.approx([0.65, y + 0.14])
        assert (row.bbox_x, row.bbox_y) == pytest.approx((0.15, y + 0.1)), "the box the page is searched by moves too"


def test_one_undo_puts_the_whole_group_back(db, client):
    doc, pass_id = _page(db, client, [])
    a, b = _line(client, doc, pass_id, 0.2), _line(client, doc, pass_id, 0.3)
    before = {sid: (db.get(Segment, sid).anchor.polygon, db.get(Segment, sid).baseline) for sid in (a, b)}

    done = _translate(db, [a, b], 0.05, 0.1)
    response = client.post(f"/api/actions/audit/{done.audit_id}/undo")
    assert response.status_code == 200, response.text

    assert {sid: (db.get(Segment, sid).anchor.polygon, db.get(Segment, sid).baseline) for sid in (a, b)} == before


def test_the_offset_is_held_at_the_page_edge_for_the_whole_group(db, client):
    doc, pass_id = _page(db, client, [])
    a, b = _line(client, doc, pass_id, 0.2), _line(client, doc, pass_id, 0.3)

    _translate(db, [a, b], 0.0, 0.9)

    lowest = max(y for sid in (a, b) for _, y in db.get(Segment, sid).anchor.polygon)
    assert lowest == pytest.approx(1.0)
    gap = db.get(Segment, b).anchor.polygon[0][1] - db.get(Segment, a).anchor.polygon[0][1]
    assert gap == pytest.approx(0.1), "the group keeps its shape: one offset for all"


def test_a_stale_segment_refuses_the_whole_move(db, client):
    doc, pass_id = _page(db, client, [])
    a, b = _line(client, doc, pass_id, 0.2), _line(client, doc, pass_id, 0.3)
    with pytest.raises(HTTPException):
        registry.invoke(db, "segment.translate", {
            "segments": [{"segment_id": a, "expected_version": 99}, {"segment_id": b, "expected_version": 1}],
            "dx": 0.1, "dy": 0.0}, _person())
    assert db.get(Segment, b).anchor.polygon[0] == pytest.approx([0.1, 0.3])
