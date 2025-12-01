# NSOutlineView Sidebar Enhancement Plan

## Executive Summary

This document provides a comprehensive plan to enhance the macOS sidebar renderer (`NSOutlineViewSidebar`, formerly `MacOSSidebarRenderer`) to expose ALL NSOutlineView capabilities through a clean Python API. The goal is to enable Mail.app-style window integration with the sidebar extending into the titlebar area.

**Status**: Phase 0 Complete - Renamed to `NSOutlineViewSidebar`
**Timeline**: 13-19 weeks total (3-5 months) for all phases

---

## Phase 0: Rename Complete ✅

**Status**: DONE (November 27, 2025)

### Changes Made:
- Renamed `MacOSSidebarRenderer` → `NSOutlineViewSidebar` throughout codebase
- Updated 8 files:
  1. `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py`
  2. `widget_list_demo.py`
  3. `src/fichero/shared/widgets/list_widget/demos/widget_list_demo.py`
  4. `src/fichero/shared/widgets/list_widget/base.py`
  5. Documentation files (markdown references)

### Rationale:
- Better reflects that it's a native NSOutlineView wrapper
- Follows Apple's naming convention
- Clearer distinction from canvas-based `SidebarRenderer`
- More discoverable for developers familiar with AppKit

---

## Current Implementation Status

### ✅ Already Implemented (1437 lines)

**Core NSOutlineView Features:**
- Data Source Protocol (`outlineView_numberOfChildrenOfItem_`, `outlineView_child_ofItem_`, `outlineView_isItemExpandable_`)
- Delegate Protocol (`outlineView_shouldSelectItem_`, `outlineView_heightOfRowByItem_`, `outlineView_viewForTableColumn_item_`)
- View-Based Rendering (custom `NSTableCellView` with icon + text)
- Hierarchical Data (callback-based children retrieval)
- Section Headers (non-selectable, uppercase, gray, bold, 32px height)
- SF Symbol Icons (leading 16x16 icons)
- Selection Handling (callback via `on_select`)
- Custom Row Heights (section headers 32px, regular items 24px)
- Text Truncation (middle truncation like Finder)
- Vibrancy Background (`NSVisualEffectView` with sidebar material)
- Drag-and-Drop (internal reordering + external file drops)

**API Patterns:**
- Callback-based selection and hierarchy
- Renderer pattern (separates widget creation from data management)
- Clean separation of concerns

### ❌ Missing Features

**Display:**
- Trailing icons/badges (unread counts, status indicators)
- Floating group rows (section headers that float on scroll)
- Custom colors per item
- Multiple columns

**Interaction:**
- Inline editing (rename)
- Right-click contextual menus
- Double-click activation callback
- Keyboard navigation improvements
- Expand/collapse animations (custom)

**Programmatic Control:**
- `expand_item()`, `collapse_item()` methods
- `expand_all()`, `collapse_all()` batch operations
- `is_item_expanded()` query
- Expand/collapse state persistence

**Drag & Drop Advanced:**
- Custom drag images
- Drop zones with visual feedback
- Spring-loaded folders

**Window Integration:**
- Titlebar extension (sidebar into title bar)
- Toolbar overlay (Mail.app-style)
- NSSplitView integration
- Translucent titlebar

---

## Implementation Phases

### Phase 1: Essential Display Features (4-6 weeks)

#### 1.1 Trailing Icons/Badges (1 week)
**Goal**: Add right-aligned badges and status icons

**Implementation**:
```python
# Item data structure
item = {
    'text': 'Documents',
    'icon': 'doc.text',
    'badge_text': '123',             # NEW: Unread count
    'trailing_icon': 'checkmark.circle',  # NEW: Status icon
}

# In outlineView_viewForTableColumn_item_:
if badge_text := item_data.get('badge_text'):
    badge_label = NSTextField.alloc().initWithFrame(((TEXT_WIDTH - 30, 6), (26, 16)))
    badge_label.stringValue = badge_text
    badge_label.font = NSFont.systemFontOfSize(10)
    badge_label.textColor = NSColor.secondaryLabelColor
    badge_label.alignment = 1  # Right align
    badge_label.bordered = False
    badge_label.editable = False
    badge_label.backgroundColor = NSColor.clearColor
    view.addSubview(badge_label)

if trailing_icon := item_data.get('trailing_icon'):
    icon_view = NSImageView.alloc().initWithFrame(((TEXT_WIDTH - 50, 4), (16, 16)))
    icon_view.image = NSImage.imageNamed(trailing_icon)
    view.addSubview(icon_view)
```

