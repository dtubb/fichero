"""Georeferencing (slice 15, #4933; `source.geo.*`): a real map's control points, placed through the
calls the app and the command line make (`POST /api/actions/invoke`, `GET /api/georef/...`).

The control points are the ones in Allmaps' published Paris georeference (the vendored
`formats/fixtures/allmaps_paris_thin_plate_spline.georef.json`), read by the format reader -- someone
else's numbers, so a fit that only agrees with itself cannot pass.
"""

from __future__ import annotations

from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.formats import read_page
from tests.unit.api.test_segments_multiuser_access import (  # noqa: F401  (fixtures)
    _grant_role,
    _make_doc,
    _make_pass,
    _make_segment,
    _override,
    multiuser_client,
    users,
)

PARIS = Path(__file__).parents[1] / "formats" / "fixtures" / "allmaps_paris_thin_plate_spline.georef.json"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _invoke(client, name, params):
    return client.post("/api/actions/invoke", json={"name": name, "params": params})


def _undo(client, audit_id):
    return _ok(client.post(f"/api/actions/audit/{audit_id}/undo"))


def _segment(client, doc_id, pass_id, kind, **anchor) -> str:
    created = _ok(_invoke(client, "segment.create", {
        "document_id": doc_id, "pass_id": pass_id, "kind": kind, "anchor": {"document_id": doc_id, **anchor}}))
    return created["result"]["segment_ids"][0]


def _paris(db, client) -> dict:
    """The Paris sheet: its mask and four control points as segments, each placed in WGS 84."""
    page = read_page("iiif-georef", PARIS.read_bytes())
    doc = _make_doc(db, "paris.jpg")
    pass_id = _ok(_invoke(client, "segment.pass_create", {"document_id": doc.id, "name": "georeferencing"}))["result"]["id"]
    [mask] = [s for s in page.segments if s.kind == "mask"]
    mask_id = _segment(client, doc.id, pass_id, "mask", polygon=mask.polygon)
    gcps = []
    for g in (s for s in page.segments if s.kind == "control-point"):
        seg_id = _segment(client, doc.id, pass_id, "control-point", shapes=[{"kind": "point", "points": [g.point]}])
        placed = _ok(_invoke(client, "georef.place", {
            "segment_id": seg_id, "x": g.world[0], "y": g.world[1], "crs": "EPSG:4326", "axis_order": "lon,lat"}))
        gcps.append({"segment_id": seg_id, "world": g.world, "point": g.point,
                     "place_id": placed["result"]["place_id"], "audit_id": placed["audit_id"]})
    return {"doc_id": doc.id, "pass_id": pass_id, "mask_id": mask_id, "gcps": gcps}


def test_a_real_maps_control_points_place_any_segment_on_the_earth(db, client):
    """`gcp-is-a-segment`, `georef-is-a-pass`, `transform-is-derived`, `transformation-type`,
    `residuals`, `world-shape`, `outside-the-mask`. If the fit or the Mercator maths is wrong, a box in
    the middle of a map of Paris lands somewhere other than Paris."""
    paris = _paris(db, client)
    read = _ok(client.get(f"/api/georef/pass/{paris['pass_id']}"))
    assert read["transformation_type"] == "polynomial1" and read["needed"] == 3
    assert read["masks"] == [paris["mask_id"]] and read["refused"] is None and read["chosen"] is True
    assert len(read["control_points"]) == 4
    assert all(p["residual_m"] is not None and p["source_crs"] == "EPSG:4326" for p in read["control_points"])

    box = _segment(client, paris["doc_id"], paris["pass_id"], "region", rect=[0.4, 0.4, 0.1, 0.1])
    world = _ok(client.get(f"/api/georef/segment/{box}/world"))
    assert world["status"] == "placed" and world["crs"] == "EPSG:4326" and world["axis_order"] == "lon,lat"
    ring = world["geometry"]["coordinates"][0]
    assert world["geometry"]["type"] == "Polygon" and ring[0] == ring[-1] and len(ring) == 5
    assert all(2.2 < lon < 2.5 and 48.8 < lat < 48.95 for lon, lat in ring), ring  # Paris
    assert world["error_m"] > 0 and world["control_points_used"] == 4
    affine_version = world["gcp_set_version"]

    # The Allmaps file's own choice: a thin-plate spline, which meets every point exactly.
    chose = _ok(_invoke(client, "georef.set_type", {"pass_id": paris["pass_id"], "transformation_type": "thin_plate_spline"}))
    tps = _ok(client.get(f"/api/georef/pass/{paris['pass_id']}"))
    assert tps["gcp_set_version"] != affine_version  # an answer names what it was worked out from
    assert all(p["residual_m"] < 0.01 for p in tps["control_points"])
    assert _ok(client.get(f"/api/georef/segment/{box}/world"))["error_m"] is None  # exact estimates nothing
    _undo(client, chose["audit_id"])
    assert _ok(client.get(f"/api/georef/pass/{paris['pass_id']}"))["transformation_type"] == "polynomial1"

    # The mask starts about 2.5% in: a box in the corner is off the map, and is not extrapolated.
    corner = _segment(client, paris["doc_id"], paris["pass_id"], "region", rect=[0.0, 0.0, 0.01, 0.01])
    off = _ok(client.get(f"/api/georef/segment/{corner}/world"))
    assert off["status"] == "outside_the_map" and off["geometry"] is None


