"""
ViewModels for Fichero

Data management and business logic layer independent of UI widgets.
"""

from .base_viewmodel import BaseViewModel, ViewModelObserver
from .library_viewmodel import LibraryViewModel
from .collection_viewmodel import CollectionViewModel

__all__ = [
    'BaseViewModel',
    'ViewModelObserver',
    'LibraryViewModel',
    'CollectionViewModel'
]