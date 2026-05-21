"""Tests for knowledge entity routes.

KnowledgeEntity is the central node in the knowledge graph — named things
(people, places, concepts) that claims refer to. Tests cover CRUD, alias
management, and entity resolution. Route ordering fix required: static paths
/alias-map and /resolve/{v} must be registered before /{entity_id}.
"""

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
        assert r.json()["items"] == []
        assert r.json()["count"] == 0

    def test_returns_saved_entities(self, client, db):
        _make_entity(db, "Alice")
        _make_entity(db, "Bob")
        r = client.get("/api/entities")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2

    def test_filter_by_type(self, client, db):
        _make_entity(db, "Alice", EntityType.person)
        _make_entity(db, "London", EntityType.location)
        r = client.get("/api/entities?entity_type=person")
        assert r.status_code == 200
        names = [e["canonical_name"] for e in r.json()["items"]]
        assert "Alice" in names
        assert "London" not in names

    def test_search_by_name(self, client, db):
        _make_entity(db, "Alice Smith")
        _make_entity(db, "Bob Jones")
        r = client.get("/api/entities?q=alice")
        assert r.status_code == 200
        data = r.json()["items"]
        assert len(data) == 1
        assert data[0]["canonical_name"] == "Alice Smith"

    def test_filter_by_document_id(self, client, db):
        """Filter entities by document_id - returns only entities
        mentioned in claims from that document."""
        from fichero.knowledge_models import KnowledgeClaim
        
        # Create entities
        entity1 = _make_entity(db, "Alice", EntityType.person)
        entity2 = _make_entity(db, "Bob", EntityType.person)
        entity3 = _make_entity(db, "Charlie", EntityType.person)
        
        # Create claims referencing only some entities
        claim1 = KnowledgeClaim(
            text="Alice did something",
            source_document_id="doc-1",
            entity_ids=[entity1.id],
        )
        claim2 = KnowledgeClaim(
            text="Bob did something else",
            source_document_id="doc-1",
            entity_ids=[entity2.id],
        )
        claim3 = KnowledgeClaim(
            text="Charlie was in doc-2",
            source_document_id="doc-2",
            entity_ids=[entity3.id],
        )
        db.save(claim1)
        db.save(claim2)
        db.save(claim3)
        
        # Filter by doc-1 should return Alice and Bob only
        r = client.get("/api/entities?document_id=doc-1")
        assert r.status_code == 200
        names = {e["canonical_name"] for e in r.json()["items"]}
        assert names == {"Alice", "Bob"}
        
        # Filter by doc-2 should return Charlie only
        r = client.get("/api/entities?document_id=doc-2")
        assert r.status_code == 200
        names = {e["canonical_name"] for e in r.json()["items"]}
        assert names == {"Charlie"}


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


class TestPatchEntity:
    """#901 — partial update for canonical_name / aliases / etc."""

    def test_patch_canonical_name(self, client, db):
        entity = _make_entity(db, "Alice")
        r = client.patch(f"/api/entities/{entity.id}", json={"canonical_name": "Alice Smith"})
        assert r.status_code == 200
        assert r.json()["canonical_name"] == "Alice Smith"
        # DB row reflects the update.
        reloaded = db.get(KnowledgeEntity, entity.id)
        assert reloaded.canonical_name == "Alice Smith"

    def test_patch_aliases_replaces_existing(self, client, db):
        entity = _make_entity(db, "Alice")
        entity.aliases = ["A", "B"]
        db.save(entity)
        r = client.patch(f"/api/entities/{entity.id}", json={"aliases": ["Al", "Ally"]})
        assert r.status_code == 200
        assert set(r.json()["aliases"]) == {"Al", "Ally"}

    def test_patch_only_supplied_fields(self, client, db):
        """PATCH should not clobber fields absent from the request body."""
        entity = _make_entity(db, "Alice")
        entity.description = "original description"
        db.save(entity)
        r = client.patch(f"/api/entities/{entity.id}", json={"canonical_name": "Renamed"})
        assert r.status_code == 200
        body = r.json()
        assert body["canonical_name"] == "Renamed"
        assert body["description"] == "original description"

    def test_patch_missing_returns_404(self, client):
        r = client.patch("/api/entities/no-such", json={"canonical_name": "X"})
        assert r.status_code == 404


class TestDeleteEntity:
    """#901 — DELETE removes the entity and optionally cascades to claims."""

    def test_delete_returns_204(self, client, db):
        entity = _make_entity(db, "Alice")
        r = client.delete(f"/api/entities/{entity.id}")
        assert r.status_code == 204
        assert db.get(KnowledgeEntity, entity.id) is None

    def test_delete_strips_entity_from_claims_by_default(self, client, db):
        """Without cascade, claims keep their text + provenance but
        lose the deleted entity from their entity_ids list."""
        from fichero.knowledge_models import KnowledgeClaim
        entity = _make_entity(db, "Alice")
        claim = KnowledgeClaim(
            text="Alice signed the deed.",
            source_document_id="doc-1",
            entity_ids=[entity.id, "other-id"],
        )
        db.save(claim)
        r = client.delete(f"/api/entities/{entity.id}")
        assert r.status_code == 204
        reloaded = db.get(KnowledgeClaim, claim.id)
        assert reloaded is not None
        assert entity.id not in reloaded.entity_ids
        assert "other-id" in reloaded.entity_ids

    def test_delete_with_cascade_removes_dependent_claims(self, client, db):
        from fichero.knowledge_models import KnowledgeClaim
        entity = _make_entity(db, "Alice")
        claim = KnowledgeClaim(
            text="Alice signed.",
            source_document_id="doc-1",
            entity_ids=[entity.id],
        )
        db.save(claim)
        r = client.delete(f"/api/entities/{entity.id}?cascade_claims=true")
        assert r.status_code == 204
        assert db.get(KnowledgeClaim, claim.id) is None

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/entities/no-such-id")
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
