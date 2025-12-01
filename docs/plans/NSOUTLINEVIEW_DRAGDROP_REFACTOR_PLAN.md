# NSOutlineView Drag-and-Drop Refactor Plan

**Date**: November 30, 2025
**Status**: ✅ COMPLETED
**Goal**: Refactor drag-and-drop implementation to follow Apple's NSOutlineView best practices

---

## Executive Summary

The current drag-and-drop implementation in `macos_sidebar.py` works but feels brittle. After reviewing Apple's official documentation and sample code from "NavigatingHierarchicalDataUsingOutlineAndSplitViews", this plan identifies deviations from best practices and proposes targeted fixes.

---

## Analysis: Current Implementation vs Apple Best Practices

### 1. Validation Logic Structure

**Apple's Pattern** (from `OutlineViewController+DragDrop.swift:191-227`):
```swift
func outlineView(_ outlineView: NSOutlineView,
                 validateDrop info: NSDraggingInfo,
                 proposedItem item: Any?,
                 proposedChildIndex index: Int) -> NSDragOperation {
    var result = NSDragOperation()

    // FIRST: Early exit for invalid drops
    guard index != -1,     // Don't allow dropping ON a child (only BETWEEN)
          item != nil      // Must have valid drop target
    else { return result }

    // THEN: Check drop target validity
    if let dropNode = node(from: item) {
        if !dropNode.isURLNode {  // Can modify this node
            if info.draggingPasteboard.availableType(from: [.nodeRowPasteBoardType]) != nil {
                // Internal drag
                if dropNode.isDirectory {
                    if okToDrop(draggingInfo: info, locationItem: item as? NSTreeNode) {
                        result = .move
                    }
                } else {
                    result = .move
                }
            } else if info.draggingPasteboard.availableType(from: [.fileURL]) != nil {
                result = .link  // External files
            } else {
                result = .copy  // File promises
            }
        }
    }
    return result
}
```

**Key Apple Principles:**
1. **Early Exit Pattern**: Check `index != -1` FIRST - Apple explicitly rejects drops "ON" items (index == -1) in many cases
2. **Clean Separation**: Pasteboard type checking happens AFTER target validation
3. **Separate Utility Function**: `okToDrop()` handles circular reference checking in isolation
4. **No setDropItem calls in validateDrop**: Apple doesn't call `setDropItem:dropChildIndex:` to "retarget" - they just return the appropriate NSDragOperation

**Current Implementation Issues** (lines 1002-1161):
- Complex nested conditions mixing target validation with visual feedback
- Calls `setDropRow_dropOperation_` DURING validation (lines 1043, 1089, 1114, etc.)
- Circular reference check is inline rather than factored out
- No clear early-exit pattern

### 2. setDropItem:dropChildIndex: Usage

**Apple Documentation** (from `setDropItem:dropChildIndex: | Documentation.pdf`):
> "Used to **retarget** a proposed drop."
>
> - Drop ON someItem: item=someItem, index=NSOutlineViewDropOnItemIndex (-1)
> - Drop BETWEEN child 2 and 3: item=someItem, index=3
> - Drop ON un-expandable item: item=someItem, index=NSOutlineViewDropOnItemIndex

**Apple's Intent**: This method is for RETARGETING (changing where the drop will go), not for setting visual feedback style. The visual feedback (blue highlight vs line) is determined automatically based on the index value.

**Current Implementation Misuse**:
```python
# Line 1043 - Using to "clear indicators" (wrong pattern)
outline_view.setDropRow_dropOperation_(NS_OUTLINE_VIEW_DROP_ON_ITEM_INDEX, NS_TABLE_VIEW_DROP_ABOVE)
return 0

# Line 1114 - Setting visual feedback explicitly (redundant)
outline_view.setDropRow_dropOperation_(container_row, NS_TABLE_VIEW_DROP_ON)
```

**Correct Usage**: Only call `setDropItem:dropChildIndex:` when you need to REDIRECT a drop to a different location than proposed. The visual feedback is automatic.

### 3. Circular Reference Prevention

