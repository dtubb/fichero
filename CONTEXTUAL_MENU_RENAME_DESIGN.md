# Contextual Menu & Inline Rename Design for macOS Sidebar

## Executive Summary

This document outlines the architecture for adding native macOS contextual menus (right-click) and Finder-style inline rename functionality to the Fichero NSOutlineView sidebar. The design follows established macOS patterns and integrates seamlessly with the existing NSOutlineViewSidebar implementation.

## Current Architecture Analysis

### Existing Structure

The sidebar is implemented in `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py` using:

- **TogaSidebar**: Custom NSOutlineView subclass serving as both data source and delegate
- **SidebarItem**: Wrapper for Python dict data to avoid ObjC introspection issues
- **NSOutlineViewSidebar**: Renderer class managing the widget lifecycle

### Current Delegate Methods

Already implemented:
- `outlineView_numberOfChildrenOfItem_` - hierarchy support
- `outlineView_child_ofItem_` - child retrieval
- `outlineView_isItemExpandable_` - expandable state
- `outlineView_shouldSelectItem_` - selection filtering (blocks section headers)
- `outlineView_heightOfRowByItem_` - custom row heights
- `outlineView_viewForTableColumn_item_` - cell rendering
- `outlineView_menuForTableColumn_item_` - **STUB IMPLEMENTATION** (lines 839-906)

### Current Menu Implementation

Lines 839-906 show a basic contextual menu stub:
- Already detects right-click on items
- Creates NSMenu programmatically
- Differentiates between section headers and regular items
- Uses hardcoded placeholder actions (Expand All, Reveal in Finder, Get Info)

**Key Issue**: Menu actions use SEL() selectors that don't connect to Python callbacks.

---

## Design Goals

1. **Native macOS UX**: Match Finder, DEVONthink, and Mail.app patterns
2. **Type-Specific Menus**: Different options for collections, folders, section headers, empty space
3. **Inline Rename**: Click-pause-click pattern like Finder
4. **Python Integration**: Callbacks that trigger Python business logic
5. **Keyboard Support**: Enter to rename, Esc to cancel
6. **Undo/Redo**: Integrate with system undo manager

---

## Architecture Design

### 1. Menu Structure by Item Type

#### Collections (Library Items)
```
Rename                          Cmd+R
Show in Inspector               Cmd+I
─────────────────────────────────────
Duplicate                       Cmd+D
Move to Folder...
─────────────────────────────────────
Export Collection...
Remove from Library             Cmd+Delete
```

#### Folders (Hierarchy Containers)
```
Rename                          Cmd+R
New Subfolder
─────────────────────────────────────
Move to...
─────────────────────────────────────
Delete Folder                   Cmd+Delete
```

#### Section Headers
```
New Collection                  Cmd+N
─────────────────────────────────────
Expand All
Collapse All
```

#### Empty Space (Below Last Item)
```
New Collection                  Cmd+N
─────────────────────────────────────
Import...                       Cmd+O
```

### 2. NSOutlineView Delegate Methods Required

#### Already Implemented ✓
- `outlineView_menuForTableColumn_item_` (needs enhancement)

#### New Methods Needed

##### Menu Action Handlers
```python
@objc_method
def performRenameItem_(self, sender):
    """Handle Rename menu action"""

@objc_method
def performDuplicateItem_(self, sender):
    """Handle Duplicate menu action"""

@objc_method
def performDeleteItem_(self, sender):
    """Handle Delete menu action"""

@objc_method
def performExpandAll_(self, sender):
    """Handle Expand All menu action"""

@objc_method
def performCollapseAll_(self, sender):
    """Handle Collapse All menu action"""
```

##### Inline Rename Support
```python
@objc_method
def outlineView_shouldEditTableColumn_item_(self, outline_view, table_column, item) -> bool:
    """Control when text field becomes editable"""
    # Block editing for section headers
    # Allow editing for regular items
    # Check rename permissions

@objc_method
def outlineView_setObjectValue_forTableColumn_byItem_(self, outline_view, value, table_column, item):
    """Handle text field edit completion"""
    # Validate new name
    # Call Python rename callback
    # Update data model
```

##### Click Detection for Click-Pause-Click Pattern
```python
@objc_method
def mouseDown_(self, event):
    """Override to detect click-pause-click rename pattern"""
    # Get clicked row and column
    # Check if same row clicked within delay threshold
    # Initiate rename if pattern matches
    # Otherwise call super for normal selection
```

