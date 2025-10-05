"""
Unit tests for Director FolderProcessor

Tests folder detection, preparation, and task submission functionality.
"""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil

from fichero.director.folder_processor import FolderProcessor


class TestFolderProcessor(unittest.TestCase):
    """Test FolderProcessor functionality"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temp directory structure
        self.temp_dir = tempfile.mkdtemp()
        self.input_dir = Path(self.temp_dir) / "input"
        self.output_dir = Path(self.temp_dir) / "output"
        self.input_dir.mkdir(parents=True)
        self.output_dir.mkdir(parents=True)

        # Create test folder structure with images
        self.folder1 = self.input_dir / "folder1"
        self.folder2 = self.input_dir / "folder2"
        self.folder1.mkdir()
        self.folder2.mkdir()

        # Add test images
        (self.folder1 / "test1.jpg").write_text("fake image 1")
        (self.folder1 / "test2.jpg").write_text("fake image 2")
        (self.folder2 / "test3.jpg").write_text("fake image 3")

        # Create mock director
        self.mock_director = Mock()
        self.mock_director.task_manager = Mock()
        self.mock_director.task_manager.submit_folders = Mock(return_value=["task1", "task2"])

        # Create mock app settings
        self.mock_settings = Mock()
        self.mock_settings.get_setting = Mock(return_value='option_alphabetical')

        with patch('fichero.config.core.settings.get_app_settings', return_value=self.mock_settings):
            self.processor = FolderProcessor(self.mock_director)

    def tearDown(self):
        """Clean up test fixtures"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_initialization(self):
        """Test FolderProcessor initializes correctly"""
        self.assertIsNotNone(self.processor)

    def test_detect_folders_with_images(self):
        """Test detecting folders containing images"""
        with patch('fichero.config.core.settings.get_app_settings', return_value=self.mock_settings):
            folders = self.processor._find_folders_with_images(self.input_dir)

        self.assertEqual(len(folders), 2)
        folder_names = [f.name for f in folders]
        self.assertIn("folder1", folder_names)
        self.assertIn("folder2", folder_names)

    def test_detect_and_prepare_folders_creates_output_structure(self):
        """Test that detect_and_prepare_folders creates proper output structure"""
        with patch('fichero.config.core.settings.get_app_settings', return_value=self.mock_settings):
            with patch('fichero.utils.folder_preparation.prepare_folder') as mock_prepare:
                # Mock prepare_folder to return paths
                mock_prepare.side_effect = lambda folder, output: output / folder.name

                prepared = self.processor.detect_and_prepare_folders([self.input_dir], self.output_dir)

        self.assertEqual(len(prepared), 2)

    def test_alphabetical_sorting(self):
        """Test alphabetical folder sorting"""
        # Create folders with specific names
        folder_a = self.input_dir / "a_first"
        folder_z = self.input_dir / "z_last"
        folder_m = self.input_dir / "m_middle"

        for folder in [folder_z, folder_a, folder_m]:  # Create in random order
            folder.mkdir()
            (folder / "test.jpg").write_text("test")

        with patch('fichero.config.core.settings.get_app_settings', return_value=self.mock_settings):
            folders = self.processor._find_folders_with_images(self.input_dir)

        folder_names = [f.name for f in folders]
        # Should be sorted alphabetically by default
        self.assertEqual(folder_names, ["a_first", "folder1", "folder2", "m_middle", "z_last"])

    def test_submit_processing_tasks(self):
        """Test submitting processing tasks for prepared folders"""
        prepared_folders = [self.folder1, self.folder2]

        # Mock director.process_folders to return task IDs
        self.mock_director.process_folders = Mock(side_effect=["task1", "task2"])

        with patch('fichero.config.core.settings.get_app_settings', return_value=self.mock_settings):
            task_ids = self.processor.submit_processing_tasks(
                prepared_folders,
                "Test Plan",
                "test_workflow"
            )

        # Verify task IDs returned
        self.assertEqual(len(task_ids), 2)
        self.assertIn("task1", task_ids)
        self.assertIn("task2", task_ids)

    def test_get_task_statuses(self):
        """Test getting task statuses"""
        from fichero.director.backends.implementations.base import ProcessingStatus

        # Mock director.get_task_status
        self.mock_director.get_task_status = Mock(side_effect=[ProcessingStatus.COMPLETED, ProcessingStatus.RUNNING])

        with patch('fichero.config.core.settings.get_app_settings', return_value=self.mock_settings):
            statuses = self.processor.get_task_statuses(["task1", "task2"])

        self.assertEqual(statuses["task1"], "completed")
        self.assertEqual(statuses["task2"], "running")

    def test_empty_input_folder(self):
        """Test handling of empty input folder"""
        empty_dir = Path(self.temp_dir) / "empty"
        empty_dir.mkdir()

        with patch('fichero.config.core.settings.get_app_settings', return_value=self.mock_settings):
            folders = self.processor._find_folders_with_images(empty_dir)

        self.assertEqual(len(folders), 0)

    def test_nested_folders_detected(self):
        """Test that nested folders with images are detected"""
        # Create nested structure
        nested = self.folder1 / "nested"
        nested.mkdir()
        (nested / "nested_image.jpg").write_text("nested")

        with patch('fichero.config.core.settings.get_app_settings', return_value=self.mock_settings):
            folders = self.processor._find_folders_with_images(self.input_dir)

        # Should detect top-level folders that contain images recursively
        self.assertGreater(len(folders), 0)


class TestFolderProcessorEdgeCases(unittest.TestCase):
    """Test edge cases and error handling"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()

        # Create mock director
        mock_director = Mock()

        mock_settings = Mock()
        mock_settings.get_setting = Mock(return_value='option_alphabetical')

        with patch('fichero.config.core.settings.get_app_settings', return_value=mock_settings):
            self.processor = FolderProcessor(mock_director)

    def tearDown(self):
        """Clean up test fixtures"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_nonexistent_input_folder(self):
        """Test handling of non-existent input folder"""
        nonexistent = Path(self.temp_dir) / "nonexistent"

        with patch('fichero.config.core.settings.get_app_settings') as mock_settings:
            mock_settings.return_value.get_setting.return_value = 'alphabetical'
            folders = self.processor._find_folders_with_images(nonexistent)

        self.assertEqual(len(folders), 0)

    def test_folder_with_no_images(self):
        """Test folder containing only non-image files"""
        no_images = Path(self.temp_dir) / "no_images"
        no_images.mkdir()
        (no_images / "text.txt").write_text("not an image")

        with patch('fichero.config.core.settings.get_app_settings') as mock_settings:
            mock_settings.return_value.get_setting.return_value = 'alphabetical'
            folders = self.processor._find_folders_with_images(Path(self.temp_dir))

        # Should not detect folder without images
        self.assertEqual(len(folders), 0)


if __name__ == '__main__':
    unittest.main()
