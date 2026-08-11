"""Coverage for the graph analytics route adapters."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import networkx as nx
import pytest
from fastapi import HTTPException

from fichero_server.api.routes import kg_graph as routes
from fichero_server.knowledge.graph import CentralityScore


def test_centrality_maps_scores_and_filters_type(monkeypatch):
    graph = nx.MultiDiGraph()
    calls = []
    monkeypatch.setattr("fichero_server.knowledge.graph.build_full_cooccurrence", lambda db: graph)
    monkeypatch.setattr(
        "fichero_server.knowledge.graph.centrality",
        lambda value, *, top_k, only_type: calls.append((value, top_k, only_type)) or [
            CentralityScore("entity-1", "Alice", 3, 0.2, 0.4)
        ],
    )

    response = asyncio.run(routes.centrality(top_k=5, entity_type="person", db=object()))

    assert response.count == 1
    assert response.items[0].entity_id == "entity-1"
    assert calls == [(graph, 5, "person")]


def test_cooccurrence_sorts_neighbors_and_rejects_unknown_entity(monkeypatch):
    graph = nx.Graph()
    graph.add_node("entity-1")
    graph.add_node("entity-2", canonical_name="Bob", entity_type="person")
    graph.add_node("entity-3", canonical_name="Carol", entity_type="place")
    graph.add_edge("entity-1", "entity-2", weight=1)
    graph.add_edge("entity-1", "entity-3", weight=3)
    monkeypatch.setattr("fichero_server.knowledge.graph.build_full_cooccurrence", lambda _db: graph)

    response = asyncio.run(routes.cooccurrence_neighbours("entity-1", db=object()))

    assert [row.entity_id for row in response.items] == ["entity-3", "entity-2"]
    assert [row.weight for row in response.items] == [3, 1]

    with pytest.raises(HTTPException) as caught:
        asyncio.run(routes.cooccurrence_neighbours("missing", db=object()))
    assert caught.value.status_code == 404


def test_shortest_path_reports_edge_length(monkeypatch):
    graph = nx.MultiDiGraph()
    monkeypatch.setattr("fichero_server.knowledge.graph.build_full_graph", lambda db: graph)
    monkeypatch.setattr(
        "fichero_server.knowledge.graph.shortest_path_entities",
        lambda value, source, target: [source, "middle", target],
    )

    response = asyncio.run(routes.shortest_path(source="a", target="b", db=object()))

    assert response.model_dump() == {
        "source_id": "a",
        "target_id": "b",
        "path": ["a", "middle", "b"],
        "length": 2,
    }


def test_metrics_counts_rows_and_claim_entity_links():
    class DB:
        def query(self, model):
            name = model.__name__
            if name == "KnowledgeEntity":
                return [SimpleNamespace(id="entity-1")]
            if name == "KnowledgeClaim":
                return [SimpleNamespace(entity_ids=["entity-1", "entity-2"])]
            return []

    response = asyncio.run(routes.metrics(db=DB()))

    assert response.entity_count == 1
    assert response.claim_count == 1
    assert response.avg_claims_per_entity == 2.0
    assert response.avg_entities_per_claim == 2.0
