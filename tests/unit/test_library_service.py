"""
Unit Tests for LibraryService

Tests the library service layer that handles all library operations
for the GUI, including collection management and item addition.
"""

import unittest
from unittest.mock import Mock, AsyncMock, patch
import asyncio
from pathlib import Path


class TestLibraryService(unittest.TestCase):
    """Unit tests for LibraryService class"""

    def setUp(self):
        """Set up test fixtures"""
        # Mock library manager
        self.mock_library_manager = Mock()

        # Import and create LibraryService
        from fichero.windows.main.services.library_service import LibraryService
        self.library_service = LibraryService(self.mock_library_manager)

        # Test data
        self.test_collections = [
            {
                'id': 'col1',
                'name': 'Test Collection 1',
                'type': 'local',
                'item_count': 5,
                'description': 'Test description',
                'source_path': '/test/path1'
            },
            {
                'id': 'col2',
                'name': 'Test Collection 2',
                'type': 'url',
                'item_count': 3,
                'description': 'URL collection',
                'source_path': 'https://example.com'
            }
        ]

    def test_library_service_initialization(self):
        """Test LibraryService initializes correctly"""
        self.assertIsNotNone(self.library_service)
        self.assertEqual(self.library_service.library_manager, self.mock_library_manager)

    async def test_get_collections_for_ui_success(self):
        """Test successful collection retrieval"""
        # Mock collections from library manager
        from fichero.library.models import Collection
        mock_collections = [
            Collection(id='col1', name='Test Collection 1', type='local'),
            Collection(id='col2', name='Test Collection 2', type='url')
        ]

        self.mock_library_manager.get_all_collections = AsyncMock(return_value=mock_collections)
        self.mock_library_manager.get_collection_items = AsyncMock(return_value=[])

        # Test the method
        result = await self.library_service.get_collections_for_ui()

        # Verify results
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['id'], 'col1')
        self.assertEqual(result[0]['name'], 'Test Collection 1')
        self.assertEqual(result[1]['id'], 'col2')
        self.assertEqual(result[1]['name'], 'Test Collection 2')

    async def test_get_collections_for_ui_error_handling(self):
        """Test error handling in collection retrieval"""
        # Mock exception
        self.mock_library_manager.get_all_collections = AsyncMock(side_effect=Exception("Database error"))

        # Test the method
        result = await self.library_service.get_collections_for_ui()

        # Should return empty list on error
        self.assertEqual(result, [])

    async def test_add_item_to_collection_for_ui_success(self):
        """Test successful item addition"""
        # Mock successful addition
        expected_item_id = 'item_123'
        self.mock_library_manager.add_item_to_collection = AsyncMock(return_value=expected_item_id)

        # Test URL addition
        result = await self.library_service.add_item_to_collection_for_ui(
            collection_id='col1',
            item_type='url',
            source='https://example.com/image.jpg',
            name='Test Image'
        )

        # Verify results
        self.assertEqual(result, expected_item_id)
        self.mock_library_manager.add_item_to_collection.assert_called_once_with(
            collection_id='col1',
            item_type='url',
            source='https://example.com/image.jpg',
            name='Test Image',
            operation='link'
        )

    async def test_add_item_to_collection_for_ui_error(self):
        """Test error handling in item addition"""
        # Mock exception
        self.mock_library_manager.add_item_to_collection = AsyncMock(side_effect=Exception("Add failed"))

        # Test the method
        result = await self.library_service.add_item_to_collection_for_ui(
            collection_id='col1',
            item_type='url',
            source='https://example.com/image.jpg',
            name='Test Image'
        )

        # Should return None on error
        self.assertIsNone(result)

    def test_get_collections_sync_success(self):
        """Test synchronous collection retrieval"""
        # Mock async method
        with patch.object(self.library_service, 'get_collections_for_ui') as mock_async:
            mock_async.return_value = self.test_collections

            # Test sync wrapper
            result = self.library_service.get_collections_sync()

            # Verify it calls the async version
            self.assertEqual(result, self.test_collections)

    async def test_add_collection_for_ui_success(self):
        """Test successful collection creation"""
        # Mock successful creation
        expected_collection_id = 'new_col_123'
        self.mock_library_manager.add_collection = AsyncMock(return_value=expected_collection_id)

        # Test collection creation
        result = await self.library_service.add_collection_for_ui(
            name='New Collection',
            collection_type='url',
            source_path='https://example.com',
            description='Test collection'
        )

        # Verify results
        self.assertEqual(result, expected_collection_id)
        self.mock_library_manager.add_collection.assert_called_once()

    async def test_delete_collection_for_ui_success(self):
        """Test successful collection deletion"""
        # Mock successful deletion
        self.mock_library_manager.delete_collection = AsyncMock(return_value=True)

        # Test collection deletion
        result = await self.library_service.delete_collection_for_ui('col1')

        # Verify results
        self.assertTrue(result)
        self.mock_library_manager.delete_collection.assert_called_once_with('col1')

    async def test_get_collection_items_for_ui_success(self):
        """Test successful item retrieval"""
        # Mock items
        mock_items = [
            {'id': 'item1', 'name': 'Item 1', 'type': 'url'},
            {'id': 'item2', 'name': 'Item 2', 'type': 'file'}
        ]
        self.mock_library_manager.get_collection_items = AsyncMock(return_value=mock_items)

        # Test item retrieval
        result = await self.library_service.get_collection_items_for_ui('col1')

        # Verify results
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['id'], 'item1')
        self.mock_library_manager.get_collection_items.assert_called_once_with('col1')


