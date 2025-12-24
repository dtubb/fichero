"""
Main Window Package

Primary application window containing the library navigation and document management interface.
Supports both desktop (SplitContainer) and mobile (full-screen drill-down) layouts.

NOTE: MainWindow has been moved to fichero.app.main_window
      Import from fichero.app instead to avoid circular imports:
        from fichero.app import MainWindow

      The old main_window.py is kept here for reference/fallback.
"""

# Other components still here
from fichero.windows.main.window_view_manager import WindowViewManager, WindowType
from fichero.windows.main.views import ViewManager, ViewType, CollectionView

__all__ = [
    # MainWindow: import from fichero.app instead
    'ViewManager',
    'ViewType',
    'CollectionView'
] 