**Apple's Pattern** (`okToDrop` utility, lines 162-185):
```swift
private func okToDrop(draggingInfo: NSDraggingInfo, locationItem: NSTreeNode?) -> Bool {
    var droppedOntoItself = false
    draggingInfo.enumerateDraggingItems(options: [],
                                        for: outlineView,
                                        classes: [NSPasteboardItem.self],
                                        searchOptions: [:]) { dragItem, _, _ in
        if let droppedPasteboardItem = dragItem.item as? NSPasteboardItem {
            if let checkItem = self.itemFromPasteboardItem(droppedPasteboardItem) {
                let treeRoot = self.treeController.arrangedObjects
                let node = treeRoot.descendant(at: checkItem.indexPath)
                var parent = locationItem
                while parent != nil {
                    if parent == node {
                        droppedOntoItself = true
                        break
                    }
                    parent = parent?.parent
                }
            }
        }
    }
    return !droppedOntoItself
}
```

**Apple's Approach**:
- Uses `enumerateDraggingItems` to get the dragged item
- Walks UP the tree from drop location checking if dragged item is an ancestor
- Clean boolean return - no side effects

**Current Implementation** (lines 1092-1102):
- Inline in validateDrop (harder to test/maintain)
- Uses custom `_is_descendant_of` which walks DOWN from item (less efficient)
- Mixes validation with visual feedback updates

### 4. Item Identity

**Apple Documentation** (from `NSOutlineView | Documentation.pdf`):
> "Each item in the outline view must be unique. In order for the collapsed state to remain consistent between reloads the item's pointer must remain the same and the item must maintain `isEqual:` sameness."

**Current Implementation**: Uses `SidebarItem` wrapper class - this is GOOD but could have issues if wrappers are recreated on reload.

### 5. Drop Indicator Visual Feedback

**Apple's System** (from docs):
- `NSOutlineViewDropOnItemIndex` (-1) = Blue highlight (drop ON item)
- `index >= 0` = Line indicator (drop BETWEEN children)

The system provides this automatically. You don't need to call `setDropRow_dropOperation_` to control the visual style - just return the right `NSDragOperation`.

---

## Proposed Refactoring

### Phase 1: Extract Utility Functions (Low Risk)

Create clean helper functions outside the ObjC method context:

```python
# In NSOutlineViewSidebar class (outer class)

def _can_accept_internal_drop(self, target_data: dict, dragged_id: str) -> bool:
    """
    Check if target can accept an internal drag.

    Returns False if:
    - Target explicitly rejects drops (_can_accept_drops=False, not a section header)
    - Target is descendant of dragged item (circular reference)
    """
    if not target_data:
        return True  # Root level accepts drops

    # Check explicit rejection (Inbox)
    if not target_data.get('_can_accept_drops', True):
        if not target_data.get('_is_section_header'):
            return False

    # Check circular reference
    return not self._is_descendant_of(target_data, dragged_id)

def _get_drop_operation(self, target_data: dict, index: int, is_internal: bool) -> int:
    """
    Determine appropriate NSDragOperation for a drop.

    Returns:
        16 (Move) for internal drags
        1 (Copy) for external file drags
        0 (None) if drop not allowed
    """
    # Section headers: only accept drops INTO (index >= 0), not ONTO (index == -1)
    if target_data and target_data.get('_is_section_header'):
        if index == -1:
            return 0  # Reject drop ONTO header

    return 16 if is_internal else 1
```

### Phase 2: Simplify validateDrop (Medium Risk)

Refactor to follow Apple's early-exit pattern:

```python
@objc_method
def outlineView_validateDrop_proposedItem_proposedChildIndex_(
    self, outline_view, drag_info, item, index: int
) -> int:
    """Validate drop following Apple's pattern."""
    try:
        # Get parent data
        parent_data = item._python_data if item and hasattr(item, '_python_data') else None

        # Get pasteboard info
        pasteboard = drag_info.draggingPasteboard
        types = pasteboard.types

        is_internal = any(str(t) == "com.fichero.collection.id" for t in types)
        is_file = any(str(t) == "public.file-url" for t in types)

        if not is_internal and not is_file:
            return 0  # Unknown drag type

        if is_internal:
            # EARLY EXIT: Section header + drop ONTO = reject
            if parent_data and parent_data.get('_is_section_header') and index == -1:
                return 0

            # Get dragged item ID
            dragged_id = pasteboard.stringForType("com.fichero.collection.id")

            # Check if drop is allowed (delegates to helper on interface)
            if not self.interface._can_accept_internal_drop(parent_data, dragged_id):
                return 0

            return 16  # NSDragOperationMove

        elif is_file:
            return 1  # NSDragOperationCopy

        return 0

    except Exception as e:
        logger.error(f"Error in validateDrop: {e}", exc_info=True)
        return 0
```

