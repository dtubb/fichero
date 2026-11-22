"""The neighbourhood is asked of `kg_mentions`: it reads the rows of the name and its neighbours, not the tables (#6758).

Pressed through the real route. `Database.query` and `Database.all` raise, so a read of a whole table fails the request.
"""

from __future__ import annotations

import pytest

from fichero_server.api.routes.kg import graph as graph_routes
from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity


@pytest.fixture(autouse=True)
def _no_embedding(db, monkeypatch):
    for name in ("schedule_entity_embedding", "schedule_claim_embedding", "schedule_claim_embeddings"):
        monkeypatch.setattr(db, name, lambda *a, **k: None)


def _seed(db):
    for eid, name in (("e-a", "Ana"), ("e-b", "Berta"), ("e-c", "Carla"), ("e-far", "Far"), ("e-x", "Xavier"), ("e-y", "Yola")):
        db.save(KnowledgeEntity(id=eid, canonical_name=name, entity_type=EntityType.person, aliases=[f"{name} the elder"]))
    db.save(KnowledgeClaim(id="c1", text="Ana knew Berta.", source_document_id="d", entity_ids=["e-a", "e-b"]))
    db.save(KnowledgeClaim(id="c2", text="Ana knew Berta again.", source_document_id="d", entity_ids=["e-a", "e-b"]))
    db.save(KnowledgeClaim(id="c3", text="Ana wrote to Carla.", source_document_id="d", entity_ids=["e-a"],
                           metadata={"verb": "wrote to", "object": "carla"}))
    db.save(KnowledgeClaim(id="c4", text="Ana wrote to Berta the elder.", source_document_id="d", entity_ids=["e-a"],
                           metadata={"verb": "wrote to", "object": "Berta The Elder"}))
    db.save(KnowledgeClaim(id="c5", text="Berta knew Far.", source_document_id="d", entity_ids=["e-b", "e-far"]))
    db.save(KnowledgeClaim(id="c6", text="Xavier knew Yola.", source_document_id="d", entity_ids=["e-x", "e-y"]))


def _forbid_whole_table_reads(db, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a whole table was read")

    monkeypatch.setattr(db, "query", refuse)
    monkeypatch.setattr(db, "all", refuse)


def _get(client, entity, **params):
    r = client.get(f"/api/kg/graph/neighborhood/{entity}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_one_hop_returns_the_names_statements_without_reading_a_table(client, db, monkeypatch):
    _seed(db)
    _forbid_whole_table_reads(db, monkeypatch)
    body = _get(client, "e-a")
    assert sorted(n["id"] for n in body["neighbors"]) == ["e-b", "e-c"]
    assert sorted(e["claim_id"] for e in body["edges"]) == ["c1", "c2", "c3", "c4"]
    assert {e["target_id"] for e in body["edges"]} == {"e-b", "e-c"}
    assert body["truncated"] is False


def test_two_hops_reach_the_next_name_and_never_an_unconnected_one(client, db, monkeypatch):
    _seed(db)
    _forbid_whole_table_reads(db, monkeypatch)
    body = _get(client, "e-a", hops=2)
    assert {n["id"]: n["hop"] for n in body["neighbors"]} == {"e-b": 1, "e-c": 1, "e-far": 2}


def test_a_name_resolves_by_canonical_name_or_alias_case_insensitively(client, db, monkeypatch):
    _seed(db)
    _forbid_whole_table_reads(db, monkeypatch)
    by_claim = {e["claim_id"]: e for e in _get(client, "e-a")["edges"]}
    assert by_claim["c3"]["target_id"] == "e-c"
    assert by_claim["c4"]["target_id"] == "e-b"


def test_degree_rank_orders_by_statements_per_name_in_the_link_table(client, db, monkeypatch):
    _seed(db)
    _forbid_whole_table_reads(db, monkeypatch)
    body = _get(client, "e-a", rank="degree", limit=1)
    assert [n["id"] for n in body["neighbors"]] == ["e-b"]
    assert body["truncated"] is True


def test_a_walk_over_the_row_limit_says_it_was_cut(client, db, monkeypatch):
    _seed(db)
    monkeypatch.setattr(graph_routes, "NEIGHBOURHOOD_CLAIM_LIMIT", 2)
    body = _get(client, "e-a")
    assert len(body["edges"]) <= 2
    assert body["truncated"] is True
