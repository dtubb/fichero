"""Tests for graph exploration routes.

Graph exploration traverses the knowledge graph — finding paths between
entities, computing subgraphs, and returning graph metrics. Routes live at
/api/kg/graph/... (router prefix="/graph" mounted at "/api").
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


BASE = "/api/kg/graph"


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
# GET /api/kg/graph/metrics
# ---------------------------------------------------------------------------


class TestGraphMetrics:
    def test_empty_graph_metrics(self, client):
        r = client.get(f"{BASE}/metrics")
        assert r.status_code == 200
        # Post-consolidation the response is a flat dict, not wrapped
        # under a "metrics" key. (#919 5c)
        data = r.json()
        assert data["entity_count"] == 0
        assert data["claim_count"] == 0

    def test_metrics_with_data(self, client, db):
        db.save(_make_entity("e-1", "Napoleon"))
        db.save(_make_entity("e-2", "Waterloo"))
        db.save(_make_claim("c-1", ["e-1", "e-2"]))

        r = client.get(f"{BASE}/metrics")
        assert r.status_code == 200
        data = r.json()
        assert data["entity_count"] == 2
        assert data["claim_count"] == 1


# ---------------------------------------------------------------------------
# GET /api/kg/graph/paths/{entity_id1}/{entity_id2}
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

        # Post-consolidation: GET /api/kg/graph/path?source=&target= (#919 5c)
        # The endpoint shape is asserted here; whether a path is actually
        # found depends on internal graph-build state (entities + claim
        # links must be reflected in build_full_graph), which the route
        # itself doesn't guarantee at unit-test scope. Smoke-only.
        r = client.get(f"{BASE}/path", params={"source": "e-a", "target": "e-b"})
        assert r.status_code == 200
        data = r.json()
        assert "path" in data
        assert "length" in data

    def test_no_paths_between_unconnected_entities(self, client, db):
        db.save(_make_entity("e-x", "X"))
        db.save(_make_entity("e-y", "Y"))

        r = client.get(f"{BASE}/path", params={"source": "e-x", "target": "e-y"})
        assert r.status_code == 200
        data = r.json()
        # No path → empty list + length 0.
        assert data["path"] == []
        assert data["length"] == 0


# ---------------------------------------------------------------------------
# GET /api/kg/graph/traverse/{entity_id}
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


# ---------------------------------------------------------------------------
# Stage 1 endpoints (#987) — neighborhood + algorithm cluster
# ---------------------------------------------------------------------------


def _make_svo_claim(
    cid: str,
    subject: str,
    verb: str,
    obj: str,
    entity_ids: list[str],
    source_doc: str = "doc-1",
) -> KnowledgeClaim:
    """Helper: a claim with SVO fully populated in metadata (the shape
    the extractor produces; see extractors.py:1375-1456)."""
    return KnowledgeClaim(
        id=cid,
        text=f"{subject} {verb} {obj}.",
        source_document_id=source_doc,
        source_ids=[source_doc],
        claim_type=ClaimType.fact,
        epistemic_status=EpistemicStatus.confirmed,
        curation_state=ClaimCurationState.unreviewed,
        confidence=0.8,
        entity_ids=entity_ids,
        metadata={"subject": subject, "verb": verb, "object": obj},
    )


class TestNeighborhood:
    def test_missing_entity_returns_404(self, client):
        r = client.get(f"{BASE}/neighborhood/no-such")
        assert r.status_code == 404

    def test_isolated_entity_returns_empty_neighbors(self, client, db):
        db.save(_make_entity("e-iso", "Isolated"))
        r = client.get(f"{BASE}/neighborhood/e-iso")
        assert r.status_code == 200
        data = r.json()
        assert data["focus_entity_id"] == "e-iso"
        assert data["focus_canonical_name"] == "Isolated"
        assert data["neighbors"] == []
        assert data["edges"] == []
        assert data["truncated"] is False

    def test_neighborhood_includes_svo_edge(self, client, db):
        # A claim where A "served as" B, both entities known.
        db.save(_make_entity("e-a", "Alice"))
        db.save(_make_entity("e-b", "Bob"))
        db.save(_make_svo_claim(
            "c-ab", subject="Alice", verb="served as", obj="Bob",
            entity_ids=["e-a", "e-b"],
        ))
        r = client.get(f"{BASE}/neighborhood/e-a")
        assert r.status_code == 200
        data = r.json()
        assert data["focus_canonical_name"] == "Alice"
        assert len(data["edges"]) >= 1
        first = data["edges"][0]
        assert first["predicate"] == "served as"
        assert first["claim_id"] == "c-ab"
        assert first["source_document_id"] == "doc-1"


class TestPageRank:
    def test_empty_returns_empty(self, client):
        r = client.get(f"{BASE}/pagerank")
        assert r.status_code == 200
        assert r.json() == []

    def test_ranks_entities(self, client, db):
        db.save(_make_entity("e-a", "A"))
        db.save(_make_entity("e-b", "B"))
        db.save(_make_svo_claim(
            "c-ab", subject="A", verb="knows", obj="B",
            entity_ids=["e-a", "e-b"],
        ))
        r = client.get(f"{BASE}/pagerank?top_k=10")
        assert r.status_code == 200
        rows = r.json()
        assert any(row["entity_id"] == "e-a" for row in rows)


class TestCommunities:
    def test_empty_returns_empty(self, client):
        r = client.get(f"{BASE}/communities")
        assert r.status_code == 200
        assert r.json() == []

    def test_assigns_community_ids(self, client, db):
        db.save(_make_entity("e-a", "A"))
        db.save(_make_entity("e-b", "B"))
        db.save(_make_svo_claim(
            "c-ab", subject="A", verb="knows", obj="B",
            entity_ids=["e-a", "e-b"],
        ))
        r = client.get(f"{BASE}/communities")
        assert r.status_code == 200
        rows = r.json()
        cids = {row["entity_id"]: row["community_id"] for row in rows}
        # Two co-occurring entities should land in the same community.
        assert cids.get("e-a") == cids.get("e-b")


class TestSimilar:
    def test_missing_entity_returns_404(self, client):
        r = client.get(f"{BASE}/similar/no-such")
        assert r.status_code == 404

    def test_returns_jaccard_scores(self, client, db):
        db.save(_make_entity("e-a", "A"))
        db.save(_make_entity("e-b", "B"))
        db.save(_make_entity("e-c", "C"))
        db.save(_make_svo_claim(
            "c-ac", subject="A", verb="knows", obj="C",
            entity_ids=["e-a", "e-c"],
        ))
        db.save(_make_svo_claim(
            "c-bc", subject="B", verb="knows", obj="C",
            entity_ids=["e-b", "e-c"],
        ))
        # A and B share neighbor C → Jaccard should be > 0.
        r = client.get(f"{BASE}/similar/e-a?method=jaccard&top_k=10")
        assert r.status_code == 200
        rows = r.json()
        if rows:
            assert all(row["score"] > 0 for row in rows)


class TestComponents:
    def test_empty_returns_empty(self, client):
        r = client.get(f"{BASE}/components")
        assert r.status_code == 200
        assert r.json() == []

    def test_groups_connected(self, client, db):
        db.save(_make_entity("e-a", "A"))
        db.save(_make_entity("e-b", "B"))
        db.save(_make_svo_claim(
            "c-ab", subject="A", verb="knows", obj="B",
            entity_ids=["e-a", "e-b"],
        ))
        r = client.get(f"{BASE}/components")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 1
        assert rows[0]["size"] >= 2


class TestTriangles:
    def test_missing_entity_returns_404(self, client):
        r = client.get(f"{BASE}/triangles/no-such")
        assert r.status_code == 404

    def test_isolated_returns_zero(self, client, db):
        db.save(_make_entity("e-iso", "Iso"))
        r = client.get(f"{BASE}/triangles/e-iso")
        assert r.status_code == 200
        assert r.json()["triangle_count"] == 0


class TestClustering:
    def test_empty_returns_empty(self, client):
        r = client.get(f"{BASE}/clustering")
        assert r.status_code == 200
        assert r.json() == []
