"""A self-crossing outline is never written.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.edge.self-intersecting` (a reshape or a
drawn shape that would cross itself is stored as the outer boundary of the area it covers, and the answer says it
was simplified). Through the real actions.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.media import line_join
from fichero_server.models import DocType, Document, FileType, Segment, Status

pytestmark = pytest.mark.source_model

#: A figure-eight: the second and fourth edges cross in the middle.
EIGHT = [[0.1, 0.1], [0.3, 0.3], [0.3, 0.1], [0.1, 0.3]]
SQUARE = [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]]


def _person() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _page(db, client):
    doc = Document(name="folio.jpg", doc_type=DocType.file, file_type=FileType.image, path="/path/folio.jpg",
                   status=Status.completed)
    db.save(doc)
    response = client.post("/api/segments/passes", json={"document_id": doc.id, "name": "lines"})
    assert response.status_code == 200, response.text
    return doc, response.json()["id"]


def _create(db, doc, pass_id, polygon):
    return registry.invoke(
        db, "segment.create",
        {"document_id": doc.id, "pass_id": pass_id, "kind": "region",
         "anchor": {"document_id": doc.id, "polygon": polygon}},
        _person(),
    )


def test_the_check_tells_a_crossing_outline_from_a_simple_one():
    assert line_join.crosses_itself(EIGHT)
    assert not line_join.crosses_itself(SQUARE)


def test_a_drawn_outline_that_crosses_itself_is_stored_simple_and_said(db, client):
    doc, pass_id = _page(db, client)

    result = _create(db, doc, pass_id, EIGHT)

    assert result.result.get("simplified") is True
    row = db.get(Segment, result.result["segment_ids"][0])
    assert not line_join.crosses_itself(row.anchor.polygon)
    assert line_join.bounds(row.anchor.polygon) == pytest.approx((0.1, 0.1, 0.3, 0.3), abs=2e-3)
    assert row.metadata.get("outline_simplified") is True


def test_a_simple_outline_is_stored_as_given(db, client):
    doc, pass_id = _page(db, client)

    result = _create(db, doc, pass_id, SQUARE)

    assert "simplified" not in result.result
    assert db.get(Segment, result.result["segment_ids"][0]).anchor.polygon == SQUARE


def test_a_reshape_that_crosses_itself_is_stored_simple_and_undo_brings_back_the_shape_before(db, client):
    doc, pass_id = _page(db, client)
    segment_id = _create(db, doc, pass_id, SQUARE).result["segment_ids"][0]
    row = db.get(Segment, segment_id)

    result = registry.invoke(
        db, "segment.update",
        {"segment_id": segment_id, "expected_version": row.version,
         "anchor": {"document_id": doc.id, "polygon": EIGHT}},
        _person(),
    )

    assert result.result.get("simplified") is True
    assert not line_join.crosses_itself(db.get(Segment, segment_id).anchor.polygon)
    response = client.post(f"/api/actions/audit/{result.audit_id}/undo")
    assert response.status_code == 200, response.text
    assert db.get(Segment, segment_id).anchor.polygon == SQUARE
