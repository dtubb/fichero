"""
Test event system integrity.

This test file verifies:
- NavigationEventBus delivers events to subscribers
- Event data includes correct keys ('item_id', 'metadata', etc.)
- No event loops or circular emissions
- Deduplication prevents duplicate events
- Event names use constants (NavigationEvents.SELECTION_CHANGED)
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import time


class TestEventSystem(unittest.TestCase):
    """Test event system integrity"""

    def setUp(self):
        """Set up test fixtures"""
        # Clear event bus before each test
        from fichero.shared.navigation.navigation_event_bus import get_event_bus
        event_bus = get_event_bus()
        event_bus.clear_all_listeners()

    def test_selection_changed_event_structure(self):
        """Verify SELECTION_CHANGED event has correct data format"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.shared.navigation.navigation_event_bus import get_event_bus, NavigationEvents

        manager = SelectionManager()

        # Subscribe to events
        received_events = []
        def capture_event(event):
            received_events.append(event)

        get_event_bus().subscribe(NavigationEvents.SELECTION_CHANGED, capture_event)

        # Set selection
        metadata = [{'item_id': 'test-123', 'name': 'Test'}]
        manager.set_selection('collection', ['test-123'], metadata=metadata)

        # Verify event structure
        self.assertEqual(len(received_events), 1)
        event = received_events[0]

        # Check required keys
        self.assertIn('view_id', event.data)
        self.assertIn('context', event.data)
        self.assertIn('old_selection', event.data)
        self.assertIn('new_selection', event.data)
        self.assertIn('count', event.data)
        self.assertIn('metadata', event.data)
        self.assertIn('timestamp', event.data)

        # Verify data types
        self.assertIsInstance(event.data['view_id'], str)
        self.assertIsInstance(event.data['new_selection'], list)
        self.assertIsInstance(event.data['count'], int)
        self.assertIsInstance(event.data['metadata'], list)
        self.assertIsInstance(event.data['timestamp'], float)

    def test_event_uses_constant_not_string(self):
        """Prevent hardcoded event name strings"""
        from fichero.shared.navigation.navigation_event_bus import NavigationEvents

        # Verify constants exist and are strings
        self.assertIsInstance(NavigationEvents.SELECTION_CHANGED, str)
        self.assertEqual(NavigationEvents.SELECTION_CHANGED, "selection_changed")

        # Verify other event constants
        self.assertIsInstance(NavigationEvents.STATE_CHANGED, str)
        self.assertIsInstance(NavigationEvents.SHOW_COLLECTION, str)
        self.assertIsInstance(NavigationEvents.SHOW_PREVIEW, str)

    def test_no_duplicate_events(self):
        """Verify deduplication prevents duplicate events"""
        from fichero.shared.navigation.navigation_event_bus import get_event_bus, emit_navigation_event

        event_bus = get_event_bus()

        # Subscribe to events
        received_events = []
        def capture_event(event):
            received_events.append(event)

        event_bus.subscribe("test_event", capture_event)

        # Emit same event multiple times rapidly
        for i in range(5):
            emit_navigation_event("test_event", {
                'collection_id': 'coll-123',
                'item_id': 'item-456'
            })

        # Due to deduplication (100ms window), should only receive 1 event
        # (or maybe 2 if timing is unlucky, but not all 5)
        self.assertLess(len(received_events), 5,
                       "Deduplication should prevent all 5 duplicate events")

    def test_subscriber_receives_event(self):
        """Verify subscribers receive emitted events"""
        from fichero.shared.navigation.navigation_event_bus import get_event_bus, emit_navigation_event

        event_bus = get_event_bus()

        # Subscribe to events
        received_events = []
        def capture_event(event):
            received_events.append(event)

        event_bus.subscribe("custom_event", capture_event)

        # Emit event
        emit_navigation_event("custom_event", {'test_data': 'value'})

        # Verify subscriber received event
        self.assertEqual(len(received_events), 1)
        event = received_events[0]
        self.assertEqual(event.event_type, "custom_event")
        self.assertEqual(event.data['test_data'], 'value')

    def test_multiple_subscribers_receive_events(self):
        """Verify all subscribers receive events"""
        from fichero.shared.navigation.navigation_event_bus import get_event_bus, emit_navigation_event

        event_bus = get_event_bus()

        # Create multiple subscribers
        received_1 = []
        received_2 = []
        received_3 = []

        def subscriber_1(event):
            received_1.append(event)

        def subscriber_2(event):
            received_2.append(event)

        def subscriber_3(event):
            received_3.append(event)

        # Subscribe all
        event_bus.subscribe("broadcast_event", subscriber_1)
        event_bus.subscribe("broadcast_event", subscriber_2)
        event_bus.subscribe("broadcast_event", subscriber_3)

        # Emit event
        emit_navigation_event("broadcast_event", {'message': 'Hello'})

        # Verify all received
        self.assertEqual(len(received_1), 1)
        self.assertEqual(len(received_2), 1)
        self.assertEqual(len(received_3), 1)

    def test_no_circular_event_emission(self):
        """Verify event handlers don't create circular event loops"""
        from fichero.shared.navigation.navigation_event_bus import get_event_bus, emit_navigation_event

        event_bus = get_event_bus()

        # Track event count
        event_count = [0]
        max_events = 10

        def potentially_circular_handler(event):
            event_count[0] += 1

            # Stop after max_events to prevent infinite loop
            if event_count[0] >= max_events:
                return

            # Try to emit another event (this could cause a loop)
            # But deduplication should prevent it
            emit_navigation_event("circular_test", {'iteration': event_count[0]})

        event_bus.subscribe("circular_test", potentially_circular_handler)

        # Emit initial event
        emit_navigation_event("circular_test", {'iteration': 0})

        # Due to deduplication, should not get max_events calls
        self.assertLess(event_count[0], max_events,
                       "Deduplication should prevent circular event loops")

    def test_unsubscribe_stops_event_delivery(self):
        """Verify unsubscribing stops event delivery"""
        from fichero.shared.navigation.navigation_event_bus import get_event_bus, emit_navigation_event

        event_bus = get_event_bus()

        # Subscribe to events
        received_events = []
        def capture_event(event):
            received_events.append(event)

        event_bus.subscribe("unsub_test", capture_event)

        # Emit event
        emit_navigation_event("unsub_test", {'phase': 1})
        self.assertEqual(len(received_events), 1)

        # Unsubscribe
        event_bus.unsubscribe("unsub_test", capture_event)

        # Wait to clear deduplication window
        time.sleep(0.2)

        # Emit another event
        emit_navigation_event("unsub_test", {'phase': 2})

        # Should still only have 1 event (unsubscribed before second)
        self.assertEqual(len(received_events), 1)


if __name__ == '__main__':
    unittest.main()
