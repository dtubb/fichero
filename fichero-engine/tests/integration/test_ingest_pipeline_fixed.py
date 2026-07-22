"""Regression coverage for stale ingest integration assumptions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fichero.db import Database
from fichero.importers.ingest import IngestMode, ingest_folder
from fichero.models import DocType, Document, FileType, Status


def _make_library(tmp_path: Path) -> tuple[Path, Database]:
    package = tmp_path / "fixed-library.fichero"
    package.mkdir()
    (package / "files").mkdir()
    db = Database(package / "fichero.duckdb")
    return package, db


class TestIngestPipelineIntegration:
    """Current ingest behavior for the legacy fixed suite."""

    def test_nested_folder_docs_are_persisted(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            test_folder = tmp_path / "collection"
            test_folder.mkdir()
            (test_folder / "root.jpg").write_bytes(b"root")
            nested = test_folder / "nested"
            nested.mkdir()
            (nested / "child.txt").write_text("child", encoding="utf-8")

            with patch("fichero.bookmarks.create_bookmark", return_value=b"bookmark_data"):
                docs = ingest_folder(
                    test_folder,
                    mode=IngestMode.LINK,
                    create_collection=True,
                    extract_text=False,
                    auto_embed=False,
                    db=db,
                    package_path=package,
                )

            assert len(docs) == 2
            folders = {folder.name: folder for folder in db.query(Document, doc_type=DocType.folder)}
            assert set(folders) == {"collection", "nested"}
            assert next(doc for doc in docs if doc.name == "child.txt").parent_id == folders["nested"].id
        finally:
            db.close()

    def test_text_files_extract_content_by_default(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            test_folder = tmp_path / "text-defaults"
            test_folder.mkdir()
            (test_folder / "notes.md").write_text("Folder import should extract this sentence.", encoding="utf-8")

            with patch("fichero.bookmarks.create_bookmark", return_value=None):
                docs = ingest_folder(
                    test_folder,
                    create_collection=False,
                    auto_embed=False,
                    db=db,
                    package_path=package,
                )

            assert len(docs) == 1
            assert "extract this sentence" in (docs[0].page_content or "")
        finally:
            db.close()

    def test_unchanged_files_are_skipped_by_checksum(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            test_folder = tmp_path / "stable"
            test_folder.mkdir()
            (test_folder / "stable.md").write_text("Stable payload for resumable ingest.", encoding="utf-8")

            with patch("fichero.bookmarks.create_bookmark", return_value=None):
                first = ingest_folder(
                    test_folder,
                    create_collection=False,
                    auto_embed=False,
                    db=db,
                    package_path=package,
                )
                second = ingest_folder(
                    test_folder,
                    create_collection=False,
                    auto_embed=False,
                    db=db,
                    package_path=package,
                )

            assert len(first) == 1
            assert second == []
        finally:
            db.close()

    def test_sidecar_files_are_not_primary_targets(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            source_dir = tmp_path / "source"
            source_dir.mkdir()
            (source_dir / "photo.jpg").write_bytes(b"image")
            (source_dir / "photo.xmp").write_text("<x:xmpmeta/>", encoding="utf-8")
            (source_dir / "photo.iffy.json").write_text("{}", encoding="utf-8")

            with patch("fichero.bookmarks.create_bookmark", return_value=None):
                docs = ingest_folder(
                    source_dir,
                    create_collection=False,
                    extract_text=False,
                    auto_embed=False,
                    db=db,
                    package_path=package,
                )

            assert len(docs) == 1
            assert docs[0].name == "photo.jpg"
        finally:
            db.close()

    def test_failed_bookmark_only_marks_that_file_failed(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            test_folder = tmp_path / "mixed"
            test_folder.mkdir()
            (test_folder / "valid.jpg").write_bytes(b"valid image data")
            (test_folder / "problematic.txt").write_text("problematic", encoding="utf-8")

            def _bookmark(path: Path):
                if path.name == "problematic.txt":
                    raise PermissionError("Permission denied")
                return b"bookmark_data"

            with patch("fichero.bookmarks.create_bookmark", side_effect=_bookmark):
                docs = ingest_folder(
                    test_folder,
                    mode=IngestMode.LINK,
                    create_collection=False,
                    extract_text=False,
                    auto_embed=False,
                    db=db,
                    package_path=package,
                )

            assert any(doc.name == "valid.jpg" for doc in docs)
            failed = next(doc for doc in db.query(Document, name="problematic.txt"))
            assert failed.status == Status.failed
        finally:
            db.close()

    def test_copy_mode_uses_package_files_directory(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            test_folder = tmp_path / "copy"
            test_folder.mkdir()
            (test_folder / "file1.jpg").write_bytes(b"fake data 1")
            (test_folder / "file2.png").write_bytes(b"fake data 2")

            with patch("fichero.bookmarks.create_bookmark", return_value=b"bookmark_data"):
                with patch("fichero.importers.ingest._try_apfs_clone", return_value=True) as mock_clone:
                    docs = ingest_folder(
                        test_folder,
                        mode=IngestMode.COPY,
                        create_collection=False,
                        extract_text=False,
                        auto_embed=False,
                        db=db,
                        package_path=package,
                    )

            assert mock_clone.call_count == 2
            assert len(docs) == 2
            assert all(doc.path.startswith("files/") for doc in docs)
        finally:
            db.close()

    def test_large_folder_ingests_every_file(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            test_folder = tmp_path / "large"
            test_folder.mkdir()
            for i in range(20):
                (test_folder / f"file_{i:03d}.jpg").write_bytes(b"fake data")

            with patch("fichero.bookmarks.create_bookmark", return_value=b"bookmark_data"):
                docs = ingest_folder(
                    test_folder,
                    mode=IngestMode.LINK,
                    create_collection=False,
                    extract_text=False,
                    auto_embed=False,
                    db=db,
                    package_path=package,
                )

            assert len(docs) == 20
        finally:
            db.close()

    def test_mixed_file_types(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            test_folder = tmp_path / "mixed-types"
            test_folder.mkdir()
            (test_folder / "image.jpg").write_bytes(b"fake image")
            (test_folder / "document.pdf").write_bytes(b"%PDF-1.4\nfake pdf")
            (test_folder / "text.txt").write_text("text content", encoding="utf-8")
            (test_folder / "audio.mp3").write_bytes(b"fake audio")
            (test_folder / "video.mp4").write_bytes(b"fake video")

            with patch("fichero.bookmarks.create_bookmark", return_value=b"bookmark_data"):
                docs = ingest_folder(
                    test_folder,
                    mode=IngestMode.LINK,
                    create_collection=False,
                    extract_text=False,
                    auto_embed=False,
                    db=db,
                    package_path=package,
                )

            assert len(docs) == 5
            file_type_map = {doc.name: doc.file_type for doc in docs}
            assert file_type_map["image.jpg"] == FileType.image
            assert file_type_map["document.pdf"] == FileType.pdf
            assert file_type_map["text.txt"] == FileType.text
            assert file_type_map["audio.mp3"] == FileType.audio
            assert file_type_map["video.mp4"] == FileType.video
        finally:
            db.close()
