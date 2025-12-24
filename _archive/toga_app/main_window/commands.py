"""Commands - Menu and toolbar action handlers.

Centralized command handling for both menu.py and toolbar.py.
Each command is a method that receives the window controller context.

Usage:
    from fichero.app.main_window.commands import Commands

    # In MainWindowController
    self.commands = Commands(self)

    # Menu/toolbar call commands
    self.commands.zoom_in()
"""
from __future__ import annotations

import logging
import sys
import webbrowser
from typing import TYPE_CHECKING

from rubicon.objc import ObjCClass

if TYPE_CHECKING:
    from fichero.app.main_window.window import MainWindowController

logger = logging.getLogger(__name__)

# Cocoa classes
NSApplication = ObjCClass("NSApplication")
NSOpenPanel = ObjCClass("NSOpenPanel")


class Commands:
    """Command handlers for menu and toolbar actions.

    Receives window controller for access to editor, inspector, sidebar, etc.
    """

    def __init__(self, window: MainWindowController):
        self.window = window

    # =========================================================================
    # App Menu
    # =========================================================================

    def about(self):
        """Show About dialog."""
        # TODO: Show native about panel
        NSApplication.sharedApplication.orderFrontStandardAboutPanel_(None)

    def open_settings(self):
        """Open Settings window."""
        if hasattr(self.window.app, 'show_settings'):
            self.window.app.show_settings()

    def hide_app(self):
        """Hide application."""
        NSApplication.sharedApplication.hide_(None)

    def hide_others(self):
        """Hide other applications."""
        NSApplication.sharedApplication.hideOtherApplications_(None)

    def show_all(self):
        """Show all applications."""
        NSApplication.sharedApplication.unhideAllApplications_(None)

    def quit_app(self):
        """Quit application cleanly."""
        logger.info("Quit requested")

        if hasattr(self.window.app, '_handle_exit'):
            self.window.app._handle_exit(self.window.app)
        else:
            if hasattr(self.window.app, 'finalize'):
                try:
                    self.window.app.finalize()
                except Exception as e:
                    logger.error(f"Error during finalize: {e}")
            sys.exit(0)

    # =========================================================================
    # File Menu
    # =========================================================================

    def import_file(self):
        """Import file via file picker."""
        panel = NSOpenPanel.openPanel()
        panel.canChooseFiles = True
        panel.canChooseDirectories = False
        panel.allowsMultipleSelection = True

        if panel.runModal() == 1:  # NSOKButton
            paths = [str(url.path) for url in panel.URLs]
            if paths:
                target = self.window._selected_collection.id if self.window._selected_collection else None
                self.window.ingest_files(paths, target_id=target)

    def import_folder(self):
        """Import folder via folder picker."""
        panel = NSOpenPanel.openPanel()
        panel.canChooseFiles = False
        panel.canChooseDirectories = True
        panel.allowsMultipleSelection = False

        if panel.runModal() == 1:  # NSOKButton
            folder = str(panel.URL.path)
            if folder:
                self.window.ingest_files([folder])

    def close_window(self):
        """Close current window."""
        self.window._window.performClose_(None)

    def close_all(self):
        """Close all windows."""
        for window in NSApplication.sharedApplication.windows:
            window.performClose_(None)

    # =========================================================================
    # View Menu - Pane Toggles
    # =========================================================================

    def toggle_library(self):
        """Toggle library sidebar."""
        self.window.toggle_pane('sidebar')

    def toggle_collection(self):
        """Toggle collection browser."""
        self.window.toggle_pane('browser')

    def toggle_preview_image(self):
        """Toggle preview image (editor)."""
        self.window.toggle_pane('editor')

    def toggle_inspector(self):
        """Toggle inspector."""
        self.window.toggle_pane('inspector')

    show_inspector = toggle_inspector  # Alias

    # =========================================================================
    # View Menu - Zoom (forwarded to editor)
    # =========================================================================

    def zoom_in(self):
        """Zoom in."""
        self.window.editor.zoom_in()

    def zoom_out(self):
        """Zoom out."""
        self.window.editor.zoom_out()

    def zoom_to_fit(self):
        """Zoom to fit."""
        self.window.editor.zoom_to_fit()

    def zoom_actual_size(self):
        """Zoom to actual size (100%)."""
        self.window.editor.zoom_actual_size()

    def zoom_to_selection(self):
        """Zoom to selection box."""
        self.window.editor.zoom_to_selection()

    # =========================================================================
    # View Menu - Magnifier (forwarded to editor)
    # =========================================================================

    def toggle_magnifier(self):
        """Toggle magnifier panel."""
        self.window.editor.toggle_magnifier()

    def magnifier_zoom_in(self):
        """Magnifier zoom in."""
        self.window.editor.magnifier_zoom_in()

    def magnifier_zoom_out(self):
        """Magnifier zoom out."""
        self.window.editor.magnifier_zoom_out()

    # =========================================================================
    # View Menu - Rotation (forwarded to editor)
    # =========================================================================

    def rotate_left(self):
        """Rotate image left."""
        self.window.editor.rotate_left()

    def rotate_right(self):
        """Rotate image right."""
        self.window.editor.rotate_right()

    # =========================================================================
    # Window Menu
    # =========================================================================

    def minimize(self):
        """Minimize window."""
        self.window._window.performMiniaturize_(None)

    # =========================================================================
    # Help Menu
    # =========================================================================

    def visit_homepage(self):
        """Visit homepage."""
        webbrowser.open("https://www.tubb.ca/fichero/")

    # =========================================================================
    # Toolbar Actions
    # =========================================================================

    def settings(self):
        """Toolbar: Settings button."""
        self.open_settings()

    def process(self):
        """Process selected items."""
        # TODO: Open processing dialog with selected documents
        docs = self.window._selected_documents
        logger.info(f"Process requested for {len(docs)} documents")
