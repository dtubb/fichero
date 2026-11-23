"""Redo of a Marker segment, a Line Brush line, Convert to Box and Convert Level: it does the edit again, and undo after
it ends where the first undo did.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.every-edit-lands-at-once` (⌘Z and ⇧⌘Z are
the window's undo stack over audit ids, for every tool here). Through the real actions and the real undo route (redo is
the undo of the undo), as `test_segment_redo_of_delete_translate_simplify.py` does for delete, move and simplify.
"""
from __future__ import annotations

import pytest

from fichero_server.actions.registry import registry
from fichero_server.models.segments import Segment
from tests.unit.api.test_document_derived_text import _person
from tests.unit.api.test_regenerate_outline import H, W, _page
from tests.unit.api.test_segment_create_from_stroke import _wobbly

pytestmark = pytest.mark.source_model

SLANT = [[0.1, 0.2], [0.5, 0.25], [0.45, 0.4], [0.12, 0.3]]


def _undo(client, audit_id) -> str:
    response = client.post(f"/api/actions/audit/{audit_id}/undo")
    assert response.status_code == 200, response.text
    return response.json()["audit_id"]


def _shape(db, sid):
    row = db.get(Segment, sid)
    return row.deleted_at is None, row.kind, row.anchor.polygon, row.anchor.rect, row.baseline


def _undo_redo_undo(db, client, audit_id, sid, *, start, done):
    undone = _undo(client, audit_id)
    assert _shape(db, sid) == start
    redone = _undo(client, undone)
    assert _shape(db, sid) == done, "redo makes the same edit again"
    _undo(client, redone)
    assert _shape(db, sid) == start


def _create(db, doc, pass_id, **body):
    return registry.invoke(db, "segment.create", {"document_id": doc.id, "pass_id": pass_id, **body}, _person())


def _segment(db, doc, pass_id, kind, polygon):
    made = _create(db, doc, pass_id, kind=kind, anchor={"document_id": doc.id, "polygon": polygon})
    return made.result["segment_ids"][0]


def test_redo_of_a_marker_segment_brings_back_the_same_simplified_outline(db, client):
    doc, pass_id = _page(db, client, [])
    loop = _wobbly([(100, 100), (500, 100), (500, 300), (100, 300), (100, 100)])
    made = _create(db, doc, pass_id, kind="region", smoothing=0.5, anchor={"document_id": doc.id, "polygon": loop})
    sid = made.result["segment_ids"][0]
    done = _shape(db, sid)

    undone = _undo(client, made.audit_id)
    assert not _shape(db, sid)[0]
    redone = _undo(client, undone)
    assert _shape(db, sid) == done, "the redone segment has the outline the stroke made, not the raw stroke"
    _undo(client, redone)
    assert not _shape(db, sid)[0]


def test_redo_of_a_line_brush_line_brings_back_its_painted_outline_and_baseline(db, client):
    doc, pass_id = _page(db, client, [])
    stroke = [[(100 + i) / W, 200 / H, 30] for i in range(0, 600, 2)]
    made = _create(db, doc, pass_id, kind="line", brush_stroke=stroke,
                   anchor={"document_id": doc.id, "shapes": [{"kind": "path", "points": [p[:2] for p in stroke]}]})
    sid = made.result["segment_ids"][0]
    done = _shape(db, sid)

    undone = _undo(client, made.audit_id)
    assert not _shape(db, sid)[0]
    redone = _undo(client, undone)
    assert _shape(db, sid) == done
    _undo(client, redone)
    assert not _shape(db, sid)[0]


def test_redo_of_convert_to_box_makes_the_box_again(db, client):
    doc, pass_id = _page(db, client, [])
    sid = _segment(db, doc, pass_id, "line", SLANT)
    start = _shape(db, sid)

    converted = registry.invoke(db, "segment.convert_to_box", {
        "segment_ids": [sid], "expected_versions": {sid: db.get(Segment, sid).version}}, _person())
    done = _shape(db, sid)
    assert done != start

    _undo_redo_undo(db, client, converted.audit_id, sid, start=start, done=done)


def test_redo_of_convert_level_makes_the_region_a_line_again(db, client):
    doc, pass_id = _page(db, client, [])
    sid = _segment(db, doc, pass_id, "region", SLANT)
    start = _shape(db, sid)

    converted = registry.invoke(db, "segment.convert_level", {
        "segment_ids": [sid], "to_kind": "line", "expected_versions": {sid: db.get(Segment, sid).version}}, _person())
    done = _shape(db, sid)
    assert done[1] == "line" and done[4]

    _undo_redo_undo(db, client, converted.audit_id, sid, start=start, done=done)


def _tree(db, ids):
    """Each segment's (live, parent) by id, the hierarchy Make Region and Ungroup change."""
    return [(db.get(Segment, i).deleted_at is None, db.get(Segment, i).parent_segment_id) for i in ids]


def test_redo_of_make_region_from_lines_puts_the_lines_back_in_the_same_region(db, client):
    from tests.unit.api.test_segment_reparent import _page as _regions_page
    from tests.unit.api.test_segment_reparent import _segment as _reparent_segment

    doc, pass_row, *_ = _regions_page(db)
    lines = [_reparent_segment(db, doc, pass_row, "line", y=y).id for y in (0.1, 0.2)]
    made = registry.invoke(db, "segment.group_lines", {
        "segment_ids": lines, "expected_versions": {i: db.get(Segment, i).version for i in lines}}, _person())
    ids = [made.result["region_id"], *lines]
    done = _tree(db, ids)

    undone = _undo(client, made.audit_id)
    assert _tree(db, ids) == [(False, None), (True, None), (True, None)]
    redone = _undo(client, undone)
    assert _tree(db, ids) == done, "redo groups the lines into the same region again"
    _undo(client, redone)
    assert _tree(db, ids) == [(False, None), (True, None), (True, None)]


def test_redo_of_ungroup_region_takes_the_region_away_again(db, client):
    from tests.unit.api.test_segment_reparent import _page as _regions_page

    _, _, region, _, line, other = _regions_page(db)
    ids = [region.id, line.id, other.id]
    start = _tree(db, ids)
    ungrouped = registry.invoke(db, "segment.ungroup_region",
                                {"region_id": region.id, "expected_version": region.version}, _person())
    done = _tree(db, ids)
    assert done == [(False, region.parent_segment_id), (True, None), (True, None)]

    undone = _undo(client, ungrouped.audit_id)
    assert _tree(db, ids) == start
    redone = _undo(client, undone)
    assert _tree(db, ids) == done
    _undo(client, redone)
    assert _tree(db, ids) == start
