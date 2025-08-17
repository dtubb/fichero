"""
Settings Window Module

Provides settings windows and views for both desktop and mobile platforms.
Uses shared SettingsContent from config module.
"""

from fichero.windows.settings.settings_window import SettingsWindow
from fichero.windows.settings.mobile_view import SettingsMobileView

__all__ = [
    'SettingsWindow',
    'SettingsMobileView'
] 