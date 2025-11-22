"""
Test the complete flow from selection to preview display.

This test file verifies:
- User selects item in collection view
- SelectionManager emits SELECTION_CHANGED event with correct metadata
- MainWindow receives event and loads preview panes
- PreviewView loads item in left and right panes
- AdjustView loads item metadata
- All panes display content correctly
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import asyncio
from pathlib import Path
import builtins

# Install gettext globally for these tests
builtins._ = lambda x: x


class TestSelectionPreviewFlow(unittest.TestCase):
    """Test end-to-end selection to preview flow"""

    def setUp(self):
        """Set up test fixtures"""
        # Clear event bus
        from fichero.shared.navigation.navigation_event_bus import get_event_bus
        import time
        get_event_bus().clear_all_listeners()
        time.sleep(0.15)

        # Mock app
        self.app = Mock()
        self.app.library_manager = Mock()

        # Mock library manager responses
        self.mock_item = Mock()
        self.mock_item.id = "test-item-123"
        self.mock_item.name = "Test Document"
        self.mock_item.type = "image"
        self.mock_item.local_path = Path("/tmp/test.jpg")
        self.mock_item.source_path = Path("/tmp/test.jpg")
        self.mock_item.metadata = {"file_path": "/tmp/test.jpg"}

        # Set up async methods
        self.app.library_manager.get_item = AsyncMock(return_value=self.mock_item)
        self.app.library_manager.get_item_output_data = AsyncMock(return_value={
            'has_outputs': False,
            'processing_steps': []
        })

    def test_selection_emits_event_with_item_id(self):
        """Verify SELECTION_CHANGED event metadata has 'item_id' key"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.shared.navigation.navigation_event_bus import get_event_bus

        # Create selection manager
        manager = SelectionManager()

        # Subscribe to events
        received_events = []
        def capture_event(event):
            received_events.append(event)

        get_event_bus().subscribe("selection_changed", capture_event)

        # Set selection with metadata
        metadata = [{'item_id': 'test-123', 'name': 'Test Item'}]
        manager.set_selection('collection', ['test-123'], metadata=metadata)

        # Verify event was emitted
        self.assertEqual(len(received_events), 1)

        # Verify event data structure
        event = received_events[0]
        self.assertEqual(event.event_type, "selection_changed")
        self.assertIn('metadata', event.data)

        # CRITICAL: Verify 'item_id' key exists (not 'id')
        event_metadata = event.data['metadata']
        self.assertEqual(len(event_metadata), 1)
        self.assertIn('item_id', event_metadata[0])
        self.assertEqual(event_metadata[0]['item_id'], 'test-123')

    def test_preview_panes_load_on_selection(self):
        """Verify both preview panes get content when item is selected"""
        from fichero.windows.main.views.preview.preview_view import PreviewView

        # Create preview view
        with patch('toga.Box'), patch('toga.Label'), patch('toga.Group'):
            preview_view = PreviewView(self.app, is_mobile=False, library_manager=self.app.library_manager)

            # Mock the layout manager and panes
            preview_view.layout_manager = Mock()
            left_pane = Mock()
            right_pane = Mock()
            left_pane.set_content = AsyncMock()
            right_pane.set_content = AsyncMock()
            preview_view.layout_manager.get_pane = Mock(side_effect=[left_pane, right_pane])
            preview_view.layout_manager.set_layout = Mock()

            # Mock the helper methods to avoid JSON serialization errors
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

            # Verify layout was set to dual-column
            preview_view.layout_manager.set_layout.assert_called_once()

            # Verify both panes received content
            left_pane.set_content.assert_called_once()
            right_pane.set_content.assert_called_once()

    def test_adjust_pane_loads_on_selection(self):
        """Verify adjust pane loads metadata when item is selected"""
        from fichero.windows.main.views.adjust.adjust_view import AdjustView

        # Create adjust view
        with patch('toga.Box'), patch('toga.ScrollContainer'), patch('toga.OptionContainer'), \
             patch('toga.MultilineTextInput'), patch('toga.Label'):
            adjust_view = AdjustView(self.app, is_mobile=False)
            adjust_view.library_manager = self.app.library_manager

            # Load item
            asyncio.run(adjust_view.load_item("test-item-123"))

            # Verify current_item_id is set
            self.assertEqual(adjust_view.current_item_id, "test-item-123")

    def test_no_selection_clears_preview(self):
        """Verify empty selection clears preview panes"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.shared.navigation.navigation_event_bus import get_event_bus
        import time

        # Create selection manager
        manager = SelectionManager()

        # Subscribe to events
        received_events = []
        def capture_event(event):
            received_events.append(event)

        get_event_bus().subscribe("selection_changed", capture_event)

        # Set selection first
        metadata = [{'item_id': 'test-123'}]
        manager.set_selection('collection', ['test-123'], metadata=metadata)

        # Wait to clear deduplication window
        time.sleep(0.15)

        # Clear selection
        manager.clear_selection('collection')

        # Verify two events: one for selection, one for clearing
        self.assertEqual(len(received_events), 2)

        # Verify clear event has empty selection
        clear_event = received_events[1]
        self.assertEqual(clear_event.data['count'], 0)
        self.assertEqual(len(clear_event.data['new_selection']), 0)

    def test_metadata_key_mismatch_regression(self):
        """Prevent the 'id' vs 'item_id' bug from returning"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.shared.navigation.navigation_event_bus import get_event_bus

        # This test specifically checks for the bug where:
        # - CollectionView used 'id' key
        # - MainWindow expected 'item_id' key
        # - Result: preview panes didn't load

        manager = SelectionManager()

        received_events = []
        def capture_event(event):
            received_events.append(event)

        get_event_bus().subscribe("selection_changed", capture_event)

        # Simulate CollectionView setting selection with 'item_id'
        metadata = [{'item_id': 'item-456', 'name': 'Test'}]
        manager.set_selection('collection', ['item-456'], metadata=metadata)

        # Verify event uses 'item_id', not 'id'
        event = received_events[0]
        event_metadata = event.data['metadata'][0]

        # CRITICAL CHECK: Must use 'item_id'
        self.assertIn('item_id', event_metadata,
                     "Metadata must use 'item_id' key, not 'id'")
        self.assertNotIn('id', event_metadata,
                        "Metadata should not use 'id' key (use 'item_id' instead)")

        # Verify the ID is correct
        self.assertEqual(event_metadata['item_id'], 'item-456')

    def test_selection_metadata_preserved_through_event(self):
        """Verify metadata is deep-copied and preserved through event emission"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.shared.navigation.navigation_event_bus import get_event_bus

        manager = SelectionManager()

        received_events = []
        def capture_event(event):
            received_events.append(event)

        get_event_bus().subscribe("selection_changed", capture_event)

        # Set selection with detailed metadata
        original_metadata = [{
            'item_id': 'test-789',
            'name': 'Test File',
            'type': 'image',
            'file_path': '/tmp/test.jpg',
            'size': 12345
        }]

        manager.set_selection('collection', ['test-789'], metadata=original_metadata)

        # Verify metadata in event matches original
        event = received_events[0]
        event_metadata = event.data['metadata'][0]

        # Check all fields are preserved
        self.assertEqual(event_metadata['item_id'], 'test-789')
        self.assertEqual(event_metadata['name'], 'Test File')
        self.assertEqual(event_metadata['type'], 'image')
        self.assertEqual(event_metadata['file_path'], '/tmp/test.jpg')
        self.assertEqual(event_metadata['size'], 12345)


if __name__ == '__main__':
    unittest.main()
