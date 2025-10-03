"""
Unit tests for MainWindow

Tests main window functionality and initialization.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import toga

from fichero.windows.main.main_window import MainWindow


class TestMainWindow(unittest.TestCase):
    """Test MainWindow functionality"""

    def setUp(self):
        """Set up test environment"""
        # Create mock app
        self.mock_app = Mock()
        self.mock_app.is_mobile = False
        self.mock_app.pane_manager = Mock()
        self.mock_app.command_bridge = Mock()

        # Mock the library service
        self.mock_library_service = Mock()
        self.mock_app.library_service = self.mock_library_service

        # Mock view integration manager
        self.mock_view_integration = Mock()
        self.mock_app.view_integration = self.mock_view_integration

        # Mock library viewmodel
        self.mock_library_viewmodel = Mock()
        self.mock_view_integration.library_viewmodel = self.mock_library_viewmodel

    @patch('fichero.windows.main.main_window.LibraryViewRefactored')
    @patch('fichero.windows.main.main_window.toga.MainWindow')
    def test_main_window_initialization(self, mock_toga_window, mock_library_view):
        """Test main window initializes correctly"""
        # Mock the Toga MainWindow
        mock_window_instance = Mock()
        mock_toga_window.return_value = mock_window_instance

        # Mock the library view
        mock_library_view_instance = Mock()
        mock_library_view.return_value = mock_library_view_instance

        # Create main window
        main_window = MainWindow(self.mock_app)

        # Check initialization
        self.assertIsNotNone(main_window)
        self.assertEqual(main_window.app, self.mock_app)

        # Check Toga window was created
        mock_toga_window.assert_called_once()

        # Check library view was created
        mock_library_view.assert_called_once()

    @patch('fichero.windows.main.main_window.LibraryViewRefactored')
    @patch('fichero.windows.main.main_window.toga.MainWindow')
    def test_main_window_show_method(self, mock_toga_window, mock_library_view):
        """Test main window show method"""
        # Mock the Toga MainWindow
        mock_window_instance = Mock()
        mock_toga_window.return_value = mock_window_instance

        # Mock the library view
        mock_library_view_instance = Mock()
        mock_library_view.return_value = mock_library_view_instance

        # Create main window
        main_window = MainWindow(self.mock_app)

        # Call show
        main_window.show()

        # Check window show was called
        mock_window_instance.show.assert_called_once()

    @patch('fichero.windows.main.main_window.LibraryViewRefactored')
    @patch('fichero.windows.main.main_window.toga.MainWindow')
    def test_main_window_pane_setup(self, mock_toga_window, mock_library_view):
        """Test main window pane setup"""
        # Mock the Toga MainWindow
        mock_window_instance = Mock()
        mock_toga_window.return_value = mock_window_instance

        # Mock the library view
        mock_library_view_instance = Mock()
        mock_library_view.return_value = mock_library_view_instance

        # Mock pane manager methods
        self.mock_app.pane_manager.create_main_layout.return_value = Mock()

        # Create main window
        main_window = MainWindow(self.mock_app)

        # Check pane manager was called
        self.mock_app.pane_manager.create_main_layout.assert_called_once()

    @patch('fichero.windows.main.main_window.LibraryViewRefactored')
    @patch('fichero.windows.main.main_window.toga.MainWindow')
    def test_main_window_handles_mobile_mode(self, mock_toga_window, mock_library_view):
        """Test main window handles mobile mode correctly"""
        # Set app to mobile mode
        self.mock_app.is_mobile = True

        # Mock the Toga MainWindow
        mock_window_instance = Mock()
        mock_toga_window.return_value = mock_window_instance

        # Mock the library view
        mock_library_view_instance = Mock()
        mock_library_view.return_value = mock_library_view_instance

        # Create main window
        main_window = MainWindow(self.mock_app)

        # Check library view was created with mobile=True
        mock_library_view.assert_called_with(
            self.mock_app,
            self.mock_library_viewmodel,
            is_mobile=True
        )

    @patch('fichero.windows.main.main_window.LibraryViewRefactored')
    @patch('fichero.windows.main.main_window.toga.MainWindow')
    def test_main_window_command_bridge_integration(self, mock_toga_window, mock_library_view):
        """Test main window integrates with command bridge"""
        # Mock the Toga MainWindow
        mock_window_instance = Mock()
        mock_toga_window.return_value = mock_window_instance

        # Mock the library view
        mock_library_view_instance = Mock()
        mock_library_view.return_value = mock_library_view_instance

        # Create main window
        main_window = MainWindow(self.mock_app)

        # Check command bridge was integrated
        self.mock_app.command_bridge.set_main_window.assert_called_once_with(main_window)

    @patch('fichero.windows.main.main_window.LibraryViewRefactored')
    @patch('fichero.windows.main.main_window.toga.MainWindow')
    def test_main_window_error_handling(self, mock_toga_window, mock_library_view):
        """Test main window handles initialization errors gracefully"""
        # Mock the library view to raise an exception
        mock_library_view.side_effect = Exception("Test initialization error")

        # Mock the Toga MainWindow
        mock_window_instance = Mock()
        mock_toga_window.return_value = mock_window_instance

        # Create main window - should not raise exception
        try:
            main_window = MainWindow(self.mock_app)
            # If we get here, error was handled gracefully
            self.assertIsNotNone(main_window)
        except Exception as e:
            self.fail(f"MainWindow initialization should handle errors gracefully, but raised: {e}")


if __name__ == '__main__':
    unittest.main()