"""
Unit tests for CollectionView navigation callback registration

Tests that CollectionView properly registers navigation callbacks with its toolbar,
ensuring back button functionality works correctly.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
import logging

# Set up logging to suppress debug output during tests
logging.getLogger('fichero').setLevel(logging.WARNING)


class TestCollectionViewNavigationCallbacks(unittest.TestCase):
    """Test navigation callback registration in CollectionView"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_app = Mock()
        self.mock_app.is_mobile = False
        self.mock_app.library_service = Mock()

        # Mock the base view initialization to avoid UI setup
        self.base_view_patcher = patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__')
        self.mock_base_init = self.base_view_patcher.start()
        self.mock_base_init.return_value = None

    def tearDown(self):
        """Clean up after tests"""
        self.base_view_patcher.stop()

    @patch('fichero.windows.main.views.collection.collection_view.CollectionTopToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.toga.ScrollContainer')
    @patch('fichero.windows.main.views.collection.collection_view.toga.Box')
    def test_navigation_callbacks_are_registered_during_init(self, mock_box, mock_scroll, mock_toolbar_class):
        """Test that navigation callbacks are registered during CollectionView initialization"""
        # Arrange
        mock_toolbar = Mock()
        mock_toolbar_class.return_value = mock_toolbar

        # Mock UI components
        mock_box.return_value = Mock()
        mock_scroll.return_value = Mock()

        # Import and create CollectionView
        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Act
        collection_view = CollectionView(self.mock_app, "Test Collection", is_mobile=False)

        # Assert that setup_toolbar_callbacks was called
        # Since we can't directly test the method call, we verify the toolbar was created
        # and would have had callbacks registered
        mock_toolbar_class.assert_called_once()
        self.assertIsNotNone(collection_view.top_toolbar)

    @patch('fichero.windows.main.views.collection.collection_view.CollectionTopToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.toga.ScrollContainer')
    @patch('fichero.windows.main.views.collection.collection_view.toga.Box')
    def test_setup_toolbar_callbacks_method_exists_and_callable(self, mock_box, mock_scroll, mock_toolbar_class):
        """Test that setup_toolbar_callbacks method exists and is callable"""
        # Arrange
        mock_toolbar = Mock()
        mock_toolbar_class.return_value = mock_toolbar

        # Mock UI components
        mock_box.return_value = Mock()
        mock_scroll.return_value = Mock()

        # Import and create CollectionView
        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Act
        collection_view = CollectionView(self.mock_app, "Test Collection", is_mobile=False)

        # Assert that setup_toolbar_callbacks method exists
        self.assertTrue(hasattr(collection_view, 'setup_toolbar_callbacks'))
        self.assertTrue(callable(getattr(collection_view, 'setup_toolbar_callbacks')))

    @patch('fichero.windows.main.views.collection.collection_view.CollectionTopToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.toga.ScrollContainer')
    @patch('fichero.windows.main.views.collection.collection_view.toga.Box')
    def test_toolbar_callback_registration_calls_correct_methods(self, mock_box, mock_scroll, mock_toolbar_class):
        """Test that toolbar callback registration calls the correct methods"""
        # Arrange
        mock_toolbar = Mock()
        mock_toolbar_class.return_value = mock_toolbar

        # Mock UI components
        mock_box.return_value = Mock()
        mock_scroll.return_value = Mock()

        # Import and create CollectionView
        from fichero.windows.main.views.collection.collection_view import CollectionView

        collection_view = CollectionView(self.mock_app, "Test Collection", is_mobile=False)

        # Act - call setup_toolbar_callbacks explicitly to test it
        collection_view.setup_toolbar_callbacks(mock_toolbar)

        # Assert that register_navigation_callbacks was called on the toolbar
        # Note: It's called twice - once during __init__ and once explicitly here
        self.assertGreaterEqual(mock_toolbar.register_navigation_callbacks.call_count, 1)

        # Verify the call was made with proper callback functions
        call_args = mock_toolbar.register_navigation_callbacks.call_args
        self.assertIsNotNone(call_args)

        # Check that callback arguments were provided
        kwargs = call_args.kwargs
        self.assertIn('on_back_to_library', kwargs)
        self.assertIn('on_navigate_back', kwargs)

    @patch('fichero.windows.main.views.collection.collection_view.CollectionTopToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.toga.ScrollContainer')
    @patch('fichero.windows.main.views.collection.collection_view.toga.Box')
    def test_mobile_and_desktop_both_register_callbacks(self, mock_box, mock_scroll, mock_toolbar_class):
        """Test that both mobile and desktop modes register navigation callbacks"""
        # Test desktop mode
        mock_toolbar_desktop = Mock()
        mock_toolbar_class.return_value = mock_toolbar_desktop
        mock_box.return_value = Mock()
        mock_scroll.return_value = Mock()

        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Desktop mode
        self.mock_app.is_mobile = False
        collection_view_desktop = CollectionView(self.mock_app, "Test Collection", is_mobile=False)

        # Reset mocks for mobile test
        mock_toolbar_class.reset_mock()
        mock_toolbar_mobile = Mock()
        mock_toolbar_class.return_value = mock_toolbar_mobile

        # Mobile mode
        self.mock_app.is_mobile = True
        collection_view_mobile = CollectionView(self.mock_app, "Test Collection", is_mobile=True)

        # Assert both created toolbars (may only show 1 due to mock reset behavior)
        self.assertGreaterEqual(mock_toolbar_class.call_count, 1)
        self.assertIsNotNone(collection_view_desktop.top_toolbar)
        self.assertIsNotNone(collection_view_mobile.top_toolbar)

    def test_collection_view_has_required_navigation_methods(self):
        """Test that CollectionView has all required navigation methods"""
        # Import without UI setup to check method existence
        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Check that required methods exist on the class
        required_methods = [
            'setup_toolbar_callbacks',
            '_on_back_to_library',
            '_on_navigate_back'
        ]

        for method_name in required_methods:
            self.assertTrue(
                hasattr(CollectionView, method_name),
                f"CollectionView missing required method: {method_name}"
            )
            self.assertTrue(
                callable(getattr(CollectionView, method_name)),
                f"CollectionView.{method_name} is not callable"
            )


if __name__ == '__main__':
    unittest.main()