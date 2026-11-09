"""#6420: the page's segments in a shown rendition's pixels, so the Preview can draw them there. A real photograph, a real line and a
real turned rendition: the line's box is the photograph's box turned a quarter; a rendition whose place is not recorded gives no boxes
and says so."""
from __future__ import annotations

from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import NodeRegion, Rendition
from fichero_server.models.anchors import SourceAnchor
from PIL import Image
from tests.unit.media.test_current_image_6296 import H, W, _page

RECT = [0.1, 0.2, 0.5, 0.1]  # x, y, w, h as fractions of the photograph


def _page_with_a_line(db, tmp_path: Path):
    doc = _page(db, tmp_path)
    ctx = ActionContext(actor="kraken", run_id="run-1", library_path=None, is_bootstrap=True)
    pass_id = registry.invoke(db, "segment.pass_create", {"document_id": doc.id, "name": "lines"}, ctx).result["id"]
    line = registry.invoke(db, "segment.create", {
        "document_id": doc.id, "pass_id": pass_id, "kind": "line", "parent_segment_id": None,
        "anchor": SourceAnchor(document_id=doc.id, rect=RECT).model_dump(mode="json")}, ctx).result["segment_ids"][0]
    return doc, line


def _turned(db, doc, tmp_path: Path, **transform) -> Rendition:
    turned = tmp_path / "turned.png"
    Image.open(tmp_path / "page.png").transpose(Image.Transpose.ROTATE_90).save(turned)
    row = Rendition(document_id=doc.id, role="rotated", path=str(turned), pixel_width=H, pixel_height=W,
                    transform=NodeRegion(rect=[0, 0, 1, 1], **transform))
    db.save(row)
    return row


def test_a_turned_rendition_carries_a_segment_box_onto_its_own_pixels(db, client, tmp_path):
    doc, line = _page_with_a_line(db, tmp_path)
    rendition = _turned(db, doc, tmp_path, method="turn", angle=90)

    answer = client.get(f"/api/segments/document/{doc.id}/on-rendition/{rendition.id}").json()

    assert answer["followed"] is True and answer["note"] is None
    assert (answer["image_width"], answer["image_height"]) == (H, W)
    x, y, w, h = answer["boxes"][line]
    # the quarter turn swaps the box's extent: its width in the turned picture is the photograph box's height (in pixels)
    assert (round(w), round(h)) == (round(RECT[3] * H), round(RECT[2] * W))
    assert 0 <= x <= H and 0 <= y <= W


def test_a_rendition_whose_place_is_not_recorded_gives_no_boxes_and_says_so(db, client, tmp_path):
    doc, _line = _page_with_a_line(db, tmp_path)
    rendition = _turned(db, doc, tmp_path, method="flatten")

    answer = client.get(f"/api/segments/document/{doc.id}/on-rendition/{rendition.id}").json()

    assert answer["followed"] is False and answer["boxes"] == {} and answer["note"]


def test_a_rendition_the_page_does_not_have_is_not_found(db, client, tmp_path):
    doc, _line = _page_with_a_line(db, tmp_path)
    assert client.get(f"/api/segments/document/{doc.id}/on-rendition/nope").status_code == 404
