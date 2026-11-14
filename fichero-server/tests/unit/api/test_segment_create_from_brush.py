"""The Paintbrush: a stroke of points with widths becomes a line, the painted area its outline, the path its baseline.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.paintbrush` (the app sends the stroke as
points with a width each; the engine turns it into the polygon and the centreline, `segment.create` with
`brush_stroke`; one action, one undo).
"""
from __future__ import annotations

import pytest

from fichero_server.actions.registry import registry
from fichero_server.media import paint_stroke
from fichero_server.models import Segment
from tests.unit.api.test_regenerate_outline import H, W, _page, _person

pytestmark = pytest.mark.source_model


def test_the_painted_area_is_the_outline_and_the_path_the_centreline():
    stroke = [[100 + i, 200 + 0.4 * (i % 2), 30] for i in range(0, 600, 2)]
    outline, centre = paint_stroke.painted(stroke, tolerance=2.0)
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    assert min(xs) == pytest.approx(85, abs=3) and max(xs) == pytest.approx(713, abs=3)
    assert min(ys) == pytest.approx(185, abs=3) and max(ys) == pytest.approx(215, abs=3), "as wide as the brush"
    assert len(outline) <= 12, "a handful of points, not one per pixel"
    assert len(centre) <= 3 and centre[0][0] == pytest.approx(100) and centre[-1][0] == pytest.approx(698)


def test_nothing_painted_is_nothing():
    assert paint_stroke.painted([], tolerance=2.0) is None
    assert paint_stroke.painted([[10, 10, 0]], tolerance=2.0) is None


def test_a_brush_stroke_makes_one_line_with_its_outline_and_baseline_and_one_undo(db, client):
    doc, pass_id = _page(db, client, [])
    stroke = [[(100 + i) / W, 200 / H, 30] for i in range(0, 600, 2)]
    made = registry.invoke(db, "segment.create", {
        "document_id": doc.id, "pass_id": pass_id, "kind": "line", "brush_stroke": stroke,
        "anchor": {"document_id": doc.id, "shapes": [{"kind": "path", "points": [p[:2] for p in stroke]}]},
    }, _person())
    row = db.get(Segment, made.result["segment_ids"][0])
    ys = [y * H for _, y in row.anchor.polygon]
    assert min(ys) == pytest.approx(185, abs=3) and max(ys) == pytest.approx(215, abs=3)
    assert len(row.baseline) == 2 and row.baseline[0][1] * H == pytest.approx(200, abs=1)

    undone = client.post(f"/api/actions/audit/{made.audit_id}/undo")
    assert undone.status_code == 200, undone.text
    assert db.get(Segment, row.id).deleted_at is not None
