"""The neighbourhood edge carries its statement's when and where (#6773).

Spec: docs/contributor_manual/specs/kg/kg-rendering.md, `kg.render.when-is-on-the-statement`
and `kg.render.where-is-on-the-statement`. Pressed through the real route, the one the graph reads.
"""

from __future__ import annotations

from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity


def _seed(db):
    with db.defer_embeddings():
        db.save(KnowledgeEntity(id="e-pedro", canonical_name="Pedro", entity_type=EntityType.person))
        db.save(KnowledgeEntity(id="e-ana", canonical_name="Ana", entity_type=EntityType.person))
        db.save(KnowledgeEntity(id="e-quito", canonical_name="Quito", entity_type=EntityType.location))
        db.save(KnowledgeClaim(
            id="c-dated", text="Pedro married Ana in Quito in 1820.", source_document_id="doc-1",
            entity_ids=["e-pedro"], metadata={"verb": "married", "object": "Ana"},
            time_start="1820-01-01", time_end="1820-12-31", time_precision="year", claim_location="Quito",
        ))
        db.save(KnowledgeClaim(
            id="c-bare", text="Pedro wrote to Ana.", source_document_id="doc-1",
            entity_ids=["e-pedro"], metadata={"verb": "wrote to", "object": "Ana"},
        ))
        db.save(KnowledgeClaim(
            id="c-unknown-place", text="Pedro met Ana at the mill.", source_document_id="doc-1",
            entity_ids=["e-pedro"], metadata={"verb": "met", "object": "Ana"}, claim_location="the mill",
        ))


def _edges_by_claim(client):
    r = client.get("/api/kg/graph/neighborhood/e-pedro")
    assert r.status_code == 200, r.text
    return {e["claim_id"]: e for e in r.json()["edges"]}


def test_an_edge_carries_its_statements_when_and_where_and_links_a_known_place(client, db):
    _seed(db)
    edge = _edges_by_claim(client)["c-dated"]
    assert (edge["time_start"], edge["time_end"], edge["time_precision"]) == ("1820-01-01", "1820-12-31", "year")
    assert edge["place"] == "Quito"
    assert edge["place_entity_id"] == "e-quito"


def test_an_edge_without_a_when_or_where_carries_none(client, db):
    _seed(db)
    edge = _edges_by_claim(client)["c-bare"]
    assert [edge[k] for k in ("time_start", "time_end", "time_precision", "place", "place_entity_id")] == [None] * 5


def test_a_place_that_is_not_a_known_name_has_no_entity_link(client, db):
    _seed(db)
    edge = _edges_by_claim(client)["c-unknown-place"]
    assert edge["place"] == "the mill"
    assert edge["place_entity_id"] is None
