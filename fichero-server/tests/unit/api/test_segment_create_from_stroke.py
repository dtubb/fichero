"""The Marker: a freehand stroke becomes a segment, simplified on the way in.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.marker` (`segment.create` with `smoothing`,
0 to 1: the stroke is simplified in the page image's pixels so the record never holds a point per pixel; a baseline
stroke with `outline_from_baseline` gets its outline drawn from the ink, as Redraw does; one action, one undo).
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import registry
from fichero_server.models import Segment
from tests.unit.api.test_regenerate_outline import H, W, _page, _person

pytestmark = pytest.mark.source_model


def _wobbly(points_px, step=2):
    """A hand-drawn stroke through `points_px`: a point every `step` pixels, wobbling half a pixel."""
    out = []
    for (x0, y0), (x1, y1) in zip(points_px, points_px[1:]):
        n = max(int(max(abs(x1 - x0), abs(y1 - y0)) / step), 1)
        out += [[(x0 + (x1 - x0) * i / n) / W, (y0 + (y1 - y0) * i / n + 0.5 * (i % 2)) / H] for i in range(n)]
    return out


def _create(db, doc, pass_id, **body):
    return registry.invoke(db, "segment.create", {"document_id": doc.id, "pass_id": pass_id, **body}, _person())


def test_a_closed_stroke_is_a_region_with_a_handful_of_points(db, client):
    doc, pass_id = _page(db, client, [])
    loop = _wobbly([(100, 100), (500, 100), (500, 300), (100, 300), (100, 100)])
    assert len(loop) > 500

    result = _create(db, doc, pass_id, kind="region", smoothing=0.5,
                     anchor={"document_id": doc.id, "polygon": loop})

    row = db.get(Segment, result.result["segment_ids"][0])
    assert 4 <= len(row.anchor.polygon) <= 8, "the record holds the corners, not a point per pixel"
    xs = [x * W for x, _ in row.anchor.polygon]
    assert min(xs) == pytest.approx(100, abs=3) and max(xs) == pytest.approx(500, abs=3)


def test_no_smoothing_keeps_the_stroke_as_drawn(db, client):
    doc, pass_id = _page(db, client, [])
    loop = _wobbly([(100, 100), (500, 100), (500, 300), (100, 300), (100, 100)])
    result = _create(db, doc, pass_id, kind="region", anchor={"document_id": doc.id, "polygon": loop})
    assert len(db.get(Segment, result.result["segment_ids"][0]).anchor.polygon) == len(loop)


def test_an_open_stroke_is_a_line_whose_baseline_is_simplified(db, client):
    doc, pass_id = _page(db, client, [])
    stroke = _wobbly([(60, 200), (740, 200)])
    result = _create(db, doc, pass_id, kind="line", smoothing=0.5, baseline=stroke,
                     anchor={"document_id": doc.id, "shapes": [{"kind": "path", "points": stroke}]})
    row = db.get(Segment, result.result["segment_ids"][0])
    assert len(row.baseline) <= 3


def test_one_undo_takes_the_marker_segment_away(db, client):
    doc, pass_id = _page(db, client, [])
    loop = _wobbly([(100, 100), (500, 100), (500, 300), (100, 300), (100, 100)])
    result = _create(db, doc, pass_id, kind="region", smoothing=0.5, anchor={"document_id": doc.id, "polygon": loop})
    response = client.post(f"/api/actions/audit/{result.audit_id}/undo")
    assert response.status_code == 200, response.text
    assert db.get(Segment, result.result["segment_ids"][0]).deleted_at is not None


class TestOutlineFromTheInk:
    @pytest.fixture(autouse=True)
    def _kraken(self):
        pytest.importorskip("kraken.lib.segmentation")

    def test_an_open_stroke_over_ink_gets_its_outline_from_the_baseline(self, db, client):
        start, end = (60, 200), (740, 200)
        doc, pass_id = _page(db, client, [(start, end)])
        stroke = _wobbly([start, end])
        result = _create(db, doc, pass_id, kind="line", smoothing=0.5, baseline=stroke, outline_from_baseline=True,
                         anchor={"document_id": doc.id, "shapes": [{"kind": "path", "points": stroke}]})
        row = db.get(Segment, result.result["segment_ids"][0])
        assert row.anchor.polygon, "the outline is drawn"
        ys = [y * H for _, y in row.anchor.polygon]
        assert min(ys) < 200 - 20 and max(ys) >= 199, "it holds the ink standing on the baseline"
        assert result.result.get("outline") == "drawn"


def test_an_open_stroke_over_no_ink_keeps_its_baseline_and_says_no_outline_was_drawn(db, client):
    doc, pass_id = _page(db, client, [])
    stroke = _wobbly([(60, 200), (740, 200)])
    result = _create(db, doc, pass_id, kind="line", smoothing=0.5, baseline=stroke, outline_from_baseline=True,
                     anchor={"document_id": doc.id, "shapes": [{"kind": "path", "points": stroke}]})
    row = db.get(Segment, result.result["segment_ids"][0])
    assert not row.anchor.polygon and row.baseline
    assert result.result.get("outline") == "none"
