"""Add Baseline: a line with no baseline is given one to drag onto the ink.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.edge.no-baseline` (Add Baseline proposes
one through the box's middle in its direction, marked estimated, for the person to drag onto the ink). Through the
real action and the real undo route.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document, FileType, Segment, Status

pytestmark = pytest.mark.source_model


def _person() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _page(db, client):
    doc = Document(name="folio.jpg", doc_type=DocType.file, file_type=FileType.image, path="/path/folio.jpg",
                   status=Status.completed)
    db.save(doc)
    return doc, client.post("/api/segments/passes", json={"document_id": doc.id, "name": "lines"}).json()["id"]


def _box_line(client, doc, pass_id, rect, baseline=None):
    body = {"document_id": doc.id, "pass_id": pass_id, "kind": "line", "anchor": {"document_id": doc.id, "rect": rect}}
    if baseline:
        body["baseline"] = baseline
    return client.post("/api/segments", json=body).json()["id"]


def _add(db, ids):
    return registry.invoke(db, "segment.add_baseline", {
        "segment_ids": ids, "expected_versions": {sid: db.get(Segment, sid).version for sid in ids}}, _person())


def test_a_box_line_gets_a_baseline_where_its_letters_stand_marked_estimated(db, client):
    doc, pass_id = _page(db, client)
    line = _box_line(client, doc, pass_id, [0.1, 0.2, 0.8, 0.04])

    _add(db, [line])

    row = db.get(Segment, line)
    assert [v for point in row.baseline for v in point] == pytest.approx([0.1, 0.23, 0.9, 0.23])
    assert row.metadata["baseline"] == "estimated"


def test_a_right_to_left_line_runs_from_the_right_and_a_line_that_has_one_is_left(db, client):
    doc, pass_id = _page(db, client)
    hebrew = _box_line(client, doc, pass_id, [0.1, 0.2, 0.8, 0.04])
    registry.invoke(db, "representation.create", {
        "document_id": doc.id, "segment_id": hebrew, "kind": "transcription", "content": "אבגד"}, _person())
    drawn = _box_line(client, doc, pass_id, [0.1, 0.3, 0.8, 0.04], baseline=[[0.1, 0.33], [0.9, 0.335]])

    result = _add(db, [hebrew, drawn])

    assert result.result["segment_ids"] == [hebrew]
    assert db.get(Segment, hebrew).baseline[0][0] == pytest.approx(0.9)
    assert db.get(Segment, drawn).baseline == [[0.1, 0.33], [0.9, 0.335]]


def test_one_undo_takes_the_proposed_baselines_away(db, client):
    doc, pass_id = _page(db, client)
    first = _box_line(client, doc, pass_id, [0.1, 0.2, 0.8, 0.04])
    second = _box_line(client, doc, pass_id, [0.1, 0.3, 0.8, 0.04])

    result = _add(db, [first, second])
    response = client.post(f"/api/actions/audit/{result.audit_id}/undo")
    assert response.status_code == 200, response.text

    assert db.get(Segment, first).baseline is None and db.get(Segment, second).baseline is None


def test_lines_that_all_have_baselines_are_refused(db, client):
    doc, pass_id = _page(db, client)
    drawn = _box_line(client, doc, pass_id, [0.1, 0.3, 0.8, 0.04], baseline=[[0.1, 0.33], [0.9, 0.33]])

    with pytest.raises(HTTPException) as refused:
        _add(db, [drawn])
    assert refused.value.status_code == 422
