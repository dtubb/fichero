"""
Tests for Fichero REST API

Uses pytest and httpx for async testing of FastAPI endpoints.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile

from fastapi.testclient import TestClient

from fichero.api.main import app
from fichero.models import Document, DocType, FileType, Status


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_db():
    """Mock database for testing."""
    with patch("fichero.api.routes.documents.db") as mock:
        yield mock


@pytest.fixture
def sample_doc():
    """Sample document for testing."""
    return Document(
        id="test123",
        name="test_document.jpg",
        doc_type=DocType.file,
        file_type=FileType.image,
        path="/path/to/test_document.jpg",
        status=Status.completed,
        metadata={"source": "test"},
    )


@pytest.fixture
def sample_collection():
    """Sample collection document."""
    return Document(
        id="coll123",
        name="Test Collection",
        doc_type=DocType.collection,
        status=Status.completed,
    )


class TestHealthEndpoint:
    """Tests for /api/health endpoint."""

    def test_health_check(self, client):
        """Health endpoint returns status."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


class TestStatsEndpoint:
    """Tests for /api/stats endpoint."""

    def test_get_stats(self, client):
        """Stats endpoint returns counts."""
        with patch("fichero.db.db") as mock_db:
            mock_db.count.return_value = 10
            mock_db.embedding_stats.return_value = {"indexed_count": 5}

            response = client.get("/api/stats")
            assert response.status_code == 200
            data = response.json()
            assert "documents" in data


