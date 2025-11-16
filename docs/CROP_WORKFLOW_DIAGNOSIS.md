# Crop Workflow Integration - Root Cause Analysis

**Date**: 2025-11-15
**Status**: Diagnosis Complete - Ready for Fix

## Problem Summary

When clicking a crop step in the StepBrowser sidebar, the OutputPane doesn't display the cropped image. The logs show:

```
StepBrowser: No selected_data in callback (probably deselection)
```

## Root Cause

The issue is in `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/preview/step_browser.py` at line 171-188.

### Current Code Flow

```python
def _on_step_selected(self, widget_or_data, **kwargs):
    # Try to get selected_data from first arg or kwargs
    selected_data = widget_or_data if isinstance(widget_or_data, dict) else kwargs.get('selected_data')

    if not selected_data:
        # Try to extract from widget.selection
        if hasattr(widget_or_data, 'selection'):
            selection = widget_or_data.selection
            if hasattr(selection, '_collection_data'):
                selected_data = selection._collection_data
            elif isinstance(selection, dict):
                selected_data = selection

    if not selected_data:
        logger.debug("StepBrowser: No selected_data in callback (probably deselection)")
        return
```

### The Problem

**ListWidget's callback signature doesn't match StepBrowser's expectations.**

From `list_widget/base.py` line 439:

```python
def _handle_select(self, widget_or_item) -> None:
    # ...
    if self._on_select_callback:
        self._on_select_callback(selection)  # Passes the Row/Node object directly!
```

So `widget_or_data` in StepBrowser is actually the **Row object** itself, not a widget with a `.selection` attribute!

### What's Actually Happening

1. **ListWidget** calls `_on_step_selected(row_object)` where `row_object` is the Toga Row
2. **StepBrowser** checks `isinstance(row_object, dict)` → **False** (it's a Row, not dict)
3. **StepBrowser** checks `hasattr(row_object, 'selection')` → **False** (Row doesn't have `.selection`)
4. **Result**: `selected_data` stays `None` and the callback returns early

### Why Row._collection_data Isn't Accessible

The Row object **does** have `_collection_data` as an accessor attribute, but the current code never checks the **first argument directly** for `_collection_data`. It only checks if the first arg has a `.selection` attribute.

## The Fix

Update `StepBrowser._on_step_selected()` to handle the Row object correctly:

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
            selected_data = widget_or_data._collection_data
            logger.debug(f"Extracted _collection_data from Row: {selected_data}")

        # Case 3: First arg is Row/Node with _item_id (fallback)
        elif hasattr(widget_or_data, '_item_id'):
            # Create minimal dict with just the item_id
            selected_data = {'_item_id': widget_or_data._item_id}
            logger.debug(f"Extracted _item_id from Row: {widget_or_data._item_id}")

        # Case 4: Legacy - widget with .selection attribute (shouldn't happen)
        elif hasattr(widget_or_data, 'selection'):
            selection = widget_or_data.selection
            if hasattr(selection, '_collection_data'):
                selected_data = selection._collection_data
            elif isinstance(selection, dict):
                selected_data = selection

        # No data found - probably deselection
        if not selected_data:
            logger.debug("StepBrowser: No selected_data in callback (probably deselection)")
            return

        # Get the index from _item_id
        index = selected_data.get('_item_id')
        if index is None:
            logger.warning("StepBrowser: No _item_id in selected_data")
            return

        logger.info(f"StepBrowser: Step selected at index {index}")
        self.current_index = index

        # Notify callback
        if self.on_step_selected:
            self.on_step_selected(index)

    except Exception as e:
        logger.error(f"Error handling step selection: {e}")
        import traceback
        logger.error(traceback.format_exc())
```

## Verification Plan

After applying the fix:

1. **Test in GUI**:
   ```bash
   briefcase dev
   ```
   - Navigate to a collection with processed items
   - Click on an item in the collection view
   - Click on the "crop" step in the step browser
   - **Expected**: OutputPane displays the cropped image, not the original

2. **Check Logs**:
   - Should see: `"Extracted _collection_data from Row: {...}"`
   - Should see: `"StepBrowser: Step selected at index X"`
   - Should NOT see: `"No selected_data in callback"`

3. **Test Other Steps**:
   - Click "transcribe" step → should show transcribed text
   - Click "enhance" step → should show enhanced image
   - Click back to "Original" → should show original image

## Related Components

This fix resolves the data extraction issue in StepBrowser. However, there may be additional issues downstream:

1. **OutputPane** (`output_pane.py`) - Verify it receives the correct step_index
2. **CropRenderer** (`library/renderers/crop.py`) - Verify it renders crop outputs correctly
3. **Library Backend** - Verify crop metadata is stored correctly

These will be verified during integration testing.

## Impact Assessment

**Files Modified**: 1
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/preview/step_browser.py`

**Risk**: Low
- The fix makes the selection handling more robust
- Adds explicit Row object handling
- Maintains backward compatibility with dict-based selection

**Dependencies**: None
- No changes to ListWidget or other components needed
- Pure fix to StepBrowser's selection parsing logic
