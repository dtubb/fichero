"""A place entity's gazetteer candidates: how each was found and how sure, kept after the choice,
a rejection remembered and not offered again -- all from local records, never the network, and a
geocoder's answer never among them (maps D4, #5123; `source.geo.gazetteer-candidates`,
`source.geo.gazetteer-offline`, `source.geo.geocoder-is-not-identity`).

WHY: "Paris" has namesakes. Wikidata's own search answers four records labelled Paris (the city, Paris in
Texas, a family name, a plant genus), and Pleiades files Paris under Lutetia. A candidate list that
forgot a person's "not that one" would offer the plant genus again
at every visit; one that did not say HOW it matched would rank a name among fifteen aliases level
with the entity's own name; one that fetched while being read would send a library's names to the
network without the switch; and a geocoder that pinned "paris" to a coordinate is a machine's guess
about WHERE, not a person's word about WHICH place -- if it became a `same_as` link, the guess
would be an identity. If this regresses, one of those comes back.

Real, licensed, recorded data (`tests/unit/api/fixtures/gazetteer/PROVENANCE.md`): Wikidata's search
answer for "Paris" (CC0), replayed through Fichero's own Wikidata refresh parser, and the Pleiades
record for Lutetia (CC BY 3.0). Nothing is fetched.
"""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.kg import entity_curation as curation
from fichero_server.knowledge.authorities import same_as_links
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import AuthoritySnapshot, EntityType, KnowledgeClaim, KnowledgeEntity

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gazetteer"
Q90 = "http://www.wikidata.org/entity/Q90"
DIFFERENT_FROM = "different_from"  # the link type a rejection is recorded as
LUTETIA = "https://pleiades.stoa.org/places/109126"
CANDIDATES = "/api/kg/entity-curation/candidates"


def _record_wikidata(db, monkeypatch) -> list[AuthoritySnapshot]:
    """The recorded answer, through the refresh's own parser -- the snapshots a real refresh stores."""
    recorded = json.loads((FIXTURES / "wikidata_search_paris.json").read_text())

    async def replay(name, url, params):
        assert params["search"] == "Paris"
        return recorded

    monkeypatch.setattr(curation, "_authority_json", replay)
    snapshots = asyncio.run(curation._fetch_wikidata_snapshots("Paris", 5))
    return curation._cache_authority_snapshots(db, snapshots)


def _record_pleiades(db) -> AuthoritySnapshot:
    record = json.loads((FIXTURES / "pleiades_109126_lutetia.json").read_text())
    names = [n["romanized"] for n in record["names"] if n.get("romanized")]
    snapshot = AuthoritySnapshot(authority="pleiades", authority_id=str(record["id"]), label=record["title"],
                                 aliases=[n for n in names if n != record["title"]], type="place",
                                 description=record["description"], source_url=record["uri"])
    db.save(snapshot)
    return snapshot


@pytest.fixture
def paris(db, monkeypatch) -> KnowledgeEntity:
    entity = KnowledgeEntity(canonical_name="Paris", entity_type=EntityType.location)
    db.save(entity)
    _record_wikidata(db, monkeypatch)
    _record_pleiades(db)
    return entity


def _offered(client, entity_id) -> dict[str, dict]:
    response = client.get(CANDIDATES, params={"scope": "external-authority", "entity_id": entity_id})
    assert response.status_code == 200, response.text
    return {row["uri"]: row for row in response.json()["items"]}


def _choose(client, entity_id, authority, identifier):
    response = client.post("/api/kg/entity-curation/authority/link",
                           json={"entity_id": entity_id, "authority": authority, "authority_id": identifier})
    assert response.status_code == 200, response.text
    return response.json()


def test_each_candidate_says_how_it_was_found_and_how_sure(client, paris):
    offered = _offered(client, paris.id)
    # The four Wikidata records labelled "Paris" (the club, labelled "Paris Saint-Germain FC", is
    # not one: Wikidata's search found it, Fichero's exact match does not), and Pleiades's Lutetia.
    assert len(offered) == 5
    assert offered[Q90]["found_by"] == "name" and offered[Q90]["confidence"] == 1.0
    lutetia = offered[LUTETIA]
    assert (lutetia["authority"], lutetia["found_by"], lutetia["confidence"]) == ("pleiades", "alias", 0.5)
    assert all(row["state"] == "proposed" and row["snapshot_id"] for row in offered.values())
    ranked = [row["confidence"] for row in _offered_list(client, paris.id)]
    assert ranked == sorted(ranked, reverse=True)                       # the surer match first


def _offered_list(client, entity_id) -> list[dict]:
    return client.get(CANDIDATES, params={"scope": "external-authority", "entity_id": entity_id}).json()["items"]


