"""
Unit tests for Updated Director Integration Service
Tests the new no-copy, hierarchical output structure
"""

import unittest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import tempfile
import shutil

from fichero.library.director_integration import DirectorIntegrationService
from fichero.library.models import CollectionItem, Collection


class TestHierarchicalOutputStructure(unittest.TestCase):
    """Test new hierarchical output structure generation"""

    def setUp(self):
        """Set up test fixtures"""
        # Create mock app
        self.mock_app = Mock()
        self.mock_app.paths = Mock()
        self.mock_app.settings = None  # No settings in test

        # Create temp directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.mock_app.paths.data = self.temp_dir

        # Create mock library manager
        self.mock_library_manager = Mock()

        # Create mock collection
        self.mock_collection = Collection(
            id="test-collection-id-12345",
            name="Test Collection",
            type="external"
        )

        async def mock_get_collection(collection_id):
            return self.mock_collection

        self.mock_library_manager.get_collection = AsyncMock(side_effect=mock_get_collection)

        # Create mock director
        self.mock_director = Mock()
        self.mock_director.processing_coordinator = Mock()
        self.mock_director.task_monitor = Mock()
        self.mock_director.task_monitor.register_callback = Mock()

        # Create service
        self.service = DirectorIntegrationService(
            app=self.mock_app,
            library_manager=self.mock_library_manager,
            director=self.mock_director
        )

    def tearDown(self):
        """Clean up test fixtures"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_generate_output_structure_basic(self):
        """Test hierarchical output structure generation"""
        base_path = Path(self.temp_dir)

        result = self.service._generate_output_structure(
            collection_name="EAP1477 Colombia Archives",
            collection_id="abc123",
            item_name="1931 Antonio Asprilla",
            workflow_name="Catalogue",
            plan_name="Default",
            base_path=base_path
        )

        # Verify structure: base/collection/date/workflow/item
        self.assertTrue(str(result).endswith("1931_Antonio_Asprilla"))
        self.assertIn("EAP1477_Colombia_Archives", str(result))
        self.assertIn("Catalogue", str(result))

        # Verify date folder exists in path
        today = datetime.now().strftime('%Y-%m-%d')
        self.assertIn(today, str(result))

    def test_generate_output_structure_sanitization(self):
        """Test that special characters are sanitized"""
        base_path = Path(self.temp_dir)

        result = self.service._generate_output_structure(
            collection_name="Test/Collection:With*Special?Chars",
            collection_id="abc123",
            item_name="File<>Name|With\\Slashes",
            workflow_name="Work/flow",
            plan_name="Plan",
            base_path=base_path
        )

        # Verify special characters are replaced (except directory separators)
        path_str = str(result)
        # Check individual path components (not the full path with valid /)
        parts = result.relative_to(base_path).parts

        # Collection name part should have no special chars
        collection_part = parts[0]
        self.assertNotIn(":", collection_part)
        self.assertNotIn("*", collection_part)
        self.assertNotIn("?", collection_part)

        # Item name part should have no special chars
        item_part = parts[-1]
        self.assertNotIn("<", item_part)
        self.assertNotIn(">", item_part)
        self.assertNotIn("|", item_part)
        self.assertNotIn("\\", item_part)

    def test_generate_output_structure_duplicate_handling(self):
        """Test that duplicate paths get numbered"""
        base_path = Path(self.temp_dir)

        # Create first path
        result1 = self.service._generate_output_structure(
            collection_name="Test",
            collection_id="abc",
            item_name="Item",
            workflow_name="Workflow",
            plan_name="Plan",
            base_path=base_path
        )
        result1.mkdir(parents=True)

        # Create duplicate (same parameters)
        result2 = self.service._generate_output_structure(
            collection_name="Test",
            collection_id="abc",
            item_name="Item",
            workflow_name="Workflow",
            plan_name="Plan",
            base_path=base_path
        )

        # Verify second path has counter
        self.assertNotEqual(result1, result2)
        self.assertTrue(str(result2).endswith("_1"))


class TestNoCopyProcessing(unittest.TestCase):
    """Test that files are NOT copied during processing"""

    def setUp(self):
        """Set up test fixtures"""
        # Create mock app
        self.mock_app = Mock()
        self.mock_app.paths = Mock()
        self.mock_app.settings = None

        # Create temp directory
        self.temp_dir = tempfile.mkdtemp()
        self.mock_app.paths.data = self.temp_dir

        # Create source files that should NOT be copied
        self.source_dir = Path(self.temp_dir) / "source"
        self.source_dir.mkdir()
        self.test_file1 = self.source_dir / "test1.jpg"
        self.test_file2 = self.source_dir / "test2.jpg"
        self.test_file1.write_text("original1")
        self.test_file2.write_text("original2")

        # Create mock library manager
        self.mock_library_manager = Mock()

        # Create mock collection
        self.mock_collection = Collection(
            id="col-123",
            name="Test Collection",
            type="external"
        )

        async def mock_get_collection(collection_id):
            return self.mock_collection

        self.mock_library_manager.get_collection = AsyncMock(side_effect=mock_get_collection)

        # Create mock director
        self.mock_director = Mock()
        self.mock_director.processing_coordinator = Mock()
        self.mock_director.processing_coordinator.process_folders = Mock(return_value="task_123")
        self.mock_director.task_monitor = Mock()
        self.mock_director.task_monitor.register_callback = Mock()

        # Create service
        self.service = DirectorIntegrationService(
            app=self.mock_app,
            library_manager=self.mock_library_manager,
            director=self.mock_director
        )

    def tearDown(self):
        """Clean up"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_process_file_batch_no_copying(self):
        """Test that batch processing does NOT copy files"""
        # Create mock items pointing to source files
        item1 = CollectionItem(
            id="item1",
            collection_id="col-123",
            type="file",
            source_path=str(self.test_file1),
            local_path=str(self.test_file1),
            name="test1.jpg"
        )
        item2 = CollectionItem(
            id="item2",
            collection_id="col-123",
            type="file",
            source_path=str(self.test_file2),
            local_path=str(self.test_file2),
            name="test2.jpg"
        )

        # Mock update_item
        self.mock_library_manager.update_item = AsyncMock()

        # Run batch processing
        file_items = [
            ("item1", item1, self.test_file1),
            ("item2", item2, self.test_file2)
        ]

        output_path = Path(self.temp_dir) / "output"

        async def run_test():
            task_ids = await self.service._process_file_batch(
                file_items=file_items,
                output_base_path=output_path,
                plan_name="Default",
                workflow_name="Catalogue",
                collection_name="Test Collection",
                collection_id="col-123"
            )
            return task_ids

        task_ids = asyncio.run(run_test())

        # Verify task was submitted
        self.assertEqual(len(task_ids), 1)

        # Verify NO files were copied - source files should still be ONLY in source_dir
        # Output directory should only have folder structure, no copied files
        if output_path.exists():
            # Find any .jpg files in output path
            copied_files = list(output_path.rglob("*.jpg"))
            # Should be 0 - we don't copy anymore!
            self.assertEqual(len(copied_files), 0,
                           f"Found copied files: {copied_files}. Files should NOT be copied!")

        # Verify source files still exist in original location
        self.assertTrue(self.test_file1.exists())
        self.assertTrue(self.test_file2.exists())

        # Verify director was called with SOURCE folder, not copied folder
        call_args = self.mock_director.processing_coordinator.process_folders.call_args
        folders_arg = call_args[1]['folders']

        # Should be processing from source directory
        self.assertEqual(len(folders_arg), 1)
        self.assertEqual(folders_arg[0], self.source_dir)


