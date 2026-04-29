"""Tests for knowledge entity routes.

KnowledgeEntity is the central node in the knowledge graph — named things
(people, places, concepts) that claims refer to. Tests cover CRUD, alias
management, and entity resolution. Route ordering fix required: static paths
/alias-map and /resolve/{v} must be registered before /{entity_id}.
"""

import pytest
from fichero.knowledge_models import EntityType, KnowledgeEntity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(db, name: str = "Alice", entity_type: EntityType = EntityType.person) -> KnowledgeEntity:
    from datetime import datetime
    entity = KnowledgeEntity(
        canonical_name=name,
        entity_type=entity_type,
        aliases=[],
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.save(entity)
    return entity


# ---------------------------------------------------------------------------
# GET /api/entities
# ---------------------------------------------------------------------------


class TestListEntities:
    def test_empty_list(self, client):
        r = client.get("/api/entities")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_saved_entities(self, client, db):
        _make_entity(db, "Alice")
        _make_entity(db, "Bob")
        r = client.get("/api/entities")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_filter_by_type(self, client, db):
        _make_entity(db, "Alice", EntityType.person)
        _make_entity(db, "London", EntityType.location)
        r = client.get("/api/entities?entity_type=person")
        assert r.status_code == 200
        names = [e["canonical_name"] for e in r.json()]
        assert "Alice" in names
        assert "London" not in names

    def test_search_by_name(self, client, db):
        _make_entity(db, "Alice Smith")
        _make_entity(db, "Bob Jones")
        r = client.get("/api/entities?q=alice")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["canonical_name"] == "Alice Smith"


# ---------------------------------------------------------------------------
# POST /api/entities (upsert)
# ---------------------------------------------------------------------------


class TestUpsertEntity:
    def test_create_entity(self, client):
        r = client.post("/api/entities", json={
            "canonical_name": "Marie Curie",
            "entity_type": "person",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["canonical_name"] == "Marie Curie"
        assert "id" in data

    def test_update_existing_entity(self, client, db):
        entity = _make_entity(db, "Old Name")
        r = client.post("/api/entities", json={
            "id": entity.id,
            "canonical_name": "New Name",
            "entity_type": "person",
        })
        assert r.status_code == 200
        assert r.json()["canonical_name"] == "New Name"
        assert r.json()["id"] == entity.id


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}
# ---------------------------------------------------------------------------


class TestGetEntity:
    def test_get_existing(self, client, db):
        entity = _make_entity(db, "Alice")
        r = client.get(f"/api/entities/{entity.id}")
        assert r.status_code == 200
        assert r.json()["id"] == entity.id

    def test_get_missing_returns_404(self, client):
        r = client.get("/api/entities/no-such-entity")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/entities/{entity_id}/aliases
# ---------------------------------------------------------------------------


class TestAddAliases:
    def test_add_aliases(self, client, db):
        entity = _make_entity(db, "Alice")
        r = client.post(f"/api/entities/{entity.id}/aliases", json={"aliases": ["Al", "Ally"]})
        assert r.status_code == 200
        data = r.json()
        assert "Al" in data["aliases"]
        assert "Ally" in data["aliases"]

    def test_add_aliases_missing_entity(self, client):
        r = client.post("/api/entities/no-such-id/aliases", json={"aliases": ["alias"]})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/entities/alias-map
# ---------------------------------------------------------------------------


class TestGetAliasMap:
    def test_returns_alias_map(self, client, db):
        _make_entity(db, "Alice")
        r = client.get("/api/entities/alias-map")
        assert r.status_code == 200
        data = r.json()
        assert "entries" in data
        assert isinstance(data["entries"], list)


# ---------------------------------------------------------------------------
# GET /api/entities/resolve/{value}
# ---------------------------------------------------------------------------


class TestResolveEntity:
    def test_resolve_by_id(self, client, db):
        entity = _make_entity(db, "Alice")
        r = client.get(f"/api/entities/resolve/{entity.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["resolved"] is True
        assert data["entity_id"] == entity.id
        assert data["match_type"] == "id"

    def test_resolve_by_name(self, client, db):
        _make_entity(db, "Alice Smith")
        r = client.get("/api/entities/resolve/Alice Smith")
        assert r.status_code == 200
        data = r.json()
        assert data["resolved"] is True

    def test_resolve_unknown(self, client):
        r = client.get("/api/entities/resolve/nobody-here")
        assert r.status_code == 200
        assert r.json()["resolved"] is False
