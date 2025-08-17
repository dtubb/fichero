"""
Settings Backend Library
Backend logic for settings - UI components moved to windows/settings/

This module now only provides legacy compatibility and backend imports.
The actual SettingsContent UI class has been moved to:
fichero.windows.settings.settings_content
"""

import logging

logger = logging.getLogger(__name__)


class SettingsLibrary:
    """Legacy compatibility class - use windows.settings.SettingsContent instead"""
    
    def __init__(self, app, show_back_button=False, on_back=None):
        logger.warning("SettingsLibrary is deprecated - use windows.settings.SettingsContent instead")
        # Import the real implementation
        from fichero.windows.settings.settings_content import SettingsContent
        self._real_content = SettingsContent(app, show_back_button, on_back)
    
    def create(self):
        """Delegate to the real implementation"""
        return self._real_content.create()
    
    def save_settings(self):
        """Delegate to the real implementation"""
        return self._real_content.save_settings()
    
    def load_settings(self):
        """Delegate to the real implementation"""
        return self._real_content.load_settings()


# For backward compatibility, alias SettingsContent to SettingsLibrary
SettingsContent = SettingsLibrary