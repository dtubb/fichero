"""
Unit tests for LibraryViewRefactored

Tests the refactored library view functionality and ViewModel integration.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import toga

from fichero.windows.main.views.library.library_view_refactored import LibraryViewRefactored


class MockObserver:
    """Mock ViewModel observer for testing"""

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


class TestLibraryViewRefactored(unittest.TestCase):
    """Test LibraryViewRefactored functionality"""

    def setUp(self):
        """Set up test environment"""
        # Create mock app
        self.mock_app = Mock()
        self.mock_app.is_mobile = False

        # Create mock library viewmodel
        self.mock_library_viewmodel = Mock()
        self.mock_library_viewmodel.collections = []
        self.mock_library_viewmodel.selected_collection = None
        self.mock_library_viewmodel.edit_mode = False

        # Mock toolbar classes
        self.mock_top_toolbar = Mock()
        self.mock_bottom_toolbar = Mock()

    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryTopToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryBottomToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.threading.Thread')
    def test_library_view_initialization(self, mock_thread, mock_bottom_toolbar, mock_top_toolbar):
        """Test library view initializes correctly"""
        # Mock toolbars
        mock_top_toolbar.return_value = self.mock_top_toolbar
        mock_bottom_toolbar.return_value = self.mock_bottom_toolbar

        # Mock thread
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance

        # Create library view
        with patch.object(LibraryViewRefactored, '_create_content'):
            library_view = LibraryViewRefactored(
                self.mock_app,
                self.mock_library_viewmodel,
                is_mobile=False
            )

        # Check initialization
        self.assertIsNotNone(library_view)
        self.assertEqual(library_view.app, self.mock_app)
        self.assertEqual(library_view.viewmodel, self.mock_library_viewmodel)
        self.assertFalse(library_view.is_edit_mode)

        # Check toolbars were created
        mock_top_toolbar.assert_called_once_with(self.mock_app, False)
        mock_bottom_toolbar.assert_called_once_with(self.mock_app, False)

        # Check observer was added to viewmodel
        self.mock_library_viewmodel.add_observer.assert_called_once_with(library_view)

        # Check background loading was scheduled
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()

    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryTopToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryBottomToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.threading.Thread')
    def test_library_view_mobile_mode(self, mock_thread, mock_bottom_toolbar, mock_top_toolbar):
        """Test library view handles mobile mode correctly"""
        # Mock toolbars
        mock_top_toolbar.return_value = self.mock_top_toolbar
        mock_bottom_toolbar.return_value = self.mock_bottom_toolbar

        # Mock thread
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance

        # Create library view in mobile mode
        with patch.object(LibraryViewRefactored, '_create_content'):
            library_view = LibraryViewRefactored(
                self.mock_app,
                self.mock_library_viewmodel,
                is_mobile=True
            )

        # Check toolbars were created with mobile=True
        mock_top_toolbar.assert_called_once_with(self.mock_app, True)
        mock_bottom_toolbar.assert_called_once_with(self.mock_app, True)

    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryTopToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryBottomToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.threading.Thread')
    def test_viewmodel_observer_methods(self, mock_thread, mock_bottom_toolbar, mock_top_toolbar):
        """Test ViewModel observer methods"""
        # Mock toolbars
        mock_top_toolbar.return_value = self.mock_top_toolbar
        mock_bottom_toolbar.return_value = self.mock_bottom_toolbar

        # Create library view
        with patch.object(LibraryViewRefactored, '_create_content'):
            library_view = LibraryViewRefactored(
                self.mock_app,
                self.mock_library_viewmodel,
                is_mobile=False
            )

        # Mock the refresh method
        library_view._refresh_collections_display = Mock()

        # Test on_data_changed with collections
        test_collections = [{'id': '1', 'name': 'Test Collection'}]
        library_view.on_data_changed('collections', test_collections)

        self.assertEqual(library_view.collections, test_collections)
        library_view._refresh_collections_display.assert_called_once()

        # Test on_data_changed with selection
        test_selection = {'id': '1', 'name': 'Test Collection'}
        library_view.on_data_changed('selection', test_selection)

        self.assertEqual(library_view.selected_collection, test_selection)

        # Test on_data_changed with edit_mode
        library_view._update_toolbars_for_edit_mode = Mock()
        library_view.on_data_changed('edit_mode', True)

        self.assertTrue(library_view.is_edit_mode)
        library_view._update_toolbars_for_edit_mode.assert_called_once()

        # Test on_loading_changed
        library_view.on_loading_changed(True)
        library_view.on_loading_changed(False)
        # Should not raise any errors

        # Test on_error_occurred
        library_view._show_message = Mock()
        library_view.on_error_occurred('test_error', 'Test error message')
        library_view._show_message.assert_called_once_with('Error', 'Test error message')

    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryTopToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryBottomToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.threading.Thread')
    def test_toggle_edit_mode(self, mock_thread, mock_bottom_toolbar, mock_top_toolbar):
        """Test toggle edit mode delegates to ViewModel"""
        # Mock toolbars
        mock_top_toolbar.return_value = self.mock_top_toolbar
        mock_bottom_toolbar.return_value = self.mock_bottom_toolbar

        # Create library view
        with patch.object(LibraryViewRefactored, '_create_content'):
            library_view = LibraryViewRefactored(
                self.mock_app,
                self.mock_library_viewmodel,
                is_mobile=False
            )

        # Test toggle_edit_mode
        library_view.toggle_edit_mode()

        # Check viewmodel method was called
        self.mock_library_viewmodel.toggle_edit_mode.assert_called_once()

    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryTopToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryBottomToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.threading.Thread')
    def test_collection_selection_handling(self, mock_thread, mock_bottom_toolbar, mock_top_toolbar):
        """Test collection selection handling"""
        # Mock toolbars
        mock_top_toolbar.return_value = self.mock_top_toolbar
        mock_bottom_toolbar.return_value = self.mock_bottom_toolbar

        # Create library view
        with patch.object(LibraryViewRefactored, '_create_content'):
            library_view = LibraryViewRefactored(
                self.mock_app,
                self.mock_library_viewmodel,
                is_mobile=False
            )

        # Test register_collection_callback
        callback = Mock()
        library_view.register_collection_callback(callback)
        self.assertEqual(library_view.on_collection_selected, callback)

        # Test _on_open_collection
        mock_row = Mock()
        mock_row.collection_data = {'id': 'col1', 'name': 'Test Collection'}
        self.mock_library_viewmodel.navigate_to_collection.return_value = True

        library_view._on_open_collection(None, mock_row)

        # Check viewmodel navigation was called
        self.mock_library_viewmodel.navigate_to_collection.assert_called_once_with('col1')

        # Check callback was called
        callback.assert_called_once_with('col1', 'Test Collection')

        # Test _on_collection_selected
        mock_widget = Mock()
        mock_widget.selection = mock_row

        library_view._on_collection_selected(mock_widget)

        # Check viewmodel selection was called
        self.mock_library_viewmodel.select_collection.assert_called_with('col1')

    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryTopToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryBottomToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.threading.Thread')
    def test_backward_compatibility_methods(self, mock_thread, mock_bottom_toolbar, mock_top_toolbar):
        """Test backward compatibility methods"""
        # Mock toolbars
        mock_top_toolbar.return_value = self.mock_top_toolbar
        mock_bottom_toolbar.return_value = self.mock_bottom_toolbar

        # Create library view
        with patch.object(LibraryViewRefactored, '_create_content'):
            library_view = LibraryViewRefactored(
                self.mock_app,
                self.mock_library_viewmodel,
                is_mobile=False
            )

        # Set up test data
        test_collections = [{'id': '1', 'name': 'Test Collection'}]
        test_selection = {'id': '1', 'name': 'Test Collection'}
        library_view.collections = test_collections
        library_view.selected_collection = test_selection
        library_view.is_edit_mode = True

        # Test get_collections
        collections = library_view.get_collections()
        self.assertEqual(collections, test_collections)
        self.assertIsNot(collections, library_view.collections)  # Should be a copy

        # Test get_selected_collection
        selected = library_view.get_selected_collection()
        self.assertEqual(selected, test_selection)
        self.assertIsNot(selected, library_view.selected_collection)  # Should be a copy

        # Test is_edit_mode_active
        self.assertTrue(library_view.is_edit_mode_active())

        # Test add_collection
        collection_data = {'name': 'New Collection', 'type': 'local'}
        self.mock_library_viewmodel.add_collection.return_value = True

        library_view.add_collection(collection_data)

        self.mock_library_viewmodel.add_collection.assert_called_once_with(
            'New Collection', 'local', None, ''
        )

        # Test remove_collection
        self.mock_library_viewmodel.delete_collection.return_value = True

        library_view.remove_collection('col1')

        self.mock_library_viewmodel.delete_collection.assert_called_once_with('col1')

        # Test refresh
        library_view.refresh()

        self.mock_library_viewmodel.refresh.assert_called_once()

    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryTopToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.LibraryBottomToolbar')
    @patch('fichero.windows.main.views.library.library_view_refactored.threading.Thread')
    def test_show_method_clears_selections(self, mock_thread, mock_bottom_toolbar, mock_top_toolbar):
        """Test show method clears cached selections"""
        # Mock toolbars
        mock_top_toolbar.return_value = self.mock_top_toolbar
        mock_bottom_toolbar.return_value = self.mock_bottom_toolbar

        # Create library view
        with patch.object(LibraryViewRefactored, '_create_content'):
            library_view = LibraryViewRefactored(
                self.mock_app,
                self.mock_library_viewmodel,
                is_mobile=False
            )

        # Mock the collections display creation
        library_view._create_collections_display = Mock()

        # Call show
        library_view.show()

        # Check collections display was recreated
        library_view._create_collections_display.assert_called_once()


if __name__ == '__main__':
    unittest.main()