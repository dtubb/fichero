"""Integration tests for complete ingest pipeline."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil
import sys


# Mock the database module before any imports
class MockDB:
    def __init__(self):
        self.save = Mock()
        self.save.return_value = None
        self.get = Mock()
        self.get.return_value = None
        self.query = Mock()
        self.query.return_value = []

# Create mock db instance
mock_db_instance = MockDB()

# Patch the database module
sys.modules['fichero.db'] = MagicMock()
sys.modules['fichero.db'].db = mock_db_instance

# Now import the modules we need
from fichero.ingest import ingest_folder, IngestMode
from fichero.models import Document, DocType


class TestIngestPipelineIntegration:
    """Integration tests for complete ingest pipeline workflow."""

    def test_complete_folder_ingestion_workflow(self, tmp_path):
        """Should complete full folder ingestion workflow with nested structure."""
        # Mock bookmark creation
        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
            mock_bookmark.return_value = b"bookmark_data"
            
            # Mock file operations for COPY mode
            with patch("fichero.ingest.shutil") as mock_shutil:
                mock_shutil.copy2.return_value = None
                
                # Create test folder structure
                test_folder = tmp_path / "test_collection"
                test_folder.mkdir()
                
                # Create nested structure
                (test_folder / "file1.jpg").write_bytes(b"fake image data 1")
                (test_folder / "file2.png").write_bytes(b"fake image data 2")
                
                subfolder = test_folder / "subfolder"
                subfolder.mkdir()
                (subfolder / "file3.txt").write_text("Test content")
                
                # Reset mock call tracking
                mock_db_instance.save.reset_mock()
                
                # Test LINK mode
                docs_link = ingest_folder(
                    test_folder,
                    mode=IngestMode.LINK,
                    create_collection=True,
                    extract_text=False,
                    auto_embed=False
                )
                
                # Verify collection was created
                collection_calls = [
                    call for call in mock_db_instance.save.call_args_list
                    if call.args[0].doc_type == DocType.folder
                ]
                assert len(collection_calls) == 1
                
                # Verify all files were ingested
                assert len(docs_link) == 3
                
                # Verify file types
                file_types = {doc.name: doc.file_type for doc in docs_link}
                assert file_types["file1.jpg"].value == "image"
                assert file_types["file2.png"].value == "image"
                assert file_types["file3.txt"].value == "text"
                
                # Verify parent-child relationships
                subfolder_docs = [doc for doc in docs_link if doc.name == "file3.txt"]
                assert len(subfolder_docs) == 1
                assert subfolder_docs[0].parent_id is not None

    def test_copy_mode_with_apfs_cloning(self, tmp_path):
        """Should test COPY mode with APFS cloning functionality."""
        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
            mock_bookmark.return_value = b"bookmark_data"
            
            with patch("fichero.ingest._try_apfs_clone") as mock_clone:
                mock_clone.return_value = True
                
                # Mock settings at the storage level
                with patch("fichero.storage.settings") as mock_settings:
                    mock_settings.base_path = tmp_path
                    
                    # Create test folder
                    test_folder = tmp_path / "copy_test"
                    test_folder.mkdir()
                    
                    (test_folder / "file1.jpg").write_bytes(b"fake image data")
                    (test_folder / "file2.png").write_bytes(b"fake image data")
                    
                    # Reset mock call tracking
                    mock_db_instance.save.reset_mock()
                    
                    docs = ingest_folder(
                        test_folder,
                        mode=IngestMode.COPY,
                        create_collection=False,
                        extract_text=False,
                        auto_embed=False
                    )
                    
                    # Verify APFS cloning was attempted
                    assert mock_clone.call_count == 2
                    
                    # Verify documents were created
                    assert len(docs) == 2
                    
                    # Verify files were copied to library structure
                    for doc in docs:
                        assert "imported" in doc.path

    def test_parent_child_relationships(self, tmp_path):
        """Should test parent-child document relationships in nested folders."""
        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
            mock_bookmark.return_value = b"bookmark_data"
            
            # Create nested folder structure
            test_folder = tmp_path / "parent_child_test"
            test_folder.mkdir()
            
            (test_folder / "root_file.jpg").write_bytes(b"root data")
            
            level1 = test_folder / "level1"
            level1.mkdir()
            (level1 / "level1_file.png").write_bytes(b"level1 data")
            
            level2 = level1 / "level2"
            level2.mkdir()
            (level2 / "level2_file.txt").write_text("level2 content")
            
            # Reset mock call tracking
            mock_db_instance.save.reset_mock()
            
            docs = ingest_folder(
                test_folder,
                mode=IngestMode.LINK,
                create_collection=True,
                extract_text=False,
                auto_embed=False
            )
            
            # Verify collection was created
            collection_calls = [
                call for call in mock_db_instance.save.call_args_list
                if call.args[0].doc_type == DocType.folder
            ]
            assert len(collection_calls) == 1
            collection_id = collection_calls[0].args[0].id
            
            # Verify parent-child relationships
            root_files = [doc for doc in docs if doc.name == "root_file.jpg"]
            level1_files = [doc for doc in docs if doc.name == "level1_file.png"]
            level2_files = [doc for doc in docs if doc.name == "level2_file.txt"]
            
            assert len(root_files) == 1
            assert len(level1_files) == 1
            assert len(level2_files) == 1
            
            # Root file should have collection as parent
            assert root_files[0].parent_id == collection_id
            
            # Level1 and level2 files should have appropriate parents
            assert level1_files[0].parent_id is not None
            assert level2_files[0].parent_id is not None

    def test_error_handling_mixed_files(self, tmp_path):
        """Should handle mixed valid/invalid files gracefully."""
        def mock_bookmark_side_effect(path):
            if "problematic" in str(path):
                raise Exception("Bookmark creation failed")
            return b"bookmark_data"
        
        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
            mock_bookmark.side_effect = mock_bookmark_side_effect
            
            # Create folder with mixed files
            test_folder = tmp_path / "mixed_test"
            test_folder.mkdir()
            
            (test_folder / "valid.jpg").write_bytes(b"valid image data")
            (test_folder / "problematic.txt").write_bytes(b"problematic content")
            
            # Reset mock call tracking
            mock_db_instance.save.reset_mock()
            
            # Should not crash, just log warnings
            docs = ingest_folder(
                test_folder,
                mode=IngestMode.LINK,
                create_collection=False,
                extract_text=False,
                auto_embed=False
            )
            
            # Should still ingest valid files
            assert len(docs) >= 1
            valid_docs = [doc for doc in docs if doc.name == "valid.jpg"]
            assert len(valid_docs) == 1

    def test_progress_reporting(self, tmp_path):
        """Should test progress reporting during folder ingestion."""
        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
            mock_bookmark.return_value = b"bookmark_data"
            
            # Create folder with multiple files
            test_folder = tmp_path / "progress_test"
            test_folder.mkdir()
            
            for i in range(5):
                (test_folder / f"file_{i}.jpg").write_bytes(b"fake data")
            
            progress_calls = []
            
            def on_progress(current, total):
                progress_calls.append((current, total))
            
            # Reset mock call tracking
            mock_db_instance.save.reset_mock()
            
            docs = ingest_folder(
                test_folder,
                mode=IngestMode.LINK,
                create_collection=False,
                extract_text=False,
                auto_embed=False,
                on_progress=on_progress
            )
            
            # Verify progress was reported
            assert len(progress_calls) == 5
            
            # Verify final progress
            final_call = progress_calls[-1]
            assert final_call[0] == 5  # current
            assert final_call[1] == 5  # total
            
            # Verify all files were processed
            assert len(docs) == 5

    def test_metadata_extraction_integration(self, tmp_path):
        """Should test metadata extraction during ingestion."""
        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
            mock_bookmark.return_value = b"bookmark_data"
            
            # Create test files
            test_folder = tmp_path / "metadata_test"
            test_folder.mkdir()
            
            (test_folder / "image.jpg").write_bytes(b"fake image data" * 100)
            (test_folder / "document.txt").write_text("Test document content")
            
            # Reset mock call tracking
            mock_db_instance.save.reset_mock()
            
            docs = ingest_folder(
                test_folder,
                mode=IngestMode.LINK,
                create_collection=False,
                extract_text=False,
                auto_embed=False
            )
            
            # Verify metadata was extracted
            assert len(docs) == 2
            
            for doc in docs:
                # Check basic metadata
                assert "file_size" in doc.metadata
                assert doc.metadata["file_size"] > 0
                
                # Check checksum
                assert "checksum" in doc.metadata
                assert len(doc.metadata["checksum"]) == 64  # SHA256
                
                # Check MIME type
                assert "mime_type" in doc.metadata

    def test_database_integration(self, tmp_path):
        """Should test database integration during ingestion."""
        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
            mock_bookmark.return_value = b"bookmark_data"
            
            # Create test folder
            test_folder = tmp_path / "db_test"
            test_folder.mkdir()
            
            (test_folder / "file1.jpg").write_bytes(b"fake data 1")
            (test_folder / "file2.png").write_bytes(b"fake data 2")
            
            # Reset mock call tracking
            mock_db_instance.save.reset_mock()
            
            docs = ingest_folder(
                test_folder,
                mode=IngestMode.LINK,
                create_collection=True,
                extract_text=False,
                auto_embed=False
            )
            
            # Verify database operations
            assert mock_db_instance.save.call_count >= 3  # Collection + 2 files
            
            # Verify collection was saved
            collection_saves = [
                call for call in mock_db_instance.save.call_args_list
                if call.args[0].doc_type == DocType.folder
            ]
            assert len(collection_saves) == 1
            
            # Verify documents were saved
            document_saves = [
                call for call in mock_db_instance.save.call_args_list
                if call.args[0].doc_type == DocType.file
            ]
            assert len(document_saves) == 2

    def test_text_extraction_integration(self, tmp_path):
        """Should test text extraction during folder ingestion."""
        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
            mock_bookmark.return_value = b"bookmark_data"
            
            # Create test files
            test_folder = tmp_path / "text_extraction_test"
            test_folder.mkdir()
            
            (test_folder / "document.txt").write_text("Hello World\nThis is test content.")
            (test_folder / "notes.md").write_text("# Test Notes\n\nSome markdown content.")
            
            # Reset mock call tracking
            mock_db_instance.save.reset_mock()
            
            docs = ingest_folder(
                test_folder,
                mode=IngestMode.LINK,
                create_collection=False,
                extract_text=True,
                auto_embed=False
            )
            
            # Verify text was extracted
            assert len(docs) == 2
            
            for doc in docs:
                # Check text extraction flag
                assert doc.metadata.get("text_extracted") == True
                
                # Check page content
                assert hasattr(doc, 'page_content')
                if doc.page_content:
                    assert len(doc.page_content) > 0

    def test_duplicate_detection(self, tmp_path):
        """Should test duplicate detection during ingestion."""
        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
            mock_bookmark.return_value = b"bookmark_data"
            
            # Create folder with duplicate files
            test_folder = tmp_path / "duplicate_test"
            test_folder.mkdir()
            
            # Create two files with same content (will have same checksum)
            content = b"identical content"
            (test_folder / "file1.jpg").write_bytes(content)
            (test_folder / "file2.jpg").write_bytes(content)
            
            # Reset mock call tracking
            mock_db_instance.save.reset_mock()
            
            docs = ingest_folder(
                test_folder,
                mode=IngestMode.LINK,
                create_collection=False,
                extract_text=False,
                auto_embed=False
            )
            
            # Verify both files were processed
            assert len(docs) == 2
            
            # Verify checksums are identical (duplicates)
            checksums = [doc.metadata.get("checksum") for doc in docs]
            assert len(set(checksums)) == 1  # Only one unique checksum
            
            # Verify both documents exist (order may vary)
            doc_names = {doc.name for doc in docs}
            assert doc_names == {"file1.jpg", "file2.jpg"}

    def test_permission_error_handling(self, tmp_path):
        """Should handle permission errors gracefully."""
        def mock_bookmark_side_effect(path):
            if "restricted" in str(path):
                raise PermissionError("Permission denied")
            return b"bookmark_data"
        
        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
            mock_bookmark.side_effect = mock_bookmark_side_effect
            
            # Create test folder
            test_folder = tmp_path / "permission_test"
            test_folder.mkdir()
            
            # Create a file
            (test_folder / "accessible.jpg").write_bytes(b"accessible data")
            
            # Create a file that will cause permission error
            restricted_file = test_folder / "restricted.jpg"
            restricted_file.write_bytes(b"restricted data")
            
            # Reset mock call tracking
            mock_db_instance.save.reset_mock()
            
            # Should not crash, just log warning
            docs = ingest_folder(
                test_folder,
                mode=IngestMode.LINK,
                create_collection=False,
                extract_text=False,
                auto_embed=False
            )
            
            # Should still process accessible files
            assert len(docs) >= 1
            accessible_docs = [doc for doc in docs if doc.name == "accessible.jpg"]
            assert len(accessible_docs) == 1

    def test_large_folder_performance(self, tmp_path):
        """Should handle large folders efficiently."""
        import time
        
        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
            mock_bookmark.return_value = b"bookmark_data"
            
            # Create folder with many files
            test_folder = tmp_path / "large_test"
            test_folder.mkdir()
            
            # Create 20 files
            for i in range(20):
                (test_folder / f"file_{i:03d}.jpg").write_bytes(b"fake data")
            
            start_time = time.time()
            
            # Reset mock call tracking
            mock_db_instance.save.reset_mock()
            
            docs = ingest_folder(
                test_folder,
                mode=IngestMode.LINK,
                create_collection=False,
                extract_text=False,
                auto_embed=False
            )
            
            end_time = time.time()
            
            # Should complete in reasonable time
            assert len(docs) == 20
            assert end_time - start_time < 30  # Should take less than 30 seconds

    def test_mixed_file_types(self, tmp_path):
        """Should handle mixed file types correctly."""
        from fichero.models import FileType
        
        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
            mock_bookmark.return_value = b"bookmark_data"
            
            # Create folder with various file types
            test_folder = tmp_path / "mixed_types"
            test_folder.mkdir()
            
            (test_folder / "image.jpg").write_bytes(b"fake image")
            (test_folder / "document.pdf").write_bytes(b"fake pdf")
            (test_folder / "text.txt").write_text("text content")
            (test_folder / "audio.mp3").write_bytes(b"fake audio")
            (test_folder / "video.mp4").write_bytes(b"fake video")
            
            # Reset mock call tracking
            mock_db_instance.save.reset_mock()
            
            docs = ingest_folder(
                test_folder,
                mode=IngestMode.LINK,
                create_collection=False,
                extract_text=False,
                auto_embed=False
            )
            
            # Verify all files were processed
            assert len(docs) == 5
            
            # Verify file types
            file_type_map = {doc.name: doc.file_type for doc in docs}
            
            assert file_type_map["image.jpg"] == FileType.image
            assert file_type_map["document.pdf"] == FileType.pdf
            assert file_type_map["text.txt"] == FileType.text
            assert file_type_map["audio.mp3"] == FileType.audio
            assert file_type_map["video.mp4"] == FileType.video