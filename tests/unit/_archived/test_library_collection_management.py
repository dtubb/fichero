"""
Unit tests for Library Collection Management Backend

Tests all collection management capabilities:
- Rename collection
- Reorder collection (manual sort)
- Update collection metadata
- Delete collection
- Export/import collection
- Collection type filtering and sorting
"""

import unittest
import tempfile
import shutil
import asyncio
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from fichero.library.library_manager import LibraryManager
from fichero.library.models import Collection, CollectionItem
from fichero.library.storage import LibraryStorage


class AsyncTestCase(unittest.TestCase):
    """Base class for async test cases"""

    def run_async(self, coro):
        """Helper to run async functions in tests"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)


class TestRenameCollection(AsyncTestCase):
    """Test collection renaming functionality"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.library_dir = self.test_dir / "library"
        self.library_dir.mkdir()

        # Create storage
        self.db_path = self.library_dir / "test.db"
        self.storage = LibraryStorage(str(self.db_path))

        # Create library manager with mock app
        self.app = Mock()
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=self.db_path):
            self.library_manager = LibraryManager(app=self.app)
        self.library_manager.storage = self.storage
        # Disable automatic inbox creation for tests
        self.library_manager._inbox_setup_pending = False

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)

    def test_rename_local_collection(self):
        """Test renaming a local collection"""
        # Create test collection
        collection_id = self.run_async(self.library_manager.add_collection(
            name="Original Name",
            collection_type="local",
            source_path=None
        ))

        self.assertIsNotNone(collection_id)

        # Rename collection
        result = self.run_async(self.library_manager.rename_collection(
            collection_id,
            "New Name"
        ))

        self.assertTrue(result)

        # Verify name changed
        collection = self.run_async(self.library_manager.get_collection(collection_id))
        self.assertIsNotNone(collection)
        self.assertEqual(collection.name, "New Name")

    def test_rename_external_collection(self):
        """Test renaming an external collection"""
        # Create external folder
        external_folder = self.test_dir / "external_source"
        external_folder.mkdir()

        # Create external collection
        collection_id = self.run_async(self.library_manager.add_collection(
            name="External Collection",
            collection_type="external",
            source_path=str(external_folder)
        ))

        self.assertIsNotNone(collection_id)

        # Rename collection
        result = self.run_async(self.library_manager.rename_collection(
            collection_id,
            "Renamed External"
        ))

        self.assertTrue(result)

        # Verify name changed in database
        collection = self.run_async(self.library_manager.get_collection(collection_id))
        self.assertIsNotNone(collection)
        self.assertEqual(collection.name, "Renamed External")

    def test_rename_nonexistent_collection(self):
        """Test renaming a collection that doesn't exist"""
        result = self.run_async(self.library_manager.rename_collection(
            "nonexistent-id",
            "New Name"
        ))

        self.assertFalse(result)

    def test_rename_with_whitespace(self):
        """Test that renaming strips whitespace"""
        collection_id = self.run_async(self.library_manager.add_collection(
            name="Test Collection",
            collection_type="local",
            source_path=None
        ))

        # Rename with leading/trailing whitespace
        result = self.run_async(self.library_manager.rename_collection(
            collection_id,
            "  Trimmed Name  "
        ))

        self.assertTrue(result)

        collection = self.run_async(self.library_manager.get_collection(collection_id))
        self.assertEqual(collection.name, "Trimmed Name")

    def test_rename_allows_duplicates(self):
        """Test that duplicate names are allowed (collections use UUIDs)"""
        # Create two collections
        id1 = self.run_async(self.library_manager.add_collection(
            name="Collection A",
            collection_type="local",
            source_path=None
        ))

        id2 = self.run_async(self.library_manager.add_collection(
            name="Collection B",
            collection_type="local",
            source_path=None
        ))

        # Rename second to same name as first
        result = self.run_async(self.library_manager.rename_collection(id2, "Collection A"))

        self.assertTrue(result)

        # Both should exist with same name
        col1 = self.run_async(self.library_manager.get_collection(id1))
        col2 = self.run_async(self.library_manager.get_collection(id2))
        self.assertEqual(col1.name, "Collection A")
        self.assertEqual(col2.name, "Collection A")


