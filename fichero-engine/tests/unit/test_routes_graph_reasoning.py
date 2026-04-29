"""Tests for graph reasoning routes.

Graph reasoning uses NetworkX for community detection, centrality analysis,
and other structural analysis of the knowledge graph. Routes use full
/api/graph/... paths (router mounted at root "").
"""

import pytest
from unittest.mock import MagicMock, patch


BASE = "/api/graph/networkx"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_reasoner(available: bool = True, enabled: bool = True) -> MagicMock:
    reasoner = MagicMock()
    reasoner.enabled = enabled
    reasoner.is_available.return_value = available
    return reasoner


# ---------------------------------------------------------------------------
# GET /api/graph/networkx/status
# ---------------------------------------------------------------------------


class TestNetworkxStatus:
    def test_returns_status_when_available(self, client):
        reasoner = _make_reasoner(available=True)
        with patch("fichero.api.routes.graph_reasoning.get_reasoner", return_value=reasoner):
            r = client.get(f"{BASE}/status")
        assert r.status_code == 200
        data = r.json()
        assert "enabled" in data
        assert "available" in data
        assert "message" in data

    def test_returns_unavailable_status(self, client):
        reasoner = _make_reasoner(available=False)
        with patch("fichero.api.routes.graph_reasoning.get_reasoner", return_value=reasoner):
            r = client.get(f"{BASE}/status")
        assert r.status_code == 200
        assert r.json()["available"] is False


# ---------------------------------------------------------------------------
# GET /api/graph/networkx/metrics
# ---------------------------------------------------------------------------


class TestNetworkxMetrics:
    def test_returns_unavailable_when_networkx_missing(self, client):
        reasoner = _make_reasoner(available=False)
        with patch("fichero.api.routes.graph_reasoning.get_reasoner", return_value=reasoner):
            r = client.get(f"{BASE}/metrics")
        assert r.status_code == 200
        data = r.json()
        assert data["networkx_available"] is False

    def test_returns_metrics_when_available(self, client):
        from fichero.graph_reasoning import GraphMetrics
        reasoner = _make_reasoner(available=True)
        mock_metrics = GraphMetrics(
            node_count=5,
            edge_count=8,
            density=0.4,
            clustering_coefficient=0.3,
            connected_components=1,
            largest_component_size=5,
        )
        reasoner.get_graph_metrics.return_value = mock_metrics

        with patch("fichero.api.routes.graph_reasoning.get_reasoner", return_value=reasoner), \
             patch("fichero.api.routes.graph_reasoning._load_graph_data", return_value=([], [], [])):
            r = client.get(f"{BASE}/metrics")
        assert r.status_code == 200
        assert r.json()["networkx_available"] is True


# ---------------------------------------------------------------------------
# GET /api/graph/networkx/algorithms
# ---------------------------------------------------------------------------


class TestListAlgorithms:
    def test_returns_algorithms(self, client):
        reasoner = _make_reasoner()
        reasoner.get_available_algorithms.return_value = {
            "community": ["louvain", "girvan_newman"],
            "centrality": ["degree", "betweenness"],
        }
        with patch("fichero.api.routes.graph_reasoning.get_reasoner", return_value=reasoner):
            r = client.get(f"{BASE}/algorithms")
        assert r.status_code == 200
