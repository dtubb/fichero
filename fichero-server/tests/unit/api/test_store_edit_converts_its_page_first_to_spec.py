"""source.store.edit-converts-its-page-first (docs/contributor_manual/specs/source/segments-and-geometry.md, #4924).

Spec: "reading a page never converts it; editing a page that is not yet converted converts it as part of that edit,
one audited action, with the same ids the whole-project conversion would give it; undo takes back the edit and keeps
the records."
The edit's mechanics are pinned in test_first_edit_conversion.py; this holds the three halves of the sentence together.
"""
from __future__ import annotations

from fichero_server.models import ActionAudit, Artifact
from fichero_server.models.segments import Segment, converted_segment_id
from tests.unit.api.test_first_edit_conversion import _artifact, _edit, _make_doc


def test_source_store_edit_converts_its_page_first(db, client):
    doc = _make_doc(db)
    artifact = _artifact(db, doc, count=3)

    assert client.get(f"/api/artifacts/{artifact.id}").status_code == 200
    assert client.get(f"/api/documents/{doc.id}").status_code == 200
    assert db.query(Segment, document_id=doc.id) == [], "reading converts nothing"
    assert db.get(Artifact, artifact.id).geometry_superseded_by_pass_id is None

    _edit(client, artifact.id, {"op": "move", "indices": [1], "bbox": [0.7, 0.7, 0.1, 0.05]})
    audits = [a for a in db.all(ActionAudit) if a.action_name.startswith(("artifact.", "segment."))]
    assert [a.action_name for a in audits] == ["segment.convert_and_edit"], "one audited action"
    ids = {s.id for s in db.query(Segment, document_id=doc.id)}
    assert ids and ids == {converted_segment_id(artifact.id, i) for i in range(3)}, "name-based, repeatable ids"

    assert client.post(f"/api/actions/audit/{audits[0].id}/undo").status_code == 200
    assert {s.id for s in db.query(Segment, document_id=doc.id)} == ids, "undo keeps the records"
