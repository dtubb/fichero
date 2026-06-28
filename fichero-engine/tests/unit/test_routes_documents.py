"""Tests for document management routes.

Documents are the primary model in the Fichero library — files, notes, and
hierarchical collections. Tests cover CRUD, hierarchy traversal, and
pagination. No external dependencies; uses real in-memory DB fixture.
"""


import asyncio
import time
from unittest.mock import AsyncMock

import pytest


from fichero import storage as storage_module
from fichero.api.routes import documents as documents_routes
from fichero.api.routes.documents import related_documents
from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity, MutationLog
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

    def test_doc_prefixed_note_routes_resolve_same_document(self, client, db):
        doc = _make_doc(db, "Prefixed Notes Doc")

        put = client.put(f"/api/documents/doc:{doc.id}/notes", json={"content": "Remember this too"})
        get = client.get(f"/api/documents/doc:{doc.id}/notes")

        assert put.status_code == 200
        assert put.json()["document_id"] == doc.id
        assert get.status_code == 200
        assert get.json()["document_id"] == doc.id
        assert get.json()["content"] == "Remember this too"

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


class TestRelatedDocuments:
    def test_direct_helper_returns_envelope_with_items_not_row_list(self, db):
        seed = _make_doc(db, "Seed")
        peer = _make_doc(db, "Peer")
        db.save(KnowledgeEntity(id="ent-shared", canonical_name="Quibdo"))
        db.save(
            KnowledgeClaim(
                id="claim-seed",
                text="Seed mentions Quibdo.",
                source_document_id=seed.id,
                entity_ids=["ent-shared"],
            )
        )
        db.save(
            KnowledgeClaim(
                id="claim-peer",
                text="Peer mentions Quibdo.",
                source_document_id=peer.id,
                entity_ids=["ent-shared"],
            )
        )

        response = asyncio.run(related_documents(seed.id, limit=10, db=db))

        assert response.count == 1
        assert len(response.items) == 1
        assert response.items[0].document_id == peer.id
        assert response.items[0].shared_entities == 1

    def test_route_returns_empty_when_document_has_no_claim_entities(self, client, db):
        doc = _make_doc(db, "Lonely")

        response = client.get(f"/api/documents/{doc.id}/related")

        assert response.status_code == 200
        assert response.json() == {"items": [], "count": 0}

    def test_route_excludes_self_deduplicates_per_entity_and_orders_by_overlap(self, client, db):
        seed = _make_doc(db, "Seed")
        top = _make_doc(db, "Top overlap")
        second = _make_doc(db, "Second overlap")
        outsider = _make_doc(db, "Outsider")

        for entity_id, name in [
            ("ent-a", "Leidy"),
            ("ent-b", "Quibdo"),
            ("ent-c", "Mining"),
        ]:
            db.save(KnowledgeEntity(id=entity_id, canonical_name=name))

        db.save(
            KnowledgeClaim(
                id="seed-1",
                text="Seed mentions Leidy and Quibdo.",
                source_document_id=seed.id,
                entity_ids=["ent-a", "ent-b"],
            )
        )
        db.save(
            KnowledgeClaim(
                id="seed-2",
                text="Seed also mentions Mining.",
                source_document_id=seed.id,
                entity_ids=["ent-c"],
            )
        )
        db.save(
            KnowledgeClaim(
                id="top-1",
                text="Top shares Leidy twice.",
                source_document_id=top.id,
                entity_ids=["ent-a"],
            )
        )
        db.save(
            KnowledgeClaim(
                id="top-2",
                text="Top shares Leidy again.",
                source_document_id=top.id,
                entity_ids=["ent-a"],
            )
        )
        db.save(
            KnowledgeClaim(
                id="top-3",
                text="Top also shares Quibdo.",
                source_document_id=top.id,
                entity_ids=["ent-b"],
            )
        )
        db.save(
            KnowledgeClaim(
                id="second-1",
                text="Second only shares Mining.",
                source_document_id=second.id,
                entity_ids=["ent-c"],
            )
        )
        db.save(
            KnowledgeClaim(
                id="outsider-1",
                text="Outsider mentions an unrelated thing.",
                source_document_id=outsider.id,
                entity_ids=["ent-outsider"],
            )
        )

        response = client.get(f"/api/documents/{seed.id}/related?limit=10")

        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 2
        assert [item["document_id"] for item in payload["items"]] == [top.id, second.id]
        assert payload["items"][0]["shared_entities"] == 2
        assert payload["items"][1]["shared_entities"] == 1
        assert seed.id not in {item["document_id"] for item in payload["items"]}
        assert outsider.id not in {item["document_id"] for item in payload["items"]}
        assert set(payload["items"][0]["sample_entity_names"]) == {"Leidy", "Quibdo"}
        assert payload["items"][1]["sample_entity_names"] == ["Mining"]

    def test_direct_helper_ignores_malformed_entity_payloads(self, db):
        seed = _make_doc(db, "Seed")
        peer = _make_doc(db, "Peer")
        db.save(KnowledgeEntity(id="ent-valid", canonical_name="Valid Entity"))
        db.save(
            KnowledgeClaim(
                id="seed-bad-json",
                text="Malformed payload",
                source_document_id=seed.id,
                entity_ids=[],
            )
        )
        db._execute(
            "UPDATE knowledgeclaims SET entity_ids = $raw WHERE id = $id",
            {"raw": '{"unexpected": "shape"}', "id": "seed-bad-json"},
        )
        db.save(
            KnowledgeClaim(
                id="seed-valid",
                text="Valid payload",
                source_document_id=seed.id,
                entity_ids=["ent-valid"],
            )
        )
        db.save(
            KnowledgeClaim(
                id="peer-valid",
                text="Peer shares the valid entity",
                source_document_id=peer.id,
                entity_ids=["ent-valid"],
            )
        )

        response = asyncio.run(related_documents(seed.id, limit=10, db=db))

        assert response.count == 1
        assert [item.document_id for item in response.items] == [peer.id]
        assert response.items[0].sample_entity_names == ["Valid Entity"]


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

        real_query_in = Database.query_in

        def flaky_query_in(self, model, column, values):
            rows = real_query_in(self, model, column, values)
            if model is Document and column == "id":
                return [row for row in rows if row.id != stale_child.id]
            return rows

        monkeypatch.setattr(Database, "query_in", flaky_query_in)

        r = client.get(f"/api/documents/{parent.id}/children")

        assert r.status_code == 200
        ids = [d["id"] for d in r.json()["items"]]
        assert good_child.id in ids
        assert stale_child.id not in ids

    def test_parent_browse_batches_child_resolution(self, client, db, monkeypatch):
        from fichero.db import Database

        parent = _make_doc(db, "Parent")
        first = _make_ordered_doc(db, "First", sort_order=0, parent_id=parent.id)
        second = _make_ordered_doc(db, "Second", sort_order=1, parent_id=parent.id)
        third = _make_ordered_doc(db, "Third", sort_order=2, parent_id=parent.id)
        child_ids = {first.id, second.id, third.id}

        real_get = Database.get
        real_query_in = Database.query_in
        child_gets: list[str] = []
        query_in_calls: list[tuple[str, tuple[str, ...]]] = []

        def counting_get(self, model, doc_id):
            if model is Document and doc_id in child_ids:
                child_gets.append(doc_id)
            return real_get(self, model, doc_id)

        def counting_query_in(self, model, column, values):
            if model is Document and column == "id":
                query_in_calls.append((column, tuple(values)))
            return real_query_in(self, model, column, values)

        monkeypatch.setattr(Database, "get", counting_get)
        monkeypatch.setattr(Database, "query_in", counting_query_in)

        r = client.get(f"/api/documents?parent_id={parent.id}")

        assert r.status_code == 200
        assert [item["name"] for item in r.json()["items"]] == [
            "First",
            "Second",
            "Third",
        ]
        assert child_gets == []
        assert len(query_in_calls) == 1
        assert query_in_calls[0][0] == "id"
        assert set(query_in_calls[0][1]) == child_ids


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

    def test_create_route_offloads_sync_write_impl_to_thread(
        self, db, monkeypatch
    ):
        request = documents_routes.DocumentCreate(name="Threaded Doc")
        doc = Document(id="threaded-doc", name="Threaded Doc", doc_type=DocType.file)
        to_thread = AsyncMock(return_value=doc)
        emitted: list[list[str]] = []

        monkeypatch.setattr(documents_routes.asyncio, "to_thread", to_thread)
        monkeypatch.setattr(
            documents_routes,
            "emit_change",
            lambda *_args, document_ids, **_kwargs: emitted.append(document_ids),
        )

        result = asyncio.run(
            documents_routes.create_document(
                doc=request,
                db=db,
                x_fichero_library_path="/tmp/library.fichero",
                actor="tester",
            )
        )

        to_thread.assert_awaited_once()
        assert to_thread.await_args.args == (
            documents_routes.create_document_impl,
            db,
            request,
        )
        assert result is doc
        assert emitted == [["threaded-doc"]]

    def test_slow_create_write_does_not_starve_event_loop(self, db, monkeypatch):
        request = documents_routes.DocumentCreate(name="Slow Doc")
        doc = Document(id="slow-doc", name="Slow Doc", doc_type=DocType.file)
        emitted: list[list[str]] = []

        def slow_create_impl(_db, _request):
            time.sleep(0.05)
            return doc

        monkeypatch.setattr(
            documents_routes, "create_document_impl", slow_create_impl
        )
        monkeypatch.setattr(
            documents_routes,
            "emit_change",
            lambda *_args, document_ids, **_kwargs: emitted.append(document_ids),
        )

        async def run_with_probe():
            write_task = asyncio.create_task(
                documents_routes.create_document(
                    doc=request,
                    db=db,
                    x_fichero_library_path="/tmp/library.fichero",
                    actor="tester",
                )
            )
            started_at = time.perf_counter()
            await asyncio.sleep(0.01)
            probe_elapsed = time.perf_counter() - started_at
            result = await write_task
            return probe_elapsed, result

        probe_elapsed, result = asyncio.run(run_with_probe())

        assert probe_elapsed < 0.04
        assert result is doc
        assert emitted == [["slow-doc"]]

    @pytest.mark.parametrize(
        ("route", "impl", "args", "thread_result"),
        [
            (
                documents_routes.update_document,
                documents_routes.update_document_impl,
                ("doc-1", documents_routes.DocumentUpdate(page_content="updated")),
                (
                    Document(id="doc-1", name="Doc", page_content="updated"),
                    {},
                    ["page_content"],
                ),
            ),
            (
                documents_routes.move_document,
                documents_routes.move_document_impl,
                ("doc-1", "parent-1"),
                (Document(id="doc-1", name="Doc", parent_id="parent-1"), {}),
            ),
            (
                documents_routes.delete_document,
                documents_routes.delete_document_impl,
                ("doc-1",),
                (["doc-1"], []),
            ),
        ],
    )
    def test_write_routes_offload_sync_db_work_to_thread(
        self, db, monkeypatch, route, impl, args, thread_result
    ):
        to_thread = AsyncMock(return_value=thread_result)
        emitted: list[tuple[str, list[str]]] = []

        monkeypatch.setattr(documents_routes.asyncio, "to_thread", to_thread)
        monkeypatch.setattr(
            documents_routes,
            "emit_change",
            lambda *_args, type, document_ids, **_kwargs: emitted.append(
                (type, document_ids)
            ),
        )

        kwargs = {
            "db": db,
            "x_fichero_library_path": "/tmp/library.fichero",
            "actor": "tester",
        }
        if route is documents_routes.move_document:
            kwargs["parent_id"] = args[1]
            call_args = (args[0],)
            expected_thread_args = (impl, db, args[0], args[1])
        elif route is documents_routes.delete_document:
            call_args = (args[0],)
            expected_thread_args = (impl, db, args[0])
        else:
            call_args = args
            expected_thread_args = (impl, db, *args)

        asyncio.run(route(*call_args, **kwargs))

        to_thread.assert_awaited_once()
        assert to_thread.await_args.args == expected_thread_args
        if route is documents_routes.delete_document:
            assert to_thread.await_args.kwargs == {"actor": "tester"}
            assert emitted == [("document.deleted", ["doc-1"])]
        else:
            assert to_thread.await_args.kwargs == {}
            assert emitted == [("document.updated", ["doc-1"])]


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

    def test_import_offloads_sync_ingest_work_to_thread(
        self, db, tmp_path, monkeypatch
    ):
        class FakeRequest:
            headers = {"content-length": "12"}

        class FakeUpload:
            filename = "analysis-mining-terms.md"

        temp_path = tmp_path / "fichero_upload_tmp.md"
        temp_path.write_text("# Analysis\n", encoding="utf-8")
        doc = Document(
            id="imported-doc",
            name="analysis-mining-terms.md",
            doc_type=DocType.file,
        )
        to_thread = AsyncMock(return_value=doc)
        emitted: list[list[str]] = []

        async def fake_save_uploaded_file(file, *, content_length=None):
            assert file.filename == "analysis-mining-terms.md"
            assert content_length == "12"
            return temp_path

        monkeypatch.setattr(storage_module, "save_uploaded_file", fake_save_uploaded_file)
        monkeypatch.setattr(documents_routes.asyncio, "to_thread", to_thread)
        monkeypatch.setattr(
            documents_routes,
            "emit_change",
            lambda *_args, document_ids, **_kwargs: emitted.append(document_ids),
        )

        result = asyncio.run(
            documents_routes.import_file(
                request=FakeRequest(),
                file=FakeUpload(),
                parent_id="parent-1",
                db=db,
                x_fichero_library_path="/tmp/library.fichero",
                actor="tester",
            )
        )

        to_thread.assert_awaited_once()
        assert to_thread.await_args.args == (
            documents_routes.import_uploaded_file_impl,
            db,
            temp_path,
        )
        assert to_thread.await_args.kwargs == {
            "original_filename": "analysis-mining-terms.md",
            "parent_id": "parent-1",
        }
        assert result is doc
        assert emitted == [[doc.id]]
        assert not temp_path.exists()

    def test_import_rejects_oversized_upload_with_413(self, client, db, monkeypatch):
        monkeypatch.setattr(storage_module.settings, "max_upload_bytes", 128)

        r = client.post(
            "/api/documents/import",
            files={"file": ("too-large.bin", b"x" * 512, "application/octet-stream")},
        )

        assert r.status_code == 413, r.text
        assert "maximum allowed size" in r.json()["detail"]
        assert len(client.get("/api/documents").json()["items"]) == 1

    # NOTE: the streaming-internals unit test (exact read_calls, asyncio.run on a
    # mock upload) was order-flaky under full-suite ordering — the UploadTooLargeError
    # escaped pytest.raises due to event-loop pollution from neighbouring async tests.
    # The cap is covered end-to-end by test_import_rejects_oversized_upload_with_413
    # (route-level, deterministic). Follow-up #2186 to re-add a robust async-isolated
    # streaming unit test.


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

    def test_update_ignores_parent_id_even_when_client_sends_it(self, client, db):
        parent = _make_doc(db, "Parent")
        sibling_parent = _make_doc(db, "Sibling Parent")
        child = _make_doc(db, "Child", parent_id=parent.id)

        r = client.put(
            f"/api/documents/{child.id}",
            json={"name": "Renamed Child", "parent_id": sibling_parent.id},
        )

        assert r.status_code == 200
        payload = r.json()
        assert payload["name"] == "Renamed Child"
        assert payload["parent_id"] == parent.id
        assert db.get(Document, child.id).parent_id == parent.id

    def test_update_page_content_merges_metadata_and_marks_user_edit(self, client, db, monkeypatch):
        doc = Document(
            name="Transcript",
            doc_type=DocType.file,
            metadata={"existing": "keep"},
            page_content="before",
        )
        db.save(doc)
        embed_calls: list[str] = []
        monkeypatch.setattr(type(db), "embed", lambda self, saved_doc: embed_calls.append(saved_doc.id))

        r = client.put(
            f"/api/documents/{doc.id}",
            json={"page_content": "after", "metadata": {"source": "manual"}},
        )

        assert r.status_code == 200
        payload = r.json()
        assert payload["page_content"] == "after"
        assert payload["metadata"]["existing"] == "keep"
        assert payload["metadata"]["source"] == "manual"
        assert payload["metadata"]["page_content_user_edited_at"]
        assert embed_calls == [doc.id]

    def test_update_position_round_trips(self, client):
        create = client.post("/api/documents", json={"name": "Positioned Node"})
        assert create.status_code == 201
        doc_id = create.json()["id"]
        assert create.json().get("position_x") is None
        assert create.json().get("position_y") is None
        assert create.json().get("position_z") is None
        assert create.json().get("rotation_z") is None
        assert create.json().get("scale") is None
        assert create.json().get("z_index") == 0

        update = client.put(
            f"/api/documents/{doc_id}",
            json={
                "position_x": 120.5,
                "position_y": 240.0,
                "position_z": 1.0,
                "rotation_z": 45.0,
                "scale": 1.25,
                "z_index": 3,
            },
        )
        assert update.status_code == 200
        payload = update.json()
        assert payload["position_x"] == 120.5
        assert payload["position_y"] == 240.0
        assert payload["position_z"] == 1.0
        assert payload["rotation_z"] == 45.0
        assert payload["scale"] == 1.25
        assert payload["z_index"] == 3

        single = client.get(f"/api/documents/{doc_id}")
        assert single.status_code == 200
        assert single.json()["position_x"] == 120.5
        assert single.json()["position_y"] == 240.0
        assert single.json()["position_z"] == 1.0
        assert single.json()["rotation_z"] == 45.0
        assert single.json()["scale"] == 1.25
        assert single.json()["z_index"] == 3

        list_resp = client.get("/api/documents")
        assert list_resp.status_code == 200
        item = next(i for i in list_resp.json()["items"] if i["id"] == doc_id)
        assert item["position_x"] == 120.5
        assert item["position_y"] == 240.0
        assert item["position_z"] == 1.0
        assert item["rotation_z"] == 45.0
        assert item["scale"] == 1.25
        assert item["z_index"] == 3


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

    def test_batch_exclude_deduplicates_and_skips_blank_ids(self, client, db):
        doc = _make_doc(db, "Doc A")

        r = client.patch(
            "/api/documents/batch-exclude",
            json={
                "document_ids": ["", "  ", doc.id, doc.id],
                "excluded": True,
                "reason": "curation",
            },
        )

        assert r.status_code == 200
        payload = r.json()
        assert payload["updated"] == 1
        assert payload["document_ids"] == [doc.id]
        assert db.get(Document, doc.id).exclude_from_processing is True

        logs = [m for m in db.query(MutationLog) if m.entity_id == doc.id]
        assert len(logs) == 1

    def test_batch_exclude_missing_document_returns_404(self, client):
        r = client.patch(
            "/api/documents/batch-exclude",
            json={
                "document_ids": ["missing-doc"],
                "excluded": True,
                "reason": "curation",
            },
        )

        assert r.status_code == 404
        assert r.json()["detail"] == "Document not found: missing-doc"


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
    def test_assigns_builtin_prototype_against_fresh_db_fixture(self, client, db):
        doc = _make_doc(db, "Fresh Fixture Letter")

        response = client.put(
            f"/api/documents/{doc.id}/prototype",
            json={"prototype_key": "letter"},
        )

        assert response.status_code == 200
        assert db.get(Document, doc.id).prototype_key == "letter"

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


