"""
Unit tests for NavigationHelper

Tests the new consistent navigation system across all windows.
"""

import unittest
from unittest.mock import MagicMock, patch, call
import logging

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestNavigationHelper(unittest.TestCase):
    """Test suite for NavigationHelper class"""

    def setUp(self):
        """Set up test environment"""
        self.app = MagicMock()
        self.app.is_mobile = False

    def test_navigate_back_with_navigation_controller_success(self):
        """Test successful navigation using NavigationController"""
        # Set up NavigationController mock
        navigation_controller = MagicMock()
        navigation_controller.can_navigate_back.return_value = True
        navigation_controller.navigate_back.return_value = True

        view_integration = MagicMock()
        view_integration.get_navigation_controller.return_value = navigation_controller

        self.app.view_integration = view_integration

        # Test navigation
        from fichero.shared.navigation import NavigationHelper

        result = NavigationHelper.navigate_back(self.app, context="test_context")

        # Verify NavigationController was used
        navigation_controller.can_navigate_back.assert_called_once()
        navigation_controller.navigate_back.assert_called_once()
        self.assertTrue(result)

    def test_navigate_back_with_navigation_controller_failure(self):
        """Test NavigationController failure with fallback to window_view_manager"""
        # Set up NavigationController mock that fails
        navigation_controller = MagicMock()
        navigation_controller.can_navigate_back.return_value = True
        navigation_controller.navigate_back.return_value = False

        view_integration = MagicMock()
        view_integration.get_navigation_controller.return_value = navigation_controller

        self.app.view_integration = view_integration

        # Set up window_view_manager fallback
        mobile_view_manager = MagicMock()
        window_view_manager = MagicMock()
        window_view_manager.mobile_view_manager = mobile_view_manager
        self.app.window_view_manager = window_view_manager

        # Test navigation
        from fichero.shared.navigation import NavigationHelper

        result = NavigationHelper.navigate_back(self.app, context="test_context")

        # Verify NavigationController was tried first
        navigation_controller.can_navigate_back.assert_called_once()
        navigation_controller.navigate_back.assert_called_once()

        # Verify fallback to window_view_manager
        mobile_view_manager.go_back.assert_called_once()
        self.assertTrue(result)

    def test_navigate_back_with_custom_fallback(self):
        """Test navigation with custom fallback callback"""
        # No NavigationController or window_view_manager
        self.app.view_integration = None
        delattr(self.app, 'window_view_manager') if hasattr(self.app, 'window_view_manager') else None

        # Custom fallback callback
        fallback_callback = MagicMock()

        # Test navigation
        from fichero.shared.navigation import NavigationHelper

        result = NavigationHelper.navigate_back(
            self.app,
            fallback_callback=fallback_callback,
            context="test_context"
        )

        # Verify fallback callback was used
        fallback_callback.assert_called_once()
        self.assertTrue(result)

    def test_navigate_back_no_navigation_available(self):
        """Test navigation when no navigation methods are available"""
        # No NavigationController, no window_view_manager, no fallback
        self.app.view_integration = None
        delattr(self.app, 'window_view_manager') if hasattr(self.app, 'window_view_manager') else None

        # Test navigation
        from fichero.shared.navigation import NavigationHelper

        result = NavigationHelper.navigate_back(self.app, context="test_context")

        # Verify navigation failed
        self.assertFalse(result)

    def test_can_navigate_back_with_navigation_controller(self):
        """Test can_navigate_back with NavigationController available"""
        navigation_controller = MagicMock()
        navigation_controller.can_navigate_back.return_value = True

        view_integration = MagicMock()
        view_integration.get_navigation_controller.return_value = navigation_controller

        self.app.view_integration = view_integration

        from fichero.shared.navigation import NavigationHelper

        result = NavigationHelper.can_navigate_back(self.app)

        self.assertTrue(result)
        navigation_controller.can_navigate_back.assert_called_once()

    def test_can_navigate_back_with_window_view_manager(self):
        """Test can_navigate_back with window_view_manager available"""
        # No NavigationController
        self.app.view_integration = None

        # Set up window_view_manager
        mobile_view_manager = MagicMock()
        window_view_manager = MagicMock()
        window_view_manager.mobile_view_manager = mobile_view_manager
        self.app.window_view_manager = window_view_manager

        from fichero.shared.navigation import NavigationHelper

        result = NavigationHelper.can_navigate_back(self.app)

        self.assertTrue(result)

    def test_can_navigate_back_no_navigation(self):
        """Test can_navigate_back with no navigation available"""
        # No NavigationController or window_view_manager
        self.app.view_integration = None
        delattr(self.app, 'window_view_manager') if hasattr(self.app, 'window_view_manager') else None

        from fichero.shared.navigation import NavigationHelper

        result = NavigationHelper.can_navigate_back(self.app)

        self.assertFalse(result)

    def test_create_standard_back_handler(self):
        """Test creating a standard back handler"""
        # Set up NavigationController mock
        navigation_controller = MagicMock()
        navigation_controller.can_navigate_back.return_value = True
        navigation_controller.navigate_back.return_value = True

        view_integration = MagicMock()
        view_integration.get_navigation_controller.return_value = navigation_controller

        self.app.view_integration = view_integration

        from fichero.shared.navigation import NavigationHelper

        # Create handler
        handler = NavigationHelper.create_standard_back_handler(
            self.app,
            "test_component"
        )

        # Test handler
        handler()

        # Verify NavigationController was used
        navigation_controller.can_navigate_back.assert_called_once()
        navigation_controller.navigate_back.assert_called_once()

    def test_create_standard_back_handler_with_fallback(self):
        """Test creating a standard back handler with fallback"""
        # No NavigationController
        self.app.view_integration = None
        delattr(self.app, 'window_view_manager') if hasattr(self.app, 'window_view_manager') else None

        fallback_callback = MagicMock()

        from fichero.shared.navigation import NavigationHelper

        # Create handler with fallback
        handler = NavigationHelper.create_standard_back_handler(
            self.app,
            "test_component",
            fallback_callback
        )

        # Test handler
        handler()

        # Verify fallback was used
        fallback_callback.assert_called_once()

    def test_error_handling_in_navigation(self):
        """Test error handling during navigation"""
        # Set up NavigationController that raises exception
        navigation_controller = MagicMock()
        navigation_controller.can_navigate_back.side_effect = Exception("Test error")

        view_integration = MagicMock()
        view_integration.get_navigation_controller.return_value = navigation_controller

        self.app.view_integration = view_integration

        fallback_callback = MagicMock()

        from fichero.shared.navigation import NavigationHelper

        result = NavigationHelper.navigate_back(
            self.app,
            fallback_callback=fallback_callback,
            context="test_context"
        )

        # Verify fallback was used due to exception
        fallback_callback.assert_called_once()
        self.assertTrue(result)

    def test_error_handling_with_fallback_failure(self):
        """Test error handling when both navigation and fallback fail"""
        # Set up NavigationController that raises exception
        navigation_controller = MagicMock()
        navigation_controller.can_navigate_back.side_effect = Exception("Test error")

        view_integration = MagicMock()
        view_integration.get_navigation_controller.return_value = navigation_controller

        self.app.view_integration = view_integration

        # Fallback that also fails
        fallback_callback = MagicMock()
        fallback_callback.side_effect = Exception("Fallback error")

        from fichero.shared.navigation import NavigationHelper

        result = NavigationHelper.navigate_back(
            self.app,
            fallback_callback=fallback_callback,
            context="test_context"
        )

        # Verify both were tried but navigation failed
        fallback_callback.assert_called_once()
        self.assertFalse(result)


