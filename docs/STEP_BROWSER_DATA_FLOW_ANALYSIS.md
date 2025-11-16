# StepBrowser Data Flow Analysis

**Date:** 2025-11-15
**Issue:** StepBrowser Row objects had `_collection_data = None`, breaking step selection

## Problem Summary

The logs showed that when clicking on a step in the StepBrowser:
```
Row 41e33eda0 icon=... steps='crop' subtitle='image' title='crop'
Extracted _collection_data from Row: None
StepBrowser: No selected_data in callback
```

The Row object was being created with display attributes (title, subtitle, icon, steps) but `_collection_data` was None, preventing the selection callback from accessing step information.

## Root Cause

### Investigation Path

1. **StepBrowser Row Creation** (`step_browser.py` lines 102-124)
   - The StepBrowser was creating list data for the ListWidget
   - It was only setting `_item_id` (the step index)
   - It was NOT setting `_collection_data` with step information

2. **ListWidget Data Flow** (`list_widget/base.py`)
   - ListWidget accepts data as a list of dicts
   - Each dict can have custom fields like `_collection_data` and `_item_id`
   - These are preserved through the Source layer (ListSource/TreeSource)

3. **NativeRenderer Processing** (`renderers/native.py` lines 122, 189-190, 218-219)
   - NativeRenderer lists `_collection_data` as a valid accessor (line 122)
   - When converting data to source format, it extracts and preserves `_collection_data` (lines 189-190, 218-219)
   - BUT if `_collection_data` wasn't in the input data, it becomes None

4. **Selection Callback** (`step_browser.py` lines 186-252)
   - When a row is selected, the callback receives a Row/Node object
   - It tries to extract `_collection_data` via `widget_or_data._collection_data`
   - If `_collection_data` is None, the callback has no information about which step was selected

### The Bug

In `step_browser.py` lines 119-124, the data was created as:
```python
list_data.append({
    'text': title,
    'subtitle': subtitle,
    'icon': toga.Icon(icon_name) if icon_name else None,
    '_item_id': i  # Store index for callback
})
# Missing: '_collection_data': {...}
```

The `_collection_data` field was never populated, so when the NativeRenderer converted this to source format, it preserved `_collection_data: None`.

## Data Flow Diagram

```
StepBrowser.load_steps(steps: List[Step])
  └─> Creates list_data = [{'text': ..., '_item_id': i}]  ❌ No _collection_data
        └─> ListWidget(data=list_data)
              └─> NativeRenderer.convert_to_source_format(data)
                    └─> Creates Row with _collection_data=None  ❌
                          └─> User clicks row
                                └─> _on_step_selected(row)
                                      └─> row._collection_data = None  ❌
                                            └─> Callback fails
```

## Expected Data Flow (Fixed)

```
StepBrowser.load_steps(steps: List[Step])
  └─> Creates list_data = [
        {
          'text': ...,
          '_item_id': i,
          '_collection_data': {  ✅ Full step info
            'step_index': i,
            'step_name': step.step_name,
            'tool_name': step.tool_name,
            'file_path': str(step.file_path),
            'file_type': step.file_type,
          }
        }
      ]
        └─> ListWidget(data=list_data)
              └─> NativeRenderer.convert_to_source_format(data)
                    └─> Creates Row with _collection_data={...}  ✅
                          └─> User clicks row
                                └─> _on_step_selected(row)
                                      └─> row._collection_data = {...}  ✅
                                            └─> Callback succeeds
                                                  └─> OutputPane.set_step(item_id, step_index)
```

## Why This Happened

The StepBrowser was originally written before the `_collection_data` pattern was established. It was using a simpler approach of just passing the index (`_item_id`), which worked for basic selection but didn't provide enough context for:
- Debugging which step was selected
- Showing step information in the path bar
- Determining which renderer to use
- Error reporting

## Step Object Structure

The Step dataclass from `step_manager.py` contains:
```python
@dataclass
class Step:
    # Core identification
    step_name: str
    tool_name: str
    step_number: int

    # File information
    file_path: Path
    file_type: str  # "image", "text", "json", "document", "folder"

    # Metadata
    description: str = ""
    parameters: Dict[str, Any] = None

    # Workflow context
    plan_name: str = ""
    workflow_name: str = ""
    prompt_used: str = ""

    # Status
    status: str = "completed"
    error_message: str = ""
```

All of this information should be available in `_collection_data` for proper debugging and display.

## Fix Applied

See `STEP_BROWSER_FIX_IMPLEMENTATION.md` for details.

## Lessons Learned

1. **Always populate _collection_data**: Any ListWidget that displays selectable items should populate `_collection_data` with all relevant information, not just an ID.

2. **Logging early and often**: The comprehensive logging we added revealed exactly where the data was lost.

3. **Follow established patterns**: The Library and Collection views already use `_collection_data` correctly. StepBrowser should have followed the same pattern from the start.

4. **Test data flow end-to-end**: Unit tests should verify that data flows through the entire chain: data creation → ListWidget → Renderer → Source → Selection → Callback.

## Related Files

- `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/preview/step_browser.py`
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/widgets/list_widget/base.py`
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/widgets/list_widget/renderers/native.py`
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/preview/step_manager.py`
