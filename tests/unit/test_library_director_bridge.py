"""
Unit tests for LibraryDirectorBridge

Tests the bridge between the library system and director processing.
"""

import unittest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import tempfile
import shutil

from fichero.library.director_bridge import LibraryDirectorBridge


class TestLibraryDirectorBridge(unittest.TestCase):
    """Test LibraryDirectorBridge functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()

        # Create mock director
        self.mock_director = Mock()
        self.mock_director.processing_coordinator = Mock()
        self.mock_director.get_task_status = Mock()
        self.mock_director.get_task_result = Mock()
        self.mock_director.cancel_task = Mock()

        # Create bridge
        self.bridge = LibraryDirectorBridge(self.mock_director)

    def tearDown(self):
        """Clean up test fixtures"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_initialization(self):
        """Test LibraryDirectorBridge initializes correctly"""
        self.assertIsNotNone(self.bridge)
        self.assertEqual(self.bridge.director, self.mock_director)

    def test_process_collection(self):
        """Test processing a collection"""
        collection_path = Path(self.temp_dir) / "collection"
        collection_path.mkdir()

        # Create minimal directory structure to pass initial checks
        # The bridge will report "No processing steps found" which is expected behavior

        # Run async test
        result = asyncio.run(self.bridge.process_collection(collection_path))

        # Should return a result (either success with steps or error with no steps)
        self.assertIn("success", result)
        self.assertIn("collection_path", result)

    def test_get_collection_processing_status(self):
        """Test getting collection processing status"""
        collection_path = Path(self.temp_dir) / "collection"
        collection_path.mkdir()

        # Create assets folder structure
        assets_path = collection_path / "assets"
        assets_path.mkdir()

        # Run async test
        result = asyncio.run(self.bridge.get_collection_processing_status(collection_path))

        # Verify result structure
        self.assertIn("collection_path", result)

    def test_process_collection_level(self):
        """Test processing a specific level of collection hierarchy"""
        collection_path = Path(self.temp_dir) / "collection"
        collection_path.mkdir()

        # Create sublevel folders
        sublevel1 = collection_path / "level1"
        sublevel1.mkdir()

        # Run async test
        result = asyncio.run(self.bridge.process_collection_level(collection_path, level=0))

        # Verify result
        self.assertTrue(result["success"])

    def test_preview_collection_structure(self):
        """Test previewing collection structure"""
        collection_path = Path(self.temp_dir) / "collection"
        collection_path.mkdir()

        # Create test structure
        subfolder = collection_path / "subfolder"
        subfolder.mkdir()
        (subfolder / "test.txt").write_text("test")

        # Run async test
        result = asyncio.run(self.bridge.preview_collection_structure(collection_path))

        # Verify result
        self.assertIn("collection_path", result)
        self.assertIn("structure", result)

    def test_get_level_paths(self):
        """Test getting paths at specific level"""
        collection_path = Path(self.temp_dir) / "collection"
        collection_path.mkdir()

        # Create multilevel structure
        level1 = collection_path / "level1"
        level1.mkdir()
        level2 = level1 / "level2"
        level2.mkdir()

        # Test level 0
        paths = self.bridge._get_level_paths(collection_path, 0)
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0], collection_path)

    def test_build_structure_tree(self):
        """Test building structure tree"""
        collection_path = Path(self.temp_dir) / "collection"
        collection_path.mkdir()

        # Create test structure
        subfolder = collection_path / "subfolder"
        subfolder.mkdir()
        (collection_path / "file.txt").write_text("test")

        # Build tree
        tree = self.bridge._build_structure_tree(collection_path, max_depth=2)

        # Verify structure
        self.assertEqual(tree["type"], "directory")
        self.assertEqual(tree["name"], "collection")

    def test_process_collection_with_steps(self):
        """Test processing collection with specific steps"""
        collection_path = Path(self.temp_dir) / "collection"
        collection_path.mkdir()

        # Create assets folder
        assets_path = collection_path / "assets"
        assets_path.mkdir()

        # Mock director
        self.mock_director.process_with_auto_detection = AsyncMock(
            return_value={"success": True}
        )

        # Run async test
        result = asyncio.run(self.bridge.process_collection(collection_path, steps=["step1"]))

        # Should handle gracefully (no steps available)
        self.assertFalse(result["success"])


class TestLibraryDirectorBridgeErrorHandling(unittest.TestCase):
    """Test error handling in LibraryDirectorBridge"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_director = Mock()
        self.bridge = LibraryDirectorBridge(self.mock_director)

    def test_process_collection_with_missing_path(self):
        """Test processing collection with missing path"""
        self.temp_dir = tempfile.mkdtemp()
        collection_path = Path(self.temp_dir) / "nonexistent"

        # Run async test
        result = asyncio.run(self.bridge.process_collection(collection_path))

        # Should handle missing path gracefully
        self.assertFalse(result["success"])

        # Cleanup
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_director_error_handling(self):
        """Test that director errors are handled correctly"""
        self.temp_dir = tempfile.mkdtemp()
        collection_path = Path(self.temp_dir) / "collection"
        collection_path.mkdir()

        # Create assets folder
        assets_path = collection_path / "assets"
        assets_path.mkdir()

        # Mock director to raise error
        self.mock_director.process_with_auto_detection = AsyncMock(
            side_effect=Exception("Director error")
        )

        # Run async test
        result = asyncio.run(self.bridge.process_collection(collection_path))

        # Should return error in result
        self.assertFalse(result["success"])
        self.assertIn("error", result)

        # Cleanup
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)


if __name__ == '__main__':
    unittest.main()
