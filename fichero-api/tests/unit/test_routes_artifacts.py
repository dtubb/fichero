"""Tests for artifact routes.

Artifacts are versioned outputs from AI/ML processing steps (transcription, entities,
summaries, etc.). They are always linked to a Document. SwiftUI uses these routes to
display processed results alongside source documents.
"""

import pytest
from datetime import datetime

from fichero.models import Artifact, Document, DocType, FileType, Status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(db, name: str = "test.jpg") -> Document:
    doc = Document(
        name=name,
        doc_type=DocType.file,
        file_type=FileType.image,
        path=f"/path/{name}",
        status=Status.completed,
    )
    db.save(doc)
    return doc


def _make_artifact(db, doc_id: str, artifact_type: str = "transcription", content: str = "text") -> Artifact:
    a = Artifact(
        document_id=doc_id,
        artifact_type=artifact_type,
        content=content,
        version=1,
        created_at=datetime.now(),
    )
    db.save(a)
    return a


# ---------------------------------------------------------------------------
# GET /api/artifacts/document/{doc_id}
# ---------------------------------------------------------------------------


class TestListDocumentArtifacts:
    def test_returns_empty_for_doc_with_no_artifacts(self, client, db):
        doc = _make_doc(db)
        r = client.get(f"/api/artifacts/document/{doc.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["artifacts"] == []

    def test_returns_artifact_for_document(self, client, db):
        doc = _make_doc(db)
        _make_artifact(db, doc.id, "transcription", "hello world")
        r = client.get(f"/api/artifacts/document/{doc.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["artifacts"][0]["artifact_type"] == "transcription"

    def test_404_for_missing_document(self, client):
        r = client.get("/api/artifacts/document/nonexistent-id")
        assert r.status_code == 404

    def test_filter_by_artifact_type(self, client, db):
        doc = _make_doc(db)
        _make_artifact(db, doc.id, "transcription")
        _make_artifact(db, doc.id, "summary")
        r = client.get(f"/api/artifacts/document/{doc.id}?artifact_type=summary")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["artifacts"][0]["artifact_type"] == "summary"

    def test_pagination_limit(self, client, db):
        doc = _make_doc(db)
        for i in range(5):
            _make_artifact(db, doc.id, "transcription", f"page {i}")
        r = client.get(f"/api/artifacts/document/{doc.id}?limit=2")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 5
        assert len(data["artifacts"]) == 2

    def test_pagination_offset(self, client, db):
        doc = _make_doc(db)
        for i in range(3):
            _make_artifact(db, doc.id, "transcription", f"page {i}")
        r = client.get(f"/api/artifacts/document/{doc.id}?offset=2")
        assert r.status_code == 200
        data = r.json()
        assert len(data["artifacts"]) == 1

    def test_response_fields_present(self, client, db):
        doc = _make_doc(db)
        a = _make_artifact(db, doc.id, "transcription", "content here")
        r = client.get(f"/api/artifacts/document/{doc.id}")
        assert r.status_code == 200
        artifact = r.json()["artifacts"][0]
        assert artifact["id"] == a.id
        assert artifact["document_id"] == doc.id
        assert artifact["content"] == "content here"
        assert "created_at" in artifact


# ---------------------------------------------------------------------------
# GET /api/artifacts/{artifact_id}
# ---------------------------------------------------------------------------


class TestGetArtifact:
    def test_returns_artifact_by_id(self, client, db):
        doc = _make_doc(db)
        a = _make_artifact(db, doc.id)
        r = client.get(f"/api/artifacts/{a.id}")
        assert r.status_code == 200
        assert r.json()["id"] == a.id

    def test_404_for_unknown_id(self, client):
        r = client.get("/api/artifacts/no-such-id")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/artifacts/ (list all)
# ---------------------------------------------------------------------------


class TestListAllArtifacts:
    def test_empty_library_returns_empty(self, client):
        r = client.get("/api/artifacts/")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_returns_all_artifacts(self, client, db):
        doc = _make_doc(db)
        _make_artifact(db, doc.id, "transcription")
        _make_artifact(db, doc.id, "summary")
        r = client.get("/api/artifacts/")
        assert r.status_code == 200
        assert r.json()["total"] == 2

    def test_filter_by_type(self, client, db):
        doc = _make_doc(db)
        _make_artifact(db, doc.id, "transcription")
        _make_artifact(db, doc.id, "entities")
        r = client.get("/api/artifacts/?artifact_type=entities")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["artifacts"][0]["artifact_type"] == "entities"

    def test_pagination(self, client, db):
        doc = _make_doc(db)
        for i in range(10):
            _make_artifact(db, doc.id, "transcription", f"p{i}")
        r = client.get("/api/artifacts/?limit=3&offset=7")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 10
        assert len(data["artifacts"]) == 3


# ---------------------------------------------------------------------------
# GET /api/artifacts/types
# ---------------------------------------------------------------------------


class TestListArtifactTypes:
    def test_empty_returns_empty_list(self, client):
        r = client.get("/api/artifacts/types")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_unique_types_sorted(self, client, db):
        doc = _make_doc(db)
        _make_artifact(db, doc.id, "transcription")
        _make_artifact(db, doc.id, "summary")
        _make_artifact(db, doc.id, "transcription")  # duplicate type
        r = client.get("/api/artifacts/types")
        assert r.status_code == 200
        types = r.json()
        assert types == sorted(set(types))
        assert "transcription" in types
        assert "summary" in types
        assert types.count("transcription") == 1


# ---------------------------------------------------------------------------
# DELETE /api/artifacts/{artifact_id}
# ---------------------------------------------------------------------------


class TestDeleteArtifact:
    def test_delete_existing_artifact(self, client, db):
        doc = _make_doc(db)
        a = _make_artifact(db, doc.id)
        r = client.delete(f"/api/artifacts/{a.id}")
        assert r.status_code == 204

    def test_delete_removes_from_listing(self, client, db):
        doc = _make_doc(db)
        a = _make_artifact(db, doc.id)
        client.delete(f"/api/artifacts/{a.id}")
        r = client.get("/api/artifacts/")
        assert r.json()["total"] == 0

    def test_delete_nonexistent_returns_404(self, client):
        r = client.delete("/api/artifacts/no-such-id")
        assert r.status_code == 404
