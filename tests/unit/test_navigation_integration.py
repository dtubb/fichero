"""
Test navigation integration for Fichero
Tests the preview navigation and view switching logic for mobile and desktop platforms.
"""

import unittest
from unittest.mock import MagicMock, patch, call
import logging

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestNavigationIntegration(unittest.TestCase):
    """Test navigation integration functionality"""

    def setUp(self):
        """Set up test environment"""
        self.app = MagicMock()
        self.app.is_mobile = False
        self.app.paths = MagicMock()
        self.app.library_service = MagicMock()

    def test_mobile_preview_navigation_shows_new_view(self):
        """Test mobile preview navigation actually switches to preview view"""
        with patch('fichero.windows.main.main_window.LibraryView'), \
             patch('fichero.windows.main.main_window.CollectionView'), \
             patch('fichero.windows.main.main_window.PreviewPane') as MockPreviewPane, \
             patch('fichero.windows.main.layout.pane_manager.PaneManager') as MockPaneManager:

            from fichero.windows.main.main_window import MainWindow

            # Set up mobile mode
            self.app.is_mobile = True

            # Create main window
            main_window = MainWindow(self.app)
            main_window.pane_manager = MockPaneManager.return_value

            # Mock preview pane
            preview_pane = MockPreviewPane.return_value
            preview_pane.top_toolbar = MagicMock()
            preview_pane.top_toolbar.register_callbacks = MagicMock()
            preview_pane.top_toolbar.update_back_label = MagicMock()

            # Test file preview request
            file_path = "/test/file.jpg"
            file_data = {"name": "file.jpg", "type": "image"}

            main_window._on_file_preview_requested(file_path, file_data)

            # Verify preview pane was created and shown
            MockPreviewPane.assert_called_once_with(self.app, True)
            preview_pane.show_file.assert_called_once_with(file_path, file_data)

            # Verify mobile view switching
            main_window.pane_manager.switch_to_view.assert_called_once_with(
                "preview", preview_pane, "mobile"
            )

            # Verify back navigation was registered
            preview_pane.top_toolbar.register_callbacks.assert_called_once()

    def test_desktop_preview_uses_right_pane(self):
        """Test desktop preview uses right pane instead of switching views"""
        with patch('fichero.windows.main.main_window.LibraryView'), \
             patch('fichero.windows.main.main_window.CollectionView'), \
             patch('fichero.windows.main.layout.pane_manager.PaneManager') as MockPaneManager:

            from fichero.windows.main.main_window import MainWindow

            # Set up desktop mode
            self.app.is_mobile = False

            # Create main window with preview pane
            main_window = MainWindow(self.app)
            main_window.pane_manager = MockPaneManager.return_value
            main_window.preview_pane = MagicMock()

            # Test file preview request
            file_path = "/test/file.jpg"
            file_data = {"name": "file.jpg", "type": "image"}

            main_window._on_file_preview_requested(file_path, file_data)

            # Verify preview was shown in existing right pane
            main_window.preview_pane.show_file.assert_called_once_with(file_path, file_data)

            # Verify no view switching occurred
            main_window.pane_manager.switch_to_view.assert_not_called()

    def test_mobile_back_navigation_from_preview(self):
        """Test mobile back navigation from preview to collection"""
        with patch('fichero.windows.main.main_window.LibraryView'), \
             patch('fichero.windows.main.main_window.CollectionView'), \
             patch('fichero.windows.main.layout.pane_manager.PaneManager') as MockPaneManager:

            from fichero.windows.main.main_window import MainWindow

            # Set up mobile mode
            self.app.is_mobile = True

            # Create main window
            main_window = MainWindow(self.app)
            main_window.pane_manager = MockPaneManager.return_value

            # Mock successful navigation back
            main_window.pane_manager.mobile_navigate_back.return_value = True

            # Test back navigation
            main_window._on_mobile_back_to_collection()

            # Verify mobile navigation was called
            main_window.pane_manager.mobile_navigate_back.assert_called_once()

    def test_collection_bottom_toolbar_preview_callback(self):
        """Test collection bottom toolbar preview callback integration"""
        with patch('fichero.windows.main.views.collection.collection_view.LibraryService'), \
             patch('fichero.shared.views.base_view.BaseView.__init__'):

            from fichero.windows.main.views.collection.collection_view import CollectionView

            # Create collection view
            collection_view = CollectionView(self.app, False)
            collection_view.on_file_preview_requested = MagicMock()

            # Test preview callback
            file_data = {"file_path": "/test/file.jpg", "name": "file.jpg"}
            collection_view._on_preview_file_from_toolbar(file_data)

            # Verify preview callback was called
            collection_view.on_file_preview_requested.assert_called_once_with(
                "/test/file.jpg", file_data
            )

    def test_desktop_collection_back_navigation(self):
        """Test desktop collection back navigation to library"""
        with patch('fichero.windows.main.main_window.LibraryView'), \
             patch('fichero.windows.main.main_window.CollectionView'), \
             patch('fichero.windows.main.layout.pane_manager.PaneManager') as MockPaneManager:

            from fichero.windows.main.main_window import MainWindow

            # Set up desktop mode
            self.app.is_mobile = False

            # Create main window
            main_window = MainWindow(self.app)
            main_window.pane_manager = MockPaneManager.return_value
            main_window.cached_library_view = MagicMock()

            # Test back to library navigation
            main_window._on_back_to_library()

            # Verify library view was shown in left pane
            main_window.pane_manager.switch_to_view.assert_called_with(
                "collection_management", main_window.cached_library_view, "left"
            )


if __name__ == '__main__':
    unittest.main()