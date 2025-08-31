"""
Views Module for Fichero Main Window

Provides view management and platform-specific view implementations.
"""

from fichero.windows.main.views.base_view import BaseView
from fichero.windows.main.views.desktop_view import DesktopView
from fichero.windows.main.views.mobile_view import MobileView
from fichero.windows.main.views.collection_view import CollectionView
from fichero.windows.main.views.collection_management_view import CollectionManagementView
from fichero.windows.main.views.fiche_view import FicheView
from fichero.windows.main.views.preview_view import PreviewView
from fichero.windows.main.views.view_manager import ViewManager, ViewType

__all__ = [
    'BaseView',
    'DesktopView',
    'MobileView',
    'CollectionView',
    'CollectionManagementView',
    'FicheView',
    'PreviewView',
    'ViewManager',
    'ViewType'
] 