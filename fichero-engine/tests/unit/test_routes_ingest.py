"""Tests for file and folder ingestion routes.

Ingest routes accept file/folder paths and either synchronously return a
Document (single file) or immediately return a task_id for async folder
ingestion. Tests mock the underlying ingest functions to avoid touching
the real filesystem or storage layer.
"""

from unittest.mock import MagicMock, patch
from pathlib import Path

import fitz

from fichero.models import ActionAudit, DocType, Document
from fichero.api.routes import ingest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_document(doc_id: str = "doc-1", name: str = "test.pdf") -> Document:
    return Document(id=doc_id, name=name)


def _write_pdf(path, pages: list[str]) -> None:
    pdf = fitz.open()
    for text in pages:
        page = pdf.new_page()
        page.insert_text((72, 72), text)
    pdf.save(str(path))
    pdf.close()


# ---------------------------------------------------------------------------
# POST /api/ingest/file
# ---------------------------------------------------------------------------


class TestIngestFile:
    def test_route_ingest_writes_audit_and_emits_document_created(self, client, db, tmp_path, monkeypatch):
        source = tmp_path / "source.txt"
        source.write_text("source")
        emitted = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *args, **kwargs: emitted.append((args, kwargs)),
        )

        with patch("fichero.importers.ingest.ingest_file", return_value=_make_document()):
            response = client.post("/api/ingest/file", json={"path": str(source)})

        assert response.status_code == 200
        audit = db.query(ActionAudit, action_name="import.file")
        assert len(audit) == 1
        assert emitted[-1][1]["type"] == "document.created"
        assert emitted[-1][1]["document_ids"] == ["doc-1"]

    def test_rejects_server_paths_outside_allowed_roots_but_allows_library_file(
        self, client, test_package
    ):
        allowed = test_package / "imports" / "allowed.txt"
        allowed.parent.mkdir()
        allowed.write_text("safe")

        with patch("fichero.importers.ingest.ingest_file", return_value=_make_document()), \
             patch("fichero.importers.ingest.IngestMode"):
            for sensitive_path in ("/etc/passwd", str(Path.home() / ".ssh" / "id_ed25519")):
                response = client.post("/api/ingest/file", json={"path": sensitive_path})
                assert response.status_code == 403

            response = client.post("/api/ingest/file", json={"path": str(allowed)})

        assert response.status_code == 200

    def test_ingest_existing_file(self, client, tmp_path):
        test_file = tmp_path / "sample.pdf"
        test_file.write_bytes(b"%PDF-1.4")
        doc = _make_document()

        with patch("fichero.importers.ingest.ingest_file", return_value=doc), \
             patch("fichero.importers.ingest.IngestMode"):
            r = client.post("/api/ingest/file", json={"path": str(test_file)})

        # ingest_file is called and document returned
        assert r.status_code == 200

    def test_ingest_missing_file_returns_400(self, client, tmp_path):
        r = client.post("/api/ingest/file", json={"path": str(tmp_path / "missing.pdf")})
        assert r.status_code == 400
        assert "not found" in r.json()["detail"].lower()

    def test_ingest_directory_as_file_returns_400(self, client, tmp_path):
        r = client.post("/api/ingest/file", json={"path": str(tmp_path)})
        assert r.status_code == 400
        assert "not a file" in r.json()["detail"].lower()

    def test_ingest_symlinked_file_returns_400(self, client, tmp_path):
        target = tmp_path / "real.pdf"
        target.write_bytes(b"%PDF-1.4")
        link = tmp_path / "linked.pdf"
        link.symlink_to(target)

        r = client.post("/api/ingest/file", json={"path": str(link)})

        assert r.status_code == 400
        assert "symlinked file" in r.json()["detail"].lower()

    def test_ingest_file_copy_mode(self, client, tmp_path):
        test_file = tmp_path / "doc.txt"
        test_file.write_text("hello")
        doc = _make_document()

        with patch("fichero.importers.ingest.ingest_file", return_value=doc), \
             patch("fichero.importers.ingest.IngestMode"):
            r = client.post("/api/ingest/file", json={
                "path": str(test_file),
                "copy_mode": True,
            })
        assert r.status_code == 200

    def test_ingest_pdf_link_mode_creates_page_children(self, client, db, tmp_path):
        pdf = tmp_path / "book.pdf"
        _write_pdf(pdf, ["Page one", "Page two"])

        r = client.post(
            "/api/ingest/file",
            json={
                "path": str(pdf),
                "extract_text": True,
                "auto_embed": False,
            },
        )

        assert r.status_code == 200
        parent_id = r.json()["id"]
        children = db.query(Document, parent_id=parent_id, doc_type=DocType.page)
        assert [child.sequence for child in children] == [1, 2]
        assert [child.page_content for child in children] == ["Page one", "Page two"]


