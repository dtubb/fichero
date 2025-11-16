# Crop Workflow Integration Guide

**Date**: 2025-11-15
**Version**: 1.0

## Overview

This guide documents how the crop workflow integrates across Fichero's architecture, from CLI processing through GUI display to interactive editing.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Interface                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  LibraryView              CollectionView           OutputView        │
│  ┌──────────┐            ┌──────────────┐         ┌───────────────┐ │
│  │Collections│   ──────>  │ Items        │  ────>  │ StepBrowser   │ │
│  │  List    │            │  List        │         │  ┌─────────┐  │ │
│  └──────────┘            └──────────────┘         │  │Original │  │ │
│                                                    │  │crop     │  │ │
│                                 ┌──────────────┐  │  │transcribe│ │ │
│                                 │              │  │  └─────────┘  │ │
│                                 │ OutputPane   │  └───────────────┘ │
│                                 │  ┌────────┐  │                    │
│                                 │  │Cropped │  │                    │
│                                 │  │Image   │  │                    │
│                                 │  └────────┘  │                    │
│                                 │  Metadata:   │                    │
│                                 │  crop_box,   │                    │
│                                 │  method, etc │                    │
│                                 └──────────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Uses
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Renderer System (Phase 2)                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  RendererRegistry                                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ get_renderer_for_step(tool_name='crop', file_type='image')  │   │
│  └───────────────────────────────────┬──────────────────────────┘   │
│                                      │                               │
│                                      ▼                               │
│  CropRenderer                                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ render_html(context)                                         │   │
│  │  - Loads cropped image from file_path                        │   │
│  │  - Reads metadata from manifest_entry                        │   │
│  │  - Generates interactive HTML with crop overlay              │   │
│  │                                                               │   │
│  │ apply_json_edits(context, json_data)                         │   │
│  │  - Applies new crop coordinates                              │   │
│  │  - Re-processes with crop tool                               │   │
│  │  - Updates library metadata                                  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Reads/Writes
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Library Backend (Storage)                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  LibraryManager                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ get_item_output_data(item_id)                                │   │
│  │  Returns:                                                     │   │
│  │  {                                                            │   │
│  │    processing_steps: [                                        │   │
│  │      {                                                         │   │
│  │        step_name: "crop",                                     │   │
│  │        tool_name: "crop",                                     │   │
│  │        file_path: "/path/to/output/crop/file_cropped.jpg",   │   │
│  │        file_type: "image",                                    │   │
│  │        manifest_entry: {                                      │   │
│  │          source: "/path/to/original.jpg",                     │   │
│  │          details: {                                            │   │
│  │            box: {x1, y1, x2, y2},                             │   │
│  │            method: "auto",                                    │   │
│  │            confidence: 0.95                                   │   │
│  │          }                                                     │   │
│  │        }                                                       │   │
│  │      },                                                        │   │
│  │      ... other steps ...                                      │   │
│  │    ]                                                           │   │
│  │  }                                                            │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  Storage Layer                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Database (SQLite):                                           │   │
│  │  - collection_items table                                    │   │
│  │  - item_processing_steps table                               │   │
│  │  - item_metadata table                                       │   │
│  │                                                               │   │
│  │ Filesystem:                                                  │   │
│  │  - /collection_root/output/crop/*.jpg                        │   │
│  │  - /collection_root/output/crop/manifest.jsonl               │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Uses
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Director System (Workflow)                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Coordinator                                                         │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ process_item(item_id, workflow='crop')                       │   │
│  │  1. Loads workflow YAML (plans/crop.yaml)                    │   │
│  │  2. Executes crop tool                                       │   │
│  │  3. Saves outputs to library                                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  Crop Tool                                                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ execute(input_path, output_path, params)                     │   │
│  │  - Detects document boundaries                               │   │
│  │  - Crops image                                               │   │
│  │  - Saves to output_path                                      │   │
│  │  - Returns metadata (box, method, confidence)                │   │
│  │                                                               │   │
│  │  Metadata written to manifest.jsonl:                         │   │
│  │  {                                                            │   │
│  │    "source": "/path/to/input.jpg",                           │   │
│  │    "output": "file_cropped.jpg",                             │   │
│  │    "tool": "crop",                                           │   │
│  │    "details": {                                               │   │
│  │      "box": {"x1": 10, "y1": 20, "x2": 500, "y2": 700},     │   │
│  │      "method": "auto",                                       │   │
│  │      "confidence": 0.95                                      │   │
│  │    }                                                          │   │
│  │  }                                                            │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow: Clicking Crop Step

### Step-by-Step Flow

1. **User clicks "crop" in StepBrowser**
   - Location: `src/fichero/windows/main/views/preview/step_browser.py`
   - Trigger: ListWidget `on_select` callback

2. **StepBrowser._on_step_selected() called**
   ```python
   # Receives Row object from ListWidget
   def _on_step_selected(self, row_object, **kwargs):
       # Extract _collection_data from Row
       selected_data = row_object._collection_data  # ← FIX APPLIED HERE
       index = selected_data.get('_item_id')  # Step index (e.g., 1 for crop)

       # Notify OutputView
       self.on_step_selected(index)  # Calls OutputView._on_step_selected
   ```

3. **OutputView._on_step_selected() called**
   - Location: `src/fichero/windows/main/views/preview/output_view.py`
   - Receives: `step_index=1` (for crop)

4. **OutputPane.set_step() called**
   ```python
   async def set_step(self, item_id: str, step_index: int):
       # Get output data from library
       output_data = await library_manager.get_item_output_data(item_id)

       # Extract the specific processing step
       processing_step_index = step_index - 1  # Adjust for 0-indexed array
       processing_step = output_data['processing_steps'][processing_step_index]

       # Use renderer system to generate HTML
       html = self._render_step_with_renderer(processing_step, output_data)

       # Display in WebView
       self._webview.set_content("", html)
   ```

5. **RendererRegistry.get_renderer_for_step() called**
   ```python
   # Gets CropRenderer based on tool_name='crop'
   renderer = RendererRegistry.get_renderer_for_step(
       tool_name='crop',
       file_type='image',
       file_path='/path/to/cropped.jpg'
   )
   ```

6. **CropRenderer.render_html() called**
   ```python
   def render_html(self, context: RenderContext) -> RenderOutput:
       # Load cropped image
       image_path = context.file_path  # /path/to/output/crop/file_cropped.jpg

       # Get crop metadata
       crop_box = context.manifest_entry['details']['box']
       method = context.manifest_entry['details']['method']

       # Generate interactive HTML with crop overlay
       html = get_interactive_image_viewer(
           image_path=image_path,
           title=f"Crop: {image_path.name}",
           metadata={
               'crop_box': crop_box,
               'method': method,
               'confidence': context.manifest_entry['details'].get('confidence')
           },
           interactive=context.interactive  # Enable crop editing
       )

       return RenderOutput(html=html)
   ```

7. **HTML displayed in OutputPane WebView**
   - Shows cropped image
   - Displays crop metadata
   - Enables interactive crop editing (if `interactive=True`)

## Common Issues and Troubleshooting

### Issue 1: "No selected_data in callback"

**Symptom**: Clicking crop step does nothing, log shows:
```
StepBrowser: No selected_data in callback (probably deselection)
```

**Cause**: StepBrowser not extracting `_collection_data` from Row object

**Fix**: Applied in this revision (see `_on_step_selected()` method)

**Verification**:
```bash
# Check logs for:
# "Extracted _collection_data from Row: {...}"
# "StepBrowser: Step selected at index X"
```

### Issue 2: Cropped image not found

**Symptom**: OutputPane shows error: "File not found"

**Cause**: Crop output not saved to library correctly

**Debug**:
```bash
# Check if crop outputs exist
ls -la /path/to/collection/output/crop/

# Check manifest
cat /path/to/collection/output/crop/manifest.jsonl

# Check library database
briefcase dev -- library metadata-show <item_id> --step crop
```

**Fix**: Verify crop tool is saving outputs to correct location

### Issue 3: Crop metadata missing

**Symptom**: Cropped image displays but no metadata (crop box, method, etc.)

**Cause**: Manifest entry not being read correctly

**Debug**:
```bash
# Check manifest.jsonl structure
cat /path/to/collection/output/crop/manifest.jsonl | jq .

# Should have:
# {
#   "details": {
#     "box": {"x1": ..., "y1": ..., "x2": ..., "y2": ...},
#     "method": "auto",
#     "confidence": 0.95
#   }
# }
```

**Fix**: Verify crop tool is writing metadata correctly

### Issue 4: Interactive crop editing doesn't work

**Symptom**: Can't adjust crop box in OutputPane

**Cause**: JavaScript crop handler not registered

**Debug**: Check browser console (if accessible) for JavaScript errors

**Fix**: Verify `get_interactive_image_viewer()` includes crop editing JavaScript

## File Locations

### Key Source Files

| Component | File | Purpose |
|-----------|------|---------|
| StepBrowser | `src/fichero/windows/main/views/preview/step_browser.py` | Sidebar list of processing steps |
| OutputPane | `src/fichero/windows/main/views/preview/output_pane.py` | Main display area for step outputs |
| CropRenderer | `src/fichero/library/renderers/crop.py` | Renders crop outputs to HTML |
| RendererRegistry | `src/fichero/library/renderers/renderer_registry.py` | Maps tools to renderers |
| LibraryManager | `src/fichero/library/library_manager.py` | Data access layer |
| Crop Tool | `src/fichero/tools/crop.py` | Crop processing logic |

### Configuration Files

| File | Purpose |
|------|---------|
| `src/fichero/resources/plans/crop.yaml` | Crop workflow definition |
| `src/fichero/resources/prompts/crop.txt` | AI prompts for crop (if using AI) |

### Test Files

| File | Purpose |
|------|---------|
| `tests/test_crop_renderer.py` | Unit tests for CropRenderer |
| `tests/test_step_browser.py` | Unit tests for StepBrowser |
| `test_preview_selection.py` | Integration test for preview system |

## Testing Checklist

- [ ] CLI: Process item with crop workflow
- [ ] CLI: Verify crop outputs saved correctly
- [ ] CLI: Verify manifest.jsonl has correct structure
- [ ] GUI: Click crop step in StepBrowser
- [ ] GUI: Verify cropped image displays in OutputPane
- [ ] GUI: Verify crop metadata visible
- [ ] GUI: Verify interactive crop editing works (if implemented)
- [ ] GUI: Switch between steps (Original → crop → transcribe)
- [ ] GUI: Switch between items
- [ ] Logs: No "No selected_data" errors
- [ ] Logs: "Extracted _collection_data from Row" appears

## Future Enhancements

1. **Interactive Crop Editing**: Allow users to adjust crop box in GUI
2. **Crop Presets**: Add common crop ratios (A4, Letter, Square, etc.)
3. **Batch Crop**: Apply same crop to multiple images
4. **Crop History**: Undo/redo crop operations
5. **Crop Preview**: Show before/after comparison

## References

- **Phase 2 Renderers**: `docs/architecture/RENDERER_STATUS.md`
- **Phase 4 Preview**: `docs/architecture/PREVIEW_INTEGRATION_PLAN_REVIEW.md`
- **Director Integration**: `DIRECTOR_INTEGRATION.md`
- **ListWidget Architecture**: `docs/architecture/LIST_WIDGET_ARCHITECTURE.md`