def test_choosing_one_keeps_it_and_rejects_its_namesakes_at_that_authority(client, db, paris):
    audit = _choose(client, paris.id, "wikidata", "Q90")
    offered = _offered(client, paris.id)
    assert offered[Q90]["state"] == "chosen"                             # kept after the choice
    # Paris (Texas), the family name and the plant genus are not offered again...
    assert sorted(offered) == [Q90, LUTETIA]
    # ...and the gazetteer's candidate is untouched: an entity may be the same as several gazetteers.
    assert offered[LUTETIA]["state"] == "proposed"
    rejections = same_as_links(db, paris.id, DIFFERENT_FROM)
    assert sorted(link.to_id.rsplit("/", 1)[1] for link in rejections) == ["Q162121", "Q18331346", "Q830149"]
    assert all(link.created_by and link.provenance_kind.value == "human" and Q90 in link.note for link in rejections)
    assert sorted(audit["alias_changes"]["authority_link"]["rejected"]) == sorted(link.to_id for link in rejections)


def test_a_person_rejects_a_candidate_and_it_stays_rejected_until_withdrawn(client, db, paris):
    ctx = ActionContext(actor="historian")
    # Given as Pleiades's own page URL: stored in the one canonical spelling, so it is recognised.
    made = registry.invoke(db, "typed_link.create", {
        "from_kind": "entity", "from_id": paris.id, "to_kind": "uri", "to_id": LUTETIA + "/",
        "link_type": "different_from", "note": "Lutetia is the Roman town, this is the modern city"}, ctx)
    link_id = made.result["link_id"]
    assert LUTETIA not in _offered(client, paris.id)
    assert len(_offered(client, paris.id)) == 4                          # the rest still offered
    registry.invoke(db, "typed_link.delete", {"link_id": link_id}, ctx)
    assert _offered(client, paris.id)[LUTETIA]["state"] == "proposed"    # the person changed their mind


def test_choosing_what_was_rejected_withdraws_the_rejection(client, db, paris):
    _choose(client, paris.id, "wikidata", "Q90")                         # rejects Paris, Texas
    _choose(client, paris.id, "wikidata", "Q830149")                     # the person's latest word
    offered = _offered(client, paris.id)
    assert offered["http://www.wikidata.org/entity/Q830149"]["state"] == "chosen"
    assert "http://www.wikidata.org/entity/Q830149" not in {
        link.to_id for link in same_as_links(db, paris.id, DIFFERENT_FROM)}


def test_reading_choosing_and_querying_places_never_touch_the_network(client, db, paris, monkeypatch):
    """`source.geo.gazetteer-offline`: only the explicit refresh, behind the switch, fetches."""

    def refuse(*_args, **_kwargs):
        raise AssertionError("a place read or choice went to the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(curation, "_authority_json", refuse)
    monkeypatch.setattr(curation, "_fetch_authority_snapshots", refuse)
    assert len(_offered(client, paris.id)) == 5
    _choose(client, paris.id, "pleiades", "109126")
    naming = client.get("/api/links/naming", params={"uri": LUTETIA})
    assert naming.status_code == 200 and naming.json()["entity_ids"] == [paris.id]
    # And the refresh itself is refused while the switch is off -- before any fetch.
    refused = client.post("/api/kg/entity-curation/authority/refresh", json={"query": "Paris"})
    assert refused.status_code == 403


def test_a_geocoder_hit_is_a_labelled_guess_and_never_a_gazetteer_link(db, paris):
    """`source.geo.geocoder-is-not-identity`."""
    from fichero_server.media import geo
    from fichero_server.models.knowledge import EvidenceBasis
    from fichero_server.models.typed_links import TypedLink
    from fichero_server.workflows.tools._entity_writer import attach_geocoded_places, save_claim

    db.save(Document(id="d1", name="page.txt", doc_type=DocType.page))
    claim_id = save_claim(db, text="He arrived in Paris.", source_document_id="d1",
                          source_page_label="1r", claim_location="Paris")
    sourced = geo.geocode_places_with_source(["Paris"], online=False)
    assert sourced["Paris"][1] == geo.SOURCE_GAZETTEER
    assert attach_geocoded_places(db, document_ids=["d1"], points_by_name=sourced)["updated"] == 1

    [place] = db.get(KnowledgeClaim, claim_id).place_values
    assert place.basis == EvidenceBasis.inferred and place.created_by == "geocoder"
    assert geo.SOURCE_GAZETTEER in place.rationale                       # which machine guessed
    # A coordinate, not an identity: no link from any entity to any authority was made...
    assert [link for link in db.query(TypedLink) if link.to_kind == "uri"] == []
    # ...and the entity's candidates are the recorded authority records, all still a person's to choose.
    rows = curation._external_authority_candidates(db, paris.id)
    assert {row["state"] for row in rows} == {"proposed"}
    assert {row["authority"] for row in rows} == {"wikidata", "pleiades"}
