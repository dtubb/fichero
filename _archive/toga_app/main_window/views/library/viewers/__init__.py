"""Viewers - Content viewers for library mode.

Available viewers:
- ImageViewer: Display images with zoom/rotate/magnifier
- TextViewer: Display text content
- TableViewer: Display tabular data

Usage:
    from fichero.app.main_window.views.library.viewers import (
        EditorType,
        EditorProtocol,
        ImageViewer,
        TextViewer,
        TableViewer,
        IMAGE_EXTENSIONS,
    )
"""

from fichero.app.main_window.views.library.viewers.base import EditorProtocol

# Editor types enum
from enum import Enum


class EditorType(Enum):
    """Available editor types."""
    image = "image"
    text = "text"
    table = "table"


# Image extensions for type detection
IMAGE_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
    ".webp", ".heic", ".heif", ".ico", ".svg"
})

# Lazy imports for viewers
def __getattr__(name):
    if name == "ImageViewer":
        from fichero.app.main_window.views.library.viewers.image_viewer import ImageViewer
        return ImageViewer
    if name == "TextViewer":
        from fichero.app.main_window.views.library.viewers.text_viewer import TextViewer
        return TextViewer
    if name == "TableViewer":
        from fichero.app.main_window.views.library.viewers.table_viewer import TableViewer
        return TableViewer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EditorType",
    "EditorProtocol",
    "ImageViewer",
    "TextViewer",
    "TableViewer",
    "IMAGE_EXTENSIONS",
]
