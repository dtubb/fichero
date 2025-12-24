"""
ObjC class definitions for native macOS sidebar.

All ObjC classes must be defined in one place for Rubicon-ObjC.
This file contains:
- MinWidthView: NSView subclass enforcing minimum width
- SidebarItem: Wrapper for Python data to avoid NSOutlineView introspection issues
- TogaSidebar: NSOutlineView subclass serving as data source and delegate

================================================================================
DRAG-DROP DELEGATE METHODS
================================================================================

NSOutlineView drag-drop follows Apple's delegate pattern. Key methods:

DRAG START:
-----------
pasteboardWriterForItem:(item)
    Called when user starts dragging. Write item ID to pasteboard.
    Returns: NSPasteboardItem with "com.fichero.collection.id" type

DRAG VALIDATION:
----------------
validateDrop:(drag_info, item, index)
    Called repeatedly as user drags over the view.

    Parameters:
    - item: The target item (or None for root)
    - index: Drop position indicator
        - index == -1: Dropping ON the item (blue highlight)
        - index >= 0: Dropping BETWEEN children at that index (insertion line)

    Actions:
    - Call setDropItem:dropChildIndex: to adjust visual feedback
    - Return NSDragOperationMove to accept, NSDragOperationNone to reject

    Validation rules:
    - Reject self-drop (item onto itself)
    - Reject drop onto non-containers (use insertion lines instead)
    - Accept section headers and folders with _can_accept_drops flag

DROP ACCEPTANCE:
----------------
acceptDrop:(drag_info, item, index)
    Called when user releases the drag.

    Parameters same as validateDrop.

    Actions:
    - Extract source ID from pasteboard
    - Determine parent_data and insert_index
    - Call self.interface.move_item_in_tree(source_id, parent_data, index)
    - Optionally call _on_reorder_callback for external updates

    Returns: True if drop was handled, False otherwise

VISUAL FEEDBACK:
----------------
The index parameter controls what macOS shows:

    index == -1:  Blue highlight on target (dropping INTO container)
                  ┌──────────────────┐
                  │▓▓▓▓ Section ▓▓▓▓│  <- highlighted blue
                  └──────────────────┘

    index >= 0:   Insertion line between items (reordering)
                  │   Item A         │
                  ├──────────────────┤  <- blue line at index 1
                  │   Item B         │

Use setDropItem:dropChildIndex: to explicitly set which feedback to show.

================================================================================
"""

import logging
from typing import Optional

from .constants import (
    RUBICON_AVAILABLE,
    load_objc_classes,
    LOCAL_REORDER_PASTEBOARD_TYPE,
    NS_OUTLINE_VIEW_DROP_ON_ITEM_INDEX,
    NS_TABLE_VIEW_DROP_ON,
    NS_TABLE_VIEW_DROP_ABOVE,
    NS_DRAG_OPERATION_NONE,
    NS_DRAG_OPERATION_COPY,
    NS_DRAG_OPERATION_MOVE,
)
from .tree_operations import get_item_id

logger = logging.getLogger(__name__)

# Cache for sidebar classes (created once, reused)
_sidebar_classes_cache = None


# Module-level storage for text field delegate instances (prevents garbage collection)
_text_field_delegates = {}


def _start_inline_edit_for_row(outline_view, row: int) -> None:
    """
    Module-level helper to start inline editing for a row.

    This is extracted as a module-level function because methods defined
    inside the Rubicon-ObjC class definition are not accessible as regular
    Python methods from within @objc_method decorated functions.

    Args:
        outline_view: The NSOutlineView instance (TogaSidebar)
        row: The row index to edit
    """
    if row < 0:
        return

    # Check if section header (not renameable)
    try:
        item = outline_view.itemAtRow_(row)
        if item and hasattr(item, '_python_data'):
            data = item._python_data
            if isinstance(data, dict) and data.get('_is_section_header', False):
                logger.debug("Cannot rename section header")
                return
    except Exception:
        pass

    try:
        # Get the cell view and text field
        cell_view = outline_view.viewAtColumn_row_makeIfNecessary_(0, row, False)
        if not cell_view or not cell_view.textField:
            logger.warning(f"No text field found for row {row}")
            return

        text_field = cell_view.textField

        # Store original text for cancel (use module-level dict keyed by outline_view ptr)
        ptr = int(outline_view.ptr.value) if hasattr(outline_view, 'ptr') else id(outline_view)
        if not hasattr(_start_inline_edit_for_row, '_editing_state'):
            _start_inline_edit_for_row._editing_state = {}
        _start_inline_edit_for_row._editing_state[ptr] = {
            'row': row,
            'original_text': str(text_field.stringValue),
            'text_field': text_field
        }

        # Make editable and start editing
        text_field.editable = True

        # Set the text field to send its action (Enter key) to the outline view
        # This is the safe way to handle Enter key without using delegates
        from rubicon.objc import SEL
        text_field.target = outline_view
        text_field.action = SEL('textFieldAction:')

        outline_view.window.makeFirstResponder_(text_field)

        # Select all text for easy replacement
        text_field.selectText_(None)

        logger.debug(f"Started inline edit for row {row}")

    except Exception as e:
        logger.error(f"Error starting inline edit: {e}", exc_info=True)


def _get_editing_state(outline_view):
    """Get the editing state for an outline view."""
    if not hasattr(_start_inline_edit_for_row, '_editing_state'):
        return None
    ptr = int(outline_view.ptr.value) if hasattr(outline_view, 'ptr') else id(outline_view)
    return _start_inline_edit_for_row._editing_state.get(ptr)


def _clear_editing_state(outline_view):
    """Clear the editing state for an outline view."""
    if hasattr(_start_inline_edit_for_row, '_editing_state'):
        ptr = int(outline_view.ptr.value) if hasattr(outline_view, 'ptr') else id(outline_view)
        _start_inline_edit_for_row._editing_state.pop(ptr, None)


def _finish_inline_edit_if_needed(outline_view, cancel: bool = False) -> bool:
    """
    Finish inline editing if in progress.

    This is called when the user clicks elsewhere or when we need to finalize
    the edit (e.g., clicking on another row, pressing Enter via keyDown).

    Args:
        outline_view: The NSOutlineView instance
        cancel: If True, cancel the edit and restore original text

    Returns:
        True if we were editing and finished, False if not editing
    """
    editing_state = _get_editing_state(outline_view)
    if not editing_state:
        return False

    row = editing_state.get('row', -1)
    original = editing_state.get('original_text', '')
    text_field = editing_state.get('text_field')

    # Clear state first to prevent re-entry
    _clear_editing_state(outline_view)

    if row < 0 or not text_field:
        return True

    try:
        # Get the current text
        new_name = str(text_field.stringValue).strip() if text_field else ''

        # Reset text field to non-editable
        text_field.editable = False

        if cancel:
            # Restore original text
            text_field.stringValue = original or ''
            logger.debug("Rename cancelled")
            return True

        # Validate new name
        if not new_name:
            text_field.stringValue = original or ''
            logger.debug("Rename cancelled: empty name")
            return True

        if new_name == original:
            logger.debug("Rename unchanged")
            return True

        # Get item data for callback
        item_data = {}
        try:
            item = outline_view.itemAtRow_(row)
            if item and hasattr(item, '_python_data'):
                item_data = item._python_data if isinstance(item._python_data, dict) else {}
        except Exception:
            pass

        # Get item ID for callback
        item_id = None
        collection_data = item_data.get('_collection_data')
        if collection_data:
            item_id = collection_data.get('id')
        if not item_id:
            item_id = item_data.get('_item_id') or item_data.get('text')

        # Call the rename callback
        if item_id and outline_view.interface and hasattr(outline_view.interface, '_on_rename_callback'):
            callback = outline_view.interface._on_rename_callback
            if callback:
                logger.info(f"Rename: '{original}' -> '{new_name}' (id: {item_id})")
                try:
                    callback(item_id, new_name)
                except Exception as e:
                    logger.error(f"Error in rename callback: {e}")
            else:
                logger.warning("No rename callback registered")
        else:
            logger.warning(f"Cannot complete rename: item_id={item_id}")

        return True

    except Exception as e:
        logger.error(f"Error finishing inline edit: {e}", exc_info=True)
        return True


