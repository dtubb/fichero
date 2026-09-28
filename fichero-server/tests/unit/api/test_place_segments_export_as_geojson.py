"""A georeferenced page's place segments export as RFC 7946 GeoJSON, each Feature citing its segment
(#5122, maps C5; `source.geo.geojson-out`, the place-segment half).

WHY: GeoJSON is how every GIS and web map takes places in. Each Feature must carry the reference
back to the segment it came from, or a point on a map cannot be traced to the ink that put it
there -- which is the whole claim of this programme. It must also be VALID RFC 7946 (WGS 84
lon/lat, closed rings, exterior rings counterclockwise: an image's y runs down, so a ring drawn on
the page comes out clockwise unless it is turned), and a shape that cannot be placed is listed
with its reason, never dropped or extrapolated. If this regresses, a map gets points nobody can
cite, rings a GIS reads inside out, or silently fewer places than the page has.

The page is the real Allmaps Paris plan (MIT) through format.import; the expected world point is
the file's own (read with json), and the ring's orientation is computed here, not by the exporter.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.models.geo import geojson_problems
from tests.unit.api.test_a_georeferencing_file_imports_as_a_pass import PARIS, _annotation, _file_gcps, _import
from tests.unit.api.test_page_text_follows_the_file import BOOT

SOURCE = _annotation(PARIS)["target"]["source"]
W, H = SOURCE["width"], SOURCE["height"]


def _page(db):
    doc_id = _import(db, PARIS, (W, H))
    names = registry.invoke(db, "segment.pass_create", {"document_id": doc_id, "name": "names"}, BOOT).result["id"]

    def seg(kind, shape):
        return registry.invoke(db, "segment.create", {
            "document_id": doc_id, "pass_id": names, "kind": kind,
            "anchor": {"document_id": doc_id, "shapes": [shape]}}, BOOT).result["segment_ids"][0]

    (px, py), world = _file_gcps(PARIS)[2]
    ids = {
        "at_gcp": seg("place", {"kind": "point", "points": [[px / W, py / H]]}),
        "area": seg("place", {"kind": "polygon", "points": [[0.3, 0.3], [0.5, 0.3], [0.5, 0.6], [0.3, 0.6]]}),
        "margin": seg("place", {"kind": "point", "points": [[10 / W, 10 / H]]}),
        "a_line": seg("line", {"kind": "point", "points": [[0.4, 0.4]]}),
    }
    return doc_id, ids, world


def _area(ring):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:])) / 2


def test_the_places_are_valid_geojson_and_each_cites_its_segment(db, client):
    doc_id, ids, (lon, lat) = _page(db)
    got = client.get(f"/api/georeference/documents/{doc_id}/geojson").json()
    assert geojson_problems(got) == []
    by_id = {f["id"]: f for f in got["features"]}
    assert set(by_id) == {ids["at_gcp"], ids["area"]}                         # places only, and placed
    point = by_id[ids["at_gcp"]]["geometry"]["coordinates"]
    assert abs(point[0] - lon) < 1e-7 and abs(point[1] - lat) < 1e-7
    ring = by_id[ids["area"]]["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1] and _area(ring) > 0                           # closed, counterclockwise
    for segment_id, feature in by_id.items():
        reference = client.get(f"/api/segments/{segment_id}/reference").json()["reference"]
        assert feature["properties"]["reference"] == reference
    assert [n["segment_id"] for n in got["fichero:not_placed"]] == [ids["margin"]]


def test_other_kinds_are_placed_when_asked_for(db, client):
    doc_id, ids, _world = _page(db)
    got = client.get(f"/api/georeference/documents/{doc_id}/geojson", params={"kinds": "place,line"}).json()
    assert ids["a_line"] in {f["id"] for f in got["features"]}


class TestTheCheckerFires:
    def _fc(self, geometry, **extra):
        return {"type": "FeatureCollection", **extra,
                "features": [{"type": "Feature", "properties": {}, "geometry": geometry}]}

    def test_a_clockwise_exterior_ring(self):
        ring = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]
        assert any("counterclockwise" in p for p in geojson_problems(self._fc({"type": "Polygon", "coordinates": [ring]})))

    def test_latitude_out_of_range_an_open_ring_and_a_crs_member(self):
        assert any("in range" in p for p in geojson_problems(self._fc({"type": "Point", "coordinates": [2.3, 148.8]})))
        assert any("closed" in p for p in geojson_problems(
            self._fc({"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]]})))
        assert any("crs" in p for p in geojson_problems(self._fc({"type": "Point", "coordinates": [2, 48]}, crs={})))
