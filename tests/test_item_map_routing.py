"""
Unit Tests for Director-Library item_map Routing Fix

Tests the critical functionality that ensures file-level outputs (transcriptions)
are routed to individual file items, not to parent folder items.
"""

import unittest
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

# Import required models and services
from fichero.library.models import (
    Collection, CollectionItem, ProcessingResult, ProcessingOutput
)
from fichero.library.director_integration import DirectorIntegrationService
from fichero.library.library_manager import LibraryManager
from fichero.library.storage import LibraryStorage


class TestItemMapRouting(unittest.TestCase):
    """Test item_map routing functionality"""

    def setUp(self):
        """Set up test environment"""
        # Create temporary directories
        self.test_dir = Path(tempfile.mkdtemp())
        self.library_dir = self.test_dir / "library"
        self.library_dir.mkdir()

        # Create test database
        self.db_path = self.library_dir / "test.db"
        self.storage = LibraryStorage(str(self.db_path))

        # Mock app and director
        self.app = Mock()
        self.director = Mock()

        # Create library manager with mocked path resolver
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=self.db_path):
            self.library_manager = LibraryManager(app=self.app)
        self.library_manager.storage = self.storage

        # Create director integration service
        self.integration = DirectorIntegrationService(
            app=self.app,
            library_manager=self.library_manager,
            director=self.director
        )

        # Create test collection
        self.collection = Collection(
            id="test-coll-123",
            name="Test Collection",
            type="local",
            local_path=str(self.test_dir / "source")
        )
        self.storage.add_collection(self.collection)

    def tearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.test_dir)

    def test_item_map_creation_from_file_items(self):
        """Test that item_map is correctly built from file items in database"""
        # ARRANGE: Create folder with 3 file items
        folder_item = CollectionItem(
            id="folder-123",
            collection_id=self.collection.id,
            type="folder",
            name="test_folder",
            source_path=str(self.test_dir / "test_folder")
        )
        self.storage.add_collection_item(folder_item)

        test_files = [
            ("file-001", "document1.jpg"),
            ("file-002", "document2.jpg"),
            ("file-003", "document3.jpg")
        ]

        for file_id, filename in test_files:
            file_item = CollectionItem(
                id=file_id,
                collection_id=self.collection.id,
                type="file",
                name=filename,
                parent_id=folder_item.id,
                source_path=str(self.test_dir / "test_folder" / filename)
            )
            self.storage.add_collection_item(file_item)

        # ACT: Query items and build item_map (simulating the fix logic)
        all_items = self.storage.get_collection_items(
            collection_id=self.collection.id
        )

        item_map = {}
        for file_item in all_items:
            if file_item.type == 'file' and file_item.parent_id == folder_item.id:
                file_path = file_item.source_path or file_item.local_path
                if file_path:
                    filename = Path(file_path).name
                    item_map[filename] = file_item.id

        # ASSERT
        self.assertEqual(len(item_map), 3, "Should have 3 entries in item_map")
        self.assertEqual(item_map["document1.jpg"], "file-001")
        self.assertEqual(item_map["document2.jpg"], "file-002")
        self.assertEqual(item_map["document3.jpg"], "file-003")

    def test_resolve_target_item_id_with_item_map_file_level(self):
        """Test that file-level outputs resolve to correct file item when item_map exists"""
        # ARRANGE
        item_map = {
            "document1.jpg": "file-001",
            "document2.jpg": "file-002"
        }
        default_item_id = "folder-123"
        collection_id = self.collection.id

        # ACT: Resolve item_id for file-level output
        target_item_id = self.integration._resolve_target_item_id(
            source="document2.jpg",
            step_name="transcribe_qwen_max_direct",
            output_type="transcription",
            default_item_id=default_item_id,
            item_map=item_map,
            collection_id=collection_id
        )

        # ASSERT: Should resolve to specific file item, NOT folder
        self.assertEqual(target_item_id, "file-002",
                        "File-level output should route to file-002, not folder")

    def test_resolve_target_item_id_without_item_map_file_level(self):
        """Test that file-level outputs fallback to default when item_map is None"""
        # ARRANGE
        default_item_id = "folder-123"
        collection_id = self.collection.id

        # ACT: Resolve item_id for file-level output WITHOUT item_map
        target_item_id = self.integration._resolve_target_item_id(
            source="document2.jpg",
            step_name="transcribe_qwen_max_direct",
            output_type="transcription",
            default_item_id=default_item_id,
            item_map=None,  # This was the bug!
            collection_id=collection_id
        )

        # ASSERT: Without item_map, should fallback to default (folder)
        # This demonstrates the bug - but now we have fallback creation
        self.assertEqual(target_item_id, default_item_id,
                        "Without item_map, falls back to folder (but fallback should try to create file item)")

    def test_resolve_target_item_id_collection_level(self):
        """Test that collection-level outputs always use default_item_id"""
        # ARRANGE
        item_map = {"document1.jpg": "file-001"}
        default_item_id = "folder-123"
        collection_id = self.collection.id

        # ACT: Resolve item_id for collection-level output
        target_item_id = self.integration._resolve_target_item_id(
            source="document1.jpg",  # Even with matching source
            step_name="catalogue_folder",
            output_type="catalogue",
            default_item_id=default_item_id,
            item_map=item_map,
            collection_id=collection_id
        )

        # ASSERT: Collection-level should always use folder/collection item_id
        self.assertEqual(target_item_id, default_item_id,
                        "Collection-level output should route to folder")

    def test_is_output_collection_level_detection(self):
        """Test detection of collection-level vs file-level outputs"""
        # Collection-level patterns
        self.assertTrue(
            self.integration._is_output_collection_level("catalogue_folder", "catalogue"),
            "catalogue_folder should be collection-level"
        )
        self.assertTrue(
            self.integration._is_output_collection_level("collection_summary", "summary"),
            "collection_summary should be collection-level"
        )
        self.assertTrue(
            self.integration._is_output_collection_level("batch_process", "batch"),
            "batch_process should be collection-level"
        )

        # File-level patterns
        self.assertFalse(
            self.integration._is_output_collection_level("transcribe_qwen_max", "transcription"),
            "transcribe_qwen_max should be file-level"
        )
        self.assertFalse(
            self.integration._is_output_collection_level("enhance_image", "enhanced_image"),
            "enhance_image should be file-level"
        )

    def test_find_or_create_file_item_finds_existing(self):
        """Test that _find_or_create_file_item finds existing file items"""
        # ARRANGE: Create folder and file item
        folder_item = CollectionItem(
            id="folder-123",
            collection_id=self.collection.id,
            type="folder",
            name="test_folder",
            source_path=str(self.test_dir / "test_folder"),
            storage_type="external"
        )
        self.storage.add_collection_item(folder_item)

        file_item = CollectionItem(
            id="file-001",
            collection_id=self.collection.id,
            type="file",
            name="existing_file.jpg",
            parent_id=folder_item.id,
            source_path=str(self.test_dir / "test_folder" / "existing_file.jpg"),
            storage_type="external"
        )
        self.storage.add_collection_item(file_item)

        # ACT: Try to find the file (use just filename as source_path)
        found_item_id = self.integration._find_or_create_file_item(
            collection_id=self.collection.id,
            source_path="existing_file.jpg",  # Just filename, as manifests typically have
            parent_id=folder_item.id
        )

        # ASSERT: Should find existing item
        self.assertEqual(found_item_id, "file-001", "Should find existing file item")

    def test_find_or_create_file_item_creates_missing(self):
        """Test that _find_or_create_file_item creates missing file items"""
        # ARRANGE: Create only folder, no file items
        folder_item = CollectionItem(
            id="folder-123",
            collection_id=self.collection.id,
            type="folder",
            name="test_folder",
            source_path=str(self.test_dir / "test_folder"),
            storage_type="external"
        )
        self.storage.add_collection_item(folder_item)

        # ACT: Try to find non-existent file (should create it)
        created_item_id = self.integration._find_or_create_file_item(
            collection_id=self.collection.id,
            source_path="new_file.jpg",  # Just filename
            parent_id=folder_item.id
        )

        # ASSERT: Should have created new item
        self.assertIsNotNone(created_item_id, "Should create new file item")

        # Verify item was actually created in database
        created_item = self.storage.get_item(created_item_id)
        self.assertIsNotNone(created_item, "Created item should be in database")
        self.assertEqual(created_item.type, "file", "Created item should be type 'file'")
        self.assertEqual(created_item.name, "new_file.jpg", "Created item should have correct name")
        self.assertEqual(created_item.parent_id, folder_item.id, "Created item should have correct parent")

    def test_item_map_missing_source_in_map(self):
        """Test behavior when source filename is not in item_map"""
        # ARRANGE
        item_map = {"document1.jpg": "file-001"}  # Only has document1
        default_item_id = "folder-123"

        # Create folder for fallback testing
        folder_item = CollectionItem(
            id="folder-123",
            collection_id=self.collection.id,
            type="folder",
            name="test_folder",
            source_path=str(self.test_dir / "test_folder"),
            storage_type="external"
        )
        self.storage.add_collection_item(folder_item)

        # ACT: Try to resolve for document2 (not in map)
        target_item_id = self.integration._resolve_target_item_id(
            source="document2.jpg",  # Not in item_map!
            step_name="transcribe_qwen_max",
            output_type="transcription",
            default_item_id=default_item_id,
            item_map=item_map,
            collection_id=self.collection.id
        )

        # ASSERT: Should attempt fallback creation
        # Since source file doesn't exist in filesystem, fallback will fail
        # and fall back to folder item_id
        self.assertIsNotNone(target_item_id, "Should return some item_id")

    def test_item_map_with_path_variations(self):
        """Test that item_map works with different path formats"""
        # ARRANGE: item_map with just filename
        item_map = {"document.jpg": "file-001"}

        # Test with full path
        target_id = self.integration._resolve_target_item_id(
            source="/full/path/to/document.jpg",  # Full path
            step_name="transcribe_qwen_max",
            output_type="transcription",
            default_item_id="folder-123",
            item_map=item_map,
            collection_id=self.collection.id
        )

        # ASSERT: Should extract filename and match
        self.assertEqual(target_id, "file-001",
                        "Should match filename even from full path")

    def test_multiple_file_outputs_route_correctly(self):
        """Integration test: Multiple file outputs should route to different items"""
        # ARRANGE: Create folder with 3 files
        folder_item = CollectionItem(
            id="folder-123",
            collection_id=self.collection.id,
            type="folder",
            name="test_folder"
        )
        self.storage.add_collection_item(folder_item)

        test_files = [
            ("file-001", "doc1.jpg"),
            ("file-002", "doc2.jpg"),
            ("file-003", "doc3.jpg")
        ]

        for file_id, filename in test_files:
            file_item = CollectionItem(
                id=file_id,
                collection_id=self.collection.id,
                type="file",
                name=filename,
                parent_id=folder_item.id,
                source_path=str(self.test_dir / "test_folder" / filename)
            )
            self.storage.add_collection_item(file_item)

        # Build item_map
        item_map = {filename: file_id for file_id, filename in test_files}

        # ACT: Resolve item_ids for multiple transcriptions
        resolved_ids = []
        for _, filename in test_files:
            target_id = self.integration._resolve_target_item_id(
                source=filename,
                step_name="transcribe_qwen_max",
                output_type="transcription",
                default_item_id=folder_item.id,
                item_map=item_map,
                collection_id=self.collection.id
            )
            resolved_ids.append(target_id)

        # ASSERT: Each should resolve to different file item
        self.assertEqual(len(set(resolved_ids)), 3,
                        "Should have 3 different item_ids")
        self.assertEqual(resolved_ids[0], "file-001")
        self.assertEqual(resolved_ids[1], "file-002")
        self.assertEqual(resolved_ids[2], "file-003")
        self.assertNotIn(folder_item.id, resolved_ids,
                        "No transcriptions should go to folder")


