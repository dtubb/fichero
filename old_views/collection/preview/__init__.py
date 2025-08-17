"""
Preview Components

Modular preview system for different file types in the collection view.
Each preview component handles a specific file type with appropriate functionality.

Components:
- PreviewManager: Coordinates all preview components
- ImagePreview: Full-size image preview with zoom and navigation
- TextPreview: Text content with syntax highlighting and editing
- DocumentPreview: Word, PDF, and other document formats
- FichePreview: Processed fiche data and metadata
- TranslationPreview: Translation results with comparison
"""

from .preview_manager import PreviewManager
from .image_preview import ImagePreview
from .text_preview import TextPreview
from .document_preview import DocumentPreview
from .fiche_preview import FichePreview
from .translation_preview import TranslationPreview

__all__ = [
    'PreviewManager',
    'ImagePreview',
    'TextPreview', 
    'DocumentPreview',
    'FichePreview',
    'TranslationPreview'
] 