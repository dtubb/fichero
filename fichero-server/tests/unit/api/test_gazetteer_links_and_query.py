"""A place's gazetteer links are `same_as` typed links to canonical URIs, the earlier metadata dict
is migrated into them on open, and "every segment that names this place" is one query (maps D3,
#5123; `source.geo.gazetteer-typed-record`, `source.geo.gazetteer-query`).

WHY: the answer to "which gazetteer place is this entity" lived in a dict in the entity's metadata:
no maker, no certainty, no time, no withdraw, and not queryable -- and after a typed record exists,
two stores answering the one question is how they drift (ruled 2026-09-28: migrate, one store). So
an existing library's entries become `same_as` links ON OPEN (the normal migration path, since real
libraries carry KG data), a malformed one is refused and named rather than dropped or guessed, a
second open changes nothing; and the segments naming a gazetteer place are found through the links,
by any spelling of its URI. If this regresses, a library's authority links vanish or split, a bad
id becomes an identity, or the place query misses segments.

Real identifiers (Wikidata Q90 and GeoNames 2988507 are Paris), recorded -- nothing is fetched.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.db import Database
from fichero_server.knowledge.authorities import REFUSED_KEY, authority_links_of, same_as_links
from fichero_server.models.knowledge import (
    AuthoritySnapshot, EntityMergeAudit, EntityMergeOperationType, EntityType, KnowledgeEntity,
)
from fichero_server.models.typed_links import TypedLink
from tests.unit.api.test_a_georeferencing_file_imports_as_a_pass import PARIS, _annotation, _import
from tests.unit.api.test_page_text_follows_the_file import BOOT

Q90 = "http://www.wikidata.org/entity/Q90"
GEONAMES_PARIS = "https://sws.geonames.org/2988507/"


def _paris(db) -> KnowledgeEntity:
    entity = KnowledgeEntity(canonical_name="Paris", entity_type=EntityType.location)
    db.save(entity)
    return entity


def test_linking_writes_same_as_records_several_gazetteers_no_duplicates(db, client):
    paris = _paris(db)
    for authority, identifier in (("wikidata", "Q90"), ("geonames", "2988507"), ("wikidata", "Q90")):
        db.save(AuthoritySnapshot(authority=authority, authority_id=identifier, label="Paris",
                                  source_url=f"recorded:{authority}:{identifier}"))
        response = client.post("/api/kg/entity-curation/authority/link",
                               json={"entity_id": paris.id, "authority": authority, "authority_id": identifier})
        assert response.status_code == 200, response.text
    links = same_as_links(db, paris.id)
    assert sorted(link.to_id for link in links) == [Q90, GEONAMES_PARIS]      # the repeat added nothing
    assert all(link.provenance_kind.value == "human" and link.created_by for link in links)
    assert "authority_links" not in (db.get(KnowledgeEntity, paris.id).metadata or {})


def test_a_library_with_the_earlier_dict_gains_typed_links_on_open(tmp_path: Path):
    path = tmp_path / "old.duckdb"
    first = Database(path)
    paris = KnowledgeEntity(canonical_name="Paris", entity_type=EntityType.location)
    first.save(paris)
    first.save(EntityMergeAudit(operation_type=EntityMergeOperationType.authority_link, source_entity_ids=[],
                                target_entity_id=paris.id, alias_changes={"authority_link": {
                                    "authority": "wikidata", "authority_id": "Q90"}}, created_by="historian"))
    table = first._table_name(KnowledgeEntity)
    first.close()
    # The entity as an OLDER build left it: the dict written straight into the file, so nothing of
    # this build has touched it before the open below.
    earlier = {"authority_links": [
        {"authority": "wikidata", "authority_id": "Q90"},
        {"authority": "geonames", "authority_id": "2988507"},
        {"authority": "pleiades", "authority_id": "Paris"},          # never an identifier
    ]}
    conn = duckdb.connect(str(path))
    conn.execute(f"UPDATE {table} SET metadata = ? WHERE id = ?", [json.dumps(earlier), paris.id])
    conn.close()

    second = Database(path)                                          # the migration runs on open
    try:
        links = {link.to_id: link for link in second.query(TypedLink, from_id=paris.id)}
        assert set(links) == {Q90, GEONAMES_PARIS}
        assert (links[Q90].created_by, links[Q90].provenance_kind.value) == ("historian", "human")
        assert (links[GEONAMES_PARIS].provenance_kind.value, links[GEONAMES_PARIS].note) == ("external_import", "earlier authority link")
        metadata = second.get(KnowledgeEntity, paris.id).metadata
        assert "authority_links" not in metadata
        [refused] = metadata[REFUSED_KEY]
        assert (refused["authority"], refused["authority_id"]) == ("pleiades", "Paris") and "Pleiades" in refused["reason"]
    finally:
        second.close()
    third = Database(path)
    try:
        assert len(third.query(TypedLink, from_id=paris.id)) == 2 and len(third.get(KnowledgeEntity, paris.id).metadata[REFUSED_KEY]) == 1
    finally:
        third.close()


def test_every_segment_naming_the_place_by_any_spelling_of_its_uri(db, client):
    source = _annotation(PARIS)["target"]["source"]
    paris = _paris(db)
    registry.invoke(db, "typed_link.create", {"from_kind": "entity", "from_id": paris.id, "to_kind": "uri",
                                              "to_id": Q90, "link_type": "same_as"}, BOOT)
    named = []
    for _ in range(2):                                               # two plans of Paris, one label each
        doc_id = _import(db, PARIS, (source["width"], source["height"]))
        names = registry.invoke(db, "segment.pass_create", {"document_id": doc_id, "name": "names"}, BOOT).result["id"]
        label = registry.invoke(db, "segment.create", {"document_id": doc_id, "pass_id": names, "kind": "place",
            "anchor": {"document_id": doc_id, "shapes": [{"kind": "point", "points": [[0.5, 0.5]]}]}}, BOOT).result["segment_ids"][0]
        named.append(registry.invoke(db, "typed_link.create", {"from_id": label, "to_kind": "entity", "to_id": paris.id,
                                                               "link_type": "names", "certainty": 0.8}, BOOT).result["link_id"])
    got = client.get("/api/links/naming", params={"uri": "https://www.wikidata.org/wiki/Q90"}).json()
    assert (got["uri"], got["authority"], got["entity_ids"]) == (Q90, "wikidata", [paris.id])
    assert len(got["segments"]) == 2 and {s["certainty"] for s in got["segments"]} == {0.8}

    registry.invoke(db, "typed_link.delete", {"link_id": named[0]}, BOOT)
    assert len(client.get("/api/links/naming", params={"uri": Q90}).json()["segments"]) == 1
    assert client.get("/api/links/naming", params={"uri": "Paris"}).status_code == 422
