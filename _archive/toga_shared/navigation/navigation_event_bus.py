"""
Navigation Event Bus for Fichero

Simple event dispatcher that prevents loops by maintaining one-way data flow.
NavigationController emits events, UI components listen and update.
"""

import logging
import time
from typing import Dict, List, Callable, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NavigationEvent:
    """Navigation event data"""
    event_type: str
    data: Dict[str, Any]


class EventDeduplicator:
    """Prevents duplicate event processing within a time window"""

    def __init__(self, window_ms: int = 100):
        """
        Initialize event deduplicator.

        Args:
            window_ms: Time window in milliseconds to deduplicate events
        """
        self._last_events: Dict[str, float] = {}  # event_key -> timestamp
        self._window_ms = window_ms

    def should_process(self, event_type: str, event_data: Dict[str, Any]) -> bool:
        """
        Check if event should be processed or is a duplicate.

        Args:
            event_type: Type of event
            event_data: Event data dictionary

        Returns:
            True if event should be processed, False if it's a duplicate
        """
        # Create unique key from event type + critical data
        # For collection events, use collection_id as key
        collection_id = event_data.get('collection_id', '')
        item_id = event_data.get('item_id', '')
        key = f"{event_type}:{collection_id}:{item_id}"

        now = time.time() * 1000  # milliseconds

        last_time = self._last_events.get(key, 0)
        if now - last_time < self._window_ms:
            logger.debug(f"🔕 Dedup: Skipping duplicate event '{event_type}' (within {self._window_ms}ms window)")
            return False  # Duplicate, skip

        self._last_events[key] = now
        return True  # Process it


class NavigationEventBus:
    """Simple event bus for navigation events - prevents loops"""

    def __init__(self):
        """Initialize event bus"""
        self._listeners: Dict[str, List[Callable]] = {}
        self._event_id = 0
        self._deduplicator = EventDeduplicator(window_ms=100)  # 100ms dedup window
        logger.info("NavigationEventBus initialized")

    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to navigation events with deduplication"""
        if event_type not in self._listeners:
            self._listeners[event_type] = []

        # Prevent duplicate subscriptions
        if callback in self._listeners[event_type]:
            logger.debug(f"🔕 Preventing duplicate subscription to '{event_type}' events")
            return

        self._listeners[event_type].append(callback)
        logger.debug(f"✅ Subscribed to '{event_type}' events (total: {len(self._listeners[event_type])})")

    def unsubscribe(self, event_type: str, callback: Callable):
        """Unsubscribe from navigation events"""
        if event_type in self._listeners and callback in self._listeners[event_type]:
            self._listeners[event_type].remove(callback)
            logger.debug(f"Unsubscribed from '{event_type}' events")

    def emit(self, event_type: str, data: Dict[str, Any] = None):
        """Emit a navigation event with deduplication"""
        if data is None:
            data = {}

        # Check if this event is a duplicate (within time window)
        if not self._deduplicator.should_process(event_type, data):
            # Duplicate event - skip emitting
            return

        self._event_id += 1
        event = NavigationEvent(event_type=event_type, data=data)

        # Call all listeners for this event type
        listeners = self._listeners.get(event_type, [])

        # Warn if too many listeners (indicates potential duplicate subscription issue)
        if len(listeners) > 3:
            logger.warning(f"⚠️ {len(listeners)} listeners for '{event_type}' - possible duplicate subscriptions")

        logger.debug(f"📡 Emitting event #{self._event_id}: {event_type} (to {len(listeners)} listeners)")

        for listener in listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Error in event listener for {event_type}: {e}")

    def clear_all_listeners(self):
        """Clear all event listeners"""
        self._listeners.clear()
        logger.debug("All event listeners cleared")

    def get_listener_count(self) -> Dict[str, int]:
        """Get count of listeners for each event type"""
        return {event_type: len(listeners) for event_type, listeners in self._listeners.items()}


# Navigation event types
class NavigationEvents:
    """Constants for navigation event types"""

    # State change events
    STATE_CHANGED = "state_changed"
    NAVIGATION_UPDATED = "navigation_updated"

    # View events
    SHOW_LIBRARY = "show_library"
    SHOW_COLLECTION = "show_collection"
    SHOW_PREVIEW = "show_preview"
    SHOW_MODAL = "show_modal"
    VIEW_FOCUSED = "view_focused"  # Phase 3.1: Layout manager view focus events

    # Selection events
    SELECTION_CHANGED = "selection_changed"  # Emitted when selection changes in any view

    # UI events
    BACK_BUTTON_STATE_CHANGED = "back_button_state_changed"
    BREADCRUMBS_UPDATED = "breadcrumbs_updated"

    # Error events
    NAVIGATION_ERROR = "navigation_error"

    # Library state change events
    COLLECTION_ADDED = "collection_added"
    COLLECTION_DELETED = "collection_deleted"
    COLLECTION_UPDATED = "collection_updated"
    COLLECTION_ITEMS_CHANGED = "collection_items_changed"


# Global event bus instance
_event_bus: NavigationEventBus = None


def get_event_bus() -> NavigationEventBus:
    """Get the global navigation event bus"""
    global _event_bus
    if _event_bus is None:
        _event_bus = NavigationEventBus()
    return _event_bus


def emit_navigation_event(event_type: str, data: Dict[str, Any] = None):
    """Convenience function to emit navigation events"""
    get_event_bus().emit(event_type, data)


def subscribe_to_navigation(event_type: str, callback: Callable):
    """Convenience function to subscribe to navigation events"""
    get_event_bus().subscribe(event_type, callback)


def unsubscribe_from_navigation(event_type: str, callback: Callable):
    """Convenience function to unsubscribe from navigation events"""
    get_event_bus().unsubscribe(event_type, callback)