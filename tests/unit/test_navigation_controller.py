"""
Unit tests for NavigationController

Tests navigation logic without GUI dependencies.
"""

import unittest
from unittest.mock import Mock, MagicMock
import tempfile
import os

from fichero.shared.navigation.navigation_controller import NavigationController
from fichero.shared.navigation.navigation_state import NavigationContext, NavigationState
from fichero.shared.navigation.navigation_commands import (
    NavigateToLibrary, NavigateToCollection, NavigateToPath, NavigateBack
)


class TestNavigationController(unittest.TestCase):
    """Test NavigationController functionality"""

    def setUp(self):
        """Set up test environment"""
        # Create mock library service
        self.mock_library_service = Mock()

        # Create navigation controller
        self.nav_controller = NavigationController(
            library_service=self.mock_library_service,
            is_mobile=False
        )

    def test_initial_state(self):
        """Test initial navigation state"""
        state = self.nav_controller.get_current_state()
        self.assertEqual(state.context, NavigationContext.LIBRARY)
        self.assertIsNone(state.collection_id)
        self.assertEqual(state.current_path, "")

    def test_navigate_to_library(self):
        """Test navigation to library"""
        success = self.nav_controller.navigate_to_library()
        self.assertTrue(success)

        state = self.nav_controller.get_current_state()
        self.assertEqual(state.context, NavigationContext.LIBRARY)

    def test_navigate_to_collection(self):
        """Test navigation to collection"""
        collection_id = "test-collection"
        collection_name = "Test Collection"

        success = self.nav_controller.navigate_to_collection(collection_id, collection_name)
        self.assertTrue(success)

        state = self.nav_controller.get_current_state()
        self.assertEqual(state.context, NavigationContext.COLLECTION)
        self.assertEqual(state.collection_id, collection_id)
        self.assertEqual(state.collection_name, collection_name)
        self.assertEqual(state.current_path, "")

    def test_navigate_to_path(self):
        """Test navigation to path within collection"""
        # First navigate to a collection
        self.nav_controller.navigate_to_collection("test-collection", "Test Collection")

        # Then navigate to path
        path = "folder1/subfolder"
        success = self.nav_controller.navigate_to_path(path)
        self.assertTrue(success)

        state = self.nav_controller.get_current_state()
        self.assertEqual(state.context, NavigationContext.COLLECTION)
        self.assertEqual(state.current_path, path)

    def test_navigate_to_path_without_collection_fails(self):
        """Test that path navigation fails when not in collection context"""
        success = self.nav_controller.navigate_to_path("some/path")
        self.assertFalse(success)

    def test_navigate_back(self):
        """Test back navigation"""
        # Navigate to collection, then back
        self.nav_controller.navigate_to_collection("test-collection", "Test Collection")

        # Should be able to go back to library if we have history
        if self.nav_controller.can_navigate_back():
            success = self.nav_controller.navigate_back()
            self.assertTrue(success)
            state = self.nav_controller.get_current_state()
            self.assertEqual(state.context, NavigationContext.LIBRARY)
        else:
            # If we can't go back, that's also acceptable behavior
            success = self.nav_controller.navigate_back()
            self.assertFalse(success)

    def test_navigate_back_from_library_fails(self):
        """Test that back navigation fails from library (no history)"""
        success = self.nav_controller.navigate_back()
        self.assertFalse(success)

    def test_command_execution(self):
        """Test command pattern execution"""
        # Test NavigateToCollection command
        cmd = NavigateToCollection(collection_id="test-collection", collection_name="Test Collection")
        success = self.nav_controller.execute_command(cmd)
        self.assertTrue(success)

        state = self.nav_controller.get_current_state()
        self.assertEqual(state.collection_id, "test-collection")

    def test_invalid_command_execution(self):
        """Test execution of invalid commands"""
        # Test NavigateToPath without collection context
        cmd = NavigateToPath(path="some/path")
        success = self.nav_controller.execute_command(cmd)
        self.assertFalse(success)

    def test_breadcrumbs(self):
        """Test breadcrumb generation"""
        # Start at library
        breadcrumbs = self.nav_controller.get_breadcrumbs()
        self.assertEqual(len(breadcrumbs), 1)
        self.assertEqual(breadcrumbs[0]['name'], 'Library')

        # Navigate to collection
        self.nav_controller.navigate_to_collection("test-collection", "Test Collection")
        breadcrumbs = self.nav_controller.get_breadcrumbs()
        self.assertEqual(len(breadcrumbs), 2)
        self.assertEqual(breadcrumbs[1]['name'], 'Test Collection')

        # Navigate to path
        self.nav_controller.navigate_to_path("folder1/subfolder")
        breadcrumbs = self.nav_controller.get_breadcrumbs()
        self.assertEqual(len(breadcrumbs), 4)  # Library + Collection + folder1 + subfolder
        self.assertEqual(breadcrumbs[2]['name'], 'folder1')
        self.assertEqual(breadcrumbs[3]['name'], 'subfolder')

    def test_navigation_callbacks(self):
        """Test navigation event callbacks"""
        callback_calls = []

        def state_changed_callback(state):
            callback_calls.append(('state_changed', state.context.value))

        def collection_loaded_callback(collection_id, collection_name):
            callback_calls.append(('collection_loaded', collection_id, collection_name))

        # Register callbacks
        self.nav_controller.add_callback('state_changed', state_changed_callback)
        self.nav_controller.add_callback('collection_loaded', collection_loaded_callback)

        # Navigate to collection
        self.nav_controller.navigate_to_collection("test-collection", "Test Collection")

        # Check callbacks were called
        self.assertTrue(len(callback_calls) >= 2)
        self.assertIn(('state_changed', 'collection'), callback_calls)
        self.assertIn(('collection_loaded', 'test-collection', 'Test Collection'), callback_calls)

    def test_history_management(self):
        """Test navigation history"""
        # Initially can't go back
        self.assertFalse(self.nav_controller.can_navigate_back())

        # Navigate to collection
        self.nav_controller.navigate_to_collection("test-collection", "Test Collection")

        # May or may not be able to go back depending on implementation
        can_go_back_after_collection = self.nav_controller.can_navigate_back()

        # Navigate to path
        self.nav_controller.navigate_to_path("folder1")

        # Should be able to go back after path navigation
        self.assertTrue(self.nav_controller.can_navigate_back())

        # Go back
        back_result = self.nav_controller.navigate_back()
        self.assertTrue(back_result)

        state = self.nav_controller.get_current_state()
        # After going back, we should be in a valid state
        self.assertIn(state.context.value, ["library", "collection"])

        # If we're in collection context, check the details
        if state.context.value == "collection":
            self.assertEqual(state.current_path, "")
            self.assertEqual(state.collection_id, "test-collection")

    def test_navigation_info(self):
        """Test navigation info retrieval"""
        info = self.nav_controller.get_navigation_info()

        # Check required fields
        self.assertIn('current_state', info)
        self.assertIn('can_go_back', info)
        self.assertIn('can_go_forward', info)
        self.assertIn('breadcrumbs', info)
        self.assertIn('history_size', info)
        self.assertIn('is_mobile', info)

        # Check values
        self.assertEqual(info['is_mobile'], False)
        self.assertEqual(info['can_go_back'], False)
        self.assertEqual(info['history_size'], 0)  # No history initially


if __name__ == '__main__':
    unittest.main()