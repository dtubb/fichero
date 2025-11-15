"""
View type enumeration for navigation system.

Defines all available view types in the Fichero application.
"""

from enum import Enum


class ViewType(Enum):
    """Types of views in the application."""

    LIBRARY = "library"           # Library/sidebar view (collections list)
    COLLECTION = "collection"     # Collection view (items in a collection)
    STEP = "step"                 # Step view (processing steps browser)
    ADJUST = "adjust"             # Adjustment view (tool settings panel)
    PREVIEW = "preview"           # Preview view (file preview with plugins)
    INSPECTOR = "inspector"       # Inspector view (metadata/JSON viewer)
    ACTIVITY = "activity"         # Activity view (processing tasks/logs)
    SETTINGS = "settings"         # Settings view
    PLANS = "plans"               # Plans view (workflow plans)


__all__ = ['ViewType']
