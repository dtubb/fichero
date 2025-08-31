"""
Layout Module for Fichero Main Window

Provides pane management and layout organization.
"""

from fichero.windows.main.layout.pane_manager import PaneManager
from fichero.windows.main.layout.library_pane import LibraryPane
from fichero.windows.main.layout.content_pane import ContentPane
from fichero.windows.main.layout.preview_pane import PreviewPane

__all__ = [
    'PaneManager',
    'LibraryPane',
    'ContentPane',
    'PreviewPane'
] 