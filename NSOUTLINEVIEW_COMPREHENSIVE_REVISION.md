# NSOutlineView Sidebar - Comprehensive Revision Plan
## Mail.app Parity Implementation

**Date**: November 27, 2025
**Goal**: Achieve full visual and functional parity with Mail.app sidebar

---

## Screenshot Analysis - Issues Identified

### Visual/Styling Issues (High Priority)

#### 1. Section Header Styling ❌
**Current**: `INBOX`, `LIBRARY` in all caps, bold font, dark color
**Mail.app**: `Mailboxes`, `Favorites` in title case, medium weight, lighter gray

**Fix Required**:
- Line 395: Remove `.upper()` call
- Line 341: Change `NSFont.boldSystemFontOfSize(11)` to `NSFont.systemFontOfSize(11)` with medium weight
- Line 344: Change `NSColor.secondaryLabelColor` to custom gray color `#8E8E93`
- Verify font size is 11pt (correct) but weight should be `.medium` not `.bold`

#### 2. Disclosure Triangle Alignment ❌
**Current**: Triangle not vertically aligned with text baseline
**Mail.app**: Triangle centered vertically with text

**Fix Required**:
- NSOutlineView automatically handles disclosure triangles
- Issue: Need to check `indentationPerLevel` and `indentationMarkerFollowsCell` settings
- The triangle should be part of NSOutlineView's built-in rendering, not custom

#### 3. Hierarchical Indentation ❌
**Current**: No indentation for child items (January, February under 2024)
**Mail.app**: Clear indentation hierarchy

**Fix Required**:
- Set `indentationPerLevel` (currently missing or set to 0)
- Mail.app uses ~16-20px per level
- Line ~800-900: In NSOutlineView initialization, add:
  ```objective-c
  self.indentationPerLevel = 16  // 16px per hierarchy level
  self.indentationMarkerFollowsCell = True  // Triangle follows indent
  ```

#### 4. Text Color Adjustment ❌
**Current**: Item text too dark (using `NSColor.labelColor`)
**Mail.app**: Slightly lighter gray for unselected items

**Fix Required**:
- Line 405: Change from `NSColor.labelColor` to `NSColor.secondaryLabelColor`
- OR use custom color for more control

#### 5. Spacing and Margins ❌
**Current**: Section header positioning incorrect
**Mail.app**: More space above section headers, tighter spacing for items

**Fix Required**:
- Implement `outlineView_heightOfRowByItem_` more precisely:
  - Section headers: 28px (currently 32px is too much)
  - Regular items: 24px (correct)
  - First section header: additional top margin
- Line 335: Adjust text field Y position from 14 to 10-12

---

### Missing Features (Medium Priority)

#### 6. Drag and Drop Reordering ✅ (Partially Implemented)
**Status**: Basic drag/drop exists but may not be working
**Location**: Lines 499-800+

**Fix Required**:
- Review and test existing drag/drop implementation
- Ensure `registerForDraggedTypes:` is called
- Verify `outlineView_validateDrop_proposedItem_proposedChildIndex_` logic
- Test reordering within same section

#### 7. Drag and Drop onto Containers ⚠️
**Status**: May exist but needs verification
**Required**: Ability to drop items onto folders/collections

**Fix Required**:
- In `outlineView_validateDrop_...`, allow drops onto expandable items
- Visual feedback when hovering over valid drop targets
- Implement in `outlineView_acceptDrop_item_childIndex_`

#### 8. Live Data Updates ❌
**Status**: No live update mechanism
**Required**: Add/remove/update items without full reload

**Fix Required**:
- Implement methods:
  - `insert_item(item, parent, index)` - uses `insertItemsAtIndexes:inParent:`
  - `remove_item(item)` - uses `removeItemsAtIndexes:inParent:`
  - `update_item(item)` - uses `reloadItem:reloadChildren:`
- Add animation support (`NSTableViewAnimationSlideLeft`)

#### 9. Selection Styling ⚠️
**Status**: May work but needs visual verification
**Required**: Match Mail.app's blue selection gradient

**Fix Required**:
- NSOutlineView handles this automatically on macOS
- May need to set `selectionHighlightStyle = 1` (NSTableViewSelectionHighlightStyleRegular)
- Verify blue gradient appears correctly

#### 10. Sidebar Resize Handling ⚠️
**Status**: May work via column width updates
**Required**: Sidebar should resize with split view

**Fix Required**:
- Verify that column width updates trigger cell frame updates
- Current code at lines 381-390 handles this
- May need to test with actual split view

#### 11. Lazy Loading ❌
**Status**: Not implemented - loads all data upfront
**Required**: Only load children when parent is expanded

**Fix Required**:
- Modify `outlineView_child_ofItem_` to check if children are loaded
- Add `_children_loaded` flag to item data
- When `outlineView_isItemExpandable_` returns True, don't load children until expansion
- Implement `outlineViewItemWillExpand_` to load children on-demand
- Add callback: `on_expand(item)` -> List[children]

---

### Additional Features (Low Priority)

#### 12. Contextual Menus ❌
**Status**: Not implemented
**Required**: Right-click menu for items