def test_retyping_one_control_point_changes_it_alone_shows_up_in_its_residual_and_undoes(db, client):
    """`gcp-corrected-alone`, `residuals`: a point typed a degree out turns metres of residual into
    kilometres.

    NOT "the wrong point has the largest residual". On this real map (four points, an affine, one to
    spare) least squares spreads one bad point over all four, and the bad one shows the SMALLEST
    residual (553 m against 4.8 km); leaving each out in turn does not single it out either. With few
    control points the residuals say the set is wrong, not which point -- found by this test, and
    recorded against `source.geo.residuals` in the spec."""
    paris = _paris(db, client)
    good_rms = _ok(client.get(f"/api/georef/pass/{paris['pass_id']}"))["rms_m"]
    wrong, others = paris["gcps"][0], paris["gcps"][1:]
    retyped = _ok(_invoke(client, "georef.place", {
        "segment_id": wrong["segment_id"], "x": wrong["world"][0] + 1.0, "y": wrong["world"][1],
        "crs": "EPSG:4326", "axis_order": "lon,lat"}))
    assert retyped["result"]["superseded_id"] == wrong["place_id"]
    points = {p["segment_id"]: p for p in _ok(client.get(f"/api/georef/pass/{paris['pass_id']}"))["control_points"]}
    assert all(points[o["segment_id"]]["place_id"] == o["place_id"] for o in others)  # nothing else changed
    bad_rms = _ok(client.get(f"/api/georef/pass/{paris['pass_id']}"))["rms_m"]
    assert bad_rms > 100 * good_rms, (good_rms, bad_rms)

    redo = _undo(client, retyped["audit_id"])
    back = {p["segment_id"]: p for p in _ok(client.get(f"/api/georef/pass/{paris['pass_id']}"))["control_points"]}
    assert back[wrong["segment_id"]]["place_id"] == wrong["place_id"]
    _undo(client, redo["audit_id"])  # ⇧⌘Z
    again = {p["segment_id"]: p for p in _ok(client.get(f"/api/georef/pass/{paris['pass_id']}"))["control_points"]}
    # Redo replays the placing (a fresh record with the same numbers), so compare the numbers.
    assert again[wrong["segment_id"]]["lon"] == wrong["world"][0] + 1.0


def test_too_few_control_points_for_the_type_is_refused_with_the_number_needed(db, client):
    paris = _paris(db, client)
    _ok(_invoke(client, "georef.set_type", {"pass_id": paris["pass_id"], "transformation_type": "polynomial2"}))
    read = _ok(client.get(f"/api/georef/pass/{paris['pass_id']}"))
    assert read["refused"] == "polynomial2 needs 6 control points with a known place; this pass has 4"
    box = _segment(client, paris["doc_id"], paris["pass_id"], "region", rect=[0.4, 0.4, 0.1, 0.1])
    refused = client.get(f"/api/georef/segment/{box}/world")
    assert refused.status_code == 422 and "needs 6" in refused.text


