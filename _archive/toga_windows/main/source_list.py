"""SourceList - macOS sidebar using NSOutlineView.

A native macOS sidebar widget for hierarchical navigation, similar to
Finder's sidebar or Mail's mailbox list. Uses NSVisualEffectView for
translucent vibrancy background.

Usage:
    from fichero.windows.main.source_list import SourceList, SourceListItem

    sidebar = SourceList(
        on_select=lambda item: print(f"Selected: {item.text}"),
        on_reorder=lambda src, tgt, idx: print(f"Moved {src}"),
        on_file_drop=lambda tgt, paths: print(f"Dropped {paths}"),
        on_action=lambda item, action: print(f"{action} on {item.text}"),
    )
    sidebar.items = [
        SourceListItem(
            id="favorites",
            text="FAVORITES",
            is_header=True,
            children=[
                SourceListItem(id="inbox", text="Inbox", icon="tray.fill", badge="3"),
                SourceListItem(id="docs", text="Documents", icon="folder.fill"),
            ],
        )
    ]
    container.addSubview_(sidebar.native)

Features:
    - Translucent vibrancy background (NSVisualEffectView)
    - Section headers with group item styling
    - SF Symbol icons (leading and trailing)
    - Badge text (e.g., item count)
    - Drag-drop reordering and file drops
    - Right-click context menus
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from rubicon.objc import ObjCClass, SEL, objc_method, objc_property


# =============================================================================
# Constants
# =============================================================================

# Pasteboard UTI types for drag-drop
ITEM_UTI = "com.fichero.sourcelist-item"
FILE_UTI = "public.file-url"

# Layout dimensions (points)
ROW_HEIGHT = 24
HEADER_HEIGHT = 28
ICON_SIZE = 16
INDENT = 12

# NSVisualEffectView - creates translucent "frosted glass" background like Finder sidebar
_MATERIAL_SIDEBAR = 4           # Dark translucent material matching system sidebar appearance
_BLENDING_BEHIND_WINDOW = 1     # Blur content behind the window (not within it)
_STATE_FOLLOWS_WINDOW = 1       # Vibrancy activates/deactivates with window focus

# NSTableView selection and drag-drop
_HIGHLIGHT_REGULAR = 1          # Standard blue selection highlight (vs source list style)
_DRAG_NONE = 0                  # Drop not allowed at this location
_DRAG_COPY = 1                  # Drop will copy (+ badge on cursor)
_DRAG_MOVE = 2                  # Drop will move item
_DRAG_FEEDBACK_REGULAR = 1      # Show insertion line + blue highlight on drop target

# Text and layout
_TRUNCATE_TAIL = 4              # NSLineBreakByTruncatingTail - "..." at end
_ALIGN_RIGHT = 2                # NSTextAlignmentRight
_AUTORESIZE_FLEX = 18           # NSViewWidthSizable (2) | NSViewHeightSizable (16)
_COLUMN_RESIZE_AUTO = 1         # NSTableColumnAutoresizingMask
_BORDER_NONE = 0                # NSNoBorder - no border around scroll view


# =============================================================================
# Cocoa Classes
# =============================================================================

NSObject = ObjCClass("NSObject")
NSOutlineView = ObjCClass("NSOutlineView")
NSScrollView = ObjCClass("NSScrollView")
NSTableColumn = ObjCClass("NSTableColumn")
NSTableCellView = ObjCClass("NSTableCellView")
NSTextField = ObjCClass("NSTextField")
NSImageView = ObjCClass("NSImageView")
NSImage = ObjCClass("NSImage")
NSColor = ObjCClass("NSColor")
NSFont = ObjCClass("NSFont")
NSMenu = ObjCClass("NSMenu")
NSMenuItem = ObjCClass("NSMenuItem")
NSPasteboardItem = ObjCClass("NSPasteboardItem")
NSArray = ObjCClass("NSArray")
NSIndexSet = ObjCClass("NSIndexSet")
NSURL = ObjCClass("NSURL")
NSVisualEffectView = ObjCClass("NSVisualEffectView")


# =============================================================================
# SourceListItem
# =============================================================================

@dataclass
class SourceListItem:
    """A single item in the source list sidebar.

    Attributes:
        id: Unique identifier for the item.
        text: Display text shown in the sidebar.
        icon: SF Symbol name for the leading icon (e.g., "folder.fill").
        badge: Text badge shown on the right (e.g., item count).
        trailing_icon: SF Symbol name for a trailing icon.
        is_header: If True, renders as a section header (non-selectable).
        accepts_drops: If True, files/items can be dropped onto this item.
        children: Child items for hierarchical display.
        data: Arbitrary user data attached to the item.
    """

    id: str
    text: str
    icon: str | None = None
    badge: str | None = None
    trailing_icon: str | None = None
    is_header: bool = False
    accepts_drops: bool = False
    children: list[SourceListItem] = field(default_factory=list)
    data: Any = None

    def find(self, item_id: str) -> SourceListItem | None:
        """Find an item by ID in this item or its descendants."""
        if self.id == item_id:
            return self
        for child in self.children:
            if found := child.find(item_id):
                return found
        return None

    def remove(self, item_id: str) -> SourceListItem | None:
        """Remove and return an item by ID from this item's descendants."""
        for i, child in enumerate(self.children):
            if child.id == item_id:
                return self.children.pop(i)
            if removed := child.remove(item_id):
                return removed
        return None


