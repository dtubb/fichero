"""Library Editor - Manages swappable editor views for library mode.

Simple dispatch: determines editor type from content, creates appropriate viewer.
No registry pattern - just straightforward if/elif for clarity.

Usage:
    from fichero.app.main_window.views.library import LibraryEditor
    from fichero.models import Document

    container = LibraryEditor()

    # Load a document - auto-selects viewer based on file type
    doc = db.get(Document, "abc123")
    container.load(doc)

    # Or explicitly show a specific editor
    container.show_editor(EditorType.text)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

from rubicon.objc import ObjCClass

from fichero.app.main_window.views.library.viewers import (
    EditorType,
    EditorProtocol,
    ImageViewer,
    TextViewer,
    TableViewer,
    IMAGE_EXTENSIONS,
)

if TYPE_CHECKING:
    from fichero.models import Document

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

_AUTORESIZE_FLEX = 18  # NSViewWidthSizable | NSViewHeightSizable

# Text file extensions
TEXT_EXTENSIONS = frozenset({".txt", ".md", ".rst", ".rtf", ".json", ".xml", ".html"})

# =============================================================================
# Cocoa Classes
# =============================================================================

NSView = ObjCClass("NSView")


# =============================================================================
# Library Editor (was EditorContainer)
# =============================================================================

class LibraryEditor:
    """Container that manages swappable editor views for library browsing.

    Auto-selects appropriate editor based on content type.
    Simple dispatch - no registry, just direct if/elif logic.
    """

    def __init__(self):
        # Container view
        self._container = NSView.alloc().initWithFrame_(((0, 0), (400, 600)))
        self._container.setAutoresizingMask_(_AUTORESIZE_FLEX)
        self._container.wantsLayer = True

        # Editors (lazy-created)
        self._editors: dict[EditorType, EditorProtocol] = {}
        self._current_editor: EditorProtocol | None = None
        self._current_type: EditorType | None = None

        logger.info("LibraryEditor created")

    @property
    def native(self) -> Any:
        """The native container NSView."""
        return self._container

    @property
    def current_editor(self) -> EditorProtocol | None:
        """The currently displayed editor."""
        return self._current_editor

    @property
    def current_type(self) -> EditorType | None:
        """The current editor type."""
        return self._current_type

    # -------------------------------------------------------------------------
    # Editor Management
    # -------------------------------------------------------------------------

    def _get_editor(self, editor_type: EditorType) -> EditorProtocol:
        """Get or create an editor of the given type."""
        if editor_type not in self._editors:
            # Simple dispatch - create the right editor
            if editor_type == EditorType.image:
                self._editors[editor_type] = ImageViewer()
            elif editor_type == EditorType.text:
                self._editors[editor_type] = TextViewer()
            elif editor_type == EditorType.table:
                self._editors[editor_type] = TableViewer()
            else:
                raise ValueError(f"Unknown editor type: {editor_type}")

        return self._editors[editor_type]

    def show_editor(self, editor_type: EditorType | str) -> EditorProtocol:
        """Switch to a specific editor type.

        Args:
            editor_type: EditorType enum or string ("image", "text", "table")

        Returns:
            The editor instance
        """
        # Convert string to EditorType
        if isinstance(editor_type, str):
            editor_type = EditorType(editor_type)

        # Already showing this editor?
        if self._current_type == editor_type:
            return self._current_editor

        # Remove current editor's view
        if self._current_editor:
            self._current_editor.native.removeFromSuperview()

        # Get and show new editor
        editor = self._get_editor(editor_type)
        editor.native.setFrame_(self._container.bounds)
        editor.native.setAutoresizingMask_(_AUTORESIZE_FLEX)
        self._container.addSubview_(editor.native)

        self._current_editor = editor
        self._current_type = editor_type

        logger.debug(f"LibraryEditor switched to: {editor_type.value}")
        return editor

    # -------------------------------------------------------------------------
    # Content Loading
    # -------------------------------------------------------------------------

    def _determine_editor_type(self, item: Any) -> EditorType:
        """Determine the best editor type for an item.

        Simple logic:
        - Document with image file_type or image extension -> image
        - Document with text file_type or text extension -> text
        - List -> table
        - Artifact -> text
        - String path to image -> image
        - Default -> image
        """
        from fichero.models import Document, Artifact

        # Document: check file_type and extension
        if isinstance(item, Document):
            # Check file_type enum
            if item.file_type:
                file_type_str = item.file_type.value if hasattr(item.file_type, 'value') else str(item.file_type)
                if file_type_str == "image":
                    return EditorType.image
                if file_type_str == "text":
                    return EditorType.text

            # Check file extension
            if item.path:
                ext = Path(item.path).suffix.lower()
                if ext in IMAGE_EXTENSIONS:
                    return EditorType.image
                if ext in TEXT_EXTENSIONS:
                    return EditorType.text

            # Default for documents: image viewer
            return EditorType.image

        # Artifact: always text
        if isinstance(item, Artifact):
            return EditorType.text

        # List: table viewer
        if isinstance(item, list):
            return EditorType.table

        # String: check if it's an image path
        if isinstance(item, str):
            ext = Path(item).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                return EditorType.image
            return EditorType.text

        # Path object
        if isinstance(item, Path):
            if item.suffix.lower() in IMAGE_EXTENSIONS:
                return EditorType.image
            return EditorType.text

        # Default: image viewer
        return EditorType.image

    def load(self, item: Any) -> None:
        """Load an item, automatically selecting appropriate editor.

        Args:
            item: Document, Artifact, list, path string, or Path
        """
        if item is None:
            self.clear()
            return

        # Determine editor type
        editor_type = self._determine_editor_type(item)

        # Switch to that editor and load
        editor = self.show_editor(editor_type)
        editor.load(item)

    def clear(self) -> None:
        """Clear the current editor."""
        if self._current_editor:
            self._current_editor.clear()

    def __getattr__(self, name: str):
        """Forward methods to current editor (zoom, rotate, magnifier, etc.)."""
        if self._current_editor and hasattr(self._current_editor, name):
            return getattr(self._current_editor, name)
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
