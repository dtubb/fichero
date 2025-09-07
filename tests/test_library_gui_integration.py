"""
Unit tests for Library GUI Integration

Tests the integration between LibraryManager and GUI components.
"""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

# Add the src directory to the path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fichero.library.library_manager import LibraryManager
from fichero.library.models import Collection, CollectionItem


class TestLibraryGUIIntegration(unittest.TestCase):
    """Test library GUI integration"""
    
    def setUp(self):
        """Set up test environment"""
        # Create a mock app
        self.mock_app = Mock()
        self.mock_app.paths = Mock()
        
        # Create a temporary directory for the library
        self.temp_dir = tempfile.mkdtemp()
        self.mock_app.paths.data = Path(self.temp_dir)
        
        # Create library manager
        self.library_manager = LibraryManager(self.mock_app)
    
    def tearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    async def test_add_and_get_collections(self):
        """Test adding and getting collections"""
        # Add a test collection
        collection_id = await self.library_manager.add_collection(
            name="Test Collection",
            collection_type="local",
            description="A test collection"
        )
        
        self.assertIsNotNone(collection_id)
        
        # Get all collections
        collections = await self.library_manager.get_all_collections()
        self.assertEqual(len(collections), 1)
        self.assertEqual(collections[0].name, "Test Collection")
        self.assertEqual(collections[0].type, "local")
    
    async def test_add_and_get_collection_items(self):
        """Test adding and getting collection items"""
        # Add a test collection
        collection_id = await self.library_manager.add_collection(
            name="Test Collection",
            collection_type="local"
        )
        
        # Add items to the collection
        item1_id = await self.library_manager.add_item_to_collection(
            collection_id=collection_id,
            item_type="file",
            source="/path/to/file1.txt",
            name="File 1"
        )
        
        item2_id = await self.library_manager.add_item_to_collection(
            collection_id=collection_id,
            item_type="folder",
            source="/path/to/folder1",
            name="Folder 1"
        )
        
        self.assertIsNotNone(item1_id)
        self.assertIsNotNone(item2_id)
        
        # Get collection items
        items = await self.library_manager.get_collection_items(collection_id)
        self.assertEqual(len(items), 2)
        
        # Check item details
        item_names = [item.name for item in items]
        self.assertIn("File 1", item_names)
        self.assertIn("Folder 1", item_names)
    
    async def test_collection_crud_operations(self):
        """Test collection CRUD operations"""
        # Create
        collection_id = await self.library_manager.add_collection(
            name="Original Name",
            collection_type="local",
            description="Original description"
        )
        
        # Read
        collection = await self.library_manager.get_collection(collection_id)
        self.assertEqual(collection.name, "Original Name")
        self.assertEqual(collection.metadata.get('description'), "Original description")
        
        # Update
        success = await self.library_manager.update_collection(
            collection_id,
            name="Updated Name",
            metadata={'description': 'Updated description'}
        )
        self.assertTrue(success)
        
        # Verify update
        updated_collection = await self.library_manager.get_collection(collection_id)
        self.assertEqual(updated_collection.name, "Updated Name")
        self.assertEqual(updated_collection.metadata.get('description'), "Updated description")
        
        # Delete
        success = await self.library_manager.delete_collection(collection_id)
        self.assertTrue(success)
        
        # Verify deletion
        collections = await self.library_manager.get_all_collections()
        self.assertEqual(len(collections), 0)
    
    def test_collection_to_gui_data_conversion(self):
        """Test conversion of collection data to GUI format"""
        from fichero.windows.main.services.library_gui_integration import LibraryGUIIntegration
        
        # Create integration instance
        integration = LibraryGUIIntegration(self.mock_app)
        
        # Create a test collection
        collection = Collection(
            id="test-id",
            name="Test Collection",
            type="local",
            source_path="/test/path",
            local_path="/test/local/path",
            metadata={'description': 'Test description'}
        )
        
        # Convert to GUI data
        gui_data = integration._collection_to_gui_data(collection)
        
        # Verify conversion
        self.assertEqual(gui_data['id'], "test-id")
        self.assertEqual(gui_data['name'], "Test Collection")
        self.assertEqual(gui_data['type'], "local")
        self.assertEqual(gui_data['source_path'], "/test/path")
        self.assertEqual(gui_data['local_path'], "/test/local/path")
        self.assertEqual(gui_data['description'], "Test description")
        self.assertIn('status', gui_data)
        self.assertIn('created_at', gui_data)
        self.assertIn('updated_at', gui_data)


def run_async_test(test_func):
    """Helper to run async tests"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_func())
    finally:
        loop.close()


if __name__ == '__main__':
    # Run async tests
    test_instance = TestLibraryGUIIntegration()
    test_instance.setUp()
    
    try:
        run_async_test(test_instance.test_add_and_get_collections)
        print("✓ test_add_and_get_collections passed")
        
        run_async_test(test_instance.test_add_and_get_collection_items)
        print("✓ test_add_and_get_collection_items passed")
        
        run_async_test(test_instance.test_collection_crud_operations)
        print("✓ test_collection_crud_operations passed")
        
        test_instance.test_collection_to_gui_data_conversion()
        print("✓ test_collection_to_gui_data_conversion passed")
        
        print("\n🎉 All tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        test_instance.tearDown()