class TestNavigationHelperIntegration(unittest.TestCase):
    """Integration tests for NavigationHelper with actual components"""

    def setUp(self):
        """Set up integration test environment"""
        self.app = MagicMock()

    def test_preview_toolbar_integration(self):
        """Test NavigationHelper integration with preview toolbar"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            from fichero.windows.preview.preview_pane_top_toolbar import PreviewPaneTopToolbar

            # Create toolbar
            toolbar = PreviewPaneTopToolbar(self.app, is_mobile=True)

            # Mock widget
            widget = MagicMock()

            # Test back button press
            toolbar._on_back_pressed(widget)

            # Verify NavigationHelper was called
            mock_navigate.assert_called_once()
            call_args = mock_navigate.call_args
            self.assertEqual(call_args[1]['context'], 'preview_toolbar')
            self.assertEqual(call_args[1]['app'], self.app)

    def test_mobile_view_integration(self):
        """Test NavigationHelper integration with mobile views"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            from fichero.windows.settings.mobile_view import SettingsMobileView

            # Create mobile view
            mobile_view = SettingsMobileView(self.app)

            # Test back button press
            mobile_view._on_back_pressed()

            # Verify NavigationHelper was called
            mock_navigate.assert_called_once()
            call_args = mock_navigate.call_args
            self.assertEqual(call_args[1]['context'], 'settings_mobile_view')
            self.assertEqual(call_args[1]['app'], self.app)


if __name__ == '__main__':
    unittest.main()