def _unwrap(wrapper: Any) -> SourceListItem | None:
    """Extract Python SourceListItem from ObjC wrapper."""
    return getattr(wrapper, "_py", None) if wrapper else None


def _create_label(text: str, x: int, width: int, is_header: bool = False):
    """Create a configured text field for display in a cell."""
    tf = NSTextField.alloc().initWithFrame_(((x, 4), (width, 16)))
    tf.stringValue = text
    tf.editable = False
    tf.bordered = False
    tf.drawsBackground = False
    if is_header:
        tf.font = NSFont.systemFontOfSize_weight_(11, 0.6)
        tf.textColor = NSColor.secondaryLabelColor
    else:
        tf.font = NSFont.systemFontOfSize_(13)
        tf.lineBreakMode = _TRUNCATE_TAIL
    return tf


# =============================================================================
# SourceListView (NSOutlineView subclass)
# =============================================================================

# Menu action definitions
_HEADER_ACTIONS = [
    ("Expand All", "expand"),
    ("Collapse All", "collapse"),
    None,
    ("New Collection", "new"),
]

_ITEM_ACTIONS = [
    ("Rename", "rename"),
    ("Duplicate", "dup"),
    None,
    ("Reveal in Finder", "reveal"),
    ("Get Info", "info"),
    None,
    ("Delete", "delete"),
]


