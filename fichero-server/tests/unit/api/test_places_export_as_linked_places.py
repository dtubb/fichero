"""A place entity exports as Linked Places Format: its names with language, dates and citations, its
dated geometries, its gazetteer links (maps D9, #4946; `source.geo.linked-places-out`).

WHY: LPF is how a place with a history leaves one gazetteer for another (the World Historical
Gazetteer takes it). An export that drops a name's language or date, or a geometry's `when`, hands
WHG a place that was everywhere at once under every name at once -- the flattening D6/D7 exist to
undo. And LPF's `when` is ISO 8601, which counts years astronomically: Pleiades's -30 (30 BC)
written out as "-0030" would put every ancient name a year early. If this regresses, a place loses
its history or its dates shift by a year on the way out.

The place is built through the app's actions from the real recorded Pleiades Lutetia record
(CC BY 3.0) and Wikidata's North Magnetic Pole (CC0); the export is checked against the source
files read with plain json, and each geometry against RFC 7946's rules (`geojson_problems`).
"""

from __future__ import annotations

from fichero_server.models.geo import geojson_problems
from fichero_server.models.knowledge import AuthoritySnapshot
from tests.unit.api.test_places_over_time import (
    LUTETIA, _entity, _invoke, _names_from_pleiades, _pleiades_span, _pole_positions,
)


def _lpf(client, entity_id):
    response = client.get(f"/api/entities/{entity_id}/linked-places")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["type"] == "FeatureCollection" and "linkedplaces-context" in body["@context"]
    [feature] = body["features"]
    return feature


def test_lutetia_leaves_with_every_name_dated_in_iso_8601_and_its_gazetteer_link(db, client):
    paris = _entity(db, "Paris")
    _names_from_pleiades(client, paris.id)
    for location in LUTETIA["locations"]:
        lon, lat = location["geometry"]["coordinates"]
        _invoke(client, "entity.add_geometry", {"entity_id": paris.id, "place": {
            "label": location["title"], "geometry_type": "point", "lat": lat, "lon": lon, "basis": "asserted",
            "when": _pleiades_span(location), "rationale": location["uri"]}})
    db.save(AuthoritySnapshot(authority="pleiades", authority_id="109126", label=LUTETIA["title"], source_url=LUTETIA["uri"]))
    linked = client.post("/api/kg/entity-curation/authority/link",
                         json={"entity_id": paris.id, "authority": "pleiades", "authority_id": "109126"})
    assert linked.status_code == 200, linked.text

    feature = _lpf(client, paris.id)
    toponyms = {(n["toponym"], n.get("lang")) for n in feature["names"]}
    for row in LUTETIA["names"]:
        attested = row["attested"] or row["romanized"]
        assert (attested, row["language"] or None) in toponyms, attested
    greek = next(n for n in feature["names"] if n["toponym"] == "Λουκοτοκία")
    assert greek["when"]["timespans"] == [{"start": {"in": "-0029"}, "end": {"in": "0300"}}]   # 30 BC is -0029
    assert greek["citations"] == [{"@id": next(r["uri"] for r in LUTETIA["names"] if r["attested"] == "Λουκοτοκία")}]
    assert ("Loutokotia", "grc-Latn") in toponyms                                  # the romanized form, marked
    geometries = feature["geometry"]["geometries"]
    assert [g["coordinates"] for g in geometries] == [l["geometry"]["coordinates"] for l in LUTETIA["locations"]]
    assert all(g["when"]["timespans"] == [{"start": {"in": "-0329"}, "end": {"in": "0640"}}] for g in geometries)
    assert feature["links"] == [{"type": "exactMatch", "identifier": LUTETIA["uri"]}]


def test_a_moving_place_leaves_with_each_position_dated(db, client):
    pole = _entity(db, "North Magnetic Pole")
    positions = list(_pole_positions())
    for lat, lon, when in positions:
        _invoke(client, "entity.add_geometry", {"entity_id": pole.id, "place": {
            "label": "North Magnetic Pole", "geometry_type": "point", "lat": lat, "lon": lon, "basis": "asserted",
            "when": {"start": when, "end": when, "basis": "asserted"}}})
    geometries = _lpf(client, pole.id)["geometry"]["geometries"]
    by_start = {g["when"]["timespans"][0]["start"]["in"]: g["coordinates"] for g in geometries}
    [(ross_lat, ross_lon)] = [(lat, lon) for lat, lon, when in positions if when.startswith("+1831")]
    assert by_start["1831-06-01"] == [ross_lon, ross_lat]                       # Ross's fix, to the day
    assert by_start["2019"] == [175.34585, 86.448]                              # Wikidata's 2019-00-00 is a year
    # Each geometry is RFC 7946 GeoJSON: lon/lat, in range.
    as_features = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": g["type"], "coordinates": g["coordinates"]}}
        for g in geometries]}
    assert geojson_problems(as_features) == []


def test_a_place_with_no_history_is_still_a_valid_feature(db, client):
    bare = _entity(db, "Popayán")
    feature = _lpf(client, bare.id)
    assert feature["names"] == [{"toponym": "Popayán"}] and "geometry" not in feature and "links" not in feature
