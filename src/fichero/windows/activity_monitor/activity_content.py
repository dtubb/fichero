"""
Activity Monitor Content Component - Shared UI Logic

This component contains the activity monitoring UI logic and can be used
in both desktop windows and mobile views.
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
    
    def __init__(self, app):
        """Initialize the activity monitor content"""
        self.app = app
        self.display: Optional[GUITaskDisplay] = None
        logger.info("ActivityMonitorContent initialized")
    
    def create(self):
        """Create the activity monitor content UI"""
        # Create the main display
        self._create_display()
        
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
            self.display = GUITaskDisplay(task_monitor, app=self.app, filter_document_id=None)
            
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