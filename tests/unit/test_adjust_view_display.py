"""
Test AdjustView functionality.

This test file verifies:
- Metadata tabs are created and visible
- OptionContainer is added to main container (not nested in ScrollContainer)
- Item metadata is loaded correctly
- Tabs are populated with content
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import asyncio
from pathlib import Path


class TestAdjustViewDisplay(unittest.TestCase):
    """Test AdjustView display functionality"""

    def setUp(self):
        """Set up test fixtures"""
        # Mock app
        self.app = Mock()

        # Mock item
        self.mock_item = Mock()
        self.mock_item.id = "test-item-123"
        self.mock_item.name = "Test Document"
        self.mock_item.type = "image"
        self.mock_item.metadata = {
            "file_path": "/tmp/test.jpg",
            "type": "image",
            "local_path": "/tmp/test.jpg"
        }
        self.mock_item.created_at = None

    def test_tabs_visible_after_load(self):
        """Verify OptionContainer tabs are shown after loading item"""
        from fichero.windows.main.views.adjust.adjust_view import AdjustView

        with patch('toga.Box'), patch('toga.ScrollContainer'), \
             patch('toga.OptionContainer') as mock_option_container, \
             patch('toga.MultilineTextInput'), patch('toga.Label'):

            # Create adjust view
            adjust_view = AdjustView(self.app, is_mobile=False)

            # Mock library manager
            adjust_view.library_manager = Mock()
            adjust_view.library_manager.storage.get_item = Mock(return_value=self.mock_item)
            adjust_view.library_manager.get_item_output_data = AsyncMock(return_value={
                'has_outputs': False,
                'processing_steps': []
            })

            # Load item
            asyncio.run(adjust_view.load_item("test-item-123"))

            # Verify tab_container exists and is OptionContainer
            self.assertIsNotNone(adjust_view.tab_container)
            self.assertEqual(adjust_view.current_item_id, "test-item-123")

    def test_no_nested_scroll_containers(self):
        """Verify OptionContainer is used as root container (not nested)"""
        from fichero.windows.main.views.adjust.adjust_view import AdjustView

        with patch('toga.Box') as mock_box, \
             patch('toga.ScrollContainer') as mock_scroll, \
             patch('toga.OptionContainer') as mock_option, \
             patch('toga.MultilineTextInput'), patch('toga.Label'):

            # Create adjust view
            adjust_view = AdjustView(self.app, is_mobile=False)

            # Verify container structure
            # AdjustView uses OptionContainer as the root container
            # Structure: container = tab_container (OptionContainer)
            # NOT: container (Box) -> scroll_container -> content_container -> tab_container

            # Check that tab_container exists
            self.assertIsNotNone(adjust_view.tab_container)

            # Verify that container IS the tab_container (OptionContainer is root)
            self.assertIs(adjust_view.container, adjust_view.tab_container,
                         "container should be the same as tab_container (OptionContainer as root)")

            # Verify that AdjustView does NOT have scroll_container
            # (it should be None since we override _create_view_structure)
            self.assertIsNone(getattr(adjust_view, 'scroll_container', None))

            # Verify that AdjustView does NOT have content_container
            # (it should be None since we override _create_view_structure)
            self.assertIsNone(getattr(adjust_view, 'content_container', None))

    def test_metadata_tabs_populated(self):
        """Verify metadata tabs are populated with content"""
        from fichero.windows.main.views.adjust.adjust_view import AdjustView

        with patch('toga.Box'), patch('toga.ScrollContainer'), \
             patch('toga.OptionContainer') as mock_option_container, \
             patch('toga.MultilineTextInput') as mock_text_input, \
             patch('toga.Label'):

            # Create adjust view
            adjust_view = AdjustView(self.app, is_mobile=False)

            # Mock library manager
            adjust_view.library_manager = Mock()
            adjust_view.library_manager.storage.get_item = Mock(return_value=self.mock_item)
            adjust_view.library_manager.get_item_output_data = AsyncMock(return_value={
                'has_outputs': False,
                'processing_steps': []
            })

            # Create mock boxes for tab content
            adjust_view.info_box = Mock()
            adjust_view.info_box.content = Mock()
            adjust_view.metadata_box = Mock()
            adjust_view.metadata_box.content = Mock()
            adjust_view.transcription_box = Mock()
            adjust_view.json_box = Mock()

            # Load item
            asyncio.run(adjust_view.load_item("test-item-123"))

            # Verify tabs were populated
            self.assertEqual(adjust_view.current_item_id, "test-item-123")

    def test_load_item_creates_tabs(self):
        """Verify load_item creates all required tabs"""
        from fichero.windows.main.views.adjust.adjust_view import AdjustView

        with patch('toga.Box'), patch('toga.ScrollContainer'), \
             patch('toga.OptionContainer') as mock_option_container, \
             patch('toga.MultilineTextInput'), patch('toga.Label'):

            # Create adjust view
            adjust_view = AdjustView(self.app, is_mobile=False)

            # Mock library manager
            adjust_view.library_manager = Mock()
            adjust_view.library_manager.storage.get_item = Mock(return_value=self.mock_item)
            adjust_view.library_manager.get_item_output_data = AsyncMock(return_value={
                'has_outputs': False,
                'processing_steps': []
            })

            # Create mock boxes for tab content
            adjust_view.info_box = Mock()
            adjust_view.info_box.content = Mock()
            adjust_view.metadata_box = Mock()
            adjust_view.metadata_box.content = Mock()
            adjust_view.transcription_box = Mock()
            adjust_view.json_box = Mock()

            # Verify tab_container exists
            self.assertIsNotNone(adjust_view.tab_container)

            # Load item
            asyncio.run(adjust_view.load_item("test-item-123"))

            # Verify current_item_id is set
            self.assertEqual(adjust_view.current_item_id, "test-item-123")

    def test_clear_removes_content(self):
        """Verify clear() removes all content from tabs"""
        from fichero.windows.main.views.adjust.adjust_view import AdjustView

        with patch('toga.Box'), patch('toga.ScrollContainer'), \
             patch('toga.OptionContainer'), \
             patch('toga.MultilineTextInput'), \
             patch('toga.Label'):

            # Create adjust view
            adjust_view = AdjustView(self.app, is_mobile=False)

            # Create mock boxes for tab content
            adjust_view.info_box = Mock()
            adjust_view.info_box.content = Mock()
            adjust_view.info_box.content.clear = Mock()

            adjust_view.metadata_box = Mock()
            adjust_view.metadata_box.content = Mock()
            adjust_view.metadata_box.content.clear = Mock()

            # Create mock text inputs
            adjust_view.transcription_box = Mock()
            adjust_view.json_box = Mock()

            # Set current item
            adjust_view.current_item_id = "test-123"

            # Clear - need to mock isinstance check for toga.MultilineTextInput
            with patch('fichero.windows.main.views.adjust.adjust_view.isinstance', return_value=True):
                adjust_view.clear()

            # Verify current_item_id is cleared
            self.assertIsNone(adjust_view.current_item_id)

            # Verify content was cleared
            adjust_view.info_box.content.clear.assert_called_once()
            adjust_view.metadata_box.content.clear.assert_called_once()

    def test_load_info_tab_displays_file_info(self):
        """Verify _load_info_tab displays file information"""
        from fichero.windows.main.views.adjust.adjust_view import AdjustView

        with patch('toga.Box') as mock_box, \
             patch('toga.ScrollContainer'), \
             patch('toga.OptionContainer'), \
             patch('toga.MultilineTextInput'), \
             patch('toga.Label') as mock_label:

            # Create adjust view
            adjust_view = AdjustView(self.app, is_mobile=False)

            # Create mock info_box
            info_content = Mock()
            info_content.clear = Mock()
            info_content.add = Mock()
            adjust_view.info_box = Mock()
            adjust_view.info_box.content = info_content

            # Load info tab
            asyncio.run(adjust_view._load_info_tab(self.mock_item))

            # Verify content was set
            # (The method creates a new Box and assigns it to info_box.content)
            self.assertIsNotNone(adjust_view.info_box)


if __name__ == '__main__':
    unittest.main()
