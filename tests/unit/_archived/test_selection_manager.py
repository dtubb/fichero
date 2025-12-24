"""
Test SelectionManager functionality.

This test file verifies:
- set_selection() stores selection correctly
- Metadata is attached to selection
- SELECTION_CHANGED event is emitted
- get_selection() returns correct data
- clear_selection() works
"""

import unittest
from unittest.mock import Mock, MagicMock, patch


class TestSelectionManager(unittest.TestCase):
    """Test SelectionManager functionality"""

    def setUp(self):
        """Set up test fixtures"""
        # Clear event bus before each test
        from fichero.shared.navigation.navigation_event_bus import get_event_bus
        import time
        event_bus = get_event_bus()
        event_bus.clear_all_listeners()
        # Wait to clear deduplication window
        time.sleep(0.15)

    def test_set_selection_with_metadata(self):
        """Verify set_selection stores selection and metadata correctly"""
        from fichero.shared.selection.selection_manager import SelectionManager

        manager = SelectionManager()

        # Set selection with metadata
        metadata = [
            {'item_id': 'item-1', 'name': 'File 1'},
            {'item_id': 'item-2', 'name': 'File 2'}
        ]
        manager.set_selection('collection', ['item-1', 'item-2'], metadata=metadata)

        # Verify selection is stored
        selection = manager.get_selection('collection')
        self.assertEqual(selection, ['item-1', 'item-2'])

        # Verify metadata is stored
        stored_metadata = manager.get_selection_metadata('collection')
        self.assertEqual(len(stored_metadata), 2)
        self.assertEqual(stored_metadata[0]['item_id'], 'item-1')
        self.assertEqual(stored_metadata[1]['item_id'], 'item-2')

    def test_metadata_has_item_id_key(self):
        """Verify metadata uses 'item_id' key, not 'id'"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.shared.navigation.navigation_event_bus import get_event_bus, NavigationEvents

        manager = SelectionManager()

        # Subscribe to events
        received_events = []
        def capture_event(event):
            received_events.append(event)

        get_event_bus().subscribe(NavigationEvents.SELECTION_CHANGED, capture_event)

        # Set selection with 'item_id' key
        metadata = [{'item_id': 'test-123', 'name': 'Test File'}]
        manager.set_selection('collection', ['test-123'], metadata=metadata)

        # Verify event metadata uses 'item_id'
        event = received_events[0]
        event_metadata = event.data['metadata'][0]

        self.assertIn('item_id', event_metadata)
        self.assertEqual(event_metadata['item_id'], 'test-123')

    def test_get_selection_returns_metadata(self):
        """Verify get_selection_metadata returns correct data"""
        from fichero.shared.selection.selection_manager import SelectionManager

        manager = SelectionManager()

        # Set selection with detailed metadata
        metadata = [{
            'item_id': 'item-456',
            'name': 'Document.pdf',
            'type': 'pdf',
            'size': 1024000,
            'path': '/tmp/document.pdf'
        }]
        manager.set_selection('collection', ['item-456'], metadata=metadata)

        # Get metadata
        retrieved = manager.get_selection_metadata('collection')

        # Verify all fields are present
        self.assertEqual(len(retrieved), 1)
        item_meta = retrieved[0]
        self.assertEqual(item_meta['item_id'], 'item-456')
        self.assertEqual(item_meta['name'], 'Document.pdf')
        self.assertEqual(item_meta['type'], 'pdf')
        self.assertEqual(item_meta['size'], 1024000)
        self.assertEqual(item_meta['path'], '/tmp/document.pdf')

    def test_clear_selection_emits_event(self):
        """Verify clear_selection emits SELECTION_CHANGED event"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.shared.navigation.navigation_event_bus import get_event_bus, NavigationEvents
        import time

        manager = SelectionManager()

        # Subscribe to events
        received_events = []
        def capture_event(event):
            received_events.append(event)

        get_event_bus().subscribe(NavigationEvents.SELECTION_CHANGED, capture_event)

        # Set selection first
        manager.set_selection('collection', ['item-1'])

        # Wait to clear deduplication window
        time.sleep(0.15)

        # Clear selection
        manager.clear_selection('collection')

        # Verify two events: set and clear
        self.assertEqual(len(received_events), 2)

        # Verify clear event
        clear_event = received_events[1]
        self.assertEqual(clear_event.data['count'], 0)
        self.assertEqual(len(clear_event.data['new_selection']), 0)

    def test_get_selection_returns_copy(self):
        """Verify get_selection returns a copy to prevent external mutation"""
        from fichero.shared.selection.selection_manager import SelectionManager

        manager = SelectionManager()

        # Set selection
        manager.set_selection('collection', ['item-1', 'item-2'])

        # Get selection
        selection1 = manager.get_selection('collection')
        selection2 = manager.get_selection('collection')

        # Modify one copy
        selection1.append('item-3')

        # Verify other copy is unchanged
        self.assertEqual(len(selection2), 2)

        # Verify internal state is unchanged
        internal = manager.get_selection('collection')
        self.assertEqual(len(internal), 2)

    def test_set_selection_emits_event(self):
        """Verify set_selection emits SELECTION_CHANGED event"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.shared.navigation.navigation_event_bus import get_event_bus, NavigationEvents

        manager = SelectionManager()

        # Subscribe to events
        received_events = []
        def capture_event(event):
            received_events.append(event)

        get_event_bus().subscribe(NavigationEvents.SELECTION_CHANGED, capture_event)

        # Set selection
        manager.set_selection('collection', ['item-1'])

        # Verify event was emitted
        self.assertEqual(len(received_events), 1)
        event = received_events[0]
        self.assertEqual(event.event_type, NavigationEvents.SELECTION_CHANGED)

    def test_selection_count_is_correct(self):
        """Verify get_selection_count returns correct count"""
        from fichero.shared.selection.selection_manager import SelectionManager

        manager = SelectionManager()

        # Empty selection
        self.assertEqual(manager.get_selection_count('collection'), 0)

        # Single item
        manager.set_selection('collection', ['item-1'])
        self.assertEqual(manager.get_selection_count('collection'), 1)

        # Multiple items
        manager.set_selection('collection', ['item-1', 'item-2', 'item-3'])
        self.assertEqual(manager.get_selection_count('collection'), 3)

        # Clear
        manager.clear_selection('collection')
        self.assertEqual(manager.get_selection_count('collection'), 0)

    def test_metadata_is_copied(self):
        """Verify metadata list is copied to prevent list mutation"""
        from fichero.shared.selection.selection_manager import SelectionManager

        manager = SelectionManager()

        # Set selection with metadata
        original_metadata = [{'item_id': 'item-1', 'name': 'Test'}]
        manager.set_selection('collection', ['item-1'], metadata=original_metadata)

        # Get metadata from manager
        stored_metadata = manager.get_selection_metadata('collection')

        # Modify the returned list by adding a new item
        stored_metadata.append({'item_id': 'item-2', 'name': 'Added'})

        # Get metadata again
        fresh_metadata = manager.get_selection_metadata('collection')

        # Verify the internal state is unchanged (only has 1 item, not 2)
        self.assertEqual(len(fresh_metadata), 1)
        self.assertEqual(fresh_metadata[0]['item_id'], 'item-1')

    def test_unchanged_selection_skips_event(self):
        """Verify setting same selection twice doesn't emit duplicate events"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.shared.navigation.navigation_event_bus import get_event_bus, NavigationEvents

        manager = SelectionManager()

        # Subscribe to events
        received_events = []
        def capture_event(event):
            received_events.append(event)

        get_event_bus().subscribe(NavigationEvents.SELECTION_CHANGED, capture_event)

        # Set selection
        manager.set_selection('collection', ['item-1'])
        self.assertEqual(len(received_events), 1)

        # Set same selection again
        manager.set_selection('collection', ['item-1'])

        # Should still only have 1 event (second call was skipped)
        self.assertEqual(len(received_events), 1)


if __name__ == '__main__':
    unittest.main()
