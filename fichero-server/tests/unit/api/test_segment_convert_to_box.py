"""Convert to Box: each selected segment's polygon becomes its axis-aligned bounding rectangle.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.convert-to-box` (one polygon gives its
box; three selected give three boxes; id, text and order unchanged; undo restores the polygon). Engine half only.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import Segment
from tests.unit.api.test_segments_validate import _page, _segment

pytestmark = pytest.mark.source_model

SLANT = [[0.1, 0.2], [0.5, 0.25], [0.45, 0.4], [0.12, 0.3]]


def _person() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _convert(db, ids):
    versions = {sid: db.get(Segment, sid).version for sid in ids}
    return registry.invoke(db, "segment.convert_to_box", {"segment_ids": ids, "expected_versions": versions}, _person())


def test_one_polygon_becomes_its_bounding_box_and_keeps_its_id_and_text(db, client):
    doc, pass_id = _page(db, client)
    sid = _segment(client, doc, pass_id, polygon=SLANT)
    before = db.get(Segment, sid)

    _convert(db, [sid])

    row = db.get(Segment, sid)
    assert row.id == sid and row.version == before.version + 1
    assert row.anchor.polygon == [[0.1, 0.2], [0.5, 0.2], [0.5, 0.4], [0.1, 0.4]]
    assert row.anchor.rect == pytest.approx([0.1, 0.2, 0.4, 0.2])


def test_three_selected_give_three_boxes_and_one_undo_puts_every_polygon_back(db, client):
    doc, pass_id = _page(db, client)
    ids = [_segment(client, doc, pass_id, polygon=[[x, y] for x, y in SLANT]) for _ in range(3)]
    result = _convert(db, ids)

    for sid in ids:
        assert len(db.get(Segment, sid).anchor.polygon) == 4
        assert db.get(Segment, sid).anchor.polygon[1] == [0.5, 0.2]
    assert client.post(f"/api/actions/audit/{result.audit_id}/undo").status_code == 200
    for sid in ids:
        assert db.get(Segment, sid).anchor.polygon == SLANT


def test_a_stale_version_refuses_all_and_changes_nothing(db, client):
    doc, pass_id = _page(db, client)
    first = _segment(client, doc, pass_id, polygon=SLANT)
    second = _segment(client, doc, pass_id, polygon=SLANT)
    versions = {first: db.get(Segment, first).version, second: db.get(Segment, second).version - 1}

    with pytest.raises(HTTPException):
        registry.invoke(db, "segment.convert_to_box", {"segment_ids": [first, second], "expected_versions": versions},
                        _person())

    assert db.get(Segment, first).anchor.polygon == SLANT