**Testing**: Demo app with badges showing unread counts, status icons

#### 1.2 Programmatic Expand/Collapse (1 week)
**Goal**: API to control expand/collapse programmatically

**Implementation**:
```python
def expand_item(self, item_data: dict):
    """Expand item programmatically"""
    item = self._find_wrapped_item(item_data)
    if item:
        self._toga_sidebar.expandItem_(item)

def collapse_item(self, item_data: dict):
    """Collapse item programmatically"""
    item = self._find_wrapped_item(item_data)
    if item:
        self._toga_sidebar.collapseItem_(item)

def expand_all(self):
    """Expand all expandable items"""
    for item in self._wrapped_items:
        self._toga_sidebar.expandItem_expandChildren_(item, True)

def collapse_all(self):
    """Collapse all items"""
    for item in self._wrapped_items:
        self._toga_sidebar.collapseItem_(item)

def is_item_expanded(self, item_data: dict) -> bool:
    """Check if item is expanded"""
    item = self._find_wrapped_item(item_data)
    if item:
        return bool(self._toga_sidebar.isItemExpanded_(item))
    return False

def _find_wrapped_item(self, item_data: dict):
    """Find wrapped SidebarItem for given item_data"""
    for item in self._wrapped_items:
        if item._python_data == item_data:
            return item
    return None
```

**Testing**: Demo app with expand/collapse buttons

#### 1.3 Animated Incremental Updates (1 week)
**Goal**: Smooth animations for insert/remove/move

**Implementation**:
```python
def remove_item_at_index(self, index: int, parent_item=None) -> bool:
    """Remove item with animation"""
    NSIndexSet = ObjCClass("NSIndexSet")
    index_set = NSIndexSet.indexSetWithIndex(index)

    # NSTableViewAnimationSlideLeft = 0x10
    self._toga_sidebar.removeItemsAtIndexes_inParent_withAnimation_(
        index_set, parent_item, 0x10
    )
    return True

def add_item_at_index(self, index: int, item_data: dict, parent_item=None) -> bool:
    """Add item with animation"""
    # Wrap item in SidebarItem
    wrapped_item = SidebarItem.alloc().init()
    wrapped_item._python_data = item_data
    self._wrapped_items.insert(index, wrapped_item)

    NSIndexSet = ObjCClass("NSIndexSet")
    index_set = NSIndexSet.indexSetWithIndex(index)

    # NSTableViewAnimationSlideLeft = 0x10
    self._toga_sidebar.insertItemsAtIndexes_inParent_withAnimation_(
        index_set, parent_item, 0x10
    )
    return True

def move_item(self, from_index: int, to_index: int, parent_item=None) -> bool:
    """Move item with animation"""
    # Remove with animation
    self.remove_item_at_index(from_index, parent_item)

    # Adjust index if moving down
    if to_index > from_index:
        to_index -= 1

    # Insert with animation
    item_data = self._data[from_index]
    self.add_item_at_index(to_index, item_data, parent_item)
    return True
```

**Testing**: Demo app with add/remove/move buttons

#### 1.4 Inline Text Editing (2 weeks)
**Goal**: Double-click to rename items

**Implementation**:
```python
def set_on_rename_callback(self, callback):
    """Set callback for when item is renamed"""
    self._on_rename_callback = callback

@objc_method
def outlineView_shouldEditTableColumn_item_(self, outline_view, column, item) -> bool:
    """Allow editing if item is marked as editable"""
    if hasattr(item, '_python_data'):
        return item._python_data.get('_editable', False)
    return False

@objc_method
def outlineView_setObjectValue_forTableColumn_byItem_(
    self, outline_view, value, column, item
):
    """Handle edited value"""
    if hasattr(item, '_python_data'):
        old_text = item._python_data.get('text', '')
        new_text = str(value)

        if old_text != new_text and self.interface._on_rename_callback:
            # Call validation callback
            accepted = self.interface._on_rename_callback(item._python_data, new_text)

            if accepted:
                # Update item data
                item._python_data['text'] = new_text
                # Reload item to reflect change
                outline_view.reloadItem_(item)
            else:
                # Revert to old value
                outline_view.reloadItem_(item)
```

**Testing**: Demo app with editable items