def create_sidebar_classes():
    """Create sidebar classes after ObjC classes are loaded (cached after first call)."""
    global _sidebar_classes_cache

    # Return cached classes if already created
    if _sidebar_classes_cache is not None:
        return _sidebar_classes_cache

    if not RUBICON_AVAILABLE:
        _sidebar_classes_cache = (None, None, None)
        return None, None, None

    load_objc_classes()

    from rubicon.objc import ObjCClass, objc_method, objc_property, SEL

    # Import NSView for custom wrapper
    NSView = ObjCClass("NSView")
    NSOutlineView = ObjCClass("NSOutlineView")
    NSObject = ObjCClass("NSObject")

    # =========================================================================
    # MinWidthView - NSView subclass that enforces minimum width
    # =========================================================================

    class MinWidthView(NSView):
        """NSView subclass that enforces a minimum width."""

        minimum_width = objc_property(float)

        @objc_method
        def setFrame_(self, frame):
            """Override setFrame to enforce minimum width."""
            new_frame = frame

            if hasattr(self, 'minimum_width') and self.minimum_width > 0:
                if new_frame.size.width < self.minimum_width:
                    logger.debug(f"Enforcing minimum width: {new_frame.size.width}px -> {self.minimum_width}px")
                    new_frame.size.width = self.minimum_width

            super().setFrame_(new_frame)

    # =========================================================================
    # SidebarItem - Wrapper for Python data
    # =========================================================================

    class SidebarItem(NSObject):
        """Wrapper for sidebar item data to avoid NSOutlineView introspection issues."""

        def __init__(self):
            super().__init__()
            self._python_data = {}

        @objc_method
        def get_data(self):
            """Get the stored Python dict."""
            return self._python_data

        @objc_method
        def set_data_(self, value):
            """Set the stored Python dict."""
            self._python_data = value

        def __repr__(self):
            """String representation for debugging."""
            if self._python_data and isinstance(self._python_data, dict):
                text = self._python_data.get('text', '<no text>')
                return f"<SidebarItem: {text}>"
            return "<SidebarItem: no data>"

    # =========================================================================
    # TogaSidebar - Main NSOutlineView subclass
    # =========================================================================

    class TogaSidebar(NSOutlineView):
        """
        NSOutlineView subclass that serves as both data source and delegate.

        Follows Toga's pattern from TogaTree implementation.
        Organized into sections:
        1. Data Source Methods
        2. Selection Delegate Methods
        3. Row Display Delegate Methods
        4. Cell Display Delegate Methods
        5. Drag and Drop Methods (following Apple's DragNDropOutlineView pattern)
        6. Contextual Menu
        7. Inline Editing (Finder-like rename)
        """

        # Weak reference to Python interface to prevent retain cycles
        interface = objc_property(object, weak=True)

        # =====================================================================
        # INLINE EDITING STATE (initialized in first use)
        # =====================================================================
        # _editing_row: int - Row being edited (-1 if none)
        # _editing_original_text: str - Original text for cancel/escape
        # _last_click_row: int - Last clicked row for slow double-click detection
        # _last_click_time: float - Time of last click for slow double-click

        # =====================================================================
        # SECTION 1: DATA SOURCE METHODS
        # =====================================================================

        @objc_method
        def outlineView_numberOfChildrenOfItem_(self, outline_view, item) -> int:
            """Return number of children for item (None = root)."""
            try:
                if item is None:
                    if self.interface and hasattr(self.interface, '_data') and self.interface._data:
                        count = len(self.interface._data)
                        logger.debug(f"Root level: {count} items")
                        return count
                    return 0

                if self.interface and hasattr(self.interface, '_get_children_callback'):
                    item_data = item._python_data
                    item_name = item_data.get('text', '?') if isinstance(item_data, dict) else str(item_data)
                    children = self.interface._get_children_callback(item_data)
                    if children is not None:
                        child_names = [c.get('text', '?') for c in children]
                        logger.debug(f"numberOfChildren('{item_name}'): {len(children)} -> {child_names}")
                        return len(children)

                return 0
            except Exception as e:
                logger.error(f"Error in numberOfChildrenOfItem: {e}", exc_info=True)
                return 0

        @objc_method
        def outlineView_child_ofItem_(self, outline_view, index: int, item):
            """Return child at index for item (None = root).

            IMPORTANT: Child wrappers must be STABLE (cached) for drag-drop
            to work without crashing. Following demo_toga_pattern.py, we store
            the wrapper directly on the item dict as '_impl'. This ensures
            NSOutlineView always gets the same wrapper after reloadData().
            """
            try:
                if item is None:
                    if self.interface and hasattr(self.interface, '_wrapped_items'):
                        if 0 <= index < len(self.interface._wrapped_items):
                            return self.interface._wrapped_items[index]
                    return None

                if self.interface and hasattr(self.interface, '_get_children_callback'):
                    children = self.interface._get_children_callback(item._python_data)
                    if children is not None and 0 <= index < len(children):
                        child_data = children[index]

                        # Return wrapper from item's _impl (stable identity like demo)
                        if '_impl' in child_data and child_data['_impl'] is not None:
                            return child_data['_impl']

                        # Fallback to interface method which stores _impl on item
                        if hasattr(self.interface, '_get_or_create_wrapper'):
                            return self.interface._get_or_create_wrapper(child_data)
                        else:
                            # Last resort fallback (shouldn't happen)
                            child_item = SidebarItem.alloc().init()
                            child_item._python_data = child_data
                            child_data['_impl'] = child_item
                            return child_item

                return None
            except Exception as e:
                logger.error(f"Error in child_ofItem: {e}", exc_info=True)
                return None

        @objc_method
        def outlineView_isItemExpandable_(self, outline_view, item) -> bool:
            """Return True if item has children."""
            try:
                if hasattr(item, '_python_data'):
                    data_value = item._python_data
                    if isinstance(data_value, dict):
                        node_type = data_value.get('_node_type')
                        if node_type in ('section', 'collection', 'folder'):
                            return data_value.get('_has_children', False)
                return False
            except Exception as e:
                logger.error(f"Error in isItemExpandable: {e}", exc_info=True)
                return False

        @objc_method
        def outlineView_objectValueForTableColumn_byItem_(self, outline_view, table_column, item):
            """Return value for table column (not used in view-based mode)."""
            if item is None:
                return ""
            return ""

        # =====================================================================
        # SECTION 2: SELECTION DELEGATE METHODS
        # =====================================================================

        @objc_method
        def outlineView_shouldSelectItem_(self, outline_view, item) -> bool:
            """Return True if item should be selectable."""
            try:
                if hasattr(item, '_python_data'):
                    data_value = item._python_data
                    if isinstance(data_value, dict):
                        if data_value.get('_is_section_header', False):
                            logger.debug(f"Blocking selection of section header: {data_value.get('text')}")
                            return False
                return True
            except Exception as e:
                logger.error(f"Error in shouldSelectItem: {e}", exc_info=True)
                return True

        @objc_method
        def outlineViewSelectionDidChange_(self, notification):
            """Handle selection change."""
            if self.interface and self.interface._on_select_callback:
                selected_row = self.selectedRow
                if selected_row >= 0:
                    item = self.itemAtRow(selected_row)
                    if item:
                        try:
                            if hasattr(item, '_python_data'):
                                data_item = item._python_data
                            else:
                                data_item = item
                            self.interface._on_select_callback(data_item)
                        except Exception as e:
                            logger.error(f"Error in selection callback: {e}")

        # =====================================================================
        # SECTION 3: ROW DISPLAY DELEGATE METHODS
        # =====================================================================

        @objc_method
        def outlineView_heightOfRowByItem_(self, outline_view, item) -> float:
            """Return height for row containing item."""
            try:
                if hasattr(item, '_python_data'):
                    data_value = item._python_data
                    if isinstance(data_value, dict):
                        if data_value.get('_is_section_header', False):
                            return 28.0
                return 24.0
            except Exception as e:
                logger.error(f"Error in heightOfRowByItem: {e}", exc_info=True)
                return 24.0

        @objc_method
        def outlineView_rowViewForItem_(self, outline_view, item):
            """
            Return row view for item.

            NOTE: Returning None lets NSOutlineView use its default row view,
            which properly draws drag destination feedback (insertion lines).
            Custom row views with background colors can interfere with drop indicators.
            """
            # Return None to use default row view for proper drop feedback
            return None

        @objc_method
        def outlineView_indentationForItem_(self, outline_view, item) -> float:
            """Return custom indentation for item."""
            try:
                level = outline_view.levelForItem_(item)
                if level <= 1:
                    return -8.0
                elif level == 2:
                    return 0.0
                else:
                    return (level - 2) * 8.0
            except Exception as e:
                logger.error(f"Error in indentationForItem: {e}", exc_info=True)
                return 0.0

        @objc_method
        def outlineView_shouldShowOutlineCellForItem_(self, outline_view, item) -> bool:
            """Return False to hide disclosure triangle for section headers."""
            try:
                if hasattr(item, '_python_data'):
                    data_value = item._python_data
                    if isinstance(data_value, dict):
                        if data_value.get('_is_section_header', False):
                            return False
                return True
            except Exception as e:
                logger.error(f"Error in shouldShowOutlineCellForItem: {e}", exc_info=True)
                return True

        @objc_method
        def outlineView_isGroupItem_(self, outline_view, item) -> bool:
            """
            Return True for section headers to mark them as group items.

            Group items display with uppercase/smaller font styling.
            Insertion lines inside groups now work because child wrappers are cached.
            """
            try:
                if item is not None and hasattr(item, '_python_data'):
                    data_value = item._python_data
                    if isinstance(data_value, dict):
                        return data_value.get('_is_section_header', False)
                return False
            except Exception as e:
                logger.error(f"Error in isGroupItem: {e}", exc_info=True)
                return False

        # =====================================================================
        # SECTION 4: CELL DISPLAY DELEGATE METHODS
        # =====================================================================

        @objc_method
        def outlineView_frameOfOutlineCellAtRow_(self, outline_view, row: int):
            """Return frame for disclosure triangle at row."""
            try:
                from rubicon.objc import CGRect

                item = outline_view.itemAtRow(row)
                if item is None:
                    return None

                level = outline_view.levelForItem_(item)
                BASE_INDENT = 5

                if level <= 1:
                    icon_x = BASE_INDENT
                    triangle_x = icon_x - 5.0
                else:
                    icon_x = BASE_INDENT + (level - 1) * 16.0
                    triangle_x = icon_x - 5.0

                frame = CGRect(((triangle_x, 4), (16, 16)))
                return frame
            except Exception as e:
                logger.debug(f"Error setting disclosure triangle frame: {e}")
                return None

        @objc_method
        def outlineView_viewForTableColumn_item_(self, outline_view, table_column, item):
            """Return view for table column and item."""
            if item is None:
                return None

            try:
                has_python_data = hasattr(item, '_python_data')
                data_value = item._python_data if has_python_data else None
                is_dict = isinstance(data_value, dict)

                if has_python_data and is_dict:
                    text = data_value.get('text', '')
                    icon_name = data_value.get('icon', None)
                    is_section_header = data_value.get('_is_section_header', False)
                    badge_text = data_value.get('badge_text', None)
                    trailing_icon = data_value.get('trailing_icon', None)
                else:
                    text = str(item)
                    icon_name = None
                    is_section_header = False
                    badge_text = None
                    trailing_icon = None

                NSTableCellView = ObjCClass("NSTableCellView")
                NSTextField = ObjCClass("NSTextField")
                NSColor = ObjCClass("NSColor")
                NSFont = ObjCClass("NSFont")
                NSImage = ObjCClass("NSImage")
                NSImageView = ObjCClass("NSImageView")

                identifier = "SectionHeaderCell" if is_section_header else "IconTextCell"
                view = outline_view.makeViewWithIdentifier(identifier, owner=outline_view)

                item_level = outline_view.levelForItem_(item) if item else 0
                BASE_INDENT = 5
                icon_x = BASE_INDENT
                text_x = icon_x + 18

                CELL_WIDTH = int(self.interface._current_cell_width) if hasattr(self.interface, '_current_cell_width') else 165

                right_margin = 20
                if badge_text:
                    badge_chars = len(str(badge_text))
                    badge_width = max(12, badge_chars * 10)
                    right_margin += badge_width + 16
                if trailing_icon:
                    right_margin += 18

                width_reduction = 9 + (item_level * 8) if item_level > 0 else 9
                effective_cell_width = CELL_WIDTH - width_reduction
                TEXT_WIDTH = int(effective_cell_width - text_x - right_margin)

                if view is None:
                    view = NSTableCellView.alloc().initWithFrame(((0, 0), (CELL_WIDTH, 24)))
                    view.identifier = identifier
                    view.wantsLayer = False

                    if is_section_header:
                        text_field = NSTextField.alloc().initWithFrame(((0, 3), (CELL_WIDTH - 8, 18)))
                        text_field.editable = False
                        text_field.bordered = False
                        text_field.drawsBackground = False
                        text_field.font = NSFont.systemFontOfSize_weight_(11, 0.5)
                        text_field.textColor = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                            0xA3 / 255.0, 0x9F / 255.0, 0xA2 / 255.0, 1.0
                        )
                        view.textField = text_field
                        view.addSubview(text_field)
                        view.imageView = None
                    else:
                        image_view = NSImageView.alloc().initWithFrame(((icon_x, 7), (14, 14)))
                        image_view.imageScaling = 1
                        if hasattr(image_view, 'contentTintColor'):
                            image_view.contentTintColor = NSColor.secondaryLabelColor
                        view.imageView = image_view
                        view.addSubview(image_view)

                        text_field = NSTextField.alloc().initWithFrame(((text_x, 6), (TEXT_WIDTH, 16)))
                        text_field.editable = False
                        text_field.bordered = False
                        text_field.drawsBackground = False
                        font = self.interface._get_font_for_item(data_value, self.interface.sidebar_font_size)
                        text_field.font = font
                        text_field.autoresizingMask = 0
                        text_field.cell.usesSingleLineMode = True
                        text_field.cell.scrollable = False
                        text_field.cell.lineBreakMode = 4
                        text_field.cell.truncatesLastVisibleLine = True
                        text_field.cell.wraps = False
                        view.textField = text_field
                        view.addSubview(text_field)
                else:
                    if view.textField:
                        if is_section_header:
                            view.textField.setFrame(((0, 3), (CELL_WIDTH - 8, 18)))
                        else:
                            view.textField.setFrame(((text_x, 6), (TEXT_WIDTH, 16)))
                    if view.imageView and not is_section_header:
                        view.imageView.setFrame(((icon_x, 7), (14, 14)))

                if view.textField:
                    view.textField.stringValue = text
                    if is_section_header:
                        view.textField.font = NSFont.systemFontOfSize_weight_(11, 0.5)
                        view.textField.textColor = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                            0xA3 / 255.0, 0x9F / 255.0, 0xA2 / 255.0, 1.0
                        )
                    else:
                        font = self.interface._get_font_for_item(data_value, self.interface.sidebar_font_size)
                        view.textField.font = font
                        view.textField.textColor = NSColor.labelColor
                        view.textField.cell.lineBreakMode = 4
                        view.textField.cell.truncatesLastVisibleLine = True

                if view.imageView and not is_section_header:
                    if text and text.lower() == "inbox":
                        inbox_icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_("tray.fill", "Inbox")
                        if inbox_icon:
                            inbox_icon.setTemplate(True)
                            view.imageView.image = inbox_icon
                        else:
                            folder_icon = NSImage.imageNamed("NSFolder")
                            if folder_icon:
                                folder_icon.setTemplate(True)
                            view.imageView.image = folder_icon
                    elif icon_name:
                        # Handle different icon types:
                        # - String: icon name for NSImage.imageNamed()
                        # - toga.images.Image: extract native NSImage
                        # - Other: fallback to folder icon
                        icon = None
                        if isinstance(icon_name, str):
                            icon = NSImage.imageNamed(icon_name)
                        elif hasattr(icon_name, '_impl') and hasattr(icon_name._impl, 'native'):
                            # toga.images.Image has _impl.native which is NSImage
                            icon = icon_name._impl.native

                        if icon:
                            # Only set template mode for string-based icons (system icons)
                            if isinstance(icon_name, str):
                                icon.setTemplate(True)
                            view.imageView.image = icon
                        else:
                            folder_icon = NSImage.imageNamed("NSFolder")
                            if folder_icon:
                                folder_icon.setTemplate(True)
                            view.imageView.image = folder_icon
                    else:
                        folder_icon = NSImage.imageNamed("NSFolder")
                        if folder_icon:
                            folder_icon.setTemplate(True)
                        view.imageView.image = folder_icon

                # Trailing elements (badges and icons)
                if not is_section_header:
                    for subview in list(view.subviews):
                        if hasattr(subview, 'identifier'):
                            ident = str(subview.identifier) if subview.identifier else ''
                            if ident in ('BadgeLabel', 'BadgeBG', 'TrailingIcon'):
                                subview.removeFromSuperview()

                    width_reduction = 9 + (item_level * 8) if item_level > 0 else 9
                    expected_cell_width = CELL_WIDTH - width_reduction
                    BASE_MARGIN = 35
                    trailing_offset = expected_cell_width - BASE_MARGIN

                    if trailing_icon:
                        icon_view = NSImageView.alloc().initWithFrame(((trailing_offset - 14, 7), (14, 14)))
                        icon_view.imageScaling = 1
                        icon_view.identifier = 'TrailingIcon'
                        icon_image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(trailing_icon, None)
                        if icon_image:
                            icon_image.setTemplate(True)
                            icon_view.image = icon_image
                            if hasattr(icon_view, 'contentTintColor'):
                                icon_view.contentTintColor = NSColor.secondaryLabelColor
                            view.addSubview(icon_view)
                            trailing_offset -= 18

                    if badge_text:
                        badge_str = str(badge_text)
                        badge_width = max(12, len(badge_str) * 10)
                        badge_label = NSTextField.alloc().initWithFrame(((trailing_offset - badge_width, 6), (badge_width, 16)))
                        badge_label.stringValue = badge_str
                        badge_label.editable = False
                        badge_label.bordered = False
                        badge_label.drawsBackground = False
                        badge_label.font = NSFont.systemFontOfSize(12)
                        badge_label.textColor = NSColor.secondaryLabelColor
                        badge_label.alignment = 1
                        badge_label.identifier = 'BadgeLabel'
                        badge_label.cell.usesSingleLineMode = True
                        badge_label.cell.truncatesLastVisibleLine = True
                        view.addSubview(badge_label)

                return view

            except Exception as e:
                logger.error(f"Error creating view: {e}", exc_info=True)
                return None

        @objc_method
        def frameDidChange_(self, notification):
            """Handle frame changes to update column width."""
            try:
                if self.interface and hasattr(self.interface, '_update_column_width_from_container'):
                    self.interface._update_column_width_from_container()
            except Exception as e:
                logger.debug(f"Error in frameDidChange: {e}")

        # =====================================================================
        # SECTION 5: CONTEXTUAL MENU
        # =====================================================================

        @objc_method
        def menuForEvent_(self, event):
            """
            Override menuForEvent: to provide contextual menus on right-click.

            NSOutlineView doesn't automatically call the delegate method
            outlineView:menuForTableColumn:item: - we must override menuForEvent:
            and determine which item was clicked, then build the menu ourselves.
            """
            try:
                # Get click location and convert to outline view coordinates
                point = self.convertPoint_fromView_(event.locationInWindow, None)
                row = self.rowAtPoint_(point)

                if row < 0:
                    # Clicked on empty area - no menu
                    return None

                # Get the item at this row
                item = self.itemAtRow_(row)

                # Select the clicked row for visual feedback
                NSIndexSet = ObjCClass("NSIndexSet")
                index_set = NSIndexSet.indexSetWithIndex_(row)
                self.selectRowIndexes_byExtendingSelection_(index_set, False)

                # Build and return the menu
                return self.outlineView_menuForTableColumn_item_(self, None, item)
            except Exception as e:
                logger.error(f"Error in menuForEvent: {e}", exc_info=True)
                return None

        @objc_method
        def outlineView_menuForTableColumn_item_(self, outline_view, table_column, item):
            """Provide contextual menu for right-click on item."""
            try:
                data_item = None
                if item is not None:
                    if hasattr(item, '_python_data'):
                        data_item = item._python_data
                    else:
                        data_item = item

                NSMenu = ObjCClass("NSMenu")
                NSMenuItem = ObjCClass("NSMenuItem")

                menu = NSMenu.alloc().initWithTitle("Contextual Menu")

                is_section_header = False
                node_type = None
                if data_item and isinstance(data_item, dict):
                    is_section_header = data_item.get('_is_section_header', False)
                    node_type = data_item.get('_node_type', 'collection')

                # Store the clicked item for menu action handlers
                self._context_menu_item = data_item

                if is_section_header:
                    # Section header menu
                    expand_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        "Expand All", SEL('performExpandAll:'), ""
                    )
                    collapse_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        "Collapse All", SEL('performCollapseAll:'), ""
                    )
                    menu.addItem(expand_item)
                    menu.addItem(collapse_item)

                    # Add "New Collection" for sections
                    menu.addItem(NSMenuItem.separatorItem())
                    new_collection_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        "New Collection", SEL('performNewCollection:'), ""
                    )
                    menu.addItem(new_collection_item)
                else:
                    # Collection/item menu
                    # Rename (no ellipsis - inline edit, not opening a dialog)
                    rename_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        "Rename", SEL('performRename:'), ""
                    )
                    menu.addItem(rename_item)

                    # Duplicate
                    duplicate_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        "Duplicate", SEL('performDuplicate:'), ""
                    )
                    menu.addItem(duplicate_item)

                    menu.addItem(NSMenuItem.separatorItem())

                    # Reveal in Finder
                    reveal_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        "Reveal in Finder", SEL('performRevealInFinder:'), ""
                    )
                    menu.addItem(reveal_item)

                    # Get Info
                    info_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        "Get Info", SEL('performGetInfo:'), ""
                    )
                    menu.addItem(info_item)

                    # Export Collection removed - not implemented yet

                    menu.addItem(NSMenuItem.separatorItem())

                    # Delete
                    delete_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        "Delete", SEL('performDelete:'), ""
                    )
                    menu.addItem(delete_item)

                return menu
            except Exception as e:
                logger.error(f"Error creating contextual menu: {e}", exc_info=True)
                return None

        # =====================================================================
        # SECTION 6B: CONTEXTUAL MENU ACTION HANDLERS
        # =====================================================================

        @objc_method
        def performRename_(self, sender) -> None:
            """Handle Rename menu action - starts inline editing."""
            try:
                row = self.selectedRow
                if row >= 0:
                    # Use module-level helper since Python methods aren't accessible
                    # from @objc_method decorated functions in Rubicon-ObjC
                    _start_inline_edit_for_row(self, row)
            except Exception as e:
                logger.error(f"Error in performRename: {e}", exc_info=True)

        @objc_method
        def textFieldAction_(self, sender) -> None:
            """Handle Enter key in text field during inline editing.

            This is the target-action handler for the text field.
            When the user presses Enter during inline editing, the text field
            sends its action to its target (this outline view).
            """
            try:
                logger.debug("textFieldAction_ called - Enter pressed in text field")
                _finish_inline_edit_if_needed(self, cancel=False)
            except Exception as e:
                logger.error(f"Error in textFieldAction: {e}", exc_info=True)

        @objc_method
        def performDuplicate_(self, sender) -> None:
            """Handle Duplicate menu action."""
            try:
                if hasattr(self, '_context_menu_item') and self._context_menu_item:
                    item_data = self._context_menu_item
                    if self.interface and hasattr(self.interface, '_on_context_menu_callback'):
                        callback = self.interface._on_context_menu_callback
                        if callback:
                            callback('duplicate', item_data)
                    logger.debug(f"Duplicate requested for: {item_data.get('text', 'unknown')}")
            except Exception as e:
                logger.error(f"Error in performDuplicate: {e}", exc_info=True)

        @objc_method
        def performRevealInFinder_(self, sender) -> None:
            """Handle Reveal in Finder menu action."""
            try:
                if hasattr(self, '_context_menu_item') and self._context_menu_item:
                    item_data = self._context_menu_item
                    if self.interface and hasattr(self.interface, '_on_context_menu_callback'):
                        callback = self.interface._on_context_menu_callback
                        if callback:
                            callback('reveal_in_finder', item_data)
                    logger.debug(f"Reveal in Finder requested for: {item_data.get('text', 'unknown')}")
            except Exception as e:
                logger.error(f"Error in performRevealInFinder: {e}", exc_info=True)

        @objc_method
        def performGetInfo_(self, sender) -> None:
            """Handle Get Info menu action."""
            try:
                if hasattr(self, '_context_menu_item') and self._context_menu_item:
                    item_data = self._context_menu_item
                    if self.interface and hasattr(self.interface, '_on_context_menu_callback'):
                        callback = self.interface._on_context_menu_callback
                        if callback:
                            callback('get_info', item_data)
                    logger.debug(f"Get Info requested for: {item_data.get('text', 'unknown')}")
            except Exception as e:
                logger.error(f"Error in performGetInfo: {e}", exc_info=True)

        @objc_method
        def performExport_(self, sender) -> None:
            """Handle Export Collection menu action."""
            try:
                if hasattr(self, '_context_menu_item') and self._context_menu_item:
                    item_data = self._context_menu_item
                    if self.interface and hasattr(self.interface, '_on_context_menu_callback'):
                        callback = self.interface._on_context_menu_callback
                        if callback:
                            callback('export', item_data)
                    logger.debug(f"Export requested for: {item_data.get('text', 'unknown')}")
            except Exception as e:
                logger.error(f"Error in performExport: {e}", exc_info=True)

        @objc_method
        def performDelete_(self, sender) -> None:
            """Handle Delete menu action."""
            try:
                if hasattr(self, '_context_menu_item') and self._context_menu_item:
                    item_data = self._context_menu_item
                    if self.interface and hasattr(self.interface, '_on_context_menu_callback'):
                        callback = self.interface._on_context_menu_callback
                        if callback:
                            callback('delete', item_data)
                    logger.debug(f"Delete requested for: {item_data.get('text', 'unknown')}")
            except Exception as e:
                logger.error(f"Error in performDelete: {e}", exc_info=True)

        @objc_method
        def performNewCollection_(self, sender) -> None:
            """Handle New Collection menu action (for section headers)."""
            try:
                if hasattr(self, '_context_menu_item') and self._context_menu_item:
                    item_data = self._context_menu_item
                    if self.interface and hasattr(self.interface, '_on_context_menu_callback'):
                        callback = self.interface._on_context_menu_callback
                        if callback:
                            callback('new_collection', item_data)
                    logger.debug(f"New Collection requested in section: {item_data.get('text', 'unknown')}")
            except Exception as e:
                logger.error(f"Error in performNewCollection: {e}", exc_info=True)

        @objc_method
        def performExpandAll_(self, sender) -> None:
            """Handle Expand All menu action."""
            try:
                if hasattr(self, '_context_menu_item') and self._context_menu_item:
                    # Find the wrapper for this item and expand it with children
                    item_data = self._context_menu_item
                    item_id = get_item_id(item_data)
                    if item_id and self.interface and hasattr(self.interface, '_item_cache'):
                        wrapper = self.interface._item_cache.get(item_id)
                        if wrapper:
                            self.expandItem_expandChildren_(wrapper, True)
                    logger.debug(f"Expand All executed for: {item_data.get('text', 'unknown')}")
            except Exception as e:
                logger.error(f"Error in performExpandAll: {e}", exc_info=True)

        @objc_method
        def performCollapseAll_(self, sender) -> None:
            """Handle Collapse All menu action."""
            try:
                if hasattr(self, '_context_menu_item') and self._context_menu_item:
                    # Find the wrapper for this item and collapse it with children
                    item_data = self._context_menu_item
                    item_id = get_item_id(item_data)
                    if item_id and self.interface and hasattr(self.interface, '_item_cache'):
                        wrapper = self.interface._item_cache.get(item_id)
                        if wrapper:
                            self.collapseItem_collapseChildren_(wrapper, True)
                    logger.debug(f"Collapse All executed for: {item_data.get('text', 'unknown')}")
            except Exception as e:
                logger.error(f"Error in performCollapseAll: {e}", exc_info=True)

        # =====================================================================
        # SECTION 6: EXPAND/COLLAPSE WITH OPTION KEY (Finder-like behavior)
        # =====================================================================

        @objc_method
        def outlineViewItemWillExpand_(self, notification) -> None:
            """
            Called when an item is about to expand.

            If Option key is held, expand all children recursively (like Finder).
            This provides Finder-like behavior: Option+click expands entire subtree.
            """
            try:
                # Get current event from NSApplication
                NSApplication = ObjCClass("NSApplication")
                app = NSApplication.sharedApplication
                event = app.currentEvent

                if event is None:
                    return

                # NSEventModifierFlagOption = 1 << 19 = 524288
                OPTION_KEY_MASK = 524288

                # Access modifierFlags as integer
                flags = int(event.modifierFlags)

                if flags & OPTION_KEY_MASK:
                    # Get the item being expanded from the notification
                    user_info = notification.userInfo
                    if user_info:
                        item = user_info.objectForKey_("NSObject")
                        if item:
                            # Mark for deferred expand
                            self._pending_option_expand = item
                            logger.debug(f"Option+expand detected, will expand children")

            except Exception as e:
                logger.debug(f"Error in outlineViewItemWillExpand: {e}")

        @objc_method
        def outlineViewItemDidExpand_(self, notification) -> None:
            """
            Called after an item has expanded.

            If Option key was held during expand, now expand all children.
            """
            try:
                if hasattr(self, '_pending_option_expand') and self._pending_option_expand:
                    item = self._pending_option_expand
                    self._pending_option_expand = None

                    # Expand all children recursively
                    self.expandItem_expandChildren_(item, True)
                    logger.debug(f"Option+expand: expanded all children")

            except Exception as e:
                logger.debug(f"Error in outlineViewItemDidExpand: {e}")

        @objc_method
        def outlineViewItemWillCollapse_(self, notification) -> None:
            """
            Called when an item is about to collapse.

            If Option key is held, collapse all children recursively (like Finder).
            """
            try:
                NSApp = ObjCClass("NSApplication").sharedApplication
                current_event = NSApp.currentEvent
                if current_event is None:
                    return

                # Get modifier flags from current event
                modifier_flags = current_event.modifierFlags

                # NSEventModifierFlagOption = 1 << 19 = 524288
                OPTION_KEY_MASK = 524288

                if modifier_flags & OPTION_KEY_MASK:
                    # Get the item being collapsed
                    item = notification.userInfo.objectForKey_("NSObject")
                    if item:
                        # Schedule deferred collapse of children
                        if hasattr(self, '_pending_option_collapse'):
                            self._pending_option_collapse = item
                        else:
                            self._pending_option_collapse = item

                        logger.debug(f"Option+collapse detected, will collapse children")

            except Exception as e:
                logger.debug(f"Error in outlineViewItemWillCollapse: {e}")

        @objc_method
        def outlineViewItemDidCollapse_(self, notification) -> None:
            """
            Called after an item has collapsed.

            If Option key was held during collapse, collapse children state is preserved
            so next expand shows them collapsed.
            """
            try:
                if hasattr(self, '_pending_option_collapse') and self._pending_option_collapse:
                    item = self._pending_option_collapse
                    self._pending_option_collapse = None

                    # Collapse all children recursively (they're already not visible,
                    # but this updates their "expanded" state for next time)
                    self.collapseItem_collapseChildren_(item, True)
                    logger.debug(f"Option+collapse: collapsed all children states")

            except Exception as e:
                logger.debug(f"Error in outlineViewItemDidCollapse: {e}")

        # =====================================================================
        # SECTION 7: DRAG AND DROP - Following Apple's DragNDropOutlineView Pattern
        # =====================================================================

        # NOTE: outlineView_draggingSession_willBeginAtPoint_forItems_ is intentionally
        # NOT implemented because it causes segfaults with Rubicon-ObjC.
        # Instead, we detect local reorder via pasteboard type in validateDrop.
        # The dragged item info is obtained from pasteboardWriterForItem.

        @objc_method
        def outlineView_pasteboardWriterForItem_(self, outline_view, item):
            """Initiate drag operation - provide pasteboard writer for dragged item."""
            try:
                if hasattr(item, '_python_data'):
                    data_item = item._python_data
                else:
                    data_item = item

                # Check if item is draggable
                if isinstance(data_item, dict):
                    is_draggable = True
                    if '_draggable' in data_item:
                        is_draggable = data_item['_draggable']
                    elif data_item.get('_is_section_header'):
                        is_draggable = False

                    if not is_draggable:
                        logger.debug(f"Rejecting drag for non-draggable item: {data_item.get('text', 'unknown')}")
                        return None

                NSPasteboardItem = ObjCClass("NSPasteboardItem")
                pasteboard_item = NSPasteboardItem.alloc().init()

                # Get collection ID
                collection_data = data_item.get('_collection_data') if isinstance(data_item, dict) else None
                if collection_data:
                    collection_id = collection_data.get('id', '')
                    if collection_id:
                        UTI = "com.fichero.collection.id"
                        pasteboard_item.setString_forType_(collection_id, UTI)
                        node_type = data_item.get('_node_type', 'collection')
                        pasteboard_item.setString_forType_(node_type, "com.fichero.item.type")
                        logger.debug(f"Started drag for collection: {collection_data.get('name')} (ID: {collection_id})")
                        return pasteboard_item

                # Fallback: use text field
                if isinstance(data_item, dict):
                    text = data_item.get('text', '')
                    if text:
                        UTI = "com.fichero.collection.id"
                        pasteboard_item.setString_forType_(text, UTI)
                        node_type = data_item.get('_node_type', 'collection')
                        pasteboard_item.setString_forType_(node_type, "com.fichero.item.type")
                        logger.debug(f"Started drag for item: {text}")
                        return pasteboard_item

                return None
            except Exception as e:
                logger.error(f"Error in pasteboardWriterForItem: {e}", exc_info=True)
                return None

        # NOTE: Helper methods like _drag_is_local_reorder cannot be called from
        # ObjC callbacks because `self` is an ObjCInstance, not a Python object.
        # All helper logic must be inlined into the @objc_method decorated methods.

        @objc_method
        def outlineView_validateDrop_proposedItem_proposedChildIndex_(
            self, outline_view, drag_info, item, index: int
        ) -> int:
            """
            Validate drop location during drag operation.

            Drop semantics:
            - index=-1: Dropping ON the item (shows blue highlight)
            - index>=0: Dropping BETWEEN children at that index (shows insertion line)

            Drop rules:
            - Cannot drop item onto itself
            - Cannot drop item onto non-section items (only reorder within sections)
            - Can drop BETWEEN items within a section (index >= 0)
            - Can drop ON section headers (redirected to end of section)

            Uses setDropItem:dropChildIndex: to explicitly set drop indicator location,
            which is required for proper visual feedback inside group items.
            """
            try:
                # Get target data
                target_data = None
                is_section = False
                if item is not None and hasattr(item, '_python_data'):
                    target_data = item._python_data
                    if isinstance(target_data, dict):
                        is_section = target_data.get('_is_section_header', False)

                target_name = target_data.get('text', 'root') if target_data else 'root'

                # Get source ID from pasteboard to validate drop
                source_id = ""
                try:
                    pasteboard = drag_info.draggingPasteboard
                    types = pasteboard.types
                    has_local = False
                    for i in range(len(types)):
                        if str(types[i]) == "com.fichero.collection.id":
                            has_local = True
                            break
                    if has_local:
                        source_id = str(pasteboard.stringForType_("com.fichero.collection.id") or "")
                except Exception:
                    pass

                # Get target ID
                target_id = ""
                if target_data and isinstance(target_data, dict):
                    collection_data = target_data.get('_collection_data')
                    if collection_data:
                        target_id = collection_data.get('id', '')
                    if not target_id:
                        target_id = target_data.get('text', '')

                # Validate drop
                if index == -1:
                    # Dropping ON an item (blue highlight)
                    if source_id and target_id and source_id == target_id:
                        # Reject: dropping item onto itself
                        logger.debug(f"validateDrop: REJECT - dropping '{source_id}' onto itself")
                        return NS_DRAG_OPERATION_NONE

                    # Check for circular reference: can't drop parent onto its own child
                    # We need to find source item and check if it CONTAINS target
                    if source_id and target_id and self.interface:
                        from .tree_operations import find_item_by_id, is_descendant_of
                        if hasattr(self.interface, '_data'):
                            source_item = find_item_by_id(self.interface._data, source_id)
                            if source_item:
                                # If source contains target, dropping source INTO target
                                # would create a cycle: target -> source -> target
                                if is_descendant_of(source_item, target_id):
                                    logger.debug(f"validateDrop: REJECT - '{source_id}' contains '{target_id}' (circular)")
                                    return NS_DRAG_OPERATION_NONE

                    # Check if target can accept drops (like Finder folders)
                    can_accept_drops = False
                    if target_data and isinstance(target_data, dict):
                        can_accept_drops = target_data.get('_can_accept_drops', False)

                    if is_section or can_accept_drops:
                        # Accept: dropping ON section header or folder
                        # Show blue highlight (don't redirect to end)
                        outline_view.setDropItem_dropChildIndex_(item, -1)
                        logger.debug(f"validateDrop: ACCEPT ON '{target_name}' (highlight)")
                        return NS_DRAG_OPERATION_MOVE

                    if target_data and not is_section and not can_accept_drops:
                        # Reject: dropping ON an item that can't accept drops
                        logger.debug(f"validateDrop: REJECT - cannot drop ON '{target_name}' (not a container)")
                        return NS_DRAG_OPERATION_NONE

                    # Root level drop (item is None)
                    outline_view.setDropItem_dropChildIndex_(item, -1)
                    return NS_DRAG_OPERATION_MOVE
                else:
                    # Dropping BETWEEN items (index >= 0)
                    # Accept: reordering within a section or at root
                    outline_view.setDropItem_dropChildIndex_(item, index)
                    logger.debug(f"validateDrop: ACCEPT BETWEEN at index {index} in '{target_name}'")
                    return NS_DRAG_OPERATION_MOVE

            except Exception as e:
                logger.error(f"Error in validateDrop: {e}", exc_info=True)
                return NS_DRAG_OPERATION_NONE

        @objc_method
        def outlineView_updateDraggingItemsForDrag_(self, outline_view, drag_info) -> None:
            """Update dragging items - required for visual feedback."""
            try:
                logger.debug("updateDraggingItemsForDrag called")
            except Exception as e:
                logger.error(f"Error in updateDraggingItemsForDrag: {e}", exc_info=True)

        @objc_method
        def outlineView_acceptDrop_item_childIndex_(
            self, outline_view, drag_info, item, index: int
        ) -> bool:
            """Accept and handle drop operation.

            Args:
                outline_view: The NSOutlineView
                drag_info: Drag session info
                item: Drop target item (where we're dropping ON or BETWEEN)
                index: -1 means ON item, >=0 means BETWEEN children at that index
            """
            try:
                # Get target data (the item we're dropping onto/into)
                target_data = None
                if item is not None:
                    if hasattr(item, '_python_data'):
                        target_data = item._python_data
                    else:
                        target_data = item

                # Check if local reorder (inlined - can't call helper methods from ObjC)
                is_local_reorder = False
                try:
                    pasteboard = drag_info.draggingPasteboard
                    types = pasteboard.types
                    for i in range(len(types)):
                        type_str = str(types[i])
                        if type_str == "com.fichero.collection.id":
                            is_local_reorder = True
                            break
                except Exception:
                    pass

                # Handle local reorder
                if is_local_reorder:
                    # Get dragged item ID from pasteboard
                    pasteboard = drag_info.draggingPasteboard
                    source_id = str(pasteboard.stringForType_("com.fichero.collection.id") or "")

                    if not source_id:
                        logger.error("No source ID in pasteboard")
                        return False

                    # Get target ID for validation
                    target_id = ""
                    if target_data and isinstance(target_data, dict):
                        collection_data = target_data.get('_collection_data')
                        if collection_data:
                            target_id = collection_data.get('id', '')
                        if not target_id:
                            target_id = target_data.get('text', '')

                    # Prevent dropping item onto itself
                    if source_id and target_id and source_id == target_id and index == -1:
                        logger.warning(f"Rejecting drop: cannot drop '{source_id}' onto itself")
                        return False

                    # For drops ON item (index=-1), we need to determine parent_data
                    # For drops BETWEEN items (index>=0), target_data IS the parent
                    if index == -1 and target_data:
                        # Dropping ON an item - check what type of container it is
                        is_section_header = isinstance(target_data, dict) and target_data.get('_is_section_header')
                        can_accept = isinstance(target_data, dict) and target_data.get('_can_accept_drops', False)

                        if is_section_header or can_accept:
                            # Drop at end of container's children
                            children = target_data.get('_children', []) if isinstance(target_data, dict) else []
                            parent_data = target_data
                            insert_index = len(children)
                            container_type = "section" if is_section_header else "folder"
                            logger.info(f"Drop ON {container_type} '{target_id}' -> inserting at end (index {insert_index})")
                        else:
                            # Dropping ON an item that can't accept drops
                            logger.warning(f"Rejecting drop ON non-container item '{target_id}'")
                            return False
                    else:
                        # Dropping BETWEEN items - target_data is the parent
                        parent_data = target_data
                        insert_index = index

                    if self.interface:
                        # Use the simple reloadData() approach (like demo_toga_pattern.py)
                        # This works because _get_or_create_wrapper returns the SAME wrapper
                        # for the same item, so NSOutlineView's references stay valid
                        try:
                            interface = self.interface
                            data = interface._data

                            # Find source item in tree
                            source_item = None
                            source_parent = None

                            def find_in_tree(items, parent=None):
                                nonlocal source_item, source_parent
                                for i, itm in enumerate(items):
                                    if not isinstance(itm, dict):
                                        continue
                                    coll_data = itm.get('_collection_data')
                                    itm_id = coll_data.get('id') if coll_data else None
                                    if not itm_id:
                                        itm_id = itm.get('text', '')

                                    if itm_id == source_id:
                                        source_item = itm
                                        source_parent = parent
                                        return True
                                    children = itm.get('_children', [])
                                    if children and find_in_tree(children, itm):
                                        return True
                                return False

                            find_in_tree(data)

                            if source_item is None:
                                logger.error(f"Source item '{source_id}' not found")
                                return False

                            # Debug: log what we found
                            logger.debug(f"Found source_item: '{source_item.get('text', '?')}'")
                            if source_parent:
                                logger.debug(f"source_parent: '{source_parent.get('text', '?')}'")
                            else:
                                logger.debug("source_parent: None (root level)")

                            # Remove from old parent
                            if source_parent is None:
                                # Was at root level
                                logger.debug(f"Removing from root. data before: {[d.get('text', '?') for d in data]}")
                                data.remove(source_item)
                                logger.debug(f"data after: {[d.get('text', '?') for d in data]}")
                            else:
                                children = source_parent.get('_children', [])
                                logger.debug(f"Parent's children before: {[c.get('text', '?') for c in children]}")
                                if source_item in children:
                                    children.remove(source_item)
                                    logger.debug(f"Removed! Children after: {[c.get('text', '?') for c in children]}")
                                else:
                                    logger.warning(f"source_item NOT in children! Object identity mismatch?")

                            # Insert at new location
                            if parent_data is None:
                                # Insert at root
                                logger.debug(f"Inserting at ROOT level, index={insert_index}")
                                if insert_index >= len(data):
                                    data.append(source_item)
                                else:
                                    data.insert(insert_index, source_item)
                                logger.debug(f"Root after insert: {[d.get('text', '?') for d in data]}")
                            else:
                                # Insert as child of parent
                                parent_name = parent_data.get('text', '?') if isinstance(parent_data, dict) else str(parent_data)
                                logger.debug(f"Inserting into parent '{parent_name}', index={insert_index}")
                                children = parent_data.setdefault('_children', [])
                                logger.debug(f"Parent children before: {[c.get('text', '?') for c in children]}")
                                if insert_index >= len(children):
                                    children.append(source_item)
                                else:
                                    children.insert(insert_index, source_item)
                                parent_data['_has_children'] = True
                                logger.debug(f"Parent children after: {[c.get('text', '?') for c in children]}")

                            # Verify final state - check BOTH the data tree and wrapper references
                            if source_parent:
                                old_children = source_parent.get('_children', [])
                                logger.debug(f"Old parent '{source_parent.get('text', '?')}' (id={id(source_parent)}) final children: {[c.get('text', '?') for c in old_children]}")
                                # Also verify if source_parent is same object as in data tree
                                for section in data:
                                    if section.get('text') == source_parent.get('text'):
                                        logger.debug(f"  Data tree section id={id(section)}, same={section is source_parent}")
                                        logger.debug(f"  Data tree children: {[c.get('text', '?') for c in section.get('_children', [])]}")
                            else:
                                logger.debug(f"Root final: {[d.get('text', '?') for d in data]}")

                            # CRITICAL: Clear child cache before reloadData()
                            # Otherwise NSOutlineView reads stale cached data
                            interface._child_cache = {}
                            logger.debug("Cleared _child_cache before reloadData()")

                            # Reload data
                            outline_view.reloadData()

                            # Only expand root sections + target parent (not ALL items)
                            # This prevents Documents/2024/January etc from auto-expanding
                            for root_item in interface._wrapped_items:
                                outline_view.expandItem_(root_item)
                            # Also expand the target parent to show the moved item
                            if parent_data is not None:
                                parent_wrapper = parent_data.get('_impl')
                                if parent_wrapper:
                                    outline_view.expandItem_(parent_wrapper)

                            # Fire reorder callback for external updates (database)
                            if hasattr(interface, '_on_reorder_callback') and \
                               interface._on_reorder_callback:
                                interface._on_reorder_callback(source_id, insert_index)

                            logger.info(f"Move completed: '{source_id}' to index {insert_index}")
                            # Return False to prevent animation (avoids segfault).
                            # The data has already been updated and reloadData() shows
                            # the new position. This is a stable workaround until we
                            # figure out why returning True causes animation crashes.
                            return False

                        except Exception as e:
                            logger.error(f"Move failed: {e}", exc_info=True)
                            return False

                    return False

                # Handle external file drop from Finder
                # Use readObjectsForClasses:options: to properly extract file URLs
                pasteboard = drag_info.draggingPasteboard
                try:
                    NSURL = ObjCClass("NSURL")
                    NSArray = ObjCClass("NSArray")

                    # Create an array with NSURL class
                    classes = NSArray.arrayWithObject_(NSURL)

                    # Read file URLs from pasteboard
                    url_objects = pasteboard.readObjectsForClasses_options_(classes, None)

                    if url_objects and len(url_objects) > 0:
                        # Convert NSURL objects to file path strings
                        file_paths = []
                        for i in range(len(url_objects)):
                            url = url_objects[i]
                            if url.isFileURL():
                                path = str(url.path)
                                file_paths.append(path)
                                logger.debug(f"File drop path: {path}")

                        if file_paths:
                            # Get the target item data (where files are being dropped)
                            target_data = None
                            if item is not None:
                                if hasattr(item, '_python_data'):
                                    target_data = item._python_data
                                else:
                                    target_data = item

                            target_name = target_data.get('text', 'root') if target_data and isinstance(target_data, dict) else 'root'
                            logger.info(f"File drop: {len(file_paths)} items onto '{target_name}'")

                            if self.interface:
                                # Try import_to_collection callback first (for dropping on specific collection)
                                if target_data and isinstance(target_data, dict):
                                    # Use the target item itself as the collection (or its _collection_data if present)
                                    collection_data = target_data.get('_collection_data') or target_data
                                    collection_id = collection_data.get('id') or target_data.get('text')
                                    if collection_id and hasattr(self.interface, '_on_import_to_collection_callback'):
                                        if self.interface._on_import_to_collection_callback:
                                            self.interface._on_import_to_collection_callback(file_paths, collection_id)
                                            # Return True for external file drops - the import happens
                                            # asynchronously and doesn't modify outline data during acceptDrop
                                            return True

                                # Fall back to general import callback
                                if hasattr(self.interface, '_on_import_callback') and self.interface._on_import_callback:
                                    self.interface._on_import_callback(file_paths)
                                    # Return True for external file drops - import is async
                                    return True

                except Exception as url_error:
                    logger.error(f"Failed to extract file URLs: {url_error}", exc_info=True)

                return False
            except Exception as e:
                logger.error(f"Error in acceptDrop: {e}", exc_info=True)
                return False

        @objc_method
        def outlineView_draggingSession_endedAtPoint_operation_(
            self, outline_view, session, screen_point, operation: int
        ) -> None:
            """Called when drag session ends - clean up."""
            try:
                # Clear drop indicators
                outline_view.setDropRow_dropOperation_(NS_OUTLINE_VIEW_DROP_ON_ITEM_INDEX, NS_TABLE_VIEW_DROP_ABOVE)
                outline_view.deselectAll_(None)

                logger.debug(f"Drag session ended (operation={operation})")
            except Exception as e:
                logger.error(f"Error in draggingSessionEnded: {e}", exc_info=True)

        @objc_method
        def draggingExited_(self, drag_info) -> None:
            """Called when drag exits the outline view bounds."""
            try:
                self.setDropRow_dropOperation_(NS_OUTLINE_VIEW_DROP_ON_ITEM_INDEX, NS_TABLE_VIEW_DROP_ABOVE)
                logger.debug("Drag exited view")
            except Exception as e:
                logger.error(f"Error in draggingExited: {e}", exc_info=True)

        @objc_method
        def draggingEntered_(self, drag_info) -> int:
            """Called when drag enters the outline view bounds."""
            try:
                if not hasattr(self, '_saved_selection_before_drag'):
                    selected = self.selectedRowIndexes
                    self._saved_selection_before_drag = selected if selected else None
                logger.debug("Drag entered view")
                return NS_DRAG_OPERATION_MOVE
            except Exception as e:
                logger.error(f"Error in draggingEntered: {e}", exc_info=True)
                return NS_DRAG_OPERATION_NONE

        @objc_method
        def processPendingMove_(self, sender) -> None:
            """
            Process a pending move operation after acceptDrop has returned.

            This is called via performSelector:withObject:afterDelay: from acceptDrop.
            By deferring the actual data modification until after acceptDrop returns,
            we avoid segfaults caused by NSOutlineView accessing invalidated wrappers
            during its post-drop processing (animations, cleanup).
            """
            try:
                if not self.interface or not hasattr(self.interface, '_pending_move'):
                    return

                pending = self.interface._pending_move
                if pending is None:
                    return

                # Clear pending move first to prevent re-entry
                self.interface._pending_move = None

                source_id = pending['source_id']
                target_parent_data = pending['target_parent_data']
                insert_index = pending['insert_index']

                logger.info(f"Processing deferred move: '{source_id}' to index {insert_index}")

                # Now safe to modify data structures
                if hasattr(self.interface, 'move_item_in_tree'):
                    success = self.interface.move_item_in_tree(source_id, target_parent_data, insert_index)
                    if success:
                        # Fire the reorder callback for external updates (database)
                        if hasattr(self.interface, '_on_reorder_callback') and self.interface._on_reorder_callback:
                            self.interface._on_reorder_callback(source_id, insert_index)
                        logger.info("Deferred move completed successfully")
                    else:
                        logger.error("Deferred move failed")
            except Exception as e:
                logger.error(f"Error in processPendingMove: {e}", exc_info=True)

        # =====================================================================
        # SECTION 8: INLINE EDITING (Finder-like rename)
        # =====================================================================
        #
        # Implements Finder-style inline rename with multiple triggers:
        # - Context menu "Rename"
        # - Return key when item is selected
        # - Slow double-click (click, pause 0.3-1.5s, click again)
        #
        # The text field in the cell view becomes editable, user types new name,
        # then Enter confirms or Escape cancels.

        def _is_section_header(self, row: int) -> bool:
            """Check if row is a section header (not renameable)."""
            if row < 0:
                return True
            try:
                item = self.itemAtRow_(row)
                if item and hasattr(item, '_python_data'):
                    data = item._python_data
                    if isinstance(data, dict):
                        return data.get('_is_section_header', False)
            except Exception:
                pass
            return False

        def _start_inline_edit(self, row: int) -> None:
            """
            Start inline editing for the given row.

            Makes the text field in the cell view editable, sets self as delegate,
            and starts editing with all text selected.
            """
            if row < 0:
                return

            # Don't allow renaming section headers
            if self._is_section_header(row):
                logger.debug("Cannot rename section header")
                return

            try:
                # Get the cell view and text field
                cell_view = self.viewAtColumn_row_makeIfNecessary_(0, row, False)
                if not cell_view or not cell_view.textField:
                    logger.warning(f"No text field found for row {row}")
                    return

                text_field = cell_view.textField

                # Initialize editing state if needed
                if not hasattr(self, '_editing_row'):
                    self._editing_row = -1
                if not hasattr(self, '_editing_original_text'):
                    self._editing_original_text = None

                # Store original text for cancel
                self._editing_row = row
                self._editing_original_text = str(text_field.stringValue)

                # Make editable and start editing
                text_field.editable = True
                text_field.delegate = self
                self.window.makeFirstResponder_(text_field)

                # Select all text for easy replacement
                text_field.selectText_(None)

                logger.debug(f"Started inline edit for row {row}: '{self._editing_original_text}'")

            except Exception as e:
                logger.error(f"Error starting inline edit: {e}", exc_info=True)
                self._editing_row = -1

        def start_rename_selected(self) -> None:
            """
            Public method to start rename on selected item.

            Called from File menu or external code. Triggers inline editing
            on the currently selected row.
            """
            row = self.selectedRow
            if row >= 0:
                # Use module-level helper for consistency with @objc_method decorated functions
                _start_inline_edit_for_row(self, row)

        # NOTE: controlTextDidEndEditing_ and control_textView_doCommandBySelector_
        # have been REMOVED because setting the NSOutlineView as a text field delegate
        # causes segfaults in Rubicon-ObjC when the text field sends delegate messages.
        #
        # Instead, we use a simpler approach:
        # 1. When inline editing starts, we make the text field editable
        # 2. The user edits the text normally
        # 3. When focus changes (click elsewhere, press Enter), we detect it via
        #    the windowDidResignFirstResponder notification or by polling
        # 4. We use the _finish_inline_edit_if_needed() method called from
        #    mouseDown_ or selection change to finalize the edit
        #
        # This avoids the delegate pattern which crashes with Rubicon-ObjC.

        @objc_method
        def keyDown_(self, event) -> None:
            """
            Override keyDown to handle Return key for inline rename.

            When Return is pressed on a selected (non-section) item,
            starts inline editing instead of default behavior.

            Also handles:
            - Return during editing: confirms the edit
            - Escape during editing: cancels the edit
            """
            try:
                from rubicon.objc import send_super
                from rubicon.objc.runtime import objc_id

                key_code = event.keyCode

                # Check if we're currently editing
                editing_state = _get_editing_state(self)

                # Escape key = keyCode 53
                if key_code == 53:
                    if editing_state:
                        # Cancel the edit
                        _finish_inline_edit_if_needed(self, cancel=True)
                        self.window.makeFirstResponder_(self)
                        return

                # Return key = keyCode 36
                if key_code == 36:
                    if editing_state:
                        # Confirm the edit
                        _finish_inline_edit_if_needed(self, cancel=False)
                        self.window.makeFirstResponder_(self)
                        return

                    # Not editing - start inline edit on selected row
                    row = self.selectedRow
                    if row >= 0:
                        # Check if section header (inline to avoid ObjC method lookup issues)
                        is_header = False
                        try:
                            item = self.itemAtRow_(row)
                            if item and hasattr(item, '_python_data'):
                                data = item._python_data
                                if isinstance(data, dict):
                                    is_header = data.get('_is_section_header', False)
                        except Exception:
                            pass

                        if not is_header:
                            # Start inline edit using the helper function
                            _start_inline_edit_for_row(self, row)
                            return

                # Let parent class handle other keys
                send_super(__class__, self, 'keyDown:', event, argtypes=[objc_id])

            except Exception as e:
                logger.error(f"Error in keyDown: {e}", exc_info=True)

        @objc_method
        def mouseDown_(self, event) -> None:
            """
            Override mouseDown to detect slow double-click for inline rename.

            Slow double-click pattern (like Finder):
            1. Click to select an item
            2. Wait 0.3-1.5 seconds
            3. Click again on the SAME SELECTED item
            -> Starts inline editing

            This is different from regular double-click (opens item).
            """
            try:
                import time
                from rubicon.objc import send_super
                from rubicon.objc.runtime import objc_id

                # First, finish any in-progress inline edit (confirms the edit)
                # This handles the case where user clicks elsewhere to confirm rename
                editing_state = _get_editing_state(self)
                if editing_state:
                    _finish_inline_edit_if_needed(self, cancel=False)
                    # Don't return - continue processing the click

                # Initialize click tracking state if needed
                if not hasattr(self, '_last_click_row'):
                    self._last_click_row = -1
                if not hasattr(self, '_last_click_time'):
                    self._last_click_time = 0

                # Get click location
                point = self.convertPoint_fromView_(event.locationInWindow, None)
                row = self.rowAtPoint_(point)
                current_time = time.time()

                # Check for slow double-click pattern:
                # - Same row as last click
                # - Row is currently selected
                # - Time between clicks is 0.3-1.5 seconds
                # - Not a section header
                if (row >= 0 and
                    row == self._last_click_row and
                    row == self.selectedRow and
                    0.3 < (current_time - self._last_click_time) < 1.5):

                    # Check if section header (inline to avoid ObjC method lookup issues)
                    is_header = False
                    try:
                        item = self.itemAtRow_(row)
                        if item and hasattr(item, '_python_data'):
                            data = item._python_data
                            if isinstance(data, dict):
                                is_header = data.get('_is_section_header', False)
                    except Exception:
                        pass

                    if not is_header:
                        # Start inline edit using the helper function
                        _start_inline_edit_for_row(self, row)

                        # Reset tracking to prevent immediate re-trigger
                        self._last_click_row = -1
                        self._last_click_time = 0
                        return

                # Update click tracking
                self._last_click_row = row
                self._last_click_time = current_time

                # Let parent class handle the click (selection, etc.)
                send_super(__class__, self, 'mouseDown:', event, argtypes=[objc_id])

            except Exception as e:
                logger.error(f"Error in mouseDown: {e}", exc_info=True)
                # Still try to pass to parent
                try:
                    from rubicon.objc import send_super
                    from rubicon.objc.runtime import objc_id
                    send_super(__class__, self, 'mouseDown:', event, argtypes=[objc_id])
                except Exception:
                    pass

    # Cache the classes for reuse
    _sidebar_classes_cache = (SidebarItem, TogaSidebar, MinWidthView)
    return SidebarItem, TogaSidebar, MinWidthView


__all__ = ['create_sidebar_classes']
