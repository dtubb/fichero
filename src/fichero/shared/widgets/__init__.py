"""
Platform-agnostic widget abstractions for Fichero.

This module provides widgets that automatically adapt to the target platform:
- AbstractTreeList: Tree (macOS/Linux), Table (Windows), DetailedList (mobile)
- AbstractToolbar: Toolbars with size variants (full, compact, mini)
- ResizableCanvas: Draggable resize handles for pane splitting
"""

from .abstract_tree_list import AbstractTreeList, Platform
from .abstract_toolbar import AbstractToolbar, ToolbarSize, ToolbarButton
from .resizable_canvas import ResizableCanvas, Orientation, create_resize_handle

__all__ = [
    'AbstractTreeList',
    'Platform',
    'AbstractToolbar',
    'ToolbarSize',
    'ToolbarButton',
    'ResizableCanvas',
    'Orientation',
    'create_resize_handle',
]
