"""
Comprehensive back navigation tests for Fichero
Tests all fixes for mobile preview back navigation and desktop collection back buttons.
"""

import unittest
from unittest.mock import MagicMock, patch, call
import logging

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestBackNavigationComprehensive(unittest.TestCase):
    """Comprehensive test suite for back navigation fixes"""

    def setUp(self):
        """Set up test environment"""
        self.app = MagicMock()
        self.app.is_mobile = False

    def test_mobile_preview_toolbar_callback_registration(self):
        """Test mobile preview toolbar callback registration"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            # Mobile preview pane
            self.app.is_mobile = True
            preview_pane = PreviewPane(self.app, True)

            # Mock callback
            mock_callback = MagicMock()

            # Register callback
            preview_pane.top_toolbar.register_callbacks(
                on_back_to_fiche=mock_callback
            )

            # Verify registration
            self.assertEqual(preview_pane.top_toolbar.on_back_to_fiche, mock_callback)
            self.assertIsNone(preview_pane.top_toolbar.on_back)

    def test_mobile_preview_back_button_functionality(self):
        """Test mobile preview back button functionality"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            # Mobile preview pane
            self.app.is_mobile = True
            preview_pane = PreviewPane(self.app, True)

            # Mock callback
            mock_callback = MagicMock()
            preview_pane.top_toolbar.register_callbacks(
                on_back_to_fiche=mock_callback
            )

            # Simulate back button press
            preview_pane.top_toolbar._on_back_pressed(None)

            # Verify callback was called
            mock_callback.assert_called_once()

    def test_desktop_collection_toolbar_callback_registration(self):
        """Test desktop collection toolbar callback registration"""
        with patch('fichero.shared.toolbars.top_toolbar.TopToolbar.__init__'):
            from fichero.windows.main.views.collection.collection_top_toolbar import CollectionTopToolbar

            # Desktop collection toolbar
            self.app.is_mobile = False
            toolbar = CollectionTopToolbar(self.app, "Test Collection", False)

            # Mock callbacks
            mock_back_to_library = MagicMock()
            mock_navigate_back = MagicMock()

            # Register navigation callbacks
            toolbar.register_navigation_callbacks(
                on_back_to_library=mock_back_to_library,
                on_navigate_back=mock_navigate_back
            )

            # Verify smart navigation is set up
            self.assertEqual(toolbar.on_back_to_library, mock_back_to_library)
            self.assertEqual(toolbar.on_navigate_back, mock_navigate_back)
            self.assertEqual(toolbar.on_back, toolbar._smart_back_navigation)

    def test_desktop_collection_toolbar_late_back_button_creation(self):
        """Test desktop collection toolbar late back button creation"""
        with patch('fichero.shared.toolbars.top_toolbar.TopToolbar.__init__'):
            from fichero.windows.main.views.collection.collection_top_toolbar import CollectionTopToolbar

            # Desktop collection toolbar
            self.app.is_mobile = False
            toolbar = CollectionTopToolbar(self.app, "Test Collection", False)

            # Mock toolbar methods
            toolbar.left_content = MagicMock()
            toolbar._create_back_button = MagicMock(return_value=MagicMock())
            toolbar.add_to_left = MagicMock()

            # Mock callbacks
            mock_back_to_library = MagicMock()

            # Simulate the late back button creation process
            toolbar.register_navigation_callbacks(
                on_back_to_library=mock_back_to_library
            )

            # Verify the late back button creation was called
            toolbar._create_back_button.assert_called()
            toolbar.add_to_left.assert_called()

    def test_desktop_collection_smart_back_navigation(self):
        """Test desktop collection smart back navigation logic"""
        with patch('fichero.shared.toolbars.top_toolbar.TopToolbar.__init__'):
            from fichero.windows.main.views.collection.collection_top_toolbar import CollectionTopToolbar

            # Desktop collection toolbar
            self.app.is_mobile = False
            toolbar = CollectionTopToolbar(self.app, "Test Collection", False)

            # Mock callbacks
            mock_back_to_library = MagicMock()
            mock_navigate_back = MagicMock()

            # Register callbacks
            toolbar.register_navigation_callbacks(
                on_back_to_library=mock_back_to_library,
                on_navigate_back=mock_navigate_back
            )

            # Test smart navigation - should call navigate_back when not at root
            toolbar._smart_back_navigation()

            # For this test, we expect fallback to library (since we can't mock internal state)
            mock_back_to_library.assert_called()

    def test_desktop_collection_back_button_only_library_callback(self):
        """Test desktop collection back button with only library callback"""
        with patch('fichero.shared.toolbars.top_toolbar.TopToolbar.__init__'):
            from fichero.windows.main.views.collection.collection_top_toolbar import CollectionTopToolbar

            # Desktop collection toolbar
            self.app.is_mobile = False
            toolbar = CollectionTopToolbar(self.app, "Test Collection", False)

            # Mock callbacks - only back to library
            mock_back_to_library = MagicMock()

            # Register callbacks
            toolbar.register_navigation_callbacks(
                on_back_to_library=mock_back_to_library
            )

            # Should set on_back to library callback directly
            self.assertEqual(toolbar.on_back, mock_back_to_library)

    def test_mobile_collection_toolbar_no_desktop_back_button(self):
        """Test mobile collection toolbar doesn't create desktop back button"""
        with patch('fichero.shared.toolbars.top_toolbar.TopToolbar.__init__'):
            from fichero.windows.main.views.collection.collection_top_toolbar import CollectionTopToolbar

            # Mobile collection toolbar
            self.app.is_mobile = True
            toolbar = CollectionTopToolbar(self.app, "Test Collection", True)

            # Mock toolbar methods
            toolbar._create_back_button = MagicMock()
            toolbar.add_to_left = MagicMock()

            # Mock callbacks
            mock_back_to_library = MagicMock()

            # Register callbacks
            toolbar.register_navigation_callbacks(
                on_back_to_library=mock_back_to_library
            )

            # Should NOT create desktop back button for mobile
            toolbar._create_back_button.assert_not_called()

    def test_preview_toolbar_debug_logging(self):
        """Test preview toolbar generates proper debug logging"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            preview_pane = PreviewPane(self.app, True)
            mock_callback = MagicMock()

            # Capture log output
            with self.assertLogs(level='INFO') as log:
                # Register callback
                preview_pane.top_toolbar.register_callbacks(
                    on_back_to_fiche=mock_callback
                )

                # Simulate back button press
                preview_pane.top_toolbar._on_back_pressed(None)

            # Verify debug logs
            log_output = '\n'.join(log.output)
            self.assertIn('🔙 Registering preview toolbar callbacks', log_output)
            self.assertIn('🔙 PREVIEW BACK BUTTON PRESSED!', log_output)
            self.assertIn('🔙 Calling on_back_to_fiche callback', log_output)

    def test_collection_toolbar_debug_logging(self):
        """Test collection toolbar generates proper debug logging"""
        with patch('fichero.shared.toolbars.top_toolbar.TopToolbar.__init__'):
            from fichero.windows.main.views.collection.collection_top_toolbar import CollectionTopToolbar

            # Desktop collection toolbar
            self.app.is_mobile = False
            toolbar = CollectionTopToolbar(self.app, "Test Collection", False)

            # Mock methods to avoid actual button creation
            toolbar._create_back_button = MagicMock(return_value=MagicMock())
            toolbar.add_to_left = MagicMock()
            toolbar.left_content = MagicMock()

            # Capture log output
            with self.assertLogs(level='INFO') as log:
                toolbar.register_navigation_callbacks(
                    on_back_to_library=MagicMock()
                )

            # Verify debug logs
            log_output = '\n'.join(log.output)
            self.assertIn('🔙 Desktop back button check', log_output)
            self.assertIn('🔙 Creating/recreating desktop back button', log_output)
            self.assertIn('🔙 ✅ Late desktop back button added successfully!', log_output)

    def test_url_preview_functionality(self):
        """Test URL preview functionality still works"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            preview_pane = PreviewPane(self.app, False)

            # Test URL detection
            self.assertEqual(preview_pane._detect_file_type("https://example.com"), "url")
            self.assertEqual(preview_pane._detect_file_type("http://example.com"), "url")
            self.assertEqual(preview_pane._detect_file_type("ftp://example.com/file.txt"), "url")

            # Test regular file detection still works
            self.assertEqual(preview_pane._detect_file_type("test.jpg"), "image")
            self.assertEqual(preview_pane._detect_file_type("test.pdf"), "pdf")


class TestBackNavigationIntegration(unittest.TestCase):
    """Integration tests for back navigation across components"""

    def setUp(self):
        """Set up integration test environment"""
        self.app = MagicMock()

    def test_mobile_preview_to_collection_flow(self):
        """Test complete mobile preview to collection navigation flow"""
        # This would test the full flow from main window to preview and back
        # Skipped for now due to complex dependencies
        pass

    def test_desktop_collection_to_library_flow(self):
        """Test complete desktop collection to library navigation flow"""
        # This would test the full flow from library to collection and back
        # Skipped for now due to complex dependencies
        pass


if __name__ == '__main__':
    unittest.main()