**Fix Required**:
- Implement `outlineView_menuForTableColumn_item_`
- Create NSMenu with appropriate actions
- Add callback: `on_context_menu(item)` -> List[menu_items]

#### 13. Inline Editing (Rename) ❌
**Status**: Not implemented
**Required**: Double-click to rename items

**Fix Required**:
- Set `textField.editable = True` for appropriate items
- Implement `outlineView_shouldEditTableColumn_item_`
- Add callback: `on_rename(item, new_text)` -> bool

#### 14. Keyboard Navigation ✅
**Status**: Should work automatically via NSOutlineView
**Required**: Arrow keys, spacebar, etc.

**Verify**: Test with demo app

---

## Implementation Order

### Phase 1: Visual Fixes (Immediate - 2 hours)
1. ✅ Fix section header styling (title case, lighter font, gray color)
2. ✅ Add hierarchical indentation (indentationPerLevel)
3. ✅ Adjust text colors for items
4. ✅ Fix spacing and margins
5. ✅ Verify disclosure triangle alignment

### Phase 2: Core Functionality (Next - 4 hours)
6. ✅ Test and fix drag and drop reordering
7. ✅ Implement drag onto containers
8. ✅ Add live data update methods (insert/remove/update)
9. ✅ Verify selection styling

### Phase 3: Advanced Features (Later - 6 hours)
10. ✅ Implement lazy loading for hierarchical data
11. ✅ Add contextual menu support
12. ✅ Implement inline editing (rename)
13. ✅ Test sidebar resize handling

### Phase 4: Polish and Testing (Final - 2 hours)
14. ✅ Update demo app with all features
15. ✅ Add comprehensive documentation
16. ✅ Performance testing with large datasets
17. ✅ Accessibility review

---

## Code Locations

### macos_sidebar.py Structure
- Lines 85-110: `SidebarItem` class
- Lines 112-200: `SidebarDataSource` class
- Lines 202-800: `SidebarDelegate` class
  - 282-470: Cell rendering (`outlineView_viewForTableColumn_item_`)
  - 499-800: Drag and drop methods
- Lines 827-1620: `NSOutlineViewSidebar` class (main interface)

### Key Methods to Modify
1. **Cell Rendering** (lines 282-470):
   - Section header styling
   - Indentation handling
   - Text colors

2. **Initialization** (lines ~900-1000):
   - Set indentationPerLevel
   - Configure drag/drop types
   - Set selection style

3. **Data Updates** (NEW methods needed):
   - `insert_item()`
   - `remove_item()`
   - `update_item()`

4. **Lazy Loading** (lines 153-180 + NEW):
   - Modify `outlineView_child_ofItem_`
   - Add `outlineViewItemWillExpand_`
   - Add `_children_loaded` flag handling

---

## Testing Checklist

### Visual Tests
- [ ] Section headers show title case (not uppercase)
- [ ] Section headers are lighter gray (#8E8E93)
- [ ] Section headers use medium weight font
- [ ] Items have proper hierarchical indentation
- [ ] Disclosure triangles align with text
- [ ] Text colors match Mail.app
- [ ] Spacing matches Mail.app

### Functional Tests
- [ ] Drag and drop reorders items within section
- [ ] Drag and drop onto folders works
- [ ] Can add items dynamically without reload
- [ ] Can remove items with animation
- [ ] Can update item text/badge dynamically
- [ ] Selection shows blue gradient
- [ ] Sidebar resizes correctly with window

### Advanced Tests
- [ ] Lazy loading: children only load on expand
- [ ] Contextual menu appears on right-click
- [ ] Inline editing works with double-click
- [ ] Large datasets (1000+ items) perform well
- [ ] Keyboard navigation works correctly

---

## API Changes

### New Methods
```python
# Live updates
sidebar.insert_item(item_dict, parent=None, index=-1, animated=True)
sidebar.remove_item(item_dict, animated=True)
sidebar.update_item(item_dict, reload_children=False)

# Lazy loading
sidebar.set_children_loader(callback)  # callback(item) -> List[children]

# Contextual menus
sidebar.set_context_menu_builder(callback)  # callback(item) -> List[menu_items]

# Inline editing
sidebar.set_rename_callback(callback)  # callback(item, new_text) -> bool
```

### New Item Data Fields
```python
item = {
    'text': 'Documents',
    'icon': 'doc.text',
    'badge_text': '123',
    'trailing_icon': 'checkmark.circle.fill',
    '_has_children': True,
    '_children': [...],  # Optional: None for lazy loading
    '_children_loaded': False,  # NEW: For lazy loading
    '_node_type': 'collection',
    '_is_section_header': False,
}
```

---

## Success Criteria

1. **Visual Parity**: Side-by-side comparison with Mail.app shows matching appearance
2. **Functional Parity**: All Mail.app sidebar features work correctly
3. **Performance**: Handles 1000+ items smoothly with lazy loading
4. **Maintainability**: Code is well-documented and tested
5. **API Simplicity**: Easy to use from Fichero application code

---

**Next Action**: Start with Phase 1 visual fixes, as these are most visible and impactful.
