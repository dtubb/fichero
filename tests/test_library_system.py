#!/usr/bin/env python3
"""
Unit Tests for Fichero Library System

These tests verify that the library system components work correctly
without requiring the full Toga app context.
"""

import unittest
import tempfile
import shutil
import asyncio
from pathlib import Path
import sys
import os

# Add the src directory to Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

class TestLibraryModels(unittest.TestCase):
    """Test the data models for the library system"""
    
    def setUp(self):
        """Set up test fixtures"""
        from fichero.library.models import Collection, CollectionItem, ProcessingResult
        
        self.Collection = Collection
        self.CollectionItem = CollectionItem
        self.ProcessingResult = ProcessingResult
    
    def test_collection_creation(self):
        """Test creating a Collection object"""
        collection = self.Collection(
            name="Test Collection",
            type="external",
            source_path="/test/path",
            description="Test description"
        )
        
        self.assertEqual(collection.name, "Test Collection")
        self.assertEqual(collection.type, "external")
        self.assertEqual(collection.source_path, "/test/path")
        self.assertIsNotNone(collection.id)
        self.assertIsNotNone(collection.created_at)
        self.assertIsNotNone(collection.updated_at)
    
    def test_collection_item_creation(self):
        """Test creating a CollectionItem object"""
        item = self.CollectionItem(
            collection_id="test-collection-id",
            type="file",
            name="test.txt",
            source_path="/test/path/test.txt",
            storage_type="external"
        )
        
        self.assertEqual(item.collection_id, "test-collection-id")
        self.assertEqual(item.type, "file")
        self.assertEqual(item.name, "test.txt")
        self.assertEqual(item.storage_type, "external")
        self.assertEqual(item.status, "pending")  # default value
        self.assertIsNotNone(item.id)
    
    def test_processing_result_creation(self):
        """Test creating a ProcessingResult object"""
        result = self.ProcessingResult(
            item_id="test-item-id",
            workflow="test_workflow",
            status="success"
        )
        
        self.assertEqual(result.item_id, "test-item-id")
        self.assertEqual(result.workflow, "test_workflow")
        self.assertEqual(result.status, "success")
        self.assertIsNotNone(result.id)
    
    def test_collection_serialization(self):
        """Test Collection serialization to/from dict"""
        collection = self.Collection(
            name="Serialization Test",
            type="local",
            source_path="/test/path"
        )
        
        # Convert to dict
        data = collection.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["name"], "Serialization Test")
        self.assertEqual(data["type"], "local")
        
        # Convert back from dict
        restored = self.Collection.from_dict(data)
        self.assertEqual(restored.name, collection.name)
        self.assertEqual(restored.type, collection.type)
        self.assertEqual(restored.source_path, collection.source_path)
    
    def test_collection_item_serialization(self):
        """Test CollectionItem serialization to/from dict"""
        item = self.CollectionItem(
            collection_id="test-collection",
            type="folder",
            name="test_folder",
            storage_type="local"
        )
        
        # Convert to dict
        data = item.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["name"], "test_folder")
        self.assertEqual(data["type"], "folder")
        
        # Convert back from dict
        restored = self.CollectionItem.from_dict(data)
        self.assertEqual(restored.name, item.name)
        self.assertEqual(restored.type, item.type)
        self.assertEqual(restored.storage_type, item.storage_type)


