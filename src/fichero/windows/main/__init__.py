"""
Main Window Package

Primary application window containing the library navigation and document management interface.
Supports both desktop (SplitContainer) and mobile (full-screen drill-down) layouts.
"""

from fichero.windows.main.main_window import MainWindow

# Export view and component classes for direct usage if needed
from fichero.windows.main.views import ViewManager, ViewType, CollectionView

__all__ = [
    'MainWindow',
    'ViewManager',
    'ViewType',
    'CollectionView'
] 