"""
Views Module for Fichero Main Window

Provides view management and platform-specific view implementations.
"""

from .base_view import BaseView
from .desktop_view import DesktopView
from .mobile_view import MobileView
from .collection_view import CollectionView
from .collection_management_view import CollectionManagementView
from .fiche_view import FicheView
from .preview_view import PreviewView
from .view_manager import ViewManager, ViewType

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