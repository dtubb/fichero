"""Search Inspector - Search filters and facets.

Shows search filters, facets, and refinement options.

Usage:
    from fichero.app.main_window.views.search import SearchInspector

    inspector = SearchInspector()
    inspector.load(facets)
"""
from __future__ import annotations

import logging
from typing import Any

from rubicon.objc import ObjCClass, objc_method

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

INSPECTOR_WIDTH = 300
AUTORESIZE_FLEX = 18
BORDER_NONE = 0

# =============================================================================
# Cocoa Classes
# =============================================================================

NSView = ObjCClass("NSView")
NSScrollView = ObjCClass("NSScrollView")
NSTextField = ObjCClass("NSTextField")
NSBox = ObjCClass("NSBox")
NSColor = ObjCClass("NSColor")
NSFont = ObjCClass("NSFont")


# =============================================================================
# Flipped View (top-down layout)
# =============================================================================

class _SearchInspectorFlippedView(NSView):
    """NSView with flipped coordinates for top-down layout."""

    @objc_method
    def isFlipped(self) -> bool:
        return True


# =============================================================================
# Search Inspector
# =============================================================================

class SearchInspector:
    """Search filters and facets inspector.

    Shows:
    - Search query display
    - Filter options (date range, type, status)
    - Facets (counts by category)
    """

    def __init__(self, width: int = INSPECTOR_WIDTH):
        self._width = width
        self._facets: dict[str, int] = {}

        # UI references
        self._query_field = None
        self._result_count_field = None

        # Build UI
        self._scroll = NSScrollView.alloc().initWithFrame_(((0, 0), (width, 600)))
        self._scroll.hasVerticalScroller = True
        self._scroll.autohidesScrollers = True
        self._scroll.borderType = BORDER_NONE
        self._scroll.backgroundColor = NSColor.windowBackgroundColor
        self._scroll.setAutoresizingMask_(AUTORESIZE_FLEX)

        self._content = _SearchInspectorFlippedView.alloc().initWithFrame_(((0, 0), (width, 400)))
        self._scroll.documentView = self._content

        self._build_ui()
        logger.debug("SearchInspector created")

    def _build_ui(self):
        """Build the inspector UI."""
        y = 10

        # Search section
        y = self._add_section_header("SEARCH", y)
        self._query_field, y = self._add_field("Query", y)
        self._result_count_field, y = self._add_field("Results", y)

        y += 10

        # Filters section (placeholder)
        y = self._add_section_header("FILTERS", y)
        placeholder = NSTextField.alloc().initWithFrame_(((10, y), (self._width - 20, 60)))
        placeholder.stringValue = "Filter options\n(Coming soon)"
        placeholder.editable = False
        placeholder.bordered = False
        placeholder.drawsBackground = False
        placeholder.font = NSFont.systemFontOfSize_(12)
        placeholder.textColor = NSColor.tertiaryLabelColor
        self._content.addSubview_(placeholder)
        y += 70

        # Facets section (placeholder)
        y = self._add_section_header("FACETS", y)
        facets_placeholder = NSTextField.alloc().initWithFrame_(((10, y), (self._width - 20, 60)))
        facets_placeholder.stringValue = "Category counts\n(Coming soon)"
        facets_placeholder.editable = False
        facets_placeholder.bordered = False
        facets_placeholder.drawsBackground = False
        facets_placeholder.font = NSFont.systemFontOfSize_(12)
        facets_placeholder.textColor = NSColor.tertiaryLabelColor
        self._content.addSubview_(facets_placeholder)
        y += 70

        # Set content size
        self._content.setFrameSize_((self._width, y + 20))

    def _add_section_header(self, title: str, y: int) -> int:
        """Add section header. Returns new y."""
        label = NSTextField.alloc().initWithFrame_(((10, y + 4), (self._width - 20, 16)))
        label.stringValue = title
        label.editable = False
        label.bordered = False
        label.drawsBackground = False
        label.font = NSFont.systemFontOfSize_weight_(11, 0.6)
        label.textColor = NSColor.secondaryLabelColor
        self._content.addSubview_(label)

        divider = NSBox.alloc().initWithFrame_(((10, y + 22), (self._width - 20, 1)))
        divider.boxType = 4  # Separator
        self._content.addSubview_(divider)

        return y + 28

    def _add_field(self, label_text: str, y: int) -> tuple[Any, int]:
        """Add label + value field. Returns (value_field, new_y)."""
        label = NSTextField.alloc().initWithFrame_(((10, y), (self._width - 20, 14)))
        label.stringValue = label_text
        label.editable = False
        label.bordered = False
        label.drawsBackground = False
        label.font = NSFont.systemFontOfSize_weight_(11, 0.5)
        label.textColor = NSColor.secondaryLabelColor
        self._content.addSubview_(label)

        value = NSTextField.alloc().initWithFrame_(((10, y + 16), (self._width - 20, 20)))
        value.stringValue = ""
        value.editable = False
        value.bordered = False
        value.drawsBackground = False
        value.font = NSFont.systemFontOfSize_(12)
        self._content.addSubview_(value)

        return value, y + 44

    @property
    def native(self) -> Any:
        """The native NSScrollView."""
        return self._scroll

    def load(self, query: str = "", count: int = 0, facets: dict[str, int] | None = None) -> None:
        """Load search info.

        Args:
            query: Search query string
            count: Number of results
            facets: Category counts
        """
        self._facets = facets or {}

        self._query_field.stringValue = query or "(empty)"
        self._result_count_field.stringValue = f"{count} items"

        logger.debug(f"SearchInspector loaded: query='{query}', count={count}")

    def clear(self) -> None:
        """Clear the inspector."""
        self._facets = {}
        self._query_field.stringValue = ""
        self._result_count_field.stringValue = "0 items"
