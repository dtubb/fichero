"""
Settings Mobile View

Mobile-specific view for settings that can be used in the main window.
"""

import logging
from fichero.windows.settings.settings_content import SettingsContent

logger = logging.getLogger(__name__)


class SettingsMobileView:
    """Mobile view for settings content that can be embedded in main window"""
    
    def __init__(self, app):
        """Initialize the mobile settings view"""
        self.app = app
        
        # Create the shared content (toolbar handles navigation)
        self.settings_content = SettingsContent(app=app)
        
        logger.info("SettingsMobileView initialized")
    
    def create(self):
        """Create the mobile settings view UI"""
        return self.settings_content.create()
    
    def show(self):
        """Show method for compatibility"""
        # Settings don't need special show logic like activity monitor
        logger.info("Settings mobile view shown")
    
    def hide(self):
        """Hide method for compatibility"""
        # Settings don't need special hide logic like activity monitor
        logger.info("Settings mobile view hidden")
    
    def save_settings(self):
        """Save current settings"""
        return self.settings_content.save_settings()
    
    def load_settings(self):
        """Load settings"""
        return self.settings_content.load_settings()
    
    def refresh(self):
        """Refresh the settings display"""
        self.settings_content.refresh() 