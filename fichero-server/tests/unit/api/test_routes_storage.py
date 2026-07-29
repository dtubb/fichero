"""Tests for storage and snapshot routes.

Storage routes serve thumbnails, display images, and source files from the
library package directory. Snapshots create point-in-time backups of the DB.
Tests focus on the simpler endpoints (stats, snapshots) and validate 404
behaviour without needing to mock the entire file-serving pipeline.
"""

import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import BackgroundTasks
from PIL import Image
from unittest.mock import AsyncMock, patch

import fitz

from fichero_server.db import storage as storage_module
from fichero_server.api.routes import storage as storage_routes
from fichero_server.db import Database
from fichero_server.models import Document, DocType, FileType, Status
from fichero_server.db.storage import expected_display_path, expected_thumbnail_path


# ---------------------------------------------------------------------------
# GET /api/storage/stats
# ---------------------------------------------------------------------------


class TestStorageStats:
    def test_returns_stats(self, client):
        with patch("fichero_server.db.storage.stats") as mock_stats:
            mock_stats.return_value = {
                "total_size_bytes": 1024,
                "document_count": 5,
                "thumbnail_count": 3,
            }
            r = client.get("/api/storage/stats")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/storage/thumbnail/{doc_id} — basic validation
# ---------------------------------------------------------------------------


