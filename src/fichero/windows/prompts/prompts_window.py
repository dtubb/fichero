"""
Prompts Window - Desktop Window Implementation

This uses the original PromptsLibrary (BaseConfigLibrary) for full file management functionality.
"""

import toga
import logging

logger = logging.getLogger(__name__)


class PromptsWindow:
    """Desktop prompts window that uses the full PromptsLibrary with file browser"""
    
    def __init__(self, app):
        """Initialize the prompts window"""
        self.app = app
        
        # Import and create the prompts library (which creates its own window)
        from fichero.config.ui.windows.prompts_library import PromptsLibrary
        self.prompts_library = PromptsLibrary(self.app)
        
        # Use the library's window directly (Toga way)
        self.window = self.prompts_library.window
        
        logger.info("PromptsWindow initialized")
    
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
            self.prompts_library = None 