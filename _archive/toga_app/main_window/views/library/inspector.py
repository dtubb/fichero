"""Library Inspector - Metadata panel for documents.

Shows document metadata, file info, and AI outputs.
Simple direct approach - no framework overhead.

Usage:
    from fichero.app.main_window.views.library import LibraryInspector

    inspector = LibraryInspector()
    inspector.load(document, artifacts)
    container.addSubview_(inspector.native)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, TYPE_CHECKING

from rubicon.objc import ObjCClass, SEL, objc_method, objc_property

if TYPE_CHECKING:
    from fichero.models import Document, Artifact

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

NSObject = ObjCClass("NSObject")
NSView = ObjCClass("NSView")
NSScrollView = ObjCClass("NSScrollView")
NSTextField = ObjCClass("NSTextField")
NSTextView = ObjCClass("NSTextView")
NSButton = ObjCClass("NSButton")
NSBox = ObjCClass("NSBox")
NSColor = ObjCClass("NSColor")
NSFont = ObjCClass("NSFont")
NSPasteboard = ObjCClass("NSPasteboard")


# =============================================================================
# Formatting Helpers
# =============================================================================

def format_size(size: int | None) -> str:
    """Format file size."""
    if size is None:
        return ""
    if size == 0:
        return "0 bytes"
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} bytes"


def format_datetime(dt: datetime | None) -> str:
    """Format datetime."""
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def format_dimensions(width: int | None, height: int | None) -> str:
    """Format dimensions."""
    if width and height:
        return f"{width} x {height}"
    return ""


# =============================================================================
# Flipped View (top-down layout)
# =============================================================================

class _LibraryInspectorFlippedView(NSView):
    """NSView with flipped coordinates for top-down layout."""

    @objc_method
    def isFlipped(self) -> bool:
        return True


# =============================================================================
# Button Delegate
# =============================================================================

class _InspectorDelegate(NSObject):
    """Handles button actions."""

    _inspector = objc_property(object, weak=True)

    @objc_method
    def copyText_(self, sender) -> None:
        """Copy transcription to clipboard."""
        inspector = self._inspector
        if inspector and inspector._transcription_view:
            text = str(inspector._transcription_view.string)
            if text:
                pb = NSPasteboard.generalPasteboard
                pb.clearContents()
                pb.setString_forType_(text, "public.utf8-plain-text")


# =============================================================================
# Library Inspector
# =============================================================================

class LibraryInspector:
    """Document metadata inspector for library mode.

    Shows:
    - Document info (name, type, status, created)
    - File info (path, size, dimensions)
    - AI outputs (transcription)
    """

    def __init__(self, width: int = INSPECTOR_WIDTH):
        self._width = width
        self._item: Document | None = None
        self._artifacts: list[Artifact] = []

        # Field references for updating
        self._name_field = None
        self._type_field = None
        self._status_field = None
        self._created_field = None
        self._path_field = None
        self._size_field = None
        self._dimensions_field = None
        self._transcription_view = None

        # Delegate
        self._delegate = _InspectorDelegate.alloc().init()
        self._delegate._inspector = self

        # Build UI
        self._scroll = NSScrollView.alloc().initWithFrame_(((0, 0), (width, 600)))
        self._scroll.hasVerticalScroller = True
        self._scroll.autohidesScrollers = True
        self._scroll.borderType = BORDER_NONE
        self._scroll.backgroundColor = NSColor.controlBackgroundColor
        self._scroll.setAutoresizingMask_(AUTORESIZE_FLEX)

        self._content = _LibraryInspectorFlippedView.alloc().initWithFrame_(((0, 0), (width, 800)))
        self._scroll.documentView = self._content

        self._build_ui()
        logger.debug("LibraryInspector created")

    def _build_ui(self):
        """Build the inspector UI."""
        y = 10

        # Document section
        y = self._add_section_header("DOCUMENT", y)
        self._name_field, y = self._add_field("Name", y, editable=True)
        self._type_field, y = self._add_field("Type", y)
        self._status_field, y = self._add_field("Status", y)
        self._created_field, y = self._add_field("Created", y)

        y += 10

        # File section
        y = self._add_section_header("FILE", y)
        self._path_field, y = self._add_field("Path", y)
        self._size_field, y = self._add_field("Size", y)
        self._dimensions_field, y = self._add_field("Dimensions", y)

        y += 10

        # AI Outputs section
        y = self._add_section_header("AI OUTPUTS", y)
        self._transcription_view, y = self._add_multiline_field("Transcription", y)

        y += 10

        # Actions
        y = self._add_section_header("ACTIONS", y)
        copy_btn = NSButton.alloc().initWithFrame_(((10, y), (80, 24)))
        copy_btn.title = "Copy Text"
        copy_btn.bezelStyle = 1  # Rounded
        copy_btn.setTarget_(self._delegate)
        copy_btn.setAction_(SEL("copyText:"))
        self._content.addSubview_(copy_btn)

        y += 40

        # Set content size
        self._content.setFrameSize_((self._width, y))

    def _add_section_header(self, title: str, y: int) -> int:
        """Add section header. Returns new y."""
        # Title
        label = NSTextField.alloc().initWithFrame_(((10, y + 4), (self._width - 20, 16)))
        label.stringValue = title
        label.editable = False
        label.bordered = False
        label.drawsBackground = False
        label.font = NSFont.systemFontOfSize_weight_(11, 0.6)
        label.textColor = NSColor.secondaryLabelColor
        self._content.addSubview_(label)

        # Divider
        divider = NSBox.alloc().initWithFrame_(((10, y + 22), (self._width - 20, 1)))
        divider.boxType = 4  # Separator
        self._content.addSubview_(divider)

        return y + 28

    def _add_field(self, label_text: str, y: int, editable: bool = False) -> tuple[Any, int]:
        """Add label + value field. Returns (value_field, new_y)."""
        # Label
        label = NSTextField.alloc().initWithFrame_(((10, y), (self._width - 20, 14)))
        label.stringValue = label_text
        label.editable = False
        label.bordered = False
        label.drawsBackground = False
        label.font = NSFont.systemFontOfSize_weight_(11, 0.5)
        label.textColor = NSColor.secondaryLabelColor
        self._content.addSubview_(label)

        # Value
        value = NSTextField.alloc().initWithFrame_(((10, y + 16), (self._width - 20, 20)))
        value.stringValue = ""
        value.editable = editable
        value.bordered = editable
        value.bezeled = editable
        value.drawsBackground = editable
        value.font = NSFont.systemFontOfSize_(12)
        self._content.addSubview_(value)

        return value, y + 44

    def _add_multiline_field(self, label_text: str, y: int) -> tuple[Any, int]:
        """Add label + multiline text view. Returns (text_view, new_y)."""
        # Label
        label = NSTextField.alloc().initWithFrame_(((10, y), (self._width - 20, 14)))
        label.stringValue = label_text
        label.editable = False
        label.bordered = False
        label.drawsBackground = False
        label.font = NSFont.systemFontOfSize_weight_(11, 0.5)
        label.textColor = NSColor.secondaryLabelColor
        self._content.addSubview_(label)

        # Scroll view with text view
        scroll = NSScrollView.alloc().initWithFrame_(((10, y + 16), (self._width - 20, 80)))
        scroll.hasVerticalScroller = True
        scroll.borderType = 2  # Bezel

        text_view = NSTextView.alloc().initWithFrame_(((0, 0), (self._width - 40, 80)))
        text_view.string = ""
        text_view.editable = False
        text_view.font = NSFont.systemFontOfSize_(12)
        text_view.setAutoresizingMask_(AUTORESIZE_FLEX)
        scroll.documentView = text_view

        self._content.addSubview_(scroll)

        return text_view, y + 104

    @property
    def native(self) -> Any:
        """The native NSScrollView."""
        return self._scroll

    @property
    def item(self) -> Document | None:
        """Currently loaded document."""
        return self._item

    def load(self, item: Any, artifacts: list[Artifact] | None = None) -> None:
        """Load a document for display."""
        self._item = item
        self._artifacts = artifacts or []

        if not item:
            self.clear()
            return

        # Document info
        self._name_field.stringValue = getattr(item, 'name', '') or ''

        doc_type = getattr(item, 'doc_type', None)
        self._type_field.stringValue = doc_type.value if doc_type and hasattr(doc_type, 'value') else ''

        status = getattr(item, 'status', None)
        self._status_field.stringValue = status.value if status and hasattr(status, 'value') else ''

        self._created_field.stringValue = format_datetime(getattr(item, 'created_at', None))

        # File info
        self._path_field.stringValue = getattr(item, 'path', '') or ''
        self._size_field.stringValue = format_size(getattr(item, 'file_size', None))
        self._dimensions_field.stringValue = format_dimensions(
            getattr(item, 'width', None),
            getattr(item, 'height', None)
        )

        # Load transcription from artifacts
        transcription = ""
        for artifact in self._artifacts:
            if getattr(artifact, 'artifact_type', None) == "transcription":
                transcription = getattr(artifact, 'content', '') or ''
                break
        self._transcription_view.string = transcription

        logger.debug(f"LibraryInspector loaded: {getattr(item, 'name', item)}")

    def load_from_id(self, doc_id: str) -> None:
        """Load document and artifacts by ID."""
        from fichero.db import db
        from fichero.models import Document, Artifact

        doc = db.get(Document, doc_id)
        if not doc:
            self.clear()
            return

        artifacts = list(db.query(Artifact, document_id=doc_id))
        self.load(doc, artifacts)

    def clear(self) -> None:
        """Clear all fields."""
        self._item = None
        self._artifacts = []

        self._name_field.stringValue = ""
        self._type_field.stringValue = ""
        self._status_field.stringValue = ""
        self._created_field.stringValue = ""
        self._path_field.stringValue = ""
        self._size_field.stringValue = ""
        self._dimensions_field.stringValue = ""
        self._transcription_view.string = ""

    def save(self) -> Document | None:
        """Save editable fields back to item. Does NOT persist to DB."""
        if not self._item:
            return None

        # Update name if edited
        if hasattr(self._item, 'name'):
            self._item.name = str(self._name_field.stringValue)

        return self._item

    def refresh(self) -> None:
        """Refresh display with current item."""
        if self._item:
            self.load(self._item, self._artifacts)
