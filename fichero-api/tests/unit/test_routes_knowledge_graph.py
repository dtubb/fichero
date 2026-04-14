"""Tests for knowledge graph routes.

The knowledge graph module provides advanced entity/claim management:
merge, split, alias, undo/redo mutations, filtered queries, and semantic
embedding. Routes live at /api/knowledge-graph/... (router has no prefix,
mounted at "/api/knowledge-graph").

Tests focus on the CRUD and query endpoints that operate directly on
the in-memory DB via the test client fixture.
"""

import pytest

from fichero.knowledge_models import (
    KnowledgeEntity,
    KnowledgeClaim,
    ClaimType,
    EpistemicStatus,
    ClaimCurationState,
    SourceType,
    EntityType,
)


BASE = "/api/knowledge-graph"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(eid: str = "ent-1", name: str = "Napoléon Bonaparte") -> KnowledgeEntity:
    return KnowledgeEntity(id=eid, canonical_name=name)


def _make_claim(cid: str = "c-1") -> KnowledgeClaim:
    return KnowledgeClaim(
        id=cid,
        text="A historical claim.",
        source_document_id="doc-1",
        source_ids=["doc-1"],
        claim_type=ClaimType.fact,
        epistemic_status=EpistemicStatus.tentative,
        curation_state=ClaimCurationState.unreviewed,
        confidence=0.7,
    )


# ---------------------------------------------------------------------------
# GET /api/knowledge-graph/entities
# ---------------------------------------------------------------------------


class TestListEntities:
    def test_empty_list(self, client):
        r = client.get(f"{BASE}/entities")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_entities(self, client, db):
        db.save(_make_entity("e-1", "Napoleon"))
        db.save(_make_entity("e-2", "Wellington"))

        r = client.get(f"{BASE}/entities")
        assert r.status_code == 200
        assert len(r.json()) == 2


# ---------------------------------------------------------------------------
# POST /api/knowledge-graph/entities
# ---------------------------------------------------------------------------


class TestCreateEntity:
    def test_create_entity(self, client):
        r = client.post(f"{BASE}/entities", json={
            "canonical_name": "Aristotle",
            "entity_type": "person",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["canonical_name"] == "Aristotle"
        assert "id" in data


# ---------------------------------------------------------------------------
# GET /api/knowledge-graph/entities/alias-map
# ---------------------------------------------------------------------------


class TestEntityAliasMap:
    def test_empty_alias_map(self, client):
        r = client.get(f"{BASE}/entities/alias-map")
        assert r.status_code == 200
        data = r.json()
        assert "entries" in data

    def test_alias_map_with_entities(self, client, db):
        entity = KnowledgeEntity(
            id="e-alias",
            canonical_name="Napoleon Bonaparte",
            aliases=["Napoleon", "The Emperor"],
        )
        db.save(entity)

        r = client.get(f"{BASE}/entities/alias-map")
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert len(entries) > 0


# ---------------------------------------------------------------------------
# GET /api/knowledge-graph/entities/resolve/{value}
# ---------------------------------------------------------------------------


class TestEntityResolution:
    def test_resolve_known_entity(self, client, db):
        entity = KnowledgeEntity(
            id="e-res",
            canonical_name="Socrates",
            aliases=["The Philosopher"],
        )
        db.save(entity)

        r = client.get(f"{BASE}/entities/resolve/Socrates")
        assert r.status_code == 200
        data = r.json()
        assert data["resolved"] is True
        assert data["entity_id"] == "e-res"

    def test_resolve_unknown_entity(self, client):
        r = client.get(f"{BASE}/entities/resolve/UnknownEntity123")
        assert r.status_code == 200
        data = r.json()
        assert data["resolved"] is False


# ---------------------------------------------------------------------------
# POST /api/knowledge-graph/claims
# ---------------------------------------------------------------------------


class TestCreateClaim:
    def test_create_claim(self, client, db):
        from fichero.models import Document
        db.save(Document(id="src-doc", name="Source Document"))

        r = client.post(f"{BASE}/claims", json={
            "text": "Aristotle was a student of Plato.",
            "source_document_id": "src-doc",
            "claim_type": "fact",
            "epistemic_status": "tentative",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["text"] == "Aristotle was a student of Plato."
        assert "id" in data


# ---------------------------------------------------------------------------
# GET /api/knowledge-graph/claims/filtered
# ---------------------------------------------------------------------------


class TestFilteredClaims:
    def test_empty_filtered_claims(self, client):
        r = client.get(f"{BASE}/claims/filtered")
        assert r.status_code == 200
        assert r.json() == []

    def test_filter_by_curation_state(self, client, db):
        db.save(_make_claim("c-unrev"))

        r = client.get(f"{BASE}/claims/filtered?curation_state=unreviewed")
        assert r.status_code == 200
        assert len(r.json()) >= 1


# ---------------------------------------------------------------------------
# GET /api/knowledge-graph/knowledge-mutations
# ---------------------------------------------------------------------------


class TestKnowledgeMutations:
    def test_returns_empty_mutations(self, client):
        r = client.get(f"{BASE}/knowledge-mutations")
        assert r.status_code == 200
        assert r.json() == []
