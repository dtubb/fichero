"""Text Viewer - Display and edit text content.

Usage:
    from fichero.app.main_window.views.library.viewers import TextViewer

    # Read-only viewer
    viewer = TextViewer()
    viewer.load(document)

    # Editable text editor
    editor = TextViewer(editable=True)
    editor.text = "Hello world"
"""
from __future__ import annotations

import logging
from typing import Any

from rubicon.objc import ObjCClass

from fichero.app.main_window.views.library.viewers.base import EditorProtocol

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

_AUTORESIZE_FLEX = 18  # NSViewWidthSizable | NSViewHeightSizable
_BORDER_NONE = 0

# Text inset (padding)
TEXT_INSET = (10, 10)
DEFAULT_FONT_SIZE = 14

# =============================================================================
# Cocoa Classes
# =============================================================================

NSScrollView = ObjCClass("NSScrollView")
NSTextView = ObjCClass("NSTextView")
NSFont = ObjCClass("NSFont")


# =============================================================================
# Text Viewer
# =============================================================================

class TextViewer(EditorProtocol):
    """Text viewer/editor for transcriptions and notes.

    Displays and optionally allows editing of text content.
    """

    def __init__(self, editable: bool = False):
        self._editable = editable

        # Scroll view
        self._scroll = NSScrollView.alloc().initWithFrame_(((0, 0), (400, 400)))
        self._scroll.hasVerticalScroller = True
        self._scroll.autohidesScrollers = True
        self._scroll.borderType = _BORDER_NONE
        self._scroll.setAutoresizingMask_(_AUTORESIZE_FLEX)

        # Text view
        self._text_view = NSTextView.alloc().initWithFrame_(((0, 0), (400, 400)))
        self._text_view.font = NSFont.systemFontOfSize_(DEFAULT_FONT_SIZE)
        self._text_view.editable = editable
        self._text_view.setAutoresizingMask_(_AUTORESIZE_FLEX)
        self._text_view.textContainerInset = TEXT_INSET

        self._scroll.documentView = self._text_view

        logger.info(f"TextViewer created (editable={editable})")

    @property
    def native(self) -> Any:
        """The native NSScrollView."""
        return self._scroll

    @property
    def text(self) -> str:
        """Current text content."""
        return str(self._text_view.string)

    @text.setter
    def text(self, value: str):
        """Set text content."""
        self._text_view.string = value or ""

    @property
    def editable(self) -> bool:
        """Whether text is editable."""
        return self._editable

    @editable.setter
    def editable(self, value: bool):
        """Set editable state."""
        self._editable = value
        self._text_view.editable = value

    def load(self, item: Any) -> None:
        """Load text from Document, Artifact, or string.

        Args:
            item: Document (uses page_content), Artifact (uses content), or string
        """
        if hasattr(item, 'page_content'):
            # Document
            self.text = item.page_content or ""
        elif hasattr(item, 'content'):
            # Artifact
            self.text = item.content or ""
        else:
            self.text = str(item) if item else ""

        logger.debug(f"TextViewer loaded {len(self.text)} chars")

    def clear(self) -> None:
        """Clear the text."""
        self.text = ""

    def scroll_to_top(self):
        """Scroll to top of text."""
        self._text_view.scrollRangeToVisible_((0, 0))

    def scroll_to_bottom(self):
        """Scroll to bottom of text."""
        length = len(self.text)
        self._text_view.scrollRangeToVisible_((length, 0))
