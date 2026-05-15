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
        assert r.json() == []

    def test_returns_saved_documents(self, client, db):
        _make_doc(db, "Doc A")
        _make_doc(db, "Doc B")
        r = client.get("/api/documents")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_pagination_limit(self, client, db):
        for i in range(5):
            _make_doc(db, f"Doc {i}")
        r = client.get("/api/documents?limit=3")
        assert r.status_code == 200
        assert len(r.json()) == 3

    def test_pagination_offset(self, client, db):
        for i in range(5):
            _make_doc(db, f"Doc {i}")
        r = client.get("/api/documents?offset=3")
        assert r.status_code == 200
        assert len(r.json()) == 2


# ---------------------------------------------------------------------------
# GET /api/documents/collections
# ---------------------------------------------------------------------------


class TestListCollections:
    def test_returns_root_docs(self, client, db):
        root = _make_doc(db, "Root")
        _make_doc(db, "Child", parent_id=root.id)
        r = client.get("/api/documents/collections")
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
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
# GET /api/documents/{doc_id}/children
# ---------------------------------------------------------------------------


class TestGetChildren:
    def test_returns_children(self, client, db):
        parent = _make_doc(db, "Parent")
        child1 = _make_doc(db, "Child 1", parent_id=parent.id)
        child2 = _make_doc(db, "Child 2", parent_id=parent.id)
        r = client.get(f"/api/documents/{parent.id}/children")
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert child1.id in ids
        assert child2.id in ids

    def test_returns_empty_for_leaf(self, client, db):
        doc = _make_doc(db)
        r = client.get(f"/api/documents/{doc.id}/children")
        assert r.status_code == 200
        assert r.json() == []

    def test_missing_parent_returns_404(self, client):
        r = client.get("/api/documents/no-such-parent/children")
        assert r.status_code == 404


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
        ids = [d["id"] for d in r.json()]
        assert parent.id in ids
        assert grandparent.id in ids

    def test_root_has_no_ancestors(self, client, db):
        doc = _make_doc(db)
        r = client.get(f"/api/documents/{doc.id}/ancestors")
        assert r.status_code == 200
        assert r.json() == []

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
