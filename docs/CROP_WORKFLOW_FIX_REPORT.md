# Crop Workflow Fix - Implementation Report

**Date**: 2025-11-15
**Status**: Fix Applied - Ready for Testing

## Summary

Fixed the crop workflow integration issue where clicking on crop steps in the StepBrowser sidebar failed to display cropped images. The root cause was incorrect selection data extraction from ListWidget Row objects.

## Root Cause

The `StepBrowser._on_step_selected()` callback was not correctly handling the Row object passed by ListWidget's `on_select` callback. It was expecting either:
1. A dict directly, or
2. A widget with a `.selection` attribute

But ListWidget actually passes the **Row object directly**, which has `_collection_data` as an accessor attribute (not as a nested `.selection._ collection_data`).

## Changes Made

### File Modified

**`/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/preview/step_browser.py`**

Updated `_on_step_selected()` method to handle Row objects correctly:

```python
def _on_step_selected(self, widget_or_data, **kwargs):
    """Handle step selection"""
    try:
        # ListWidget passes the Row/Node object directly as first arg
        selected_data = None

        # Case 1: First arg is already a dict (custom renderers)
        if isinstance(widget_or_data, dict):
            selected_data = widget_or_data

        # Case 2: First arg is Row/Node object with _collection_data accessor
        elif hasattr(widget_or_data, '_collection_data'):
            selected_data = widget_or_data._collection_data  # ← KEY FIX
            logger.debug(f"Extracted _collection_data from Row: {selected_data}")

        # Case 3: First arg is Row/Node with _item_id (fallback)
        elif hasattr(widget_or_data, '_item_id'):
            selected_data = {'_item_id': widget_or_data._item_id}

        # Case 4: Legacy - widget with .selection attribute
        elif hasattr(widget_or_data, 'selection'):
            # ... (kept for backward compatibility)

        # ... rest of method unchanged
```

**Key Change**: Added direct check for `_collection_data` attribute on the Row object itself (Case 2).

## Before vs After Behavior

### Before Fix

1. User clicks "crop" step in StepBrowser
2. ListWidget calls `_on_step_selected(row_object)`
3. StepBrowser checks `isinstance(row_object, dict)` → False
4. StepBrowser checks `hasattr(row_object, 'selection')` → False
5. **Result**: `selected_data = None` → callback returns early
6. **Log**: `"StepBrowser: No selected_data in callback (probably deselection)"`
7. **UI**: Nothing happens, OutputPane shows same file

### After Fix

1. User clicks "crop" step in StepBrowser
2. ListWidget calls `_on_step_selected(row_object)`
3. StepBrowser checks `isinstance(row_object, dict)` → False
4. StepBrowser checks `hasattr(row_object, '_collection_data')` → **True** ✅
5. **Result**: `selected_data = row_object._collection_data` → contains step info
6. **Log**: `"Extracted _collection_data from Row: {...}"`
7. **Log**: `"StepBrowser: Step selected at index X"`
8. **UI**: OutputPane displays cropped image ✅

## Testing Instructions

### Prerequisites

1. Ensure you have a collection with processed items including crop steps
2. If not, create one:

```bash
# Create test collection
briefcase dev -- library add "Crop Test" --type external --source ~/Desktop/test_images

# Process with crop workflow
briefcase dev -- library process <collection_id> --plan "Crop Only" --workflow "crop"
```

### Manual GUI Testing

1. **Launch the app**:
   ```bash
   briefcase dev
   ```

2. **Navigate to collection**:
   - Open the collection in the Library view
   - Click on an item that has been processed with crop

3. **Test step selection**:
   - Look at the StepBrowser (sidebar showing processing steps)
   - You should see:
     - "Original" (step 0)
     - "crop" (step 1)
     - Any other processing steps

4. **Click on "crop" step**:
   - **Expected**: OutputPane displays the cropped image
   - **Expected**: Crop metadata is visible (crop coordinates, method, etc.)
   - **Not Expected**: Seeing the same original image

5. **Click on "Original"**:
   - **Expected**: OutputPane displays the original (uncropped) image

6. **Click on other steps** (if present):
   - **Expected**: Each step displays its corresponding output

### Log Verification

While testing, check the console logs:

**Expected Logs (Success)**:
```
Extracted _collection_data from Row: {...}
StepBrowser: Step selected at index 1
OutputPane.set_step called: item_id=xxx, step_index=1
```

**Not Expected (Failure)**:
```
StepBrowser: No selected_data in callback (probably deselection)
```

### Test Matrix

| Test Case | Action | Expected Result | Status |
|-----------|--------|-----------------|--------|
| Select crop step | Click "crop" in StepBrowser | Cropped image displayed | ⏳ |
| Select original | Click "Original" in StepBrowser | Original image displayed | ⏳ |
| Select transcribe | Click "transcribe" in StepBrowser | Transcribed text displayed | ⏳ |
| Step metadata | View any step | Metadata visible in OutputPane | ⏳ |
| Multiple items | Switch between items | Steps update correctly | ⏳ |

### CLI Testing (Optional)

Verify crop outputs exist in the library:

```bash
# List items in collection
briefcase dev -- library items <collection_id>

# Show crop metadata for specific item
briefcase dev -- library metadata-show <item_id> --step crop

# Verify crop output files exist
ls -la /path/to/collection/output/crop/
```

## Known Limitations

This fix resolves the **data extraction** issue in StepBrowser. However, there may be additional issues in the crop workflow:

1. **Crop Renderer**: Verify it correctly loads and displays crop outputs
2. **Crop Metadata**: Verify crop coordinates are stored and displayed correctly
3. **Interactive Editing**: If crop editing is implemented, verify it works
4. **Library Backend**: Verify crop outputs are saved to the correct locations

These will be verified during integration testing.

## Rollback Plan

If issues arise, revert the change:

```bash
git checkout HEAD -- src/fichero/windows/main/views/preview/step_browser.py
```

## Next Steps

1. **Test in GUI** (see testing instructions above)
2. **Verify logs** show correct data extraction
3. **Test all processing steps**, not just crop
4. **If issues found**: Check OutputPane, CropRenderer, and Library backend
5. **Document results** in this file

## Impact Assessment

**Risk**: Low
- Single-method change in StepBrowser
- Maintains backward compatibility with all selection formats
- No changes to data structures or APIs

**Benefits**:
- Fixes crop step display issue
- Makes selection handling more robust
- Adds better logging for debugging

**Dependencies**: None
- No changes to ListWidget needed
- No changes to other components needed
- Pure fix to selection parsing logic

---

## Test Results

*(Fill in after testing)*

### GUI Test Results

**Date**: ___________
**Tester**: ___________

- [ ] Crop step displays cropped image
- [ ] Original step displays original image
- [ ] Other steps display correctly
- [ ] Metadata is visible
- [ ] Logs show correct data extraction
- [ ] No "No selected_data" errors

**Notes**:


### Issues Found

*(List any issues discovered during testing)*


### Follow-up Actions

*(List any additional fixes or improvements needed)*
