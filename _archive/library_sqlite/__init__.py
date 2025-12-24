"""
Library Management Package for Fichero

Provides collection management, item tracking, and processing history
for the Fichero document processing system.
"""

from fichero.library.library_manager import LibraryManager
from fichero.library.models import Collection, CollectionItem, ProcessingResult
from fichero.library.storage import LibraryStorage
from fichero.library.import_export import CollectionImporter, CollectionExporter

__all__ = [
    'LibraryManager',
    'Collection', 
    'CollectionItem',
    'ProcessingResult',
    'LibraryStorage',
    'CollectionImporter',
    'CollectionExporter'
]
# Add new processing navigation classes
from fichero.library.processing_navigator import ProcessingNavigator, ProcessingStep, ProcessingOutput
# Note: LibraryDirectorBridge uses lazy import to avoid circular dependency with Director

__all__.extend([
    'ProcessingNavigator',
    'ProcessingStep',
    'ProcessingOutput'
])
