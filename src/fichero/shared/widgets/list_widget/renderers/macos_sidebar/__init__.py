"""
Native macOS sidebar renderer using NSOutlineView.

This package provides a true native macOS sidebar using NSOutlineView via Rubicon-ObjC,
following Toga's established pattern for wrapping native widgets.

Usage:
    from fichero.shared.widgets.list_widget.renderers.macos_sidebar import NSOutlineViewSidebar, RUBICON_AVAILABLE
"""

from .constants import RUBICON_AVAILABLE
from .renderer import NSOutlineViewSidebar

__all__ = ['NSOutlineViewSidebar', 'RUBICON_AVAILABLE']
