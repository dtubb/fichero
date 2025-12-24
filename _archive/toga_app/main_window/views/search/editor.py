"""Search Editor - Search results preview.

Shows search results with preview capabilities.

Usage:
    from fichero.app.main_window.views.search import SearchEditor

    editor = SearchEditor()
    editor.load(results)
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from rubicon.objc import ObjCClass

if TYPE_CHECKING:
    from fichero.models import Document

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

_AUTORESIZE_FLEX = 18  # NSViewWidthSizable | NSViewHeightSizable

# =============================================================================
# Cocoa Classes
# =============================================================================

NSView = ObjCClass("NSView")
NSColor = ObjCClass("NSColor")
NSTextField = ObjCClass("NSTextField")
NSFont = ObjCClass("NSFont")


# =============================================================================
# Search Editor
# =============================================================================

class SearchEditor:
    """Search results editor.

    Shows search results with preview and navigation.
    """

    def __init__(self):
        self._results: list[Document] = []

        # Container view
        self._container = NSView.alloc().initWithFrame_(((0, 0), (400, 600)))
        self._container.setAutoresizingMask_(_AUTORESIZE_FLEX)
        self._container.wantsLayer = True
        self._container.layer.backgroundColor = NSColor.windowBackgroundColor.CGColor

        # Placeholder label
        self._placeholder = NSTextField.alloc().initWithFrame_(((0, 0), (400, 100)))
        self._placeholder.stringValue = "Search Results\n(Coming soon)"
        self._placeholder.editable = False
        self._placeholder.bordered = False
        self._placeholder.drawsBackground = False
        self._placeholder.alignment = 1  # Center
        self._placeholder.font = NSFont.systemFontOfSize_(18)
        self._placeholder.textColor = NSColor.secondaryLabelColor
        self._container.addSubview_(self._placeholder)

        # Center the placeholder
        self._placeholder.setFrameOrigin_((0, 250))
        self._placeholder.setFrameSize_((400, 100))

        logger.info("SearchEditor created (placeholder)")

    @property
    def native(self) -> Any:
        """The native container NSView."""
        return self._container

    @property
    def results(self) -> list[Document]:
        """Current search results."""
        return self._results

    def load(self, results: list[Document] | None) -> None:
        """Load search results.

        Args:
            results: List of Document models from search
        """
        self._results = results or []

        if results:
            self._placeholder.stringValue = f"Search Results\n{len(results)} items found"
        else:
            self._placeholder.stringValue = "Search Results\n(No results)"

        logger.debug(f"SearchEditor loaded {len(self._results)} results")

    def clear(self) -> None:
        """Clear search results."""
        self._results = []
        self._placeholder.stringValue = "Search Results\n(Enter a search query)"