class TestItemMapIntegrationFlow(unittest.TestCase):
    """Test complete flow from folder processing through metadata extraction"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.library_dir = self.test_dir / "library"
        self.output_dir = self.test_dir / "outputs"
        self.library_dir.mkdir()
        self.output_dir.mkdir()

        self.db_path = self.library_dir / "test.db"
        self.storage = LibraryStorage(str(self.db_path))

        self.app = Mock()
        self.director = Mock()

        with patch('fichero.library.path_resolver.get_library_database_path', return_value=self.db_path):
            self.library_manager = LibraryManager(app=self.app)
        self.library_manager.storage = self.storage

        self.integration = DirectorIntegrationService(
            app=self.app,
            library_manager=self.library_manager,
            director=self.director
        )

        self.collection = Collection(
            id="test-coll-123",
            name="Test Collection",
            type="local",
            local_path=str(self.test_dir / "source")
        )
        self.storage.add_collection(self.collection)

    def tearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.test_dir)

    def test_folder_processing_creates_item_map(self):
        """Test that folder processing creates and stores item_map"""
        # ARRANGE: Create folder with files
        folder_item = CollectionItem(
            id="folder-123",
            collection_id=self.collection.id,
            type="folder",
            name="test_folder",
            source_path=str(self.test_dir / "source" / "test_folder")
        )
        self.storage.add_collection_item(folder_item)

        # Create 2 file items
        for i, filename in enumerate(["doc1.jpg", "doc2.jpg"], 1):
            file_item = CollectionItem(
                id=f"file-00{i}",
                collection_id=self.collection.id,
                type="file",
                name=filename,
                parent_id=folder_item.id,
                source_path=str(self.test_dir / "source" / "test_folder" / filename)
            )
            self.storage.add_collection_item(file_item)

        # Mock the director's process_folders method
        self.director.processing_coordinator = Mock()
        self.director.processing_coordinator.process_folders = Mock(return_value="task-123")

        # Create actual folder structure
        folder_path = Path(self.test_dir / "source" / "test_folder")
        folder_path.mkdir(parents=True)
        output_path = self.output_dir / "test_output"
        output_path.mkdir()

        # ACT: Process the folder (this should create item_map)
        import asyncio
        task_ids = asyncio.run(self.integration._process_single_folder(
            item_id=folder_item.id,
            input_path=folder_path,
            output_path=output_path,
            plan_name="Test Plan",
            workflow_name="Test Workflow",
            collection_id=self.collection.id
        ))

        # ASSERT: Check that task was created with item_map
        self.assertEqual(len(task_ids), 1, "Should return one task ID")
        task_id = task_ids[0]

        self.assertIn(task_id, self.integration.active_tasks,
                     "Task should be tracked")

        task_info = self.integration.active_tasks[task_id]
        self.assertIn('item_map', task_info,
                     "Task info should contain item_map")

        item_map = task_info['item_map']
        self.assertEqual(len(item_map), 2,
                        "item_map should have 2 entries")
        self.assertIn("doc1.jpg", item_map)
        self.assertIn("doc2.jpg", item_map)
        self.assertEqual(item_map["doc1.jpg"], "file-001")
        self.assertEqual(item_map["doc2.jpg"], "file-002")


if __name__ == '__main__':
    # Run with verbose output
    unittest.main(verbosity=2)
