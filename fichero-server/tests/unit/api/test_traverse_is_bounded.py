"""The traverse route reads the rows of the name it stands on and stops at TRAVERSE_NODE_LIMIT nodes (#6758)."""

from __future__ import annotations

import pytest

from fichero_server.api.routes.kg import graph as graph_routes
from fichero_server.models.knowledge import (
    ClaimRelationType,
    EntityType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
)


@pytest.fixture(autouse=True)
def _no_embedding(db, monkeypatch):
    for name in ("schedule_entity_embedding", "schedule_claim_embedding", "schedule_claim_embeddings"):
        monkeypatch.setattr(db, name, lambda *a, **k: None)


def _seed(db, count=6):
    db.save(KnowledgeEntity(id="e-a", canonical_name="Ana", entity_type=EntityType.person))
    for i in range(count):
        db.save(KnowledgeClaim(id=f"c{i}", text=f"Ana did thing {i}.", source_document_id="d", entity_ids=["e-a"]))
    db.save(KnowledgeClaim(id="c-linked", text="Elsewhere.", source_document_id="d", entity_ids=[]))
    db.save(KnowledgeClaimLink(claim_id="c0", related_claim_id="c-linked", relation_type=ClaimRelationType.supports))


def _get(client, **params):
    r = client.get("/api/kg/graph/traverse/e-a", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_traverse_reaches_claims_and_linked_claims_without_reading_a_table(client, db, monkeypatch):
    _seed(db)

    def refuse(*a, **k):
        raise AssertionError("a whole table was read")

    monkeypatch.setattr(db, "query", refuse)
    monkeypatch.setattr(db, "all", refuse)
    body = _get(client)
    assert {n["id"] for n in body["nodes"]} == {"e-a", *(f"c{i}" for i in range(6)), "c-linked"}
    assert body["truncated"] is False


def test_a_traversal_over_the_node_limit_stops_and_says_it_was_cut(client, db, monkeypatch):
    _seed(db)
    monkeypatch.setattr(graph_routes, "TRAVERSE_NODE_LIMIT", 4)
    body = _get(client)
    assert len(body["nodes"]) <= 4
    assert body["truncated"] is True
