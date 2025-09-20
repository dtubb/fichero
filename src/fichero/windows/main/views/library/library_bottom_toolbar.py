"""
Library Bottom Toolbar for Fichero

Bottom toolbar for library view - currently empty as requested.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from fichero.shared.toolbars.bottom_toolbar import BottomToolbar

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
            
            # Create centered buttons using new centering method
            self.add_centered_button_group([
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
        logger.info("🔧 Processing clicked - checking app state")
        logger.info(f"🔧 App has show_processing: {hasattr(self.app, 'show_processing')}")
        logger.info(f"🔧 App has window_view_manager: {hasattr(self.app, 'window_view_manager')}")
        if hasattr(self.app, 'window_view_manager'):
            logger.info(f"🔧 Window view manager is_mobile: {self.app.window_view_manager.is_mobile}")
            logger.info(f"🔧 Mobile view manager set: {self.app.window_view_manager.mobile_view_manager is not None}")
        
        # Use the app's processing window method
        try:
            if hasattr(self.app, 'show_processing'):
                result = self.app.show_processing()
                logger.info(f"🔧 show_processing() result: {result}")
            else:
                logger.error("Processing window not available - app.show_processing() not found")
        except Exception as e:
            logger.error(f"Failed to open processing: {e}")
    
    def _on_activity_monitor_clicked(self, widget):
        """Handle activity monitor button click"""
        logger.info("🔧 Activity monitor clicked - checking app state")
        logger.info(f"🔧 App has show_activity_monitor: {hasattr(self.app, 'show_activity_monitor')}")
        logger.info(f"🔧 App has window_view_manager: {hasattr(self.app, 'window_view_manager')}")
        if hasattr(self.app, 'window_view_manager'):
            logger.info(f"🔧 Window view manager is_mobile: {self.app.window_view_manager.is_mobile}")
            logger.info(f"🔧 Mobile view manager set: {self.app.window_view_manager.mobile_view_manager is not None}")
        
        # Use the app's activity monitor window method
        try:
            if hasattr(self.app, 'show_activity_monitor'):
                result = self.app.show_activity_monitor()
                logger.info(f"🔧 show_activity_monitor() result: {result}")
            else:
                logger.error("Activity monitor window not available - app.show_activity_monitor() not found")
        except Exception as e:
            logger.error(f"Failed to open activity monitor: {e}")
    
    def _on_about_clicked(self, widget):
        """Handle about button click"""
        logger.info("🔧 About clicked - checking app state")
        logger.info(f"🔧 App has show_about: {hasattr(self.app, 'show_about')}")
        logger.info(f"🔧 App has window_view_manager: {hasattr(self.app, 'window_view_manager')}")
        if hasattr(self.app, 'window_view_manager'):
            logger.info(f"🔧 Window view manager is_mobile: {self.app.window_view_manager.is_mobile}")
            logger.info(f"🔧 Mobile view manager set: {self.app.window_view_manager.mobile_view_manager is not None}")
        
        # Use the app's about window method
        try:
            if hasattr(self.app, 'show_about'):
                result = self.app.show_about()
                logger.info(f"🔧 show_about() result: {result}")
            else:
                logger.error("About window not available - app.show_about() not found")
        except Exception as e:
            logger.error(f"Failed to open about: {e}")
    
    def _on_library_settings_clicked(self, widget):
        """Handle library settings button click"""
        logger.info("🔧 Library settings clicked - checking app state")
        logger.info(f"🔧 App has show_settings: {hasattr(self.app, 'show_settings')}")
        logger.info(f"🔧 App has window_view_manager: {hasattr(self.app, 'window_view_manager')}")
        if hasattr(self.app, 'window_view_manager'):
            logger.info(f"🔧 Window view manager is_mobile: {self.app.window_view_manager.is_mobile}")
            logger.info(f"🔧 Mobile view manager set: {self.app.window_view_manager.mobile_view_manager is not None}")
        
        # Use the app's settings window method - single source of truth
        try:
            if hasattr(self.app, 'show_settings'):
                result = self.app.show_settings()
                logger.info(f"🔧 show_settings() result: {result}")
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
    def _on_add_clicked(self, widget):
        """Handle add button click in edit mode"""
        logger.info("Add button clicked in edit mode")
        if self.on_add_clicked:
            self.on_add_clicked()
    
    def clear_buttons(self):
        """Clear all buttons from toolbar"""
        try:
            if hasattr(self, 'left_content'):
                self.left_content.clear()
            if hasattr(self, 'center_content'):
                self.center_content.clear()
            if hasattr(self, 'right_content'):
                self.right_content.clear()
            
            logger.debug("Library bottom toolbar buttons cleared")
            
        except Exception as e:
            logger.error(f"Failed to clear buttons: {e}")
    
    def set_edit_mode(self, is_edit_mode: bool):
        """Set edit mode state and update toolbar accordingly"""
        try:
            if is_edit_mode:
                # Edit mode: Show only "Add" button
                self.clear_buttons()
                self.add_button_text_center("Add", self._on_add_clicked)
                logger.info("Library bottom toolbar set to edit mode - showing Add button")
            else:
                # Normal mode: Show regular buttons
                self.clear_buttons()
                self.add_centered_button_group([
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
                logger.info("Library bottom toolbar set to normal mode - showing regular buttons")
                
        except Exception as e:
            logger.error(f"Failed to set edit mode: {e}")
