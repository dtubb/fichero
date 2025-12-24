"""Main Window - Native macOS Mail/Finder-style architecture.

Uses NSSplitViewController for 4-pane layout with native behaviors:
- Sidebar (NSOutlineView) - extends to title bar
- Browser (NSCollectionView) - document grid
- Editor (swappable viewers) - image/text/table
- Inspector (context-aware) - metadata pane

See window.py for MainWindowController implementation.

Usage:
    from fichero.app.main_window import create_main_window, USE_NATIVE_WINDOW

    wrapper = create_main_window(app)
    wrapper.show()
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Feature flags
USE_NATIVE_WINDOW = True
USE_NATIVE_MENU_TOOLBAR = True


class MainWindow:
    """Wrapper that creates native NSWindow + MainWindowController.

    Provides interface expected by gui.py:
    - show() - display window
    - window - native NSWindow (for Toga compatibility)
    - _native_menu - menu handler
    - _native_toolbar - toolbar handler
    """

    def __init__(self, app):
        self.app = app
        self._controller = None
        self._ns_window = None
        self._native_menu = None
        self._native_toolbar = None

    def show(self):
        """Create and show the native window."""
        from rubicon.objc import ObjCClass
        from fichero.app.main_window.window import MainWindowController

        NSWindow = ObjCClass("NSWindow")
        NSScreen = ObjCClass("NSScreen")

        # Window style: titled, closable, miniaturizable, resizable
        style = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3)

        # Default size
        screen = NSScreen.mainScreen
        screen_frame = screen.visibleFrame
        width = min(1400, screen_frame.size.width * 0.8)
        height = min(900, screen_frame.size.height * 0.8)
        x = (screen_frame.size.width - width) / 2 + screen_frame.origin.x
        y = (screen_frame.size.height - height) / 2 + screen_frame.origin.y

        # Create window
        self._ns_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, y), (width, height)),
            style,
            2,  # NSBackingStoreBuffered
            False
        )
        self._ns_window.title = "Fichero"
        self._ns_window.minSize = (800, 600)

        # Create controller (this sets up the 4-pane layout)
        self._controller = MainWindowController(self.app, self._ns_window)
        self._controller.show()

        # Store menu/toolbar references for gui.py
        if hasattr(self._controller, '_menu'):
            self._native_menu = self._controller._menu
        if hasattr(self._controller, '_toolbar'):
            self._native_toolbar = self._controller._toolbar

        logger.info("MainWindow shown")

    @property
    def window(self):
        """Native NSWindow."""
        return self._ns_window

    @property
    def controller(self):
        """The MainWindowController."""
        return self._controller

    def _save_window_state(self):
        """Save window state (handled by NSWindow autosave)."""
        pass  # NSWindow.setFrameAutosaveName_ handles this

    def _update_toolbar_for_library_view(self, context: str = 'normal'):
        """Legacy toolbar update (no-op for native)."""
        pass


def create_main_window(app) -> MainWindow:
    """Factory function to create main window wrapper.

    Args:
        app: The Fichero app instance

    Returns:
        MainWindow wrapper
    """
    return MainWindow(app)


# Lazy import for MainWindowController and ViewMode to avoid ObjC loading at module import
def __getattr__(name):
    """Lazy loading of MainWindowController and ViewMode."""
    if name == "MainWindowController":
        from fichero.app.main_window.window import MainWindowController
        return MainWindowController
    if name == "ViewMode":
        from fichero.app.main_window.window import ViewMode
        return ViewMode
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "MainWindow",
    "MainWindowController",
    "ViewMode",
    "create_main_window",
    "USE_NATIVE_WINDOW",
    "USE_NATIVE_MENU_TOOLBAR",
]
