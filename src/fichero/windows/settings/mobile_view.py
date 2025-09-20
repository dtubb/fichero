"""
Settings Mobile View

Mobile-specific view for settings that can be used in the main window.
"""

import logging
import toga
from toga.style import Pack
from toga.constants import COLUMN

from fichero.windows.settings.settings_content import SettingsContent
from fichero.shared.views.base_view import BaseView
from fichero.shared.toolbars.top_toolbar import TopToolbar
from fichero.shared.toolbars.bottom_toolbar import BottomToolbar

logger = logging.getLogger(__name__)


class SettingsMobileView(BaseView):
    """Mobile view for settings content that can be embedded in main window"""
    
    def __init__(self, app):
        """Initialize the mobile settings view"""
        # Create the settings content BEFORE calling super().__init__()
        # because BaseView.__init__ calls _create_content() which needs this
        self.settings_content = SettingsContent(app=app)
        
        # Initialize BaseView
        super().__init__(app, app.is_mobile)
        
        # Create toolbars
        self._create_toolbars()
        
        logger.info("SettingsMobileView initialized")
    
    def create(self):
        """Create the mobile settings view UI"""
        # Use BaseView's create which handles toolbar + content layout
        return self.get_container()
    
    def _create_content(self):
        """Create the settings content"""
        try:
            # Create content using the shared settings content
            content = self.settings_content.create()
            
            # Add to the content container
            if self.content_container and content:
                self.content_container.add(content)
                logger.info("Settings content added to view")
            
        except Exception as e:
            logger.error(f"Failed to create settings content: {e}")
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for settings view"""
        try:
            from fichero.shared.toolbars.simple_top_toolbar import SimpleTopToolbar
            from fichero.shared.toolbars.bottom_toolbar import BottomToolbar
            
            # Create simple top toolbar using automatic navigation (no manual on_back)
            self.top_toolbar = SimpleTopToolbar(
                app=self.app,
                title="Settings",
                is_mobile=self.is_mobile
            )
            
            # Bottom toolbar (empty for now, but consistent structure)
            class SettingsBottomToolbar(BottomToolbar):
                def _create_toolbar(self):
                    super()._create_toolbar()
                    # Settings-specific actions could go here
            
            self.bottom_toolbar = SettingsBottomToolbar(self.app, is_mobile=self.is_mobile)
            
            # Set toolbars on the view (mobile navigation will be connected automatically)
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)
            
            logger.info("Settings toolbars created successfully")            
        except Exception as e:
            logger.error(f"Failed to create settings toolbars: {e}")
    
    def show(self):
        """Show method for compatibility"""
        # Settings don't need special show logic like activity monitor
        logger.info("Settings mobile view shown")
    
    def hide(self):
        """Hide method for compatibility"""
        # Settings don't need special hide logic like activity monitor
        logger.info("Settings mobile view hidden")
    
    def _on_back_pressed(self):
        """Handle back button press"""
        logger.debug("Settings back button pressed")
        # Use the app's window view manager to go back
        if hasattr(self.app, 'window_view_manager') and hasattr(self.app.window_view_manager, 'mobile_view_manager'):
            self.app.window_view_manager.mobile_view_manager.go_back()
    
    def save_settings(self):
        """Save current settings"""
        return self.settings_content.save_settings()
    
    def load_settings(self):
        """Load settings"""
        return self.settings_content.load_settings()
    
    def refresh(self):
        """Refresh the settings display"""
        self.settings_content.refresh() 