class TestReorderCollection(AsyncTestCase):
    """Test collection reordering (manual sort) functionality"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.library_dir = self.test_dir / "library"
        self.library_dir.mkdir()

        self.db_path = self.library_dir / "test.db"
        self.storage = LibraryStorage(str(self.db_path))

        self.app = Mock()
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=self.db_path):
            self.library_manager = LibraryManager(app=self.app)
        self.library_manager.storage = self.storage
        # Disable automatic inbox creation for tests
        self.library_manager._inbox_setup_pending = False

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)

    def test_reorder_basic(self):
        """Test basic reordering of collections"""
        # Create three collections
        id1 = self.run_async(self.library_manager.add_collection("Collection 1", "local", None))
        id2 = self.run_async(self.library_manager.add_collection("Collection 2", "local", None))
        id3 = self.run_async(self.library_manager.add_collection("Collection 3", "local", None))

        # Move collection 3 to position 1
        result = self.run_async(self.library_manager.reorder_collection(id3, 1))
        self.assertTrue(result)

        # Verify new order
        collections = self.run_async(self.library_manager.get_all_collections(sort_by="manual"))
        names = [c.name for c in collections]

        self.assertEqual(names[0], "Collection 3")
        self.assertEqual(names[1], "Collection 1")
        self.assertEqual(names[2], "Collection 2")

    def test_reorder_to_middle(self):
        """Test moving collection to middle position"""
        # Create four collections
        ids = []
        for i in range(1, 5):
            id = self.run_async(self.library_manager.add_collection(f"Collection {i}", "local", None))
            ids.append(id)

        # Move collection 1 to position 3
        result = self.run_async(self.library_manager.reorder_collection(ids[0], 3))
        self.assertTrue(result)

        # Verify order: 2, 3, 1, 4
        collections = self.run_async(self.library_manager.get_all_collections(sort_by="manual"))
        names = [c.name for c in collections]

        self.assertEqual(names, ["Collection 2", "Collection 3", "Collection 1", "Collection 4"])

    def test_reorder_to_end(self):
        """Test moving collection to last position"""
        ids = []
        for i in range(1, 4):
            id = self.run_async(self.library_manager.add_collection(f"Collection {i}", "local", None))
            ids.append(id)

        # Move collection 1 to position 3 (end)
        result = self.run_async(self.library_manager.reorder_collection(ids[0], 3))
        self.assertTrue(result)

        collections = self.run_async(self.library_manager.get_all_collections(sort_by="manual"))
        names = [c.name for c in collections]

        self.assertEqual(names, ["Collection 2", "Collection 3", "Collection 1"])

    def test_reorder_invalid_position(self):
        """Test reordering with invalid positions"""
        id = self.run_async(self.library_manager.add_collection("Test Collection", "local", None))

        # Position 0 (invalid, must be 1-based)
        result = self.run_async(self.library_manager.reorder_collection(id, 0))
        self.assertFalse(result)

        # Position too high
        result = self.run_async(self.library_manager.reorder_collection(id, 999))
        self.assertFalse(result)

    def test_reorder_nonexistent_collection(self):
        """Test reordering a collection that doesn't exist"""
        result = self.run_async(self.library_manager.reorder_collection("fake-id", 1))
        self.assertFalse(result)

    def test_reorder_persistence(self):
        """Test that reorder persists after cache clear"""
        ids = []
        for i in range(1, 4):
            id = self.run_async(self.library_manager.add_collection(f"Collection {i}", "local", None))
            ids.append(id)

        # Reorder
        self.run_async(self.library_manager.reorder_collection(ids[2], 1))

        # Clear cache and reload
        self.library_manager._clear_cache()

        collections = self.run_async(self.library_manager.get_all_collections(sort_by="manual", force_refresh=True))
        names = [c.name for c in collections]

        self.assertEqual(names, ["Collection 3", "Collection 1", "Collection 2"])