#### 1.5 Contextual Menus (1 week)
**Goal**: Right-click menus per item

**Implementation**:
```python
def set_contextual_menu_callback(self, callback):
    """Set callback to create contextual menu"""
    self._contextual_menu_callback = callback

@objc_method
def menuForEvent_(self, event):
    """Provide contextual menu for right-click"""
    # Get clicked item
    point = self.convertPoint_fromView_(event.locationInWindow, None)
    row = self.rowAtPoint_(point)

    if row >= 0:
        item = self.itemAtRow_(row)
        if item and self.interface._contextual_menu_callback:
            # Call callback to create menu
            menu = self.interface._contextual_menu_callback(item._python_data, event)
            return menu

    return None
```

**Testing**: Demo app with contextual menus

---

### Phase 2: Enhanced User Experience (3-4 weeks)

#### 2.1 Tooltips (1 week)
**Goal**: Show full text on hover for truncated items

**Implementation**:
```python
@objc_method
def outlineView_toolTipForCell_rect_tableColumn_item_mouseLocation_(
    self, outline_view, cell, rect, column, item, mouse_location
):
    """Provide tooltip for truncated text"""
    if hasattr(item, '_python_data'):
        text = item._python_data.get('text', '')
        # Always show tooltip - NSOutlineView will only display if needed
        return at(text)
    return None
```

#### 2.2 Floating Group Rows (1 week)
**Goal**: Section headers float above content on scroll

**Implementation**:
```python
@objc_method
def outlineView_isGroupItem_(self, outline_view, item) -> bool:
    """Mark section headers as group items"""
    if hasattr(item, '_python_data'):
        return item._python_data.get('_is_section_header', False)
    return False
```

#### 2.3 Expand State Persistence (1 week)
**Goal**: Save and restore expand/collapse state

**Implementation**:
```python
def save_expand_state(self) -> Dict[str, bool]:
    """Return dict of item_id -> expanded state"""
    state = {}
    for item in self._wrapped_items:
        item_id = item._python_data.get('id')
        if item_id:
            is_expanded = self._toga_sidebar.isItemExpanded_(item)
            state[item_id] = bool(is_expanded)
    return state

def restore_expand_state(self, state: Dict[str, bool]):
    """Restore expand state from saved dict"""
    for item in self._wrapped_items:
        item_id = item._python_data.get('id')
        if item_id in state and state[item_id]:
            self._toga_sidebar.expandItem_(item)
        elif item_id in state and not state[item_id]:
            self._toga_sidebar.collapseItem_(item)

def enable_autosave(self, name: str):
    """Enable automatic expand state persistence"""
    self._toga_sidebar.autosaveExpandedItems = True
    self._toga_sidebar.autosaveName = name
```

#### 2.4 Search/Filtering (1 week)
**Goal**: Filter visible items by search query

**Implementation**:
```python
def set_search_filter(self, query: str):
    """Filter items by search query"""
    self._search_query = query
    self._toga_sidebar.reloadData()

    if query:
        # Auto-expand items matching search
        self._expand_matching_items(query)

def _expand_matching_items(self, query: str):
    """Expand all items matching query"""
    query_lower = query.lower()
    for item in self._wrapped_items:
        text = item._python_data.get('text', '').lower()
        if query_lower in text:
            # Expand all ancestors
            self._expand_ancestors(item)

def clear_search_filter(self):
    """Clear search filter"""
    self.set_search_filter('')
```

#### 2.5 Double-Click Activation (0.5 weeks)
**Goal**: Separate activation from selection

**Implementation**:
```python
def set_on_activate_callback(self, callback):
    """Set callback for item activation (double-click)"""
    self._on_activate_callback = callback

@objc_method
def outlineView_shouldSelectItem_(self, outline_view, item) -> bool:
    """Track double-clicks and fire activation callback"""
    import time
    current_time = time.time()

    # Check if this is a double-click
    if (hasattr(self, '_last_click_item') and
        self._last_click_item == item and
        (current_time - self._last_click_time) < 0.5):

        # Fire activation callback
        if self.interface._on_activate_callback:
            self.interface._on_activate_callback(item._python_data)

        return False  # Don't select on double-click

    # Update last click tracking
    self._last_click_item = item
    self._last_click_time = current_time

    # Allow selection for section headers check
    if hasattr(item, '_python_data'):
        return not item._python_data.get('_is_section_header', False)

    return True
```

