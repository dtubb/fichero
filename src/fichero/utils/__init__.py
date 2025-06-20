"""
Utility modules for Fichero application.

This package contains shared infrastructure and helper functions
that are used across multiple parts of the application.
"""

from .shared_data import get_shared_data, SharedDataManager, DataType
from .app_settings import get_app_settings, AppSettings, reload_settings
from .i18n import translator, _
from .ui_generator import SchemaUIGenerator, UISchema, load_ui_schema_from_file

__all__ = [
    "get_shared_data", "SharedDataManager", "DataType",
    "get_app_settings", "AppSettings", "reload_settings", 
    "translator", "_",
    "SchemaUIGenerator", "UISchema", "load_ui_schema_from_file"
] 