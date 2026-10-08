"""`source.extract.search-reads-the-record` (#5597): a scoped search reads the entities.

`people:` / `places:` used to read the `people` artifact's JSON, so a name corrected in the
graph was still found under its old spelling and a merged entity under both. Through the
search route the app and `fichero_search` use (POST /api/search), with the correction,
merge and rejection made through the KG routes a person uses.
"""

from __future__ import annotations

from fichero_server.models import Artifact, Document
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import EntityType, KnowledgeEntity, SourceSupport


def _doc(db, doc_id: str, text: str) -> Document:
    doc = Document(id=doc_id, name=f"{doc_id}.txt", page_content=text)
    db.save(doc)
    return doc


def _person(db, name: str, doc_id: str, *, segment_id: str | None = None,
            entity_type: EntityType = EntityType.person) -> KnowledgeEntity:
    anchor = SourceAnchor(document_id=doc_id, segment_id=segment_id) if segment_id else None
    entity = KnowledgeEntity(
        canonical_name=name,
        entity_type=entity_type,
        source_document_ids=[doc_id],
        source_supports=[SourceSupport(source_document_id=doc_id, source_excerpt=name,
                                       source_anchor=anchor)],
    )
    db.save(entity)
    return entity


def _people_artifact(db, doc_id: str, name: str) -> None:
    """The artifact copy extraction also writes -- the search must no longer read it."""
    db.save(Artifact(document_id=doc_id, artifact_type="people", content="",
                     data={"items": [{"name": name}]}))


def _search(client, query: str) -> list[dict]:
    response = client.post("/api/search", json={"query": query, "min_score": 0.0})
    assert response.status_code == 200, response.text
    return response.json()["results"]


def test_a_corrected_name_is_found_by_its_new_spelling_not_its_old(client, db):
    _doc(db, "doc-asprilla", "compareció Don Joseph Antonio Asprila, vezino")
    entity = _person(db, "Joseph Antonio Asprila", "doc-asprilla", segment_id="seg-line-3")
    _people_artifact(db, "doc-asprilla", "Joseph Antonio Asprila")

    renamed = client.patch(f"/api/entities/{entity.id}",
                           json={"canonical_name": "Joseph Antonio Asprilla"})
    assert renamed.status_code == 200, renamed.text

    hits = _search(client, "people:Asprilla")
    assert [hit["document_id"] for hit in hits] == ["doc-asprilla"]
    assert hits[0]["metadata"]["entity_id"] == entity.id
    assert hits[0]["metadata"]["entity_name"] == "Joseph Antonio Asprilla"
    assert entity.id in hits[0]["kg_entity_ids"]
    # The old spelling is still in the artifact copy; the record no longer has it.
    assert _search(client, "people:Asprila") == []


def test_two_merged_entities_are_one_hit_reaching_both_documents(client, db):
    _doc(db, "doc-a", "Juan de Mosquera firmó")
    _doc(db, "doc-b", "Joan Mosquera, alcalde")
    survivor = _person(db, "Juan de Mosquera", "doc-a")
    absorbed = _person(db, "Joan Mosquera", "doc-b")

    merged = client.post("/api/kg/entity-curation/merge", json={
        "absorbing_entity_id": survivor.id, "absorbed_entity_ids": [absorbed.id]})
    assert merged.status_code == 200, merged.text

    for query in ("people:Mosquera", "people:Joan"):
        hits = _search(client, query)
        assert sorted(hit["document_id"] for hit in hits) == ["doc-a", "doc-b"], query
        # One entity: every hit names the survivor, never the merged-away one.
        assert {hit["metadata"]["entity_id"] for hit in hits} == {survivor.id}, query


def test_an_entity_a_person_rejected_is_not_found(client, db):
    _doc(db, "doc-c", "ordenamiento real")
    entity = _person(db, "Ordenamiento Real", "doc-c")
    _people_artifact(db, "doc-c", "Ordenamiento Real")
    assert [hit["document_id"] for hit in _search(client, "people:Ordenamiento")] == ["doc-c"]

    rejected = client.patch("/api/kg/entities/batch-curation",
                            json={"entity_ids": [entity.id], "curation_state": "rejected"})
    assert rejected.status_code == 200, rejected.text
    assert _search(client, "people:Ordenamiento") == []


def test_results_carry_the_documents_and_lines_where_the_name_is_written(client, db):
    _doc(db, "doc-tied", "Quibdó, a 23 de Julio")
    _doc(db, "doc-untied", "en Quibdó")
    place = _person(db, "Quibdó", "doc-tied", segment_id="seg-7", entity_type=EntityType.location)
    place.source_supports = [*place.source_supports,
                             SourceSupport(source_document_id="doc-untied", source_excerpt="Quibdó")]
    db.save(place)

    hits = {hit["document_id"]: hit for hit in _search(client, "places:quibdo")}  # accent-blind
    assert set(hits) == {"doc-tied", "doc-untied"}
    assert hits["doc-tied"]["metadata"]["segment_ids"] == ["seg-7"]
    assert hits["doc-untied"]["metadata"]["segment_ids"] == []
    assert hits["doc-tied"]["metadata"]["match_source"] == "entity"
    # The scope is the entity's type: a place is not a person.
    assert _search(client, "people:Quibdo") == []


def test_a_name_only_in_the_artifact_copy_is_not_found(client, db):
    _doc(db, "doc-d", "sin nombres")
    _people_artifact(db, "doc-d", "Rosalia Hortiga")
    assert _search(client, "people:Hortiga") == []
