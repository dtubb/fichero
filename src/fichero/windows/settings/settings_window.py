"""
Settings Window - Desktop Window Implementation

Desktop window wrapper that uses the shared SettingsContent component.
"""

import logging
from typing import Optional
import toga
from toga.style import Pack
from toga.constants import COLUMN

from fichero.windows.settings.settings_content import SettingsContent
import gettext  # Import translation function

logger = logging.getLogger(__name__)


class SettingsWindow:
    """Desktop settings window that uses the shared SettingsContent component"""
    
    def __init__(self, app):
        """Initialize the settings window"""
        self.app = app
        self.window = toga.Window(
            title=_("preferences_title") if '_' in globals() else "Fichero Settings",
            size=(425, 500),
            resizable=True
        )
        
        # Create the settings content
        self.settings_content = SettingsContent(app)
        self.window.content = self.settings_content.create()
        
        # Center the window
        self._center_window()

        # Register with window state tracker for position/size persistence
        if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
            self.app.window_state_tracker.register_window("settings", self.window, restore=True)

        logger.info("SettingsWindow initialized")
    
    def _center_window(self):
        """Center the window on screen"""
        try:
            # Get the primary screen dimensions
            screen = self.app.screens[0]  # Primary screen
            screen_width = screen.size.width
            screen_height = screen.size.height
            
            # Calculate center position
            window_width = self.window.size.width
            window_height = self.window.size.height
            
            center_x = (screen_width - window_width) // 2
            center_y = (screen_height - window_height) // 2
            
            # Set the position
            self.window.position = (center_x, center_y)
        except Exception:
            # If centering fails, just use default position
            pass
    
    def show(self):
        """Show the settings window"""
        self.window.show()
    
    def hide(self):
        """Hide the settings window"""
        self.window.hide()
    
    def close(self):
        """Close the settings window"""
        if self.window:
            self.window.close()
            self.window = None
            self.settings_content = None 