### Phase 3: Remove Unnecessary setDropRow Calls (Low Risk)

The current code calls `setDropRow_dropOperation_` to try to control visual feedback. This is unnecessary - NSOutlineView handles this automatically based on the proposed index.

**Remove these patterns:**
```python
# REMOVE - Visual feedback is automatic
outline_view.setDropRow_dropOperation_(NS_OUTLINE_VIEW_DROP_ON_ITEM_INDEX, NS_TABLE_VIEW_DROP_ABOVE)

# REMOVE - System handles blue highlight automatically
outline_view.setDropRow_dropOperation_(container_row, NS_TABLE_VIEW_DROP_ON)
```

**Keep only for explicit retargeting** (if needed):
```python
# KEEP - Only if we need to REDIRECT a drop to a different location
# Example: Redirect to parent container instead of leaf node
outline_view.setDropItem_dropChildIndex_(parent_item, 0)
```

### Phase 4: Implement Proper Item Identity (Low Risk)

Ensure `SidebarItem` wrappers are reused across reloads:

```python
def attach_source(self, source):
    """Attach data with stable item identity."""
    # Build item cache keyed by unique ID
    if not hasattr(self, '_item_cache'):
        self._item_cache = {}

    new_cache = {}
    self._wrapped_items = []

    for data_item in self._data:
        item_id = self._get_item_id(data_item)

        # Reuse existing wrapper if available (stable pointer)
        if item_id in self._item_cache:
            wrapper = self._item_cache[item_id]
            wrapper._python_data = data_item  # Update data
        else:
            wrapper = self.SidebarItem.alloc().init()
            wrapper._python_data = data_item

        new_cache[item_id] = wrapper
        self._wrapped_items.append(wrapper)

    self._item_cache = new_cache
```

---

## Implementation Order

| Phase | Risk | Effort | Description |
|-------|------|--------|-------------|
| 1 | Low | 30 min | Extract `_can_accept_internal_drop()` helper |
| 2 | Medium | 1 hour | Simplify `validateDrop` with early-exit pattern |
| 3 | Low | 20 min | Remove unnecessary `setDropRow` calls |
| 4 | Low | 30 min | Add item identity cache |

**Total Estimated Time**: ~2-2.5 hours

---

## Testing Plan

### After Each Phase:

1. **Basic Drag**: Drag collection between siblings → Line indicator appears
2. **Drop ON folder**: Drag onto folder → Blue highlight appears
3. **Drop ON section header**: Drag onto "Library" header → Rejected
4. **Drop INTO section**: Drag between items under "Library" → Line indicator
5. **Drop onto Inbox**: Any drag onto Inbox → Rejected
6. **Circular reference**: Drag parent onto child → Rejected
7. **External file drop**: Drag from Finder → Copy indicator

### Visual Verification:

- Line indicators appear correctly positioned
- Blue highlights appear on valid drop targets
- No "ghost" highlights after drop completes
- No horizontal scrolling artifacts

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking existing functionality | Test each phase independently before proceeding |
| Rubicon-ObjC quirks | Keep existing error handling, add more specific logging |
| Performance regression | Cache item lookups, avoid redundant tree traversals |

---

## Files to Modify

1. **macos_sidebar.py** - Main implementation
   - Lines 1002-1161: `outlineView_validateDrop_proposedItem_proposedChildIndex_`
   - Lines 2114-2186: Helper methods `_find_item_by_id`, `_is_descendant_of`
   - Lines 1999+: `attach_source` for item caching

---

## Summary

The current implementation works but doesn't follow Apple's recommended patterns. The main issues are:

1. **Convoluted validation logic** - Should use early-exit pattern
2. **Misuse of setDropItem** - Using it for visual feedback instead of retargeting
3. **Inline circular check** - Should be factored into utility function
4. **No item identity caching** - May cause expand/collapse state issues

Following Apple's patterns from the sample code will make the drag-and-drop more robust and maintainable.

---

**Ready for approval to proceed with implementation.**
