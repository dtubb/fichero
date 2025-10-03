"""
Unit tests for LibraryViewModel

Tests library data management without GUI dependencies.
"""

import unittest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from fichero.viewmodels.library_viewmodel import LibraryViewModel
from fichero.shared.navigation.navigation_controller import NavigationController


class MockObserver:
    """Mock observer for testing"""

    def __init__(self):
        self.data_changes = []
        self.loading_changes = []
        self.errors = []

    def on_data_changed(self, data_type: str, data):
        self.data_changes.append((data_type, data))

    def on_loading_changed(self, is_loading: bool):
        self.loading_changes.append(is_loading)

    def on_error_occurred(self, error_type: str, message: str):
        self.errors.append((error_type, message))


class TestLibraryViewModel(unittest.TestCase):
    """Test LibraryViewModel functionality"""

    def setUp(self):
        """Set up test environment"""
        # Create mock library service
        self.mock_library_service = Mock()
        self.mock_library_service.get_collections_sync.return_value = []

        # Create mock navigation controller
        self.mock_navigation_controller = Mock(spec=NavigationController)

        # Create library ViewModel
        self.library_viewmodel = LibraryViewModel(
            library_service=self.mock_library_service,
            navigation_controller=self.mock_navigation_controller
        )

        # Create mock observer
        self.observer = MockObserver()
        self.library_viewmodel.add_observer(self.observer)

    def test_initial_state(self):
        """Test initial ViewModel state"""
        self.assertEqual(len(self.library_viewmodel.collections), 0)
        self.assertIsNone(self.library_viewmodel.selected_collection)
        self.assertFalse(self.library_viewmodel.edit_mode)
        self.assertIsNone(self.library_viewmodel.last_refresh)

    def test_load_collections(self):
        """Test loading collections"""
        # Mock collections data
        mock_collections = [
            {'id': 'col1', 'title': 'Collection 1', 'item_count': 5},
            {'id': 'col2', 'title': 'Collection 2', 'item_count': 3}
        ]
        self.mock_library_service.get_collections_sync.return_value = mock_collections

        # Load collections
        self.library_viewmodel.load_collections()

        # Check data was loaded
        self.assertEqual(len(self.library_viewmodel.collections), 2)
        self.assertEqual(self.library_viewmodel.collections[0]['id'], 'col1')
        self.assertIsNotNone(self.library_viewmodel.last_refresh)

        # Check observer was notified
        self.assertIn(('collections', mock_collections), self.observer.data_changes)
        self.assertIn(True, self.observer.loading_changes)  # Loading started
        self.assertIn(False, self.observer.loading_changes)  # Loading finished

    def test_select_collection(self):
        """Test collection selection"""
        # Set up collections
        mock_collections = [
            {'id': 'col1', 'title': 'Collection 1', 'item_count': 5}
        ]
        self.library_viewmodel.collections = mock_collections

        # Select collection
        success = self.library_viewmodel.select_collection('col1')
        self.assertTrue(success)

        # Check selection
        self.assertIsNotNone(self.library_viewmodel.selected_collection)
        self.assertEqual(self.library_viewmodel.selected_collection['id'], 'col1')

        # Check observer was notified
        selection_changes = [change for change in self.observer.data_changes if change[0] == 'selection']
        self.assertTrue(len(selection_changes) > 0)

    def test_select_nonexistent_collection(self):
        """Test selecting a collection that doesn't exist"""
        success = self.library_viewmodel.select_collection('nonexistent')
        self.assertFalse(success)

        # Check error was recorded
        self.assertTrue(len(self.observer.errors) > 0)

    def test_navigate_to_collection(self):
        """Test navigation to collection"""
        # Set up collections
        mock_collections = [
            {'id': 'col1', 'title': 'Collection 1', 'item_count': 5}
        ]
        self.library_viewmodel.collections = mock_collections

        # Mock navigation controller success
        self.mock_navigation_controller.execute_command.return_value = True

        # Navigate to collection
        success = self.library_viewmodel.navigate_to_collection('col1')
        self.assertTrue(success)

        # Check navigation controller was called
        self.mock_navigation_controller.execute_command.assert_called_once()

        # Check collection was selected
        self.assertIsNotNone(self.library_viewmodel.selected_collection)
        self.assertEqual(self.library_viewmodel.selected_collection['id'], 'col1')

    def test_toggle_edit_mode(self):
        """Test edit mode toggling"""
        # Initially not in edit mode
        self.assertFalse(self.library_viewmodel.edit_mode)

        # Toggle to edit mode
        result = self.library_viewmodel.toggle_edit_mode()
        self.assertTrue(result)
        self.assertTrue(self.library_viewmodel.edit_mode)

        # Check observer was notified
        edit_mode_changes = [change for change in self.observer.data_changes if change[0] == 'edit_mode']
        self.assertIn(('edit_mode', True), edit_mode_changes)

        # Toggle back
        result = self.library_viewmodel.toggle_edit_mode()
        self.assertFalse(result)
        self.assertFalse(self.library_viewmodel.edit_mode)

    def test_set_edit_mode(self):
        """Test setting edit mode directly"""
        # Set to edit mode
        self.library_viewmodel.set_edit_mode(True)
        self.assertTrue(self.library_viewmodel.edit_mode)

        # Set to normal mode
        self.library_viewmodel.set_edit_mode(False)
        self.assertFalse(self.library_viewmodel.edit_mode)

        # Setting same value shouldn't trigger notification
        initial_changes = len(self.observer.data_changes)
        self.library_viewmodel.set_edit_mode(False)
        self.assertEqual(len(self.observer.data_changes), initial_changes)

    def test_data_access_methods(self):
        """Test data access methods"""
        # Set up test data
        mock_collections = [
            {'id': 'col1', 'title': 'Collection 1', 'item_count': 5},
            {'id': 'col2', 'title': 'Collection 2', 'item_count': 3}
        ]
        self.library_viewmodel.collections = mock_collections
        self.library_viewmodel.selected_collection = mock_collections[0]

        # Test get_collections
        collections = self.library_viewmodel.get_collections()
        self.assertEqual(len(collections), 2)
        self.assertIsNot(collections, self.library_viewmodel.collections)  # Should be a copy

        # Test get_selected_collection
        selected = self.library_viewmodel.get_selected_collection()
        self.assertEqual(selected['id'], 'col1')
        self.assertIsNot(selected, self.library_viewmodel.selected_collection)  # Should be a copy

        # Test get_collection_by_id
        collection = self.library_viewmodel.get_collection_by_id('col2')
        self.assertIsNotNone(collection)
        self.assertEqual(collection['id'], 'col2')

        # Test get_collection_count
        count = self.library_viewmodel.get_collection_count()
        self.assertEqual(count, 2)

    def test_refresh(self):
        """Test refresh functionality"""
        # Mock collections data
        mock_collections = [{'id': 'col1', 'title': 'Collection 1'}]
        self.mock_library_service.get_collections_sync.return_value = mock_collections

        # Call refresh
        self.library_viewmodel.refresh()

        # Check service was called
        self.mock_library_service.get_collections_sync.assert_called()

        # Check data was updated
        self.assertEqual(len(self.library_viewmodel.collections), 1)

    def test_cache_validation(self):
        """Test cache validation"""
        # Load collections
        self.library_viewmodel.collections = [{'id': 'col1'}]
        self.library_viewmodel.last_refresh = datetime.now()

        # Call load_collections without force_refresh
        self.library_viewmodel.load_collections(force_refresh=False)

        # Service should not be called again (using cache)
        self.mock_library_service.get_collections_sync.assert_not_called()

        # Call with force_refresh
        self.library_viewmodel.load_collections(force_refresh=True)

        # Service should be called
        self.mock_library_service.get_collections_sync.assert_called()

    def test_state_dict(self):
        """Test state dictionary generation"""
        # Set up some state
        self.library_viewmodel.collections = [{'id': 'col1'}]
        self.library_viewmodel.edit_mode = True
        self.library_viewmodel.last_refresh = datetime.now()

        # Get state dict
        state = self.library_viewmodel.get_state_dict()

        # Check required fields
        self.assertIn('class', state)
        self.assertIn('collection_count', state)
        self.assertIn('edit_mode', state)
        self.assertIn('last_refresh', state)
        self.assertIn('auto_refresh_enabled', state)

        # Check values
        self.assertEqual(state['collection_count'], 1)
        self.assertEqual(state['edit_mode'], True)

    def test_error_handling(self):
        """Test error handling"""
        # Mock service to raise exception
        self.mock_library_service.get_collections_sync.side_effect = Exception("Test error")

        # Load collections
        self.library_viewmodel.load_collections()

        # Check error was handled
        self.assertTrue(len(self.observer.errors) > 0)
        error_type, error_message = self.observer.errors[0]
        self.assertEqual(error_type, 'load_error')
        self.assertIn("Test error", error_message)

        # Check loading state was reset
        self.assertIn(False, self.observer.loading_changes)


if __name__ == '__main__':
    unittest.main()