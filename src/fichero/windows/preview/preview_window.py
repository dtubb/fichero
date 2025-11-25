"""
Preview Window - Desktop Window Implementation

Desktop window for file preview and editing capabilities.
Supports multiple file types with appropriate viewers and editors.
"""

import logging
from typing import Optional
import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
from pathlib import Path

from fichero.windows.preview.preview_content import PreviewContent

logger = logging.getLogger(__name__)


class PreviewWindow:
    """Desktop preview window for file preview and editing"""
    
    def __init__(self, app, file_path=None, **kwargs):
        """Initialize the preview window"""
        self.app = app
        self.file_path = file_path
        
        # Determine window title based on file
        if file_path:
            file_name = Path(file_path).name
            title = f"Preview - {file_name}"
        else:
            title = "Preview"
        
        self.window = toga.Window(
            title=title,
            size=(800, 600),
            resizable=True
        )
        
        # Create the preview content
        self.preview_content = PreviewContent(app, file_path=file_path, **kwargs)
        self.window.content = self.preview_content.create()
        
        # Center the window
        self._center_window()

        # Register with window state tracker for position/size persistence
        if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
            self.app.window_state_tracker.register_window("preview", self.window, restore=True)

        logger.info(f"PreviewWindow initialized for: {file_path or 'no file'}")
    
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
        try:
            self.window.show()
            logger.info("Preview window shown")
        except Exception as e:
            logger.error(f"Failed to show preview window: {e}")
    
    def close(self):
        """Close the window"""
        try:
            if hasattr(self.preview_content, 'cleanup'):
                self.preview_content.cleanup()
            self.window.close()
            logger.info("Preview window closed")
        except Exception as e:
            logger.error(f"Failed to close preview window: {e}")
    
    def update_file(self, file_path):
        """Update the preview to show a different file"""
        try:
            self.file_path = file_path
            
            # Update window title
            if file_path:
                file_name = Path(file_path).name
                self.window.title = f"Preview - {file_name}"
            else:
                self.window.title = "Preview"
            
            # Update content
            if hasattr(self.preview_content, 'update_file'):
                self.preview_content.update_file(file_path)
            
            logger.info(f"Preview window updated for: {file_path}")
        except Exception as e:
            logger.error(f"Failed to update preview window: {e}")
    
    @property
    def closed(self):
        """Check if window is closed"""
        try:
            return self.window.closed
        except AttributeError:
            return True 