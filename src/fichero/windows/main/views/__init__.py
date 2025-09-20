"""
Main Window Views Package

Contains all view components and their associated toolbars.
Each view type has its own package for better organization.
"""

from fichero.shared.views.base_view import BaseView
from fichero.shared.views.view_manager import ViewManager, ViewType
from fichero.windows.main.views.library.library_view import LibraryView
from fichero.windows.main.views.collection.collection_view import CollectionView

__all__ = [
    'BaseView',
    'ViewManager',
    'ViewType',
    'LibraryView',
    'CollectionView'
]
