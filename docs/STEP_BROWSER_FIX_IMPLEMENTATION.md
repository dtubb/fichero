# StepBrowser Fix Implementation

**Date:** 2025-11-15
**Status:** Implemented and ready for testing
**Files Modified:** 2

## Summary

Fixed the StepBrowser data flow issue where Row objects had `_collection_data = None`, preventing step selection from working correctly. Also added comprehensive debugging information to help diagnose rendering issues.

## Changes Made

### 1. Fix StepBrowser Row Data Population

**File:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/preview/step_browser.py`

**Location:** Lines 119-139

**Before:**
```python
list_data.append({
    'text': title,
    'subtitle': subtitle,
    'icon': toga.Icon(icon_name) if icon_name else None,
    '_item_id': i  # Store index for callback
})
```

**After:**
```python
# Populate _collection_data with full step information
# This is what gets extracted when a row is selected
collection_data = {
    '_item_id': i,  # Index for callback
    'step_index': i,
    'step_name': step.step_name,
    'tool_name': step.tool_name,
    'file_path': str(step.file_path),
    'file_type': step.file_type,
    'step_number': step.step_number if hasattr(step, 'step_number') else i,
}

list_data.append({
    'text': title,
    'subtitle': subtitle,
    'icon': toga.Icon(icon_name) if icon_name else None,
    '_item_id': i,  # Store index for callback (backward compat)
    '_collection_data': collection_data  # Full step data
})

self.logger.debug(f"StepBrowser: Created row {i}: title='{title}', collection_data={collection_data}")
```

**Impact:** Now when a step is selected, the Row object contains full step information in `_collection_data`, allowing the selection callback to properly identify which step was clicked.

### 2. Enhanced StepBrowser Selection Logging

**File:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/preview/step_browser.py`

**Location:** Lines 186-251

**Added Logging:**
```python
self.logger.info(f"🔍 StepBrowser: Selection callback triggered")
self.logger.info(f"🔍   widget_or_data type: {type(widget_or_data)}")
self.logger.info(f"🔍   widget_or_data: {widget_or_data}")
# ... extracting data ...
self.logger.info(f"🔍 Selected data contents: {selected_data}")
self.logger.info(f"✅ StepBrowser: Step selected at index {index}")
self.logger.info(f"✅   Step name: {selected_data.get('step_name', 'unknown')}")
self.logger.info(f"✅   Tool name: {selected_data.get('tool_name', 'unknown')}")
self.logger.info(f"✅   File path: {selected_data.get('file_path', 'unknown')}")
```

**Impact:** Complete visibility into what data is being passed through the selection callback, making it easy to debug future issues.

### 3. Add Debugging Info to Path Bar

**File:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/preview/output_pane.py`

**Location:** Lines 1079-1134

**Changes:**
1. Modified `_update_path_bar()` signature to accept optional `processing_step` parameter
2. Added debug info to path bar display showing step name, renderer, and item ID
3. Added comprehensive logging of what's being rendered

**Added Display:**
```
Collection › Item • Step: crop • Renderer: CropRenderer • Item: abc123de
```

**Added Logging:**
```python
self.logger.info(f"🎨 Path bar updated:")
self.logger.info(f"🎨   Collection: {collection_name}")
self.logger.info(f"🎨   Item: {item.name}")
self.logger.info(f"🎨   Step: {processing_step.step_name}")
self.logger.info(f"🎨   Renderer: {renderer_name}")
self.logger.info(f"🎨   Output: {processing_step.file_path}")
```

**Impact:** The path bar now shows exactly which step is being displayed and which renderer is being used, making it immediately obvious if the wrong renderer is selected.

### 4. Enhanced OutputPane Step Rendering Logging

**File:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/preview/output_pane.py`

**Location:** Lines 610-623, 681-692

**Added Logging:**

At step selection:
```python
self.logger.info(f"📍 OutputPane: Rendering step {step_index}")
self.logger.info(f"📍   Step name: {processing_step.step_name}")
self.logger.info(f"📍   Tool name: {processing_step.tool_name}")
self.logger.info(f"📍   File path: {processing_step.file_path}")
self.logger.info(f"📍   File type: {processing_step.file_type}")
```

At renderer selection:
```python
self.logger.info(f"🎨 OutputPane: Requesting renderer for:")
self.logger.info(f"🎨   tool_name: {tool_name}")
self.logger.info(f"🎨   file_type: {file_type}")
self.logger.info(f"🎨   file_path: {file_path}")
# ... get renderer ...
self.logger.info(f"✅ Using renderer: {renderer.__class__.__name__} for tool '{tool_name}'")
```

**Impact:** Complete traceability of which renderer is selected for each step, making it easy to verify that CropRenderer is being used for crop steps.

## Testing Instructions

### Manual Testing

