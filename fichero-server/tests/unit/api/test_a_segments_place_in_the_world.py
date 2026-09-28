"""Any segment on a georeferenced image is answered with its place in the world -- worked out
through the pass's transform, never stored -- or "outside the map" (#5122;
`source.geo.world-shape`, `source.geo.outside-the-mask`).

WHY: this is what georeferencing is FOR: a place name written on a plan, a boundary drawn on it,
answered as a point or shape on the earth, with how far off it may be. Stored, it would go stale
the moment a GCP is corrected; so it is worked out on every read, naming the GCP set it came
from. And a shape in the margin, the title cartouche or the scale bar is not on the map at all:
extrapolating the transform there gives a confident place that means nothing, so it is answered
"outside the map". If this regresses, a label lands in the wrong street, a corrected GCP changes
nothing, or the cartouche gets coordinates.

The pass is the real Allmaps Paris plan (MIT) through format.import; the expected world points
are the file's own, read with json (under its thin-plate spline, a GCP's pixel maps exactly to
its world point).
"""

from __future__ import annotations

import json

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.api.routes.document.segment_readings import counting_by_kind, readings_of_segment
from fichero_server.models import Segment, SegmentPass
from tests.unit.api.test_a_georeferencing_file_imports_as_a_pass import PARIS, _annotation, _file_gcps, _import
from tests.unit.api.test_page_text_follows_the_file import BOOT

SOURCE = _annotation(PARIS)["target"]["source"]
W, H = SOURCE["width"], SOURCE["height"]


def _setup(db):
    doc_id = _import(db, PARIS, (W, H))
    labels = registry.invoke(db, "segment.pass_create", {"document_id": doc_id, "name": "place names"}, BOOT).result["id"]
    return doc_id, labels


def _segment(db, doc_id, pass_id, shape) -> str:
    return registry.invoke(db, "segment.create", {
        "document_id": doc_id, "pass_id": pass_id, "kind": "place",
        "anchor": {"document_id": doc_id, "shapes": [shape]}}, BOOT).result["segment_ids"][0]


def _shape(client, segment_id):
    response = client.get(f"/api/georeference/segments/{segment_id}/world-shape")
    assert response.status_code == 200, response.text
    return response.json()


def test_a_label_at_a_gcps_pixel_is_at_that_gcps_place(db, client):
    doc_id, labels = _setup(db)
    (px, py), (lon, lat) = _file_gcps(PARIS)[2]
    got = _shape(client, _segment(db, doc_id, labels, {"kind": "point", "points": [[px / W, py / H]]}))
    assert got["geometry"]["type"] == "Point" and got["crs"] == "EPSG:4326"
    assert abs(got["geometry"]["coordinates"][0] - lon) < 1e-7 and abs(got["geometry"]["coordinates"][1] - lat) < 1e-7
    assert got["transformation"] == "thin-plate-spline" and got["outside_the_map"] is False


def test_an_area_inside_the_map_is_a_closed_polygon_among_the_gcps(db, client):
    doc_id, labels = _setup(db)
    ring = [[0.3, 0.3], [0.5, 0.3], [0.5, 0.6], [0.3, 0.6]]
    got = _shape(client, _segment(db, doc_id, labels, {"kind": "polygon", "points": ring}))
    coords = got["geometry"]["coordinates"][0]
    assert got["geometry"]["type"] == "Polygon" and len(coords) == 5 and coords[0] == coords[-1]
    lons, lats = [p[0] for _px, p in _file_gcps(PARIS)], [p[1] for _px, p in _file_gcps(PARIS)]
    assert all(min(lons) - 0.01 < x < max(lons) + 0.01 and min(lats) - 0.01 < y < max(lats) + 0.01 for x, y in coords)


def test_the_margin_is_outside_the_map_not_extrapolated(db, client):
    doc_id, labels = _setup(db)
    got = _shape(client, _segment(db, doc_id, labels, {"kind": "point", "points": [[10 / W, 10 / H]]}))
    assert got["outside_the_map"] is True and got["geometry"] is None and got["reason"]


def test_a_corrected_gcp_moves_the_answer(db, client):
    doc_id, labels = _setup(db)
    label = _segment(db, doc_id, labels, {"kind": "point", "points": [[0.4, 0.5]]})
    before = _shape(client, label)
    gcp = sorted(s.id for s in db.all(Segment) if s.document_id == doc_id and s.kind == "control-point")[0]
    old = counting_by_kind(db, gcp, readings_of_segment(db, gcp))["world-point"].representation_id
    registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": gcp, "kind": "world-point", "corrects_representation_id": old,
        "content": json.dumps({"coordinates": [2.2870, 48.8610], "crs": "EPSG:4326", "axis_order": "lon,lat"})}, BOOT)
    after = _shape(client, label)
    assert after["gcp_set_version"] != before["gcp_set_version"]
    assert after["geometry"]["coordinates"] != before["geometry"]["coordinates"]
