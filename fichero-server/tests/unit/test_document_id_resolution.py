"""#2462 — GET /api/documents/{id} must resolve the same way /children and /outline do.

Root cause: document_outline and inspector were missing _normalize_document_id,
so doc:-prefixed IDs would 404 there while /children and GET (which both normalize)
returned 200. After the fix all three handlers normalize the prefix and apply the
same soft-delete filter.

Scenarios verified:
  1. Bare id — GET, /children, /outline all return 200 for a live document.
  2. doc:-prefixed id — all three normalize and return 200.
  3. GET and /outline agree on soft-deleted docs (both 404); /children may still
     return 200 when children exist (intentional workflow-tolerance behaviour, not
     part of this fix).
  4. Genuinely missing id returns 404 even after prefix normalization.
"""

from datetime import datetime, timezone

from fichero_server.models import Document, DocType


def _make_doc(db, name: str = "Doc", parent_id: str | None = None) -> Document:
    doc = Document(name=name, parent_id=parent_id, doc_type=DocType.file)
    db.save(doc)
    return doc


def _soft_delete(db, doc: Document) -> Document:
    doc.deleted_at = datetime.now(tz=timezone.utc)
    db.save(doc)
    return doc


# ---------------------------------------------------------------------------
# Bare id — happy path
# ---------------------------------------------------------------------------


class TestBareIdResolution:
    def test_get_resolves_when_outline_resolves(self, client, db):
        doc = _make_doc(db)
        assert client.get(f"/api/documents/{doc.id}/outline").status_code == 200
        r = client.get(f"/api/documents/{doc.id}")
        assert r.status_code == 200
        assert r.json()["id"] == doc.id

    def test_get_resolves_when_children_resolves(self, client, db):
        parent = _make_doc(db, "Parent")
        _make_doc(db, "Child", parent_id=parent.id)
        assert client.get(f"/api/documents/{parent.id}/children").status_code == 200
        r = client.get(f"/api/documents/{parent.id}")
        assert r.status_code == 200
        assert r.json()["id"] == parent.id


# ---------------------------------------------------------------------------
# doc:-prefixed id — the #2462 regression
# ---------------------------------------------------------------------------


class TestDocPrefixedIdResolution:
    def test_all_three_handlers_accept_doc_prefix(self, client, db):
        """#2462: outline and inspector were missing normalization; doc: prefix caused 404."""
        parent = _make_doc(db, "Parent")
        _make_doc(db, "Child", parent_id=parent.id)
        prefixed = f"doc:{parent.id}"

        children_r = client.get(f"/api/documents/{prefixed}/children")
        outline_r = client.get(f"/api/documents/{prefixed}/outline")
        get_r = client.get(f"/api/documents/{prefixed}")

        assert children_r.status_code == 200, f"/children {children_r.status_code}"
        assert outline_r.status_code == 200, f"/outline {outline_r.status_code}"
        assert get_r.status_code == 200, f"GET {get_r.status_code}"
        assert get_r.json()["id"] == parent.id

    def test_doc_prefixed_and_bare_return_same_document(self, client, db):
        doc = _make_doc(db)
        bare = client.get(f"/api/documents/{doc.id}")
        prefixed = client.get(f"/api/documents/doc:{doc.id}")
        assert bare.status_code == 200
        assert prefixed.status_code == 200
        assert bare.json()["id"] == prefixed.json()["id"]

    def test_doc_prefix_missing_document_is_404(self, client):
        r = client.get("/api/documents/doc:no-such-id")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Soft-delete consistency: GET and /outline must agree
# ---------------------------------------------------------------------------


class TestSoftDeleteConsistency:
    def test_get_and_outline_agree_on_soft_deleted_doc(self, client, db):
        """Both GET and /outline apply the soft-delete filter — they must agree."""
        doc = _make_doc(db)
        _soft_delete(db, doc)

        get_r = client.get(f"/api/documents/{doc.id}")
        outline_r = client.get(f"/api/documents/{doc.id}/outline")

        assert get_r.status_code == outline_r.status_code == 404

    def test_soft_deleted_with_doc_prefix_also_404(self, client, db):
        doc = _make_doc(db)
        _soft_delete(db, doc)

        assert client.get(f"/api/documents/doc:{doc.id}").status_code == 404
        assert client.get(f"/api/documents/doc:{doc.id}/outline").status_code == 404
