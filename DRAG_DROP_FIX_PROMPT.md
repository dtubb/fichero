# NSOutlineView Drag & Drop Visual Feedback Fix

## Problem Statement

The drag and drop system in our macOS sidebar (NSOutlineView) is working functionally but has **no visual feedback**:

1. ❌ **No insertion line indicators** showing where items will drop
2. ❌ **Blue selection artifacts** appearing on multiple items during drag (screenshot evidence)
3. ✅ Data structure updates work correctly after drop
4. ✅ validateDrop is being called correctly (confirmed by logging)
5. ✅ setDropRow_dropOperation_ is being called with correct parameters

## Current Behavior (from logging)

```
DEBUG: ✅ Sibling reordering - line at index 0
DEBUG: outline_view.setDropRow_dropOperation_(0, 1)  # Being called!
```

**But visually**: Nothing appears. No lines, just ghost blue highlights.

## Technical Context

**File**: `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py` (~2500 lines)

**Architecture**:
- NSOutlineView-based sidebar using Rubicon-ObjC
- Hierarchical tree structure (3+ levels)
- Drag and drop for reordering collections/folders
- Line ~1500: NSOutlineView setup
- Lines ~1000-1100: validateDrop delegate method
- Lines ~1300-1350: drag cleanup methods

**Key Delegate Methods**:
1. `outlineView_pasteboardWriterForItem_` - Creates drag data ✅ Working
2. `outlineView_validateDrop_proposedItem_proposedChildIndex_` - Validates and sets drop indicators ⚠️ Partially working
3. `outlineView_acceptDrop_item_childIndex_` - Handles the drop ✅ Working
4. `outlineView_draggingSessionEndedAtPoint_operation_` - Cleanup ⚠️ Maybe overcleaning

## What We've Tried (and failed)

1. ✅ Set `draggingDestinationFeedbackStyle = 2` (SourceList)
   - Result: No change

2. ✅ Set `draggingDestinationFeedbackStyle = 1` (Regular)
   - Result: No change

3. ❌ Added `deselectAll_()` everywhere
   - Result: Broke the indicators that were working

4. ❌ Added `verticalMotionCanBeginDrag = False`
   - Result: Might have blocked drop feedback

5. ✅ Call `setDropRow_dropOperation_(index, 1)` in validateDrop
   - Result: Code executes, no visual

## User Requirements

1. **Insertion lines**: Like Finder or DEVONthink - horizontal line with small bars showing where item will insert
2. **Clean visual state**: No multiple blue selections during drag
3. **Clear on exit**: Drop indicators clear when drag exits or ends
4. **No artifacts**: After drag ends, all indicators gone

## Tasks for You

### 1. **Review & Analyze** (30 min)

Read the file and understand:
- How NSOutlineView drop indicators actually work in native macOS
- What the correct NSTableViewDropOperation values mean (0 vs 1)
- Why setDropRow_dropOperation_ isn't showing visual feedback
- Whether we're fighting NSOutlineView's native behavior

### 2. **Create Plan** (15 min)

Answer these questions:
- Is `draggingDestinationFeedbackStyle` the right approach?
- Should we use NSTableViewDropOn (0) or NSTableViewDropAbove (1)?
- Do we need custom drawing for drop indicators?
- Is there a simpler native macOS way?

### 3. **Research Best Practices** (15 min)

Check:
- Apple's NSOutlineView documentation for drop indicators
- Whether setDropRow_dropOperation_ requires additional setup
- If we need to implement `draggingUpdated_` delegate
- Whether line indicators require table view column configuration

### 4. **Implement Fix** (45 min)

Fix the visual feedback while ensuring:
- ✅ Insertion lines appear between items during drag
- ✅ No blue selection artifacts
- ✅ Lines clear when drag exits/ends
- ✅ Data structure updates still work

### 5. **Test & Verify** (15 min)

Test scenarios:
- Drag between siblings - see insertion line
- Drag onto folder - see appropriate indicator
- Drag over invalid target (section) - no indicator
- Drag ends - all indicators clear
- Check console for errors

## Key Code Sections

### validateDrop (lines ~1000-1100)
```python
if index >= 0:
    # Reordering siblings
    outline_view.setDropRow_dropOperation_(index, 1)  # NSTableViewDropAbove
    return 16  # NSDragOperationMove
```

**Question**: Why doesn't this show a line?

### NSOutlineView Setup (lines ~1500-1550)
```python
self._toga_sidebar.draggingDestinationFeedbackStyle = 1
```

**Question**: Is this the right constant? Does it need additional setup?

## Success Criteria

✅ User drags item and sees **horizontal line with bars** at drop location
✅ NO blue highlight artifacts during drag
✅ Indicators **clear immediately** when drag exits/ends
✅ Data persistence still works (already working)
✅ Logging shows setDropRow_dropOperation called AND visual appears

## Additional Notes

- Previous developer tried many approaches - they're all in the code
- Some code comments say "this fixes X" but it doesn't actually work
- The user saw it working before, so we broke something
- Focus on SIMPLE native macOS approach first

## Questions to Answer in Your Plan

1. What does `setDropRow_dropOperation_` actually do visually?
2. Is there a required setup step we're missing?
3. Should we be using row-based or view-based NSOutlineView?
4. Do we need to override additional delegate methods?
5. Is the column configuration affecting drop indicators?

## Output Required

1. **Diagnosis**: Why isn't setDropRow_dropOperation_ showing visuals?
2. **Plan**: Step-by-step approach to fix (with alternatives)
3. **Code Review**: Issues found in current implementation
4. **Implementation**: Working fix with clear insertion lines
5. **Testing**: Verification that all scenarios work

Good luck! Focus on understanding WHY the native API isn't working before trying custom solutions.
