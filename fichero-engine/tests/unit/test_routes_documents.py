"""Tests for document management routes.

Documents are the primary model in the Fichero library — files, notes, and
hierarchical collections. Tests cover CRUD, hierarchy traversal, and
pagination. No external dependencies; uses real in-memory DB fixture.
"""

from fichero.models import Document, DocType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(db, name: str = "Test Doc", parent_id: str | None = None) -> Document:
    doc = Document(name=name, parent_id=parent_id, doc_type=DocType.file)
    db.save(doc)
    return doc


# ---------------------------------------------------------------------------
# GET /api/documents
# ---------------------------------------------------------------------------


class TestListDocuments:
    def test_empty_list(self, client):
        r = client.get("/api/documents")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_returns_saved_documents(self, client, db):
        _make_doc(db, "Doc A")
        _make_doc(db, "Doc B")
        r = client.get("/api/documents")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2

    def test_pagination_limit(self, client, db):
        for i in range(5):
            _make_doc(db, f"Doc {i}")
        r = client.get("/api/documents?limit=3")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 3

    def test_pagination_offset(self, client, db):
        for i in range(5):
            _make_doc(db, f"Doc {i}")
        r = client.get("/api/documents?offset=3")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2


# ---------------------------------------------------------------------------
# GET /api/documents/collections
# ---------------------------------------------------------------------------


class TestListCollections:
    def test_returns_root_docs(self, client, db):
        root = _make_doc(db, "Root")
        _make_doc(db, "Child", parent_id=root.id)
        r = client.get("/api/documents/collections")
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()["items"]]
        assert root.id in ids
        assert len(ids) == 1  # child excluded


# ---------------------------------------------------------------------------
# GET /api/documents/{doc_id}
# ---------------------------------------------------------------------------


class TestGetDocument:
    def test_get_existing(self, client, db):
        doc = _make_doc(db, "My Doc")
        r = client.get(f"/api/documents/{doc.id}")
        assert r.status_code == 200
        assert r.json()["id"] == doc.id

    def test_get_missing_returns_404(self, client):
        r = client.get("/api/documents/nonexistent")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# /api/documents/{doc_id}/notes
# ---------------------------------------------------------------------------


class TestDocumentNotes:
    def test_put_then_get_document_note(self, client, db):
        doc = _make_doc(db, "Noted Doc")
        put = client.put(f"/api/documents/{doc.id}/notes", json={"content": "Remember this"})
        assert put.status_code == 200
        assert put.json()["document_id"] == doc.id
        assert put.json()["content"] == "Remember this"

        get = client.get(f"/api/documents/{doc.id}/notes")
        assert get.status_code == 200
        assert get.json()["content"] == "Remember this"

    def test_put_updates_existing_note(self, client, db):
        doc = _make_doc(db, "Updatable Note")
        first = client.put(f"/api/documents/{doc.id}/notes", json={"content": "v1"})
        second = client.put(f"/api/documents/{doc.id}/notes", json={"content": "v2"})
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert second.json()["content"] == "v2"

    def test_get_missing_note_returns_404(self, client, db):
        doc = _make_doc(db, "No Note")
        r = client.get(f"/api/documents/{doc.id}/notes")
        assert r.status_code == 404

    def test_delete_document_note(self, client, db):
        doc = _make_doc(db, "Delete Note")
        create = client.put(f"/api/documents/{doc.id}/notes", json={"content": "temp"})
        assert create.status_code == 200

        delete = client.delete(f"/api/documents/{doc.id}/notes")
        assert delete.status_code == 204

        missing = client.get(f"/api/documents/{doc.id}/notes")
        assert missing.status_code == 404

    def test_notes_missing_document_returns_404(self, client):
        r = client.put("/api/documents/no-such-doc/notes", json={"content": "x"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/documents/{doc_id}/children
# ---------------------------------------------------------------------------


class TestGetChildren:
    def test_returns_children(self, client, db):
        parent = _make_doc(db, "Parent")
        child1 = _make_doc(db, "Child 1", parent_id=parent.id)
        child2 = _make_doc(db, "Child 2", parent_id=parent.id)
        r = client.get(f"/api/documents/{parent.id}/children")
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()["items"]]
        assert child1.id in ids
        assert child2.id in ids

    def test_returns_empty_for_leaf(self, client, db):
        doc = _make_doc(db)
        r = client.get(f"/api/documents/{doc.id}/children")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_missing_parent_returns_404(self, client):
        r = client.get("/api/documents/no-such-parent/children")
        assert r.status_code == 404

    def test_returns_children_when_parent_lookup_is_transiently_missing(
        self, client, db, monkeypatch
    ):
        """#1345: don't 404 if children exist but parent lookup races to None."""
        from fichero.db import Database

        parent = _make_doc(db, "Parent")
        child = _make_doc(db, "Child 1", parent_id=parent.id)

        real_get = Database.get

        def flaky_get(self, model, doc_id):
            if model is Document and doc_id == parent.id:
                return None
            return real_get(self, model, doc_id)

        monkeypatch.setattr(Database, "get", flaky_get)

        r = client.get(f"/api/documents/{parent.id}/children")
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()["items"]]
        assert child.id in ids


