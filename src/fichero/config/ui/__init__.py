"""
Configuration Windows Factory
Convenience functions for creating different types of configuration windows
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from fichero.config.ui.base_config_library import UISchema, load_ui_schema_from_file
from fichero.config.ui.components.file_library_panel import FileLibraryPanel

# Conditional imports for iOS compatibility
try:
    # Import window classes - all now come from windows module
    from fichero.windows.settings import SettingsWindow
    from fichero.windows.plans import PlansWindow
    from fichero.windows.prompts import PromptsWindow
    UI_WINDOWS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"UI windows not available: {e}")
    UI_WINDOWS_AVAILABLE = False
    # Create fallback classes
    class SettingsWindow:
        def __init__(self, app):
            raise RuntimeError("Settings window not available on this platform")
    
    class PromptsWindow:
        def __init__(self, app):
            raise RuntimeError("Prompts window not available on this platform")
    
    class PlansWindow:
        def __init__(self, app):
            raise RuntimeError("Plans window not available on this platform")


# create_settings_window removed - use app.show_settings() instead
# The settings window is now managed at the app level for proper single-instance behavior


# create_prompts_window and create_plans_window removed - use app.show_prompts() and app.show_plans() instead
# The prompts and plans windows are now managed at the app level for proper single-instance behavior