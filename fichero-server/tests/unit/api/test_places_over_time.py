"""A place's names and geometries over time (maps D6/D7, #5120; `source.geo.names-over-time`,
`source.geo.geometry-over-time`).

WHY: Paris was Lutetia to Rome, Λουκοτοκία to Ptolemy and باريس to an Ottoman clerk; an archive's
place is named by the name of ITS time, in its own script, and a reader needs to know which name was
current when. And places move: the North Magnetic Pole was fixed by Ross in 1831 in the Canadian
Arctic and has since drifted toward Siberia -- a letter about 1831 is about a different spot than a
2019 survey. Before this an entity held plain `aliases` and undated place points: a name with no
language, script, date or source, and a place that was everywhere it had ever been at once.

Two rulings pinned here (2026-09-28): `aliases` is DERIVED from the names, so "what is it called"
has one answer however it is asked (an alias written the old way still reads back; search finds a
name); and as of a date the answer is every geometry valid then -- rivals as rivals -- or none, with
the reason, never the nearest.

Real, licensed, recorded data (`tests/unit/api/fixtures/gazetteer/PROVENANCE.md`): Pleiades's Lutetia
(CC BY 3.0) and Wikidata's North Magnetic Pole (CC0), read with plain json and written through the
app's action route. Nothing is fetched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models.knowledge import EntityType, KnowledgeEntity

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gazetteer"
LUTETIA = json.loads((FIXTURES / "pleiades_109126_lutetia.json").read_text())
POLE = json.loads((FIXTURES / "wikidata_Q842763_north_magnetic_pole.json").read_text())["entities"]["Q842763"]


def _invoke(client, name, params):
    response = client.post("/api/actions/invoke", json={"name": name, "params": params})
    assert response.status_code == 200, response.text
    return response.json()


def _entity(db, name, kind=EntityType.location, aliases=()):
    entity = KnowledgeEntity(canonical_name=name, entity_type=kind, aliases=list(aliases))
    db.save(entity)
    return entity


def _pleiades_span(row):
    return {"start": None if row.get("start") is None else str(row["start"]),
            "end": None if row.get("end") is None else str(row["end"]),
            "numbering": "historical", "basis": "asserted"}


def _names_from_pleiades(client, entity_id):
    for row in LUTETIA["names"]:
        _invoke(client, "entity.add_name", {
            "entity_id": entity_id, "text": row["attested"] or row["romanized"],
            "romanized": row["romanized"] if row["attested"] else None, "language": row["language"] or None,
            "when": _pleiades_span(row) if row.get("start") is not None or row.get("end") is not None else None,
            "source": row["uri"]})


def test_each_name_keeps_its_language_script_dates_and_source(db, client):
    paris = _entity(db, "Paris")
    _names_from_pleiades(client, paris.id)
    names = db.get(KnowledgeEntity, paris.id).names
    assert len(names) == len(LUTETIA["names"]) == 15
    by_text = {name.text: name for name in names}
    greek = by_text["Λουκοτοκία"]
    assert (greek.language, greek.script, greek.romanized) == ("grc", "Grek", "Loutokotia")
    assert (greek.when.start, greek.when.end, greek.when.numbering) == ("-30", "300", "historical")
    arabic = by_text["باريس"]
    assert (arabic.language, arabic.script) == ("ota", "Arab")                  # the letters, not a guess
    assert arabic.source == next(r["uri"] for r in LUTETIA["names"] if r["attested"] == "باريس")
    assert all(name.provenance_kind.value == "human" and name.created_by for name in names)


def test_aliases_read_the_names_and_an_old_alias_still_reads_back(db, client):
    paris = _entity(db, "Paris", aliases=["Lutèce (older plain alias)"])        # written the old way
    _names_from_pleiades(client, paris.id)
    aliases = db.get(KnowledgeEntity, paris.id).aliases
    assert "Lutèce (older plain alias)" in aliases
    assert {"Λουκοτοκία", "Loutokotia", "Lutetia Parisiorum"} <= set(aliases)
    assert "Paris" not in aliases                                              # the canonical name is not its own alias
    for q in ("Loutokotia", "Parisiorum", "older plain"):
        found = client.get("/api/entities", params={"q": q}).json()["items"]
        assert [item["id"] for item in found] == [paris.id], q


def test_withdrawing_a_name_takes_it_out_of_aliases_and_undo_puts_it_back(db, client):
    paris = _entity(db, "Paris")
    made = _invoke(client, "entity.add_name", {"entity_id": paris.id, "text": "Λουκοτοκία", "romanized": "Loutokotia",
                                               "language": "grc", "source": LUTETIA["uri"]})
    name_id = made["result"]["name_id"]
    withdrawn = _invoke(client, "entity.withdraw_name", {"entity_id": paris.id, "name_id": name_id})
    after = db.get(KnowledgeEntity, paris.id)
    assert after.names == [] and "Loutokotia" not in after.aliases and "Λουκοτοκία" not in after.aliases
    undone = client.post(f"/api/actions/audit/{withdrawn['audit_id']}/undo")
    assert undone.status_code == 200, undone.text
    back = db.get(KnowledgeEntity, paris.id)
    assert [(n.id, n.text, n.language) for n in back.names] == [(name_id, "Λουκοτοκία", "grc")]
    assert "Loutokotia" in back.aliases


def test_names_move_with_a_merge(db, client):
    paris, lutetia = _entity(db, "Paris"), _entity(db, "Lutetia")
    _invoke(client, "entity.add_name", {"entity_id": lutetia.id, "text": "Λουκοτοκία", "language": "grc",
                                        "source": LUTETIA["uri"]})
    response = client.post("/api/kg/entity-curation/merge",
                           json={"absorbing_entity_id": paris.id, "absorbed_entity_ids": [lutetia.id]})
    assert response.status_code == 200, response.text
    moved = db.get(KnowledgeEntity, paris.id).names
    assert [(n.text, n.language, n.source) for n in moved] == [("Λουκοτοκία", "grc", LUTETIA["uri"])]


def _pole_positions():
    for statement in POLE["claims"]["P625"]:
        value = statement["mainsnak"]["datavalue"]["value"]
        [when] = [q["datavalue"]["value"]["time"] for q in statement["qualifiers"]["P585"]]
        yield value["latitude"], value["longitude"], when


def test_as_of_a_date_the_place_is_where_it_was_then_or_nowhere_said(db, client):
    pole = _entity(db, "North Magnetic Pole")
    positions = list(_pole_positions())
    assert len(positions) == 10
    for lat, lon, when in positions:
        _invoke(client, "entity.add_geometry", {"entity_id": pole.id, "place": {
            "label": "North Magnetic Pole", "geometry_type": "point", "lat": lat, "lon": lon, "basis": "asserted",
            "when": {"start": when, "end": when, "basis": "asserted"},
            "rationale": "Wikidata Q842763 P625 with P585"}})
    ross = [(lat, lon) for lat, lon, when in positions if when.startswith("+1831")]
    at_1831 = client.get(f"/api/entities/{pole.id}/place", params={"as_of": "1831"}).json()
    assert [(g["lat"], g["lon"]) for g in at_1831["geometries"]] == ross and at_1831["reason"] is None
    at_2012 = client.get(f"/api/entities/{pole.id}/place", params={"as_of": "2012-06-30"}).json()
    assert [(g["lat"], g["lon"]) for g in at_2012["geometries"]] == [(85.9, -147)]
    at_2015 = client.get(f"/api/entities/{pole.id}/place", params={"as_of": "2015"}).json()
    assert at_2015["geometries"] == [] and at_2015["reason"] == "none valid in 2015"   # not the nearest


def test_rival_geometries_of_one_period_are_listed_as_rivals_and_undated_apart(db, client):
    paris = _entity(db, "Paris")
    for location in LUTETIA["locations"]:
        lon, lat = location["geometry"]["coordinates"]
        _invoke(client, "entity.add_geometry", {"entity_id": paris.id, "place": {
            "label": location["title"], "geometry_type": "point", "lat": lat, "lon": lon, "basis": "asserted",
            "when": _pleiades_span(location), "rationale": location["uri"]}})
    lon, lat = LUTETIA["reprPoint"]                                           # Pleiades's undated point
    _invoke(client, "entity.add_geometry", {"entity_id": paris.id, "place": {
        "label": "Lutetia (representative point)", "geometry_type": "point", "lat": lat, "lon": lon,
        "basis": "asserted", "rationale": LUTETIA["uri"]}})
    at_100 = client.get(f"/api/entities/{paris.id}/place", params={"as_of": "100"}).json()
    assert sorted(g["label"] for g in at_100["geometries"]) == sorted(l["title"] for l in LUTETIA["locations"])
    assert [g["label"] for g in at_100["undated"]] == ["Lutetia (representative point)"]
    at_1800 = client.get(f"/api/entities/{paris.id}/place", params={"as_of": "1800"}).json()
    assert at_1800["geometries"] == [] and at_1800["reason"] == "none valid in 1800"
    assert [g["label"] for g in at_1800["undated"]] == ["Lutetia (representative point)"]   # never counted as valid


@pytest.mark.parametrize("as_of, valid", [("-329", True), ("-330", False), ("640", True), ("641", False)])
def test_the_source_s_year_numbering_is_honoured(db, client, as_of, valid):
    """Pleiades counts historically: its -330 is 330 BC, astronomical -329. `as_of` is ISO 8601
    (astronomical), so 330 BC is -329 and -330 is 331 BC, before the span."""
    paris = _entity(db, "Paris")
    location = LUTETIA["locations"][0]
    lon, lat = location["geometry"]["coordinates"]
    _invoke(client, "entity.add_geometry", {"entity_id": paris.id, "place": {
        "label": location["title"], "geometry_type": "point", "lat": lat, "lon": lon, "basis": "asserted",
        "when": _pleiades_span(location)}})
    answer = client.get(f"/api/entities/{paris.id}/place", params={"as_of": as_of}).json()
    assert bool(answer["geometries"]) is valid


def test_an_as_of_that_is_no_date_is_refused(db, client):
    paris = _entity(db, "Paris")
    assert client.get(f"/api/entities/{paris.id}/place", params={"as_of": "the Romans"}).status_code == 422


def test_the_mcp_tool_is_the_route(db, client, monkeypatch):
    """One question, one code path: an agent asking where a place was gets the app's answer."""
    import httpx
    from fichero_cli import FicheroClient
    from fichero_mcp import openapi_tools_generated as generated
    from fichero_mcp import server as mcp_server

    pole = _entity(db, "North Magnetic Pole")
    for lat, lon, when in _pole_positions():
        _invoke(client, "entity.add_geometry", {"entity_id": pole.id, "place": {
            "label": "North Magnetic Pole", "geometry_type": "point", "lat": lat, "lon": lon, "basis": "asserted",
            "when": {"start": when, "end": when, "basis": "asserted"}}})
    by_route = client.get(f"/api/entities/{pole.id}/place", params={"as_of": "2019"}).json()

    def forward(request: httpx.Request) -> httpx.Response:
        answered = client.request(request.method, request.url.path, params=dict(request.url.params))
        return httpx.Response(answered.status_code, json=answered.json())

    monkeypatch.setattr(mcp_server, "_client", lambda: FicheroClient(
        base_url="http://test", library_path="/tmp/Lib.fichero", token="t", transport=httpx.MockTransport(forward)))
    by_tool = generated.fichero_entities_place_as_of(entity_id=pole.id, as_of="2019")
    assert by_tool == by_route and [(g["lat"], g["lon"]) for g in by_tool["geometries"]] == [(86.448, 175.34585)]
