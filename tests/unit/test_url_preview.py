"""
Test URL preview functionality for Fichero
Tests the URL detection and WebView integration.
"""

import unittest
from unittest.mock import MagicMock, patch, call
import logging

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestURLPreview(unittest.TestCase):
    """Test URL preview functionality"""

    def setUp(self):
        """Set up test environment"""
        self.app = MagicMock()
        self.app.is_mobile = False

    def test_url_detection_https(self):
        """Test URL detection for HTTPS URLs"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            preview_pane = PreviewPane(self.app, False)

            # Test HTTPS URL detection
            file_type = preview_pane._detect_file_type("https://www.example.com")
            self.assertEqual(file_type, "url")

    def test_url_detection_http(self):
        """Test URL detection for HTTP URLs"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            preview_pane = PreviewPane(self.app, False)

            # Test HTTP URL detection
            file_type = preview_pane._detect_file_type("http://www.example.com")
            self.assertEqual(file_type, "url")

    def test_url_detection_ftp(self):
        """Test URL detection for FTP URLs"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            preview_pane = PreviewPane(self.app, False)

            # Test FTP URL detection
            file_type = preview_pane._detect_file_type("ftp://files.example.com/file.txt")
            self.assertEqual(file_type, "url")

    def test_regular_file_detection_still_works(self):
        """Test that regular file detection still works with URL support"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            preview_pane = PreviewPane(self.app, False)

            # Test regular file types still work
            self.assertEqual(preview_pane._detect_file_type("test.jpg"), "image")
            self.assertEqual(preview_pane._detect_file_type("test.pdf"), "pdf")
            self.assertEqual(preview_pane._detect_file_type("test.txt"), "text")
            self.assertEqual(preview_pane._detect_file_type("test.docx"), "docx")

    @patch('toga.WebView')
    def test_url_preview_creation(self, MockWebView):
        """Test URL preview creation using WebView"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            preview_pane = PreviewPane(self.app, False)
            preview_pane.content_container = MagicMock()

            # Mock WebView
            mock_webview = MagicMock()
            MockWebView.return_value = mock_webview

            # Test URL preview creation
            url = "https://www.example.com"
            preview_pane._create_url_preview(url)

            # Verify WebView was created with correct URL
            MockWebView.assert_called_once()
            call_args = MockWebView.call_args
            self.assertEqual(call_args[1]['url'], url)

            # Verify WebView was added to container
            preview_pane.content_container.add.assert_called_once_with(mock_webview)

    @patch('toga.WebView')
    def test_url_preview_error_handling(self, MockWebView):
        """Test URL preview error handling with fallback"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            preview_pane = PreviewPane(self.app, False)
            preview_pane.content_container = MagicMock()

            # Make WebView raise an exception
            MockWebView.side_effect = Exception("WebView not supported")

            # Test URL preview with error
            url = "https://www.example.com"
            preview_pane._create_url_preview(url)

            # Should fallback to MultilineTextInput
            self.assertTrue(preview_pane.content_container.add.called)
            # The fallback widget should be added
            added_widget = preview_pane.content_container.add.call_args[0][0]
            self.assertEqual(type(added_widget).__name__, 'MagicMock')  # Mock of MultilineTextInput

    def test_show_file_with_url(self):
        """Test show_file method with URL input"""
        with patch('fichero.windows.main.layout.preview_pane.BaseView.__init__'):
            from fichero.windows.main.layout.preview_pane import PreviewPane

            preview_pane = PreviewPane(self.app, False)
            preview_pane.content_container = MagicMock()
            preview_pane._create_url_preview = MagicMock()

            # Test showing a URL
            url = "https://www.example.com"
            preview_pane.show_file(url)

            # Verify URL type was detected and URL preview was created
            self.assertEqual(preview_pane.current_file_type, "url")
            preview_pane._create_url_preview.assert_called_once_with(url)


if __name__ == '__main__':
    unittest.main()