"""
Fichero App - GUI components.

Windows:
- main_window/: Main application window (with menu, toolbar, sidebar)
- about_window.py: About dialog
- activity_window.py: Activity/task monitor
- settings_window.py: Settings/preferences

New native components (app/main_window/):
- sidebar.py: SourceList (NSOutlineView sidebar)
- browser.py: Browser (NSCollectionView grid)
- views/library/: LibraryEditor + LibraryInspector (document browsing)
- views/workflow/: WorkflowEditor + WorkflowInspector (workflow editing)
- views/search/: SearchEditor + SearchInspector (search results)
- window.py: MainWindowController (4-pane NSSplitView)
- menu.py: AppMenu (native NSMenu)
- toolbar.py: AppToolbar (native NSToolbar)
"""

from fichero.app.main_window import MainWindow
from fichero.app.about_window import AboutWindow
from fichero.app.activity_window import ActivityMonitorWindow
from fichero.app.settings_window import SettingsWindow

# New native components (lazy import to avoid Rubicon issues at module load)
# Use: from fichero.app.main_window.sidebar import SourceList, SourceListItem
# Use: from fichero.app.main_window.browser import Browser
# Use: from fichero.app.main_window.views.library import LibraryEditor, LibraryInspector
# Use: from fichero.app.main_window.views.workflow import WorkflowEditor, WorkflowInspector
# Use: from fichero.app.main_window.window import MainWindowController

__all__ = [
    "MainWindow",
    "AboutWindow",
    "ActivityMonitorWindow",
    "SettingsWindow",
]
