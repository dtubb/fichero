"""DEPRECATED - Use fichero.app.main_window.views.library.editor instead.

This module is kept for backwards compatibility.
"""
import warnings

warnings.warn(
    "fichero.app.main_window.editor is deprecated. "
    "Use fichero.app.main_window.views.library instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from new location
from fichero.app.main_window.views.library.editor import LibraryEditor

# Old name for backwards compatibility
EditorContainer = LibraryEditor

__all__ = ["EditorContainer", "LibraryEditor"]
