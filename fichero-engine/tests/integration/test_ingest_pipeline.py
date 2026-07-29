"""Integration tests for the current folder-ingest pipeline."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

from fichero.db import Database
from fichero.importers.ingest import IngestMode, ingest_folder
from fichero.models import DocType, Document, FileType


def _make_library(tmp_path: Path) -> tuple[Path, Database]:
    package = tmp_path / "library.fichero"
    package.mkdir()
    (package / "files").mkdir()
    db = Database(package / "fichero.duckdb")
    return package, db


class TestIngestPipelineIntegration:
    """Current ingest pipeline behavior with a real temporary database."""

    def test_complete_folder_ingestion_workflow(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            test_folder = tmp_path / "test_collection"
            test_folder.mkdir()
            (test_folder / "file1.jpg").write_bytes(b"fake image data 1")
            (test_folder / "file2.png").write_bytes(b"fake image data 2")
            subfolder = test_folder / "subfolder"
            subfolder.mkdir()
            (subfolder / "file3.txt").write_text("Test content", encoding="utf-8")

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

            assert len(docs) == 3
            file_types = {doc.name: doc.file_type for doc in docs}
            assert file_types["file1.jpg"] == FileType.image
            assert file_types["file2.png"] == FileType.image
            assert file_types["file3.txt"] == FileType.text

            folders = db.query(Document, doc_type=DocType.folder)
            folder_by_name = {folder.name: folder for folder in folders}
            assert set(folder_by_name) == {"test_collection", "subfolder"}
            subfolder_doc = folder_by_name["subfolder"]
            nested = next(doc for doc in docs if doc.name == "file3.txt")
            assert nested.parent_id == subfolder_doc.id
        finally:
            db.close()

    def test_copy_mode_with_apfs_cloning(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            test_folder = tmp_path / "copy_test"
            test_folder.mkdir()
            (test_folder / "file1.jpg").write_bytes(b"fake image data")
            (test_folder / "file2.png").write_bytes(b"fake image data")

            # The fake clone must MATERIALIZE the destination: the pipeline now
            # verifies the copied bytes (write durability), so a mock that
            # returns True without producing a file is correctly rejected.
            def fake_clone(source, dest):
                shutil.copy2(source, dest)
                return True

            with patch("fichero.bookmarks.create_bookmark", return_value=b"bookmark_data"):
                with patch(
                    "fichero.importers.ingest._try_apfs_clone", side_effect=fake_clone
                ) as mock_clone:
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
            for doc in docs:
                assert doc.path.startswith("files/")
        finally:
            db.close()

    def test_parent_child_relationships(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            test_folder = tmp_path / "parent_child_test"
            test_folder.mkdir()
            (test_folder / "root_file.jpg").write_bytes(b"root data")
            level1 = test_folder / "level1"
            level1.mkdir()
            (level1 / "level1_file.png").write_bytes(b"level1 data")
            level2 = level1 / "level2"
            level2.mkdir()
            (level2 / "level2_file.txt").write_text("level2 content", encoding="utf-8")

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

            folders = {folder.name: folder for folder in db.query(Document, doc_type=DocType.folder)}
            assert {"parent_child_test", "level1", "level2"} <= set(folders)

            root_file = next(doc for doc in docs if doc.name == "root_file.jpg")
            level1_file = next(doc for doc in docs if doc.name == "level1_file.png")
            level2_file = next(doc for doc in docs if doc.name == "level2_file.txt")
            assert root_file.parent_id == folders["parent_child_test"].id
            assert level1_file.parent_id == folders["level1"].id
            assert level2_file.parent_id == folders["level2"].id
        finally:
            db.close()

    def test_progress_reporting(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            test_folder = tmp_path / "progress_test"
            test_folder.mkdir()
            for i in range(5):
                (test_folder / f"file_{i}.jpg").write_bytes(b"fake data")

            progress_calls: list[tuple[int, int]] = []

            def _on_progress(current: int, total: int) -> None:
                progress_calls.append((current, total))

            with patch("fichero.bookmarks.create_bookmark", return_value=b"bookmark_data"):
                docs = ingest_folder(
                    test_folder,
                    mode=IngestMode.LINK,
                    create_collection=False,
                    extract_text=False,
                    auto_embed=False,
                    on_progress=_on_progress,
                    db=db,
                    package_path=package,
                )

            assert len(docs) == 5
            assert progress_calls[-1] == (5, 5)
        finally:
            db.close()

    def test_text_extraction_integration(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            test_folder = tmp_path / "text_extraction_test"
            test_folder.mkdir()
            (test_folder / "document.txt").write_text("Hello World\nThis is test content.", encoding="utf-8")
            (test_folder / "notes.md").write_text("# Test Notes\n\nSome markdown content.", encoding="utf-8")

            with patch("fichero.bookmarks.create_bookmark", return_value=b"bookmark_data"):
                docs = ingest_folder(
                    test_folder,
                    mode=IngestMode.LINK,
                    create_collection=False,
                    extract_text=True,
                    auto_embed=False,
                    db=db,
                    package_path=package,
                )

            assert len(docs) == 2
            for doc in docs:
                assert doc.metadata.get("text_extracted")
                assert doc.page_content
                assert "file_size" in doc.metadata
                assert "checksum" in doc.metadata
        finally:
            db.close()

    def test_mixed_file_types(self, tmp_path):
        package, db = _make_library(tmp_path)
        try:
            test_folder = tmp_path / "mixed_types"
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