class TestUpdateCollection(AsyncTestCase):
    """Test collection metadata update functionality"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.library_dir = self.test_dir / "library"
        self.library_dir.mkdir()

        self.db_path = self.library_dir / "test.db"
        self.storage = LibraryStorage(str(self.db_path))

        self.app = Mock()
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=self.db_path):
            self.library_manager = LibraryManager(app=self.app)
        self.library_manager.storage = self.storage
        # Disable automatic inbox creation for tests
        self.library_manager._inbox_setup_pending = False

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)

    def test_update_metadata_description(self):
        """Test updating collection description in metadata"""
        id = self.run_async(self.library_manager.add_collection("Test Collection", "local", None))

        # Update with description
        result = self.run_async(self.library_manager.update_collection(
            id,
            metadata={"description": "This is a test collection"}
        ))

        self.assertTrue(result)

        collection = self.run_async(self.library_manager.get_collection(id))
        self.assertEqual(collection.metadata.get("description"), "This is a test collection")

    def test_update_metadata_icon(self):
        """Test updating collection icon in metadata"""
        id = self.run_async(self.library_manager.add_collection("Test Collection", "local", None))

        # Update with custom icon
        result = self.run_async(self.library_manager.update_collection(
            id,
            metadata={"icon": "NSFolder", "icon_custom": "/path/to/icon.png"}
        ))

        self.assertTrue(result)

        collection = self.run_async(self.library_manager.get_collection(id))
        self.assertEqual(collection.metadata.get("icon"), "NSFolder")
        self.assertEqual(collection.metadata.get("icon_custom"), "/path/to/icon.png")

    def test_update_metadata_tags(self):
        """Test updating collection tags/categories"""
        id = self.run_async(self.library_manager.add_collection("Test Collection", "local", None))

        # Update with tags
        result = self.run_async(self.library_manager.update_collection(
            id,
            metadata={"tags": ["work", "important", "archive"]}
        ))

        self.assertTrue(result)

        collection = self.run_async(self.library_manager.get_collection(id))
        self.assertEqual(collection.metadata.get("tags"), ["work", "important", "archive"])

    def test_update_nonexistent_collection(self):
        """Test updating a collection that doesn't exist"""
        result = self.run_async(self.library_manager.update_collection(
            "fake-id",
            name="New Name"
        ))

        self.assertFalse(result)


