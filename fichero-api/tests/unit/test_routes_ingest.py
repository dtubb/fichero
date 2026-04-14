"""Tests for file and folder ingestion routes.

Ingest routes accept file/folder paths and either synchronously return a
Document (single file) or immediately return a task_id for async folder
ingestion. Tests mock the underlying ingest functions to avoid touching
the real filesystem or storage layer.
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fichero.models import Document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_document(doc_id: str = "doc-1", name: str = "test.pdf") -> Document:
    return Document(id=doc_id, name=name)


# ---------------------------------------------------------------------------
# POST /api/ingest/file
# ---------------------------------------------------------------------------


class TestIngestFile:
    def test_ingest_existing_file(self, client, tmp_path):
        test_file = tmp_path / "sample.pdf"
        test_file.write_bytes(b"%PDF-1.4")
        doc = _make_document()

        with patch("fichero.ingest.ingest_file", return_value=doc), \
             patch("fichero.ingest.IngestMode"):
            r = client.post("/api/ingest/file", json={"path": str(test_file)})

        # ingest_file is called and document returned
        assert r.status_code == 200

    def test_ingest_missing_file_returns_400(self, client):
        r = client.post("/api/ingest/file", json={"path": "/no/such/file.pdf"})
        assert r.status_code == 400
        assert "not found" in r.json()["detail"].lower()

    def test_ingest_directory_as_file_returns_400(self, client, tmp_path):
        r = client.post("/api/ingest/file", json={"path": str(tmp_path)})
        assert r.status_code == 400
        assert "not a file" in r.json()["detail"].lower()

    def test_ingest_file_copy_mode(self, client, tmp_path):
        test_file = tmp_path / "doc.txt"
        test_file.write_text("hello")
        doc = _make_document()

        with patch("fichero.ingest.ingest_file", return_value=doc), \
             patch("fichero.ingest.IngestMode"):
            r = client.post("/api/ingest/file", json={
                "path": str(test_file),
                "copy_mode": True,
            })
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/ingest/folder
# ---------------------------------------------------------------------------


class TestIngestFolder:
    def test_ingest_folder_returns_task_id(self, client, tmp_path):
        (tmp_path / "a.txt").write_text("a")

        with patch("fichero.ingest.ingest_folder") as _mock_folder, \
             patch("fichero.ingest.count_files", return_value=1), \
             patch("fichero.ingest.IngestMode"):
            r = client.post("/api/ingest/folder", json={"path": str(tmp_path)})

        assert r.status_code == 200
        data = r.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert data["path"] == str(tmp_path)

    def test_ingest_missing_folder_returns_400(self, client):
        r = client.post("/api/ingest/folder", json={"path": "/no/such/folder"})
        assert r.status_code == 400

    def test_ingest_file_as_folder_returns_400(self, client, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        r = client.post("/api/ingest/folder", json={"path": str(f)})
        assert r.status_code == 400
        assert "not a directory" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /api/ingest/status/{task_id}
# ---------------------------------------------------------------------------


class TestIngestStatus:
    def test_missing_task_returns_404(self, client):
        r = client.get("/api/ingest/status/no-such-task")
        assert r.status_code == 404

    def test_task_status_after_folder_ingest(self, client, tmp_path):
        (tmp_path / "b.txt").write_text("b")

        with patch("fichero.ingest.ingest_folder"), \
             patch("fichero.ingest.count_files", return_value=2), \
             patch("fichero.ingest.IngestMode"):
            resp = client.post("/api/ingest/folder", json={"path": str(tmp_path)})

        task_id = resp.json()["task_id"]
        r = client.get(f"/api/ingest/status/{task_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["task_id"] == task_id
        assert data["status"] in ("pending", "running", "completed", "failed")
        assert "total" in data
        assert "processed" in data