### 3. Python Callback Integration

#### Callback Registration (NSOutlineViewSidebar class)

```python
def __init__(self, ...):
    # Existing callbacks
    self._on_select_callback = on_select
    self._on_reorder_callback = None
    self._on_import_callback = None

    # NEW: Rename and menu action callbacks
    self._on_rename_callback = None           # (item_id, old_name, new_name) -> bool
    self._on_delete_callback = None           # (item_id) -> bool
    self._on_duplicate_callback = None        # (item_id) -> bool
    self._on_move_to_callback = None          # (item_id, target_id) -> bool
    self._on_new_collection_callback = None   # (section_id) -> bool
    self._on_export_callback = None           # (item_id) -> bool
    self._on_show_inspector_callback = None   # (item_id) -> None
```

#### Public API Methods

```python
def set_rename_callback(self, callback: Callable[[str, str, str], bool]) -> None:
    """Register callback for item rename operations.

    Args:
        callback: Function(item_id, old_name, new_name) -> success
    """

def set_delete_callback(self, callback: Callable[[str], bool]) -> None:
    """Register callback for item delete operations."""

def set_duplicate_callback(self, callback: Callable[[str], bool]) -> None:
    """Register callback for item duplication."""

# ... similar for other actions
```

### 4. Inline Rename Implementation

#### Strategy: Editable NSTextField in Cell

The current implementation uses `NSTextField` with `editable = False`. For inline rename:

1. **Make text field conditionally editable** via `outlineView_shouldEditTableColumn_item_`
2. **Trigger edit mode** via click-pause-click or Enter key
3. **Validate and commit** via `outlineView_setObjectValue_forTableColumn_byItem_`

#### Click-Pause-Click Pattern

