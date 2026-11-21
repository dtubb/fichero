"""Convert level: a region becomes a line and a line a region, keeping shape, reading and order.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.convert-level` (each direction keeps shape,
text and order; a region with children is refused and says why; undo restores). Engine half only.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import Segment
from tests.unit.api.test_segment_convert_to_box import _kept, _read
from tests.unit.api.test_segments_validate import _box, _page, _segment

pytestmark = pytest.mark.source_model


def _person() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _convert(db, ids, kind):
    versions = {sid: db.get(Segment, sid).version for sid in ids}
    return registry.invoke(
        db, "segment.convert_level", {"segment_ids": ids, "to_kind": kind, "expected_versions": versions}, _person())


def test_a_region_becomes_a_line_with_a_baseline_in_its_lower_third_and_keeps_shape_text_and_order(db, client):
    doc, pass_id = _page(db, client)
    sid = _segment(client, doc, pass_id, kind="region", polygon=_box(0.1, 0.2, 0.6, 0.3))
    _read(db, doc, sid, "caput")
    kept, shape = _kept(db, sid), db.get(Segment, sid).anchor.polygon

    _convert(db, [sid], "line")

    row = db.get(Segment, sid)
    assert (row.kind, row.doc_kind) == ("line", f"{doc.id}:line")
    assert row.anchor.polygon == shape and _kept(db, sid) == kept
    assert row.baseline == [[0.1, pytest.approx(0.4)], [pytest.approx(0.7), pytest.approx(0.4)]]


def test_a_line_becomes_a_region_and_one_undo_puts_it_back(db, client):
    doc, pass_id = _page(db, client)
    sid = _segment(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.6, 0.05), baseline=[[0.1, 0.24], [0.7, 0.24]])
    _read(db, doc, sid, "in nomine")
    kept = _kept(db, sid)

    done = _convert(db, [sid], "region")

    assert db.get(Segment, sid).kind == "region" and _kept(db, sid) == kept
    assert client.post(f"/api/actions/audit/{done.audit_id}/undo").status_code == 200
    row = db.get(Segment, sid)
    assert (row.kind, row.doc_kind) == ("line", f"{doc.id}:line") and row.baseline == [[0.1, 0.24], [0.7, 0.24]]
    assert _kept(db, sid) == kept


def test_a_region_with_child_lines_is_refused_with_the_reason_and_nothing_changes(db, client):
    doc, pass_id = _page(db, client)
    region = _segment(client, doc, pass_id, kind="region", polygon=_box(0.05, 0.1, 0.9, 0.5))
    other = _segment(client, doc, pass_id, kind="region", polygon=_box(0.05, 0.7, 0.9, 0.2))
    _segment(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.8, 0.05), parent=region)

    with pytest.raises(HTTPException) as refused:
        _convert(db, [other, region], "line")

    assert refused.value.status_code == 422 and "lines" in refused.value.detail
    assert db.get(Segment, other).kind == "region" and db.get(Segment, region).kind == "region"


def test_a_segment_already_at_that_level_is_refused(db, client):
    doc, pass_id = _page(db, client)
    sid = _segment(client, doc, pass_id, kind="region", polygon=_box(0.1, 0.2, 0.6, 0.3))
    with pytest.raises(HTTPException) as refused:
        _convert(db, [sid], "region")
    assert refused.value.status_code == 422
