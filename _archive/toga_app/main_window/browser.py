"""Browser - Grid view for browsing documents.

Displays documents as a thumbnail grid using NSCollectionView.
Pure view component - receives Document models, doesn't query database.

Data Flow:
    sidebar selection → window._on_sidebar_select() → db.query() → browser.items

Usage:
    from fichero.app.main_window.browser import Browser
    from fichero.models import Document
    from fichero.db import db

    browser = Browser(
        on_select=lambda docs: print(f"Selected: {[d.name for d in docs]}"),
        on_double_click=lambda doc: print(f"Opened: {doc.name}"),
        on_action=lambda docs, action: print(f"{action}: {docs}"),
    )

    # Load documents (typically done by window controller)
    docs = db.query(Document, parent_id=collection_id)
    browser.items = docs

    # Add to view
    container.addSubview_(browser.native)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

from rubicon.objc import ObjCClass, SEL, objc_method, objc_property, send_super

if TYPE_CHECKING:
    from fichero.models import Document

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Item layout (points)
ITEM_WIDTH = 120
ITEM_HEIGHT = 140
ITEM_SIZE = (ITEM_WIDTH, ITEM_HEIGHT)

# Thumbnail
THUMBNAIL_SIZE = (100, 100)
THUMBNAIL_Y_OFFSET = 30  # Distance from bottom of item

# Label
LABEL_PADDING = 4
LABEL_HEIGHT = 24

# Grid spacing
GRID_SPACING = 10
SECTION_INSET = 10

# NSCollectionView
_BORDER_NONE = 0
_AUTORESIZE_FLEX = 18  # NSViewWidthSizable | NSViewHeightSizable
_SELECTION_HIGHLIGHT_REGULAR = 0
_SCROLL_POSITION_NONE = 0
_SCROLL_POSITION_TOP = 1

# NSImageView
_IMAGE_SCALE_PROPORTIONALLY = 3

# NSTextField
_TEXT_ALIGN_CENTER = 1
_LINE_BREAK_TRUNCATE_TAIL = 4


# =============================================================================
# Context Menu Actions
# =============================================================================

@dataclass(frozen=True)
class ContextAction:
    """A context menu action.

    Attributes:
        label: Menu item text
        action: Action identifier (passed to on_action callback)
        key: Keyboard shortcut (e.g., " " for space)
    """
    label: str
    action: str
    key: str = ""


# Default context menu (None = separator)
DEFAULT_CONTEXT_ACTIONS: tuple[ContextAction | None, ...] = (
    ContextAction("Open", "open"),
    ContextAction("Quick Look", "quicklook", " "),
    None,
    ContextAction("Reveal in Finder", "reveal"),
    ContextAction("Get Info", "info", "i"),
    None,
    ContextAction("Delete", "delete"),
)


# =============================================================================
# Cocoa Classes
# =============================================================================

NSObject = ObjCClass("NSObject")
NSCollectionView = ObjCClass("NSCollectionView")
NSCollectionViewFlowLayout = ObjCClass("NSCollectionViewFlowLayout")
NSCollectionViewItem = ObjCClass("NSCollectionViewItem")
NSScrollView = ObjCClass("NSScrollView")
NSView = ObjCClass("NSView")
NSImageView = ObjCClass("NSImageView")
NSTextField = ObjCClass("NSTextField")
NSImage = ObjCClass("NSImage")
NSColor = ObjCClass("NSColor")
NSFont = ObjCClass("NSFont")
NSIndexPath = ObjCClass("NSIndexPath")
NSSet = ObjCClass("NSSet")
NSArray = ObjCClass("NSArray")
NSMenu = ObjCClass("NSMenu")
NSMenuItem = ObjCClass("NSMenuItem")


# =============================================================================
# Item View
# =============================================================================

class _BrowserItemView(NSCollectionViewItem):
    """Single item in the browser grid: thumbnail + label."""

    _thumbnail = objc_property(object)
    _label = objc_property(object)

    @objc_method
    def loadView(self) -> None:
        """Create the view hierarchy."""
        # Container
        view = NSView.alloc().initWithFrame_(((0, 0), ITEM_SIZE))
        view.wantsLayer = True

        # Thumbnail (centered horizontally, offset from bottom)
        thumb_x = (ITEM_WIDTH - THUMBNAIL_SIZE[0]) / 2
        thumb_view = NSImageView.alloc().initWithFrame_(
            ((thumb_x, THUMBNAIL_Y_OFFSET), THUMBNAIL_SIZE)
        )
        thumb_view.imageScaling = _IMAGE_SCALE_PROPORTIONALLY
        thumb_view.wantsLayer = True
        # Layer styling handled after view is added
        view.addSubview_(thumb_view)
        self._thumbnail = thumb_view

        # Label (at bottom, centered)
        label = NSTextField.alloc().initWithFrame_(
            ((LABEL_PADDING, LABEL_PADDING),
             (ITEM_WIDTH - LABEL_PADDING * 2, LABEL_HEIGHT))
        )
        label.stringValue = ""
        label.editable = False
        label.bordered = False
        label.drawsBackground = False
        label.alignment = _TEXT_ALIGN_CENTER
        label.font = NSFont.systemFontOfSize_(11)
        label.lineBreakMode = _LINE_BREAK_TRUNCATE_TAIL
        label.maximumNumberOfLines = 2
        view.addSubview_(label)
        self._label = label

        self.view = view

    @objc_method
    def setSelected_(self, selected: bool) -> None:
        """Update selection appearance."""
        send_super(__class__, self, 'setSelected:', selected)
        if self.view and self.view.layer:
            if selected:
                self.view.layer.backgroundColor = (
                    NSColor.selectedContentBackgroundColor.CGColor
                )
            else:
                self.view.layer.backgroundColor = None

    @objc_method
    def prepareForReuse(self) -> None:
        """Reset state before reuse."""
        send_super(__class__, self, 'prepareForReuse')
        self._thumbnail.image = None
        self._label.stringValue = ""


# =============================================================================
# Collection View (Data Source + Delegate)
# =============================================================================

class _BrowserCollectionView(NSCollectionView):
    """NSCollectionView with integrated data source and delegate."""

    _browser = objc_property(object, weak=True)

    # -------------------------------------------------------------------------
    # Data Source
    # -------------------------------------------------------------------------

    @objc_method
    def numberOfSectionsInCollectionView_(self, cv) -> int:
        return 1

    @objc_method
    def collectionView_numberOfItemsInSection_(self, cv, section: int) -> int:
        try:
            if self._browser:
                return len(self._browser._items)
            return 0
        except Exception as e:
            logger.error(f"Error in numberOfItemsInSection: {e}")
            return 0

    @objc_method
    def collectionView_itemForRepresentedObjectAtIndexPath_(self, cv, indexPath):
        """Provide item view for index."""
        try:
            if not self._browser:
                return None

            # Dequeue reusable item
            item = cv.makeItemWithIdentifier_forIndexPath_("BrowserItem", indexPath)
            idx = indexPath.item

            if idx >= len(self._browser._items):
                return item

            doc = self._browser._items[idx]

            # Set label and thumbnail
            item._label.stringValue = doc.name or ""
            # DEBUG: Skip thumbnail loading to test if that's the freeze
            item._thumbnail.image = self._browser._placeholder

            return item
        except Exception as e:
            logger.error(f"Error creating item at index {indexPath.item if indexPath else 'unknown'}: {e}")
            return None

    # -------------------------------------------------------------------------
    # Delegate: Selection
    # -------------------------------------------------------------------------

    @objc_method
    def collectionView_didSelectItemsAtIndexPaths_(self, cv, indexPaths) -> None:
        self._notify_selection()

    @objc_method
    def collectionView_didDeselectItemsAtIndexPaths_(self, cv, indexPaths) -> None:
        self._notify_selection()

    def _notify_selection(self) -> None:
        """Notify browser of selection change."""
        if self._browser and self._browser._on_select:
            self._browser._on_select(self._browser.selected)

    # -------------------------------------------------------------------------
    # Double-Click
    # -------------------------------------------------------------------------

    @objc_method
    def handleDoubleClick_(self, sender) -> None:
        """Handle double-click on item."""
        if not self._browser or not self._browser._on_double_click:
            return

        # Find clicked item
        event = self.window.currentEvent
        point = self.convertPoint_fromView_(event.locationInWindow, None)
        indexPath = self.indexPathForItemAtPoint_(point)

        if indexPath:
            idx = indexPath.item
            if idx < len(self._browser._items):
                self._browser._on_double_click(self._browser._items[idx])

    # -------------------------------------------------------------------------
    # Context Menu (Dynamic)
    # -------------------------------------------------------------------------

    @objc_method
    def menuForEvent_(self, event):
        """Build context menu dynamically from ContextAction definitions."""
        if not self._browser or not self._browser._on_action:
            return None

        # Find clicked item
        point = self.convertPoint_fromView_(event.locationInWindow, None)
        indexPath = self.indexPathForItemAtPoint_(point)

        if not indexPath:
            return None

        # Select clicked item if not already selected
        if not self.selectionIndexPaths.containsObject_(indexPath):
            self.selectionIndexPaths = NSSet.setWithObject_(indexPath)

        # Build menu from actions
        menu = NSMenu.alloc().initWithTitle_("")
        actions = self._browser._context_actions

        for action in actions:
            if action is None:
                menu.addItem_(NSMenuItem.separatorItem())
            else:
                # All items use the same handler with tag to identify action
                mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    action.label, SEL("handleContextAction:"), action.key
                )
                mi.target = self
                mi.representedObject = action.action  # Store action ID
                menu.addItem_(mi)

        return menu

    @objc_method
    def handleContextAction_(self, sender) -> None:
        """Handle any context menu action via representedObject."""
        if not self._browser or not self._browser._on_action:
            return

        action = sender.representedObject
        if action and self._browser.selected:
            self._browser._on_action(self._browser.selected, action)


# =============================================================================
# Browser (Public API)
# =============================================================================

class Browser:
    """Document browser grid view.

    Displays Document models as thumbnails in a grid.
    Pure view - doesn't query database, receives data via .items property.

    Attributes:
        items: List of Document models to display
        selected: Currently selected Document models

    Callbacks:
        on_select: Called when selection changes
        on_double_click: Called when item is double-clicked
        on_action: Called when context menu action is triggered
    """

    def __init__(
        self,
        on_select: Callable[[list[Document]], None] | None = None,
        on_double_click: Callable[[Document], None] | None = None,
        on_action: Callable[[list[Document], str], None] | None = None,
        context_actions: tuple[ContextAction | None, ...] | None = None,
    ):
        """Create a browser view.

        Args:
            on_select: Called with list of selected Documents
            on_double_click: Called with double-clicked Document
            on_action: Called with (selected Documents, action string)
            context_actions: Custom context menu, or None for default
        """
        self._on_select = on_select
        self._on_double_click = on_double_click
        self._on_action = on_action
        self._context_actions = context_actions or DEFAULT_CONTEXT_ACTIONS
        self._items: list[Document] = []

        # Placeholder for items without thumbnails
        self._placeholder = self._create_placeholder()

        # Layout
        layout = NSCollectionViewFlowLayout.alloc().init()
        layout.itemSize = ITEM_SIZE
        layout.minimumInteritemSpacing = GRID_SPACING
        layout.minimumLineSpacing = GRID_SPACING
        layout.sectionInset = (SECTION_INSET,) * 4

        # Collection view
        self._collection = _BrowserCollectionView.alloc().initWithFrame_(
            ((0, 0), (400, 400))
        )
        self._collection._browser = self
        self._collection.collectionViewLayout = layout
        self._collection.backgroundColors = [NSColor.clearColor]
        self._collection.allowsMultipleSelection = True
        self._collection.allowsEmptySelection = True
        self._collection.selectionHighlightStyle = _SELECTION_HIGHLIGHT_REGULAR
        self._collection.dataSource = self._collection
        self._collection.delegate = self._collection

        # Register item class
        self._collection.registerClass_forItemWithIdentifier_(
            _BrowserItemView, "BrowserItem"
        )

        # Wire double-click (use property assignment, not setTarget_)
        self._collection.target = self._collection
        self._collection.doubleAction = SEL("handleDoubleClick:")

        # Scroll view
        self._scroll = NSScrollView.alloc().initWithFrame_(((0, 0), (400, 400)))
        self._scroll.documentView = self._collection
        self._scroll.hasVerticalScroller = True
        self._scroll.hasHorizontalScroller = False
        self._scroll.autohidesScrollers = True
        self._scroll.borderType = _BORDER_NONE
        self._scroll.backgroundColor = NSColor.windowBackgroundColor
        self._scroll.setAutoresizingMask_(_AUTORESIZE_FLEX)

        # Empty state label (shown when no items)
        self._empty_label = NSTextField.alloc().initWithFrame_(((0, 0), (300, 60)))
        self._empty_label.stringValue = "No documents\nDrag files here or select a collection"
        self._empty_label.alignment = _TEXT_ALIGN_CENTER
        self._empty_label.editable = False
        self._empty_label.bordered = False
        self._empty_label.drawsBackground = False
        self._empty_label.textColor = NSColor.secondaryLabelColor
        self._empty_label.font = NSFont.systemFontOfSize_(13)
        self._empty_label.hidden = True
        self._scroll.addSubview_(self._empty_label)

        logger.info("Browser created")

    def _create_placeholder(self) -> NSImage | None:
        """Create placeholder image for items without thumbnails."""
        img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "doc.fill", None
        )
        if img:
            img.setTemplate_(True)
        return img

    def _load_thumbnail(self, doc: Document) -> NSImage | None:
        """Load thumbnail for a document with caching.

        Uses fast path: check metadata directly instead of expensive
        filesystem checks via doc.thumbnail_path property.

        Args:
            doc: Document model

        Returns:
            NSImage or placeholder
        """
        # Check cache first
        if not hasattr(self, '_thumb_cache'):
            self._thumb_cache = {}  # doc.id -> NSImage
            self._thumb_cache_misses = set()  # doc.id where no thumbnail exists

        doc_id = doc.id
        if doc_id in self._thumb_cache:
            return self._thumb_cache[doc_id]
        if doc_id in self._thumb_cache_misses:
            return self._placeholder

        # Fast path: check metadata directly (no filesystem check)
        # This avoids the expensive doc.thumbnail_path property which
        # imports storage module and checks file existence
        thumb_path = doc.metadata.get("thumbnail_path")

        if thumb_path:
            path = Path(thumb_path)
            try:
                # Only check existence if we have a path in metadata
                if path.exists():
                    img = NSImage.alloc().initWithContentsOfFile_(str(path))
                    if img:
                        self._thumb_cache[doc_id] = img
                        return img
            except Exception as e:
                logger.warning(f"Failed to load thumbnail {path}: {e}")

        # No thumbnail in metadata - return placeholder immediately
        # Don't do expensive filesystem search
        self._thumb_cache_misses.add(doc_id)
        return self._placeholder

    def _update_empty_state(self) -> None:
        """Show/hide empty state based on items."""
        if self._items:
            self._empty_label.hidden = True
        else:
            # Center the label
            bounds = self._scroll.bounds
            label_size = self._empty_label.frame.size
            x = (bounds.size.width - label_size.width) / 2
            y = (bounds.size.height - label_size.height) / 2
            self._empty_label.setFrameOrigin_((x, y))
            self._empty_label.hidden = False

    # -------------------------------------------------------------------------
    # Public Properties
    # -------------------------------------------------------------------------

    @property
    def native(self) -> Any:
        """Native NSScrollView for adding to parent."""
        return self._scroll

    @property
    def items(self) -> list[Document]:
        """Current documents being displayed."""
        return self._items

    @items.setter
    def items(self, docs: list[Document] | None) -> None:
        """Set documents to display."""
        self._items = list(docs) if docs else []
        self._collection.reloadData()
        self._update_empty_state()

    @property
    def selected(self) -> list[Document]:
        """Currently selected documents."""
        result = []
        for indexPath in self._collection.selectionIndexPaths or []:
            idx = indexPath.item
            if idx < len(self._items):
                result.append(self._items[idx])
        return result

    @selected.setter
    def selected(self, docs: list[Document] | None) -> None:
        """Set selection by Document objects.

        Args:
            docs: Documents to select, or None/empty to clear
        """
        if not docs:
            self._collection.deselectAll_(None)
            return

        # Build set of IDs to select
        doc_ids = {d.id for d in docs}

        # Find matching indices and create index paths
        paths = []
        for i, doc in enumerate(self._items):
            if doc.id in doc_ids:
                paths.append(NSIndexPath.indexPathForItem_inSection_(i, 0))

        if paths:
            self._collection.selectionIndexPaths = NSSet.setWithArray_(paths)

    # -------------------------------------------------------------------------
    # Public Methods
    # -------------------------------------------------------------------------

    def select_by_id(self, doc_id: str) -> bool:
        """Select a document by ID.

        Args:
            doc_id: Document ID to select

        Returns:
            True if found and selected
        """
        for i, doc in enumerate(self._items):
            if doc.id == doc_id:
                indexPath = NSIndexPath.indexPathForItem_inSection_(i, 0)
                index_set = NSSet.setWithObject_(indexPath)
                self._collection.selectionIndexPaths = index_set
                self._collection.scrollToItemsAtIndexPaths_scrollPosition_(
                    index_set, _SCROLL_POSITION_TOP
                )
                return True
        return False

    def reload(self) -> None:
        """Reload the display."""
        self._collection.reloadData()
        self._update_empty_state()

    def scroll_to_top(self) -> None:
        """Scroll to top of the grid."""
        if self._items:
            indexPath = NSIndexPath.indexPathForItem_inSection_(0, 0)
            self._collection.scrollToItemsAtIndexPaths_scrollPosition_(
                NSSet.setWithObject_(indexPath), _SCROLL_POSITION_TOP
            )
