"""
Native macOS sidebar renderer using NSOutlineView via Rubicon-ObjC.

This module is a backwards-compatibility shim. The implementation has been
split into the macos_sidebar/ package for better maintainability.

See macos_sidebar/ for the actual implementation:
- macos_sidebar/constants.py - Constants and ObjC class loading
- macos_sidebar/objc_classes.py - ObjC class definitions (TogaSidebar, SidebarItem, MinWidthView)
- macos_sidebar/tree_operations.py - Tree manipulation helpers
- macos_sidebar/renderer.py - Main NSOutlineViewSidebar class
"""

# Re-export everything from the package for backwards compatibility
from .macos_sidebar import NSOutlineViewSidebar, RUBICON_AVAILABLE

__all__ = ['NSOutlineViewSidebar', 'RUBICON_AVAILABLE']
