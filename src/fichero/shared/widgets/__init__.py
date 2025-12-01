"""
Platform-agnostic widget abstractions for Fichero.

This module provides widgets that automatically adapt to the target platform:
- ListWidget: Platform-adaptive list (Table/DetailedList/Tree with pluggable renderers)
- ResizableCanvas: Draggable resize handles for pane splitting
- CollapsibleSection: Collapsible section with disclosure triangle
- MetadataFieldWidget: Single editable metadata field
- FieldSelectorDialog: Tinderbox-style field visibility selector

Note: Toolbar functionality is provided by src/fichero/shared/toolbars/
"""

from .list_widget import ListWidget, Platform
from .collapsible_section import CollapsibleSection
from .metadata_field import MetadataFieldWidget
from .field_selector_dialog import FieldSelectorDialog

# ResizableCanvas import is optional (may not exist yet)
try:
    from .resizable_canvas import ResizableCanvas, Orientation, create_resize_handle
    __all__ = [
        'ListWidget',
        'Platform',
        'ResizableCanvas',
        'Orientation',
        'create_resize_handle',
        'CollapsibleSection',
        'MetadataFieldWidget',
        'FieldSelectorDialog',
    ]
except ImportError:
    __all__ = [
        'ListWidget',
        'Platform',
        'CollapsibleSection',
        'MetadataFieldWidget',
        'FieldSelectorDialog',
    ]
