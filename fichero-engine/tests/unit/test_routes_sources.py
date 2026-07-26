"""Tests for knowledge source routes.

Sources are Documents tagged with a special metadata flag (_fichero_source).
They represent bibliographic sources (books, papers) that claims cite.
Tests verify the upsert/CRUD contract and the source-vs-document boundary.
"""

from fichero.models import Document, DocType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source_payload(title: str = "My Source", file_path: str = "/path/to/file.pdf") -> dict:
    return {
        "title": title,
        "file_path": file_path,
        "document_type": "source",
    }


def _make_non_source_doc(db, name: str = "Regular Doc") -> Document:
    doc = Document(name=name, doc_type=DocType.file)
    db.save(doc)
    return doc


# ---------------------------------------------------------------------------
# GET /api/sources
# ---------------------------------------------------------------------------


class TestListSources:
    def test_empty_list(self, client):
        r = client.get("/api/sources")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "items" in data
        assert "count" in data
        assert data["items"] == []
        assert data["count"] == 0

    def test_returns_sources(self, client):
        client.post("/api/sources", json=_source_payload("Source A"))
        client.post("/api/sources", json=_source_payload("Source B"))
        r = client.get("/api/sources")
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) == 2
        assert data["count"] == 2

    def test_excludes_non_source_documents(self, client, db):
        _make_non_source_doc(db, "Not a source")
        client.post("/api/sources", json=_source_payload("Real Source"))
        r = client.get("/api/sources")
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) == 1
        assert data["count"] == 1
        assert data["items"][0]["title"] == "Real Source"


# ---------------------------------------------------------------------------
# POST /api/sources (upsert)
# ---------------------------------------------------------------------------


class TestUpsertSource:
    def test_create_source(self, client):
        r = client.post("/api/sources", json=_source_payload("Book Title"))
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Book Title"
        assert "id" in data

    def test_wrong_document_type_rejected(self, client):
        r = client.post("/api/sources", json={
            "title": "Bad Source",
            "file_path": "/x.pdf",
            "document_type": "note",
        })
        assert r.status_code == 400

    def test_update_existing_source(self, client):
        created = client.post("/api/sources", json=_source_payload("Original")).json()
        r = client.post("/api/sources", json={
            "id": created["id"],
            "title": "Updated Title",
            "file_path": "/updated.pdf",
            "document_type": "source",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == created["id"]
        assert data["title"] == "Updated Title"


# ---------------------------------------------------------------------------
# GET /api/sources/{source_id}
# ---------------------------------------------------------------------------


class TestGetSource:
    def test_get_existing_source(self, client):
        created = client.post("/api/sources", json=_source_payload("Get Me")).json()
        r = client.get(f"/api/sources/{created['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == created["id"]

    def test_get_missing_returns_404(self, client):
        r = client.get("/api/sources/no-such-source")
        assert r.status_code == 404

    def test_get_non_source_document_returns_400(self, client, db):
        doc = _make_non_source_doc(db)
        r = client.get(f"/api/sources/{doc.id}")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# PUT /api/sources/{source_id}
# ---------------------------------------------------------------------------


class TestUpdateSource:
    def test_update_title(self, client):
        created = client.post("/api/sources", json=_source_payload("Old Title")).json()
        r = client.put(f"/api/sources/{created['id']}", json={
            "title": "New Title",
            "file_path": "/new.pdf",
            "document_type": "source",
        })
        assert r.status_code == 200
        assert r.json()["title"] == "New Title"

    def test_update_missing_returns_404(self, client):
        r = client.put("/api/sources/no-such-id", json=_source_payload())
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/sources/{source_id}
# ---------------------------------------------------------------------------


class TestDeleteSource:
    def test_delete_removes_source(self, client):
        created = client.post("/api/sources", json=_source_payload()).json()
        r = client.delete(f"/api/sources/{created['id']}")
        assert r.status_code == 204
        r2 = client.get(f"/api/sources/{created['id']}")
        assert r2.status_code == 404

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/sources/no-such-id")
        assert r.status_code == 404
