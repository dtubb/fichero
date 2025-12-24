"""Library View - Document browsing mode.

Components:
- LibraryEditor: EditorContainer that swaps between image/text/table viewers
- LibraryInspector: Document metadata inspector

Usage:
    from fichero.app.main_window.views.library import LibraryEditor, LibraryInspector

    editor = LibraryEditor()
    inspector = LibraryInspector()

    # Load a document
    editor.load(document)
    inspector.load(document, artifacts)
"""

from fichero.app.main_window.views.library.editor import LibraryEditor
from fichero.app.main_window.views.library.inspector import LibraryInspector

__all__ = [
    "LibraryEditor",
    "LibraryInspector",
]