class TestLibraryServiceIntegration(unittest.TestCase):
    """Integration tests for LibraryService with real components"""

    def setUp(self):
        """Set up integration test fixtures"""
        # Create temporary directory for testing
        import tempfile
        self.temp_dir = Path(tempfile.mkdtemp())

        # Mock app with proper paths
        self.mock_app = Mock()
        self.mock_app.paths = Mock()
        self.mock_app.paths.data = self.temp_dir

    def tearDown(self):
        """Clean up test files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_full_workflow_url_import(self):
        """Test complete URL import workflow"""
        try:
            # Import real components
            from fichero.library.library_manager import LibraryManager
            from fichero.windows.main.services.library_service import LibraryService
            from fichero.library.models import Collection

            # Create real library manager
            library_manager = LibraryManager(self.temp_dir)
            library_service = LibraryService(library_manager)

            # Test collection creation
            collection = Collection(
                name='EAP Test Collection',
                type='url',
                metadata={'description': 'Test collection for EAP URLs'}
            )

            collection_id = await library_manager.add_collection(collection)
            self.assertIsNotNone(collection_id)

            # Test URL addition
            test_urls = [
                'https://images.eap.bl.uk/EAP1477/EAP1477_1_2_1/1.jp2/full/max/0/default.jpg',
                'https://images.eap.bl.uk/EAP1477/EAP1477_1_2_2/1.jp2/full/max/0/default.jpg'
            ]

            for i, url in enumerate(test_urls, 1):
                item_id = await library_service.add_item_to_collection_for_ui(
                    collection_id=collection_id,
                    item_type='image_url',
                    source=url,
                    name=f'EAP Document {i:02d}'
                )
                self.assertIsNotNone(item_id)

            # Test collection retrieval
            collections = await library_service.get_collections_for_ui()
            self.assertEqual(len(collections), 1)
            self.assertEqual(collections[0]['name'], 'EAP Test Collection')
            self.assertEqual(collections[0]['item_count'], 2)

            # Test item retrieval
            items = await library_service.get_collection_items_for_ui(collection_id)
            self.assertEqual(len(items), 2)

        except ImportError as e:
            self.skipTest(f"Required modules not available: {e}")


def run_async_test(test_func):
    """Helper to run async tests"""
    def wrapper(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(test_func(self))
        finally:
            loop.close()
    return wrapper


# Apply async wrapper to async test methods
for name, method in TestLibraryService.__dict__.items():
    if name.startswith('test_') and asyncio.iscoroutinefunction(method):
        setattr(TestLibraryService, name, run_async_test(method))

for name, method in TestLibraryServiceIntegration.__dict__.items():
    if name.startswith('test_') and asyncio.iscoroutinefunction(method):
        setattr(TestLibraryServiceIntegration, name, run_async_test(method))


if __name__ == '__main__':
    unittest.main()