# ---------------------------------------------------------------------------
# POST /api/ingest/folder
# ---------------------------------------------------------------------------


class TestIngestFolder:
    def test_ingest_folder_returns_task_id(self, client, tmp_path):
        (tmp_path / "a.txt").write_text("a")

        with patch("fichero.importers.ingest.ingest_folder") as _mock_folder, \
             patch("fichero.importers.ingest.count_files", return_value=1), \
             patch("fichero.importers.ingest.IngestMode"):
            r = client.post("/api/ingest/folder", json={"path": str(tmp_path)})

        assert r.status_code == 200
        data = r.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert data["path"] == str(tmp_path)

    def test_ingest_missing_folder_returns_400(self, client, tmp_path):
        r = client.post("/api/ingest/folder", json={"path": str(tmp_path / "missing")})
        assert r.status_code == 400

    def test_ingest_file_as_folder_returns_400(self, client, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        r = client.post("/api/ingest/folder", json={"path": str(f)})
        assert r.status_code == 400
        assert "not a directory" in r.json()["detail"].lower()

    def test_background_ingest_uses_fresh_db_handle(self, client, tmp_path):
        """#1216: background folder ingest should reopen DB by library path."""
        (tmp_path / "a.txt").write_text("a")
        fresh_db = MagicMock(name="fresh_db")
        seen: dict[str, object] = {}

        def _fake_ingest_folder(*_args, **kwargs):
            seen["db"] = kwargs.get("db")
            return []

        with patch("fichero.importers.ingest.ingest_folder", side_effect=_fake_ingest_folder), \
             patch("fichero.importers.ingest.count_files", return_value=1), \
             patch("fichero.importers.ingest.IngestMode"), \
             patch("fichero.api.routes.ingest.db_manager.get_database", return_value=fresh_db):
            r = client.post("/api/ingest/folder", json={"path": str(tmp_path)})

        assert r.status_code == 200
        assert seen.get("db") is fresh_db

    def test_background_ingest_streams_per_file_created_events(self, client, tmp_path, monkeypatch):
        """#4065/#4067: folder ingest emits one ``document.created`` change event
        per successfully ingested file (and accumulates ids in the task's
        ``document_ids``) so the sidebar populates incrementally instead of
        waiting for the whole import to finish, and the completion event
        carries the full set so the store refreshes promptly when it stops."""
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        emitted: list[dict] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *args, **kwargs: emitted.append(kwargs),
        )

        def _fake_ingest_folder(*_args, **kwargs):
            on_document = kwargs.get("on_document")
            docs = [
                Document(id="doc-a", name="a.txt"),
                Document(id="doc-b", name="b.txt"),
            ]
            # Mirror the real ingest_folder: fire on_document per successful
            # file AS it lands — the streaming hook the route uses to emit
            # per-file change events.
            for doc in docs:
                if on_document is not None:
                    on_document(doc)
            return docs

        with patch("fichero.importers.ingest.ingest_folder", side_effect=_fake_ingest_folder), \
             patch("fichero.importers.ingest.count_files", return_value=2), \
             patch("fichero.importers.ingest.IngestMode"), \
             patch("fichero.api.routes.ingest.db_manager.get_database", return_value=MagicMock()):
            r = client.post("/api/ingest/folder", json={"path": str(tmp_path)})

        assert r.status_code == 200
        task_id = r.json()["task_id"]

        created = [e for e in emitted if e.get("type") == "document.created"]
        # One per-file event for each document (progressive streaming), plus
        # the action's trailing bulk completion event with the full set.
        per_file = [e for e in created if len(e["document_ids"]) == 1]
        assert {e["document_ids"][0] for e in per_file} == {"doc-a", "doc-b"}
        # The bulk completion event carries both ids and fires last.
        assert created[-1]["document_ids"] == ["doc-a", "doc-b"]

        # The task's document_ids accumulated the full set by completion.
        status = client.get(f"/api/ingest/status/{task_id}").json()
        assert status["status"] == "completed"
        assert set(status["document_ids"]) == {"doc-a", "doc-b"}


# ---------------------------------------------------------------------------
# GET /api/ingest/status/{task_id}
# ---------------------------------------------------------------------------


