# Crop Workflow Fix - Summary

**Date**: 2025-11-15
**Status**: ✅ Fix Applied - Ready for Testing

## What Was Fixed

Fixed the crop workflow integration issue where clicking on crop steps in the StepBrowser sidebar failed to display cropped images.

## Root Cause

The `StepBrowser._on_step_selected()` callback was not correctly handling the Row object passed by ListWidget. It was looking for `widget.selection._collection_data` but should have been looking directly at `row._collection_data`.

## The Fix

Updated `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/preview/step_browser.py`:

```python
# BEFORE: Failed to extract data from Row object
def _on_step_selected(self, widget_or_data, **kwargs):
    selected_data = widget_or_data if isinstance(widget_or_data, dict) else kwargs.get('selected_data')
    if not selected_data:
        if hasattr(widget_or_data, 'selection'):  # Row doesn't have .selection!
            selection = widget_or_data.selection
            # ... never reached

# AFTER: Correctly handles Row object
def _on_step_selected(self, widget_or_data, **kwargs):
    selected_data = None

    if isinstance(widget_or_data, dict):
        selected_data = widget_or_data
    elif hasattr(widget_or_data, '_collection_data'):  # ← KEY FIX
        selected_data = widget_or_data._collection_data  # Extract directly from Row
    elif hasattr(widget_or_data, '_item_id'):
        selected_data = {'_item_id': widget_or_data._item_id}
    # ... rest of logic
```

## How to Test

### Quick Test

```bash
# 1. Launch the app
briefcase dev

# 2. Navigate to a collection with processed items
# 3. Click on an item
# 4. In the StepBrowser sidebar, click on the "crop" step
# 5. Expected: OutputPane displays the cropped image
```

### Expected Behavior

**Before Fix**:
- Click "crop" step → Nothing happens
- Log: `"StepBrowser: No selected_data in callback"`

**After Fix**:
- Click "crop" step → Cropped image appears in OutputPane
- Log: `"Extracted _collection_data from Row: {...}"`
- Log: `"StepBrowser: Step selected at index 1"`

### Verification Logs

Look for these log messages (in order):

```
Extracted _collection_data from Row: {<data>}
StepBrowser: Step selected at index 1
OutputPane.set_step called: item_id=xxx, step_index=1
Rendering step: crop from /path/to/cropped.jpg
```

Should NOT see:
```
StepBrowser: No selected_data in callback (probably deselection)
```

## Files Changed

1. `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/preview/step_browser.py`
   - Updated `_on_step_selected()` method to handle Row objects correctly
   - Added detailed logging for debugging

## Documentation Created

1. `/Users/dtubb/code/fichero_main/fichero/docs/CROP_WORKFLOW_DIAGNOSIS.md`
   - Root cause analysis
   - Technical details of the bug

2. `/Users/dtubb/code/fichero_main/fichero/docs/CROP_WORKFLOW_FIX_REPORT.md`
   - Implementation details
   - Before/after behavior
   - Complete testing instructions
   - Test result template

3. `/Users/dtubb/code/fichero_main/fichero/docs/CROP_WORKFLOW_INTEGRATION_GUIDE.md`
   - Complete architecture overview
   - Data flow diagrams
   - Troubleshooting guide
   - Future enhancements

## Testing Checklist

Use this checklist when testing the fix:

- [ ] Launch app with `briefcase dev`
- [ ] Navigate to a collection with crop outputs
- [ ] Click on an item
- [ ] Click "crop" in StepBrowser → cropped image appears
- [ ] Click "Original" in StepBrowser → original image appears
- [ ] Click other steps → correct outputs appear
- [ ] Check logs for "Extracted _collection_data from Row"
- [ ] No "No selected_data" errors in logs

## If Issues Occur

If the fix doesn't work:

1. **Check logs** for the exact error message
2. **Verify crop outputs exist**: `ls -la /path/to/collection/output/crop/`
3. **Check manifest**: `cat /path/to/collection/output/crop/manifest.jsonl`
4. **Test CLI**: `briefcase dev -- library metadata-show <item_id> --step crop`
5. **Report issue** with logs and steps to reproduce

## Next Steps

After verifying the fix works:

1. Test with different collection types
2. Test with multiple processing steps
3. Test interactive crop editing (if implemented)
4. Consider implementing additional crop features (see Integration Guide)

## Rollback

If needed, revert the change:

```bash
git checkout HEAD -- src/fichero/windows/main/views/preview/step_browser.py
```

---

## Questions?

Refer to:
- `CROP_WORKFLOW_FIX_REPORT.md` - Detailed testing instructions
- `CROP_WORKFLOW_INTEGRATION_GUIDE.md` - Architecture and troubleshooting
- `CROP_WORKFLOW_DIAGNOSIS.md` - Technical root cause analysis
