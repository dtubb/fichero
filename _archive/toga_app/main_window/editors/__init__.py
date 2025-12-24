"""DEPRECATED - Use fichero.app.main_window.views.library.viewers instead.

This module is kept for backwards compatibility.
"""
import warnings

warnings.warn(
    "fichero.app.main_window.editors is deprecated. "
    "Use fichero.app.main_window.views.library.viewers instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from new location
from fichero.app.main_window.views.library.viewers import (
    EditorType,
    EditorProtocol,
    ImageViewer,
    TextViewer,
    TableViewer,
    IMAGE_EXTENSIONS,
)
from fichero.app.main_window.views.library.viewers.table_viewer import TableColumn


__all__ = [
    # Types
    "EditorType",
    "EditorProtocol",
    # Editors
    "ImageViewer",
    "TextViewer",
    "TableViewer",
    "TableColumn",
    # Constants
    "IMAGE_EXTENSIONS",
]
