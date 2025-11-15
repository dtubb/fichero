"""
Shared Views Package

Contains base classes and utilities for all views across the application.
Moved from windows/main/views/base to be shared by all window types.

Navigation System (Phase 6):
- BaseViewInterface: Standard interface for all views in navigation system
- ViewType: Enum of all view types
"""

from fichero.shared.views.base_view import BaseView
from fichero.shared.views.view_manager import ViewManager
from fichero.shared.views.base_view_interface import BaseViewInterface
from fichero.shared.views.view_types import ViewType as NavigationViewType

# Keep old ViewType from view_manager for backward compatibility
from fichero.shared.views.view_manager import ViewType as LegacyViewType

__all__ = [
    'BaseView',
    'ViewManager',
    'BaseViewInterface',
    'NavigationViewType',
    'LegacyViewType',
    'ViewType',  # Alias to LegacyViewType for backward compat
]

# Default ViewType to legacy for backward compatibility
ViewType = LegacyViewType
