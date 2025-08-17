"""
Activity Monitor Window - Desktop Window Implementation

Desktop window wrapper that uses the shared ActivityMonitorContent component.
"""

import logging
from typing import Optional
import toga

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class ActivityMonitorWindow:
    """Desktop activity monitor window that uses the shared ActivityMonitorContent component"""
    
    def __init__(self, app):
        """Initialize the activity monitor window"""
        self.app = app
        self.window: Optional[toga.Window] = None
        self.is_visible = False
        logger.info("ActivityMonitorWindow initialized")
    
    def show(self):
        """Show the activity monitor window"""
        if self.window is None:
            self._create_window()
        
        if not self.is_visible:
            self.window.show()
            self.is_visible = True
            
            # Start monitoring all tasks
            if hasattr(self, 'activity_content') and self.activity_content:
                self.activity_content.start_monitoring()
            
            logger.info("Activity monitor window shown")
    
    def hide(self):
        """Hide the activity monitor window"""
        if self.window and self.is_visible:
            self.window.hide()
            self.is_visible = False
            
            # Stop monitoring
            if hasattr(self, 'activity_content') and self.activity_content:
                self.activity_content.stop_monitoring()
            
            logger.info("Activity monitor window hidden")
    
    def close(self):
        """Close the activity monitor window"""
        if self.window:
            # Stop monitoring first
            if hasattr(self, 'activity_content') and self.activity_content:
                self.activity_content.stop_monitoring()
            
            # Close the window - Toga will handle the rest
            self.window.close()
            self.window = None
            self.activity_content = None
            self.is_visible = False
            
            logger.info("Activity monitor window closed")
    
    def _create_window(self):
        """Create the activity monitor window with ActivityMonitorContent"""
        try:
            # Import and create the shared activity monitor content
            from fichero.windows.activity_monitor.activity_content import ActivityMonitorContent
            self.activity_content = ActivityMonitorContent(self.app)
            
            # Create window with the content
            self.window = toga.Window(
                title=_("activity_monitor_window_title") if _("activity_monitor_window_title") != "activity_monitor_window_title" else "Fichero Activity Monitor",
                size=(1000, 500),
                resizable=True,
                content=self.activity_content.create()
            )
            
            # Center the window
            self._center_window()
            
            logger.info("Activity monitor window created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create activity monitor window: {e}")
            raise
    
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