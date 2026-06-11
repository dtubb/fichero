"""Tests for document management routes.

Documents are the primary model in the Fichero library — files, notes, and
hierarchical collections. Tests cover CRUD, hierarchy traversal, and
pagination. No external dependencies; uses real in-memory DB fixture.
"""

from fichero.knowledge_models import MutationLog
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
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["name"] == "Inbox"
        assert items[0]["parent_id"] is None
        assert items[0]["doc_type"] == "folder"

    def test_returns_saved_documents(self, client, db):
        _make_doc(db, "Doc A")
        _make_doc(db, "Doc B")
        r = client.get("/api/documents")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 3
        names = {item["name"] for item in items}
        assert {"Inbox", "Doc A", "Doc B"} <= names

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
        assert len(r.json()["items"]) == 3


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
        assert len(ids) == 2  # child excluded; Inbox is always present


# ---------------------------------------------------------------------------
# GET /api/documents/{doc_id}
# ---------------------------------------------------------------------------


class TestGetDocument:
    def test_get_existing(self, client, db):
        doc = _make_doc(db, "My Doc")
        r = client.get(f"/api/documents/{doc.id}")
        assert r.status_code == 200
        assert r.json()["id"] == doc.id

    def test_get_doc_prefixed_existing_returns_same_document(self, client, db):
        doc = _make_doc(db, "My Doc")
        r = client.get(f"/api/documents/doc:{doc.id}")
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

    def test_doc_prefixed_id_resolves_same_as_bare(self, client, db):
        """#1345: callers (e.g. the catalogue workflow) sometimes pass a
        ``doc:``-prefixed id. It must normalize to the bare hex id so the
        children lookup returns the same result instead of 404ing."""
        parent = _make_doc(db, "Parent")
        child = _make_doc(db, "Child 1", parent_id=parent.id)

        bare = client.get(f"/api/documents/{parent.id}/children")
        prefixed = client.get(f"/api/documents/doc:{parent.id}/children")

        assert bare.status_code == 200
        assert prefixed.status_code == 200  # not 404
        bare_ids = sorted(d["id"] for d in bare.json()["items"])
        prefixed_ids = sorted(d["id"] for d in prefixed.json()["items"])
        assert bare_ids == prefixed_ids
        assert child.id in prefixed_ids

    def test_doc_prefixed_missing_parent_still_404(self, client):
        """A ``doc:``-prefixed id for a genuinely-absent parent still 404s
        (normalization must not mask real misses)."""
        r = client.get("/api/documents/doc:no-such-parent/children")
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

    def test_excludes_children_that_no_longer_resolve(self, client, db, monkeypatch):
        from fichero.db import Database

        parent = _make_doc(db, "Parent")
        good_child = _make_doc(db, "Good Child", parent_id=parent.id)
        stale_child = _make_doc(db, "Stale Child", parent_id=parent.id)

        real_get = Database.get

        def flaky_get(self, model, doc_id):
            if model is Document and doc_id == stale_child.id:
                return None
            return real_get(self, model, doc_id)

        monkeypatch.setattr(Database, "get", flaky_get)

        r = client.get(f"/api/documents/{parent.id}/children")

        assert r.status_code == 200
        ids = [d["id"] for d in r.json()["items"]]
        assert good_child.id in ids
        assert stale_child.id not in ids


# ---------------------------------------------------------------------------
# Ordering: list + children honour sort_order (#572)
# ---------------------------------------------------------------------------


def _make_ordered_doc(db, name, sort_order, parent_id=None):
    doc = Document(
        name=name, parent_id=parent_id, doc_type=DocType.file, sort_order=sort_order
    )
    db.save(doc)
    return doc


class TestSortOrder:
    """After a reorder persists sort_order, list endpoints must return rows in
    sort_order ASC, name ASC order so the client doesn't have to re-sort and the
    drag-drop position survives refresh (#572)."""

    def test_children_ordered_by_sort_order(self, client, db):
        parent = _make_doc(db, "Parent")
        # Inserted out of order; sort_order should drive the result order.
        _make_ordered_doc(db, "Zebra", sort_order=0, parent_id=parent.id)
        _make_ordered_doc(db, "Apple", sort_order=1, parent_id=parent.id)
        _make_ordered_doc(db, "Mango", sort_order=2, parent_id=parent.id)
        r = client.get(f"/api/documents/{parent.id}/children")
        assert r.status_code == 200
        names = [d["name"] for d in r.json()["items"]]
        assert names == ["Zebra", "Apple", "Mango"]

    def test_children_tie_breaks_by_name(self, client, db):
        parent = _make_doc(db, "Parent")
        # Reorder-unaware siblings all tie at sort_order 0 → fall back to name.
        _make_ordered_doc(db, "Charlie", sort_order=0, parent_id=parent.id)
        _make_ordered_doc(db, "Alpha", sort_order=0, parent_id=parent.id)
        _make_ordered_doc(db, "Bravo", sort_order=0, parent_id=parent.id)
        r = client.get(f"/api/documents/{parent.id}/children")
        names = [d["name"] for d in r.json()["items"]]
        assert names == ["Alpha", "Bravo", "Charlie"]

    def test_list_documents_ordered_by_sort_order(self, client, db):
        parent = _make_doc(db, "Parent")
        _make_ordered_doc(db, "Third", sort_order=2, parent_id=parent.id)
        _make_ordered_doc(db, "First", sort_order=0, parent_id=parent.id)
        _make_ordered_doc(db, "Second", sort_order=1, parent_id=parent.id)
        r = client.get(f"/api/documents?parent_id={parent.id}")
        names = [d["name"] for d in r.json()["items"]]
        assert names == ["First", "Second", "Third"]

    def test_reorder_then_children_reflects_new_order(self, client, db):
        parent = _make_doc(db, "Parent")
        a = _make_ordered_doc(db, "A", sort_order=0, parent_id=parent.id)
        b = _make_ordered_doc(db, "B", sort_order=1, parent_id=parent.id)
        c = _make_ordered_doc(db, "C", sort_order=2, parent_id=parent.id)
        # Move C to the front.
        resp = client.post("/api/documents/reorder", json=[c.id, a.id, b.id])
        assert resp.status_code == 200
        r = client.get(f"/api/documents/{parent.id}/children")
        names = [d["name"] for d in r.json()["items"]]
        assert names == ["C", "A", "B"]


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


