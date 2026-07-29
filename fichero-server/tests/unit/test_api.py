"""
Tests for Fichero REST API

Uses pytest and httpx for async testing of FastAPI endpoints.
"""

import tempfile
from importlib.metadata import version as package_version
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request

from fichero_server.actions.registry import ActionResult
from fichero_server.models import ActionAudit
from fichero_server.models import Document, DocType, FileType, Status, Artifact


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
        doc_type=DocType.folder,
        status=Status.completed,
    )


@pytest.fixture
def record_background_task():
    """Prevent TestClient from running scheduled background ingestion."""
    with patch("starlette.background.BackgroundTasks.add_task") as add_task:
        yield add_task


class TestHealthEndpoint:
    """Tests for /api/health endpoint."""

    def test_health_check(self, client):
        """Health endpoint returns status."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["backend_version"] == package_version("fichero-server")

    def test_library_health_includes_backend_version(self, client, test_package):
        """Library-scoped health keeps the same version reporting."""
        response = client.get(
            "/api/health",
            headers={"X-Fichero-Library-Path": str(test_package)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["backend_version"] == package_version("fichero-server")


class TestStatsEndpoint:
    """Tests for /api/stats endpoint."""

    def test_get_stats(self, client, db, sample_doc):
        """Stats endpoint returns counts including the default Inbox."""
        # Add some test data
        db.save(sample_doc)

        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert data["documents"] == 2


class TestDocumentRoutes:
    """Tests for /api/documents endpoints."""

    def test_list_documents(self, client, db, sample_doc):
        """List documents returns array including the default Inbox."""
        db.save(sample_doc)

        response = client.get("/api/documents")
        assert response.status_code == 200
        data = response.json()["items"]
        assert isinstance(data, list)
        assert len(data) == 2
        assert any(item["id"] == sample_doc.id for item in data)

    def test_list_documents_with_filters(self, client, db, sample_doc):
        """List documents with type filter."""
        db.save(sample_doc)

        response = client.get("/api/documents?doc_type=file")
        assert response.status_code == 200
        data = response.json()["items"]
        assert len(data) == 1

    def test_list_collections(self, client, db, sample_collection):
        """List collections returns root folders including the default Inbox."""
        db.save(sample_collection)

        response = client.get("/api/documents/collections")
        assert response.status_code == 200
        data = response.json()["items"]
        assert isinstance(data, list)
        assert len(data) == 2
        assert all(item["doc_type"] == "folder" for item in data)
        assert any(item["name"] == "Inbox" for item in data)
        assert any(item["id"] == sample_collection.id for item in data)

    def test_get_document_found(self, client, db, sample_doc):
        """Get document by ID returns document."""
        db.save(sample_doc)

        response = client.get(f"/api/documents/{sample_doc.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_doc.id
        assert data["name"] == sample_doc.name

    def test_get_document_not_found(self, client, db):
        """Get document returns 404 if not found."""
        response = client.get("/api/documents/nonexistent")
        assert response.status_code == 404

    def test_get_document_workflow_runs(self, client, db, sample_doc):
        """Read the recorded workflow provenance for a document."""
        sample_doc.workflow_runs = [
            {
                "thread_id": "thread-123",
                "workflow_id": "wf-123",
                "workflow_name": "Transcribe",
                "model": "gpt-4o-mini",
                "result": {"status": "completed", "pages": 1},
                "started_at": "2026-05-31T10:00:00Z",
                "completed_at": "2026-05-31T10:02:30Z",
            }
        ]
        db.save(sample_doc)

        response = client.get(f"/api/documents/{sample_doc.id}/workflow-runs")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["items"][0]["workflow_id"] == "wf-123"
        assert data["items"][0]["model"] == "gpt-4o-mini"
        assert data["items"][0]["result"]["pages"] == 1

    def test_get_document_workflow_runs_skips_malformed_rows(self, client, db, sample_doc):
        """Malformed legacy rows should be ignored, not fail the whole response."""
        sample_doc.workflow_runs = [
            {"thread_id": "missing-workflow-id"},
            {
                "thread_id": "thread-123",
                "workflow_id": "wf-123",
                "workflow_name": "Transcribe",
                "result": {"status": "completed"},
            },
        ]
        db.save(sample_doc)

        response = client.get(f"/api/documents/{sample_doc.id}/workflow-runs")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["items"][0]["workflow_id"] == "wf-123"

    def test_get_children(self, client, db, sample_doc, sample_collection):
        """Get children of a document."""
        db.save(sample_collection)
        sample_doc.parent_id = sample_collection.id
        db.save(sample_doc)

        response = client.get(f"/api/documents/{sample_collection.id}/children")
        assert response.status_code == 200
        data = response.json()["items"]
        assert isinstance(data, list)
        assert len(data) == 1

    def test_get_children_resolvability_check_uses_one_batched_lookup(
        self, client, db, sample_collection, monkeypatch
    ):
        """Child browsing must not regress to one DB lookup per child."""
        from fichero_server.db import Database

        db.save(sample_collection)
        children = [
            Document(
                id=f"child-{idx}",
                name=f"Child {idx}",
                doc_type=DocType.page,
                parent_id=sample_collection.id,
                sort_order=idx,
            )
            for idx in range(5)
        ]
        for child in children:
            db.save(child)

        query_in_calls: list[tuple[type, str, tuple[str, ...]]] = []
        document_get_ids: list[str] = []
        original_query_in = Database.query_in
        original_get = Database.get

        def counting_query_in(self, model_class, field_name, values):
            query_in_calls.append((model_class, field_name, tuple(values)))
            return original_query_in(self, model_class, field_name, values)

        def counting_get(self, model_class, record_id):
            if model_class is Document:
                document_get_ids.append(record_id)
            return original_get(self, model_class, record_id)

        monkeypatch.setattr(Database, "query_in", counting_query_in)
        monkeypatch.setattr(Database, "get", counting_get)

        response = client.get(f"/api/documents/{sample_collection.id}/children")

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == [
            child.id for child in children
        ]
        assert query_in_calls == [
            (Document, "id", tuple(child.id for child in children))
        ]
        assert document_get_ids == []

    def test_get_children_doc_prefix(self, client, db, sample_doc, sample_collection):
        """GET /children accepts a doc:-prefixed id and returns the same result (#1345).

        During folder catalogue runs the caller sometimes URL-encodes a
        ``doc:<hex>`` id (e.g. ``doc%3Acoll123``). FastAPI decodes the percent
        encoding, leaving the literal ``doc:`` prefix in the path parameter.
        The handler must strip the prefix before the DB lookup, otherwise the
        exact-match query misses and returns 404.
        """
        db.save(sample_collection)
        sample_doc.parent_id = sample_collection.id
        db.save(sample_doc)

        # Simulate caller passing the doc:-prefixed form
        prefixed_id = f"doc:{sample_collection.id}"
        response = client.get(f"/api/documents/{prefixed_id}/children")
        assert response.status_code == 200
        data = response.json()["items"]
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == sample_doc.id

    def test_create_document(self, client, db):
        """Create document returns new document."""
        response = client.post("/api/documents", json={
            "name": "new_doc.jpg",
            "doc_type": "file",
            "file_type": "image",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "new_doc.jpg"

    def test_create_document_with_parent(self, client, db, sample_collection):
        """Create document with parent ID verifies parent exists."""
        db.save(sample_collection)

        response = client.post("/api/documents", json={
            "name": "child_doc.jpg",
            "parent_id": sample_collection.id,
            "doc_type": "file",
        })
        assert response.status_code == 201

    def test_create_document_invalid_parent(self, client, db):
        """Create document with invalid parent returns 400."""
        response = client.post("/api/documents", json={
            "name": "orphan_doc.jpg",
            "parent_id": "nonexistent",
            "doc_type": "file",
        })
        assert response.status_code == 400

    def test_update_document(self, client, db, sample_doc):
        """Update document modifies fields."""
        db.save(sample_doc)

        response = client.put(f"/api/documents/{sample_doc.id}", json={
            "name": "renamed.jpg",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "renamed.jpg"

    def test_update_document_not_found(self, client, db):
        """Update nonexistent document returns 404."""
        response = client.put("/api/documents/nonexistent", json={
            "name": "renamed.jpg",
        })
        assert response.status_code == 404

    def test_delete_document(self, client, db, sample_doc):
        """Delete document soft-deletes it."""
        db.save(sample_doc)

        response = client.delete(f"/api/documents/{sample_doc.id}")
        assert response.status_code == 204
        persisted = db.get(Document, sample_doc.id)
        assert persisted is not None
        assert persisted.deleted_at is not None

    def test_delete_document_cascades_soft_delete_to_descendants(self, client, db):
        """Delete document soft-deletes descendants."""
        parent = Document(name="Parent", doc_type=DocType.folder)
        child = Document(name="Child", doc_type=DocType.file, parent_id=parent.id, file_type=FileType.image)
        grandchild = Document(name="Grandchild", doc_type=DocType.file, parent_id=child.id, file_type=FileType.image)
        child_artifact = Artifact(
            document_id=child.id,
            artifact_type="transcription",
            content="sample",
        )

        db.save(parent)
        db.save(child)
        db.save(grandchild)
        db.save(child_artifact)

        response = client.delete(f"/api/documents/{parent.id}")
        assert response.status_code == 204

        assert db.get(Document, parent.id).deleted_at is not None
        assert db.get(Document, child.id).deleted_at is not None
        assert db.get(Document, grandchild.id).deleted_at is not None
        assert db.get(Artifact, child_artifact.id) is not None

    def test_delete_document_not_found(self, client, db):
        """Delete nonexistent document returns 404."""
        response = client.delete("/api/documents/nonexistent")
        assert response.status_code == 404

    def test_cleanup_orphan_documents(self, client, db):
        """Cleanup endpoint removes unreachable orphan documents."""
        root = Document(name="Root", doc_type=DocType.folder)
        child = Document(name="Child", doc_type=DocType.file, parent_id=root.id, file_type=FileType.image)
        orphan = Document(name="Orphan", doc_type=DocType.file, parent_id="missing-parent", file_type=FileType.image)
        orphan_artifact = Artifact(
            document_id=orphan.id,
            artifact_type="transcription",
            content="orphan artifact",
        )

        db.save(root)
        db.save(child)
        db.save(orphan)
        db.save(orphan_artifact)

        response = client.post("/api/documents/cleanup-orphans")
        assert response.status_code == 200
        payload = response.json()
        assert payload["orphaned_documents_deleted"] == 1
        assert payload["artifacts_deleted"] == 1

        assert db.get(Document, root.id) is not None
        assert db.get(Document, child.id) is not None
        assert db.get(Document, orphan.id) is None
        assert db.get(Artifact, orphan_artifact.id) is None


class TestSearchRoutes:
    """Tests for /api/search endpoints."""

    def test_semantic_search(self, client, db, sample_doc):
        """Semantic search returns results."""
        # Add doc with page_content for search
        sample_doc.page_content = "test content for searching"
        db.save(sample_doc)

        response = client.post("/api/search", json={
            "query": "test query",
            "limit": 10,
        })
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "count" in data

    def test_search_empty_query(self, client):
        """Search with empty / whitespace query is a 'browse the index'
        affordance and returns 200 with recent docs — see
        enhanced_search docstring.
        """
        response = client.post("/api/search", json={
            "query": "   ",
            "limit": 10,
        })
        assert response.status_code == 200

    def test_search_stats(self, client, db):
        """Search stats returns embedding info."""
        response = client.get("/api/search/stats")
        assert response.status_code == 200
        data = response.json()
        assert "indexed_count" in data
        assert "entity_indexed_count" in data
        assert "claim_indexed_count" in data


class TestIngestRoutes:
    """Tests for /api/ingest endpoints."""

    @pytest.mark.asyncio
    async def test_ingest_file_offloads_sync_import_work_to_thread(self):
        """The async route must not run file copy/OCR/embed work on the loop."""
        from fichero_server.api.routes import ingest as ingest_routes

        request = ingest_routes.IngestFileRequest(path="/tmp/input.jpg")
        http_request = Request({"type": "http", "headers": []})
        http_request.state.user = MagicMock()
        db = MagicMock()
        doc = Document(id="new123", name="ingested.jpg", doc_type=DocType.file)
        to_thread = AsyncMock(return_value=ActionResult(True, doc, "", []))

        with patch.object(ingest_routes.asyncio, "to_thread", to_thread):
            result = await ingest_routes.ingest_file(
                request,
                http_request=http_request,
                db=db,
                x_fichero_library_path="/tmp/library.fichero",
            )

        to_thread.assert_awaited_once()
        assert to_thread.await_args.args == (
            ingest_routes.registry.invoke,
            db,
            "import.file",
            request.model_dump(mode="json"),
            ingest_routes._ingest_action_context(http_request, "/tmp/library.fichero"),
        )
        assert result is doc

    def test_ingest_file(self, client):
        """Ingest file creates document."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake image data")
            temp_path = f.name

        try:
            with patch("fichero_server.importers.ingest.ingest_file") as mock_ingest:
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
            "path": str(Path(tempfile.gettempdir()) / "does-not-exist.jpg"),
        })
        assert response.status_code == 400

    def test_ingest_file_disallowed_path_forbidden(self, client):
        """Ingest paths outside the allowlist return 403."""
        response = client.post("/api/ingest/file", json={
            "path": "/nonexistent/file.jpg",
        })
        assert response.status_code == 403

    def test_ingest_folder_starts_task(self, client, record_background_task):
        """Ingest folder returns task ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "test.jpg"
            test_file.write_bytes(b"fake image data")

            with patch("fichero_server.importers.ingest.count_files") as mock_count:
                mock_count.return_value = 1

                response = client.post("/api/ingest/folder", json={
                    "path": tmpdir,
                })
                assert response.status_code == 200
                data = response.json()
                assert "task_id" in data
                assert data["status"] == "pending"
                record_background_task.assert_called_once()

    def test_ingest_folder_not_found(self, client):
        """Ingest nonexistent folder returns 400."""
        response = client.post("/api/ingest/folder", json={
            "path": str(Path(tempfile.gettempdir()) / "does-not-exist-folder"),
        })
        assert response.status_code == 400

    def test_get_ingest_status_not_found(self, client):
        """Get status of unknown task returns 404."""
        response = client.get("/api/ingest/status/nonexistent")
        assert response.status_code == 404

    def test_ingest_file_with_parameters(self, client):
        """Ingest file with all parameters."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake image data")
            temp_path = f.name

        try:
            with patch("fichero_server.importers.ingest.ingest_file") as mock_ingest:
                mock_ingest.return_value = Document(
                    id="new123",
                    name="ingested.jpg",
                    doc_type=DocType.file,
                    parent_id="parent-123",
                )

                response = client.post("/api/ingest/file", json={
                    "path": temp_path,
                    "parent_id": "parent-123",
                    "copy_mode": True,
                    "extract_text": False,
                    "auto_embed": False,
                })
                assert response.status_code == 200
                data = response.json()
                assert data["parent_id"] == "parent-123"
                
                # Verify the ingest_file was called with correct parameters
                mock_ingest.assert_called_once()
                call_args = mock_ingest.call_args
                assert call_args[1]["parent_id"] == "parent-123"
                assert call_args[1]["mode"].value == "copy"  # copy_mode=True
                assert call_args[1]["extract_text"] is False
                assert call_args[1]["auto_embed"] is False
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_ingest_file_not_a_file(self, client):
        """Ingest directory as file returns 400."""
        with tempfile.TemporaryDirectory() as tmpdir:
            response = client.post("/api/ingest/file", json={
                "path": tmpdir,
            })
            assert response.status_code == 400
            data = response.json()
            assert "detail" in data
            assert "Not a file" in data["detail"]

    def test_ingest_file_invalid_path_type(self, client):
        """Ingest with invalid path type returns 422."""
        response = client.post("/api/ingest/file", json={
            "path": 123,  # Invalid type
        })
        assert response.status_code == 422  # Validation error

    def test_ingest_file_missing_required_path(self, client):
        """Ingest file without path returns 422."""
        response = client.post("/api/ingest/file", json={
            # Missing path
        })
        assert response.status_code == 422

    def test_ingest_folder_with_parameters(self, client, record_background_task):
        """Ingest folder with all parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "file1.jpg").write_bytes(b"data1")
            (Path(tmpdir) / "file2.png").write_bytes(b"data2")

            with patch("fichero_server.importers.ingest.count_files") as mock_count:
                mock_count.return_value = 2

                response = client.post("/api/ingest/folder", json={
                    "path": tmpdir,
                    "parent_id": "parent-456",
                    "copy_mode": True,
                    "recursive": False,
                    "extract_text": True,
                    "auto_embed": True,
                })
                assert response.status_code == 200
                data = response.json()
                assert "task_id" in data
                assert data["status"] == "pending"
                assert data["path"] == tmpdir

    def test_ingest_folder_not_a_directory(self, client):
        """Ingest file as folder returns 400."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake image data")
            temp_path = f.name

        try:
            response = client.post("/api/ingest/folder", json={
                "path": temp_path,
            })
            assert response.status_code == 400
            data = response.json()
            assert "detail" in data
            assert "Not a directory" in data["detail"]
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_ingest_folder_empty_directory(self, client, record_background_task):
        """Ingest empty folder returns task ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Empty directory
            with patch("fichero_server.importers.ingest.count_files") as mock_count:
                mock_count.return_value = 0

                response = client.post("/api/ingest/folder", json={
                    "path": tmpdir,
                })
                assert response.status_code == 200
                data = response.json()
                assert "task_id" in data
                assert data["status"] == "pending"

    def test_ingest_folder_missing_required_path(self, client):
        """Ingest folder without path returns 422."""
        response = client.post("/api/ingest/folder", json={
            # Missing path
        })
        assert response.status_code == 422

    def test_get_ingest_status_valid_task(self, client, record_background_task):
        """A freshly created task reports the SCANNING state: total still 0.

        Streaming ingest (#4203) no longer counts the folder up-front — the
        total is discovered by the background walk and reported through
        ``on_progress``. Until that first callback lands, ``total`` is 0, and
        the client renders "Scanning…" rather than "0 of 0". This fixture
        suppresses the background task, so 0 is the whole contract here.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.jpg"
            test_file.write_bytes(b"fake image data")

            create_response = client.post("/api/ingest/folder", json={
                "path": tmpdir,
            })
            assert create_response.status_code == 200
            task_data = create_response.json()
            task_id = task_data["task_id"]

            status_response = client.get(f"/api/ingest/status/{task_id}")
            assert status_response.status_code == 200
            status_data = status_response.json()
            assert status_data["task_id"] == task_id
            assert status_data["status"] in ["pending", "completed", "running"]
            assert status_data["path"] == tmpdir
            assert status_data["progress"] >= 0.0
            # Scanning: total is unknown, NOT "an empty folder".
            assert status_data["total"] == 0
            assert status_data["processed"] == 0

    def test_ingest_file_different_file_types(self, client):
        """Test ingest with different file types."""
        file_types = [
            ("test.pdf", b"%PDF-1.4 fake pdf"),
            ("test.txt", b"text content"),
            ("test.png", b"\x89PNG\r\n\x1a\n fake png"),
        ]

        for filename, content in file_types:
            with tempfile.NamedTemporaryFile(suffix=filename, delete=False) as f:
                f.write(content)
                temp_path = f.name

            try:
                with patch("fichero_server.importers.ingest.ingest_file") as mock_ingest:
                    mock_ingest.return_value = Document(
                        id="test123",
                        name=filename,
                        doc_type=DocType.file,
                    )

                    response = client.post("/api/ingest/file", json={
                        "path": temp_path,
                    })
                    assert response.status_code == 200
                    data = response.json()
                    assert data["name"] == filename
            finally:
                Path(temp_path).unlink(missing_ok=True)

    def test_ingest_file_with_special_characters(self, client):
        """Test ingest file with special characters in filename."""
        special_names = [
            "test file with spaces.jpg",
            "test-file-with-dashes.jpg",
            "test_file_with_underscores.jpg",
            "test.file.with.dots.jpg",
        ]

        for filename in special_names:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                f.write(b"fake image data")
                # Rename to include special characters
                special_path = Path(f.name).parent / filename
                Path(f.name).rename(special_path)

            try:
                with patch("fichero_server.importers.ingest.ingest_file") as mock_ingest:
                    mock_ingest.return_value = Document(
                        id="test123",
                        name=filename,
                        doc_type=DocType.file,
                    )

                    response = client.post("/api/ingest/file", json={
                        "path": str(special_path),
                    })
                    assert response.status_code == 200
                    data = response.json()
                    assert data["name"] == filename
            finally:
                special_path.unlink(missing_ok=True)

    def test_ingest_endpoint_error_handling(self, client):
        """Test error handling in ingest endpoints."""
        # Test file ingest with exception
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake image data")
            temp_path = f.name

        try:
            with patch("fichero_server.importers.ingest.ingest_file") as mock_ingest:
                mock_ingest.side_effect = Exception("Test error")

                response = client.post("/api/ingest/file", json={
                    "path": temp_path,
                })
                assert response.status_code == 500
                data = response.json()
                assert "detail" in data
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_ingest_folder_recursive_parameter(self, client, record_background_task):
        """Test recursive parameter in folder ingest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested structure
            (Path(tmpdir) / "file1.jpg").write_bytes(b"data1")
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "file2.jpg").write_bytes(b"data2")

            with patch("fichero_server.importers.ingest.count_files") as mock_count:
                # Test recursive=True
                mock_count.return_value = 2
                response = client.post("/api/ingest/folder", json={
                    "path": tmpdir,
                    "recursive": True,
                })
                assert response.status_code == 200
                
                # Test recursive=False
                mock_count.return_value = 1
                response = client.post("/api/ingest/folder", json={
                    "path": tmpdir,
                    "recursive": False,
                })
                assert response.status_code == 200

    def test_ingest_status_progress_tracking(self, client, record_background_task):
        """Test progress tracking in task status."""
        # This would require more complex setup with actual background tasks
        # For now, just verify the structure
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.jpg"
            test_file.write_bytes(b"fake image data")

            with patch("fichero_server.importers.ingest.count_files") as mock_count:
                mock_count.return_value = 1

                create_response = client.post("/api/ingest/folder", json={
                    "path": tmpdir,
                })
                assert create_response.status_code == 200
                task_data = create_response.json()
                task_id = task_data["task_id"]

                # Verify status structure
                status_response = client.get(f"/api/ingest/status/{task_id}")
                assert status_response.status_code == 200
                status_data = status_response.json()
                
                # Check all expected fields are present
                expected_fields = ["task_id", "status", "path", "progress", "total", "processed"]
                for field in expected_fields:
                    assert field in status_data
                
                # Verify field types
                assert isinstance(status_data["progress"], float)
                assert isinstance(status_data["total"], int)
                assert isinstance(status_data["processed"], int)


class TestStorageRoutes:
    """Tests for /api/storage endpoints."""

    def test_storage_stats(self, client):
        """Storage stats returns info."""
        response = client.get("/api/storage/stats")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_get_thumbnail_not_found(self, client, db):
        """Get thumbnail for nonexistent doc returns 404."""
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
        data = response.json()["items"]
        assert isinstance(data, list)

    def test_get_ancestors_not_found(self, client, mock_db):
        """Get ancestors of nonexistent doc returns 404."""
        mock_db.get.return_value = None

        response = client.get("/api/documents/nonexistent/ancestors")
        assert response.status_code == 404

    def test_move_document_success(self, client, mock_db, sample_doc, sample_collection):
        """Move document to new parent successfully."""
        # Mock the document to be moved
        
        # Mock the parent document
        def get_side_effect(cls, doc_id):
            if doc_id == sample_doc.id:
                return sample_doc
            elif doc_id == sample_collection.id:
                return sample_collection
            return None
        
        mock_db.get.side_effect = get_side_effect
        mock_db.save.return_value = None

        response = client.put(f"/api/documents/{sample_doc.id}/move?parent_id={sample_collection.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_doc.id
        assert data["parent_id"] == sample_collection.id
        saved_rows = [call.args[0] for call in mock_db.save.call_args_list]
        assert sum(isinstance(row, Document) for row in saved_rows) == 1
        assert sum(isinstance(row, ActionAudit) for row in saved_rows) == 1

    def test_move_document_to_root(self, client, mock_db, sample_doc):
        """Move document to root (no parent)."""
        def get_side_effect(cls, doc_id):
            if doc_id == sample_doc.id:
                return sample_doc
            return None
        
        mock_db.get.side_effect = get_side_effect
        mock_db.save.return_value = None

        response = client.put(f"/api/documents/{sample_doc.id}/move")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_doc.id
        assert data["parent_id"] is None

    def test_move_document_not_found(self, client, mock_db):
        """Move nonexistent document returns 404."""
        mock_db.get.return_value = None

        response = client.put("/api/documents/nonexistent/move?parent_id=parent123")
        assert response.status_code == 404

    def test_move_document_invalid_parent(self, client, mock_db, sample_doc):
        """Move document to nonexistent parent returns 400."""
        def get_side_effect(cls, doc_id):
            if doc_id == sample_doc.id:
                return sample_doc  # Document exists
            return None  # Parent doesn't exist
        
        mock_db.get.side_effect = get_side_effect

        response = client.put(f"/api/documents/{sample_doc.id}/move?parent_id=nonexistent")
        assert response.status_code == 400

    def test_move_document_preserves_properties(self, client, mock_db, sample_doc, sample_collection):
        """Move document preserves other properties."""
        original_name = sample_doc.name
        original_path = sample_doc.path
        
        def get_side_effect(cls, doc_id):
            if doc_id == sample_doc.id:
                return sample_doc
            elif doc_id == sample_collection.id:
                return sample_collection
            return None
        
        mock_db.get.side_effect = get_side_effect
        mock_db.save.return_value = None

        response = client.put(f"/api/documents/{sample_doc.id}/move?parent_id={sample_collection.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == original_name
        assert data["path"] == original_path
        assert data["doc_type"] == sample_doc.doc_type.value


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


# --- Engine version resolution (health/About surface) ------------------------
# Regression guard for the Briefcase packaging mismatch: the project is named
# "fichero" but the Briefcase bundle ships only server-<ver>.dist-info, which
# made the shipped app's /health report backend_version="dev".

def test_engine_version_falls_back_to_briefcase_dist_name(monkeypatch):
    from importlib.metadata import PackageNotFoundError
    from fichero_server.api import main as api_main

    def fake_version(name: str) -> str:
        if name == "engine":
            return "2026.7.20b1"
        raise PackageNotFoundError(name)  # simulate the bundle: no "fichero" dist-info

    monkeypatch.setattr(api_main, "package_version", fake_version)
    assert api_main._resolve_engine_version() == "2026.7.20b1"


def test_engine_version_prefers_project_dist_name_in_dev(monkeypatch):
    from fichero_server.api import main as api_main

    # #4227: the project dist is named fichero-server now; it must still win
    # over the Briefcase bundle name in a dev/editable install.
    monkeypatch.setattr(
        api_main, "package_version", lambda name: "9.9.9-dev" if name == "fichero-server" else "x"
    )
    assert api_main._resolve_engine_version() == "9.9.9-dev"


def test_engine_version_is_dev_only_when_no_dist_info(monkeypatch):
    from importlib.metadata import PackageNotFoundError
    from fichero_server.api import main as api_main

    def always_missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(api_main, "package_version", always_missing)
    assert api_main._resolve_engine_version() == "dev"


def test_engine_version_resolver_covers_every_briefcase_app_name():
    """Build invariant: the resolver MUST try each Briefcase app's distribution
    name, else the shipped bundle reports 'dev' again. Ties the resolver's dist
    names to [tool.briefcase.app.*] so renaming the app forces an update here.
    """
    import inspect
    import tomllib

    from fichero_server.api import main as api_main

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    app_names = list(data["tool"]["briefcase"]["app"].keys())
    assert app_names, "expected at least one [tool.briefcase.app.*]"
    src = inspect.getsource(api_main._resolve_engine_version)
    for app in app_names:
        assert f'"{app}"' in src, f"version resolver must try Briefcase app dist name {app!r}"
