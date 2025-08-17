"""
Utility modules for Fichero application.

This package contains shared infrastructure and helper functions
that are used across multiple parts of the application.
"""

from fichero.shared_data import get_shared_data, SimpleSharedData
# from fichero.config.core.settings import get_app_settings, AppSettings, reload_settings
# from fichero.config.core.app_preferences import get_app_preferences, AppPreferences
from fichero.config.ui.base_config_library import UISchema, load_ui_schema_from_file
from fichero.utils.path_icons import render_path_with_icons, get_folder_icon_path, PathIconLoader, PathBuilder

__all__ = [
    "get_shared_data", "SimpleSharedData",
    # "get_app_settings", "AppSettings", "reload_settings", 
    # "get_app_preferences", "AppPreferences",
    "UISchema", "load_ui_schema_from_file",
    "render_path_with_icons", "get_folder_icon_path", "PathIconLoader", "PathBuilder"
] 