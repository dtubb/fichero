"""
Activity Monitor Window for Fichero - Direct GUI Task Display

Uses the simple GUITaskDisplay class directly to show all tasks across all documents.
Provides a clean interface for showing/hiding the activity monitor.
"""

import logging
from typing import Optional
import toga
from toga.style import Pack

from ...director.monitoring.displays.gui_display import GUITaskDisplay
from ...director.monitoring.task_monitor import TaskMonitor

logger = logging.getLogger(__name__)


class ActivityMonitorWindow:
    """
    Activity Monitor Window using GUITaskDisplay directly.
    Shows all tasks across all documents with full task management controls.
    """
    
    def __init__(self, app):
        self.app = app
        self.window: Optional[toga.Window] = None
        self.display: Optional[GUITaskDisplay] = None
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
            if self.display:
                self.display.start_monitoring()
            
            logger.info("Activity monitor window shown")
    
    def hide(self):
        """Hide the activity monitor window"""
        if self.window and self.is_visible:
            self.window.hide()
            self.is_visible = False
            
            # Stop monitoring
            if self.display:
                self.display.stop_monitoring()
            
            logger.info("Activity monitor window hidden")
    
    def close(self):
        """Close the activity monitor window"""
        if self.window:
            # Stop monitoring
            if self.display:
                self.display.stop_monitoring()
            
            self.window.close()
            self.window = None
            self.display = None
            self.is_visible = False
            
            logger.info("Activity monitor window closed")
    
    def _create_window(self):
        """Create the activity monitor window with GUITaskDisplay"""
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
            
            # Create window with the display
            self.window = toga.Window(
                title="Fichero Activity Monitor",
                size=(1000, 500),
                resizable=True,
                content=self.display.container
            )
            
            # Set window close handler
            self.window.on_close = self._on_close
            
            logger.info("Activity monitor window created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create activity monitor window: {e}")
            raise
    
    def _on_close(self, widget):
        """Handle window close event"""
        self.close()
        return True
    
    @property
    def closed(self):
        """Check if the activity monitor window is closed"""
        return self.window is None 