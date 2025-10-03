"""
Navigation Event Bus for Fichero

Simple event dispatcher that prevents loops by maintaining one-way data flow.
NavigationController emits events, UI components listen and update.
"""

import logging
from typing import Dict, List, Callable, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NavigationEvent:
    """Navigation event data"""
    event_type: str
    data: Dict[str, Any]


class NavigationEventBus:
    """Simple event bus for navigation events - prevents loops"""

    def __init__(self):
        """Initialize event bus"""
        self._listeners: Dict[str, List[Callable]] = {}
        self._event_id = 0
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
        """Emit a navigation event"""
        if data is None:
            data = {}

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

    # UI events
    BACK_BUTTON_STATE_CHANGED = "back_button_state_changed"
    BREADCRUMBS_UPDATED = "breadcrumbs_updated"

    # Error events
    NAVIGATION_ERROR = "navigation_error"


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