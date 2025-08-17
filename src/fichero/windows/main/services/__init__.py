"""
Services for Main Window

Business logic services separated from UI components.
"""

from fichero.windows.main.services.collection_scanner import CollectionScanner
from fichero.windows.main.services.library_manager import LibraryManager

__all__ = [
    'CollectionScanner',
    'LibraryManager'
] 