---

### Phase 3: Window Integration - Mail.app Style (3-4 weeks)

#### 3.1 Titlebar Extension (1 week)
**Goal**: Sidebar extends into titlebar area

**Implementation**:
```python
def integrate_with_window(self, toga_window):
    """Integrate sidebar with window titlebar (Mail.app style)"""
    if not hasattr(toga_window, '_impl'):
        return

    native_window = toga_window._impl.native

    # Enable full-size content view
    # NSWindowStyleMaskFullSizeContentView = 0x8000
    native_window.styleMask |= 0x8000

    # Make titlebar transparent
    native_window.titlebarAppearsTransparent = True

    # Hide titlebar separator
    # NSTitlebarSeparatorStyleNone = 0
    native_window.titlebarSeparatorStyle = 0
```

#### 3.2 NSSplitView Integration (1 week)
**Goal**: Wrap sidebar + content in NSSplitView

**Implementation**:
```python
def configure_split_view(
    self,
    sidebar_width: int = 250,
    min_width: int = 150,
    max_width: int = 400,
    collapsible: bool = True
):
    """Configure NSSplitView for sidebar layout"""
    NSSplitView = ObjCClass("NSSplitView")

    # Create split view
    split_view = NSSplitView.alloc().initWithFrame(window_frame)
    split_view.vertical = True
    split_view.dividerStyle = 1  # Thin divider

    # Add sidebar
    split_view.addSubview(self._vibrancy_view)

    # Set width constraints
    self._sidebar_min_width = min_width
    self._sidebar_max_width = max_width
    self._sidebar_collapsible = collapsible

    # Set delegate for constraints
    split_view.delegate = self._split_view_delegate

def toggle_sidebar(self):
    """Collapse/expand sidebar with animation"""
    if not hasattr(self, '_split_view'):
        return

    is_collapsed = self._split_view.isSubviewCollapsed_(self._vibrancy_view)
    if is_collapsed:
        self._split_view.setPosition_ofDividerAtIndex_(250, 0)
    else:
        self._split_view.setPosition_ofDividerAtIndex_(0, 0)
```

#### 3.3 Toolbar Overlay (1 week)
**Goal**: Toolbar appears over sidebar

**Implementation**:
```python
def adjust_for_toolbar(self, toolbar_height: int = 52):
    """Adjust sidebar top inset for toolbar overlay"""
    # Add top padding to sidebar content
    if self._toga_sidebar:
        # Update content inset
        edge_insets = NSEdgeInsets()
        edge_insets.top = toolbar_height
        edge_insets.left = 0
        edge_insets.bottom = 0
        edge_insets.right = 0

        self._toga_sidebar.enclosingScrollView.contentInsets = edge_insets
```

#### 3.4 Polish & Testing (1 week)
- Handle window resize
- Edge case testing
- Cross-window consistency
- Performance optimization

---

### Phase 4: Advanced Features (2-3 weeks)

#### 4.1 Advanced Delegate Methods (1 week)
```python
@objc_method
def outlineView_shouldExpandItem_(self, outline_view, item) -> bool:
    """Allow/block item expansion"""
    if self.interface._should_expand_callback:
        return self.interface._should_expand_callback(item._python_data)
    return True

@objc_method
def outlineViewItemWillExpand_(self, notification):
    """Called before item expands"""
    if self.interface._will_expand_callback:
        item = notification.userInfo['NSObject']
        self.interface._will_expand_callback(item._python_data)

@objc_method
def outlineViewItemDidExpand_(self, notification):
    """Called after item expands"""
    if self.interface._did_expand_callback:
        item = notification.userInfo['NSObject']
        self.interface._did_expand_callback(item._python_data)
```

#### 4.2 Accessibility (1 week)
```python
def set_accessibility_label_callback(self, callback):
    """Set callback to provide accessibility labels"""
    self._accessibility_label_callback = callback

# In cell creation:
if self.interface._accessibility_label_callback:
    label = self.interface._accessibility_label_callback(item._python_data)
    view.setAccessibilityLabel(label)
```

#### 4.3 Performance Optimization (1 week)
- Large dataset handling (1000+ items)
- Lazy loading children
- View recycling optimization
- Memory profiling

---

### Phase 5: Demo & Documentation (1-2 weeks)

