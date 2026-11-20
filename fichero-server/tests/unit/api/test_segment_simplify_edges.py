"""Simplify edges: the floors on points, several segments in one action, a stale or deleted segment.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.vertices` (never below three outline
points and two baseline points; one action, one undo; every edit is refused when the row changed since it was read).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import registry
from fichero_server.models import Segment
from tests.unit.api.test_segment_simplify import _dense_line, _page, _person, _simplify

pytestmark = pytest.mark.source_model


def test_a_huge_tolerance_keeps_three_outline_points_and_two_baseline_points(db, client):
    doc, pass_id = _page(db, client)
    line = _dense_line(client, doc, pass_id)

    _simplify(db, [line], 20.0)

    after = db.get(Segment, line)
    assert len(after.anchor.polygon) >= 3
    assert len(after.baseline) >= 2


def test_two_segments_simplify_as_one_action_and_one_undo_restores_both(db, client):
    doc, pass_id = _page(db, client)
    a, b = _dense_line(client, doc, pass_id), _dense_line(client, doc, pass_id)
    before = {sid: (db.get(Segment, sid).anchor.polygon, db.get(Segment, sid).baseline) for sid in (a, b)}

    result = _simplify(db, [a, b], 2.0)

    for sid in (a, b):
        assert len(db.get(Segment, sid).anchor.polygon) < len(before[sid][0])
    response = client.post(f"/api/actions/audit/{result.audit_id}/undo")
    assert response.status_code == 200, response.text
    for sid in (a, b):
        assert (db.get(Segment, sid).anchor.polygon, db.get(Segment, sid).baseline) == before[sid]


def test_a_stale_version_refuses_the_whole_simplify_and_changes_nothing(db, client):
    doc, pass_id = _page(db, client)
    a, b = _dense_line(client, doc, pass_id), _dense_line(client, doc, pass_id)
    versions = {sid: db.get(Segment, sid).version for sid in (a, b)}
    points = {sid: len(db.get(Segment, sid).anchor.polygon) for sid in (a, b)}

    with pytest.raises(HTTPException) as refused:
        registry.invoke(db, "segment.simplify", {
            "segment_ids": [a, b],
            "expected_versions": {a: versions[a], b: versions[b] - 1}, "tolerance": 2.0}, _person())

    assert refused.value.status_code in (409, 422)
    for sid in (a, b):
        assert len(db.get(Segment, sid).anchor.polygon) == points[sid]
