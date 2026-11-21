"""Redo of a delete, a group move and a simplify: it does the edit again, and is refused if someone changed a segment.

Spec: docs/contributor_manual/specs/source/segment-editor.md -- `source.editor.redo-works` (after undoing a segment
edit, Redo does it again; refused only if something else changed the segment since; undo, redo, undo ends where the
first undo ended). Through the real actions and the real undo route (redo is the undo of the undo).
"""
from __future__ import annotations

import pytest

from fichero_server.actions.registry import registry
from fichero_server.models.segments import Segment
from tests.unit.api.test_document_derived_text import _person
from tests.unit.api.test_regenerate_outline import _page
from tests.unit.api.test_segment_simplify import _dense_line, _page as _raster_page, _simplify
from tests.unit.api.test_segment_translate import _line, _translate

pytestmark = pytest.mark.source_model


def _undo(client, audit_id):
    response = client.post(f"/api/actions/audit/{audit_id}/undo")
    assert response, response.text
    return response


def _shapes(db, sid):
    row = db.get(Segment, sid)
    return row.anchor.polygon, row.baseline


def test_redo_of_a_group_move_moves_again_and_undo_after_it_ends_where_the_first_undo_did(db, client):
    doc, pass_id = _page(db, client, [])
    a, b = _line(client, doc, pass_id, 0.2), _line(client, doc, pass_id, 0.3)
    start = {sid: _shapes(db, sid) for sid in (a, b)}

    moved = _translate(db, [a, b], 0.05, 0.1)
    after_move = {sid: _shapes(db, sid) for sid in (a, b)}
    undone = _undo(client, moved.audit_id).json()
    assert {sid: _shapes(db, sid) for sid in (a, b)} == start

    redone = _undo(client, undone["audit_id"]).json()
    assert {sid: _shapes(db, sid) for sid in (a, b)} == after_move, "redo moves the group by the same offset again"

    _undo(client, redone["audit_id"])
    assert {sid: _shapes(db, sid) for sid in (a, b)} == start


def test_redo_of_a_group_move_is_refused_when_another_writer_changed_a_member_since(db, client):
    doc, pass_id = _page(db, client, [])
    a, b = _line(client, doc, pass_id, 0.2), _line(client, doc, pass_id, 0.3)
    moved = _translate(db, [a, b], 0.05, 0.1)
    undone = _undo(client, moved.audit_id).json()

    changed = client.put(f"/api/segments/{b}", json={"segment_id": b, "expected_version": db.get(Segment, b).version, "kind": "heading"})
    assert changed.status_code == 200, changed.text
    polygon_before = _shapes(db, a)

    refused = client.post(f"/api/actions/audit/{undone['audit_id']}/undo")
    assert refused.status_code == 409, refused.text
    assert _shapes(db, a) == polygon_before, "a refused redo moves nothing"


def test_redo_of_a_simplify_simplifies_again_and_undo_after_it_ends_where_the_first_undo_did(db, client):
    doc, pass_id = _raster_page(db, client)
    line = _dense_line(client, doc, pass_id)
    start = _shapes(db, line)

    done = _simplify(db, [line], 2.0)
    simplified = _shapes(db, line)
    assert len(simplified[0]) < len(start[0])
    undone = _undo(client, done.audit_id).json()
    assert _shapes(db, line) == start

    redone = _undo(client, undone["audit_id"]).json()
    assert _shapes(db, line) == simplified

    _undo(client, redone["audit_id"])
    assert _shapes(db, line) == start


def test_redo_of_a_delete_deletes_again_and_undo_after_it_brings_the_lines_back(db, client):
    doc, pass_id = _page(db, client, [])
    a, b = _line(client, doc, pass_id, 0.2), _line(client, doc, pass_id, 0.3)
    versions = {sid: db.get(Segment, sid).version for sid in (a, b)}

    gone = registry.invoke(db, "segment.delete", {"segment_ids": [a, b], "expected_versions": versions}, _person())
    undone = _undo(client, gone.audit_id).json()
    assert all(db.get(Segment, sid).deleted_at is None for sid in (a, b))

    redone = _undo(client, undone["audit_id"]).json()
    assert all(db.get(Segment, sid).deleted_at is not None for sid in (a, b)), "redo deletes both again"

    _undo(client, redone["audit_id"])
    assert all(db.get(Segment, sid).deleted_at is None for sid in (a, b))
