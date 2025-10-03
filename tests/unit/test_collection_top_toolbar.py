"""
Unit tests for CollectionTopToolbar NavigationController integration

Tests the pure NavigationController approach in collection top toolbar navigation,
with no legacy fallbacks.
"""

import unittest
from unittest.mock import MagicMock, patch
import logging

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestCollectionTopToolbar(unittest.TestCase):
    """Test suite for CollectionTopToolbar pure NavigationController integration"""

    def setUp(self):
        """Set up test environment"""
        self.app = MagicMock()
        self.app.is_mobile = False

    def test_smart_navigation_uses_navigation_helper_only(self):
        """Test that smart navigation uses NavigationHelper with no fallbacks"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = True

            from fichero.windows.main.views.collection.collection_top_toolbar import CollectionTopToolbar

            # Create toolbar
            toolbar = CollectionTopToolbar(self.app, collection_name="Test Collection")

            # Test smart back navigation
            toolbar._smart_back_navigation()

            # Verify NavigationHelper was called with correct parameters
            mock_navigate.assert_called_once()
            call_args = mock_navigate.call_args
            self.assertEqual(call_args[1]['app'], self.app)
            self.assertEqual(call_args[1]['context'], 'collection_toolbar_smart_navigation')

    def test_smart_navigation_success(self):
        """Test successful NavigationController navigation"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = True

            from fichero.windows.main.views.collection.collection_top_toolbar import CollectionTopToolbar

            # Create toolbar
            toolbar = CollectionTopToolbar(self.app, collection_name="Test Collection")

            # Test smart back navigation
            toolbar._smart_back_navigation()

            # Verify NavigationHelper was called
            mock_navigate.assert_called_once()

    def test_smart_navigation_failure(self):
        """Test NavigationController navigation failure - no fallbacks"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = False

            from fichero.windows.main.views.collection.collection_top_toolbar import CollectionTopToolbar

            # Create toolbar
            toolbar = CollectionTopToolbar(self.app, collection_name="Test Collection")

            # Test smart back navigation - should not raise exception even on failure
            toolbar._smart_back_navigation()

            # Verify NavigationHelper was called
            mock_navigate.assert_called_once()

    def test_smart_navigation_exception_handling(self):
        """Test exception handling in pure NavigationController approach"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.side_effect = Exception("Test exception")

            from fichero.windows.main.views.collection.collection_top_toolbar import CollectionTopToolbar

            # Create toolbar
            toolbar = CollectionTopToolbar(self.app, collection_name="Test Collection")

            # Test smart back navigation - should handle exception gracefully
            toolbar._smart_back_navigation()

            # Verify NavigationHelper was called and exception was caught
            mock_navigate.assert_called_once()

    def test_navigation_state_tracking(self):
        """Test navigation state tracking functionality"""
        from fichero.windows.main.views.collection.collection_top_toolbar import CollectionTopToolbar

        # Create toolbar
        toolbar = CollectionTopToolbar(self.app, collection_name="Test Collection")

        # Test setting navigation state
        toolbar.set_navigation_state("folder1/folder2")
        self.assertEqual(toolbar._current_path, "folder1/folder2")
        self.assertFalse(toolbar._is_at_root)

        # Test root state
        toolbar.set_navigation_state("")
        self.assertEqual(toolbar._current_path, "")
        self.assertTrue(toolbar._is_at_root)

        # Test None state
        toolbar.set_navigation_state(None)
        self.assertEqual(toolbar._current_path, "")
        self.assertTrue(toolbar._is_at_root)

    def test_navigation_state_getter(self):
        """Test navigation state getter functionality"""
        from fichero.windows.main.views.collection.collection_top_toolbar import CollectionTopToolbar

        # Create toolbar
        toolbar = CollectionTopToolbar(self.app, collection_name="Test Collection")

        # Test default state (should be at root)
        self.assertFalse(toolbar._get_current_navigation_state())

        # Test with path
        toolbar.set_navigation_state("folder1")
        self.assertFalse(toolbar._get_current_navigation_state())

        # Test at root
        toolbar.set_navigation_state("")
        self.assertTrue(toolbar._get_current_navigation_state())

    def test_update_navigation_state(self):
        """Test update navigation state method"""
        from fichero.windows.main.views.collection.collection_top_toolbar import CollectionTopToolbar

        # Create toolbar
        toolbar = CollectionTopToolbar(self.app, collection_name="Test Collection")

        # Test update navigation state (should call set_navigation_state)
        toolbar.update_navigation_state("test/path")
        self.assertEqual(toolbar._current_path, "test/path")
        self.assertFalse(toolbar._is_at_root)


if __name__ == '__main__':
    unittest.main()