class TestIngestStatus:
    def test_missing_task_returns_404(self, client):
        r = client.get("/api/ingest/status/no-such-task")
        assert r.status_code == 404

    def test_task_status_after_folder_ingest(self, client, tmp_path):
        (tmp_path / "b.txt").write_text("b")

        with patch("fichero.importers.ingest.ingest_folder"), \
             patch("fichero.importers.ingest.count_files", return_value=2), \
             patch("fichero.importers.ingest.IngestMode"):
            resp = client.post("/api/ingest/folder", json={"path": str(tmp_path)})

        task_id = resp.json()["task_id"]
        r = client.get(f"/api/ingest/status/{task_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["task_id"] == task_id
        assert data["status"] in ("pending", "running", "completed", "failed")
        assert "total" in data
        assert "processed" in data

    def test_task_status_is_scoped_to_its_library(self, client, monkeypatch):
        # ponytail: patch ingest.core._tasks (the module-level dict the route
        # handlers actually read), not ingest._tasks — the package re-export
        # is a separate binding to the same original dict (#2569).
        monkeypatch.setattr(ingest.core, "_tasks", {
            "other-library": {
                "status": "completed",
                "path": "/tmp/import",
                "progress": 1.0,
                "total": 1,
                "processed": 1,
                "document_ids": ["doc-1"],
                "library_path": "/other-library.fichero",
                "finished_at": ingest.time.monotonic(),
            }
        })

        response = client.get("/api/ingest/status/other-library")

        assert response.status_code == 404

    def test_expired_terminal_tasks_are_pruned(self, monkeypatch):
        monkeypatch.setattr(ingest.core, "_tasks", {
            **{
                f"old-{index}": {
                    "status": "completed",
                    "finished_at": 0.0,
                }
                for index in range(101)
            },
            "running": {"status": "running"},
        })

        ingest._prune_tasks(now=ingest._TASK_TTL_SECONDS + 1)

        assert ingest.core._tasks == {"running": {"status": "running"}}

    def test_terminal_task_history_is_capped(self, monkeypatch):
        monkeypatch.setattr(ingest.core, "_tasks", {
            f"task-{index}": {
                "status": "completed",
                "finished_at": float(index),
            }
            for index in range(ingest._MAX_TERMINAL_TASKS + 1)
        })

        ingest._prune_tasks(now=ingest._MAX_TERMINAL_TASKS)

        assert len(ingest.core._tasks) == ingest._MAX_TERMINAL_TASKS
        assert "task-0" not in ingest.core._tasks


# ---------------------------------------------------------------------------
# Image import metadata persistence (issue #384)
# ---------------------------------------------------------------------------


class TestImageIngestMetadata:
    """Verify that image files are ingested with correct type metadata.

    These tests use a real database (via the `client` fixture) to confirm that
    metadata flows end-to-end through the route → ingest → Document chain.
    """

    def test_jpg_ingest_returns_image_file_type(self, client, tmp_path):
        """POST /api/ingest/file on a .jpg must return file_type='image'."""
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 16)  # minimal JPEG header

        r = client.post("/api/ingest/file", json={"path": str(img)})

        assert r.status_code == 200
        data = r.json()
        assert data.get("file_type") == "image", (
            f"Expected file_type='image' for .jpg, got {data.get('file_type')!r}"
        )

    def test_png_ingest_returns_image_file_type(self, client, tmp_path):
        """POST /api/ingest/file on a .png must return file_type='image'."""
        img = tmp_path / "screenshot.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)  # minimal PNG header

        r = client.post("/api/ingest/file", json={"path": str(img)})

        assert r.status_code == 200
        assert r.json().get("file_type") == "image"

    def test_image_ingest_populates_name_and_path(self, client, tmp_path):
        """Ingested image document must have name and path set."""
        img = tmp_path / "landscape.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)

        r = client.post("/api/ingest/file", json={"path": str(img)})

        assert r.status_code == 200
        data = r.json()
        assert data.get("name") == "landscape.png", (
            f"Document name should be filename, got {data.get('name')!r}"
        )
        assert data.get("path") is not None, "Document path should be populated"

    def test_heic_ingest_returns_image_file_type(self, client, tmp_path):
        """POST /api/ingest/file on a .heic must return file_type='image'."""
        img = tmp_path / "iphone_photo.heic"
        img.write_bytes(b"\x00" * 12 + b"ftyp")  # minimal HEIC-like bytes

        r = client.post("/api/ingest/file", json={"path": str(img)})

        assert r.status_code == 200
        assert r.json().get("file_type") == "image"

    def test_image_ingest_doc_type_is_file(self, client, tmp_path):
        """Ingested image must have doc_type='file', not 'folder'."""
        img = tmp_path / "avatar.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 16)

        r = client.post("/api/ingest/file", json={"path": str(img)})

        assert r.status_code == 200
        assert r.json().get("doc_type") == "file"

    def test_multiple_image_formats_ingest_correctly(self, client, tmp_path):
        """All major image formats must ingest with file_type='image'."""
        formats = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff", ".bmp"]

        for ext in formats:
            img = tmp_path / f"test{ext}"
            img.write_bytes(b"\x00" * 16)

            r = client.post("/api/ingest/file", json={"path": str(img)})
            assert r.status_code == 200, f"Failed for {ext}: {r.text}"
            assert r.json().get("file_type") == "image", (
                f"Expected file_type='image' for {ext}, got {r.json().get('file_type')!r}"
            )
