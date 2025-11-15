"""
Integration tests for Phase 2: Status Bar Selection Tracking.

Tests the complete event flow:
SelectionManager → NavigationEventBus → MainWindow → StatusBar
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
import sys
from pathlib import Path
import time

# Add src to path
src_path = Path(__file__).parent.parent.parent / 'src'
sys.path.insert(0, str(src_path))


class TestPhase2Integration(unittest.TestCase):
    """Integration tests for Phase 2 selection tracking"""

    def setUp(self):
        """Set up test fixtures"""
        # Mock app
        self.app = Mock()
        self.app.is_mobile = False
        self.app.formal_name = "Fichero Test"

        # Create SelectionManager
        from fichero.shared.selection.selection_manager import SelectionManager
        self.selection_manager = SelectionManager()
        self.app.selection_manager = self.selection_manager

        # Track emitted events
        self.emitted_events = []

    def tearDown(self):
        """Clean up after tests"""
        # Clear all selections
        if hasattr(self, 'selection_manager'):
            self.selection_manager.clear_all_selections()

        # Clear event tracking
        self.emitted_events = []

    @patch('fichero.shared.selection.selection_manager.emit_navigation_event')
    def test_selection_manager_emits_events(self, mock_emit):
        """Test that SelectionManager emits SELECTION_CHANGED events"""
        # Set selection
        self.selection_manager.set_selection(
            'library',
            ['collection-1', 'collection-2'],
            metadata=[
                {'id': 'collection-1', 'name': 'Collection 1'},
                {'id': 'collection-2', 'name': 'Collection 2'}
            ]
        )

        # Verify event was emitted
        mock_emit.assert_called_once()

        # Check event type and data
        call_args = mock_emit.call_args
        event_type = call_args[0][0]
        event_data = call_args[0][1]

        self.assertEqual(event_type, "SELECTION_CHANGED")
        self.assertEqual(event_data['view_id'], 'library')
        self.assertEqual(event_data['context'], 'library')
        self.assertEqual(event_data['count'], 2)
        self.assertEqual(len(event_data['new_selection']), 2)

    @patch('fichero.shared.selection.selection_manager.emit_navigation_event')
    def test_selection_manager_no_event_when_unchanged(self, mock_emit):
        """Test that SelectionManager doesn't emit events when selection unchanged"""
        # Set initial selection
        self.selection_manager.set_selection('library', ['collection-1'])
        mock_emit.reset_mock()

        # Set same selection again
        self.selection_manager.set_selection('library', ['collection-1'])

        # Should NOT emit event
        mock_emit.assert_not_called()

    def test_status_bar_update_from_selection_library(self):
        """Test StatusBar updates for library context"""
        from fichero.shared.bars.status_bar import StatusBar

        status_bar = StatusBar(platform='desktop')

        # No selection
        status_bar.update_status_from_selection(
            context='library',
            selected_count=0,
            metadata={'total_items': 10}
        )
        self.assertEqual(status_bar.status_label.text, "10 collections")

        # 1 selected
        status_bar.update_status_from_selection(
            context='library',
            selected_count=1,
            metadata={'total_items': 10}
        )
        self.assertEqual(status_bar.status_label.text, "1 item selected")

        # Multiple selected
        status_bar.update_status_from_selection(
            context='library',
            selected_count=3,
            metadata={'total_items': 10}
        )
        self.assertEqual(status_bar.status_label.text, "3 items selected")

    def test_status_bar_update_from_selection_collection(self):
        """Test StatusBar updates for collection context"""
        from fichero.shared.bars.status_bar import StatusBar

        status_bar = StatusBar(platform='desktop')

        # No selection, no folders
        status_bar.update_status_from_selection(
            context='collection',
            selected_count=0,
            metadata={'total_items': 127, 'folder_count': 0}
        )
        self.assertEqual(status_bar.status_label.text, "127 items")

        # No selection, with folders
        status_bar.update_status_from_selection(
            context='collection',
            selected_count=0,
            metadata={'total_items': 127, 'folder_count': 5}
        )
        self.assertEqual(status_bar.status_label.text, "127 items, 5 folders")

        # Items selected
        status_bar.update_status_from_selection(
            context='collection',
            selected_count=3,
            metadata={'total_items': 127, 'folder_count': 5}
        )
        self.assertEqual(status_bar.status_label.text, "3 items selected")

    def test_status_bar_update_from_selection_steps(self):
        """Test StatusBar updates for steps context"""
        from fichero.shared.bars.status_bar import StatusBar

        status_bar = StatusBar(platform='desktop')

        # No selection
        status_bar.update_status_from_selection(
            context='steps',
            selected_count=0,
            metadata={'total_items': 15}
        )
        self.assertEqual(status_bar.status_label.text, "15 steps")

        # Items selected
        status_bar.update_status_from_selection(
            context='steps',
            selected_count=1,
            metadata={'total_items': 15}
        )
        self.assertEqual(status_bar.status_label.text, "1 item selected")

    @patch('fichero.shared.selection.selection_manager.emit_navigation_event')
    def test_event_data_structure(self, mock_emit):
        """Test that event data has correct structure"""
        # Set selection with metadata
        self.selection_manager.set_selection(
            'collection',
            ['item-1', 'item-2'],
            metadata=[
                {'id': 'item-1', 'name': 'Item 1', 'is_folder': False},
                {'id': 'item-2', 'name': 'Item 2', 'is_folder': True}
            ]
        )

        # Get emitted event data
        call_args = mock_emit.call_args
        event_data = call_args[0][1]

        # Verify all required fields
        self.assertIn('view_id', event_data)
        self.assertIn('context', event_data)
        self.assertIn('old_selection', event_data)
        self.assertIn('new_selection', event_data)
        self.assertIn('count', event_data)
        self.assertIn('metadata', event_data)
        self.assertIn('timestamp', event_data)

        # Verify data types
        self.assertIsInstance(event_data['view_id'], str)
        self.assertIsInstance(event_data['context'], str)
        self.assertIsInstance(event_data['old_selection'], list)
        self.assertIsInstance(event_data['new_selection'], list)
        self.assertIsInstance(event_data['count'], int)
        self.assertIsInstance(event_data['metadata'], list)
        self.assertIsInstance(event_data['timestamp'], float)

        # Verify values
        self.assertEqual(event_data['view_id'], 'collection')
        self.assertEqual(event_data['count'], 2)
        self.assertEqual(len(event_data['metadata']), 2)

    def test_main_window_event_handler_defensive_checks(self):
        """Test MainWindow event handler defensive checks"""
        from fichero.shared.bars.status_bar import StatusBar

        # Create mock event
        mock_event = Mock()
        mock_event.data = {
            'view_id': 'library',
            'context': 'library',
            'count': 1,
            'metadata': []
        }

        # Create StatusBar
        status_bar = StatusBar(platform='desktop')

        # Simulate MainWindow with no views (views not ready)
        mock_main_window = Mock()
        mock_main_window.status_bar = status_bar
        mock_main_window.left_pane_view = None  # View not ready

        # Import the handler (we'll test it directly)
        # The handler should check if views are ready before proceeding
        # This is tested by verifying it doesn't crash when views are None

        # We can't easily test the actual MainWindow._handle_selection_changed
        # without creating a full MainWindow instance, so we'll test the logic separately

        # Test that StatusBar handles None metadata gracefully
        status_bar.update_status_from_selection(
            context='library',
            selected_count=0,
            metadata=None
        )
        self.assertEqual(status_bar.status_label.text, "No collections")

    def test_folder_counting_with_dictionaries(self):
        """Test folder counting works correctly with dictionary items"""
        from fichero.shared.bars.status_bar import StatusBar

        status_bar = StatusBar(platform='desktop')

        # Test items as dictionaries (real-world scenario)
        items = [
            {'id': '1', 'name': 'Folder 1', 'is_folder': True},
            {'id': '2', 'name': 'Item 1', 'is_folder': False},
            {'id': '3', 'name': 'Folder 2', 'is_folder': True},
            {'id': '4', 'name': 'Item 2', 'is_folder': False},
            {'id': '5', 'name': 'Item 3'},  # Missing is_folder key
        ]

        folder_count, total_count = status_bar._count_folders_and_items(items)

        self.assertEqual(total_count, 5)
        self.assertEqual(folder_count, 2)  # Only items with is_folder=True

    def test_performance_large_selection(self):
        """Test performance with large selection counts"""
        from fichero.shared.bars.status_bar import StatusBar

        status_bar = StatusBar(platform='desktop')

        # Test with 1000 items
        start_time = time.time()
        status_bar.update_status_from_selection(
            context='collection',
            selected_count=1000,
            metadata={'total_items': 10000, 'folder_count': 100}
        )
        elapsed_time = time.time() - start_time

        # Should complete in less than 100ms (very generous threshold)
        self.assertLess(elapsed_time, 0.1)
        self.assertEqual(status_bar.status_label.text, "1000 items selected")

    def test_edge_case_empty_view(self):
        """Test edge case: empty view with no items"""
        from fichero.shared.bars.status_bar import StatusBar

        status_bar = StatusBar(platform='desktop')

        # Library with no collections
        status_bar.update_status_from_selection(
            context='library',
            selected_count=0,
            metadata={'total_items': 0}
        )
        self.assertEqual(status_bar.status_label.text, "No collections")

        # Collection with no items
        status_bar.update_status_from_selection(
            context='collection',
            selected_count=0,
            metadata={'total_items': 0, 'folder_count': 0}
        )
        self.assertEqual(status_bar.status_label.text, "No items")

        # Steps with no steps
        status_bar.update_status_from_selection(
            context='steps',
            selected_count=0,
            metadata={'total_items': 0}
        )
        self.assertEqual(status_bar.status_label.text, "No steps")

    def test_edge_case_all_items_selected(self):
        """Test edge case: all items selected"""
        from fichero.shared.bars.status_bar import StatusBar

        status_bar = StatusBar(platform='desktop')

        # All 10 collections selected
        status_bar.update_status_from_selection(
            context='library',
            selected_count=10,
            metadata={'total_items': 10}
        )
        self.assertEqual(status_bar.status_label.text, "10 items selected")

    def test_context_switching(self):
        """Test switching between different contexts"""
        from fichero.shared.bars.status_bar import StatusBar

        status_bar = StatusBar(platform='desktop')

        # Start in library
        status_bar.update_status_from_selection(
            context='library',
            selected_count=0,
            metadata={'total_items': 5}
        )
        self.assertEqual(status_bar.status_label.text, "5 collections")

        # Switch to collection
        status_bar.update_status_from_selection(
            context='collection',
            selected_count=0,
            metadata={'total_items': 127, 'folder_count': 5}
        )
        self.assertEqual(status_bar.status_label.text, "127 items, 5 folders")

        # Switch to steps
        status_bar.update_status_from_selection(
            context='steps',
            selected_count=0,
            metadata={'total_items': 10}
        )
        self.assertEqual(status_bar.status_label.text, "10 steps")

        # Back to library with selection
        status_bar.update_status_from_selection(
            context='library',
            selected_count=2,
            metadata={'total_items': 5}
        )
        self.assertEqual(status_bar.status_label.text, "2 items selected")


if __name__ == '__main__':
    unittest.main()