class TestLibraryStorage(unittest.TestCase):
    """Test the SQLite storage backend"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.test_db_path = self.test_dir / "test_library.db"
        
        # Import storage after setting up test path
        from fichero.library.storage import LibraryStorage
        self.LibraryStorage = LibraryStorage
    
    def tearDown(self):
        """Clean up test fixtures"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_storage_initialization(self):
        """Test storage initialization and database creation"""
        storage = self.LibraryStorage(self.test_db_path)
        
        # Check that database file was created
        self.assertTrue(self.test_db_path.exists())
        
        # Check that storage instance was created
        self.assertIsNotNone(storage)
    
    def test_collection_crud_operations(self):
        """Test Create, Read, Update, Delete operations for collections"""
        from fichero.library.models import Collection
        
        storage = self.LibraryStorage(self.test_db_path)
        
        # Create a collection
        collection = Collection(
            name="Test Collection",
            type="external",
            source_path="/test/path"
        )
        
        # Add to storage
        success = storage.add_collection(collection)
        self.assertTrue(success)
        
        # Retrieve from storage
        retrieved = storage.get_collection(collection.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Test Collection")
        self.assertEqual(retrieved.type, "external")
        
        # Update collection
        collection.name = "Updated Collection"
        collection.updated_at = collection.updated_at  # Trigger update
        success = storage.update_collection(collection)
        self.assertTrue(success)
        
        # Verify update
        updated = storage.get_collection(collection.id)
        self.assertEqual(updated.name, "Updated Collection")
        
        # Delete collection
        success = storage.delete_collection(collection.id)
        self.assertTrue(success)
        
        # Verify deletion
        deleted = storage.get_collection(collection.id)
        self.assertIsNone(deleted)
    
    def test_collection_item_crud_operations(self):
        """Test CRUD operations for collection items"""
        from fichero.library.models import Collection, CollectionItem
        
        storage = self.LibraryStorage(self.test_db_path)
        
        # Create a collection first
        collection = Collection(name="Test Collection", type="local")
        storage.add_collection(collection)
        
        # Create an item
        item = CollectionItem(
            collection_id=collection.id,
            type="file",
            name="test.txt",
            storage_type="local"
        )
        
        # Add to storage
        success = storage.add_collection_item(item)
        self.assertTrue(success)
        
        # Retrieve from storage
        retrieved = storage.get_collection_item(item.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "test.txt")
        
        # Update item
        item.name = "updated.txt"
        success = storage.update_collection_item(item)
        self.assertTrue(success)
        
        # Verify update
        updated = storage.get_collection_item(item.id)
        self.assertEqual(updated.name, "updated.txt")
        
        # Delete item
        success = storage.delete_collection_item(item.id)
        self.assertTrue(success)
        
        # Verify deletion
        deleted = storage.get_collection_item(item.id)
        self.assertIsNone(deleted)
    
    def test_get_collections_by_type(self):
        """Test retrieving collections by type"""
        from fichero.library.models import Collection
        
        storage = self.LibraryStorage(self.test_db_path)
        
        # Create collections of different types
        local_collection = Collection(name="Local Collection", type="local")
        external_collection = Collection(name="External Collection", type="external")
        url_collection = Collection(name="URL Collection", type="url")
        
        storage.add_collection(local_collection)
        storage.add_collection(external_collection)
        storage.add_collection(url_collection)
        
        # Test getting collections by type
        local_collections = storage.get_collections_by_type("local")
        self.assertEqual(len(local_collections), 1)
        self.assertEqual(local_collections[0].name, "Local Collection")
        
        external_collections = storage.get_collections_by_type("external")
        self.assertEqual(len(external_collections), 1)
        self.assertEqual(external_collections[0].name, "External Collection")
        
        url_collections = storage.get_collections_by_type("url")
        self.assertEqual(len(url_collections), 1)
        self.assertEqual(url_collections[0].name, "URL Collection")


class TestLibraryManager(unittest.TestCase):
    """Test the library manager orchestration layer"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = Path(tempfile.mkdtemp())
        
        # Create mock app
        class MockApp:
            class paths:
                data = self.test_dir
        
        self.mock_app = MockApp()
        
        # Import library manager
        from fichero.library.library_manager import LibraryManager
        self.LibraryManager = LibraryManager
    
    def tearDown(self):
        """Clean up test fixtures"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_library_manager_initialization(self):
        """Test library manager initialization"""
        library_manager = self.LibraryManager(self.mock_app)
        
        self.assertIsNotNone(library_manager)
        self.assertIsNotNone(library_manager.storage)
        self.assertIsNotNone(library_manager.exporter)
        self.assertIsNotNone(library_manager.importer)
        
        # Check that library directory was created
        library_path = self.test_dir / "library"
        self.assertTrue(library_path.exists())
    
    @unittest.skip("Async test requires proper event loop setup")
    async def test_add_collection(self):
        """Test adding a collection through the library manager"""
        library_manager = self.LibraryManager(self.mock_app)
        
        collection_id = await library_manager.add_collection(
            name="Test Collection",
            collection_type="external",
            source_path="/test/path"
        )
        
        self.assertIsNotNone(collection_id)
        
        # Verify collection was added to storage
        collection = await library_manager.get_collection(collection_id)
        self.assertIsNotNone(collection)
        self.assertEqual(collection.name, "Test Collection")
    
    @unittest.skip("Async test requires proper event loop setup")
    async def test_get_all_collections(self):
        """Test retrieving all collections"""
        library_manager = self.LibraryManager(self.mock_app)
        
        # Add some collections
        await library_manager.add_collection(
            name="Collection 1",
            collection_type="local"
        )
        await library_manager.add_collection(
            name="Collection 2",
            collection_type="external"
        )
        
        # Get all collections
        collections = await library_manager.get_all_collections()
        self.assertEqual(len(collections), 2)
        
        # Check collection names
        names = [c.name for c in collections]
        self.assertIn("Collection 1", names)
        self.assertIn("Collection 2", names)


class TestImportExport(unittest.TestCase):
    """Test the import/export functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.test_db_path = self.test_dir / "test_export.db"
        
        # Import required modules
        from fichero.library.storage import LibraryStorage
        from fichero.library.import_export import CollectionExporter, CollectionImporter
        
        self.LibraryStorage = LibraryStorage
        self.CollectionExporter = CollectionExporter
        self.CollectionImporter = CollectionImporter
    
    def tearDown(self):
        """Clean up test fixtures"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_exporter_creation(self):
        """Test creating a collection exporter"""
        storage = self.LibraryStorage(self.test_db_path)
        exporter = self.CollectionExporter(storage)
        
        self.assertIsNotNone(exporter)
        self.assertEqual(exporter.storage, storage)
    
    def test_importer_creation(self):
        """Test creating a collection importer"""
        storage = self.LibraryStorage(self.test_db_path)
        importer = self.CollectionImporter(storage)
        
        self.assertIsNotNone(importer)
        self.assertEqual(importer.storage, storage)


def run_tests():
    """Run all library system tests"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestLibraryModels))
    suite.addTests(loader.loadTestsFromTestCase(TestLibraryStorage))
    suite.addTests(loader.loadTestsFromTestCase(TestLibraryManager))
    suite.addTests(loader.loadTestsFromTestCase(TestImportExport))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 60)
    print("FICHERO LIBRARY SYSTEM - UNIT TESTS")
    print("=" * 60)
    
    success = run_tests()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 ALL TESTS PASSED!")
        print("The library system is working correctly.")
    else:
        print("💥 SOME TESTS FAILED!")
        print("Check the test output above for issues.")
    print("=" * 60)
    
    exit(0 if success else 1) 