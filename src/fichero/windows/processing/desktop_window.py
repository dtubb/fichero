"""
Desktop Processing Window

Standalone window for document processing on desktop platforms.
Uses the refactored ProcessingContent component.
"""

import toga
from toga.style import Pack
import asyncio
import logging

# Use builtin _ function installed by translation.install()

from fichero.windows.processing.processing_content import ProcessingContent

logger = logging.getLogger(__name__)


class ProcessingWindow:
    """Desktop processing window that uses the shared ProcessingContent component"""
    
    def __init__(self, app):
        """Initialize the processing window"""
        self.app = app
        self.window = toga.Window(
            title=_("processing_window_title") if _("processing_window_title") != "processing_window_title" else "Fichero - Process",
            size=(650, 450),  # Slightly taller for new layout
            resizable=True
        )
        
        # Create the processing content (no back button for desktop)
        self.processing_content = ProcessingContent(app=app)
        self.window.content = self.processing_content.create()
        
        # Center the window
        self._center_window()

        # Register with window state tracker for position/size persistence
        if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
            self.app.window_state_tracker.register_window("processing", self.window, restore=True)

        logger.info("Processing window initialized successfully")
    
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
        """Show the window"""
        self.window.show()
    
    def hide(self):
        """Hide the window"""  
        self.window.hide() 
    
    def close(self):
        """Close the window"""
        if self.window:
            self.window.close()
            self.window = None 