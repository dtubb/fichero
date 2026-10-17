"""source.segment.furniture (docs/contributor_manual/specs/source/segments-and-geometry.md, #4927).

Spec: "page furniture is marked, and a reading can leave it out."
Marked through the real `segment.update` action (is_furniture), left out of the page's text by default and asked for
back, and the mark is undone like any edit.
"""
from __future__ import annotations

from fichero_server.actions.registry import registry
from fichero_server.api.routes.document.segment_conversion import live_rows_in_order
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.models import ActionAudit
from fichero_server.models.segments import Segment, converted_pass_id
from tests.unit.api.test_document_derived_text import LINES, PAGE_TEXT, _artifact, _convert, _make_doc, _person


def test_source_segment_furniture__a_marked_running_head_is_left_out_of_a_reading_and_can_be_unmarked(db, client):
    doc = _make_doc(db)
    artifact = _artifact(db, doc)
    _convert(client, artifact.id)
    head = live_rows_in_order(db, converted_pass_id(artifact.id))[0]

    registry.invoke(db, "segment.update",
                           {"segment_id": head.id, "expected_version": head.version, "is_furniture": True}, _person())
    assert db.get(Segment, head.id).is_furniture is True, "the segment is marked"
    assert document_text(db, doc.id).text == " ".join(LINES[1:]), "a reading leaves it out"
    assert document_text(db, doc.id, include_furniture=True).text == PAGE_TEXT, "and can ask for it back"

    audit = [a for a in db.all(ActionAudit) if a.action_name == "segment.update"][-1]
    assert client.post(f"/api/actions/audit/{audit.id}/undo").status_code == 200
    assert db.get(Segment, head.id).is_furniture is False
    assert document_text(db, doc.id).text == PAGE_TEXT
