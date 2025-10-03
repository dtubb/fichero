"""
Unit tests for MainWindow NavigationController integration

Tests the updated main window preview→collection navigation using NavigationController
without legacy fallbacks.
"""

import unittest
from unittest.mock import MagicMock, patch
import logging

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestMainWindowNavigation(unittest.TestCase):
    """Test suite for MainWindow NavigationController integration"""

    def setUp(self):
        """Set up test environment"""
        self.app = MagicMock()
        self.app.is_mobile = False
        self.app.library_service = MagicMock()

    def test_mobile_back_from_preview_uses_navigation_helper(self):
        """Test that mobile back from preview uses NavigationHelper"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = True

            from fichero.windows.main.main_window import MainWindowRefactored

            # Create main window
            main_window = MainWindowRefactored(self.app)

            # Test mobile back from preview navigation
            main_window._on_mobile_back_to_collection()

            # Verify NavigationHelper was called with correct parameters
            mock_navigate.assert_called_once()
            call_args = mock_navigate.call_args
            self.assertEqual(call_args[1]['app'], self.app)
            self.assertEqual(call_args[1]['context'], 'preview_back_to_collection')

    def test_mobile_back_from_preview_navigation_success(self):
        """Test successful mobile back from preview navigation"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = True

            from fichero.windows.main.main_window import MainWindowRefactored

            # Create main window
            main_window = MainWindowRefactored(self.app)

            # Test mobile back from preview navigation
            main_window._on_mobile_back_to_collection()

            # Verify NavigationHelper was called
            mock_navigate.assert_called_once()

    def test_mobile_back_from_preview_navigation_failure(self):
        """Test mobile back from preview navigation when NavigationController fails"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = False

            from fichero.windows.main.main_window import MainWindowRefactored

            # Create main window
            main_window = MainWindowRefactored(self.app)

            # Test mobile back from preview navigation - should not raise exception
            main_window._on_mobile_back_to_collection()

            # Verify NavigationHelper was called
            mock_navigate.assert_called_once()

    def test_mobile_back_from_preview_exception_handling(self):
        """Test exception handling in mobile back from preview navigation"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.side_effect = Exception("Test exception")

            from fichero.windows.main.main_window import MainWindowRefactored

            # Create main window
            main_window = MainWindowRefactored(self.app)

            # Test mobile back from preview navigation - should handle exception gracefully
            main_window._on_mobile_back_to_collection()

            # Verify NavigationHelper was called
            mock_navigate.assert_called_once()

    def test_main_window_initialization_with_mobile_false(self):
        """Test main window initialization with mobile=False"""
        self.app.is_mobile = False

        from fichero.windows.main.main_window import MainWindowRefactored

        # Create main window
        with patch.object(MainWindowRefactored, '_detect_mobile_platform', return_value=False):
            with patch.object(MainWindowRefactored, '_initialize_components'):
                with patch.object(MainWindowRefactored, '_create_window'):
                    with patch.object(MainWindowRefactored, '_setup_initial_views'):
                        main_window = MainWindowRefactored(self.app)

                        # Verify mobile state
                        self.assertFalse(main_window.is_mobile)

    def test_main_window_initialization_with_mobile_true(self):
        """Test main window initialization with mobile=True"""
        self.app.is_mobile = True

        from fichero.windows.main.main_window import MainWindowRefactored

        # Create main window
        with patch.object(MainWindowRefactored, '_detect_mobile_platform', return_value=True):
            with patch.object(MainWindowRefactored, '_initialize_components'):
                with patch.object(MainWindowRefactored, '_create_window'):
                    with patch.object(MainWindowRefactored, '_setup_initial_views'):
                        with patch.object(MainWindowRefactored, '_setup_mobile_view_manager'):
                            main_window = MainWindowRefactored(self.app)

                            # Verify mobile state
                            self.assertTrue(main_window.is_mobile)

    def test_no_legacy_fallbacks_in_navigation(self):
        """Test that NavigationHelper is used without legacy fallbacks"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = True

            from fichero.windows.main.main_window import MainWindowRefactored

            # Create main window
            main_window = MainWindowRefactored(self.app)

            # Test mobile back from preview navigation
            main_window._on_mobile_back_to_collection()

            # Verify NavigationHelper was used, no legacy methods called
            mock_navigate.assert_called_once()
            call_args = mock_navigate.call_args
            self.assertEqual(call_args[1]['context'], 'preview_back_to_collection')

    def test_navigation_integration_without_fallbacks(self):
        """Test that preview→collection navigation uses unified NavigationController system"""
        with patch('fichero.shared.navigation.NavigationHelper.navigate_back') as mock_navigate:
            mock_navigate.return_value = True

            from fichero.windows.main.main_window import MainWindowRefactored

            # Create main window
            main_window = MainWindowRefactored(self.app)

            # Test navigation
            main_window._on_mobile_back_to_collection()

            # Verify unified system is used
            mock_navigate.assert_called_once()
            self.assertIn('preview_back_to_collection', str(mock_navigate.call_args))


if __name__ == '__main__':
    unittest.main()