# Drag-Drop Improvement Plan for NSOutlineView Sidebar

## Current State Analysis

### What's Working
1. ✅ Drag starts successfully (no segfault after fix)
2. ✅ Collection ID written to pasteboard via `pasteboardWriterForItem`
3. ✅ Full drop validation in `validateDrop` with proper retargeting
4. ✅ Drop acceptance in `acceptDrop` with proper parent detection
5. ✅ Cleanup in `draggingSession:endedAtPoint:operation:`
6. ✅ Visual feedback: Insertion lines (between items) and blue highlights (on containers)
7. ✅ Self-drop prevention (cannot drop item onto itself)
8. ✅ Circular reference detection (cannot drop parent into descendant)
9. ✅ Folder drop support via `_can_accept_drops` flag

### Apple's NSOutlineView Pattern vs Our Implementation

| Method | Apple Pattern | Our Status | Notes |
|--------|--------------|------------|-------|
| `pasteboardWriterForItem:` | Required for drag source | ✅ Implemented | Writes collection ID to pasteboard |
| `draggingSession:willBeginAtPoint:forItems:` | Customize drag start | ❌ Causes segfault | Rubicon can't iterate ObjC NSArray |
| `validateDrop:proposedItem:proposedChildIndex:` | Validate/retarget drops | ✅ Full | Uses `setDropItem:dropChildIndex:` for retargeting |
| `acceptDrop:item:childIndex:` | Handle the drop | ✅ Implemented | Handles both ON and BETWEEN drops |
| `draggingSession:endedAtPoint:operation:` | Cleanup | ✅ Implemented | |
| `updateDraggingItemsForDrag:` | Visual feedback | ⚠️ Empty | Only logs |
| `draggingEntered:` | Track entry | ✅ Implemented | |
| `draggingExited:` | Track exit | ✅ Implemented | |

### Known Issues (Resolved)

1. ~~**No Drop Retargeting**~~: ✅ FIXED - Now uses `setDropItem:dropChildIndex:` to control visual feedback
2. ~~**Full Tree Rebuild on Move**~~: ✅ FIXED - Uses stable wrapper caching
3. **No Spring-Loading**: Folders don't auto-expand on hover during drag (Future enhancement)
4. **Missing Visual Feedback**: No custom drag image or count indicator (Future enhancement)
5. ~~**Item Cache Not Updated**~~: ✅ FIXED - Cache is properly maintained

---

## Improvement Plan

### Phase 1: Fix Core Move Operation (Priority: High)
**Goal**: Make the actual move operation reliable

#### 1.1 Improve `move_item_in_tree()`
- Don't rebuild entire `_wrapped_items` list
- Update only the moved item's wrapper
- Keep stable item identity through the move

#### 1.2 Ensure Item Cache Consistency
- After move, update `_item_cache` with new item positions
- Clear stale entries for removed items

#### 1.3 Use Incremental NSOutlineView Updates
Instead of `reloadData()`, use:
```python
# Remove item
outline_view.removeItemsAtIndexes_inParent_withAnimation_(
    index_set, parent_item, NSTableViewAnimationEffectFade
)

# Insert item
outline_view.insertItemsAtIndexes_inParent_withAnimation_(
    index_set, parent_item, NSTableViewAnimationEffectFade
)

# Or move item
outline_view.moveItemAtIndex_inParent_toIndex_inParent_(
    old_index, old_parent, new_index, new_parent
)
```

### Phase 2: Add Drop Retargeting (Priority: High)
**Goal**: Proper drop target behavior following Apple's pattern

#### 2.1 Implement Drop Retargeting in `validateDrop`
```python
@objc_method
def outlineView_validateDrop_proposedItem_proposedChildIndex_(
    self, outline_view, drag_info, item, index: int
) -> int:
    # Get target info
    target_data = item._python_data if item else None

    # Retarget: dropping ON section header → drop INTO section at end
    if target_data and target_data.get('_is_section_header') and index == -1:
        children = target_data.get('_children', [])
        outline_view.setDropItem_dropChildIndex_(item, len(children))
        return NS_DRAG_OPERATION_MOVE

    # Retarget: dropping BETWEEN root items → reject (must be in section)
    if item is None:
        # Find first valid section and redirect there
        # ...
```

#### 2.2 Handle All Drop Scenarios
| Scenario | Proposed | Retarget To | Result |
|----------|----------|-------------|--------|
| ON section header | item=section, index=-1 | item=section, index=child_count | Move into section at end |
| ON collection | item=collection, index=-1 | Keep or reject based on nesting | May nest or reject |
| BETWEEN collections | item=parent, index=N | Keep | Insert at position N |
| AT root level | item=None, index=N | Reject or find section | Reject (must be in section) |

### Phase 3: Visual Feedback (Priority: Medium)
**Goal**: Better user feedback during drag

#### 3.1 Implement `updateDraggingItemsForDrag:`
```python
@objc_method
def outlineView_updateDraggingItemsForDrag_(self, outline_view, drag_info):
    # Update drag image count if multiple items
    # Customize appearance during drag
    try:
        count = drag_info.numberOfValidItemsForDrop
        if count > 1:
            drag_info.draggingFormation = NSDraggingFormationStack
    except Exception:
        pass
```

