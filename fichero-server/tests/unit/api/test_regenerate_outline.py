"""Redraw Outline from Baseline: a line's outline drawn again from its baseline and the page image.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.regenerate-polygon-from-baseline`
(`segment.regenerate_outline` over Kraken's polygonal-environment routine on the current image, the
neighbouring baselines as bounds so outlines do not overlap, an optional fixed height for a page with no
ink, a selection is one action and one undo) and `segment-editor.edge.no-baseline` (a line with no
baseline cannot be redrawn, and the answer says so).

The page is painted: ink where the lines are, so the assertions are about where the outline lands.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.media import line_join
from fichero_server.models import DocType, Document, FileType, Segment, Status

pytestmark = pytest.mark.source_model

W, H = 800, 400


def _person() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _ink(draw, start, end):
    """Forty letters standing on the line from `start` to `end` (pixels), each 28 px tall."""
    (x0, y0), (x1, y1) = start, end
    for i in range(40):
        x, y = x0 + (x1 - x0) * i / 40, y0 + (y1 - y0) * i / 40
        draw.rectangle([x, y - 28, x + 10, y], fill=0)


def _page(db, client, lines):
    from PIL import Image, ImageDraw

    image = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(image)
    for start, end in lines:
        _ink(draw, start, end)
    path = Path(db.path.parent) / "folio.png"
    image.save(path)
    doc = Document(name="folio.png", doc_type=DocType.file, file_type=FileType.image, path=str(path), status=Status.completed)
    db.save(doc)
    response = client.post("/api/segments/passes", json={"document_id": doc.id, "name": "lines"})
    assert response.status_code == 200, response.text
    return doc, response.json()["id"]


def _line(client, doc, pass_id, start, end, *, with_baseline=True) -> str:
    """A line whose stored outline is a thin wrong box, with its baseline in page fractions."""
    (x0, y0), (x1, y1) = start, end
    body = {
        "document_id": doc.id, "pass_id": pass_id, "kind": "line",
        "anchor": {"document_id": doc.id, "rect": [x0 / W, min(y0, y1) / H - 0.01, (x1 - x0) / W, 0.01]},
    }
    if with_baseline:
        body["baseline"] = [[x0 / W, y0 / H], [x1 / W, y1 / H]]
    response = client.post("/api/segments", json=body)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _redraw(db, ids, **extra):
    return registry.invoke(
        db, "segment.regenerate_outline",
        {"segment_ids": ids, "expected_versions": {sid: db.get(Segment, sid).version for sid in ids}, **extra},
        _person(),
    )


def _pixels(polygon):
    return [[x * W, y * H] for x, y in polygon]


def _overlap(a, b) -> int:
    import cv2
    import numpy as np

    masks = []
    for polygon in (a, b):
        mask = np.zeros((H, W), dtype=np.uint8)
        cv2.fillPoly(mask, [np.array([[round(x), round(y)] for x, y in _pixels(polygon)], dtype=np.int32)], 1)
        masks.append(mask)
    return int((masks[0] & masks[1]).sum())


class TestWithKraken:
    @pytest.fixture(autouse=True)
    def _kraken(self):
        pytest.importorskip("kraken.lib.segmentation")

    def test_a_tilted_line_gets_an_outline_around_its_ink(self, db, client):
        start, end = (60, 120), (740, 160)
        doc, pass_id = _page(db, client, [(start, end)])
        line = _line(client, doc, pass_id, start, end)
        before = db.get(Segment, line).version

        _redraw(db, [line])

        row = db.get(Segment, line)
        assert row.version == before + 1
        x0, y0, x1, y1 = (v for v in line_join.bounds(_pixels(row.anchor.polygon)))
        assert x0 == pytest.approx(60, abs=4) and x1 == pytest.approx(740, abs=4)
        # The letters stand 28 px over a baseline that falls 40 px across the page.
        assert y0 < 120 - 20 and y1 > 160 - 4
        assert row.anchor.rect == pytest.approx([min(p[0] for p in row.anchor.polygon), min(p[1] for p in row.anchor.polygon),
                                                 max(p[0] for p in row.anchor.polygon) - min(p[0] for p in row.anchor.polygon),
                                                 max(p[1] for p in row.anchor.polygon) - min(p[1] for p in row.anchor.polygon)])
        assert row.baseline == [[60 / W, 120 / H], [740 / W, 160 / H]], "the baseline is not touched"

    def test_two_close_lines_do_not_overlap(self, db, client):
        upper, lower = ((60, 150), (740, 150)), ((60, 190), (740, 190))
        doc, pass_id = _page(db, client, [upper, lower])
        first, second = _line(client, doc, pass_id, *upper), _line(client, doc, pass_id, *lower)

        _redraw(db, [first, second])

        assert _overlap(db.get(Segment, first).anchor.polygon, db.get(Segment, second).anchor.polygon) < 2 * W

    def test_a_neighbour_not_redrawn_still_bounds_the_outline(self, db, client):
        upper, lower = ((60, 150), (740, 150)), ((60, 190), (740, 190))
        doc, pass_id = _page(db, client, [upper, lower])
        _first, second = _line(client, doc, pass_id, *upper), _line(client, doc, pass_id, *lower)

        _redraw(db, [second])

        _x0, y0, _x1, _y1 = line_join.bounds(_pixels(db.get(Segment, second).anchor.polygon))
        assert y0 >= 150 - 2, "the outline does not climb past the line above's baseline"


class TestWithoutInk:
    def test_a_line_with_no_ink_gets_the_fixed_height(self, db, client):
        start, end = (60, 200), (740, 200)
        doc, pass_id = _page(db, client, [])
        line = _line(client, doc, pass_id, start, end)

        _redraw(db, [line], fixed_height=40)

        _x0, y0, _x1, y1 = line_join.bounds(_pixels(db.get(Segment, line).anchor.polygon))
        assert y0 == pytest.approx(160, abs=1)
        assert y1 == pytest.approx(210, abs=1)

    def test_with_no_ink_and_no_height_nothing_is_written_and_it_says_why(self, db, client):
        doc, pass_id = _page(db, client, [])
        line = _line(client, doc, pass_id, (60, 200), (740, 200))
        before = db.get(Segment, line).version

        with pytest.raises(HTTPException) as refused:
            _redraw(db, [line])
        assert refused.value.status_code == 422
        assert "fixed height" in str(refused.value.detail)
        assert db.get(Segment, line).version == before


class TestUndoAndRefusals:
    def test_one_undo_restores_every_line(self, db, client):
        doc, pass_id = _page(db, client, [])
        first = _line(client, doc, pass_id, (60, 150), (740, 150))
        second = _line(client, doc, pass_id, (60, 250), (740, 250))
        before = {sid: db.get(Segment, sid).anchor.model_dump() for sid in (first, second)}

        redraw = _redraw(db, [first, second], fixed_height=30)
        assert db.get(Segment, first).anchor.polygon is not None
        response = client.post(f"/api/actions/audit/{redraw.audit_id}/undo")
        assert response.status_code == 200, response.text

        assert {sid: db.get(Segment, sid).anchor.model_dump() for sid in (first, second)} == before

    def test_a_line_with_no_baseline_is_refused_by_name(self, db, client):
        doc, pass_id = _page(db, client, [])
        line = _line(client, doc, pass_id, (60, 150), (740, 150), with_baseline=False)

        with pytest.raises(HTTPException) as refused:
            _redraw(db, [line], fixed_height=30)
        assert refused.value.status_code == 422
        assert "no baseline" in str(refused.value.detail) and line in str(refused.value.detail)

    def test_a_stale_line_is_refused(self, db, client):
        doc, pass_id = _page(db, client, [])
        line = _line(client, doc, pass_id, (60, 150), (740, 150))

        with pytest.raises(HTTPException) as refused:
            registry.invoke(
                db, "segment.regenerate_outline",
                {"segment_ids": [line], "expected_versions": {line: db.get(Segment, line).version + 5}, "fixed_height": 30},
                _person(),
            )
        assert refused.value.status_code == 409
