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

        # Register with window state tracker for position/size persistence
        if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
            self.app.window_state_tracker.register_window("prompts", self.window, restore=True)

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
            # Save state BEFORE closing (weak ref will be invalid after)
            if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
                self.app.window_state_tracker.save_window_state("prompts")
            self.window.close()
            self.window = None
            self.prompts_library = None 