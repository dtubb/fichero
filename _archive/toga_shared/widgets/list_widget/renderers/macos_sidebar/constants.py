"""
Constants for native macOS sidebar renderer.

NSOutlineView drag & drop constants per Apple documentation.
"""

import sys
import logging

logger = logging.getLogger(__name__)

# Check if Rubicon is available on macOS
RUBICON_AVAILABLE = False

if sys.platform == 'darwin':
    try:
        from rubicon.objc import ObjCClass, objc_method, objc_property, SEL
        from rubicon.objc.runtime import objc_id

        RUBICON_AVAILABLE = True
        logger.info("Rubicon-ObjC available - native macOS sidebar support enabled")
    except ImportError as e:
        logger.warning(f"Rubicon-ObjC not available - using Canvas fallback: {e}")


# NSOutlineView drag & drop constants (per Apple documentation)
# https://developer.apple.com/documentation/appkit/nsoutlineview

# Row index constants for setDropRow:dropOperation:
NS_OUTLINE_VIEW_DROP_ON_ITEM_INDEX = -1  # Special value meaning "drop ON the item itself"

# Drop operation constants (dropOperation parameter)
NS_TABLE_VIEW_DROP_ON = 0  # Blue highlight - drop ONTO item
NS_TABLE_VIEW_DROP_ABOVE = 1  # Line indicator - drop BETWEEN items

# Custom pasteboard type for local reordering
LOCAL_REORDER_PASTEBOARD_TYPE = "com.fichero.sidebar.localreorder"

# Drag operation constants
NS_DRAG_OPERATION_NONE = 0
NS_DRAG_OPERATION_COPY = 1
NS_DRAG_OPERATION_MOVE = 16


# Lazy-loaded ObjC classes
_objc_classes_loaded = False
NSOutlineView = None
NSScrollView = None
NSTableColumn = None
NSColor = None
NSFont = None
NSImage = None
NSImageView = None
NSObject = None


def load_objc_classes():
    """Lazy-load ObjC classes to avoid import-time issues."""
    global _objc_classes_loaded
    global NSOutlineView, NSScrollView, NSTableColumn, NSColor, NSFont, NSImage, NSImageView, NSObject

    if _objc_classes_loaded:
        return

    if not RUBICON_AVAILABLE:
        return

    try:
        from rubicon.objc import ObjCClass, NSObject as RubiconNSObject

        # Load AppKit classes
        NSOutlineView = ObjCClass("NSOutlineView")
        NSScrollView = ObjCClass("NSScrollView")
        NSTableColumn = ObjCClass("NSTableColumn")
        NSColor = ObjCClass("NSColor")
        NSFont = ObjCClass("NSFont")
        NSImage = ObjCClass("NSImage")
        NSImageView = ObjCClass("NSImageView")
        NSObject = RubiconNSObject

        _objc_classes_loaded = True
        logger.debug("ObjC classes loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load ObjC classes: {e}")
        raise


__all__ = [
    'RUBICON_AVAILABLE',
    'NS_OUTLINE_VIEW_DROP_ON_ITEM_INDEX',
    'NS_TABLE_VIEW_DROP_ON',
    'NS_TABLE_VIEW_DROP_ABOVE',
    'LOCAL_REORDER_PASTEBOARD_TYPE',
    'NS_DRAG_OPERATION_NONE',
    'NS_DRAG_OPERATION_COPY',
    'NS_DRAG_OPERATION_MOVE',
    'load_objc_classes',
    'NSOutlineView',
    'NSScrollView',
    'NSTableColumn',
    'NSColor',
    'NSFont',
    'NSImage',
    'NSImageView',
    'NSObject',
]