#### 3.2 Add Drag Image (Workaround for willBeginAtPoint)
Since we can't use `willBeginAtPoint:forItems:`, set a custom drag image during `pasteboardWriterForItem`:
```python
# Create drag image in pasteboardWriterForItem
# Store it and apply in first validateDrop call
```

### Phase 4: Spring-Loading (Priority: Medium)
**Goal**: Auto-expand folders when hovering during drag

#### 4.1 Enable Spring-Loading
```python
# In create_widget()
self._toga_sidebar.springLoadingEnabled = True
self._toga_sidebar.springLoadingAllowsExpansion = True
```

#### 4.2 Implement `outlineView:shouldExpandItem:` delegate
```python
@objc_method
def outlineView_shouldExpandItem_(self, outline_view, item) -> bool:
    # Allow expansion during drag for spring-loading
    return True
```

### Phase 5: Animation and Polish (Priority: Low)
**Goal**: Smooth, native-feeling animations

#### 5.1 Use Animated Insert/Remove
```python
# Replace reloadData() calls with animated equivalents
self._toga_sidebar.beginUpdates()
# ... insert/remove operations ...
self._toga_sidebar.endUpdates()
```

#### 5.2 Add Drop Insertion Line Feedback
The `draggingDestinationFeedbackStyle = 2` (sourceList style) should show this, but verify it's working.

---

## Implementation Order

1. ✅ **Phase 1.1-1.3**: Fix core move operation (most important for reliability) - COMPLETE
2. ✅ **Phase 2.1-2.2**: Add drop retargeting (proper drop behavior) - COMPLETE
3. ⏳ **Phase 4.1-4.2**: Spring-loading (quick win, nice UX) - Future
4. ⏳ **Phase 3.1-3.2**: Visual feedback (polish) - Future
5. ⏳ **Phase 5.1-5.2**: Animation (final polish) - Future

## Testing Plan

### Unit Tests ✅ COMPLETE (65 tests)
- ✅ Test `move_item_in_tree()` with various scenarios
- ✅ Test drop retargeting logic
- ✅ Test item cache consistency after moves
- ✅ Test visual feedback (insertion lines vs highlights)
- ✅ Test container types (section headers, folders)
- ✅ Test validation rules (self-drop, circular reference)
- ✅ Test complete move operations

### Integration Tests
- ✅ Drag collection within same section (reorder)
- ✅ Drag collection to different section
- ✅ Drag to create nested hierarchy (via `_can_accept_drops`)
- ✅ Drop on section header
- ✅ Drop between collections
- ⏳ Verify animations play correctly (Future)

### Manual Tests ✅
- ✅ Visual inspection of drop indicators (lines + highlights)
- ⏳ Spring-loading behavior (Future)
- ⏳ Drag image appearance (Future)
- ⏳ Multi-item drag (if supported) (Future)

---

## Files Modified

1. `renderers/macos_sidebar/objc_classes.py`
   - ✅ `validateDrop` - Full drop retargeting with `setDropItem:dropChildIndex:`
   - ✅ Self-drop detection and rejection
   - ✅ `_can_accept_drops` flag support for folder drops
   - ⏳ `updateDraggingItemsForDrag` - add visual feedback (Future)
   - ⏳ Add spring-loading support (Future)

2. `renderers/macos_sidebar/renderer.py`
   - ✅ `move_item_in_tree()` - with safety checks
   - ✅ `is_descendant_of` import for circular reference detection
   - ✅ Stable wrapper caching with `_get_or_create_wrapper`
   - ⏳ `create_widget()` - enable spring-loading (Future)

3. `renderers/macos_sidebar/tree_operations.py`
   - ✅ `get_item_id()` - extract unique identifier
   - ✅ `is_descendant_of()` - circular reference detection
   - ✅ `find_item_in_tree()` - locate items with parent info
   - ✅ `remove_item_from_parent()` - remove from tree
   - ✅ `insert_item_into_parent()` - insert into tree

4. `tests/unit/test_macos_sidebar_tree_operations.py`
   - ✅ 65 comprehensive tests covering all drag-drop scenarios
   - ✅ `TestDragDropValidation` - validation and detection
   - ✅ `TestDropVisualFeedback` - insertion lines vs highlights
   - ✅ `TestDropContainerTypes` - section headers, folders
   - ✅ `TestDropValidationRules` - acceptance/rejection rules
   - ✅ `TestMoveOperations` - complete move scenarios

## Drop Behavior Summary

### Visual Feedback
| Scenario | Index | Feedback | Result |
|----------|-------|----------|--------|
| Drag over gap between items | `index >= 0` | Insertion line | Reorder |
| Drag over section header | `index = -1` | Blue highlight | Add to section |
| Drag over folder (`_can_accept_drops: True`) | `index = -1` | Blue highlight | Add as child |
| Drag over regular item | `index = -1` | Rejected | No drop allowed |

### Flags
- `_is_section_header: True` - Item is a collapsible section
- `_can_accept_drops: True` - Item can receive children (like a folder)
- `_has_children: True` - Item has child items
- `_children: []` - List of child items
