"""Views - Mode-specific editor + inspector pairs.

Each view mode has its own editor and inspector:
- library: Document browsing (image/text/table viewers + metadata)
- workflow: Workflow editing/running (node canvas + provider settings)
- search: Search results (preview + filters)

Usage:
    from fichero.app.main_window.views.library import LibraryEditor, LibraryInspector
    from fichero.app.main_window.views.workflow import WorkflowEditor, WorkflowInspector
    from fichero.app.main_window.views.search import SearchEditor, SearchInspector
"""

from fichero.app.main_window.views.library import LibraryEditor, LibraryInspector
from fichero.app.main_window.views.workflow import WorkflowEditor, WorkflowInspector
from fichero.app.main_window.views.search import SearchEditor, SearchInspector

__all__ = [
    # Library view
    "LibraryEditor",
    "LibraryInspector",
    # Workflow view
    "WorkflowEditor",
    "WorkflowInspector",
    # Search view
    "SearchEditor",
    "SearchInspector",
]
