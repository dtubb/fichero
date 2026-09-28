"""Control points and shapes measured on ANOTHER image of the page are carried to it only through a
recorded alignment; otherwise Fichero says it cannot (#5122, maps C2; `source.geo.gcp-other-image`,
`source.segment.no-guessing-across-images`).

WHY: a page has several images -- the scan, a crop, a deskewed copy -- and a point's normalised
coordinates mean a different place on each. A label drawn on a crop and read as if it were on the
full scan lands in the wrong street, with nothing on the answer to say so. Through the recorded
relation (a crop's rect on the page) the place is exact; with none (a turned image whose angle is
not recorded) the honest answer is "cannot", for a GCP (left out, with the reason) and for a shape
(refused, with the reason). If this regresses, shapes on another image are silently misplaced.

The pass is the real Allmaps Paris plan (MIT) through format.import; the expected world point is the
file's own (a thin-plate spline is exact at its GCPs).
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.models import Rendition, Segment
from fichero_server.models.anchors import NodeRegion
from tests.unit.api.test_a_georeferencing_file_imports_as_a_pass import PARIS, _annotation, _file_gcps, _import
from tests.unit.api.test_page_text_follows_the_file import BOOT

SOURCE = _annotation(PARIS)["target"]["source"]
W, H = SOURCE["width"], SOURCE["height"]
CROP = [0.25, 0.2, 0.5, 0.7]   # the crop's place on the page (normalised)


def _setup(db):
    doc_id = _import(db, PARIS, (W, H))
    crop = Rendition(document_id=doc_id, role="crop", path="files/crop.jpg", transform=NodeRegion(rect=CROP))
    turned = Rendition(document_id=doc_id, role="rotated", path="files/turned.jpg", transform=NodeRegion(rect=[0, 0, 1, 1]))
    db.save(crop)
    db.save(turned)
    names = registry.invoke(db, "segment.pass_create", {"document_id": doc_id, "name": "names"}, BOOT).result["id"]
    return doc_id, names, crop.id, turned.id


def _label(db, doc_id, pass_id, rendition_id, point) -> str:
    return registry.invoke(db, "segment.create", {
        "document_id": doc_id, "pass_id": pass_id, "kind": "place",
        "anchor": {"document_id": doc_id, "rendition_id": rendition_id,
                   "shapes": [{"kind": "point", "points": [point]}]}}, BOOT).result["segment_ids"][0]


def test_a_label_on_a_crop_is_carried_to_the_page_through_its_rect(db, client):
    doc_id, names, crop, _turned = _setup(db)
    (px, py), (lon, lat) = _file_gcps(PARIS)[2]
    on_page = (px / W, py / H)
    on_crop = [(on_page[0] - CROP[0]) / CROP[2], (on_page[1] - CROP[1]) / CROP[3]]
    assert all(0 <= v <= 1 for v in on_crop), "the GCP lies inside the crop"
    got = client.get(f"/api/georeference/segments/{_label(db, doc_id, names, crop, on_crop)}/world-shape").json()
    assert abs(got["geometry"]["coordinates"][0] - lon) < 1e-7 and abs(got["geometry"]["coordinates"][1] - lat) < 1e-7


def test_a_label_on_a_turned_image_is_refused_not_guessed(db, client):
    doc_id, names, _crop, turned = _setup(db)
    response = client.get(f"/api/georeference/segments/{_label(db, doc_id, names, turned, [0.4, 0.5])}/world-shape")
    assert response.status_code == 422 and "rotated image" in response.text and "cannot be carried" in response.text


def test_a_gcp_moved_onto_a_turned_image_is_left_out_with_the_reason(db, client):
    doc_id, _names, _crop, turned = _setup(db)
    gcp = sorted((s for s in db.all(Segment) if s.document_id == doc_id and s.kind == "control-point"), key=lambda s: s.id)[0]
    moved = gcp.anchor.model_copy(update={"rendition_id": turned})
    registry.invoke(db, "segment.update", {"segment_id": gcp.id, "expected_version": gcp.version,
                                           "anchor": moved.model_dump(mode="json")}, BOOT)
    [pass_id] = {s.pass_id for s in db.all(Segment) if s.id == gcp.id}
    got = client.get(f"/api/georeference/passes/{pass_id}/transform").json()
    assert gcp.id not in {g["segment_id"] for g in got["gcps"]}
    [left_out] = [n for n in got["not_used"] if n["segment_id"] == gcp.id]
    assert "rotated image" in left_out["reason"]
