"""
Unit tests for CollectionView NavigationController integration

Tests the updated collection view back-to-library navigation using NavigationController
without legacy fallbacks.
"""

import unittest
from unittest.mock import MagicMock, patch
import logging

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestCollectionView(unittest.TestCase):
    """Test suite for CollectionView NavigationController integration"""

    def setUp(self):
        """Set up test environment"""
        self.app = MagicMock()
        self.app.is_mobile = False
        self.app.library_service = MagicMock()

    def test_back_to_library_uses_navigation_helper(self):
        """Test that back-to-library navigation uses NavigationHelper"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = True

            from fichero.windows.main.views.collection.collection_view import CollectionView

            # Create collection view
            collection_view = CollectionView(self.app, collection_name="Test Collection")

            # Test back to library navigation
            collection_view._on_back_to_library()

            # Verify NavigationHelper was called with correct parameters
            mock_navigate.assert_called_once()
            call_args = mock_navigate.call_args
            self.assertEqual(call_args[1]['app'], self.app)
            self.assertEqual(call_args[1]['context'], 'collection_back_to_library')

    def test_back_to_library_navigation_success(self):
        """Test successful back-to-library navigation"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = True

            from fichero.windows.main.views.collection.collection_view import CollectionView

            # Create collection view
            collection_view = CollectionView(self.app, collection_name="Test Collection")

            # Test back to library navigation
            collection_view._on_back_to_library()

            # Verify NavigationHelper was called
            mock_navigate.assert_called_once()

    def test_back_to_library_navigation_failure(self):
        """Test back-to-library navigation when NavigationController fails"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = False

            from fichero.windows.main.views.collection.collection_view import CollectionView

            # Create collection view
            collection_view = CollectionView(self.app, collection_name="Test Collection")

            # Test back to library navigation - should not raise exception
            collection_view._on_back_to_library()

            # Verify NavigationHelper was called
            mock_navigate.assert_called_once()

    def test_back_to_library_exception_handling(self):
        """Test exception handling in back-to-library navigation"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.side_effect = Exception("Test exception")

            from fichero.windows.main.views.collection.collection_view import CollectionView

            # Create collection view
            collection_view = CollectionView(self.app, collection_name="Test Collection")

            # Test back to library navigation - should handle exception gracefully
            collection_view._on_back_to_library()

            # Verify NavigationHelper was called
            mock_navigate.assert_called_once()

    def test_collection_view_initialization_with_mobile_false(self):
        """Test collection view initialization with mobile=False"""
        self.app.is_mobile = False

        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Create collection view
        collection_view = CollectionView(self.app, collection_name="Test Collection", is_mobile=False)

        # Verify mobile state
        self.assertFalse(collection_view.is_mobile)
        self.assertEqual(collection_view.collection_name, "Test Collection")

    def test_collection_view_initialization_with_mobile_true(self):
        """Test collection view initialization with mobile=True"""
        self.app.is_mobile = True

        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Create collection view
        collection_view = CollectionView(self.app, collection_name="Test Collection", is_mobile=True)

        # Verify mobile state
        self.assertTrue(collection_view.is_mobile)
        self.assertEqual(collection_view.collection_name, "Test Collection")

    def test_navigation_back_uses_navigation_helper(self):
        """Test that _on_navigate_back_via_navigation_helper uses NavigationHelper"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = True

            from fichero.windows.main.views.collection.collection_view import CollectionView

            # Create collection view
            collection_view = CollectionView(self.app, collection_name="Test Collection")

            # Test hierarchical back navigation
            collection_view._on_navigate_back_via_navigation_helper()

            # Verify NavigationHelper was called
            mock_navigate.assert_called_once()

    def test_navigation_callbacks_integration(self):
        """Test that NavigationHelper is used instead of legacy PaneManager calls"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = True

            from fichero.windows.main.views.collection.collection_view import CollectionView

            # Create collection view
            collection_view = CollectionView(self.app, collection_name="Test Collection")

            # Register navigation callbacks
            on_back_to_library = MagicMock()
            collection_view.register_callbacks(on_back_to_library=on_back_to_library)

            # Test back to library navigation using the internal method
            collection_view._on_back_to_library()

            # Verify NavigationHelper was used, not the legacy callback
            mock_navigate.assert_called_once()
            call_args = mock_navigate.call_args
            self.assertEqual(call_args[1]['context'], 'collection_back_to_library')

            # Legacy callback should not be called directly
            on_back_to_library.assert_not_called()


if __name__ == '__main__':
    unittest.main()