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
    # Import window classes
    from fichero.config.ui.windows.settings import SettingsWindow
    from fichero.config.ui.windows.prompts_library import PromptsLibrary
    from fichero.config.ui.windows.plans_library import PlansLibrary
    UI_WINDOWS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"UI windows not available: {e}")
    UI_WINDOWS_AVAILABLE = False
    # Create fallback classes
    class SettingsWindow:
        def __init__(self, app):
            raise RuntimeError("Settings window not available on this platform")
    
    class PromptsLibrary:
        def __init__(self, app):
            raise RuntimeError("Prompts window not available on this platform")
    
    class PlansLibrary:
        def __init__(self, app):
            raise RuntimeError("Plans window not available on this platform")


def create_settings_window(app):
    """Create a settings window with file library"""
    if not UI_WINDOWS_AVAILABLE:
        logger.error("Settings window not available on this platform")
        return None
    
    try:
        logger.info("Creating SettingsWindow...")
        settings_window = SettingsWindow(app)
        logger.info(f"SettingsWindow created: {settings_window}")
        return settings_window
    except Exception as e:
        logger.error(f"Failed to create SettingsWindow: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def create_prompts_window(app):
    """Create a prompts window with file library"""
    if not UI_WINDOWS_AVAILABLE:
        logger.error("Prompts window not available on this platform")
        return None
    
    return PromptsLibrary(app)


def create_plans_window(app):
    """Create a plans window with file library"""
    if not UI_WINDOWS_AVAILABLE:
        logger.error("Plans window not available on this platform")
        return None
    
    return PlansLibrary(app)