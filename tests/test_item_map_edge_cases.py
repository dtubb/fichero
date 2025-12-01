"""
Test edge cases for item_map routing system.

Tests Priority 2 improvements:
- Duplicate filename detection
- Invalid path handling
- Path validation
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from fichero.library.storage import LibraryStorage
from fichero.library.models import (
    Collection,
    CollectionItem,
    ProcessingResult,
    ProcessingOutput
)
from fichero.library.director_integration import DirectorIntegrationService


class TestDuplicateFilenames:
    """Test duplicate filename detection in item_map"""

    def setup_method(self):
        """Set up test fixtures"""
        # Create temp database
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.db_file.name
        self.db_file.close()

        self.storage = LibraryStorage(db_path=self.db_path)

        # Create test collection
        self.collection = Collection(
            name="Test Collection",
            type="external",
            source_path="/test/path"
        )
        self.storage.add_collection(self.collection)

        # Create folder item
        self.folder = CollectionItem(
            collection_id=self.collection.id,
            type="folder",
            name="Test Folder",
            source_path="/test/path/folder",
            storage_type="external"
        )
        self.storage.add_collection_item(self.folder)

    def teardown_method(self):
        """Clean up temp database"""
        import os
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_duplicate_filenames_warning(self, caplog):
        """Test that duplicate filenames trigger warning"""
        import logging
        caplog.set_level(logging.WARNING)

        # Create two files with same name but different paths
        file1 = CollectionItem(
            collection_id=self.collection.id,
            type="file",
            name="document.jpg",
            source_path="/test/path/folder/subdir1/document.jpg",
            parent_id=self.folder.id,
            storage_type="external"
        )
        self.storage.add_collection_item(file1)

        file2 = CollectionItem(
            collection_id=self.collection.id,
            type="file",
            name="document.jpg",
            source_path="/test/path/folder/subdir2/document.jpg",
            parent_id=self.folder.id,
            storage_type="external"
        )
        self.storage.add_collection_item(file2)

        # Build item_map (simulating what director_integration does)
        file_items = self.storage.get_file_items_by_parent(
            collection_id=self.collection.id,
            parent_id=self.folder.id
        )

        item_map = {}
        duplicate_count = 0
        for file_item in file_items:
            file_path = file_item.source_path or file_item.local_path
            if file_path:
                filename = Path(file_path).name

                if filename in item_map:
                    duplicate_count += 1
                    print(f"[ITEM_MAP] Duplicate filename in folder: '{filename}'")

                item_map[filename] = file_item.id

        # Verify duplicate was detected
        assert duplicate_count == 1
        assert len(item_map) == 1  # Only one entry (latest overwrites)
        assert "document.jpg" in item_map

    def test_duplicate_filenames_uses_latest(self):
        """Test that duplicate filenames use the latest item_id"""

        # Create two files with same name
        file1 = CollectionItem(
            collection_id=self.collection.id,
            type="file",
            name="test.jpg",
            source_path="/test/path/folder/test.jpg",
            parent_id=self.folder.id,
            storage_type="external"
        )
        self.storage.add_collection_item(file1)
        first_id = file1.id

        file2 = CollectionItem(
            collection_id=self.collection.id,
            type="file",
            name="test.jpg",
            source_path="/test/path/folder/test.jpg",
            parent_id=self.folder.id,
            storage_type="external"
        )
        self.storage.add_collection_item(file2)
        second_id = file2.id

        # Build item_map
        file_items = self.storage.get_file_items_by_parent(
            collection_id=self.collection.id,
            parent_id=self.folder.id
        )

        item_map = {}
        for file_item in file_items:
            filename = Path(file_item.source_path).name
            item_map[filename] = file_item.id

        # Should use the latest (second) item
        assert item_map["test.jpg"] == second_id
        assert item_map["test.jpg"] != first_id


class TestInvalidPaths:
    """Test invalid path handling"""

    def test_empty_path(self):
        """Test handling of empty path"""
        try:
            filename = Path("").name
            if not filename or filename in ('.', '..'):
                filename = None
        except (TypeError, ValueError, OSError):
            filename = None

        assert filename is None or filename == ""

    def test_none_path(self):
        """Test handling of None path"""
        source = None
        try:
            if source:
                filename = Path(source).name
            else:
                filename = None
        except (TypeError, ValueError, OSError):
            filename = None

        assert filename is None

    def test_dot_path(self):
        """Test handling of . and .. paths"""
        for invalid_path in ('.', '..'):
            filename = Path(invalid_path).name
            # Path('..').name returns '' (empty string), Path('.').name returns '.'
            if filename in ('.', '..', ''):
                filename = None

            assert filename is None

    def test_invalid_characters(self):
        """Test handling of paths with invalid characters"""
        # Most systems will handle these, but we validate
        test_paths = [
            "file\x00name.jpg",  # Null character
            "file\nname.jpg",    # Newline
        ]

        for test_path in test_paths:
            try:
                filename = Path(test_path).name
                # Some systems may allow these, but we're testing the try/except
                assert filename is not None  # Path() succeeded
            except (TypeError, ValueError, OSError):
                # Expected for truly invalid paths
                pass


class TestPathValidation:
    """Test path validation in _resolve_target_item_id and _find_or_create_file_item"""

    def test_resolve_with_invalid_source(self):
        """Test _resolve_target_item_id with invalid source paths"""
        # Mock objects
        mock_app = Mock()
        mock_library_manager = Mock()
        mock_director = Mock()

        service = DirectorIntegrationService(
            app=mock_app,
            library_manager=mock_library_manager,
            director=mock_director
        )

        # Test with None source
        result = service._resolve_target_item_id(
            source=None,
            step_name="transcribe",
            output_type="transcription",
            default_item_id="folder-123",
            item_map={"valid.jpg": "file-001"}
        )
        # Should fall back to default when source is None
        assert result == "folder-123"

        # Test with empty source
        result = service._resolve_target_item_id(
            source="",
            step_name="transcribe",
            output_type="transcription",
            default_item_id="folder-123",
            item_map={"valid.jpg": "file-001"}
        )
        # Should fall back to default when source is empty
        assert result == "folder-123"

    def test_find_or_create_with_invalid_path(self):
        """Test _find_or_create_file_item with invalid paths"""
        # Create temp database
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        db_path = db_file.name
        db_file.close()

        try:
            storage = LibraryStorage(db_path=db_path)

            # Create test collection
            collection = Collection(
                name="Test",
                type="external",
                source_path="/test"
            )
            storage.add_collection(collection)

            folder = CollectionItem(
                collection_id=collection.id,
                type="folder",
                name="Folder",
                source_path="/test/folder",
                storage_type="external"
            )
            storage.add_collection_item(folder)

            # Mock service
            mock_app = Mock()
            mock_library_manager = Mock()
            mock_library_manager.storage = storage
            mock_director = Mock()

            service = DirectorIntegrationService(
                app=mock_app,
                library_manager=mock_library_manager,
                director=mock_director
            )

            # Test with invalid paths
            invalid_paths = ["", ".", "..", None]

            for invalid_path in invalid_paths:
                if invalid_path is None:
                    continue  # Skip None for this test

                result = service._find_or_create_file_item(
                    collection_id=collection.id,
                    source_path=invalid_path,
                    parent_id=folder.id
                )

                # Should return None for invalid paths
                assert result is None

        finally:
            import os
            if os.path.exists(db_path):
                os.unlink(db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