class _View(NSOutlineView):
    """NSOutlineView subclass implementing data source, delegate, drag-drop, and menus."""

    _sl = objc_property(object, weak=True)

    # --- Data Source ---

    @objc_method
    def outlineView_numberOfChildrenOfItem_(self, ov, w) -> int:
        if item := _unwrap(w):
            return len(item.children)
        return len(self._sl._items) if self._sl else 0

    @objc_method
    def outlineView_child_ofItem_(self, ov, i: int, w):
        if not self._sl:
            return None
        item = _unwrap(w)
        child = item.children[i] if item else self._sl._items[i]
        return self._sl._wrap(child)

    @objc_method
    def outlineView_isItemExpandable_(self, ov, w) -> bool:
        item = _unwrap(w)
        return bool(item and (item.is_header or item.children))

    @objc_method
    def outlineView_objectValueForTableColumn_byItem_(self, ov, col, w):
        return ""

    # --- Selection & Display ---

    @objc_method
    def outlineView_shouldSelectItem_(self, ov, w) -> bool:
        item = _unwrap(w)
        return not item.is_header if item else True

    @objc_method
    def outlineViewSelectionDidChange_(self, n):
        if self._sl and self._sl.on_select and self._sl.selected:
            self._sl.on_select(self._sl.selected)

    @objc_method
    def outlineView_isGroupItem_(self, ov, w) -> bool:
        item = _unwrap(w)
        return item.is_header if item else False

    @objc_method
    def outlineView_heightOfRowByItem_(self, ov, w) -> float:
        item = _unwrap(w)
        return float(HEADER_HEIGHT if item and item.is_header else ROW_HEIGHT)

    @objc_method
    def outlineView_viewForTableColumn_item_(self, ov, col, w):
        item = _unwrap(w)
        if not item:
            return None

        cell = NSTableCellView.alloc().initWithFrame_(((0, 0), (200, ROW_HEIGHT)))

        if item.is_header:
            cell.addSubview_(_create_label(item.text, 4, 190, is_header=True))
        else:
            # Calculate right margin for trailing elements
            right_margin = 8
            if item.badge:
                right_margin += len(item.badge) * 8 + 8
            if item.trailing_icon:
                right_margin += ICON_SIZE + 4

            # Leading icon
            x = 4
            if item.icon:
                img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                    item.icon, None
                )
                if img:
                    img.setTemplate_(True)
                    iv = NSImageView.alloc().initWithFrame_(((4, 4), (ICON_SIZE, ICON_SIZE)))
                    iv.image = img
                    iv.contentTintColor = NSColor.secondaryLabelColor
                    cell.addSubview_(iv)
                    x = 4 + ICON_SIZE + 4

            # Text label
            cell.addSubview_(_create_label(item.text, x, 200 - x - right_margin))

            # Trailing icon
            trailing_x = 200 - 8
            if item.trailing_icon:
                trailing_x -= ICON_SIZE
                img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                    item.trailing_icon, None
                )
                if img:
                    img.setTemplate_(True)
                    iv = NSImageView.alloc().initWithFrame_(
                        ((trailing_x, 4), (ICON_SIZE, ICON_SIZE))
                    )
                    iv.image = img
                    iv.contentTintColor = NSColor.secondaryLabelColor
                    cell.addSubview_(iv)
                trailing_x -= 4

            # Badge text
            if item.badge:
                badge_width = len(item.badge) * 8 + 4
                trailing_x -= badge_width
                badge = NSTextField.alloc().initWithFrame_(
                    ((trailing_x, 4), (badge_width, 16))
                )
                badge.stringValue = item.badge
                badge.editable = False
                badge.bordered = False
                badge.drawsBackground = False
                badge.font = NSFont.systemFontOfSize_(11)
                badge.textColor = NSColor.secondaryLabelColor
                badge.alignment = _ALIGN_RIGHT
                cell.addSubview_(badge)

        return cell

    # --- Drag & Drop ---

    @objc_method
    def outlineView_pasteboardWriterForItem_(self, ov, w):
        item = _unwrap(w)
        if not item or item.is_header:
            return None
        pb = NSPasteboardItem.alloc().init()
        pb.setString_forType_(item.id, ITEM_UTI)
        return pb

    @objc_method
    def outlineView_validateDrop_proposedItem_proposedChildIndex_(
        self, ov, info, w, idx: int
    ) -> int:
        pb = info.draggingPasteboard
        src_id = str(pb.stringForType_(ITEM_UTI) or "")
        tgt = _unwrap(w)

        if not src_id:
            has_files = FILE_UTI in [str(t) for t in pb.types or []]
            return _DRAG_COPY if tgt and tgt.accepts_drops and has_files else _DRAG_NONE

        tgt_id = tgt.id if tgt else None
        if src_id == tgt_id and idx == -1:
            return _DRAG_NONE
        if idx == -1 and tgt and not tgt.is_header and not tgt.accepts_drops:
            return _DRAG_NONE

        return _DRAG_MOVE

    @objc_method
    def outlineView_acceptDrop_item_childIndex_(self, ov, info, w, idx: int) -> bool:
        if not self._sl:
            return False

        pb = info.draggingPasteboard
        src_id = str(pb.stringForType_(ITEM_UTI) or "")
        tgt = _unwrap(w)
        tgt_id = tgt.id if tgt else None

        if src_id and self._sl.on_reorder:
            self._sl.on_reorder(src_id, tgt_id, idx)
            return True

        if self._sl.on_file_drop:
            urls = pb.readObjectsForClasses_options_(NSArray.arrayWithObject_(NSURL), None)
            paths = [str(u.path) for u in (urls or []) if u.isFileURL()]
            if paths:
                self._sl.on_file_drop(tgt_id, paths)
                return True

        return False

    # --- Context Menu ---

    @objc_method
    def menuForEvent_(self, event):
        if not self._sl:
            return None

        pt = self.convertPoint_fromView_(event.locationInWindow, None)
        row = self.rowAtPoint_(pt)
        if row < 0:
            return None

        item = _unwrap(self.itemAtRow_(row))
        if not item:
            return None

        self.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(row), False)

        actions = _HEADER_ACTIONS if item.is_header else _ITEM_ACTIONS
        menu = NSMenu.alloc().initWithTitle_("")

        for action in actions:
            if action is None:
                menu.addItem_(NSMenuItem.separatorItem())
            else:
                title, cmd = action
                mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    title, SEL(f"do_{cmd}:"), ""
                )
                mi.target = self
                menu.addItem_(mi)

        return menu

    @objc_method
    def validateMenuItem_(self, item) -> bool:
        return True

    def _do(self, action: str):
        if self._sl and self._sl.on_action and self._sl.selected:
            self._sl.on_action(self._sl.selected, action)

    @objc_method
    def do_rename_(self, sender):
        self._do("rename")

    @objc_method
    def do_dup_(self, sender):
        self._do("duplicate")

    @objc_method
    def do_reveal_(self, sender):
        self._do("reveal")

    @objc_method
    def do_info_(self, sender):
        self._do("info")

    @objc_method
    def do_delete_(self, sender):
        self._do("delete")

    @objc_method
    def do_new_(self, sender):
        self._do("new")

    @objc_method
    def do_expand_(self, sender):
        if self._sl:
            for item in self._sl._items:
                if w := self._sl._cache.get(item.id):
                    self.expandItem_expandChildren_(w, True)

    @objc_method
    def do_collapse_(self, sender):
        if self._sl:
            for item in self._sl._items:
                if w := self._sl._cache.get(item.id):
                    self.collapseItem_collapseChildren_(w, True)