1. **Start the app:**
   ```bash
   briefcase dev
   ```

2. **Select a collection** with processed items

3. **Select an item** that has multiple steps (e.g., Original → crop → rotate)

4. **Click on the "crop" step** in the step browser

5. **Verify in logs:**
   ```
   🔍 StepBrowser: Selection callback triggered
   🔍   widget_or_data type: <class 'toga.sources.list_source.Row'>
   🔍 Extracted _collection_data from Row: {'_item_id': 1, 'step_index': 1, 'step_name': 'crop', ...}
   ✅ StepBrowser: Step selected at index 1
   ✅   Step name: crop
   ✅   Tool name: crop
   ✅   File path: /path/to/output/crop/image.jpg
   📍 OutputPane: Rendering step 1
   📍   Step name: crop
   📍   Tool name: crop
   📍   File path: /path/to/output/crop/image.jpg
   🎨 OutputPane: Requesting renderer for:
   🎨   tool_name: crop
   🎨   file_type: image
   ✅ Using renderer: CropRenderer for tool 'crop'
   🎨 Path bar updated:
   🎨   Step: crop
   🎨   Renderer: CropRenderer
   🎨   Output: /path/to/output/crop/image.jpg
   ```

6. **Verify in UI:**
   - Path bar shows: `Collection › Item • Step: crop • Renderer: CropRenderer • Item: abc123de`
   - Output pane displays the cropped image
   - Crop boundaries are visible (if CropRenderer is working correctly)

### Expected Log Flow

Complete data flow for successful step selection:

```
🔍 StepBrowser: Selection callback triggered
🔍   widget_or_data type: <class 'toga.sources.list_source.Row'>
🔍   widget_or_data: Row 41e33eda0 icon=... steps='crop' subtitle='image' title='crop'
🔍 Extracted _collection_data from Row: {'_item_id': 1, 'step_index': 1, 'step_name': 'crop', ...}
🔍 Selected data contents: {'_item_id': 1, 'step_index': 1, 'step_name': 'crop', ...}
✅ StepBrowser: Step selected at index 1
✅   Step name: crop
✅   Tool name: crop
✅   File path: /Users/.../output/crop/0001.jpg
✅ Calling parent on_step_selected callback with index 1
📍 OutputPane: Rendering step 1
📍   Step name: crop
📍   Tool name: crop
📍   File path: /Users/.../output/crop/0001.jpg
📍   File type: image
🎨 OutputPane: Requesting renderer for:
🎨   tool_name: crop
🎨   file_type: image
🎨   file_path: /Users/.../output/crop/0001.jpg
✅ Using renderer: CropRenderer for tool 'crop'
🎨 Path bar updated:
🎨   Collection: My Collection
🎨   Item: 0001.jpg
🎨   Step: crop
🎨   Renderer: CropRenderer
🎨   Output: /Users/.../output/crop/0001.jpg
```

### Automated Testing

**Future Enhancement:** Add unit test to verify data flow:

```python
def test_step_browser_populates_collection_data():
    """Verify that StepBrowser populates _collection_data in list items."""
    # Create test steps
    steps = [
        Step(step_name='Original', tool_name='original', ...),
        Step(step_name='crop', tool_name='crop', ...),
    ]

    # Load into StepBrowser
    browser = StepBrowser()
    browser.load_steps(steps)

    # Verify list_data has _collection_data
    # (need to expose list_data for testing)
    assert browser._step_list._data[0]['_collection_data'] is not None
    assert browser._step_list._data[1]['_collection_data']['step_name'] == 'crop'
```

## Verification Checklist

- [x] Code changes implemented
- [x] Logging added for full traceability
- [x] Path bar shows debug information
- [ ] Manual testing completed (pending app startup)
- [ ] Crop step displays correctly
- [ ] CropRenderer is being used for crop steps
- [ ] Unit tests added (future enhancement)

## Related Documents

- `STEP_BROWSER_DATA_FLOW_ANALYSIS.md` - Root cause analysis
- `TOOL_INTEGRATION_MASTER_PLAN.md` - Overall architecture plan
- `RENDERER_STATUS.md` - Renderer integration status

## Success Criteria

1. ✅ StepBrowser creates Row objects with populated `_collection_data`
2. ✅ Selection callback receives full step information
3. ✅ Path bar displays step name, renderer name, and item ID
4. ✅ Comprehensive logging shows complete data flow
5. ⏳ Crop steps display using CropRenderer (pending verification)
6. ⏳ Crop boundaries are visible in output (pending verification)

## Next Steps

1. Complete manual testing by clicking on crop step
2. Verify CropRenderer is being used
3. Investigate why crop boundaries might not be displaying (if issue persists)
4. Add unit tests for data flow
5. Apply same pattern to other browsers (FileListBrowser, etc.)
