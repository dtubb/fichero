"""A word broken at a line's end: Cut Words names the two pieces, and a merge keeps both their shapes.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.edge.word-across-lines` (a word broken at a
line end is one segment with two shapes; Cut Words on both lines makes the two pieces and offers to join them when the
first line's reading ends with a hyphen and the second's starts without a space; the join is `segment.merge` keeping
both shapes).
"""
from __future__ import annotations

import pytest

from fichero_server.actions.registry import registry
from fichero_server.models import Segment
from tests.unit.api.test_segment_cut_words import _page, _person, _read, _words

pytestmark = pytest.mark.source_model


def _line_at(client, doc, pass_id, y):
    response = client.post("/api/segments", json={
        "document_id": doc.id, "pass_id": pass_id, "kind": "line",
        "anchor": {"document_id": doc.id, "polygon": [[0.1, y], [0.9, y], [0.9, y + 0.1], [0.1, y + 0.1]]},
        "baseline": [[0.1, y + 0.08], [0.9, y + 0.08]],
    })
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _two_lines(db, client, first="en el nom-", second="bre dice"):
    doc, pass_id = _page(db, client)
    top, bottom = _line_at(client, doc, pass_id, 0.2), _line_at(client, doc, pass_id, 0.4)
    _read(db, top, first, [i / len(first) for i in range(len(first))])
    _read(db, bottom, second, [i / len(second) for i in range(len(second))])
    cut = registry.invoke(db, "segment.cut_words", {
        "segment_ids": [top, bottom],
        "expected_versions": {sid: db.get(Segment, sid).version for sid in (top, bottom)}}, _person())
    return top, bottom, cut


def test_cut_words_names_the_two_pieces_of_a_hyphenated_word(db, client):
    top, bottom, cut = _two_lines(db, client)
    assert cut.result["joinable"] == [[_words(db, top)[-1].id, _words(db, bottom)[0].id]]


def test_no_hyphen_no_offer(db, client):
    _top, _bottom, cut = _two_lines(db, client, first="en el nombre", second="dice que")
    assert cut.result["joinable"] == []


def test_the_join_keeps_both_shapes_and_one_undo_parts_them(db, client):
    top, bottom, cut = _two_lines(db, client)
    first, second = cut.result["joinable"][0]
    shapes_before = [db.get(Segment, sid).anchor.polygon for sid in (first, second)]

    merged = registry.invoke(db, "segment.merge", {
        "segment_ids": [first, second], "keep_id": first, "keep_shapes": True, "move_into_region": True,
        "expected_versions": {sid: db.get(Segment, sid).version for sid in (first, second)}}, _person())

    word = db.get(Segment, first)
    assert [shape.points for shape in word.anchor.shapes] == shapes_before, "one word, both pieces' shapes"
    assert db.get(Segment, second).deleted_at is not None

    undone = client.post(f"/api/actions/audit/{merged.audit_id}/undo")
    assert undone.status_code == 200, undone.text
    assert db.get(Segment, second).deleted_at is None
    assert db.get(Segment, second).parent_segment_id == bottom
    assert db.get(Segment, first).anchor.polygon == shapes_before[0]