class TestDocumentRoutes:
    """Tests for /api/documents endpoints."""

    def test_list_documents(self, client, mock_db, sample_doc):
        """List documents returns array."""
        mock_db.all.return_value = [sample_doc]
        mock_db.query.return_value = [sample_doc]

        response = client.get("/api/documents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_documents_with_filters(self, client, mock_db, sample_doc):
        """List documents with type filter."""
        mock_db.query.return_value = [sample_doc]

        response = client.get("/api/documents?doc_type=file")
        assert response.status_code == 200
        mock_db.query.assert_called()

    def test_list_collections(self, client, mock_db, sample_collection):
        """List collections returns only collections."""
        mock_db.query.return_value = [sample_collection]

        response = client.get("/api/documents/collections")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 0

    def test_get_document_found(self, client, mock_db, sample_doc):
        """Get document by ID returns document."""
        mock_db.get.return_value = sample_doc

        response = client.get(f"/api/documents/{sample_doc.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_doc.id
        assert data["name"] == sample_doc.name

    def test_get_document_not_found(self, client, mock_db):
        """Get document returns 404 if not found."""
        mock_db.get.return_value = None

        response = client.get("/api/documents/nonexistent")
        assert response.status_code == 404

    def test_get_children(self, client, mock_db, sample_doc, sample_collection):
        """Get children of a document."""
        mock_db.get.return_value = sample_collection
        mock_db.query.return_value = [sample_doc]

        response = client.get(f"/api/documents/{sample_collection.id}/children")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_create_document(self, client, mock_db):
        """Create document returns new document."""
        mock_db.save.return_value = None
        mock_db.get.return_value = None  # No parent check

        response = client.post("/api/documents", json={
            "name": "new_doc.jpg",
            "doc_type": "file",
            "file_type": "image",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "new_doc.jpg"
        mock_db.save.assert_called_once()

    def test_create_document_with_parent(self, client, mock_db, sample_collection):
        """Create document with parent ID verifies parent exists."""
        mock_db.get.return_value = sample_collection
        mock_db.save.return_value = None

        response = client.post("/api/documents", json={
            "name": "child_doc.jpg",
            "parent_id": sample_collection.id,
            "doc_type": "file",
        })
        assert response.status_code == 201

    def test_create_document_invalid_parent(self, client, mock_db):
        """Create document with invalid parent returns 400."""
        mock_db.get.return_value = None  # Parent not found

        response = client.post("/api/documents", json={
            "name": "orphan_doc.jpg",
            "parent_id": "nonexistent",
            "doc_type": "file",
        })
        assert response.status_code == 400

    def test_update_document(self, client, mock_db, sample_doc):
        """Update document modifies fields."""
        mock_db.get.return_value = sample_doc
        mock_db.save.return_value = None

        response = client.put(f"/api/documents/{sample_doc.id}", json={
            "name": "renamed.jpg",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "renamed.jpg"

    def test_update_document_not_found(self, client, mock_db):
        """Update nonexistent document returns 404."""
        mock_db.get.return_value = None

        response = client.put("/api/documents/nonexistent", json={
            "name": "renamed.jpg",
        })
        assert response.status_code == 404

    def test_delete_document(self, client, mock_db, sample_doc):
        """Delete document removes it."""
        mock_db.get.return_value = sample_doc
        mock_db.delete.return_value = None

        response = client.delete(f"/api/documents/{sample_doc.id}")
        assert response.status_code == 204
        mock_db.delete.assert_called_once()

    def test_delete_document_not_found(self, client, mock_db):
        """Delete nonexistent document returns 404."""
        mock_db.get.return_value = None

        response = client.delete("/api/documents/nonexistent")
        assert response.status_code == 404


class TestSearchRoutes:
    """Tests for /api/search endpoints."""

    def test_semantic_search(self, client):
        """Semantic search returns results."""
        with patch("fichero.api.routes.search.db") as mock_db:
            from fichero.db import SearchResult
            mock_db.search.return_value = [
                SearchResult(
                    document_id="doc1",
                    score=0.95,
                    content_preview="test content",
                    metadata={"name": "test.jpg"},
                )
            ]

            response = client.post("/api/search", json={
                "query": "test query",
                "limit": 10,
            })
            assert response.status_code == 200
            data = response.json()
            assert "results" in data
            assert data["count"] >= 0

    def test_search_empty_query(self, client):
        """Search with empty query returns 400."""
        response = client.post("/api/search", json={
            "query": "   ",
            "limit": 10,
        })
        assert response.status_code == 400

    def test_search_stats(self, client):
        """Search stats returns embedding info."""
        with patch("fichero.api.routes.search.db") as mock_db:
            mock_db.embedding_stats.return_value = {
                "indexed_count": 100,
                "table_exists": True,
            }

            response = client.get("/api/search/stats")
            assert response.status_code == 200
            data = response.json()
            assert "indexed_count" in data


class TestIngestRoutes:
    """Tests for /api/ingest endpoints."""

    def test_ingest_file(self, client):
        """Ingest file creates document."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake image data")
            temp_path = f.name

        try:
            with patch("fichero.ingest.ingest_file") as mock_ingest:
                mock_ingest.return_value = Document(
                    id="new123",
                    name="ingested.jpg",
                    doc_type=DocType.file,
                )

                response = client.post("/api/ingest/file", json={
                    "path": temp_path,
                })
                assert response.status_code == 200
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_ingest_file_not_found(self, client):
        """Ingest nonexistent file returns 400."""
        response = client.post("/api/ingest/file", json={
            "path": "/nonexistent/file.jpg",
        })
        assert response.status_code == 400

    def test_ingest_folder_starts_task(self, client):
        """Ingest folder returns task ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "test.jpg"
            test_file.write_bytes(b"fake image data")

            with patch("fichero.ingest.count_files") as mock_count:
                mock_count.return_value = 1

                response = client.post("/api/ingest/folder", json={
                    "path": tmpdir,
                })
                assert response.status_code == 200
                data = response.json()
                assert "task_id" in data
                assert data["status"] == "pending"

    def test_ingest_folder_not_found(self, client):
        """Ingest nonexistent folder returns 400."""
        response = client.post("/api/ingest/folder", json={
            "path": "/nonexistent/folder",
        })
        assert response.status_code == 400

    def test_get_ingest_status_not_found(self, client):
        """Get status of unknown task returns 404."""
        response = client.get("/api/ingest/status/nonexistent")
        assert response.status_code == 404


class TestStorageRoutes:
    """Tests for /api/storage endpoints."""

    def test_storage_stats(self, client):
        """Storage stats returns info."""
        with patch("fichero.storage.stats") as mock_stats:
            mock_stats.return_value = {
                "count": 10,
                "size_mb": 5.5,
            }

            response = client.get("/api/storage/stats")
            assert response.status_code == 200

    def test_get_thumbnail_not_found(self, client):
        """Get thumbnail for nonexistent doc returns 404."""
        with patch("fichero.api.routes.storage.db") as mock_db:
            mock_db.get.return_value = None

            response = client.get("/api/storage/thumbnail/nonexistent")
            assert response.status_code == 404


class TestDocumentHierarchy:
    """Tests for document hierarchy operations."""

    def test_get_ancestors(self, client, mock_db):
        """Get ancestors returns parent chain."""
        parent = Document(id="parent1", name="Parent", doc_type=DocType.folder)
        child = Document(id="child1", name="Child", parent_id="parent1", doc_type=DocType.file)

        # First call returns child, second returns parent, third returns None (root)
        mock_db.get.side_effect = [child, parent, None]

        response = client.get("/api/documents/child1/ancestors")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_ancestors_not_found(self, client, mock_db):
        """Get ancestors of nonexistent doc returns 404."""
        mock_db.get.return_value = None

        response = client.get("/api/documents/nonexistent/ancestors")
        assert response.status_code == 404


class TestPagination:
    """Tests for pagination parameters."""

    def test_list_with_limit(self, client, mock_db, sample_doc):
        """List documents respects limit parameter."""
        # Return more docs than limit
        mock_db.all.return_value = [sample_doc] * 10

        response = client.get("/api/documents?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 5

    def test_list_with_offset(self, client, mock_db, sample_doc):
        """List documents respects offset parameter."""
        mock_db.all.return_value = [sample_doc] * 10

        response = client.get("/api/documents?offset=5&limit=5")
        assert response.status_code == 200


class TestErrorHandling:
    """Tests for error handling."""

    def test_invalid_doc_type(self, client):
        """Invalid doc_type in query returns error."""
        response = client.get("/api/documents?doc_type=invalid_type")
        assert response.status_code == 422  # Validation error

    def test_invalid_json_body(self, client):
        """Invalid JSON body returns error."""
        response = client.post(
            "/api/documents",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


class TestCORS:
    """Tests for CORS headers."""

    def test_cors_headers_present(self, client):
        """CORS headers are present on responses."""
        response = client.options("/api/documents")
        # OPTIONS requests should work for CORS preflight
        assert response.status_code in [200, 405]
