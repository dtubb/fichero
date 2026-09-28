"""A ground control point's world end is a `world-point` reading, stored in WGS 84, its CRS
always said (#5122; `source.geo.gcp-is-a-segment`, `crs-explicit`, `crs-stored-as-wgs84`,
`crs-unknown`).

WHY: nothing in a library could hold a GCP's place on the earth, so a georeferencing file was
refused on import. The world end is a READING of the point segment -- so it has a maker, a
history, corrections that count and undo, with no second table -- and the reading is where the
coordinate rules bite: a coordinate with no CRS is refused (a number means nothing without its
frame), EPSG:4326 is stored with the axis order it arrived in recorded, and any other CRS is held
UNCONVERTED as `unknown` until PROJ ships -- never quietly taken to be WGS 84, which puts a
British National Grid point in the Gulf of Guinea. If this regresses, a GCP's place is lost, or a
wrong one is stored as right.

The GCPs are the real Allmaps plan of Paris (MIT), read with the standard library's json.
"""

from __future__ import annotations

import json
from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.models import DocType, Document, FileType, Status
from tests.unit.api.test_page_text_follows_the_file import BOOT

PARIS = Path(__file__).parents[1] / "formats" / "fixtures" / "allmaps_paris_thin_plate_spline.georef.json"


def _gcps() -> tuple[int, int, list[tuple[list[float], list[float]]]]:
    data = json.loads(PARIS.read_text())
    source = data["target"]["source"]
    return source["width"], source["height"], [
        (f["properties"]["resourceCoords"], f["geometry"]["coordinates"]) for f in data["body"]["features"]]


def _a_control_point(db) -> tuple[str, str, list[float]]:
    width, height, gcps = _gcps()
    doc = Document(name="paris.jpg", doc_type=DocType.file, file_type=FileType.image, path="/p/paris.jpg",
                   status=Status.completed, metadata={"width": width, "height": height})
    db.save(doc)
    pass_id = registry.invoke(db, "segment.pass_create", {"document_id": doc.id, "name": "georeference"}, BOOT).result["id"]
    (x, y), world = gcps[0]
    point = [x / width, y / height]
    segment = registry.invoke(db, "segment.create", {
        "document_id": doc.id, "pass_id": pass_id, "kind": "control-point",
        "anchor": {"document_id": doc.id, "shapes": [{"kind": "point", "points": [point]}]},
    }, BOOT).result
    return doc.id, segment["segment_ids"][0], world


def _write(client, doc_id, segment_id, value):
    return client.post("/api/content-representations", json={
        "document_id": doc_id, "segment_id": segment_id, "kind": "world-point", "content": json.dumps(value)})


def test_the_files_first_gcp_is_stored_in_wgs84_with_what_it_arrived_as(db, client):
    doc_id, segment_id, (lon, lat) = _a_control_point(db)
    response = _write(client, doc_id, segment_id, {"coordinates": [lon, lat], "crs": "EPSG:4326", "axis_order": "lon,lat"})
    assert response.status_code == 200, response.text
    stored = json.loads(response.json()["content"])
    assert (stored["lon"], stored["lat"], stored["crs"]) == (lon, lat, "EPSG:4326")
    assert (stored["crs_in"], stored["axis_order_in"], stored["as_entered"]) == ("EPSG:4326", "lon,lat", [lon, lat])
    assert response.json()["provenance_kind"] == "human"                    # a reading: the engine's maker


def test_latitude_first_is_turned_round_not_misread(db, client):
    doc_id, segment_id, (lon, lat) = _a_control_point(db)
    stored = json.loads(_write(client, doc_id, segment_id,
                               {"coordinates": [lat, lon], "crs": "EPSG:4326", "axis_order": "lat,lon"}).json()["content"])
    assert (stored["lon"], stored["lat"]) == (lon, lat)


def test_no_crs_is_refused_and_another_crs_is_held_unconverted(db, client):
    doc_id, segment_id, _world = _a_control_point(db)
    assert _write(client, doc_id, segment_id, {"coordinates": [2.29, 48.86], "axis_order": "lon,lat"}).status_code == 422
    grid = _write(client, doc_id, segment_id, {"coordinates": [529090, 179645], "crs": "EPSG:27700", "axis_order": "x,y"})
    stored = json.loads(grid.json()["content"])
    assert (stored["lon"], stored["lat"], stored["crs"], stored["crs_in"]) == (None, None, "unknown", "EPSG:27700")
    assert stored["as_entered"] == [529090, 179645] and "no conversion available" in stored["conversion"]


def test_a_number_that_is_not_a_longitude_and_latitude_is_refused(db, client):
    doc_id, segment_id, (lon, lat) = _a_control_point(db)
    swapped_wrongly = _write(client, doc_id, segment_id, {"coordinates": [lat, lon + 200], "crs": "EPSG:4326", "axis_order": "lon,lat"})
    assert swapped_wrongly.status_code == 422
