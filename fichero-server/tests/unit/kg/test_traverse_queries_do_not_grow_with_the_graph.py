"""The traverse route reads each depth in a few queries, not two or three per node (perf-optimize, 2026-11-27).

Measured at origin/integration on a busy name with ~900 statements: 1,841 queries for one `GET /api/kg/graph/traverse/{id}`
at depth 2, 680 ms. Each queued node asked for the statements mentioning it (a claim id never is an entity, so every one of
those answers was empty) and for its links, one query each. This case holds a 60-statement graph to a flat bound.
"""
from __future__ import annotations

import perf_ratchet
import pytest

from fichero_server.models.knowledge import (
    ClaimRelationType,
    EntityType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
)

ROUTE_KEY = "queries.GET./api/kg/graph/traverse/{entity_id}"
BOUND = 12  # measured after the fix: 9 at depth 2 on this graph (187 before, about three a node)
N_CLAIMS = 60


@pytest.fixture(autouse=True)
def _no_embedding(db, monkeypatch):
    for name in ("schedule_entity_embedding", "schedule_claim_embedding", "schedule_claim_embeddings"):
        monkeypatch.setattr(db, name, lambda *a, **k: None)


def _seed(db):
    db.save(KnowledgeEntity(id="e-a", canonical_name="Ana", entity_type=EntityType.person))
    db.save_many([KnowledgeClaim(id=f"c{i}", text=f"Ana did thing {i}.", source_document_id="d", entity_ids=["e-a"]) for i in range(N_CLAIMS)])
    db.save_many([KnowledgeClaim(id=f"l{i}", text=f"Elsewhere {i}.", source_document_id="d", entity_ids=[]) for i in range(N_CLAIMS)])
    db.save_many([KnowledgeClaimLink(claim_id=f"c{i}", related_claim_id=f"l{i}", relation_type=ClaimRelationType.supports) for i in range(N_CLAIMS)])


def test_a_depth_two_traversal_issues_a_flat_number_of_queries(db, client, test_package, monkeypatch):
    from fichero_server.db.manager import db_manager

    _seed(db)
    monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")
    db_manager.close_database(test_package)  # the counter wraps a connection when it OPENS
    db_manager.get_database(test_package)
    perf_ratchet._query_session.pop(ROUTE_KEY, None)
    r = client.get("/api/kg/graph/traverse/e-a", params={"max_depth": 2})
    assert r.status_code == 200, r.text
    count = perf_ratchet._query_session.pop(ROUTE_KEY, None)
    body = r.json()
    assert {n["id"] for n in body["nodes"]} == {"e-a", *(f"c{i}" for i in range(N_CLAIMS)), *(f"l{i}" for i in range(N_CLAIMS))}
    assert body["truncated"] is False
    assert count is not None and count <= BOUND, f"{count} queries for {2 * N_CLAIMS} nodes: the traversal grows with the graph"
