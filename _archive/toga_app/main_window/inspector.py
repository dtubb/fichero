"""DEPRECATED - Use fichero.app.main_window.views.library.inspector instead.

This module is kept for backwards compatibility.
"""
import warnings

warnings.warn(
    "fichero.app.main_window.inspector is deprecated. "
    "Use fichero.app.main_window.views.library instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from new location
from fichero.app.main_window.views.library.inspector import LibraryInspector

# Old name for backwards compatibility
Inspector = LibraryInspector

__all__ = ["Inspector", "LibraryInspector"]