# =============================================================================
# SourceList (Public API)
# =============================================================================

class SourceList:
    """Native macOS sidebar using NSOutlineView.

    Args:
        on_select: Called when an item is selected.
            Signature: (item: SourceListItem) -> None
        on_reorder: Called when an item is dragged to a new location.
            Signature: (source_id: str, target_id: str | None, index: int) -> None
        on_file_drop: Called when files are dropped on an item.
            Signature: (target_id: str | None, paths: list[str]) -> None
        on_action: Called when context menu action is triggered.
            Signature: (item: SourceListItem, action: str) -> None
    """

    def __init__(
        self,
        on_select: Callable[[SourceListItem], None] | None = None,
        on_reorder: Callable[[str, str | None, int], None] | None = None,
        on_file_drop: Callable[[str | None, list[str]], None] | None = None,
        on_action: Callable[[SourceListItem, str], None] | None = None,
    ):
        self.on_select = on_select
        self.on_reorder = on_reorder
        self.on_file_drop = on_file_drop
        self.on_action = on_action
        self._items: list[SourceListItem] = []
        self._cache: dict[str, Any] = {}

        # Vibrancy view for translucent sidebar background
        self._vibrancy = NSVisualEffectView.alloc().initWithFrame_(((0, 0), (250, 400)))
        self._vibrancy.material = _MATERIAL_SIDEBAR
        self._vibrancy.blendingMode = _BLENDING_BEHIND_WINDOW
        self._vibrancy.state = _STATE_FOLLOWS_WINDOW

        # Scroll view
        self._scroll = NSScrollView.alloc().initWithFrame_(((0, 0), (250, 400)))
        self._scroll.hasVerticalScroller = True
        self._scroll.borderType = _BORDER_NONE
        self._scroll.autohidesScrollers = True
        self._scroll.drawsBackground = False

        # Outline view
        self._view = _View.alloc().initWithFrame_(self._scroll.contentView.bounds)
        self._view._sl = self
        self._view.headerView = None
        self._view.rowHeight = ROW_HEIGHT
        self._view.indentationPerLevel = INDENT
        self._view.usesDataSource = True
        self._view.dataSource = self._view
        self._view.delegate = self._view
        self._view.selectionHighlightStyle = _HIGHLIGHT_REGULAR
        self._view.floatsGroupRows = False
        self._view.backgroundColor = NSColor.clearColor
        self._view.drawsBackground = True
        self._view.wantsLayer = True
        self._view.draggingDestinationFeedbackStyle = _DRAG_FEEDBACK_REGULAR

        # Table column
        col = NSTableColumn.alloc().initWithIdentifier_("main")
        col.resizingMask = _COLUMN_RESIZE_AUTO
        self._view.addTableColumn_(col)
        self._view.outlineTableColumn = col
        self._view.registerForDraggedTypes_(NSArray.arrayWithArray_([ITEM_UTI, FILE_UTI]))

        # Assemble
        self._scroll.documentView = self._view
        self._vibrancy.addSubview_(self._scroll)
        self._scroll.setAutoresizingMask_(_AUTORESIZE_FLEX)

    @property
    def native(self):
        """The native NSVisualEffectView to add to a parent view."""
        return self._vibrancy

    @property
    def items(self) -> list[SourceListItem]:
        """The current list of root-level items."""
        return self._items

    @items.setter
    def items(self, value: list[SourceListItem]):
        """Set sidebar items and refresh display."""
        self._items = value
        self._cache.clear()
        self._view.reloadData()
        for item in self._items:
            if item.is_header:
                self._view.expandItem_(self._wrap(item))

    @property
    def selected(self) -> SourceListItem | None:
        """The currently selected item, or None."""
        row = self._view.selectedRow
        if row < 0:
            return None
        return getattr(self._view.itemAtRow_(row), "_py", None)

    def select(self, item_id: str) -> bool:
        """Select an item by ID and scroll it into view."""
        if w := self._cache.get(item_id):
            row = self._view.rowForItem_(w)
            if row >= 0:
                self._view.selectRowIndexes_byExtendingSelection_(
                    NSIndexSet.indexSetWithIndex_(row), False
                )
                return True
        return False

    def find(self, item_id: str) -> SourceListItem | None:
        """Find an item by ID anywhere in the hierarchy."""
        for item in self._items:
            if found := item.find(item_id):
                return found
        return None

    def _wrap(self, item: SourceListItem) -> Any:
        """Wrap a Python item in an ObjC object for NSOutlineView."""
        if item.id not in self._cache:
            w = NSObject.alloc().init()
            w._py = item
            self._cache[item.id] = w
        return self._cache[item.id]