class TestThumbnailRoute:
    def test_missing_doc_returns_404(self, client):
        r = client.get("/api/storage/thumbnail/no-such-doc")
        assert r.status_code == 404

    def test_cache_miss_offloads_thumbnail_generation_to_thread(
        self, db, tmp_path, monkeypatch
    ):
        doc = Document(
            id="thumb-offload",
            name="thumb.jpg",
            doc_type=DocType.file,
            file_type=FileType.image,
            status=Status.completed,
        )
        db.save(doc)
        generated_path = tmp_path / "thumb.jpg"
        generated_path.write_bytes(b"jpeg")
        to_thread = AsyncMock(return_value=generated_path)

        monkeypatch.setattr(storage_module, "get_thumbnail", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(storage_module, "get_display", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(storage_routes.asyncio, "to_thread", to_thread)

        response = asyncio.run(
            storage_routes.get_thumbnail(
                doc.id,
                background_tasks=BackgroundTasks(),
                db=db,
                x_fichero_library_path=str(tmp_path),
            )
        )

        # Only the main thumbnail generation is awaited; the companion display
        # generation is added as a background task (not awaited in this call).
        to_thread.assert_awaited_once()
        assert to_thread.await_args.args == (storage_module.ensure_thumbnail, doc)
        assert to_thread.await_args.kwargs == {"package_path": tmp_path, "db": db}
        assert Path(response.path) == generated_path

    def test_cache_miss_offloads_display_generation_to_thread(
        self, db, tmp_path, monkeypatch
    ):
        doc = Document(
            id="display-offload",
            name="display.jpg",
            doc_type=DocType.file,
            file_type=FileType.image,
            status=Status.completed,
        )
        db.save(doc)
        generated_path = tmp_path / "display.jpg"
        generated_path.write_bytes(b"jpeg")
        to_thread = AsyncMock(return_value=generated_path)

        monkeypatch.setattr(storage_module, "get_display", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(storage_module, "get_thumbnail", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(storage_routes.asyncio, "to_thread", to_thread)

        response = asyncio.run(
            storage_routes.get_display_image(
                doc.id,
                background_tasks=BackgroundTasks(),
                db=db,
                x_fichero_library_path=str(tmp_path),
            )
        )

        # Only the main display generation is awaited; the companion thumbnail
        # generation is added as a background task (not awaited in this call).
        to_thread.assert_awaited_once()
        assert to_thread.await_args.args == (storage_module.ensure_display, doc)
        assert to_thread.await_args.kwargs == {"package_path": tmp_path, "db": db}
        assert Path(response.path) == generated_path


class TestPdfStorageRoutes:
    @pytest.mark.parametrize(
        ("endpoint_template", "expected_content_type_prefix"),
        [
            ("/api/storage/thumbnail/doc:{doc_id}", "image/jpeg"),
            ("/api/storage/display/doc:{doc_id}", "image/jpeg"),
            ("/api/storage/source/doc:{doc_id}", "application/pdf"),
        ],
    )
    def test_doc_prefixed_storage_routes_resolve_existing_document(
        self,
        client,
        db,
        test_package,
        endpoint_template,
        expected_content_type_prefix,
    ):
        pdf_path = _write_test_pdf(test_package / "files" / "pd" / "book.pdf")
        parent = Document(
            id="pdf-parent-prefixed",
            name="book.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf_path.relative_to(test_package)),
            status=Status.completed,
            metadata={},
        )
        db.save(parent)

        response = client.get(endpoint_template.format(doc_id=parent.id))

        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            expected_content_type_prefix
        )

    @pytest.mark.parametrize(
        ("endpoint_template", "path_getter"),
        [
            ("/api/storage/thumbnail/{doc_id}", expected_thumbnail_path),
            ("/api/storage/display/{doc_id}", expected_display_path),
        ],
    )
    def test_top_level_pdf_route_renders_relative_package_path(
        self,
        client,
        db,
        test_package,
        endpoint_template,
        path_getter,
    ):
        pdf_path = _write_test_pdf(test_package / "files" / "pd" / "book.pdf")
        parent = Document(
            id="pdf-parent",
            name="book.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf_path.relative_to(test_package)),
            status=Status.completed,
            metadata={},
        )
        db.save(parent)

        response = client.get(endpoint_template.format(doc_id=parent.id))

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        _assert_valid_jpeg(response.content)
        assert path_getter(parent.id, test_package).exists()

    @pytest.mark.parametrize(
        ("endpoint_template", "path_getter"),
        [
            ("/api/storage/thumbnail/{doc_id}", expected_thumbnail_path),
            ("/api/storage/display/{doc_id}", expected_display_path),
        ],
    )
    def test_page_child_route_renders_parent_pdf_page_with_stale_child_pdf_path(
        self,
        client,
        db,
        test_package,
        endpoint_template,
        path_getter,
    ):
        pdf_path = _write_test_pdf(test_package / "files" / "pd" / "book.pdf")
        parent = Document(
            id="pdf-parent",
            name="book.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf_path.relative_to(test_package)),
            status=Status.completed,
            metadata={},
        )
        page = Document(
            id="pdf-page-2",
            name="book.pdf - Page 2",
            doc_type=DocType.page,
            parent_id=parent.id,
            sequence=2,
            status=Status.completed,
            metadata={
                "pdf_parent_id": parent.id,
                "pdf_path": "/tmp/stale-import-path.pdf",
                "page_number": 2,
            },
        )
        db.save(parent)
        db.save(page)

        parent_response = client.get(endpoint_template.format(doc_id=parent.id))
        page_response = client.get(endpoint_template.format(doc_id=page.id))

        assert parent_response.status_code == 200
        assert page_response.status_code == 200
        assert page_response.headers["content-type"] == "image/jpeg"
        _assert_valid_jpeg(page_response.content)
        assert page_response.content != parent_response.content
        assert path_getter(page.id, test_package).exists()

    def test_thumbnail_route_reuses_cached_variant_without_regeneration(
        self,
        client,
        db,
        test_package,
    ):
        pdf_path = _write_test_pdf(test_package / "files" / "pd" / "cached-book.pdf")
        parent = Document(
            id="pdf-cache-parent",
            name="cached-book.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf_path.relative_to(test_package)),
            status=Status.completed,
            metadata={},
        )
        db.save(parent)

        first = client.get(f"/api/storage/thumbnail/{parent.id}")
        assert first.status_code == 200

        cache_files = sorted(
            (test_package / "storage" / "thumbnails" / parent.id[:2].lower()).glob(
                f"{parent.id}__*.jpg"
            )
        )
        assert len(cache_files) == 1
        first_mtime_ns = cache_files[0].stat().st_mtime_ns

        second = client.get(f"/api/storage/thumbnail/{parent.id}")
        assert second.status_code == 200

        cache_files_after = sorted(
            (test_package / "storage" / "thumbnails" / parent.id[:2].lower()).glob(
                f"{parent.id}__*.jpg"
            )
        )
        assert len(cache_files_after) == 1
        assert cache_files_after[0].stat().st_mtime_ns == first_mtime_ns


class TestSourceRouteConfinement:
    def test_source_route_refuses_absolute_path_outside_library(self, client, db):
        doc = Document(
            id="outside-absolute",
            name="passwd",
            doc_type=DocType.file,
            file_type=FileType.text,
            path="/etc/passwd",
            status=Status.completed,
            metadata={},
        )
        db.save(doc)

        response = client.get(f"/api/storage/source/{doc.id}")

        assert response.status_code == 404

    def test_source_route_refuses_metadata_path_outside_library(self, client, db):
        doc = Document(
            id="outside-metadata",
            name="passwd",
            doc_type=DocType.file,
            file_type=FileType.text,
            path=None,
            status=Status.completed,
            metadata={"source_path": "/etc/passwd"},
        )
        db.save(doc)

        response = client.get(f"/api/storage/source/{doc.id}")

        assert response.status_code == 404

    def test_source_route_refuses_traversal_and_symlink_escape(
        self, client, db, test_package, tmp_path
    ):
        outside = tmp_path / "outside.txt"
        outside.write_text("outside secret")
        symlink = test_package / "files" / "escape.txt"
        symlink.symlink_to(outside)
        docs = [
            Document(
                id="traversal-source",
                name="traversal.txt",
                doc_type=DocType.file,
                file_type=FileType.text,
                path="../outside.txt",
                status=Status.completed,
                metadata={},
            ),
            Document(
                id="symlink-source",
                name="escape.txt",
                doc_type=DocType.file,
                file_type=FileType.text,
                path=str(symlink.relative_to(test_package)),
                status=Status.completed,
                metadata={},
            ),
        ]
        for doc in docs:
            db.save(doc)

        assert client.get("/api/storage/source/traversal-source").status_code == 404
        assert client.get("/api/storage/source/symlink-source").status_code == 404

    def test_source_route_serves_relative_and_absolute_paths_under_library(
        self, client, db, test_package
    ):
        relative_path = test_package / "files" / "re" / "relative.txt"
        absolute_path = test_package / "files" / "ab" / "absolute.txt"
        relative_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        relative_path.write_text("relative ok")
        absolute_path.write_text("absolute ok")
        relative_doc = Document(
            id="relative-source",
            name="relative.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            path=str(relative_path.relative_to(test_package)),
            status=Status.completed,
            metadata={},
        )
        absolute_doc = Document(
            id="absolute-source",
            name="absolute.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            path=str(absolute_path),
            status=Status.completed,
            metadata={},
        )
        db.save(relative_doc)
        db.save(absolute_doc)

        relative_response = client.get(f"/api/storage/source/{relative_doc.id}")
        absolute_response = client.get(f"/api/storage/source/{absolute_doc.id}")

        assert relative_response.status_code == 200
        assert relative_response.text == "relative ok"
        assert absolute_response.status_code == 200
        assert absolute_response.text == "absolute ok"


# ---------------------------------------------------------------------------
# GET /api/storage/snapshots
# ---------------------------------------------------------------------------


class TestRegenerateMissingThumbnails:
    def test_generates_thumbnails_for_docs_missing_them(
        self, client, db, test_package
    ):
        pdf_path = _write_test_pdf(test_package / "files" / "rg" / "regen.pdf")
        doc = Document(
            id="regen-missing",
            name="regen.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf_path.relative_to(test_package)),
            status=Status.completed,
            metadata={},
        )
        db.save(doc)

        response = client.post("/api/storage/regenerate-missing")

        assert response.status_code == 200
        data = response.json()
        assert data["generated"] >= 1
        assert "regen-missing" in data["doc_ids"]

    def test_skips_docs_that_already_have_thumbnails(
        self, client, db, test_package
    ):
        pdf_path = _write_test_pdf(test_package / "files" / "sk" / "skip.pdf")
        doc = Document(
            id="regen-skip",
            name="skip.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf_path.relative_to(test_package)),
            status=Status.completed,
            metadata={},
        )
        db.save(doc)
        # Generate thumbnail first so the doc is already cached
        client.get(f"/api/storage/thumbnail/{doc.id}")

        response = client.post("/api/storage/regenerate-missing")

        assert response.status_code == 200
        data = response.json()
        assert "regen-skip" not in data["doc_ids"]


class TestListSnapshots:
    def test_returns_empty_snapshots(self, client):
        with patch("fichero_server.api.routes.storage.list_snapshots") as mock_list:
            mock_list.return_value = []
            r = client.get("/api/storage/snapshots")
        assert r.status_code == 200
        data = r.json()
        assert "snapshots" in data
        assert data["snapshots"] == []
        assert data["total"] == 0

    def test_snapshots_total_matches_count(self, client):
        from fichero_server.models import LibrarySnapshot, SnapshotInitiatorType
        from datetime import datetime

        snap = LibrarySnapshot(
            id="snap-1",
            library_name="test-lib",
            library_path="/tmp/test.fichero",
            reason="test backup",
            initiator=SnapshotInitiatorType.user,
            snapshot_path="/tmp/snapshots/snap-1",
            duckdb_path="db.parquet",
            lance_path="lance/",
            created_at=datetime.now(),
        )
        with patch("fichero_server.api.routes.storage.list_snapshots") as mock_list:
            mock_list.return_value = [snap]
            r = client.get("/api/storage/snapshots")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert len(data["snapshots"]) == 1


class TestSnapshotAuditWrapper:
    def test_create_and_restore_write_app_db_audits_around_library_close(
        self, client, app_db, tmp_path, monkeypatch
    ):
        library_path = tmp_path / "AuditWrapped.fichero"
        library_path.mkdir(parents=True, exist_ok=True)
        seeded = Database(library_path / "fichero.duckdb")
        seeded.save(
            Document(
                id="snap-doc-1",
                name="Snapshot Source",
                page_content="content long enough to embed",
            )
        )
        seeded.close()

        emitted: list[tuple[str, str, str]] = []
        monkeypatch.setattr(
            storage_routes,
            "emit_change",
            lambda library_path, *, type, actor, origin_user=None: emitted.append(
                (library_path, type, actor)
            ),
        )

        created = client.post(
            "/api/storage/snapshots",
            params={"library_path": str(library_path), "reason": "before restore"},
        )
        assert created.status_code == 200, created.text
        snapshot_id = created.json()["id"]

        mutated = Database(library_path / "fichero.duckdb")
        mutated.delete(mutated.get(Document, "snap-doc-1"))
        mutated.close()

        restored = client.post(f"/api/storage/snapshots/{snapshot_id}/restore")
        assert restored.status_code == 200, restored.text

        snapshot_audits = [
            row
            for row in app_db.list_action_audits()
            if row.action_name.startswith("snapshot.")
            and row.target_ids == [str(library_path)]
        ]
        assert [row.action_name for row in snapshot_audits] == [
            "snapshot.create.intent",
            "snapshot.create.outcome",
            "snapshot.restore.intent",
            "snapshot.restore.outcome",
        ]
        assert snapshot_audits[1].after["id"] == snapshot_id
        assert snapshot_audits[3].after["snapshot_id"] == snapshot_id

        restored_db = Database(library_path / "fichero.duckdb")
        assert restored_db.get(Document, "snap-doc-1") is not None
        restored_db.close()

        assert emitted == [
            (str(library_path), "snapshot.create.intent", "user"),
            (str(library_path), "snapshot.created", "user"),
            (str(library_path), "snapshot.restore.intent", "user"),
            (str(library_path), "snapshot.restored", "user"),
        ]


def _write_test_pdf(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    colors = ((1, 0.85, 0.85), (0.85, 1, 0.85))
    labels = ("First page", "Second page")
    for idx, (color, label) in enumerate(zip(colors, labels), start=1):
        page = doc.new_page(width=300, height=420)
        page.draw_rect(page.rect, color=color, fill=color)
        page.insert_text((72, 72), f"{label} {idx}", fontsize=24)
    doc.save(path)
    doc.close()
    return path


def _assert_valid_jpeg(payload: bytes) -> None:
    image = Image.open(BytesIO(payload))
    assert image.format == "JPEG"
    assert image.size[0] > 0
    assert image.size[1] > 0
