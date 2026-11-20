"""Group move edges: shapes move too, a segment named twice or already deleted refuses the whole move, the answer says the offset used.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.group-drag` (all or nothing, one offset for
every segment, rect, outline, shapes and baseline together).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import registry
from fichero_server.models.segments import Segment
from tests.unit.api.test_document_derived_text import _person
from tests.unit.api.test_regenerate_outline import _page
from tests.unit.api.test_segment_translate import _line, _translate

pytestmark = pytest.mark.source_model


def _line_with_a_mark(client, doc, pass_id, y):
    response = client.post("/api/segments", json={
        "document_id": doc.id, "pass_id": pass_id, "kind": "line",
        "anchor": {"document_id": doc.id,
                   "polygon": [[0.1, y], [0.6, y], [0.6, y + 0.05], [0.1, y + 0.05]],
                   "shapes": [{"kind": "path", "points": [[0.2, y], [0.3, y + 0.02]]}]},
    })
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_the_shapes_of_a_segment_move_with_its_outline(db, client):
    doc, pass_id = _page(db, client, [])
    sid = _line_with_a_mark(client, doc, pass_id, 0.2)

    _translate(db, [sid], 0.1, 0.1)

    row = db.get(Segment, sid)
    assert [c for p in row.anchor.shapes[0].points for c in p] == pytest.approx([0.3, 0.3, 0.4, 0.32])
    assert row.anchor.polygon[0] == pytest.approx([0.2, 0.3])


def test_the_answer_names_the_offset_used_after_it_was_held_at_the_page_edge(db, client):
    doc, pass_id = _page(db, client, [])
    sid = _line(client, doc, pass_id, 0.2)

    done = _translate(db, [sid], 0.0, 0.9)

    assert done.result["dy"] == pytest.approx(1.0 - 0.25)
    assert done.result["dx"] == pytest.approx(0.0)


def test_a_segment_named_twice_refuses_the_whole_move(db, client):
    doc, pass_id = _page(db, client, [])
    a, b = _line(client, doc, pass_id, 0.2), _line(client, doc, pass_id, 0.3)
    version = db.get(Segment, a).version

    with pytest.raises(HTTPException) as refused:
        registry.invoke(db, "segment.translate", {
            "segments": [{"segment_id": b, "expected_version": db.get(Segment, b).version},
                         {"segment_id": a, "expected_version": version},
                         {"segment_id": a, "expected_version": version}],
            "dx": 0.1, "dy": 0.0}, _person())

    assert refused.value.status_code == 422
    assert db.get(Segment, b).anchor.polygon[0] == pytest.approx([0.1, 0.3])


def test_a_deleted_segment_refuses_the_whole_move_and_moves_nothing(db, client):
    doc, pass_id = _page(db, client, [])
    a, b = _line(client, doc, pass_id, 0.2), _line(client, doc, pass_id, 0.3)
    versions = {sid: db.get(Segment, sid).version for sid in (a, b)}
    registry.invoke(db, "segment.delete", {"segment_ids": [b], "expected_versions": {b: versions[b]}}, _person())

    with pytest.raises(HTTPException):
        registry.invoke(db, "segment.translate", {
            "segments": [{"segment_id": a, "expected_version": versions[a]},
                         {"segment_id": b, "expected_version": db.get(Segment, b).version}],
            "dx": 0.1, "dy": 0.0}, _person())

    assert db.get(Segment, a).anchor.polygon[0] == pytest.approx([0.1, 0.2])
