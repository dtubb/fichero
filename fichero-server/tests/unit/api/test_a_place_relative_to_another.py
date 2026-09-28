"""A place described relative to another -- "21 leguas de Quito", "96 leguas al N de Santa Fe" -- is
stored as written and resolves to an AREA, through a unit conversion the library chooses, with its
tolerance said out loud (maps D10, #5120; `source.geo.relative-place`, `source.geo.historical-units`).

WHY: most places in colonial sources are located this way, and a legua was not one length -- the
legua legal of 5000 varas and the legua común of 20000 pies differ by a third. Turning "21 leguas
de Quito" into a point invents a precision the source never had; storing the metres instead of the
words loses what the source said, so a better conversion could never be applied. And a width
nobody can see is a guess dressed as a measurement. So: the words and number are kept, the area is
worked out on every read through the library's chosen conversion, and the answer names the
conversion, its source, and where the tolerance came from. If this regresses, a relative place
becomes a false point, a conversion change silently rewrites what the source said, or an area's
width cannot be explained.

Real data: two entries of Alcedo's Diccionario (1786, public domain) and the anchors' coordinates
from Wikidata (CC0), all recorded (`fixtures/maps`, `fixtures/gazetteer`), written through the
app's action route. Alcedo's leguas are travel distances, so the areas are checked for how they
are worked out (with an independent haversine), not against the towns' true positions.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from fichero_server.knowledge.units import DEFAULT_TOLERANCE_FRACTION, UNITS, resolve_distance
from fichero_server.models.geo import geojson_problems
from fichero_server.models.knowledge import EntityType, KnowledgeEntity

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ALCEDO = json.loads((FIXTURES / "maps" / "alcedo_1786_leguas_excerpts.json").read_text())["excerpts"]


def _wikidata_point(name):
    record = json.loads(next((FIXTURES / "gazetteer").glob(f"wikidata_*_{name}_P625.json")).read_text())
    value = record["claims"]["P625"][0]["mainsnak"]["datavalue"]["value"]
    return value["latitude"], value["longitude"]


def _invoke(client, name, params, expect=200):
    response = client.post("/api/actions/invoke", json={"name": name, "params": params})
    assert response.status_code == expect, response.text
    return response.json()


def _anchor(db, client, name, wikidata_name):
    entity = KnowledgeEntity(canonical_name=name, entity_type=EntityType.location)
    db.save(entity)
    lat, lon = _wikidata_point(wikidata_name)
    _invoke(client, "entity.add_geometry", {"entity_id": entity.id, "place": {
        "label": name, "geometry_type": "point", "lat": lat, "lon": lon, "basis": "asserted"}})
    return entity, (lat, lon)


def _haversine(a, b):
    (lat1, lon1), (lat2, lon2) = a, b
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def _bearing(a, b):
    (lat1, lon1), (lat2, lon2) = a, b
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    return math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                   math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) % 360


def _rfc7946(area):
    """The area as RFC 7946 wants it: rings closed, exterior counterclockwise, holes clockwise."""
    return geojson_problems({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": area}]})


def _ibarra(db, client):
    quito, quito_at = _anchor(db, client, "Quito", "quito")
    ibarra = KnowledgeEntity(canonical_name="Ibarra", entity_type=EntityType.location)
    db.save(ibarra)
    assert "21 leguas de Quito" in ALCEDO["ibarra"]
    made = _invoke(client, "entity.add_relative_place", {
        "entity_id": ibarra.id, "relative": {"anchor_entity_id": quito.id, "relation_as_written": "de",
                                             "distance_as_written": "21 leguas", "distance_value": 21, "unit": "legua"},
        "source_field": "Alcedo, Diccionario (1786), II, s.v. Ibarra", "source_excerpt": ALCEDO["ibarra"]})
    return ibarra, quito, quito_at, made


def _relative(client, entity_id, as_of="1786"):
    body = client.get(f"/api/entities/{entity_id}/place", params={"as_of": as_of}).json()
    return body, body["relative"]


def test_a_distance_from_an_anchor_is_a_ring_never_a_point(db, client):
    ibarra, quito, quito_at, _ = _ibarra(db, client)
    body, [answer] = _relative(client, ibarra.id)
    assert body["geometries"] == [] and body["undated"] == []                 # not a point, anywhere
    conversion = answer["conversion"]
    legal, comun = UNITS["legua"].conversion("legal").metres, UNITS["legua"].conversion("comun").metres
    assert conversion["conversion"] == "legal" and abs(conversion["distance_m"] - 21 * legal) < 1e-6
    assert abs(conversion["tolerance_m"] - 21 * (comun - legal) / 2) < 1e-6    # from the unit's own spread
    assert "spread" in conversion["tolerance_basis"] and "Ley de 19 de julio de 1849" in conversion["source"]
    area = answer["area"]
    assert area["type"] == "Polygon" and len(area["coordinates"]) == 2      # a ring: outer edge and hole
    outer, inner = area["coordinates"]
    for ring, radius in ((outer, conversion["distance_m"] + conversion["tolerance_m"]),
                         (inner, conversion["distance_m"] - conversion["tolerance_m"])):
        assert all(abs(_haversine(quito_at, (lat, lon)) - radius) < 5 for lon, lat in ring[:-1])
    assert answer["anchor"]["entity_id"] == quito.id and answer["anchor"]["basis"] == "undated"   # said, not hidden
    assert _rfc7946(area) == []
    assert answer["relative"]["distance_as_written"] == "21 leguas"


def test_choosing_another_conversion_re_resolves_and_rewrites_nothing(db, client):
    ibarra, _quito, quito_at, _ = _ibarra(db, client)
    _, [legal] = _relative(client, ibarra.id)
    chosen = _invoke(client, "units.set_conversion", {"unit": "legua", "conversion": "comun"})
    _, [comun] = _relative(client, ibarra.id)
    assert comun["conversion"]["conversion"] == "comun"
    assert abs(comun["conversion"]["distance_m"] - 21 * UNITS["legua"].conversion("comun").metres) < 1e-6
    assert comun["area"] != legal["area"]                                      # the area moved outward
    stored = db.get(KnowledgeEntity, ibarra.id).place_values[0].relative
    assert (stored.distance_as_written, stored.distance_value, stored.unit) == ("21 leguas", 21, "legua")
    undone = client.post(f"/api/actions/audit/{chosen['audit_id']}/undo")
    assert undone.status_code == 200
    _, [back] = _relative(client, ibarra.id)
    assert back["conversion"]["conversion"] == "legal" and back["area"] == legal["area"]


def test_a_direction_narrows_the_ring_to_its_sector(db, client):
    santa_fe, santa_fe_at = _anchor(db, client, "Santa Fe", "bogota")
    town = KnowledgeEntity(canonical_name="a town of Pamplona's jurisdiction", entity_type=EntityType.location)
    db.save(town)
    assert "96 leguas al N de Santa Fe" in ALCEDO["pamplona_town"]
    _invoke(client, "entity.add_relative_place", {
        "entity_id": town.id, "relative": {"anchor_entity_id": santa_fe.id, "relation_as_written": "al N de",
                                           "bearing_deg": 0, "distance_as_written": "96 leguas",
                                           "distance_value": 96, "unit": "legua"},
        "source_excerpt": ALCEDO["pamplona_town"]})
    _, [answer] = _relative(client, town.id)
    [ring] = answer["area"]["coordinates"]
    assert _rfc7946(answer["area"]) == []
    bearings = [_bearing(santa_fe_at, (lat, lon)) for lon, lat in ring[:-1]]
    assert all(b <= 22.5 + 1e-6 or b >= 337.5 - 1e-6 for b in bearings)       # north, ±22.5°
    distances = [_haversine(santa_fe_at, (lat, lon)) for lon, lat in ring[:-1]]
    conversion = answer["conversion"]
    assert min(distances) > conversion["distance_m"] - conversion["tolerance_m"] - 5
    assert max(distances) < conversion["distance_m"] + conversion["tolerance_m"] + 5


def test_a_unit_with_one_conversion_carries_the_stated_default_tolerance():
    got = resolve_distance(3, "league")
    assert got["distance_m"] == 3 * 3 * 1609.344
    assert got["tolerance_m"] == got["distance_m"] * DEFAULT_TOLERANCE_FRACTION
    assert got["tolerance_basis"].startswith("stated default") and "NIST Handbook 44" in got["source"]


def test_an_unknown_unit_or_conversion_is_refused(db, client):
    quito, _ = _anchor(db, client, "Quito", "quito")
    ibarra = KnowledgeEntity(canonical_name="Ibarra", entity_type=EntityType.location)
    db.save(ibarra)
    _invoke(client, "entity.add_relative_place", {"entity_id": ibarra.id, "relative": {
        "anchor_entity_id": quito.id, "distance_as_written": "21 stadia", "distance_value": 21, "unit": "stadion"}},
        expect=422)
    _invoke(client, "units.set_conversion", {"unit": "legua", "conversion": "de 17 al grado"}, expect=422)


def test_an_anchor_with_nowhere_to_measure_from_says_so(db, client):
    nowhere = KnowledgeEntity(canonical_name="Pasto", entity_type=EntityType.location)
    ibarra = KnowledgeEntity(canonical_name="Ibarra", entity_type=EntityType.location)
    db.save(nowhere), db.save(ibarra)
    _invoke(client, "entity.add_relative_place", {"entity_id": ibarra.id, "relative": {
        "anchor_entity_id": nowhere.id, "distance_as_written": "49 leguas", "distance_value": 49, "unit": "legua"}})
    _, [answer] = _relative(client, ibarra.id)
    assert answer["area"] is None and "no geometry to measure from" in answer["reason"]
