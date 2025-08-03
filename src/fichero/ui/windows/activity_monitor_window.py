"""
Activity Monitor Window for Fichero - Direct GUI Task Display

Uses the simple GUITaskDisplay class directly to show all tasks across all documents.
Provides a clean interface for showing/hiding the activity monitor.
"""

import logging
from typing import Optional
import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

from fichero.director.monitoring.displays.gui_display import GUITaskDisplay
from fichero.director.monitoring.task_monitor import TaskMonitor

logger = logging.getLogger(__name__)


class ActivityMonitorContent:
    """Activity monitor content component that can be used in windows or as content replacement"""
    
    def __init__(self, app, show_back_button=False, on_back=None):
        """Initialize the activity monitor content"""
        self.app = app
        self.show_back_button = show_back_button
        self.on_back = on_back
        self.display: Optional[GUITaskDisplay] = None
        logger.info("ActivityMonitorContent initialized")
    
    def create(self):
        """Create the activity monitor content UI"""
        # Create the main display
        self._create_display()
        
        # Add back button if requested (for main window use)
        if self.show_back_button and self.on_back:
            # Create container with back button
            main_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1
                )
            )
            
            back_container = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin_bottom=10
                )
            )
            
            back_button = toga.Button(
                text="← Back",
                on_press=self.on_back
            )
            
            back_container.add(back_button)
            main_container.add(back_container)
            main_container.add(self.display.container)
            
            return main_container
        
        return self.display.container
    
    def _create_display(self):
        """Create the GUI task display"""
        try:
            # Get director from app
            director = getattr(self.app, 'director', None)
            if director is None:
                components = getattr(self.app, 'components', {})
                director = components.get('director')
            
            if director is None:
                raise RuntimeError("Director not available - cannot create activity monitor")
            
            # Create simple GUI task display (filter_document_id=None shows all tasks)
            task_monitor = TaskMonitor.get_instance(director)
            self.display = GUITaskDisplay(task_monitor, filter_document_id=None)
            
            logger.info("Activity monitor content created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create activity monitor content: {e}")
            raise
    
    def start_monitoring(self):
        """Start monitoring all tasks"""
        if self.display:
            self.display.start_monitoring()
    
    def stop_monitoring(self):
        """Stop monitoring"""
        if self.display:
            self.display.stop_monitoring()


class ActivityMonitorWindow:
    """Activity monitor window that uses the shared ActivityMonitorContent component"""
    
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
            # Create the activity monitor content
            self.activity_content = ActivityMonitorContent(self.app)
            
            # Create window with the content
            self.window = toga.Window(
                title="Fichero Activity Monitor",
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