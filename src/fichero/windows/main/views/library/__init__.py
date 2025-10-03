"""
Library View Package

Contains the library overview view and its associated toolbars.
"""

from fichero.windows.main.views.library.library_view import LibraryView
# LibraryTopToolbar and LibraryBottomToolbar removed - now using composition pattern

__all__ = [
    'LibraryView',
    # 'LibraryTopToolbar',  # Now using TopToolbar + composition
    # 'LibraryBottomToolbar'  # Now using BottomToolbar + composition
]
