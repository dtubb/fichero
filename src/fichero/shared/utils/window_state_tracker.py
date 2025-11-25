"""
WindowStateTracker - Cross-platform window state tracking with native macOS support.

On macOS: Uses NSWindow frame/position APIs via Rubicon-ObjC for accurate tracking
On other platforms: Uses Toga's standard window properties (best-effort)
On mobile (iOS/Android): Window tracking is disabled (single-window apps)

Features:
- Track window position, size, visibility, and minimized state
- Automatic save/restore of window states across sessions
- Support for multiple windows with unique identifiers
- Native macOS notifications for real-time state updates
- Graceful fallback for non-macOS platforms
"""

import sys
import logging
import weakref
from typing import Dict, Optional, Any, Callable
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# Platform detection
IS_DARWIN = sys.platform == 'darwin'
IS_MOBILE = any(x in sys.platform for x in ['ios', 'android', 'iphone'])
PLATFORM_SUPPORTED = IS_DARWIN and not IS_MOBILE
RUBICON_AVAILABLE = False

# ObjC classes loaded lazily to avoid issues when AppKit isn't available
_objc_classes_loaded = False
_NSNotificationCenter = None
_NSScreen = None

if PLATFORM_SUPPORTED:
    try:
        from rubicon.objc import ObjCClass, objc_method, NSObject, SEL
        from rubicon.objc.runtime import objc_id
        RUBICON_AVAILABLE = True
        logger.info("Rubicon-ObjC available - native window state tracking enabled")
    except ImportError as e:
        logger.warning(f"Rubicon-ObjC not available: {e}")


def _load_objc_classes():
    """Lazily load ObjC classes when first needed."""
    global _objc_classes_loaded, _NSNotificationCenter, _NSScreen

    if _objc_classes_loaded or not RUBICON_AVAILABLE:
        return

    try:
        _NSNotificationCenter = ObjCClass('NSNotificationCenter')
        _NSScreen = ObjCClass('NSScreen')
        _objc_classes_loaded = True
        logger.debug("Loaded ObjC classes for window state tracking")
    except Exception as e:
        logger.warning(f"Failed to load ObjC classes: {e}")


@dataclass
class WindowState:
    """Snapshot of a window's state for persistence."""
    x: int
    y: int
    width: int
    height: int
    is_visible: bool = True
    is_minimized: bool = False
    display_id: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'WindowState':
        """Create from dictionary (e.g., from JSON)."""
        return cls(
            x=data.get('x', 0),
            y=data.get('y', 0),
            width=data.get('width', 800),
            height=data.get('height', 600),
            is_visible=data.get('is_visible', True),
            is_minimized=data.get('is_minimized', False),
            display_id=data.get('display_id'),
        )


# Module-level observer class (created once)
_WindowObserver = None

# Module-level storage for observer callbacks and window mappings
# These must be at module level because Rubicon's NSObject subclass
# doesn't properly support Python class-level dict attributes
_observer_callbacks: Dict[str, Callable] = {}
_observer_window_ids: Dict[int, str] = {}  # NSWindow hash -> window_id

def _handle_window_notification(notification, event_type: str):
    """
    Module-level handler for window notifications.

    This must be at module level because Rubicon's NSObject subclass
    can only call @objc_method decorated methods, not regular Python methods.
    """
    try:
        ns_window = notification.object
        window_hash = hash(ns_window)

        window_id = _observer_window_ids.get(window_hash)
        if window_id and window_id in _observer_callbacks:
            callback = _observer_callbacks[window_id]
            callback(window_id, event_type)

    except Exception as e:
        logger.error(f"Error handling window notification: {e}")


if RUBICON_AVAILABLE:
    class WindowObserver(NSObject):
        """
        NSObject subclass to observe NSWindow notifications.

        Handles:
        - NSWindowDidResizeNotification
        - NSWindowDidMoveNotification
        - NSWindowDidMiniaturizeNotification
        - NSWindowDidDeminiaturizeNotification

        Note: All actual handling is done via module-level function because
        Rubicon NSObject subclasses can only call @objc_method methods.
        """

        @objc_method
        def windowDidResize_(self, notification):
            """Handle window resize notification."""
            _handle_window_notification(notification, 'resize')

        @objc_method
        def windowDidMove_(self, notification):
            """Handle window move notification."""
            _handle_window_notification(notification, 'move')

        @objc_method
        def windowDidMiniaturize_(self, notification):
            """Handle window minimize notification."""
            _handle_window_notification(notification, 'minimize')

        @objc_method
        def windowDidDeminiaturize_(self, notification):
            """Handle window restore from minimize notification."""
            _handle_window_notification(notification, 'deminiaturize')

        @objc_method
        def windowDidEndLiveResize_(self, notification):
            """Handle end of live resize (drag resize)."""
            _handle_window_notification(notification, 'end_live_resize')

    _WindowObserver = WindowObserver


