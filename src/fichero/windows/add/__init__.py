"""
Add Window Package

Desktop window and mobile view for adding items to the library.
Uses BaseView pattern with DetailedList like LibraryView.
Supports platform-specific features: files, folders, URLs, camera, and audio recording.
"""

# AddWindow, AddContent, AddTopToolbar and AddBottomToolbar removed - now using NavigationController
from fichero.windows.add.platform_features import detect_platform_features, get_available_add_options, PlatformFeatures

__all__ = [
    # AddWindow, AddContent, AddContentView removed - now using NavigationController
    "detect_platform_features",
    "get_available_add_options",
    "PlatformFeatures"
]
