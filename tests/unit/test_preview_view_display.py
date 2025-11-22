"""
Test PreviewView functionality.

This test file verifies:
- Left pane displays image for unprocessed items
- Right pane displays metadata when no transcription exists
- Right pane displays transcription when available
- Dual-column layout works correctly
- Content updates when item changes
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import asyncio
from pathlib import Path
import tempfile
import json
import builtins

# Install gettext globally for these tests
builtins._ = lambda x: x


class TestPreviewViewDisplay(unittest.TestCase):
    """Test PreviewView display functionality"""

    def setUp(self):
        """Set up test fixtures"""
        # Mock app
        self.app = Mock()
        self.app.library_manager = Mock()

        # Mock item
        self.mock_item = Mock()
        self.mock_item.id = "test-item-123"
        self.mock_item.name = "Test Document"
        self.mock_item.type = "image"
        self.mock_item.local_path = Path("/tmp/test.jpg")
        self.mock_item.source_path = Path("/tmp/test.jpg")
        self.mock_item.metadata = {"file_path": "/tmp/test.jpg"}
        self.mock_item.created_at = None
        self.mock_item.updated_at = None

        # Set up async methods
        self.app.library_manager.get_item = AsyncMock(return_value=self.mock_item)
        self.app.library_manager.get_item_output_data = AsyncMock(return_value={
            'has_outputs': False,
            'processing_steps': []
        })

    def test_left_pane_shows_original_image(self):
        """Verify left pane displays original image for unprocessed items"""
        from fichero.windows.main.views.preview.preview_view import PreviewView

        with patch('toga.Box'), patch('toga.Label'), patch('toga.Group'):
            preview_view = PreviewView(self.app, is_mobile=False, library_manager=self.app.library_manager)

            # Mock layout manager
            preview_view.layout_manager = Mock()
            left_pane = Mock()
            left_pane.set_content = AsyncMock()
            preview_view.layout_manager.get_pane = Mock(return_value=left_pane)
            preview_view.layout_manager.set_layout = Mock()

            # Mock _get_latest_output to return original file
            async def mock_get_latest_output(item_id, output_data=None):
                return {
                    'file_path': Path("/tmp/test.jpg"),
                    'file_type': 'image',
                    'step_name': 'Original',
                    'tool_name': 'original'
                }

            preview_view._get_latest_output = mock_get_latest_output

            # Load item
            asyncio.run(preview_view.load_item("test-item-123"))

            # Verify left pane was set with image content
            left_pane.set_content.assert_called_once()
            call_args = left_pane.set_content.call_args
            self.assertIn('file_path', call_args.kwargs)
            self.assertEqual(call_args.kwargs['file_type'], 'image')

    def test_right_pane_shows_metadata_when_no_transcription(self):
        """Verify right pane shows metadata when no transcription exists"""
        from fichero.windows.main.views.preview.preview_view import PreviewView

        with patch('toga.Box'), patch('toga.Label'), patch('toga.Group'):
            preview_view = PreviewView(self.app, is_mobile=False, library_manager=self.app.library_manager)

            # Mock layout manager
            preview_view.layout_manager = Mock()
            left_pane = Mock()
            right_pane = Mock()
            left_pane.set_content = AsyncMock()
            right_pane.set_content = AsyncMock()
            preview_view.layout_manager.get_pane = Mock(side_effect=[left_pane, right_pane])
            preview_view.layout_manager.set_layout = Mock()

            # Mock helper methods
            preview_view._get_latest_output = AsyncMock(return_value={
                'file_path': Path("/tmp/test.jpg"),
                'file_type': 'image',
                'step_name': 'Original',
                'tool_name': 'original'
            })
            preview_view._get_transcription_text = AsyncMock(return_value=None)
            preview_view._get_item_metadata_from_backend = AsyncMock(return_value={
                'item_info': {'name': 'Test', 'type': 'image'}
            })

            # Load item
            asyncio.run(preview_view.load_item("test-item-123"))

            # Verify right pane was set with JSON metadata content
            right_pane.set_content.assert_called_once()
            call_args = right_pane.set_content.call_args
            self.assertEqual(call_args.kwargs['file_type'], 'json')

    def test_right_pane_shows_transcription_when_available(self):
        """Verify right pane displays transcription when available"""
        from fichero.windows.main.views.preview.preview_view import PreviewView

        with patch('toga.Box'), patch('toga.Label'), patch('toga.Group'):
            preview_view = PreviewView(self.app, is_mobile=False, library_manager=self.app.library_manager)

            # Mock layout manager
            preview_view.layout_manager = Mock()
            left_pane = Mock()
            right_pane = Mock()
            left_pane.set_content = AsyncMock()
            right_pane.set_content = AsyncMock()
            preview_view.layout_manager.get_pane = Mock(side_effect=[left_pane, right_pane])
            preview_view.layout_manager.set_layout = Mock()

            # Mock helper methods
            preview_view._get_latest_output = AsyncMock(return_value={
                'file_path': Path("/tmp/test.jpg"),
                'file_type': 'image',
                'step_name': 'Original',
                'tool_name': 'original'
            })

            # Create temporary transcription file
            temp_file = Path(tempfile.gettempdir()) / "test_transcription.txt"
            temp_file.write_text("This is a test transcription")

            preview_view._get_transcription_text = AsyncMock(return_value=temp_file)

            # Load item
            asyncio.run(preview_view.load_item("test-item-123"))

            # Verify right pane was set with text content
            right_pane.set_content.assert_called_once()
            call_args = right_pane.set_content.call_args
            self.assertEqual(call_args.kwargs['file_type'], 'text')

            # Clean up
            if temp_file.exists():
                temp_file.unlink()

    def test_load_item_updates_both_panes(self):
        """Verify load_item updates both left and right panes"""
        from fichero.windows.main.views.preview.preview_view import PreviewView

        with patch('toga.Box'), patch('toga.Label'), patch('toga.Group'):
            preview_view = PreviewView(self.app, is_mobile=False, library_manager=self.app.library_manager)

            # Mock layout manager
            preview_view.layout_manager = Mock()
            left_pane = Mock()
            right_pane = Mock()
            left_pane.set_content = AsyncMock()
            right_pane.set_content = AsyncMock()

            # Track call order
            call_count = [0]
            panes = [left_pane, right_pane]
            def get_pane_side_effect(index):
                result = panes[call_count[0]]
                call_count[0] += 1
                return result

            preview_view.layout_manager.get_pane = Mock(side_effect=get_pane_side_effect)
            preview_view.layout_manager.set_layout = Mock()

            # Mock helper methods
            preview_view._get_latest_output = AsyncMock(return_value={
                'file_path': Path("/tmp/test.jpg"),
                'file_type': 'image',
                'step_name': 'Original',
                'tool_name': 'original'
            })
            preview_view._get_transcription_text = AsyncMock(return_value=None)
            preview_view._get_item_metadata_from_backend = AsyncMock(return_value={})

            # Load item
            asyncio.run(preview_view.load_item("test-item-123"))

            # Verify both panes were updated
            left_pane.set_content.assert_called_once()
            right_pane.set_content.assert_called_once()

    def test_dual_column_layout_always_used(self):
        """Verify dual-column layout is always used regardless of processing status"""
        from fichero.windows.main.views.preview.preview_view import PreviewView
        from fichero.windows.main.views.preview.layout_manager import LayoutType

        with patch('toga.Box'), patch('toga.Label'), patch('toga.Group'):
            preview_view = PreviewView(self.app, is_mobile=False, library_manager=self.app.library_manager)

            # Mock layout manager
            preview_view.layout_manager = Mock()
            left_pane = Mock()
            right_pane = Mock()
            left_pane.set_content = AsyncMock()
            right_pane.set_content = AsyncMock()
            preview_view.layout_manager.get_pane = Mock(side_effect=[left_pane, right_pane])
            preview_view.layout_manager.set_layout = Mock()

            # Mock helper methods
            preview_view._get_latest_output = AsyncMock(return_value={
                'file_path': Path("/tmp/test.jpg"),
                'file_type': 'image',
                'step_name': 'Original',
                'tool_name': 'original'
            })
            preview_view._get_transcription_text = AsyncMock(return_value=None)
            preview_view._get_item_metadata_from_backend = AsyncMock(return_value={})

            # Load item
            asyncio.run(preview_view.load_item("test-item-123"))

            # Verify set_layout was called with DUAL_COMPARE
            preview_view.layout_manager.set_layout.assert_called_once()
            call_args = preview_view.layout_manager.set_layout.call_args
            # The layout type should be DUAL_COMPARE
            self.assertEqual(str(call_args[0][0]), "LayoutType.DUAL_COMPARE")

    def test_content_updates_on_item_change(self):
        """Verify content updates when switching between items"""
        from fichero.windows.main.views.preview.preview_view import PreviewView

        with patch('toga.Box'), patch('toga.Label'), patch('toga.Group'):
            preview_view = PreviewView(self.app, is_mobile=False, library_manager=self.app.library_manager)

            # Mock layout manager
            preview_view.layout_manager = Mock()
            left_pane = Mock()
            right_pane = Mock()
            left_pane.set_content = AsyncMock()
            right_pane.set_content = AsyncMock()
            preview_view.layout_manager.get_pane = Mock(side_effect=[left_pane, right_pane] * 2)
            preview_view.layout_manager.set_layout = Mock()

            # Mock helper methods
            preview_view._get_latest_output = AsyncMock(return_value={
                'file_path': Path("/tmp/test.jpg"),
                'file_type': 'image',
                'step_name': 'Original',
                'tool_name': 'original'
            })
            preview_view._get_transcription_text = AsyncMock(return_value=None)
            preview_view._get_item_metadata_from_backend = AsyncMock(return_value={})

            # Load first item
            asyncio.run(preview_view.load_item("item-1"))
            self.assertEqual(preview_view.current_item_id, "item-1")

            # Load second item
            asyncio.run(preview_view.load_item("item-2"))
            self.assertEqual(preview_view.current_item_id, "item-2")

            # Verify panes were updated twice (once for each item)
            self.assertEqual(left_pane.set_content.call_count, 2)
            self.assertEqual(right_pane.set_content.call_count, 2)


if __name__ == '__main__':
    unittest.main()