def test_the_crs_is_always_said_converted_to_wgs84_or_held_unknown(db, client):
    """`crs-explicit`, `crs-stored-as-wgs84`, `crs-unknown`, `proj-at-build`."""
    paris = _paris(db, client)
    seg = paris["gcps"][0]["segment_id"]
    lon, lat = paris["gcps"][0]["world"]
    grid = _invoke(client, "georef.place", {"segment_id": seg, "x": 529090, "y": 179645, "crs": "EPSG:27700"})
    assert grid.status_code == 422 and "PROJ" in grid.text
    unsaid = _invoke(client, "georef.place", {"segment_id": seg, "x": lon, "y": lat, "crs": "EPSG:4326"})
    assert unsaid.status_code == 422 and "axis_order" in unsaid.text

    _ok(_invoke(client, "georef.place", {"segment_id": seg, "x": lat, "y": lon, "crs": "EPSG:4326", "axis_order": "lat,lon"}))
    point = next(p for p in _ok(client.get(f"/api/georef/pass/{paris['pass_id']}"))["control_points"] if p["segment_id"] == seg)
    assert (point["lon"], point["lat"]) == (lon, lat)  # stored lon/lat in WGS 84
    assert (point["source_x"], point["source_y"], point["axis_order"]) == (lat, lon, "lat,lon")  # as typed

    _ok(_invoke(client, "georef.place", {"segment_id": seg, "x": 12.5, "y": 99.0, "crs": "unknown"}))
    read = _ok(client.get(f"/api/georef/pass/{paris['pass_id']}"))
    held = next(p for p in read["control_points"] if p["segment_id"] == seg)
    assert held["lon"] is None and held["source_crs"] == "unknown" and held["residual_m"] is None
    assert read["unknown_crs"] == 1 and read["refused"] is None  # three placed points still fit an affine


def test_a_machines_control_points_are_unchosen_and_two_georeferencings_are_not_picked_between(db, client):
    """`machine-gcps-unchosen`, the working-pass rule, `gcp-other-image`."""
    paris = _paris(db, client)
    machine = _make_pass(db, paris["doc_id"])  # a workflow's pass
    for g in paris["gcps"][:3]:
        seg = _segment(client, paris["doc_id"], machine.id, "control-point", shapes=[{"kind": "point", "points": [g["point"]]}])
        _ok(_invoke(client, "georef.place", {"segment_id": seg, "x": g["world"][0], "y": g["world"][1], "crs": "OGC:CRS84"}))
    assert _ok(client.get(f"/api/georef/pass/{machine.id}"))["chosen"] is False
    box = _segment(client, paris["doc_id"], paris["pass_id"], "region", rect=[0.4, 0.4, 0.1, 0.1])
    two = client.get(f"/api/georef/segment/{box}/world")
    assert two.status_code == 409 and "none is chosen" in two.text

    _ok(_invoke(client, "pass.choose_working", {"document_id": paris["doc_id"], "pass_id": machine.id}))
    assert _ok(client.get(f"/api/georef/pass/{machine.id}"))["chosen"] is True
    assert _ok(client.get(f"/api/georef/segment/{box}/world"))["pass_id"] == machine.id

    other = _segment(client, paris["doc_id"], paris["pass_id"], "region", rect=[0.4, 0.4, 0.1, 0.1],
                     rendition_id="a-rescan")
    refused = client.get(f"/api/georef/segment/{other}/world", params={"pass_id": paris["pass_id"]})
    assert refused.status_code == 422 and "another image" in refused.text


def test_a_person_denied_the_page_cannot_place_or_withdraw_its_control_points(multiuser_client, app_db, users, db):
    from fichero_server.models.georeference import ControlPointPlace

    client, login, library_path = multiuser_client
    _grant_role(app_db, users.editor, library_path, "editor")
    denied, allowed = _make_doc(db, "denied.jpg"), _make_doc(db, "allowed.jpg")
    _override(app_db, users.editor, library_path, denied.id, "deny")
    places = {}
    for doc in (denied, allowed):
        seg = _make_segment(db, document_id=doc.id, pass_id=_make_pass(db, doc.id).id, rect=[0.1, 0.1, 0.01, 0.01])
        place = ControlPointPlace(segment_id=seg.id, lon=2.3, lat=48.8, source_crs="EPSG:4326",
                                  source_x=2.3, source_y=48.8, axis_order="lon,lat")
        db.save(place)
        places[doc.id] = place.id
    for doc, expected in ((denied, 403), (allowed, 200)):
        withdrew = client.post("/api/actions/invoke", headers=login("editor"), json={
            "name": "georef.withdraw_place", "params": {"place_id": places[doc.id]}})
        assert withdrew.status_code == expected, (doc.name, withdrew.text)