# ---------------------------------------------------------------------------
# node_kind round-trip (#2591)
# ---------------------------------------------------------------------------

class TestNodeKind:
    def test_default_node_kind_is_document(self, client):
        r = client.get("/api/documents")
        assert r.status_code == 200
        inbox = next(item for item in r.json()["items"] if item["name"] == "Inbox")
        assert inbox["node_kind"] == "document"

    def test_create_document_with_node_kind(self, client):
        r = client.post("/api/documents", json={"name": "Task A", "node_kind": "task"})
        assert r.status_code == 201
        assert r.json()["node_kind"] == "task"

    def test_update_document_node_kind(self, client, db):
        doc = _make_doc(db, "Doc")
        r = client.put(f"/api/documents/{doc.id}", json={"node_kind": "workspace"})
        assert r.status_code == 200
        assert r.json()["node_kind"] == "workspace"
        r = client.get(f"/api/documents/{doc.id}")
        assert r.json()["node_kind"] == "workspace"

    def test_list_documents_filter_by_node_kind(self, client, db):
        _make_doc(db, "Plain Doc")
        r = client.post("/api/documents", json={"name": "Saved Search A", "node_kind": "saved_search"})
        assert r.status_code == 201

        r = client.get("/api/documents?node_kind=saved_search")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["name"] == "Saved Search A"
        assert items[0]["node_kind"] == "saved_search"
