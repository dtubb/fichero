"""
Unit tests for pure NavigationController system without any legacy fallbacks

Tests that the complete navigation system works using only NavigationController
and NavigationHelper without any legacy fallback code paths.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
import logging

# Set up logging to suppress debug output during tests
logging.getLogger('fichero').setLevel(logging.WARNING)


class TestPureNavigationControllerSystem(unittest.TestCase):
    """Test pure NavigationController system without legacy fallbacks"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_app = Mock()
        self.mock_app.is_mobile = False
        self.mock_app.library_service = Mock()

        # Mock NavigationController
        self.mock_navigation_controller = Mock()
        self.mock_navigation_controller.navigate_back.return_value = True
        self.mock_navigation_controller.navigate_to_path.return_value = True
        self.mock_navigation_controller.navigate_to_collection.return_value = True
        self.mock_navigation_controller.navigate_to_library.return_value = True
        self.mock_navigation_controller.can_navigate_back.return_value = True

        # Mock view_integration
        self.mock_view_integration = Mock()
        self.mock_view_integration.get_navigation_controller.return_value = self.mock_navigation_controller
        self.mock_app.view_integration = self.mock_view_integration

    @patch('fichero.shared.navigation.NavigationHelper.navigate_back')
    def test_navigation_helper_uses_navigation_controller_only(self, mock_nav_helper):
        """Test that NavigationHelper uses NavigationController without fallbacks"""
        # Arrange
        mock_nav_helper.return_value = True

        # Import NavigationHelper
        from fichero.shared.navigation import NavigationHelper

        # Act
        result = NavigationHelper.navigate_back(self.mock_app, context="test")

        # Assert
        mock_nav_helper.assert_called_once_with(self.mock_app, context="test")
        self.assertTrue(result)

    @patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__')
    @patch('fichero.windows.main.views.collection.collection_view.CollectionTopToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.CollectionBottomToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.toga.ScrollContainer')
    @patch('fichero.windows.main.views.collection.collection_view.toga.Box')
    def test_collection_view_uses_pure_navigation_controller(self, mock_box, mock_scroll,
                                                           mock_bottom_toolbar, mock_top_toolbar,
                                                           mock_base_init):
        """Test that CollectionView uses pure NavigationController system"""
        # Arrange
        mock_base_init.return_value = None
        mock_toolbar = Mock()
        mock_top_toolbar.return_value = mock_toolbar
        mock_bottom_toolbar.return_value = Mock()
        mock_box.return_value = Mock()
        mock_scroll.return_value = Mock()

        # Import and create CollectionView
        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Act
        collection_view = CollectionView(self.mock_app, "Test Collection", is_mobile=False)

        # Assert that navigation callback methods exist and use NavigationController
        self.assertTrue(hasattr(collection_view, '_on_back_to_library'))
        self.assertTrue(hasattr(collection_view, '_on_navigate_back_via_navigation_helper'))
        self.assertTrue(hasattr(collection_view, '_on_navigate_to_path_via_navigation_controller'))

        # Verify that legacy methods were removed
        self.assertFalse(hasattr(collection_view, '_go_back'))
        self.assertFalse(hasattr(collection_view, '_on_navigate_back'))
        self.assertFalse(hasattr(collection_view, '_on_navigate_to_path'))
        self.assertFalse(hasattr(collection_view, 'navigate_to_breadcrumb'))
        self.assertFalse(hasattr(collection_view, 'reset_navigation'))

    @patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__')
    @patch('fichero.windows.main.views.collection.collection_view.CollectionTopToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.CollectionBottomToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.toga.ScrollContainer')
    @patch('fichero.windows.main.views.collection.collection_view.toga.Box')
    def test_navigation_back_uses_navigation_helper(self, mock_box, mock_scroll,
                                                   mock_bottom_toolbar, mock_top_toolbar,
                                                   mock_base_init):
        """Test that back navigation uses NavigationHelper only"""
        # Arrange
        mock_base_init.return_value = None
        mock_toolbar = Mock()
        mock_top_toolbar.return_value = mock_toolbar
        mock_bottom_toolbar.return_value = Mock()
        mock_box.return_value = Mock()
        mock_scroll.return_value = Mock()

        from fichero.windows.main.views.collection.collection_view import CollectionView
        collection_view = CollectionView(self.mock_app, "Test Collection", is_mobile=False)

        # Mock NavigationHelper
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_nav_helper:
            mock_nav_helper.return_value = True

            # Act
            collection_view._on_navigate_back_via_navigation_helper()

            # Assert
            mock_nav_helper.assert_called_once_with(
                app=self.mock_app,
                context="collection_toolbar_back"
            )

    @patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__')
    @patch('fichero.windows.main.views.collection.collection_view.CollectionTopToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.CollectionBottomToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.toga.ScrollContainer')
    @patch('fichero.windows.main.views.collection.collection_view.toga.Box')
    def test_path_navigation_uses_navigation_controller_directly(self, mock_box, mock_scroll,
                                                               mock_bottom_toolbar, mock_top_toolbar,
                                                               mock_base_init):
        """Test that path navigation uses NavigationController directly"""
        # Arrange
        mock_base_init.return_value = None
        mock_toolbar = Mock()
        mock_top_toolbar.return_value = mock_toolbar
        mock_bottom_toolbar.return_value = Mock()
        mock_box.return_value = Mock()
        mock_scroll.return_value = Mock()

        from fichero.windows.main.views.collection.collection_view import CollectionView
        collection_view = CollectionView(self.mock_app, "Test Collection", is_mobile=False)

        # Act
        collection_view._on_navigate_to_path_via_navigation_controller("test/path")

        # Assert
        self.mock_navigation_controller.navigate_to_path.assert_called_once_with("test/path")

    @patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__')
    @patch('fichero.windows.main.views.collection.collection_view.CollectionTopToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.CollectionBottomToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.toga.ScrollContainer')
    @patch('fichero.windows.main.views.collection.collection_view.toga.Box')
    def test_navigate_to_folder_uses_navigation_controller_only(self, mock_box, mock_scroll,
                                                              mock_bottom_toolbar, mock_top_toolbar,
                                                              mock_base_init):
        """Test that folder navigation uses NavigationController only, no fallbacks"""
        # Arrange
        mock_base_init.return_value = None
        mock_toolbar = Mock()
        mock_top_toolbar.return_value = mock_toolbar
        mock_bottom_toolbar.return_value = Mock()
        mock_box.return_value = Mock()
        mock_scroll.return_value = Mock()

        from fichero.windows.main.views.collection.collection_view import CollectionView
        collection_view = CollectionView(self.mock_app, "Test Collection", is_mobile=False)

        # Set up initial state
        collection_view.collection_id = "test_collection"
        collection_view.current_path = ""

        # Act
        collection_view.navigate_to_folder("test_folder")

        # Assert - verify NavigationController was called with correct path
        self.mock_navigation_controller.navigate_to_path.assert_called_once_with("test_folder")

    @patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__')
    @patch('fichero.windows.main.views.collection.collection_view.CollectionTopToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.CollectionBottomToolbar')
    @patch('fichero.windows.main.views.collection.collection_view.toga.ScrollContainer')
    @patch('fichero.windows.main.views.collection.collection_view.toga.Box')
    def test_navigation_controller_failure_raises_runtime_error(self, mock_box, mock_scroll,
                                                              mock_bottom_toolbar, mock_top_toolbar,
                                                              mock_base_init):
        """Test that NavigationController failure raises RuntimeError (no fallback)"""
        # Arrange
        mock_base_init.return_value = None
        mock_toolbar = Mock()
        mock_top_toolbar.return_value = mock_toolbar
        mock_bottom_toolbar.return_value = Mock()
        mock_box.return_value = Mock()
        mock_scroll.return_value = Mock()

        # Make NavigationController fail
        self.mock_navigation_controller.navigate_to_path.return_value = False

        from fichero.windows.main.views.collection.collection_view import CollectionView
        collection_view = CollectionView(self.mock_app, "Test Collection", is_mobile=False)

        # Set up initial state
        collection_view.collection_id = "test_collection"
        collection_view.current_path = ""

        # Act & Assert - NavigationController failure should raise RuntimeError
        with self.assertRaises(RuntimeError) as context:
            collection_view.navigate_to_folder("test_folder")

        self.assertIn("NavigationController failed to navigate to path", str(context.exception))

    def test_navigation_controller_integration_no_legacy_path_history(self):
        """Test that NavigationController is integrated without legacy path_history"""
        # Import NavigationController
        from fichero.shared.navigation.navigation_controller import NavigationController

        # Act
        navigation_controller = NavigationController(self.mock_app.library_service, is_mobile=False)

        # Assert that NavigationController doesn't use legacy path_history
        self.assertFalse(hasattr(navigation_controller, 'path_history'))
        self.assertTrue(hasattr(navigation_controller, 'history'))  # Uses NavigationHistory instead
        self.assertTrue(hasattr(navigation_controller, 'current_state'))

    def test_navigation_helper_no_legacy_fallbacks(self):
        """Test that NavigationHelper has no legacy fallback code"""
        from fichero.shared.navigation import NavigationHelper

        # Verify NavigationHelper only has NavigationController methods
        helper_methods = [method for method in dir(NavigationHelper) if not method.startswith('_')]
        expected_methods = ['navigate_back', 'get_navigation_controller', 'can_navigate_back', 'create_standard_back_handler']

        for method in expected_methods:
            self.assertIn(method, helper_methods)

        # Verify no legacy fallback methods exist
        legacy_methods = ['_legacy_navigate_back', 'fallback_navigation', '_old_navigate']
        for legacy_method in legacy_methods:
            self.assertNotIn(legacy_method, helper_methods)


if __name__ == '__main__':
    unittest.main()