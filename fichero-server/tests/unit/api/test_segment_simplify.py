"""Simplify: fewer points on an outline and a baseline, within a tolerance in image pixels.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.vertices` (Simplify asks the engine for
a simpler outline, `segment.simplify` with a tolerance in image pixels, Douglas-Peucker on the outline and the
baseline; one action, one undo). Through the real action and the real undo route.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document, FileType, Segment, Status

pytestmark = pytest.mark.source_model

W, H = 1000, 500


def _person() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _page(db, client):
    from PIL import Image

    path = Path(db.path.parent) / "folio.png"
    Image.new("L", (W, H), 255).save(path)
    doc = Document(name="folio.png", doc_type=DocType.file, file_type=FileType.image, path=str(path),
                   status=Status.completed)
    db.save(doc)
    response = client.post("/api/segments/passes", json={"document_id": doc.id, "name": "lines"})
    assert response.status_code == 200, response.text
    return doc, response.json()["id"]


def _dense_line(client, doc, pass_id):
    """A box traced with a point every pixel along its long sides, wobbling half a pixel, and a baseline the same."""
    top = [[(100 + i) / W, (100 + 0.5 * (i % 2)) / H] for i in range(0, 600, 3)]
    bottom = [[(700 - i) / W, (140 + 0.5 * (i % 2)) / H] for i in range(0, 600, 3)]
    baseline = [[(100 + i) / W, (132 + 0.5 * (i % 2)) / H] for i in range(0, 600, 3)]
    response = client.post("/api/segments", json={
        "document_id": doc.id, "pass_id": pass_id, "kind": "line",
        "anchor": {"document_id": doc.id, "polygon": top + bottom}, "baseline": baseline,
    })
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _simplify(db, ids, tolerance):
    return registry.invoke(
        db, "segment.simplify",
        {"segment_ids": ids, "expected_versions": {sid: db.get(Segment, sid).version for sid in ids},
         "tolerance": tolerance},
        _person(),
    )


def test_a_dense_outline_comes_down_to_a_handful_of_points_within_the_tolerance(db, client):
    doc, pass_id = _page(db, client)
    line = _dense_line(client, doc, pass_id)
    before = db.get(Segment, line)

    _simplify(db, [line], 2.0)

    after = db.get(Segment, line)
    assert len(after.anchor.polygon) <= 8 < len(before.anchor.polygon)
    assert len(after.baseline) <= 4 < len(before.baseline)
    # Every point it dropped is within the tolerance (in pixels) of the corner points it kept.
    xs = [x * W for x, _ in after.anchor.polygon]
    assert min(xs) == pytest.approx(100, abs=2.5) and max(xs) == pytest.approx(700, abs=3.5)
    assert after.anchor.rect[2] * W == pytest.approx(600, abs=4)


def test_one_undo_brings_every_point_back(db, client):
    doc, pass_id = _page(db, client)
    line = _dense_line(client, doc, pass_id)
    before = db.get(Segment, line)

    result = _simplify(db, [line], 2.0)
    response = client.post(f"/api/actions/audit/{result.audit_id}/undo")
    assert response.status_code == 200, response.text

    after = db.get(Segment, line)
    assert after.anchor.polygon == before.anchor.polygon
    assert after.baseline == before.baseline


def test_a_shape_already_simple_is_refused_and_left_alone(db, client):
    doc, pass_id = _page(db, client)
    response = client.post("/api/segments", json={
        "document_id": doc.id, "pass_id": pass_id, "kind": "line",
        "anchor": {"document_id": doc.id, "polygon": [[0.1, 0.2], [0.7, 0.2], [0.7, 0.28], [0.1, 0.28]]},
    })
    box = response.json()["id"]
    version = db.get(Segment, box).version

    with pytest.raises(HTTPException) as refused:
        _simplify(db, [box], 2.0)
    assert refused.value.status_code == 422
    assert db.get(Segment, box).version == version


def test_the_tolerance_is_in_pixels_not_fractions(db, client):
    doc, pass_id = _page(db, client)
    line = _dense_line(client, doc, pass_id)
    points = len(db.get(Segment, line).anchor.polygon)

    # A tenth of a pixel is less than the half-pixel wobble, so no point can go (read as a fraction of the page it
    # would have flattened the whole line).
    with pytest.raises(HTTPException) as refused:
        _simplify(db, [line], 0.1)
    assert refused.value.status_code == 422
    assert len(db.get(Segment, line).anchor.polygon) == points
