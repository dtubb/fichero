"""
Plans Window - Desktop Window Implementation

This uses the original PlansLibrary (BaseConfigLibrary) for full file management functionality.
"""

import toga
import logging

logger = logging.getLogger(__name__)


class PlansWindow:
    """Desktop plans window that uses the full PlansLibrary with file browser"""
    
    def __init__(self, app):
        """Initialize the plans window"""
        self.app = app
        
        # Import and create the plans library (which creates its own window)
        from fichero.config.ui.windows.plans_library import PlansLibrary
        self.plans_library = PlansLibrary(self.app)
        
        # Use the library's window directly (Toga way)
        self.window = self.plans_library.window
        
        logger.info("PlansWindow initialized")
    
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
            self.plans_library = None 