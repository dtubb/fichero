"""
Services for Main Window

Business logic services separated from UI components.
"""

from fichero.main_window.services.collection_scanner import CollectionScanner
from fichero.main_window.services.library_manager import LibraryManager

__all__ = [
    'CollectionScanner',
    'LibraryManager'
] 