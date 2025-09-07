"""
Library Bottom Toolbar for Fichero

Bottom toolbar for library view - currently empty as requested.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from fichero.windows.main.toolbars.bottom_toolbar import BottomToolbar

logger = logging.getLogger(__name__)


class LibraryBottomToolbar(BottomToolbar):
    """Bottom toolbar for library view - currently empty"""
    
    def __init__(self, app, is_mobile: bool = None):
        """Initialize library bottom toolbar"""
        logger.info(f"LibraryBottomToolbar.__init__ called with app={app}, is_mobile={is_mobile}")
        super().__init__(app, is_mobile)
        
        # Library-specific callbacks (none for now)
        self.on_global_inbox: Optional[Callable] = None
        self.on_tags: Optional[Callable] = None
        self.on_library_settings: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the library bottom toolbar content"""
        try:
            # Call parent to set up basic structure
            super()._create_toolbar()
            
            # Create centered buttons using smart helper
            self.add_standard_center_buttons([
                {
                    'icon': 'export',
                    'on_press': self._on_processing_clicked,
                    'tooltip': 'Process Documents'
                },
                {
                    'icon': 'activity',
                    'on_press': self._on_activity_monitor_clicked,
                    'tooltip': 'Activity Monitor'
                },
                {
                    'icon': 'help',
                    'on_press': self._on_about_clicked,
                    'tooltip': 'About Fichero'
                },
                {
                    'icon': 'gear@10x',
                    'on_press': self._on_library_settings_clicked,
                    'tooltip': 'Library Settings'
                }
            ])
            
            logger.info("Library bottom toolbar created with centered buttons using smart methods")
            
        except Exception as e:
            logger.error(f"Failed to create library bottom toolbar: {e}")
    
    def _create_processing_button(self):
        """Legacy method - no longer needed"""
        pass
    
    def _create_activity_monitor_button(self):
        """Legacy method - no longer needed"""
        pass
    
    def _create_about_button(self):
        """Legacy method - no longer needed"""
        pass
    
    def _create_settings_button(self):
        """Legacy method - no longer needed"""
        pass
    
    def _on_processing_clicked(self, widget):
        """Handle processing button click"""
        logger.debug("Processing clicked")
        
        # Use the app's processing window method
        try:
            if hasattr(self.app, 'show_processing'):
                self.app.show_processing()
            else:
                logger.error("Processing window not available - app.show_processing() not found")
        except Exception as e:
            logger.error(f"Failed to open processing: {e}")
    
    def _on_activity_monitor_clicked(self, widget):
        """Handle activity monitor button click"""
        logger.debug("Activity monitor clicked")
        
        # Use the app's activity monitor window method
        try:
            if hasattr(self.app, 'show_activity_monitor'):
                self.app.show_activity_monitor()
            else:
                logger.error("Activity monitor window not available - app.show_activity_monitor() not found")
        except Exception as e:
            logger.error(f"Failed to open activity monitor: {e}")
    
    def _on_about_clicked(self, widget):
        """Handle about button click"""
        logger.debug("About clicked")
        
        # Use the app's about window method
        try:
            if hasattr(self.app, 'show_about'):
                self.app.show_about()
            else:
                logger.error("About window not available - app.show_about() not found")
        except Exception as e:
            logger.error(f"Failed to open about: {e}")
    
    def _on_library_settings_clicked(self, widget):
        """Handle library settings button click"""
        logger.debug("Library settings clicked")
        
        # Use the app's settings window method - single source of truth
        try:
            if hasattr(self.app, 'show_settings'):
                self.app.show_settings()
            else:
                logger.error("Settings window not available - app.show_settings() not found")
        except Exception as e:
            logger.error(f"Failed to open settings: {e}")
    
    def register_callbacks(self, on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None,
                         on_global_inbox: Optional[Callable] = None,
                         on_tags: Optional[Callable] = None,
                         on_library_settings: Optional[Callable] = None):
        """Register callbacks for library bottom toolbar actions"""
        super().register_callbacks(on_settings, on_about, on_help)
        self.on_global_inbox = on_global_inbox
        self.on_tags = on_tags
        self.on_library_settings = on_library_settings
        logger.debug("Library bottom toolbar callbacks registered")
    
    def update_status(self, status_text: str):
        """Update the status information"""
        # Find and update the status label
        for child in self.content.children:
            if hasattr(child, 'text') and "Ready" in child.text:
                child.text = status_text
                break 