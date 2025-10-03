"""
Unit tests for BaseView NavigationController integration

Tests the updated base view mobile navigation using NavigationController
without legacy fallbacks.
"""

import unittest
from unittest.mock import MagicMock, patch
import logging

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestBaseViewNavigation(unittest.TestCase):
    """Test suite for BaseView NavigationController integration"""

    def setUp(self):
        """Set up test environment"""
        self.app = MagicMock()
        self.app.is_mobile = True

    def test_base_view_mobile_navigation_uses_navigation_helper(self):
        """Test that BaseView mobile navigation uses NavigationHelper"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = True

            from fichero.shared.views.base_view import BaseView

            # Create base view
            base_view = BaseView(self.app, is_mobile=True)

            # Mock toolbar with back callback capability
            mock_toolbar = MagicMock()
            mock_toolbar.set_back_callback = MagicMock()
            base_view.top_toolbar = mock_toolbar

            # Test mobile navigation connection
            base_view.connect_mobile_navigation()

            # Verify toolbar callback was set
            mock_toolbar.set_back_callback.assert_called_once()

            # Get the callback function that was passed
            callback_func = mock_toolbar.set_back_callback.call_args[0][0]

            # Test the callback
            result = callback_func()

            # Verify NavigationHelper was called with correct parameters
            mock_navigate.assert_called_once()
            call_args = mock_navigate.call_args
            self.assertEqual(call_args[1]['app'], self.app)
            self.assertEqual(call_args[1]['context'], 'base_view_mobile_back')
            self.assertTrue(result)

    def test_base_view_navigation_success(self):
        """Test successful BaseView navigation"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = True

            from fichero.shared.views.base_view import BaseView

            base_view = BaseView(self.app, is_mobile=True)
            mock_toolbar = MagicMock()
            base_view.top_toolbar = mock_toolbar

            base_view.connect_mobile_navigation()
            callback_func = mock_toolbar.set_back_callback.call_args[0][0]

            result = callback_func()

            self.assertTrue(result)
            mock_navigate.assert_called_once()

    def test_base_view_navigation_failure(self):
        """Test BaseView navigation when NavigationController fails"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = False

            from fichero.shared.views.base_view import BaseView

            base_view = BaseView(self.app, is_mobile=True)
            mock_toolbar = MagicMock()
            base_view.top_toolbar = mock_toolbar

            base_view.connect_mobile_navigation()
            callback_func = mock_toolbar.set_back_callback.call_args[0][0]

            result = callback_func()

            self.assertFalse(result)
            mock_navigate.assert_called_once()

    def test_base_view_navigation_exception_handling(self):
        """Test exception handling in BaseView navigation"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.side_effect = Exception("Test exception")

            from fichero.shared.views.base_view import BaseView

            base_view = BaseView(self.app, is_mobile=True)
            mock_toolbar = MagicMock()
            base_view.top_toolbar = mock_toolbar

            base_view.connect_mobile_navigation()
            callback_func = mock_toolbar.set_back_callback.call_args[0][0]

            # Should handle exception gracefully
            result = callback_func()

            self.assertFalse(result)
            mock_navigate.assert_called_once()

    def test_no_mobile_navigation_for_desktop(self):
        """Test that desktop views don't connect mobile navigation"""
        from fichero.shared.views.base_view import BaseView

        base_view = BaseView(self.app, is_mobile=False)
        mock_toolbar = MagicMock()
        base_view.top_toolbar = mock_toolbar

        base_view.connect_mobile_navigation()

        # Should not call set_back_callback for desktop
        mock_toolbar.set_back_callback.assert_not_called()

    def test_no_navigation_without_toolbar(self):
        """Test that navigation is not connected without toolbar"""
        from fichero.shared.views.base_view import BaseView

        base_view = BaseView(self.app, is_mobile=True)
        base_view.top_toolbar = None

        # Should not raise exception
        base_view.connect_mobile_navigation()


if __name__ == '__main__':
    unittest.main()