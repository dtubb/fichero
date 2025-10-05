"""
Unit tests for Director Integration Service
"""

import unittest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import tempfile
import shutil

from fichero.library.director_integration import DirectorIntegrationService
from fichero.library.models import CollectionItem, ProcessingResult


class TestDirectorIntegrationService(unittest.TestCase):
    """Test DirectorIntegrationService"""

    def setUp(self):
        """Set up test fixtures"""
        # Create mock app
        self.mock_app = Mock()
        self.mock_app.paths = Mock()

        # Create temp directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.mock_app.paths.data = self.temp_dir

        # Create mock library manager
        self.mock_library_manager = Mock()
        self.mock_library_manager.storage = Mock()

        # Create mock director
        self.mock_director = Mock()
        self.mock_director.processing_coordinator = Mock()
        self.mock_director.get_task_result = Mock()
        self.mock_director.get_task_status = Mock()
        self.mock_director.cancel_task = Mock()

        # Create mock task monitor
        self.mock_task_monitor = Mock()
        self.mock_task_monitor.register_callback = Mock()
        self.mock_director.task_monitor = self.mock_task_monitor

        # Create service
        self.service = DirectorIntegrationService(
            app=self.mock_app,
            library_manager=self.mock_library_manager,
            director=self.mock_director
        )

    def tearDown(self):
        """Clean up test fixtures"""
        # Remove temp directory
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_initialization(self):
        """Test service initialization"""
        self.assertIsNotNone(self.service)
        self.assertEqual(self.service.app, self.mock_app)
        self.assertEqual(self.service.library_manager, self.mock_library_manager)
        self.assertEqual(self.service.director, self.mock_director)
        self.assertIsNotNone(self.service.output_parser)
        self.assertEqual(len(self.service.active_tasks), 0)

    def test_process_file_batch_creates_temp_folder(self):
        """Test that batch processing creates proper temp folder structure"""
        # Create test files
        test_file1 = Path(self.temp_dir) / "test1.jpg"
        test_file2 = Path(self.temp_dir) / "test2.jpg"
        test_file1.write_text("test1")
        test_file2.write_text("test2")

        # Create mock items
        item1 = CollectionItem(
            id="item1",
            collection_id="col1",
            type="file",
            source_path=str(test_file1),
            name="test1.jpg"
        )
        item2 = CollectionItem(
            id="item2",
            collection_id="col1",
            type="file",
            source_path=str(test_file2),
            name="test2.jpg"
        )

        # Mock library manager methods
        async def mock_update_item(item):
            return item

        self.mock_library_manager.update_item = AsyncMock(side_effect=mock_update_item)

        # Mock director submission
        self.mock_director.processing_coordinator.process_folders = Mock(return_value="task_123")

        # Run batch processing
        file_items = [
            ("item1", item1, test_file1),
            ("item2", item2, test_file2)
        ]

        output_path = Path(self.temp_dir) / "output"

        async def run_test():
            task_ids = await self.service._process_file_batch(
                file_items=file_items,
                output_base_path=output_path,
                plan_name="Default",
                workflow_name="default"
            )
            return task_ids

        task_ids = asyncio.run(run_test())

        # Verify task was submitted
        self.assertEqual(len(task_ids), 1)
        self.assertEqual(task_ids[0], "task_123")

        # Verify batch folder structure was created
        batch_folders = list(output_path.glob("batch_*"))
        self.assertEqual(len(batch_folders), 1)

        batch_folder = batch_folders[0]
        input_folder = batch_folder / "input"
        self.assertTrue(input_folder.exists())

        # Verify files were copied
        copied_files = list(input_folder.glob("*.jpg"))
        self.assertEqual(len(copied_files), 2)

        # Verify task was tracked
        self.assertIn("task_123", self.service.active_tasks)
        task_info = self.service.active_tasks["task_123"]
        self.assertEqual(task_info['type'], 'batch')
        self.assertEqual(len(task_info['item_ids']), 2)

    def test_process_items_separates_files_and_folders(self):
        """Test that process_items correctly separates files and folders"""
        # Create test structure
        test_file = Path(self.temp_dir) / "test.jpg"
        test_folder = Path(self.temp_dir) / "folder"
        test_file.write_text("test")
        test_folder.mkdir()

        # Create mock items
        file_item = CollectionItem(
            id="item1",
            collection_id="col1",
            type="file",
            source_path=str(test_file),
            local_path=str(test_file),
            name="test.jpg"
        )
        folder_item = CollectionItem(
            id="item2",
            collection_id="col1",
            type="folder",
            source_path=str(test_folder),
            local_path=str(test_folder),
            name="folder"
        )

        # Mock library manager
        async def mock_get_item(item_id):
            if item_id == "item1":
                return file_item
            elif item_id == "item2":
                return folder_item
            return None

        self.mock_library_manager.get_item = AsyncMock(side_effect=mock_get_item)
        self.mock_library_manager.update_item = AsyncMock()

        # Mock director
        self.mock_director.processing_coordinator.process_folders = Mock(return_value="task_file")
        self.mock_director.processing_coordinator.process_with_auto_detection = Mock(return_value=["task_folder"])

        # Run processing
        async def run_test():
            task_ids = await self.service.process_items(
                collection_id="col1",
                item_ids=["item1", "item2"],
                plan_name="Default",
                workflow_name="default"
            )
            return task_ids

        task_ids = asyncio.run(run_test())

        # Verify both file and folder were processed
        self.assertEqual(len(task_ids), 2)  # 1 for file batch, 1 for folder
        self.assertIn("task_file", task_ids)
        self.assertIn("task_folder", task_ids)

    def test_update_item_progress(self):
        """Test progress update for a single item"""
        # Create mock item
        item = CollectionItem(
            id="item1",
            collection_id="col1",
            type="file",
            name="test.jpg"
        )

        self.mock_library_manager.storage.get_item = Mock(return_value=item)
        self.mock_library_manager.storage.update_item = Mock()

        # Update progress
        progress_data = {
            'progress': 50,
            'status': 'running'
        }

        self.service._update_item_progress("item1", "task_123", progress_data)

        # Verify item was updated
        self.assertEqual(item.metadata['director_task_id'], "task_123")
        self.assertEqual(item.metadata['director_progress'], 50)
        self.assertEqual(item.metadata['director_status'], 'running')
        self.mock_library_manager.storage.update_item.assert_called_once()

    def test_get_processing_status(self):
        """Test getting processing status for an item"""
        # Add active task
        self.service.active_tasks["task_123"] = {
            'item_id': 'item1',
            'type': 'file',
            'started_at': datetime.now()
        }

        # Mock director status
        from fichero.director.backends.implementations.base import ProcessingStatus
        mock_status = ProcessingStatus.RUNNING

        self.mock_director.get_task_status = Mock(return_value=mock_status)

        # Get status
        status = self.service.get_processing_status("item1")

        # Verify
        self.assertIsNotNone(status)
        self.assertEqual(status['task_id'], "task_123")
        self.assertEqual(status['status'], mock_status)

    def test_get_processing_status_no_active_task(self):
        """Test getting status when no active task exists"""
        status = self.service.get_processing_status("item1")
        self.assertIsNone(status)

    def test_cancel_processing(self):
        """Test cancelling processing for an item"""
        # Create mock item
        item = CollectionItem(id="item1", collection_id="col1")

        # Add active task
        self.service.active_tasks["task_123"] = {
            'item_id': 'item1',
            'type': 'file',
            'started_at': datetime.now()
        }

        # Mock methods
        self.mock_director.cancel_task = Mock(return_value=True)
        self.mock_library_manager.get_item = AsyncMock(return_value=item)
        self.mock_library_manager.update_item = AsyncMock()

        # Cancel
        async def run_test():
            result = await self.service.cancel_processing("item1")
            return result

        result = asyncio.run(run_test())

        # Verify
        self.assertTrue(result)
        self.assertNotIn("task_123", self.service.active_tasks)
        self.assertEqual(item.metadata['director_status'], 'cancelled')