class WindowStateTracker:
    """
    Tracks and restores window state across sessions.

    Usage:
        tracker = WindowStateTracker(state_manager)
        tracker.register_window("main", main_window)
        tracker.register_window("inspector", inspector_window)

        # On shutdown:
        tracker.save_all_states()

        # On startup (after window creation):
        tracker.restore_window_state("main", main_window)
    """

    def __init__(self, state_manager, on_state_change: Optional[Callable] = None):
        """
        Initialize the window state tracker.

        Args:
            state_manager: The StateManager instance for persistence
            on_state_change: Optional callback when any window state changes
        """
        self.state_manager = state_manager
        self.on_state_change = on_state_change

        # Tracked windows: window_id -> toga.Window (weak reference)
        self._tracked_windows: Dict[str, weakref.ref] = {}

        # Observer instance (macOS only)
        self._observer = None
        if RUBICON_AVAILABLE:
            self._observer = _WindowObserver.alloc().init()

    def register_window(self, window_id: str, window, restore: bool = True):
        """
        Register a window for state tracking.

        Args:
            window_id: Unique identifier for the window (e.g., "main", "inspector")
            window: The Toga window instance
            restore: If True, immediately restore saved state (default True)
        """
        if IS_MOBILE:
            logger.debug(f"Skipping window registration on mobile: {window_id}")
            return

        logger.info(f"Registering window for state tracking: {window_id}")

        # Store weak reference to window
        self._tracked_windows[window_id] = weakref.ref(window)

        # Set up native observers on macOS
        if RUBICON_AVAILABLE and hasattr(window, '_impl') and hasattr(window._impl, 'native'):
            self._setup_native_observers(window_id, window)

        # Restore saved state if requested
        if restore:
            self.restore_window_state(window_id, window)

    def unregister_window(self, window_id: str):
        """
        Unregister a window from state tracking.

        Args:
            window_id: The window identifier to unregister
        """
        if window_id in self._tracked_windows:
            # Remove native observers on macOS
            if RUBICON_AVAILABLE and self._observer:
                self._remove_native_observers(window_id)

            del self._tracked_windows[window_id]
            logger.debug(f"Unregistered window: {window_id}")

    def _setup_native_observers(self, window_id: str, window):
        """Set up NSWindow notification observers for real-time tracking."""
        if not RUBICON_AVAILABLE or not self._observer:
            return

        # Lazily load ObjC classes
        _load_objc_classes()
        if not _NSNotificationCenter:
            return

        try:
            native_window = window._impl.native
            window_hash = hash(native_window)

            # Store mapping and callback
            _observer_window_ids[window_hash] = window_id
            _observer_callbacks[window_id] = self._on_window_event

            # Get notification center
            center = _NSNotificationCenter.defaultCenter

            # Register for notifications
            # Note: Using string names because we can't easily get the NSString constants
            center.addObserver_selector_name_object_(
                self._observer,
                SEL("windowDidResize:"),
                "NSWindowDidResizeNotification",
                native_window
            )
            center.addObserver_selector_name_object_(
                self._observer,
                SEL("windowDidMove:"),
                "NSWindowDidMoveNotification",
                native_window
            )
            center.addObserver_selector_name_object_(
                self._observer,
                SEL("windowDidMiniaturize:"),
                "NSWindowDidMiniaturizeNotification",
                native_window
            )
            center.addObserver_selector_name_object_(
                self._observer,
                SEL("windowDidDeminiaturize:"),
                "NSWindowDidDeminiaturizeNotification",
                native_window
            )
            # End of live resize (fires after drag-resize or zoom)
            center.addObserver_selector_name_object_(
                self._observer,
                SEL("windowDidEndLiveResize:"),
                "NSWindowDidEndLiveResizeNotification",
                native_window
            )

            logger.debug(f"Set up native observers for window: {window_id}")

        except Exception as e:
            logger.error(f"Failed to set up native observers for {window_id}: {e}")

    def _remove_native_observers(self, window_id: str):
        """Remove NSWindow notification observers."""
        if not RUBICON_AVAILABLE or not self._observer:
            return

        # Lazily load ObjC classes
        _load_objc_classes()
        if not _NSNotificationCenter:
            return

        try:
            window_ref = self._tracked_windows.get(window_id)
            if not window_ref:
                return

            window = window_ref()
            if not window or not hasattr(window, '_impl'):
                return

            native_window = window._impl.native
            window_hash = hash(native_window)

            # Remove from mappings
            _observer_window_ids.pop(window_hash, None)
            _observer_callbacks.pop(window_id, None)

            # Remove observer
            center = _NSNotificationCenter.defaultCenter
            center.removeObserver_name_object_(
                self._observer,
                None,  # All notifications
                native_window
            )

        except Exception as e:
            logger.error(f"Failed to remove native observers for {window_id}: {e}")

    def _on_window_event(self, window_id: str, event_type: str):
        """Handle window state change events."""
        logger.debug(f"Window event: {window_id} - {event_type}")

        # Auto-save state on significant events
        # These events indicate the window has finished a position/size change
        auto_save_events = {'move', 'end_live_resize', 'deminiaturize'}
        if event_type in auto_save_events:
            try:
                self.save_window_state(window_id)
                logger.debug(f"Auto-saved window state for {window_id} after {event_type}")
            except Exception as e:
                logger.error(f"Failed to auto-save window state: {e}")

        # Notify callback if set
        if self.on_state_change:
            try:
                self.on_state_change(window_id, event_type)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")

    def get_window_state(self, window_id: str) -> Optional[WindowState]:
        """
        Get current state of a tracked window.

        Args:
            window_id: The window identifier

        Returns:
            WindowState if window is tracked and accessible, None otherwise
        """
        window_ref = self._tracked_windows.get(window_id)
        if not window_ref:
            return None

        window = window_ref()
        if not window:
            # Window was garbage collected
            del self._tracked_windows[window_id]
            return None

        if RUBICON_AVAILABLE and hasattr(window, '_impl') and hasattr(window._impl, 'native'):
            return self._get_native_state(window)
        else:
            return self._get_toga_state(window)

    def _get_native_state(self, window) -> WindowState:
        """Get window state via NSWindow APIs."""
        try:
            native = window._impl.native

            # Use NSWindow's frame method which returns CGRect
            # In Rubicon, we can call frameForContentRect or just get frame
            frame = native.frame

            # Rubicon CGRect is a ctypes Structure with origin and size
            # Access the underlying values directly
            from rubicon.objc.types import CGRect

            # The frame should be a CGRect struct
            if isinstance(frame, CGRect):
                x = frame.origin.x
                y = frame.origin.y
                width = frame.size.width
                height = frame.size.height
            else:
                # Try attribute access
                x = frame.origin.x
                y = frame.origin.y
                width = frame.size.width
                height = frame.size.height

            # Ensure we have Python floats
            x = float(x)
            y = float(y)
            width = float(width)
            height = float(height)

            # macOS uses bottom-left origin, but we want top-left for consistency
            # Get screen height to convert coordinate system
            screen = native.screen
            if screen:
                screen_frame = screen.frame
                screen_height = float(screen_frame.size.height)
                # Convert from bottom-left to top-left origin
                # y_top = screen_height - y_bottom - window_height
                y = screen_height - y - height

            # Get display ID if available
            display_id = None
            if screen:
                try:
                    desc = screen.deviceDescription
                    if desc:
                        screen_number = desc.objectForKey_("NSScreenNumber")
                        if screen_number and hasattr(screen_number, 'intValue'):
                            display_id = int(screen_number.intValue)
                except Exception:
                    pass

            logger.info(f"Got native state: x={int(x)}, y={int(y)}, w={int(width)}, h={int(height)}")

            return WindowState(
                x=int(x),
                y=int(y),
                width=int(width),
                height=int(height),
                is_visible=bool(native.isVisible),
                is_minimized=bool(native.isMiniaturized),
                display_id=display_id,
            )

        except Exception as e:
            logger.error(f"Failed to get native window state: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._get_toga_state(window)

    def _get_toga_state(self, window) -> WindowState:
        """Fallback: Get window state via Toga APIs."""
        try:
            # Toga window properties - be careful with None values
            position = getattr(window, 'position', None)
            size = getattr(window, 'size', None)
            visible = getattr(window, 'visible', True)

            # Extract position values carefully
            if position is not None:
                try:
                    x = int(position[0]) if position[0] is not None else 100
                    y = int(position[1]) if position[1] is not None else 100
                except (TypeError, IndexError):
                    x, y = 100, 100
            else:
                x, y = 100, 100

            # Extract size values carefully
            if size is not None:
                try:
                    width = int(size[0]) if size[0] is not None else 800
                    height = int(size[1]) if size[1] is not None else 600
                except (TypeError, IndexError):
                    width, height = 800, 600
            else:
                width, height = 800, 600

            logger.info(f"Got Toga state: x={x}, y={y}, w={width}, h={height}")

            return WindowState(
                x=x,
                y=y,
                width=width,
                height=height,
                is_visible=bool(visible),
                is_minimized=False,  # Can't detect via Toga
            )

        except Exception as e:
            logger.error(f"Failed to get Toga window state: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return WindowState(x=100, y=100, width=800, height=600)

    def restore_window_state(self, window_id: str, window):
        """
        Restore a window's saved state.

        Args:
            window_id: The window identifier
            window: The Toga window instance
        """
        if IS_MOBILE:
            return

        saved = self.state_manager.get_window_state(window_id)
        if not saved:
            logger.info(f"No saved state for window: {window_id}")
            return

        logger.info(f"Restoring window state for: {window_id}")
        logger.info(f"  Saved state: x={saved.get('x')}, y={saved.get('y')}, "
                    f"w={saved.get('width')}, h={saved.get('height')}")

        # Validate position is on screen
        if not self._is_position_valid(saved):
            logger.warning(f"Saved position invalid for {window_id}, using defaults")
            return

        if RUBICON_AVAILABLE and hasattr(window, '_impl') and hasattr(window._impl, 'native'):
            self._restore_native_state(window, saved)
        else:
            self._restore_toga_state(window, saved)

    def _is_position_valid(self, state: dict) -> bool:
        """Check if saved position is on a visible screen."""
        x = state.get('x', 0)
        y = state.get('y', 0)
        width = state.get('width', 800)
        height = state.get('height', 600)

        # Minimum size validation
        if width < 200 or height < 200:
            return False

        # Lazily load ObjC classes
        if RUBICON_AVAILABLE:
            _load_objc_classes()

        if RUBICON_AVAILABLE and _NSScreen:
            try:
                # Check against all available screens
                screens = _NSScreen.screens
                for screen in screens:
                    frame = screen.frame
                    # Allow some tolerance (-100px) for windows partially off screen
                    if (x + width > frame.origin.x - 100 and
                        x < frame.origin.x + frame.size.width + 100 and
                        y + height > frame.origin.y - 100 and
                        y < frame.origin.y + frame.size.height + 100):
                        return True
                return False

            except Exception as e:
                logger.warning(f"Screen validation failed: {e}")
                return True  # Allow if we can't validate

        return True  # Non-macOS: assume valid

    def _restore_native_state(self, window, state: dict):
        """Restore window state via NSWindow APIs."""
        try:
            native = window._impl.native

            x = state['x']
            y = state['y']
            width = state['width']
            height = state['height']

            # Convert from top-left origin (saved) to bottom-left origin (macOS)
            screen = native.screen
            if screen:
                screen_frame = screen.frame
                screen_height = float(screen_frame.size.height)
                # y_bottom = screen_height - y_top - window_height
                y = screen_height - y - height

            # Use setFrame:display: for atomic position+size update
            from rubicon.objc.types import CGRect, CGPoint, CGSize

            frame = CGRect(
                CGPoint(x, y),
                CGSize(width, height)
            )

            native.setFrame_display_(frame, True)
            logger.debug(f"Restored native window frame: x={state['x']}, y={state['y']}, "
                         f"w={width}, h={height}")

        except Exception as e:
            logger.error(f"Failed to restore native window state: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._restore_toga_state(window, state)

    def _restore_toga_state(self, window, state: dict):
        """Restore window state via Toga APIs."""
        try:
            # Set position and size
            window.position = (state['x'], state['y'])
            window.size = (state['width'], state['height'])
            logger.debug(f"Restored Toga window state: {state}")

        except Exception as e:
            logger.error(f"Failed to restore Toga window state: {e}")

    def save_window_state(self, window_id: str):
        """
        Save current state of a specific window.

        Args:
            window_id: The window identifier
        """
        state = self.get_window_state(window_id)
        if state:
            self.state_manager.set_window_state(window_id, state.to_dict())
            logger.debug(f"Saved window state: {window_id}")

    def save_all_states(self):
        """Save state of all tracked windows."""
        saved_count = 0
        for window_id in list(self._tracked_windows.keys()):
            state = self.get_window_state(window_id)
            if state:
                self.state_manager.set_window_state(window_id, state.to_dict())
                saved_count += 1

        logger.info(f"Saved state for {saved_count} windows")

    def get_tracked_window_ids(self) -> list:
        """Get list of currently tracked window IDs."""
        return list(self._tracked_windows.keys())

    def cleanup(self):
        """Clean up observers and references."""
        if RUBICON_AVAILABLE:
            # Remove all observers
            for window_id in list(self._tracked_windows.keys()):
                self._remove_native_observers(window_id)

        self._tracked_windows.clear()
        logger.debug("WindowStateTracker cleanup complete")