# ---------------------------------------------------------------------------
# GET /api/documents/{doc_id}/ancestors
# ---------------------------------------------------------------------------


class TestGetAncestors:
    def test_returns_ancestor_chain(self, client, db):
        grandparent = _make_doc(db, "Grandparent")
        parent = _make_doc(db, "Parent", parent_id=grandparent.id)
        child = _make_doc(db, "Child", parent_id=parent.id)
        r = client.get(f"/api/documents/{child.id}/ancestors")
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()["items"]]
        assert parent.id in ids
        assert grandparent.id in ids

    def test_root_has_no_ancestors(self, client, db):
        doc = _make_doc(db)
        r = client.get(f"/api/documents/{doc.id}/ancestors")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_missing_returns_404(self, client):
        r = client.get("/api/documents/no-such-id/ancestors")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/documents
# ---------------------------------------------------------------------------


class TestCreateDocument:
    def test_create_document(self, client):
        r = client.post("/api/documents", json={"name": "New Doc"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "New Doc"
        assert "id" in data

    def test_create_with_parent(self, client, db):
        parent = _make_doc(db, "Parent")
        r = client.post("/api/documents", json={"name": "Child", "parent_id": parent.id})
        assert r.status_code == 201
        assert r.json()["parent_id"] == parent.id

    def test_create_with_missing_parent_returns_400(self, client):
        r = client.post("/api/documents", json={"name": "Doc", "parent_id": "no-such-parent"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/documents/import
# ---------------------------------------------------------------------------


class TestImportDocument:
    """Regression: #1104 — original filename must survive multipart upload.

    Before the fix, ``save_uploaded_file`` wrote the body to a tempfile
    named ``fichero_upload_<random><ext>`` and ``ingest_file`` set
    ``Document.name = path.name``, so every imported doc displayed as
    ``fichero_upload_*`` instead of the user's filename.
    """

    def test_import_preserves_original_filename(self, client):
        original = "analysis-mining-terms.md"
        body = b"# Analysis\n\nMining terms used in the corpus.\n"
        r = client.post(
            "/api/documents/import",
            files={"file": (original, body, "text/markdown")},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == original, (
            f"Document.name = {data['name']!r}, expected {original!r} "
            "(import endpoint must use multipart filename, not temp path)"
        )
        assert not data["name"].startswith("fichero_upload_")


# ---------------------------------------------------------------------------
# PUT /api/documents/{doc_id}
# ---------------------------------------------------------------------------


class TestUpdateDocument:
    def test_update_name(self, client, db):
        doc = _make_doc(db, "Old Name")
        r = client.put(f"/api/documents/{doc.id}", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_update_missing_returns_404(self, client):
        r = client.put("/api/documents/no-such-id", json={"name": "X"})
        assert r.status_code == 404

    def test_update_read_flag_star_state(self, client, db):
        doc = _make_doc(db, "Mail style states")
        r = client.put(
            f"/api/documents/{doc.id}",
            json={"is_read": True, "is_flagged": True, "is_starred": True},
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["is_read"] is True
        assert payload["is_flagged"] is True
        assert payload["is_starred"] is True

        r2 = client.get(f"/api/documents/{doc.id}")
        assert r2.status_code == 200
        payload2 = r2.json()
        assert payload2["is_read"] is True
        assert payload2["is_flagged"] is True
        assert payload2["is_starred"] is True

    def test_update_can_clear_read_flag_state(self, client, db):
        doc = _make_doc(db, "Unread toggle")
        client.put(
            f"/api/documents/{doc.id}",
            json={"is_read": True, "is_flagged": True, "is_starred": True},
        )
        r = client.put(
            f"/api/documents/{doc.id}",
            json={"is_read": False, "is_flagged": False, "is_starred": False},
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["is_read"] is False
        assert payload["is_flagged"] is False
        assert payload["is_starred"] is False


# ---------------------------------------------------------------------------
# DELETE /api/documents/{doc_id}
# ---------------------------------------------------------------------------


class TestDeleteDocument:
    def test_delete_removes_document(self, client, db):
        doc = _make_doc(db)
        r = client.delete(f"/api/documents/{doc.id}")
        assert r.status_code == 204
        r2 = client.get(f"/api/documents/{doc.id}")
        assert r2.status_code == 404

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/documents/no-such-id")
        assert r.status_code == 404

    def test_delete_cascades_to_children(self, client, db):
        parent = _make_doc(db, "Parent")
        child = _make_doc(db, "Child", parent_id=parent.id)
        client.delete(f"/api/documents/{parent.id}")
        r = client.get(f"/api/documents/{child.id}")
        assert r.status_code == 404

    def test_delete_cascades_to_kg_claims_and_orphan_entities(self, client, db):
        """Deleting a source document removes the claims it sourced and
        prunes entities left with no remaining claims — logged to
        MutationLog so the cascade is reversible. (#1021)"""
        from fichero.knowledge_models import (
            KnowledgeClaim,
            KnowledgeEntity,
            MutationLog,
        )

        doc = _make_doc(db, "Source Doc")
        entity = KnowledgeEntity(canonical_name="Eldorado")
        db.save(entity)
        claim = KnowledgeClaim(
            text="Eldorado is a mine.",
            source_document_id=doc.id,
            entity_ids=[entity.id],
        )
        db.save(claim)

        r = client.delete(f"/api/documents/{doc.id}")
        assert r.status_code == 204

        # Claim sourced from the deleted doc is gone.
        assert db.get(KnowledgeClaim, claim.id) is None
        # Entity had no other claims → pruned.
        assert db.get(KnowledgeEntity, entity.id) is None
        # Both deletions are logged and reversible.
        logs = {
            (m.entity_type, m.entity_id): m
            for m in db.query(MutationLog)
        }
        claim_log = logs[("KnowledgeClaim", claim.id)]
        assert claim_log.operation.value == "delete"
        assert claim_log.before_state is not None
        assert claim_log.after_state is None
        entity_log = logs[("KnowledgeEntity", entity.id)]
        assert entity_log.operation.value == "delete"
        assert entity_log.before_state is not None

    def test_delete_keeps_entities_still_referenced_by_other_docs(self, client, db):
        """An entity referenced by a claim sourced from a *different*
        document survives — only genuinely-orphaned entities are pruned.
        (#1021)"""
        from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity

        doc_a = _make_doc(db, "Doc A")
        doc_b = _make_doc(db, "Doc B")
        shared = KnowledgeEntity(canonical_name="Chocó")
        db.save(shared)
        db.save(KnowledgeClaim(
            text="Chocó claim from A.",
            source_document_id=doc_a.id,
            entity_ids=[shared.id],
        ))
        claim_b = KnowledgeClaim(
            text="Chocó claim from B.",
            source_document_id=doc_b.id,
            entity_ids=[shared.id],
        )
        db.save(claim_b)

        r = client.delete(f"/api/documents/{doc_a.id}")
        assert r.status_code == 204

        # Claim B and the shared entity both survive.
        assert db.get(KnowledgeClaim, claim_b.id) is not None
        assert db.get(KnowledgeEntity, shared.id) is not None


# ---------------------------------------------------------------------------
# GET /api/documents/{id}/parent
# ---------------------------------------------------------------------------


class TestGetDocumentParent:
    def test_get_parent_of_child_document(self, client, db):
        """Test getting the parent of a child document."""
        parent = _make_doc(db, "Parent Doc")
        child = _make_doc(db, "Child Doc", parent_id=parent.id)
        
        r = client.get(f"/api/documents/{child.id}/parent")
        assert r.status_code == 200
        result = r.json()
        assert result["id"] == parent.id
        assert result["name"] == "Parent Doc"
    
    def test_get_parent_of_root_document_returns_404(self, client, db):
        """Test getting parent of root document returns 404."""
        root = _make_doc(db, "Root Doc")
        
        r = client.get(f"/api/documents/{root.id}/parent")
        assert r.status_code == 404
    
    def test_get_parent_of_missing_document_returns_404(self, client, db):
        """Test getting parent of missing document returns 404."""
        r = client.get("/api/documents/missing-id/parent")
        assert r.status_code == 404
    
    def test_get_parent_when_parent_is_missing_returns_404(self, client, db):
        """Test getting parent when parent document is missing returns 404."""
        child = _make_doc(db, "Child Doc", parent_id="missing-parent-id")

        r = client.get(f"/api/documents/{child.id}/parent")
        assert r.status_code == 404


class TestDocumentPrototypes:
    def test_assigns_prototype_to_single_document(self, client, db):
        doc = _make_doc(db, "Letter A")
        r = client.put(
            f"/api/documents/{doc.id}/prototype",
            json={"prototype_key": "letter"},
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["updated_count"] == 1
        refreshed = db.get(Document, doc.id)
        assert refreshed.prototype_key == "letter"

    def test_assigns_prototype_to_descendant_page_range(self, client, db):
        folder = _make_doc(db, "Folder")
        page1 = Document(name="p1", doc_type=DocType.page, parent_id=folder.id, sequence=1)
        page2 = Document(name="p2", doc_type=DocType.page, parent_id=folder.id, sequence=2)
        page3 = Document(name="p3", doc_type=DocType.page, parent_id=folder.id, sequence=3)
        db.save(page1)
        db.save(page2)
        db.save(page3)
        r = client.put(
            f"/api/documents/{folder.id}/prototype",
            json={
                "prototype_key": "chapter",
                "include_descendants": True,
                "page_start": 2,
                "page_end": 3,
            },
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["updated_count"] == 2
        assert db.get(Document, page1.id).prototype_key is None
        assert db.get(Document, page2.id).prototype_key == "chapter"
        assert db.get(Document, page3.id).prototype_key == "chapter"


class TestDocumentPageRanges:
    def test_upsert_and_lookup_page_ranges(self, client, db):
        pdf = Document(name="Book PDF", doc_type=DocType.file)
        db.save(pdf)

        put = client.put(
            f"/api/documents/{pdf.id}/page-ranges",
            json={
                "items": [
                    {"name": "Chapter 1", "page_start": 1, "page_end": 10},
                    {"name": "Chapter 2", "page_start": 11, "page_end": 20},
                ]
            },
        )
        assert put.status_code == 200
        assert put.json()["count"] == 2

        get_all = client.get(f"/api/documents/{pdf.id}/page-ranges")
        assert get_all.status_code == 200
        assert get_all.json()["count"] == 2

        at_page = client.get(f"/api/documents/{pdf.id}/page-ranges/at/12")
        assert at_page.status_code == 200
        assert at_page.json()["name"] == "Chapter 2"
