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

    def test_filter_by_parent_document_id_rolls_up_page_claims(self, client, db):
        from fichero.knowledge_models import KnowledgeClaim
        from fichero.models import DocType, Document

        parent = Document(name="Preface.pdf", doc_type=DocType.file)
        page1 = Document(name="page 1", doc_type=DocType.page, parent_id=parent.id)
        page2 = Document(name="page 2", doc_type=DocType.page, parent_id=parent.id)
        db.save(parent)
        db.save(page1)
        db.save(page2)

        person = _make_entity(db, "Louise Livingstone", EntityType.person)
        place = _make_entity(db, "Deloro", EntityType.location)
        db.save(
            KnowledgeClaim(
                text="Livingstone signed.",
                source_document_id=page1.id,
                entity_ids=[person.id],
            )
        )
        db.save(
            KnowledgeClaim(
                text="Deloro appears.",
                source_document_id=page2.id,
                entity_ids=[place.id],
            )
        )

        r = client.get(f"/api/entities?document_id={page1.id}")
        assert r.status_code == 200
        assert {e["canonical_name"] for e in r.json()["items"]} == {
            "Louise Livingstone"
        }

        r = client.get(f"/api/entities?document_id={parent.id}")
        assert r.status_code == 200
        assert {e["canonical_name"] for e in r.json()["items"]} == {
            "Deloro",
            "Louise Livingstone",
        }

    def test_filter_by_page_honors_entity_source_document_ids(self, client, db):
        """#1562 read-side — an entity scoped to a page via
        ``source_document_ids`` surfaces for that page even when its
        CLAIMS point at the PARENT doc (legacy / non-aggregate flow)."""
        from datetime import datetime

        from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity
        from fichero.models import DocType, Document

        parent = Document(name="Chapter.pdf", doc_type=DocType.file)
        page1 = Document(name="page 1", doc_type=DocType.page, parent_id=parent.id)
        page2 = Document(name="page 2", doc_type=DocType.page, parent_id=parent.id)
        db.save(parent)
        db.save(page1)
        db.save(page2)

        # Entity scoped to page1 via the merged write-side field, but its
        # claim carries the PARENT id (the exact #1562 failure mode).
        ada = KnowledgeEntity(
            canonical_name="Ada Lovelace",
            entity_type=EntityType.person,
            aliases=[],
            source_document_ids=[page1.id],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.save(ada)
        db.save(
            KnowledgeClaim(
                text="Ada appears.",
                source_document_id=parent.id,
                entity_ids=[ada.id],
            )
        )

        # Querying page1 returns Ada (via source_document_ids union)...
        r = client.get(f"/api/entities?document_id={page1.id}")
        assert r.status_code == 200
        assert {e["canonical_name"] for e in r.json()["items"]} == {"Ada Lovelace"}

        # ...but page2 does NOT — Ada was never scoped to it.
        r = client.get(f"/api/entities?document_id={page2.id}")
        assert r.status_code == 200
        assert {e["canonical_name"] for e in r.json()["items"]} == set()

        # The parent query still returns the compiled (union) set: the
        # parent-scoped claim already references Ada.
        r = client.get(f"/api/entities?document_id={parent.id}")
        assert r.status_code == 200
        assert {e["canonical_name"] for e in r.json()["items"]} == {"Ada Lovelace"}

    def test_default_list_hides_bare_dates_but_search_can_find_them(self, client, db):
        _make_entity(db, "Alice", EntityType.person)
        _make_entity(db, "1960", EntityType.other)
        _make_entity(db, "1891-03-08", EntityType.other)

        r = client.get("/api/entities")
        assert r.status_code == 200
        names = [e["canonical_name"] for e in r.json()["items"]]
        assert "Alice" in names
        assert "1960" not in names
        assert "1891-03-08" not in names

        r = client.get("/api/entities?q=1960")
        assert r.status_code == 200
        names = [e["canonical_name"] for e in r.json()["items"]]
        assert "1960" in names


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

    def test_upsert_with_unknown_id_returns_404_not_silent_create(self, client):
        """#2507: a specific id requested for update but absent must 404, never
        silently create a NEW entity under a different auto-generated id."""
        r = client.post("/api/entities", json={
            "id": "no-such-entity-id",
            "canonical_name": "Ghost",
            "entity_type": "person",
        })
        assert r.status_code == 404
        # And nothing was written: no substitute row appears in the list.
        listing = client.get("/api/entities")
        assert listing.status_code == 200
        entities = listing.json()["items"]
        assert all(e["id"] != "no-such-entity-id" for e in entities)
        assert all(e["canonical_name"] != "Ghost" for e in entities)

    def test_upsert_unknown_id_leaves_other_entities_untouched(self, client, db):
        """The failed upsert must not create a substitute row alongside real data."""
        keep = _make_entity(db, "Keeper")
        before = client.get("/api/entities").json()["items"]
        r = client.post("/api/entities", json={
            "id": "missing-id",
            "canonical_name": "Substitute",
            "entity_type": "person",
        })
        assert r.status_code == 404
        after = client.get("/api/entities").json()["items"]
        assert {e["id"] for e in after} == {e["id"] for e in before}
        assert any(e["id"] == keep.id for e in after)

    def test_garbage_name_timestamp_rejected(self, client):
        """Timestamp-shaped names like '12:10' contain no letters and must be rejected."""
        r = client.post("/api/entities", json={
            "canonical_name": "12:10",
            "entity_type": "other",
        })
        assert r.status_code == 422

    def test_garbage_name_pure_numeric_rejected(self, client):
        r = client.post("/api/entities", json={
            "canonical_name": "99999",
            "entity_type": "other",
        })
        assert r.status_code == 422

    def test_garbage_name_single_char_rejected(self, client):
        r = client.post("/api/entities", json={
            "canonical_name": "x",
            "entity_type": "other",
        })
        assert r.status_code == 422

    def test_clean_name_with_letters_accepted(self, client):
        """Names that contain letters (even mixed with digits) are accepted."""
        r = client.post("/api/entities", json={
            "canonical_name": "Section 12",
            "entity_type": "concept",
        })
        assert r.status_code == 200
        assert r.json()["canonical_name"] == "Section 12"


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


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/biography  (#1352)
# ---------------------------------------------------------------------------


class TestEntityBiography:
    """Tests for the structured entity biography endpoint."""

    def test_biography_returns_entity_with_claims(self, client, db):
        """Entity with claims — biography contains entity facts, claims,
        documents, and co-occurring entities."""
        from fichero.knowledge_models import KnowledgeClaim
        from fichero.models import DocType, Document

        # Entity under test
        alice = _make_entity(db, "Alice", EntityType.person)
        bob = _make_entity(db, "Bob", EntityType.person)

        # Create real Document rows so the biography doc-links can resolve them
        doc1 = Document(name="Doc A", doc_type=DocType.file)
        doc2 = Document(name="Doc B", doc_type=DocType.file)
        db.save(doc1)
        db.save(doc2)

        # Two claims that mention Alice; one also mentions Bob (co-occurrence)
        claim1 = KnowledgeClaim(
            text="Alice served as mayor",
            source_document_id=doc1.id,
            entity_ids=[alice.id],
            subject_canonical="Alice",
            predicate_verb="served as",
            object_phrase="mayor",
        )
        claim2 = KnowledgeClaim(
            text="Alice and Bob collaborated",
            source_document_id=doc2.id,
            entity_ids=[alice.id, bob.id],
            subject_canonical="Alice",
            predicate_verb="collaborated with",
            object_phrase="Bob",
        )
        db.save(claim1)
        db.save(claim2)

        r = client.get(f"/api/entities/{alice.id}/biography")
        assert r.status_code == 200
        data = r.json()

        # Entity facts
        assert data["entity"]["canonical_name"] == "Alice"
        assert data["entity"]["entity_type"] == "person"

        # Both claims present
        claim_texts = {c["text"] for c in data["claims"]}
        assert "Alice served as mayor" in claim_texts
        assert "Alice and Bob collaborated" in claim_texts

        # Documents aggregated (resolved to their names via real Document rows)
        doc_ids = {d["document_id"] for d in data["documents"]}
        assert doc1.id in doc_ids
        assert doc2.id in doc_ids

        # Bob appears as co-occurring entity
        co_names = {e["name"] for e in data["co_occurring"]}
        assert "Bob" in co_names

    def test_biography_404_for_unknown_entity(self, client):
        """Non-existent entity_id returns HTTP 404."""
        r = client.get("/api/entities/does-not-exist-xyz/biography")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_biography_empty_but_valid_for_entity_with_no_claims(self, client, db):
        """Entity that exists but has no claims — biography returns empty
        claims / documents / co_occurring lists but valid entity block."""
        entity = _make_entity(db, "Lonely Entity", EntityType.other)

        r = client.get(f"/api/entities/{entity.id}/biography")
        assert r.status_code == 200
        data = r.json()

        assert data["entity"]["canonical_name"] == "Lonely Entity"
        assert data["claims"] == []
        assert data["documents"] == []
        assert data["co_occurring"] == []

    def test_biography_respects_claims_limit(self, client, db):
        """claims_limit query param caps the returned claims list."""
        from fichero.knowledge_models import KnowledgeClaim

        entity = _make_entity(db, "Busy Person", EntityType.person)
        for i in range(10):
            db.save(KnowledgeClaim(
                text=f"Claim {i}",
                source_document_id=f"doc-{i}",
                entity_ids=[entity.id],
            ))

        r = client.get(f"/api/entities/{entity.id}/biography?claims_limit=3")
        assert r.status_code == 200
        assert len(r.json()["claims"]) == 3

    def test_biography_response_shape(self, client, db):
        """Response always contains the four top-level keys."""
        entity = _make_entity(db, "Shape Test", EntityType.concept)

        r = client.get(f"/api/entities/{entity.id}/biography")
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) >= {"entity", "claims", "documents", "co_occurring"}
