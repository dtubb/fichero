"""
Header Component for Main Window

Handles the title and action buttons (Refresh, Settings, About).
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN

import gettext


class HeaderComponent:
    """Header component with title and action buttons"""
    
    def __init__(self, on_refresh=None, on_settings=None, on_about=None):
        """Initialize header component with callback handlers"""
        self.on_refresh = on_refresh
        self.on_settings = on_settings
        self.on_about = on_about
        self.container = None
    
    def create(self):
        """Create the header UI"""
        header = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(0, 0, 10, 0)
            )
        )
        
        # Empty header - no redundant labels
        self.container = header
        return header
    
    def _on_refresh(self, widget):
        """Handle refresh button press"""
        if self.on_refresh:
            self.on_refresh(widget)
    
    def _on_settings(self, widget):
        """Handle settings button press"""
        if self.on_settings:
            self.on_settings(widget)
    
    def _on_about(self, widget):
        """Handle about button press"""
        if self.on_about:
            self.on_about(widget) 