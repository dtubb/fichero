"""
Add Window Package

Desktop window and mobile view for adding items to the library.
Uses BaseView pattern with DetailedList like LibraryView.
Supports platform-specific features: files, folders, URLs, camera, and audio recording.
"""

from fichero.windows.add.add_window import AddWindow
from fichero.windows.add.mobile_add_view import MobileAddView
from fichero.windows.add.add_content import AddContent, AddContentView
from fichero.windows.add.add_top_toolbar import AddTopToolbar
from fichero.windows.add.add_bottom_toolbar import AddBottomToolbar
from fichero.windows.add.platform_features import detect_platform_features, get_available_add_options, PlatformFeatures

__all__ = [
    "AddWindow",
    "MobileAddView", 
    "AddContent",
    "AddContentView",
    "AddTopToolbar",
    "AddBottomToolbar",
    "detect_platform_features",
    "get_available_add_options",
    "PlatformFeatures"
]
