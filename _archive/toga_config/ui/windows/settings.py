"""
Settings Backend Library - DEPRECATED

Use fichero.app.settings_window.SettingsWindow instead.
"""

import logging

logger = logging.getLogger(__name__)

# Re-export from new location for backwards compatibility
from fichero.app.settings_window import SettingsWindow

# Legacy alias
SettingsLibrary = SettingsWindow
SettingsContent = SettingsWindow