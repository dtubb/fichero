"""
Activity Monitor Window for Fichero - Thin Wrapper

Lightweight wrapper around ActivityMonitorDisplay from gui_display.py.
Provides a simple interface for showing/hiding the activity monitor.
"""

import logging
from typing import Optional

from ...director.monitoring.displays.gui_display import ActivityMonitorDisplay

logger = logging.getLogger(__name__)


class ActivityMonitorWindow:
    """
    Thin wrapper around ActivityMonitorDisplay.
    Provides a simple interface for the app to show/hide the activity monitor.
    """
    
    def __init__(self, app):
        self.app = app
        self.display: Optional[ActivityMonitorDisplay] = None
        logger.info("ActivityMonitorWindow wrapper initialized")
    
    def show(self):
        """Show the activity monitor window"""
        if not self.display:
            self.display = ActivityMonitorDisplay(self.app)
        
        self.display.show()
        logger.info("Activity monitor window shown via display")
    
    def hide(self):
        """Hide the activity monitor window"""
        if self.display:
            self.display.hide()
            logger.info("Activity monitor window hidden via display")
    
    def close(self):
        """Close the activity monitor window"""
        if self.display:
            self.display.close()
            self.display = None
            logger.info("Activity monitor window closed via display")
    
    @property
    def is_visible(self):
        """Check if the activity monitor is visible"""
        return self.display and self.display.is_visible
    
    @property
    def closed(self):
        """Check if the activity monitor window is closed"""
        return self.display is None or (hasattr(self.display, 'window') and self.display.window is None) 