Based on [Lap Cat Software's approach](https://lapcatsoftware.com/blog/2006/10/12/single-click-renaming-in-nstableview/):

```python
class TogaSidebar(NSOutlineView):
    # Track click state
    _last_click_row = objc_property(int)
    _last_click_time = objc_property(float)
    _click_threshold = 0.8  # seconds between clicks

    @objc_method
    def mouseDown_(self, event):
        """Detect click-pause-click for rename."""
        import time
        from rubicon.objc import CGPoint

        # Get clicked row
        point = self.convertPoint_fromView_(event.locationInWindow, None)
        row = self.rowAtPoint(point)

        if row >= 0:
            current_time = time.time()

            # Check if this is second click on same row
            if (row == self._last_click_row and
                current_time - self._last_click_time < self._click_threshold):

                # Second click detected - initiate rename
                item = self.itemAtRow(row)
                if item and not self._is_section_header(item):
                    # Edit the text field
                    self.editColumn_row_withEvent_select_(0, row, None, True)
                    return  # Don't propagate event

            # Record click for next time
            self._last_click_row = row
            self._last_click_time = current_time

        # Normal click handling
        super().mouseDown_(event)
```

#### Enter Key Rename

```python
@objc_method
def keyDown_(self, event):
    """Handle Enter key to start rename."""
    if event.keyCode == 36:  # Return/Enter key
        selected_row = self.selectedRow
        if selected_row >= 0:
            item = self.itemAtRow(selected_row)
            if item and not self._is_section_header(item):
                self.editColumn_row_withEvent_select_(0, selected_row, None, True)
                return

    super().keyDown_(event)
```

#### Edit Validation and Commit

```python
@objc_method
def outlineView_shouldEditTableColumn_item_(self, outline_view, table_column, item) -> bool:
    """Control when text field becomes editable."""
    try:
        if hasattr(item, '_python_data'):
            data = item._python_data

            # Block editing section headers
            if data.get('_is_section_header', False):
                return False

            # Block editing Inbox (special collection)
            if data.get('text') == 'Inbox':
                return False

            # Allow editing regular items
            return True

        return False
    except Exception as e:
        logger.error(f"Error in shouldEditTableColumn: {e}")
        return False

@objc_method
def outlineView_setObjectValue_forTableColumn_byItem_(
    self, outline_view, value, table_column, item
):
    """Handle text field edit completion."""
    try:
        if not hasattr(item, '_python_data'):
            return

        data = item._python_data
        old_name = data.get('text', '')
        new_name = str(value) if value else ''

        # Validate new name
        if not new_name or new_name.strip() == '':
            logger.warning("Empty name rejected")
            return

        if new_name == old_name:
            logger.debug("Name unchanged")
            return

        # Get item ID for callback
        item_id = None
        if '_collection_data' in data:
            item_id = data['_collection_data'].get('id')
        else:
            item_id = data.get('id') or old_name

        # Call Python rename callback
        if self.interface and hasattr(self.interface, '_on_rename_callback'):
            if self.interface._on_rename_callback:
                success = self.interface._on_rename_callback(item_id, old_name, new_name)

                if success:
                    # Update data model
                    data['text'] = new_name
                    # Reload row to show new name
                    row = outline_view.rowForItem(item)
                    if row >= 0:
                        index_set = NSIndexSet.indexSetWithIndex(row)
                        outline_view.reloadDataForRowIndexes_columnIndexes_(
                            index_set,
                            NSIndexSet.indexSetWithIndex(0)
                        )
                    logger.info(f"✅ Renamed '{old_name}' to '{new_name}'")
                else:
                    logger.warning(f"❌ Rename rejected by callback")
            else:
                logger.warning("No rename callback registered")

    except Exception as e:
        logger.error(f"Error in setObjectValue: {e}", exc_info=True)
```

### 5. Enhanced Menu Implementation

#### Menu Creation with Python Callbacks

```python
@objc_method
def outlineView_menuForTableColumn_item_(self, outline_view, table_column, item):
    """Provide contextual menu for right-click on item."""
    try:
        from rubicon.objc import ObjCClass, SEL
        NSMenu = ObjCClass("NSMenu")
        NSMenuItem = ObjCClass("NSMenuItem")

        # Get item data
        data_item = None
        if item is not None:
            if hasattr(item, '_python_data'):
                data_item = item._python_data

        # Store clicked item for menu action handlers
        self._menu_clicked_item = item
        self._menu_clicked_data = data_item

        menu = NSMenu.alloc().initWithTitle("Contextual Menu")

        # Determine item type
        item_type = self._get_item_type(data_item)

        if item_type == 'section_header':
            self._add_section_header_menu_items(menu)
        elif item_type == 'collection':
            self._add_collection_menu_items(menu, data_item)
        elif item_type == 'folder':
            self._add_folder_menu_items(menu, data_item)
        elif item_type == 'empty':
            self._add_empty_space_menu_items(menu)

        return menu

    except Exception as e:
        logger.error(f"Error creating menu: {e}", exc_info=True)
        return None

def _get_item_type(self, data_item):
    """Determine type of clicked item."""
    if data_item is None:
        return 'empty'

    if data_item.get('_is_section_header'):
        return 'section_header'

    node_type = data_item.get('_node_type')
    if node_type == 'collection':
        return 'collection'
    elif node_type == 'folder':
        return 'folder'

    return 'unknown'

def _add_collection_menu_items(self, menu, data_item):
    """Add menu items for collection."""
    from rubicon.objc import SEL
    NSMenuItem = ObjCClass("NSMenuItem")

    # Rename
    rename_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Rename", SEL('performRenameItem:'), "r"
    )
    rename_item.target = self
    menu.addItem(rename_item)

    # Show in Inspector
    inspector_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Show in Inspector", SEL('performShowInspector:'), "i"
    )
    inspector_item.target = self
    menu.addItem(inspector_item)

    # Separator
    menu.addItem(NSMenuItem.separatorItem())

    # Duplicate
    duplicate_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Duplicate", SEL('performDuplicateItem:'), "d"
    )
    duplicate_item.target = self
    menu.addItem(duplicate_item)

    # Move to Folder...
    move_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Move to Folder...", SEL('performMoveToFolder:'), ""
    )
    move_item.target = self
    menu.addItem(move_item)

    # Separator
    menu.addItem(NSMenuItem.separatorItem())

    # Export Collection...
    export_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Export Collection...", SEL('performExportCollection:'), ""
    )
    export_item.target = self
    menu.addItem(export_item)

    # Remove from Library (check if not Inbox)
    if data_item.get('text') != 'Inbox':
        delete_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Remove from Library", SEL('performDeleteItem:'), "\x08"  # Delete key
        )
        delete_item.target = self
        menu.addItem(delete_item)

def _add_section_header_menu_items(self, menu):
    """Add menu items for section header."""
    from rubicon.objc import SEL
    NSMenuItem = ObjCClass("NSMenuItem")

    # New Collection
    new_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "New Collection", SEL('performNewCollection:'), "n"
    )
    new_item.target = self
    menu.addItem(new_item)

    # Separator
    menu.addItem(NSMenuItem.separatorItem())

    # Expand All
    expand_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Expand All", SEL('performExpandAll:'), ""
    )
    expand_item.target = self
    menu.addItem(expand_item)

    # Collapse All
    collapse_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Collapse All", SEL('performCollapseAll:'), ""
    )
    collapse_item.target = self
    menu.addItem(collapse_item)

# Similar for _add_folder_menu_items and _add_empty_space_menu_items
```

#### Menu Action Handlers

```python
@objc_method
def performRenameItem_(self, sender):
    """Handle Rename menu action."""
    try:
        if hasattr(self, '_menu_clicked_item'):
            row = self.rowForItem(self._menu_clicked_item)
            if row >= 0:
                # Initiate inline edit
                self.editColumn_row_withEvent_select_(0, row, None, True)
    except Exception as e:
        logger.error(f"Error in performRenameItem: {e}")

@objc_method
def performDuplicateItem_(self, sender):
    """Handle Duplicate menu action."""
    try:
        if not hasattr(self, '_menu_clicked_data'):
            return

        data = self._menu_clicked_data
        item_id = self._extract_item_id(data)

        # Call Python callback
        if self.interface and hasattr(self.interface, '_on_duplicate_callback'):
            if self.interface._on_duplicate_callback:
                success = self.interface._on_duplicate_callback(item_id)
                if success:
                    logger.info(f"✅ Duplicated item: {item_id}")
                else:
                    logger.warning(f"❌ Duplication failed: {item_id}")
    except Exception as e:
        logger.error(f"Error in performDuplicateItem: {e}")

@objc_method
def performDeleteItem_(self, sender):
    """Handle Delete menu action."""
    try:
        if not hasattr(self, '_menu_clicked_data'):
            return

        data = self._menu_clicked_data
        item_id = self._extract_item_id(data)
        item_name = data.get('text', 'item')

        # Show confirmation dialog (macOS NSAlert)
        from rubicon.objc import ObjCClass
        NSAlert = ObjCClass("NSAlert")

        alert = NSAlert.alloc().init()
        alert.messageText = f"Delete '{item_name}'?"
        alert.informativeText = "This action cannot be undone."
        alert.addButtonWithTitle("Delete")
        alert.addButtonWithTitle("Cancel")
        alert.alertStyle = 2  # NSAlertStyleCritical

        response = alert.runModal()

        if response == 1000:  # NSAlertFirstButtonReturn (Delete)
            # Call Python callback
            if self.interface and hasattr(self.interface, '_on_delete_callback'):
                if self.interface._on_delete_callback:
                    success = self.interface._on_delete_callback(item_id)
                    if success:
                        logger.info(f"✅ Deleted item: {item_id}")
                    else:
                        logger.warning(f"❌ Deletion failed: {item_id}")
    except Exception as e:
        logger.error(f"Error in performDeleteItem: {e}")

@objc_method
def performExpandAll_(self, sender):
    """Handle Expand All menu action."""
    try:
        self.expandItem_expandChildren_(None, True)
        logger.info("✅ Expanded all items")
    except Exception as e:
        logger.error(f"Error in performExpandAll: {e}")

@objc_method
def performCollapseAll_(self, sender):
    """Handle Collapse All menu action."""
    try:
        self.collapseItem_collapseChildren_(None, True)
        logger.info("✅ Collapsed all items")
    except Exception as e:
        logger.error(f"Error in performCollapseAll: {e}")

def _extract_item_id(self, data):
    """Extract item ID from data dict."""
    if '_collection_data' in data:
        return data['_collection_data'].get('id')
    return data.get('id') or data.get('text')
```

---

## Integration with Library View

### Callback Registration in library_view.py

```python
def _create_collections_list(self):
    """Create the collections sidebar list widget."""
    self.collections_list = ListWidget(
        headings=['Collections'],
        data=[],
        on_select=self._on_collection_selected,
        renderer='sidebar',
        style=Pack(flex=1)
    )

    # Register get_children callback (existing)
    if hasattr(self.collections_list, 'set_get_children_callback'):
        self.collections_list.set_get_children_callback(self._get_children_for_item)

    # Register drag-and-drop callbacks (existing)
    if hasattr(self.collections_list.renderer, 'set_reorder_callback'):
        self.collections_list.renderer.set_reorder_callback(self._on_collection_reordered)

    # NEW: Register menu action callbacks
    if hasattr(self.collections_list.renderer, 'set_rename_callback'):
        self.collections_list.renderer.set_rename_callback(self._on_collection_renamed)

    if hasattr(self.collections_list.renderer, 'set_delete_callback'):
        self.collections_list.renderer.set_delete_callback(self._on_collection_deleted)

    if hasattr(self.collections_list.renderer, 'set_duplicate_callback'):
        self.collections_list.renderer.set_duplicate_callback(self._on_collection_duplicated)

    # ... similar for other callbacks

def _on_collection_renamed(self, item_id: str, old_name: str, new_name: str) -> bool:
    """Handle collection rename request."""
    try:
        # Validate name
        if not new_name or new_name.strip() == '':
            logger.warning("Empty collection name rejected")
            return False

        # Check for duplicates
        existing = self.library_manager.get_collection_by_name(new_name)
        if existing and existing['id'] != item_id:
            logger.warning(f"Collection name '{new_name}' already exists")
            # Show error dialog
            return False

        # Perform rename via library manager
        success = self.library_manager.rename_collection(item_id, new_name)

        if success:
            # Refresh sidebar to show new name
            self._refresh_collections_list()
            logger.info(f"✅ Renamed collection '{old_name}' to '{new_name}'")

        return success

    except Exception as e:
        logger.error(f"Failed to rename collection: {e}")
        return False

def _on_collection_deleted(self, item_id: str) -> bool:
    """Handle collection delete request."""
    try:
        # Perform deletion via library manager
        success = self.library_manager.remove_collection(item_id)

        if success:
            # Refresh sidebar
            self._refresh_collections_list()
            # Clear selection if deleted collection was selected
            logger.info(f"✅ Deleted collection: {item_id}")

        return success

    except Exception as e:
        logger.error(f"Failed to delete collection: {e}")
        return False

# Similar implementations for other actions
```

---

## Testing Strategy

### Unit Tests

#### Test Menu Creation
```python
def test_contextual_menu_for_collection():
    """Test that collection items show appropriate menu."""
    # Create test collection item
    # Right-click to trigger menu
    # Assert menu contains: Rename, Duplicate, Delete, etc.

def test_contextual_menu_for_section_header():
    """Test that section headers show appropriate menu."""
    # Create test section header
    # Right-click
    # Assert menu contains: New Collection, Expand All, Collapse All

def test_contextual_menu_blocks_inbox_deletion():
    """Test that Inbox cannot be deleted."""
    # Right-click Inbox
    # Assert "Remove from Library" is not in menu
```

#### Test Inline Rename
```python
def test_inline_rename_click_pause_click():
    """Test click-pause-click triggers rename."""
    # Select item with first click
    # Wait 0.5 seconds
    # Click same item again
    # Assert text field becomes editable

def test_inline_rename_enter_key():
    """Test Enter key triggers rename."""
    # Select item
    # Press Enter
    # Assert text field becomes editable

def test_inline_rename_validation():
    """Test rename validation."""
    # Start rename
    # Enter empty string
    # Assert rename rejected
    # Enter duplicate name
    # Assert rename rejected with error

def test_inline_rename_escape_cancels():
    """Test Esc key cancels rename."""
    # Start rename
    # Type new name
    # Press Esc
    # Assert original name retained
```

#### Test Menu Actions
```python
def test_duplicate_action():
    """Test Duplicate menu action."""
    # Right-click collection
    # Select "Duplicate"
    # Assert callback called with correct item_id
    # Assert new collection appears in sidebar

def test_delete_action_shows_confirmation():
    """Test Delete shows confirmation dialog."""
    # Right-click collection
    # Select "Remove from Library"
    # Assert NSAlert appears
    # Click Cancel
    # Assert collection still exists

def test_expand_collapse_all():
    """Test Expand/Collapse All actions."""
    # Create nested hierarchy
    # Collapse all
    # Assert all items collapsed
    # Expand all
    # Assert all items expanded
```

### Integration Tests

#### Test Library Manager Integration
```python
def test_rename_updates_database():
    """Test rename persists to database."""
    # Rename collection
    # Restart app
    # Assert new name persists

def test_delete_removes_from_library():
    """Test delete removes from library_manager."""
    # Delete collection
    # Query library_manager
    # Assert collection gone
```

### Manual Testing Checklist

- [ ] Right-click on collection shows correct menu
- [ ] Right-click on folder shows correct menu
- [ ] Right-click on section header shows correct menu
- [ ] Right-click on empty space shows correct menu
- [ ] Click-pause-click on collection name triggers rename
- [ ] Enter key on selected collection triggers rename
- [ ] Esc during rename cancels and restores original
- [ ] Enter during rename commits new name
- [ ] Empty name validation prevents rename
- [ ] Duplicate name validation prevents rename
- [ ] Delete shows confirmation dialog
- [ ] Delete removes collection from sidebar and database
- [ ] Duplicate creates new collection with "(Copy)" suffix
- [ ] Expand All expands entire hierarchy
- [ ] Collapse All collapses entire hierarchy
- [ ] Keyboard shortcuts work (Cmd+R, Cmd+D, Cmd+Delete)

---

## Implementation Plan

### Phase 1: Enhanced Menu System (2-3 hours)
1. ✅ Already have stub `outlineView_menuForTableColumn_item_`
2. Add `_get_item_type()` helper method
3. Add `_add_collection_menu_items()` and similar methods
4. Add menu action handler methods (performRenameItem_, etc.)
5. Add item ID tracking for menu actions
6. Test menu appears with correct items for each type

### Phase 2: Inline Rename Core (3-4 hours)
1. Add `outlineView_shouldEditTableColumn_item_` delegate method
2. Add `outlineView_setObjectValue_forTableColumn_byItem_` delegate method
3. Implement validation logic (empty names, duplicates)
4. Add `_on_rename_callback` property to NSOutlineViewSidebar
5. Add `set_rename_callback()` public API method
6. Test basic rename flow (programmatic edit)

### Phase 3: Click-Pause-Click Pattern (2 hours)
1. Add click tracking properties (_last_click_row, _last_click_time)
2. Override `mouseDown_` to detect click pattern
3. Trigger `editColumn_row_withEvent_select_` on pattern match
4. Test click-pause-click activates rename

### Phase 4: Keyboard Support (1 hour)
1. Override `keyDown_` to handle Enter key
2. Test Enter key activates rename
3. Test Esc key cancels rename (handled automatically by NSTextField)

### Phase 5: Menu Action Handlers (3-4 hours)
1. Implement all performXXX_ methods
2. Add callbacks to NSOutlineViewSidebar (_on_delete_callback, etc.)
3. Add public API methods (set_delete_callback, etc.)
4. Add NSAlert confirmation for destructive actions
5. Test all menu actions trigger callbacks

### Phase 6: Library View Integration (2-3 hours)
1. Add callback registration in library_view.py
2. Implement _on_collection_renamed() handler
3. Implement _on_collection_deleted() handler
4. Implement other action handlers
5. Add validation and error dialogs
6. Test end-to-end: menu → callback → database → UI update

### Phase 7: Testing & Polish (3-4 hours)
1. Write unit tests for menu creation
2. Write unit tests for rename flow
3. Write integration tests for library manager
4. Manual testing checklist
5. Fix bugs and edge cases
6. Documentation updates

**Total Estimated Time: 16-21 hours**

---

## Code Examples

### Key Code Snippets

#### Making NSTextField Editable
```python
@objc_method
def outlineView_shouldEditTableColumn_item_(self, outline_view, table_column, item) -> bool:
    """Block editing for section headers and Inbox."""
    if hasattr(item, '_python_data'):
        data = item._python_data
        if data.get('_is_section_header'):
            return False
        if data.get('text') == 'Inbox':
            return False
        return True
    return False
```

#### Extracting Item ID from Menu
```python
def _extract_item_id(self, data_item):
    """Extract item ID from data dict (collection ID or text fallback)."""
    if '_collection_data' in data_item:
        return data_item['_collection_data'].get('id')
    return data_item.get('id') or data_item.get('text')
```

#### Confirmation Dialog
```python
from rubicon.objc import ObjCClass
NSAlert = ObjCClass("NSAlert")

alert = NSAlert.alloc().init()
alert.messageText = "Delete 'My Collection'?"
alert.informativeText = "This action cannot be undone."
alert.addButtonWithTitle("Delete")
alert.addButtonWithTitle("Cancel")
alert.alertStyle = 2  # Critical

response = alert.runModal()
if response == 1000:  # First button (Delete)
    # Perform deletion
```

---

## References

### Apple Documentation
- [NSOutlineViewDelegate Protocol](https://developer.apple.com/documentation/appkit/nsoutlineviewdelegate)
- [NSOutlineViewDataSource Protocol](https://developer.apple.com/documentation/appkit/nsoutlineviewdatasource)
- [NSMenu Class](https://developer.apple.com/documentation/appkit/nsmenu)
- [NSTextField Class](https://developer.apple.com/documentation/appkit/nstextfield)

### Community Resources
- [How to do "Standard" macOS text field editing](https://developer.apple.com/forums/thread/52529)
- [NSTable/OutlineView: Edit textfield in a row without selecting the row](https://stackoverflow.com/questions/32419287/nstable-outlineview-edit-textfield-in-a-row-without-selecting-the-row)
- [Single-click renaming in NSTableView](https://lapcatsoftware.com/blog/2006/10/12/single-click-renaming-in-nstableview/)
- [How to prevent right-click textfield renaming in NSOutlineView](https://stackoverflow.com/questions/65477038/how-to-prevent-right-click-textfield-renaming-in-nsoutlineview)
- [Custom NSOutlineView doesn't show context menu when right clicked](https://stackoverflow.com/questions/46841946/custom-nsoutlineview-doesnt-show-context-menu-when-right-clicked)
- [How to add context sensitive menu to NSOutlineView](https://stackoverflow.com/questions/1309602/how-do-you-add-context-senstive-menu-to-nsoutlineview-ie-right-click-menu)
- [NSOutlineView how to connect context menu to the delegate](https://stackoverflow.com/questions/15689979/nsoutlineview-how-to-connect-context-menu-to-the-delegate)
- [How can I get the element that was right-clicked in a context menu](https://stackoverflow.com/questions/16032698/how-can-i-get-the-element-that-was-right-clicked-in-a-context-menu-on-a-nsoutlin)

---

## Risk Mitigation

### Potential Issues

1. **NSTextField Edit Mode Conflicts with Selection**
   - Risk: Clicking to rename might change selection
   - Mitigation: Use click-pause-click pattern with delay threshold

2. **Undo/Redo Not Integrated**
   - Risk: Users expect Cmd+Z to undo rename
   - Mitigation: NSTextField has built-in undo manager for edit session; document-level undo requires NSUndoManager integration (future enhancement)

3. **Menu Actions Block UI Thread**
   - Risk: Long-running operations freeze UI
   - Mitigation: Callbacks should return immediately, perform async operations in background

4. **Keyboard Shortcuts Conflict**
   - Risk: Cmd+R for rename conflicts with other shortcuts
   - Mitigation: Document all shortcuts, use macOS standard shortcuts where possible

### Validation Requirements

- Name cannot be empty
- Name cannot contain invalid characters (/, \, :, etc.)
- Name must be unique within section
- Special collections (Inbox) cannot be renamed/deleted

---

## Future Enhancements

1. **Multi-Select Operations**: Rename/delete multiple collections at once
2. **Drag to Rename**: Drag collection to new section renames folder
3. **Inline Field Editing**: Edit other metadata fields inline (not just name)
4. **Smart Folders**: Add "Smart Collection" menu item with criteria editor
5. **Color Labels**: macOS Finder-style color labels for collections
6. **Quick Look**: Space bar preview for collections
7. **Undo Manager Integration**: Full undo/redo support beyond text field

---

## Conclusion

This design provides a comprehensive, native macOS contextual menu and inline rename system that:

✅ Matches Finder/DEVONthink/Mail.app UX patterns
✅ Integrates cleanly with existing NSOutlineViewSidebar architecture
✅ Provides type-specific menu options
✅ Supports click-pause-click and Enter key rename triggers
✅ Validates renames and shows appropriate error dialogs
✅ Connects to Python business logic via callbacks
✅ Includes confirmation dialogs for destructive actions
✅ Is testable via unit and integration tests

The implementation can be done in phases over 16-21 hours, with immediate value from Phase 1 (enhanced menus) and Phase 2 (basic rename).
