"""
Shared Views Package

Contains base classes and utilities for all views across the application.
Moved from windows/main/views/base to be shared by all window types.
"""

from fichero.shared.views.base_view import BaseView
from fichero.shared.views.view_manager import ViewManager, ViewType

__all__ = [
    'BaseView',
    'ViewManager',
    'ViewType'
]