#### 5.1 Enhanced Demo App (1 week)
**Features to showcase:**
- All display features (badges, trailing icons, floating headers)
- All interactions (edit, contextual menu, double-click)
- Expand/collapse API
- Animations
- Search/filtering
- Window integration
- Persistence

**Demo UI:**
```
┌─────────────────────────────────────────────────┐
│ [⚙️ Features] [🔍 Search] [▶️ Test]            │
├──────────────┬──────────────────────────────────┤
│   Sidebar    │   Feature Control Panel          │
│   (Testing)  │                                  │
│              │   ☑ Show badges                  │
│              │   ☑ Show trailing icons          │
│              │   ☑ Enable editing               │
│              │   ☑ Enable menus                 │
│              │   ☑ Enable animations            │
│              │                                  │
│              │   [Expand All] [Collapse All]    │
│              │   [Add Item] [Remove Selected]   │
│              │                                  │
└──────────────┴──────────────────────────────────┘
```

#### 5.2 Documentation (1 week)
- Complete API reference
- Usage examples for each feature
- Integration guide
- Best practices
- Performance tips

---

## API Reference (Proposed)

### Initialization
```python
sidebar = NSOutlineViewSidebar(
    headings=['text'],
    on_select=callback,
    multiple_select=False,
    toga_style=Pack(flex=1)
)
```

### Data Management
```python
sidebar.attach_source(data)
sidebar.set_get_children_callback(get_children)
sidebar.refresh()
```

### Expand/Collapse
```python
sidebar.expand_item(item_data)
sidebar.collapse_item(item_data)
sidebar.expand_all()
sidebar.collapse_all()
sidebar.is_item_expanded(item_data)
```

### Persistence
```python
state = sidebar.save_expand_state()
sidebar.restore_expand_state(state)
sidebar.enable_autosave("FicheroSidebar")
```

### Editing
```python
sidebar.set_on_rename_callback(on_rename)
```

### Menus
```python
sidebar.set_contextual_menu_callback(create_menu)
```

### Search
```python
sidebar.set_search_filter("query")
sidebar.clear_search_filter()
```

### Window Integration
```python
sidebar.integrate_with_window(toga_window)
sidebar.configure_split_view(width=250, min=150, max=400)
sidebar.toggle_sidebar()
```

### Item Data Structure
```python
item = {
    'text': 'Documents',
    'icon': 'doc.text',              # SF Symbol
    'badge_text': '123',             # Trailing badge
    'trailing_icon': 'checkmark.circle',  # Status icon
    '_editable': True,               # Allow rename
    '_node_type': 'collection',
    '_is_section_header': False,
    '_has_children': True,
    '_children': [...]
}
```

---

## Timeline Summary

| Phase | Features | Duration | Status |
|-------|----------|----------|--------|
| 0 | Rename to NSOutlineViewSidebar | Done | ✅ Complete |
| 1 | Essential Display Features | 4-6 weeks | Pending |
| 2 | Enhanced UX | 3-4 weeks | Pending |
| 3 | Window Integration | 3-4 weeks | Pending |
| 4 | Advanced Features | 2-3 weeks | Pending |
| 5 | Demo & Docs | 1-2 weeks | Pending |
| **Total** | **All Features** | **13-19 weeks** | **In Progress** |

---

## Success Criteria

- ✅ All NSOutlineView delegate/datasource methods accessible
- ✅ Clean Python API (no ObjC exposure)
- ✅ Mail.app-style window layout achievable
- ✅ Demo app showcases all features
- ✅ Documentation covers all capabilities
- ✅ Backward compatible (existing code still works)
- ✅ Performance with 1000+ items
- ✅ Memory efficient

---

## Next Steps

1. **Phase 1.1**: Implement trailing badges and icons (1 week)
2. **Phase 1.2**: Add programmatic expand/collapse API (1 week)
3. **Test incrementally**: Update demo app after each feature
4. **Document as you go**: Update API docs with each phase

---

## References

- Apple NSOutlineView Documentation: https://developer.apple.com/documentation/appkit/outline-view
- Apple Views and Controls: https://developer.apple.com/documentation/appkit/views-and-controls
- Mail.app screenshot reference: `/Users/dtubb/Pictures/Screen Shots/Screenshot 2025-11-27 at 11.03.48 AM.png`
- Current implementation: `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py` (1437 lines)

---

**Document Version**: 1.0
**Last Updated**: November 27, 2025
**Author**: AI Assistant (with human oversight)
