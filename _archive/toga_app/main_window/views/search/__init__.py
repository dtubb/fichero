"""Search View - Search results mode.

Components:
- SearchEditor: Search results preview
- SearchInspector: Search filters and facets

Usage:
    from fichero.app.main_window.views.search import SearchEditor, SearchInspector

    editor = SearchEditor()
    inspector = SearchInspector()

    # Load search results
    editor.load(results)
    inspector.load(query, count, facets)
"""

from fichero.app.main_window.views.search.editor import SearchEditor
from fichero.app.main_window.views.search.inspector import SearchInspector

__all__ = [
    "SearchEditor",
    "SearchInspector",
]
