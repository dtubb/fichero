"""
Layout Module for Fichero Main Window

Provides pane management and layout organization.
"""

from .pane_manager import PaneManager
from .library_pane import LibraryPane
from .content_pane import ContentPane
from .preview_pane import PreviewPane

__all__ = [
    'PaneManager',
    'LibraryPane',
    'ContentPane',
    'PreviewPane'
] 