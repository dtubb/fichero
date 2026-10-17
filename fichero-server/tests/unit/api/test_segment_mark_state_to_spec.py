"""source.segment.mark-with-state / source.segment.marks-have-state (docs/contributor_manual/specs/source/segments-and-geometry.md, #4928).

Spec (ruled 2026-10-17): a segment carries one mark, `mark_state`, one of ticked|crossed|struck|none (default none), set only
through `segment.update`, additive, and undone like any edit; a value outside the four is refused.
"""
from __future__ import annotations

import pytest

from fichero_server.actions.registry import registry
from fichero_server.api.routes.document.segment_conversion import live_rows_in_order
from fichero_server.models import ActionAudit
from fichero_server.models.segments import Segment, converted_pass_id
from tests.unit.api.test_document_derived_text import _artifact, _convert, _make_doc, _person


def _first(db, client):
    doc = _make_doc(db)
    artifact = _artifact(db, doc)
    _convert(client, artifact.id)
    return live_rows_in_order(db, converted_pass_id(artifact.id))[0]


def test_source_segment_mark_with_state__a_segment_starts_unmarked_takes_one_mark_and_undo_clears_it(db, client):
    seg = _first(db, client)
    assert db.get(Segment, seg.id).mark_state == "none", "additive: an unmarked segment reads as before"

    registry.invoke(db, "segment.update", {"segment_id": seg.id, "expected_version": seg.version, "mark_state": "ticked"}, _person())
    assert db.get(Segment, seg.id).mark_state == "ticked"
    now = db.get(Segment, seg.id)
    registry.invoke(db, "segment.update", {"segment_id": seg.id, "expected_version": now.version, "mark_state": "struck"}, _person())
    assert db.get(Segment, seg.id).mark_state == "struck", "one mark per segment: the new state replaces the old"

    audit = [a for a in db.all(ActionAudit) if a.action_name == "segment.update"][-1]
    assert client.post(f"/api/actions/audit/{audit.id}/undo").status_code == 200
    assert db.get(Segment, seg.id).mark_state == "ticked"


def test_source_segment_marks_have_state__a_value_outside_the_four_is_refused(db, client):
    seg = _first(db, client)
    with pytest.raises(Exception):
        registry.invoke(db, "segment.update", {"segment_id": seg.id, "expected_version": seg.version, "mark_state": "circled"}, _person())
    assert db.get(Segment, seg.id).mark_state == "none"
