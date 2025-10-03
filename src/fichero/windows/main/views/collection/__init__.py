"""
Collection View Package

Contains the collection browsing view and its associated toolbars.
"""

from fichero.windows.main.views.collection.collection_view import CollectionView
# CollectionTopToolbar and CollectionBottomToolbar removed - now using composition pattern

__all__ = [
    'CollectionView',
    # 'CollectionTopToolbar',  # Now using SimpleTopToolbar + composition
    # 'CollectionBottomToolbar'  # Now using BottomToolbar + composition
]