class TestBatchExcludeDocuments:
    def test_batch_exclude_updates_documents_and_logs_mutation(self, client, db):
        doc_a = _make_doc(db, "Doc A")
        doc_b = _make_doc(db, "Doc B")

        r = client.patch(
            "/api/documents/batch-exclude",
            json={
                "document_ids": [doc_a.id, doc_b.id],
                "excluded": True,
                "reason": "curation",
            },
        )

        assert r.status_code == 200
        payload = r.json()
        assert payload["updated"] == 2
        assert set(payload["document_ids"]) == {doc_a.id, doc_b.id}

        refreshed_a = db.get(Document, doc_a.id)
        refreshed_b = db.get(Document, doc_b.id)
        assert refreshed_a is not None and refreshed_a.exclude_from_processing is True
        assert refreshed_b is not None and refreshed_b.exclude_from_processing is True

        logs = [
            m
            for m in db.query(MutationLog)
            if m.entity_type == "Document" and m.entity_id in {doc_a.id, doc_b.id}
        ]
        assert len(logs) == 2
        assert all(m.changed_fields == ["exclude_from_processing"] for m in logs)
        assert all(m.after_state["exclude_from_processing"] is True for m in logs)


# ---------------------------------------------------------------------------
# DELETE /api/documents/{doc_id}
# ---------------------------------------------------------------------------


class TestDeleteDocument:
    def test_delete_soft_deletes_document(self, client, db):
        doc = _make_doc(db)
        r = client.delete(f"/api/documents/{doc.id}")
        assert r.status_code == 204
        persisted = db.get(Document, doc.id)
        assert persisted is not None
        assert persisted.deleted_at is not None
        assert persisted.deleted_by == "system"
        r2 = client.get(f"/api/documents/{doc.id}")
        assert r2.status_code == 404

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/documents/no-such-id")
        assert r.status_code == 404

    def test_delete_soft_deletes_children(self, client, db):
        parent = _make_doc(db, "Parent")
        child = _make_doc(db, "Child", parent_id=parent.id)
        client.delete(f"/api/documents/{parent.id}")
        assert db.get(Document, parent.id).deleted_at is not None
        assert db.get(Document, child.id).deleted_at is not None
        r = client.get(f"/api/documents/{child.id}")
        assert r.status_code == 404

    def test_delete_preserves_kg_rows_for_restore(self, client, db):
        """Soft-delete hides the document without destroying its KG rows."""
        from fichero.knowledge_models import (
            KnowledgeClaim,
            KnowledgeEntity,
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

        assert db.get(KnowledgeClaim, claim.id) is not None
        assert db.get(KnowledgeEntity, entity.id) is not None


class TestRestoreAndPurgeDocument:
    def test_restore_clears_deleted_flags(self, client, db):
        doc = _make_doc(db, "Restore Me")
        assert client.delete(f"/api/documents/{doc.id}").status_code == 204

        restore = client.post(f"/api/documents/{doc.id}/restore")
        assert restore.status_code == 204

        refreshed = db.get(Document, doc.id)
        assert refreshed is not None
        assert refreshed.deleted_at is None
        assert refreshed.deleted_by is None
        assert client.get(f"/api/documents/{doc.id}").status_code == 200

    def test_purge_hard_deletes_document_and_kg_rows(self, client, db):
        from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity, MutationLog

        doc = _make_doc(db, "Source Doc")
        entity = KnowledgeEntity(canonical_name="Eldorado")
        db.save(entity)
        claim = KnowledgeClaim(
            text="Eldorado is a mine.",
            source_document_id=doc.id,
            entity_ids=[entity.id],
        )
        db.save(claim)
        assert client.delete(f"/api/documents/{doc.id}").status_code == 204

        purge = client.delete(f"/api/documents/{doc.id}/purge")
        assert purge.status_code == 204

        assert db.get(Document, doc.id) is None
        assert db.get(KnowledgeClaim, claim.id) is None
        assert db.get(KnowledgeEntity, entity.id) is None
        logs = {(m.entity_type, m.entity_id): m for m in db.query(MutationLog)}
        assert logs[("KnowledgeClaim", claim.id)].operation.value == "delete"
        assert logs[("KnowledgeEntity", entity.id)].operation.value == "delete"

    def test_trash_lists_deleted_without_normal_list_leak(self, client, db):
        doc = _make_doc(db, "Trash Entry")
        assert client.delete(f"/api/documents/{doc.id}").status_code == 204

        normal = client.get("/api/documents")
        assert normal.status_code == 200
        assert all(item["id"] != doc.id for item in normal.json()["items"])

        trash = client.get("/api/documents/trash")
        assert trash.status_code == 200
        assert any(item["id"] == doc.id for item in trash.json()["items"])


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
