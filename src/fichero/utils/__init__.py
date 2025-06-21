"""
Utility modules for Fichero application.

This package contains shared infrastructure and helper functions
that are used across multiple parts of the application.
"""

from ..shared_data import get_shared_data, SharedDataManager, DataType
from ..config.core.settings import get_app_settings, AppSettings, reload_settings
from ..config.core.app_preferences import get_app_preferences, AppPreferences
from .i18n import translator, _
from ..config.ui.base_config_library import UISchema, load_ui_schema_from_file

__all__ = [
    "get_shared_data", "SharedDataManager", "DataType",
    "get_app_settings", "AppSettings", "reload_settings", 
    "get_app_preferences", "AppPreferences",
    "translator", "_",
    "UISchema", "load_ui_schema_from_file"
] 