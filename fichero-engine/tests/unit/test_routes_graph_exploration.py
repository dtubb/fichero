"""Tests for graph exploration routes.

Graph exploration traverses the knowledge graph — finding paths between
entities, computing subgraphs, and returning graph metrics. Routes live at
/api/graph/... (router prefix="/graph" mounted at "/api").
"""

import pytest

from fichero.knowledge_models import (
    KnowledgeClaim,
    KnowledgeEntity,
    ClaimType,
    EpistemicStatus,
    ClaimCurationState,
    SourceType,
    EntityType,
)


BASE = "/api/graph"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(eid: str = "ent-1", name: str = "Napoleon") -> KnowledgeEntity:
    return KnowledgeEntity(id=eid, canonical_name=name)


def _make_claim(cid: str = "c-1", entity_ids: list[str] | None = None) -> KnowledgeClaim:
    return KnowledgeClaim(
        id=cid,
        text="A historical fact.",
        source_document_id="doc-1",
        source_ids=["doc-1"],
        claim_type=ClaimType.fact,
        epistemic_status=EpistemicStatus.tentative,
        curation_state=ClaimCurationState.unreviewed,
        confidence=0.7,
        entity_ids=entity_ids or [],
    )


# ---------------------------------------------------------------------------
# GET /api/graph/metrics
# ---------------------------------------------------------------------------


class TestGraphMetrics:
    def test_empty_graph_metrics(self, client):
        r = client.get(f"{BASE}/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "metrics" in data
        assert data["metrics"]["entity_count"] == 0
        assert data["metrics"]["claim_count"] == 0

    def test_metrics_with_data(self, client, db):
        db.save(_make_entity("e-1", "Napoleon"))
        db.save(_make_entity("e-2", "Waterloo"))
        db.save(_make_claim("c-1", ["e-1", "e-2"]))

        r = client.get(f"{BASE}/metrics")
        assert r.status_code == 200
        metrics = r.json()["metrics"]
        assert metrics["entity_count"] == 2
        assert metrics["claim_count"] == 1


# ---------------------------------------------------------------------------
# GET /api/graph/paths/{entity_id1}/{entity_id2}
# ---------------------------------------------------------------------------


class TestEntityPaths:
    def test_missing_entity1_returns_404(self, client):
        r = client.get(f"{BASE}/paths/no-such/ent-2")
        assert r.status_code == 404

    def test_missing_entity2_returns_404(self, client, db):
        db.save(_make_entity("e-src", "Source"))
        r = client.get(f"{BASE}/paths/e-src/no-such")
        assert r.status_code == 404

    def test_finds_direct_path(self, client, db):
        db.save(_make_entity("e-a", "Entity A"))
        db.save(_make_entity("e-b", "Entity B"))
        db.save(_make_claim("c-ab", ["e-a", "e-b"]))

        r = client.get(f"{BASE}/paths/e-a/e-b")
        assert r.status_code == 200
        data = r.json()
        assert "paths" in data

    def test_no_paths_between_unconnected_entities(self, client, db):
        db.save(_make_entity("e-x", "X"))
        db.save(_make_entity("e-y", "Y"))

        r = client.get(f"{BASE}/paths/e-x/e-y")
        assert r.status_code == 200
        assert r.json()["paths"] == []


# ---------------------------------------------------------------------------
# GET /api/graph/traverse/{entity_id}
# ---------------------------------------------------------------------------


class TestGraphTraverse:
    def test_missing_entity_returns_404(self, client):
        r = client.get(f"{BASE}/traverse/no-such")
        assert r.status_code == 404

    def test_traverse_returns_structure(self, client, db):
        db.save(_make_entity("e-t", "Traversable"))

        r = client.get(f"{BASE}/traverse/e-t")
        assert r.status_code == 200
        data = r.json()
        assert data["entity_id"] == "e-t"
        assert "nodes" in data
        assert "edges" in data
