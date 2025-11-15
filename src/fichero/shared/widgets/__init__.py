"""
Platform-agnostic widget abstractions for Fichero.

This module provides widgets that automatically adapt to the target platform:
- ListWidget: Platform-adaptive list (Table/DetailedList/Tree with pluggable renderers)
- ResizableCanvas: Draggable resize handles for pane splitting

Note: Toolbar functionality is provided by src/fichero/shared/toolbars/
"""

from .list_widget import ListWidget, Platform

# ResizableCanvas import is optional (may not exist yet)
try:
    from .resizable_canvas import ResizableCanvas, Orientation, create_resize_handle
    __all__ = [
        'ListWidget',
        'Platform',
        'ResizableCanvas',
        'Orientation',
        'create_resize_handle',
    ]
except ImportError:
    __all__ = [
        'ListWidget',
        'Platform',
    ]
