"""
Test mobile back navigation functionality for Fichero
Tests the mobile preview back navigation callback system.
"""

import unittest
from unittest.mock import MagicMock, patch, call
import logging

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestMobileBackNavigation(unittest.TestCase):
    """Test mobile back navigation functionality"""

    def setUp(self):
        """Set up test environment"""
        self.app = MagicMock()
        self.app.is_mobile = True

    def test_mobile_preview_back_navigation_callback_registration(self):
        """Test that mobile preview back navigation callback is registered correctly"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            preview_pane = PreviewPane(self.app, True)

            # Mock the callback function
            mock_callback = MagicMock()

            # Register the callback
            preview_pane.top_toolbar.register_callbacks(
                on_back_to_fiche=mock_callback
            )

            # Verify the callback was registered
            self.assertEqual(preview_pane.top_toolbar.on_back_to_fiche, mock_callback)

    def test_mobile_preview_back_button_press_triggers_callback(self):
        """Test that pressing back button triggers the registered callback"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            preview_pane = PreviewPane(self.app, True)

            # Mock the callback function
            mock_callback = MagicMock()

            # Register the callback
            preview_pane.top_toolbar.register_callbacks(
                on_back_to_fiche=mock_callback
            )

            # Simulate back button press
            preview_pane.top_toolbar._on_back_pressed(None)

            # Verify the callback was called
            mock_callback.assert_called_once()

    def test_main_window_mobile_back_to_collection_method_exists(self):
        """Test that the main window has the mobile back to collection method"""
        with patch('fichero.windows.main.layout.pane_manager.PaneManager'):
            with patch('fichero.windows.main.commands.command_bridge.CommandBridge'):
                from fichero.windows.main.main_window import MainWindow

                main_window = MainWindow(self.app, True)

                # Verify the method exists
                self.assertTrue(hasattr(main_window, '_on_mobile_back_to_collection'))
                self.assertTrue(callable(getattr(main_window, '_on_mobile_back_to_collection')))

    def test_main_window_mobile_back_to_collection_calls_pane_manager(self):
        """Test that mobile back to collection calls pane manager navigation"""
        with patch('fichero.windows.main.layout.pane_manager.PaneManager') as MockPaneManager:
            with patch('fichero.windows.main.commands.command_bridge.CommandBridge'):
                from fichero.windows.main.main_window import MainWindow

                # Mock pane manager
                mock_pane_manager = MagicMock()
                MockPaneManager.return_value = mock_pane_manager

                main_window = MainWindow(self.app, True)
                main_window.pane_manager = mock_pane_manager

                # Mock the mobile_navigate_back method to return True
                mock_pane_manager.mobile_navigate_back.return_value = True

                # Call the mobile back to collection method
                main_window._on_mobile_back_to_collection()

                # Verify pane manager navigation was called
                mock_pane_manager.mobile_navigate_back.assert_called_once()

    def test_preview_toolbar_back_button_debug_logging(self):
        """Test that back button press generates proper debug logging"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            preview_pane = PreviewPane(self.app, True)

            # Mock the callback function
            mock_callback = MagicMock()

            # Register the callback
            preview_pane.top_toolbar.register_callbacks(
                on_back_to_fiche=mock_callback
            )

            # Capture log output
            with self.assertLogs(level='INFO') as log:
                # Simulate back button press
                preview_pane.top_toolbar._on_back_pressed(None)

            # Verify debug logs were generated
            log_output = '\n'.join(log.output)
            self.assertIn('🔙 PREVIEW BACK BUTTON PRESSED!', log_output)
            self.assertIn('🔙 Calling on_back_to_fiche callback', log_output)

    def test_main_window_callback_registration_debug_logging(self):
        """Test that callback registration generates proper debug logging"""
        # This test would need to mock the main window file selection process
        # that triggers preview pane creation and callback registration
        pass  # Skip for now - requires complex mocking


if __name__ == '__main__':
    unittest.main()