class TestDirectorOutputParser(unittest.TestCase):
    """Test DirectorOutputParser"""

    def setUp(self):
        """Set up test fixtures"""
        from fichero.library.director_output_parser import DirectorOutputParser
        self.parser = DirectorOutputParser()

        # Create temp directory
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = Path(self.temp_dir) / "output"
        self.output_dir.mkdir()

    def tearDown(self):
        """Clean up"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_parse_empty_folder(self):
        """Test parsing an empty output folder"""
        result = self.parser.parse_output_folder(self.output_dir)

        self.assertEqual(len(result['input_files']), 0)
        self.assertEqual(len(result['prepared_files']), 0)
        self.assertEqual(len(result['transcriptions']), 0)
        self.assertEqual(len(result['word_docs']), 0)

    def test_parse_nonexistent_folder(self):
        """Test parsing a nonexistent folder"""
        result = self.parser.parse_output_folder(Path("/nonexistent"))

        self.assertEqual(len(result['input_files']), 0)

    def test_parse_with_documents(self):
        """Test parsing folder with documents"""
        # Create documents folder
        docs_dir = self.output_dir / "documents"
        docs_dir.mkdir()

        # Add test files
        (docs_dir / "test1.jpg").write_text("test1")
        (docs_dir / "test2.jpg").write_text("test2")

        result = self.parser.parse_output_folder(self.output_dir)

        self.assertEqual(len(result['input_files']), 2)

    def test_parse_with_prepared_files(self):
        """Test parsing folder with prepared files"""
        # Create assets/prepared folder
        prepared_dir = self.output_dir / "assets" / "prepared"
        prepared_dir.mkdir(parents=True)

        # Add test files
        (prepared_dir / "test1.jpg").write_text("prepared1")
        (prepared_dir / "test2.jpg").write_text("prepared2")

        result = self.parser.parse_output_folder(self.output_dir)

        self.assertEqual(len(result['prepared_files']), 2)

    def test_get_file_outputs(self):
        """Test getting outputs for a specific file"""
        # Create structure
        docs_dir = self.output_dir / "documents"
        prepared_dir = self.output_dir / "assets" / "prepared"
        docs_dir.mkdir(parents=True)
        prepared_dir.mkdir(parents=True)

        # Add files
        (docs_dir / "test1.jpg").write_text("original")
        (prepared_dir / "test1.jpg").write_text("prepared")

        outputs = self.parser.get_file_outputs(self.output_dir, "test1.jpg")

        self.assertEqual(len(outputs), 1)
        self.assertIsNotNone(outputs[0].original_file)
        self.assertIsNotNone(outputs[0].prepared_file)

    def test_get_all_file_outputs(self):
        """Test getting all file outputs"""
        # Create structure
        docs_dir = self.output_dir / "documents"
        prepared_dir = self.output_dir / "assets" / "prepared"
        docs_dir.mkdir(parents=True)
        prepared_dir.mkdir(parents=True)

        # Add files
        (docs_dir / "test1.jpg").write_text("original1")
        (docs_dir / "test2.jpg").write_text("original2")
        (prepared_dir / "test1.jpg").write_text("prepared1")
        (prepared_dir / "test2.jpg").write_text("prepared2")

        outputs = self.parser.get_all_file_outputs(self.output_dir)

        self.assertEqual(len(outputs), 2)
        self.assertTrue(all(o.original_file for o in outputs))
        self.assertTrue(all(o.prepared_file for o in outputs))


if __name__ == '__main__':
    unittest.main()
