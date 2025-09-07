"""
Views Module for Fichero Main Window

Provides view management and platform-specific view implementations.
"""

from fichero.windows.main.views.base_view import BaseView
from fichero.windows.main.views.mobile_view import MobileView
from fichero.windows.main.views.collection_view import CollectionView
from fichero.windows.main.views.collection_management_view import CollectionManagementView
from fichero.windows.main.views.view_manager import ViewManager, ViewType

__all__ = [
    'BaseView',
    'MobileView',
    'CollectionView',
    'CollectionManagementView',
    'ViewManager',
    'ViewType'
] 