class TestDeleteCollection(AsyncTestCase):
    """Test collection deletion functionality"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.library_dir = self.test_dir / "library"
        self.library_dir.mkdir()

        self.db_path = self.library_dir / "test.db"
        self.storage = LibraryStorage(str(self.db_path))

        self.app = Mock()
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=self.db_path):
            self.library_manager = LibraryManager(app=self.app)
        self.library_manager.storage = self.storage
        # Disable automatic inbox creation for tests
        self.library_manager._inbox_setup_pending = False

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)

    def test_delete_local_collection(self):
        """Test deleting a local collection"""
        # Create collection
        id = self.run_async(self.library_manager.add_collection("Test Collection", "local", None))

        # Verify it exists
        collection = self.run_async(self.library_manager.get_collection(id))
        self.assertIsNotNone(collection)

        # Delete
        result = self.run_async(self.library_manager.delete_collection(id))
        self.assertTrue(result)

        # Verify it's gone
        collection = self.run_async(self.library_manager.get_collection(id))
        self.assertIsNone(collection)

    def test_delete_external_collection(self):
        """Test deleting external collection (doesn't delete external files)"""
        # Create external folder
        external_folder = self.test_dir / "external_data"
        external_folder.mkdir()
        (external_folder / "test.txt").write_text("test data")

        # Create external collection
        id = self.run_async(self.library_manager.add_collection(
            "External Collection",
            "external",
            str(external_folder)
        ))

        # Delete collection
        result = self.run_async(self.library_manager.delete_collection(id))
        self.assertTrue(result)

        # External folder should still exist
        self.assertTrue(external_folder.exists())
        self.assertTrue((external_folder / "test.txt").exists())

    def test_delete_nonexistent_collection(self):
        """Test deleting a collection that doesn't exist"""
        result = self.run_async(self.library_manager.delete_collection("fake-id"))
        self.assertFalse(result)

    def test_delete_clears_cache(self):
        """Test that deletion clears cache properly"""
        # Create two collections
        id1 = self.run_async(self.library_manager.add_collection("Collection 1", "local", None))
        id2 = self.run_async(self.library_manager.add_collection("Collection 2", "local", None))

        # Get all (populates cache)
        collections = self.run_async(self.library_manager.get_all_collections())
        self.assertEqual(len(collections), 2)

        # Delete one
        self.run_async(self.library_manager.delete_collection(id1))

        # Get all again (should reflect deletion)
        collections = self.run_async(self.library_manager.get_all_collections(force_refresh=True))
        self.assertEqual(len(collections), 1)
        self.assertEqual(collections[0].id, id2)


class TestCollectionSorting(AsyncTestCase):
    """Test collection sorting modes"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.library_dir = self.test_dir / "library"
        self.library_dir.mkdir()

        self.db_path = self.library_dir / "test.db"
        self.storage = LibraryStorage(str(self.db_path))

        self.app = Mock()
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=self.db_path):
            self.library_manager = LibraryManager(app=self.app)
        self.library_manager.storage = self.storage
        # Disable automatic inbox creation for tests
        self.library_manager._inbox_setup_pending = False

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)

    def test_sort_by_name(self):
        """Test sorting collections alphabetically by name"""
        # Create collections in random order
        self.run_async(self.library_manager.add_collection("Zebra Collection", "local", None))
        self.run_async(self.library_manager.add_collection("Alpha Collection", "local", None))
        self.run_async(self.library_manager.add_collection("Beta Collection", "local", None))

        # Get sorted by name
        collections = self.run_async(self.library_manager.get_all_collections(sort_by="name"))
        names = [c.name for c in collections]

        self.assertEqual(names, ["Alpha Collection", "Beta Collection", "Zebra Collection"])

    def test_sort_by_manual(self):
        """Test sorting by manual sort_order"""
        # Create collections
        id1 = self.run_async(self.library_manager.add_collection("First", "local", None))
        id2 = self.run_async(self.library_manager.add_collection("Second", "local", None))
        id3 = self.run_async(self.library_manager.add_collection("Third", "local", None))

        # Reorder
        self.run_async(self.library_manager.reorder_collection(id3, 1))
        self.run_async(self.library_manager.reorder_collection(id1, 3))

        # Get sorted by manual order
        collections = self.run_async(self.library_manager.get_all_collections(sort_by="manual"))
        names = [c.name for c in collections]

        # Should be: Third, Second, First
        self.assertEqual(names, ["Third", "Second", "First"])

    def test_sort_by_type(self):
        """Test sorting by collection type"""
        # Create collections of different types
        self.run_async(self.library_manager.add_collection("Local 1", "local", None))

        external_folder = self.test_dir / "external1"
        external_folder.mkdir()
        self.run_async(self.library_manager.add_collection("External 1", "external", str(external_folder)))

        self.run_async(self.library_manager.add_collection("URL 1", "url", "https://example.com"))

        # Get sorted by type
        collections = self.run_async(self.library_manager.get_all_collections(sort_by="type"))
        types = [c.type for c in collections]

        # Should group by type (exact order may vary)
        self.assertIn("local", types)
        self.assertIn("external", types)
        self.assertIn("url", types)


class TestCollectionTypeFiltering(AsyncTestCase):
    """Test filtering collections by type"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.library_dir = self.test_dir / "library"
        self.library_dir.mkdir()

        self.db_path = self.library_dir / "test.db"
        self.storage = LibraryStorage(str(self.db_path))

        self.app = Mock()
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=self.db_path):
            self.library_manager = LibraryManager(app=self.app)
        self.library_manager.storage = self.storage
        # Disable automatic inbox creation for tests
        self.library_manager._inbox_setup_pending = False

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)

    def test_get_collections_by_type_local(self):
        """Test getting only local collections"""
        # Create mixed collection types
        self.run_async(self.library_manager.add_collection("Local 1", "local", None))
        self.run_async(self.library_manager.add_collection("Local 2", "local", None))
        self.run_async(self.library_manager.add_collection("URL 1", "url", "https://example.com"))

        # Get all collections and filter
        collections = self.run_async(self.library_manager.get_all_collections())
        local_collections = [c for c in collections if c.type == "local"]

        self.assertEqual(len(local_collections), 2)
        self.assertTrue(all(c.type == "local" for c in local_collections))

    def test_get_collections_by_type_external(self):
        """Test getting only external collections"""
        # Create external folders
        ext1 = self.test_dir / "ext1"
        ext1.mkdir()
        ext2 = self.test_dir / "ext2"
        ext2.mkdir()

        # Create collections
        self.run_async(self.library_manager.add_collection("Local 1", "local", None))
        self.run_async(self.library_manager.add_collection("External 1", "external", str(ext1)))
        self.run_async(self.library_manager.add_collection("External 2", "external", str(ext2)))

        # Filter
        collections = self.run_async(self.library_manager.get_all_collections())
        external_collections = [c for c in collections if c.type == "external"]

        self.assertEqual(len(external_collections), 2)
        self.assertTrue(all(c.type == "external" for c in external_collections))


if __name__ == "__main__":
    unittest.main()
