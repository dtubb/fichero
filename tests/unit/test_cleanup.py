"""
Unit tests for cleanup functionality
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta

from fichero.library.storage import LibraryStorage
from fichero.library.models import Collection, CollectionItem, ProcessingResult


class TestCleanupFunctionality(unittest.TestCase):
    """Test cleanup of processing outputs"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temporary directory for test database
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_library.db"
        self.storage = LibraryStorage(db_path=self.db_path)

        # Create temporary output directory
        self.output_dir = Path(self.temp_dir) / "processed"
        self.output_dir.mkdir()

        # Create test collection
        self.collection = Collection(
            name="Test Collection",
            type="local",
            local_path=str(Path(self.temp_dir) / "source")
        )
        self.storage.add_collection(self.collection)

        # Create test items
        self.item1 = CollectionItem(
            collection_id=self.collection.id,
            name="Item 1",
            type="folder",
            source_path=str(Path(self.temp_dir) / "source" / "item1")
        )
        self.storage.add_collection_item(self.item1)

        self.item2 = CollectionItem(
            collection_id=self.collection.id,
            name="Item 2",
            type="folder",
            source_path=str(Path(self.temp_dir) / "source" / "item2")
        )
        self.storage.add_collection_item(self.item2)

    def tearDown(self):
        """Clean up test fixtures"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def _create_test_output(self, item_id: str, subfolder: str = "test_output") -> Path:
        """Create a test output directory with some files"""
        output_path = self.output_dir / subfolder
        output_path.mkdir(parents=True, exist_ok=True)

        # Create some test files
        (output_path / "file1.txt").write_text("test content 1")
        (output_path / "file2.txt").write_text("test content 2")

        # Create subdirectory with files
        subdir = output_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("test content 3")

        return output_path

    def test_cleanup_by_item_dry_run(self):
        """Test dry-run cleanup for a specific item"""
        # Create test output
        output_path = self._create_test_output(self.item1.id, "output1")

        # Create processing result
        result = ProcessingResult(
            item_id=self.item1.id,
            workflow="TestWorkflow",
            status="success",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            output_paths=[str(output_path)]
        )
        self.storage.add_processing_result(result)

        # Dry-run cleanup
        stats = self.storage.cleanup_processing_outputs(
            item_id=self.item1.id,
            dry_run=True
        )

        # Verify stats
        self.assertEqual(stats['files_deleted'], 3)
        self.assertEqual(stats['dirs_deleted'], 2)  # subdir + output_path
        self.assertGreater(stats['bytes_freed'], 0)
        self.assertEqual(stats['records_deleted'], 1)
        self.assertEqual(len(stats['deleted_paths']), 1)
        self.assertEqual(len(stats['errors']), 0)

        # Verify files still exist (dry run)
        self.assertTrue(output_path.exists())
        self.assertTrue((output_path / "file1.txt").exists())

        # Verify database record still exists
        history = self.storage.get_processing_history(self.item1.id)
        self.assertEqual(len(history), 1)

    def test_cleanup_by_item_execute(self):
        """Test actual cleanup execution for a specific item"""
        # Create test output
        output_path = self._create_test_output(self.item1.id, "output2")

        # Create processing result
        result = ProcessingResult(
            item_id=self.item1.id,
            workflow="TestWorkflow",
            status="success",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            output_paths=[str(output_path)]
        )
        self.storage.add_processing_result(result)

        # Execute cleanup
        stats = self.storage.cleanup_processing_outputs(
            item_id=self.item1.id,
            dry_run=False
        )

        # Verify stats
        self.assertEqual(stats['files_deleted'], 3)
        self.assertEqual(stats['dirs_deleted'], 2)
        self.assertEqual(stats['records_deleted'], 1)

        # Verify files are deleted
        self.assertFalse(output_path.exists())

        # Verify database record is deleted
        history = self.storage.get_processing_history(self.item1.id)
        self.assertEqual(len(history), 0)

    def test_cleanup_by_collection(self):
        """Test cleanup for entire collection"""
        # Create outputs for both items
        output1 = self._create_test_output(self.item1.id, "output_item1")
        output2 = self._create_test_output(self.item2.id, "output_item2")

        # Create processing results
        result1 = ProcessingResult(
            item_id=self.item1.id,
            workflow="TestWorkflow",
            status="success",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            output_paths=[str(output1)]
        )
        self.storage.add_processing_result(result1)

        result2 = ProcessingResult(
            item_id=self.item2.id,
            workflow="TestWorkflow",
            status="success",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            output_paths=[str(output2)]
        )
        self.storage.add_processing_result(result2)

        # Cleanup by collection
        stats = self.storage.cleanup_processing_outputs(
            collection_id=self.collection.id,
            dry_run=False
        )

        # Verify both items cleaned up
        self.assertEqual(stats['files_deleted'], 6)  # 3 files per item
        self.assertEqual(stats['dirs_deleted'], 4)   # 2 dirs per item
        self.assertEqual(stats['records_deleted'], 2)
        self.assertEqual(len(stats['deleted_paths']), 2)

        # Verify files are deleted
        self.assertFalse(output1.exists())
        self.assertFalse(output2.exists())

    def test_cleanup_by_date(self):
        """Test cleanup for outputs before a specific date"""
        # Create old output
        old_output = self._create_test_output(self.item1.id, "old_output")
        old_date = datetime.now() - timedelta(days=10)
        old_result = ProcessingResult(
            item_id=self.item1.id,
            workflow="OldWorkflow",
            status="success",
            started_at=old_date,
            completed_at=old_date,
            output_paths=[str(old_output)]
        )
        self.storage.add_processing_result(old_result)

        # Create new output
        new_output = self._create_test_output(self.item2.id, "new_output")
        new_result = ProcessingResult(
            item_id=self.item2.id,
            workflow="NewWorkflow",
            status="success",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            output_paths=[str(new_output)]
        )
        self.storage.add_processing_result(new_result)

        # Cleanup outputs before 5 days ago
        cutoff_date = datetime.now() - timedelta(days=5)
        stats = self.storage.cleanup_processing_outputs(
            before_date=cutoff_date,
            dry_run=False
        )

        # Verify only old output cleaned up
        self.assertEqual(stats['files_deleted'], 3)
        self.assertEqual(stats['records_deleted'], 1)
        self.assertFalse(old_output.exists())
        self.assertTrue(new_output.exists())

        # Verify only old record deleted
        old_history = self.storage.get_processing_history(self.item1.id)
        new_history = self.storage.get_processing_history(self.item2.id)
        self.assertEqual(len(old_history), 0)
        self.assertEqual(len(new_history), 1)

    def test_cleanup_multiple_outputs_per_item(self):
        """Test cleanup when item has multiple processing results"""
        # Create multiple outputs for same item
        output1 = self._create_test_output(self.item1.id, "run1")
        output2 = self._create_test_output(self.item1.id, "run2")

        result1 = ProcessingResult(
            item_id=self.item1.id,
            workflow="Run1",
            status="success",
            started_at=datetime.now() - timedelta(hours=2),
            completed_at=datetime.now() - timedelta(hours=2),
            output_paths=[str(output1)]
        )
        self.storage.add_processing_result(result1)

        result2 = ProcessingResult(
            item_id=self.item1.id,
            workflow="Run2",
            status="success",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            output_paths=[str(output2)]
        )
        self.storage.add_processing_result(result2)

        # Cleanup all outputs for item
        stats = self.storage.cleanup_processing_outputs(
            item_id=self.item1.id,
            dry_run=False
        )

        # Verify both outputs cleaned up
        self.assertEqual(stats['files_deleted'], 6)
        self.assertEqual(stats['records_deleted'], 2)
        self.assertFalse(output1.exists())
        self.assertFalse(output2.exists())

    def test_cleanup_nonexistent_output_path(self):
        """Test cleanup when output path doesn't exist on filesystem"""
        # Create processing result with nonexistent path
        nonexistent_path = self.output_dir / "does_not_exist"
        result = ProcessingResult(
            item_id=self.item1.id,
            workflow="TestWorkflow",
            status="success",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            output_paths=[str(nonexistent_path)]
        )
        self.storage.add_processing_result(result)

        # Cleanup should handle gracefully
        stats = self.storage.cleanup_processing_outputs(
            item_id=self.item1.id,
            dry_run=False
        )

        # Verify database record still deleted even though files don't exist
        self.assertEqual(stats['files_deleted'], 0)
        self.assertEqual(stats['records_deleted'], 1)
        self.assertEqual(len(stats['errors']), 0)

        # Verify database record is deleted
        history = self.storage.get_processing_history(self.item1.id)
        self.assertEqual(len(history), 0)

    def test_cleanup_no_matching_results(self):
        """Test cleanup when no results match criteria"""
        stats = self.storage.cleanup_processing_outputs(
            item_id="nonexistent-item-id",
            dry_run=False
        )

        # Should return empty stats
        self.assertEqual(stats['files_deleted'], 0)
        self.assertEqual(stats['records_deleted'], 0)
        self.assertEqual(len(stats['deleted_paths']), 0)

    def test_get_processing_results_by_collection(self):
        """Test querying processing results by collection"""
        # Create results for items in collection
        result1 = ProcessingResult(
            item_id=self.item1.id,
            workflow="Test1",
            status="success",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            output_paths=[]
        )
        self.storage.add_processing_result(result1)

        result2 = ProcessingResult(
            item_id=self.item2.id,
            workflow="Test2",
            status="success",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            output_paths=[]
        )
        self.storage.add_processing_result(result2)

        # Query by collection
        results = self.storage.get_processing_results_by_collection(self.collection.id)

        # Verify both results returned
        self.assertEqual(len(results), 2)
        workflows = {r.workflow for r in results}
        self.assertEqual(workflows, {"Test1", "Test2"})

    def test_get_processing_results_before_date(self):
        """Test querying processing results before date"""
        # Create old result
        old_result = ProcessingResult(
            item_id=self.item1.id,
            workflow="OldRun",
            status="success",
            started_at=datetime.now() - timedelta(days=10),
            completed_at=datetime.now() - timedelta(days=10),
            output_paths=[]
        )
        self.storage.add_processing_result(old_result)

        # Create new result
        new_result = ProcessingResult(
            item_id=self.item2.id,
            workflow="NewRun",
            status="success",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            output_paths=[]
        )
        self.storage.add_processing_result(new_result)

        # Query before 5 days ago
        cutoff = datetime.now() - timedelta(days=5)
        results = self.storage.get_processing_results_before_date(cutoff)

        # Verify only old result returned
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].workflow, "OldRun")


if __name__ == '__main__':
    unittest.main()