class TestLibraryProcessingIntegration(unittest.TestCase):
    """Integration tests for library processing workflow"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_app = Mock()
        self.mock_app.paths = Mock()
        self.mock_app.settings = None

        self.temp_dir = tempfile.mkdtemp()
        self.mock_app.paths.data = self.temp_dir

        # Create realistic folder structure
        self.source_folder = Path(self.temp_dir) / "Small Test"
        self.subfolder = self.source_folder / "1931 Antonio Asprilla"
        self.subfolder.mkdir(parents=True)

        # Add test files
        for i in range(1, 4):
            (self.subfolder / f"doc_{i:03d}.jpg").write_text(f"document {i}")

        # Create mocks
        self.mock_library_manager = Mock()
        self.mock_collection = Collection(
            id="small-test-123",
            name="Small Test Collection",
            type="external",
            source_path=str(self.source_folder)
        )

        async def mock_get_collection(collection_id):
            return self.mock_collection

        self.mock_library_manager.get_collection = AsyncMock(side_effect=mock_get_collection)

        self.mock_director = Mock()
        self.mock_director.processing_coordinator = Mock()
        self.mock_director.processing_coordinator.process_with_auto_detection = Mock(
            return_value=["task_auto_123"]
        )
        self.mock_director.task_monitor = Mock()
        self.mock_director.task_monitor.register_callback = Mock()

        self.service = DirectorIntegrationService(
            app=self.mock_app,
            library_manager=self.mock_library_manager,
            director=self.mock_director
        )

    def tearDown(self):
        """Clean up"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_process_folder_item_hierarchical_structure(self):
        """Test processing folder item creates hierarchical structure"""
        # Create folder item
        folder_item = CollectionItem(
            id="item-folder-1",
            collection_id="small-test-123",
            type="folder",
            source_path=str(self.source_folder),
            local_path=str(self.source_folder),
            name="Small Test"
        )

        # Mock get_item
        async def mock_get_item(item_id):
            return folder_item

        self.mock_library_manager.get_item = AsyncMock(side_effect=mock_get_item)
        self.mock_library_manager.update_item = AsyncMock()

        # Process
        async def run_test():
            task_ids = await self.service.process_items(
                collection_id="small-test-123",
                item_ids=["item-folder-1"],
                plan_name="Default",
                workflow_name="Catalogue"
            )
            return task_ids

        task_ids = asyncio.run(run_test())

        # Verify task submitted
        self.assertGreater(len(task_ids), 0)

        # Verify hierarchical output structure was created
        output_base = Path(self.temp_dir) / "processed"
        self.assertTrue(output_base.exists())

        # Check for collection folder
        collection_folders = list(output_base.glob("Small_Test_Collection"))
        self.assertEqual(len(collection_folders), 1)

        # Check for date folder
        today = datetime.now().strftime('%Y-%m-%d')
        date_folders = list(output_base.glob(f"Small_Test_Collection/{today}"))
        self.assertEqual(len(date_folders), 1)

        # Check for workflow folder
        workflow_folders = list(output_base.glob(f"Small_Test_Collection/{today}/Catalogue"))
        self.assertEqual(len(workflow_folders), 1)


if __name__ == '__main__':
    unittest.main()
