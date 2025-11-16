# Crop Tool Code Review

**Date:** November 15, 2025
**Reviewer:** Claude (Sonnet 4.5)
**Scope:** Comprehensive review of crop tool backend, renderer, HTML templates, and library integration

---

## Executive Summary

The crop tool implementation is functionally complete for batch processing but **lacks critical features for interactive editing**. Key findings:

1. **CRITICAL**: No bidirectional data flow - HTML renderer can display crops but cannot save changes back to manifests/library
2. **MAJOR**: Missing JavaScript-to-Python message passing bridge for interactive crop adjustments
3. **MAJOR**: Crop coordinate system inconsistency - tool uses `{x1, y1, x2, y2}` but renderer validates `{x, y, width, height}`
4. **MAJOR**: No integration with StepEditor for manifest updates
5. **MINOR**: Rubber-band crop viewer is display-only (TODO comment indicates incomplete implementation)

**Current State:** Crop tool can process images and save metadata. Users can view crops in HTML but cannot adjust them interactively.

**Desired State:** Users can draw/adjust crops in HTML renderer, and changes are saved to both JSONL manifest AND library database.

---

## Part 1: Bug Inventory

### BUG-001: Coordinate System Mismatch (CRITICAL)
**File:** `src/fichero/library/renderers/tool_renderers/crop_renderer.py` (lines 218-243)
**Description:** Validation expects `crop_box` with `{x, y, width, height}` but crop tool produces `details.box` with `{x1, y1, x2, y2}`
**Impact:** Validation will always fail when applying edits from HTML viewer
**Evidence:**
```python
# crop_renderer.py line 219-228 (WRONG format expected)
if 'crop_box' not in json_data:
    return False, "Missing 'crop_box' field"
crop_box = json_data['crop_box']
required_fields = ['x', 'y', 'width', 'height']  # ❌ Wrong format

# crop.py line 71-73 (ACTUAL format from tool)
box: dict  # {"x1": int, "y1": int, "x2": int, "y2": int}  # ✅ Actual format
```
**Fix:** Update validation to use `x1, y1, x2, y2` format OR convert between formats consistently

---

### BUG-002: Missing Source Path Resolution (MAJOR)
**File:** `src/fichero/library/renderers/tool_renderers/crop_renderer.py` (lines 72-94)
**Description:** Source image search tries multiple locations but doesn't check `documents/` folder first (where originals are stored)
**Impact:** May fail to find source image for re-cropping
**Evidence:**
```python
possible_source_paths = [
    item_dir / 'assets' / 'original' / source_file,  # Prepared images
    item_dir / 'documents' / source_file,  # Original documents ← ORDER MATTERS
    item_dir / source_file,  # Root level
]
```
**Fix:** Reorder to check `documents/` first, or use library's path resolution utility

---

### BUG-003: apply_json_edits Doesn't Update Library Database (CRITICAL)
**File:** `src/fichero/library/renderers/tool_renderers/crop_renderer.py` (lines 286-378)
**Description:** `apply_json_edits()` only updates JSONL manifest file, doesn't persist to SQLite library database
**Impact:** Changes lost on library reload; library queries don't reflect manual crops
**Evidence:**
```python
# Line 368: Only updates manifest file
with open(manifest_file, 'w') as f:
    f.writelines(lines)
# ❌ No call to library_manager.storage.update_processing_output()
```
**Fix:** After manifest update, also update `processing_outputs` table via LibraryStorage

---

### BUG-004: No Message Handler for HTML Crop Viewer (CRITICAL)
**File:** `src/fichero/library/renderers/html_templates_crop.py` (line 448)
**Description:** Apply Crop button shows alert() but has no Python callback
**Impact:** Interactive crop selection cannot be saved
**Evidence:**
```javascript
function applyCrop() {
    if (!selection) return;
    const cropData = { x1: ..., y1: ..., x2: ..., y2: ... };
    console.log('Applying crop:', cropData);
    // TODO: Send to Python backend  ← Not implemented!
    alert('Crop applied!...');
}
```
**Fix:** Add `window.webkit.messageHandlers` integration like OutputPane click detection

---

### BUG-005: Crop Tool Doesn't Support Interactive Mode (MAJOR)
**File:** `src/fichero/tools/crop.py`
**Description:** Crop tool is batch-only, no function to crop a single image with provided coordinates
**Impact:** Cannot reprocess single image when user adjusts crop in GUI
**Evidence:**
- `crop_batch()` - batch processing only
- `process_image()` - uses YOLO/contour detection, no coordinate override
- No `crop_with_box()` function that accepts manual coordinates
**Fix:** Add new function `crop_with_manual_box(image_path, box, output_path)`

---

### BUG-006: ContourSettings Not Editable in GUI (MINOR)
**File:** `src/fichero/library/renderers/tool_renderers/crop_renderer.py`
**Description:** `get_editable_json()` returns entire manifest (line 198) instead of extracting crop-specific fields
**Impact:** Users see all metadata fields, can't easily adjust crop template/padding/settings
**Evidence:**
```python
def _extract_crop_data(self, manifest_entry: Dict[str, Any]) -> Dict[str, Any]:
    # Just return the entire manifest - no need to extract specific fields
    return manifest_entry  # ❌ Too much data
```
**Fix:** Extract only editable fields: `box`, `padding`, `method`, `contour_settings`

---

### BUG-007: Missing Crop Box Validation in Tool (MINOR)
**File:** `src/fichero/tools/crop.py`
**Description:** No validation that crop box coordinates are within image bounds
**Impact:** Could generate invalid crops if manually edited coordinates exceed image size
**Evidence:**
- Line 310-315: Padding validation exists
- No validation that `x1 >= 0`, `y1 >= 0`, `x2 <= width`, `y2 <= height`
**Fix:** Add bounds checking in `crop_with_manual_box()` function

---

## Part 2: Architecture Issues

### ARCH-001: No Renderer-to-Library Communication Channel
**Current State:**
- HTML templates are display-only
- No JavaScript message passing bridge exists for crop renderer
- `apply_json_edits()` method exists but not connected to HTML

**Problem:**
Interactive crop viewer (rubber-band selection) cannot trigger Python code to save changes

**Required Architecture:**
```
HTML Crop Viewer → JavaScript postMessage → OutputPane WKWebView Handler →
CropRenderer.apply_json_edits() → StepEditor.update_manifest_entry() →
LibraryManager.save_output_metadata()
```

**Current Architecture:**
```
HTML Crop Viewer → JavaScript alert() → ❌ DEAD END
```

**Reference Implementation:**
OutputPane already has working message handler (line 27-69 in `output_pane.py`)

---

### ARCH-002: Tight Coupling Between Renderer and File System
**Problem:**
`CropRenderer.apply_json_edits()` directly manipulates:
- File paths (line 313-317)
- JSONL files (line 343-372)
- PIL image operations (line 321-340)

This violates single responsibility and makes testing difficult.

**Better Architecture:**
```
CropRenderer → delegates to → ImageCropService → uses →
    - StepEditor (for manifest updates)
    - LibraryManager (for database updates)
    - CropTool.crop_with_manual_box() (for image processing)
```

---

### ARCH-003: Missing Crop Metadata Schema
**Problem:**
No formal schema for crop metadata in library database. Currently stored as JSON blob in `processing_outputs.metadata` or manifest `details`.

**Issues:**
- Cannot query crops by method (YOLO vs contour vs manual)
- Cannot search by confidence threshold
- Cannot filter by crop size
- Cannot rebuild processing history

**Proposed Schema:**
```python
# Add to ProcessingOutput model or create CropMetadata model
crop_method: str  # "yolo", "contour", "manual"
crop_box_x1: int
crop_box_y1: int
crop_box_x2: int
crop_box_y2: int
crop_confidence: float
crop_padding: int
crop_contour_template: str  # "auto", "dark_background", etc.
original_width: int
original_height: int
cropped_width: int
cropped_height: int
```

---

### ARCH-004: No Versioning for Manual Edits
**Problem:**
When user manually adjusts crop:
- Original YOLO/contour crop is lost
- Cannot revert to auto-detected crop
- Cannot compare manual vs auto

**Proposed Solution:**
- Keep original crop in `details.auto_crop_box`
- Save manual edit as `details.manual_crop_box`
- Track edit history: `details.crop_history = [{timestamp, box, method, user}, ...]`

---

## Part 3: Feature Gap Analysis

### Feature 1: Interactive Crop in HTML Renderer

**User Story:** As a user, I want to draw a crop box in the HTML viewer and save it

**Current State:**
✅ HTML crop viewer displays image with rubber-band selection
✅ User can draw/resize crop box
✅ Crop coordinates displayed in toolbar
❌ "Apply Crop" button just shows alert
❌ No Python callback registered
❌ No integration with library backend

**Required Components:**

1. **JavaScript Message Handler** (NEW)
   - File: `src/fichero/library/renderers/html_templates_crop.py`
   - Add: `window.webkit.messageHandlers.cropEdit.postMessage(cropData)`
   - Pattern: Copy from `output_pane.py` lines 272-300

2. **OutputPane Crop Message Handler** (NEW)
   - File: `src/fichero/windows/main/views/preview/output_pane.py`
   - Add: Handler for 'cropEdit' messages
   - Action: Call `renderer.apply_json_edits(context, cropData)`

3. **CropRenderer.apply_json_edits() Enhancement** (MODIFY)
   - File: `src/fichero/library/renderers/tool_renderers/crop_renderer.py`
   - Current: Lines 286-378 (partially implemented)
   - Add: Database update after manifest update
   - Add: Event emission for UI refresh

**Data Flow:**
```
User drags crop box in HTML
    ↓
JavaScript applyCrop() called
    ↓
window.webkit.messageHandlers.cropEdit.postMessage({
    x1: 100, y1: 50, x2: 900, y2: 650,
    item_id: "...", step_index: 2
})
    ↓
OutputPane._handle_crop_edit() receives message
    ↓
CropRenderer.apply_json_edits(context, crop_data)
    ↓
    1. Load source image
    2. Crop with PIL
    3. Save cropped image
    4. Update manifest JSONL
    5. Update library database (NEW!)
    6. Emit "output_updated" event
    ↓
UI refreshes to show new crop
```

---

### Feature 2: Edit All Crop Settings

**User Story:** As a user, I want to edit crop method, padding, and contour template in the GUI

**Current State:**
✅ Settings exist in crop tool (padding, template, method)
✅ Settings saved to manifest in `details.contour_settings`
❌ Not exposed in renderer's `get_editable_json()`
❌ No GUI controls for adjusting
❌ No re-processing with new settings

**Required Components:**

1. **Settings Editor UI** (NEW)
   - File: `src/fichero/library/renderers/html_templates_crop.py` (or new file)
   - Add: Form with dropdowns and sliders
   - Fields:
     - Method: YOLO / Contour / Manual
     - Padding: 0-100px slider
     - Template: auto / dark_background / light_background / etc.
     - (If contour) threshold_method, blur_kernel, etc.

2. **get_editable_json() Enhancement** (MODIFY)
   - File: `src/fichero/library/renderers/tool_renderers/crop_renderer.py`
   - Current: Line 184-199 (returns entire manifest)
   - Change: Extract only editable fields
```python
def _extract_crop_data(self, manifest_entry: Dict[str, Any]) -> Dict[str, Any]:
    details = manifest_entry.get('details', {})
    return {
        'box': details.get('box'),
        'padding': details.get('padding', 30),
        'method': details.get('method', 'auto'),
        'contour_settings': details.get('contour_settings', {}),
        # Include source info for re-processing
        'source': manifest_entry.get('source'),
    }
```

3. **Re-process with New Settings** (NEW)
   - Add method: `CropRenderer.reprocess_with_settings(context, settings)`
   - Calls: `crop_tool.crop_with_contours(image, settings=ContourSettings(**settings))`
   - Updates: Both manifest and database

---

### Feature 3: Save to Both Library and JSON

**User Story:** As a developer, I need crop changes persisted in both JSONL manifest and SQLite database

**Current State:**
✅ JSONL manifest updated (line 343-372 in crop_renderer.py)
❌ Library database NOT updated
❌ ProcessingOutput record not marked as modified
❌ ExtractedMetadata not updated with new crop coordinates

**Required Architecture:**

```python
# In CropRenderer.apply_json_edits()

# After updating manifest file (line 368)...

# 1. Get the ProcessingOutput record for this file
output_record = self.library_manager.storage.get_processing_outputs(
    processing_result_id=...  # Need to track this!
)

# 2. Update the output record
output_record.metadata = {
    **output_record.metadata,
    'crop_manually_edited': True,
    'crop_edited_at': datetime.now().isoformat(),
    'crop_box': box,
}
output_record.file_modified = datetime.now()

self.library_manager.storage.update_processing_output(output_record)

# 3. Update ExtractedMetadata for searchability
from fichero.library.models import ExtractedMetadata
metadata = ExtractedMetadata(
    processing_output_id=output_record.id,
    collection_id=context.collection_id,
    item_id=context.item_id,
    metadata_type='crop',
    key='manual_box',
    value=json.dumps(box),
    confidence=1.0,
    context='User manually adjusted crop',
    created_at=datetime.now()
)
self.library_manager.storage.add_extracted_metadata(metadata)

# 4. Emit event for UI refresh
emit_navigation_event("output_updated", {
    "item_id": context.item_id,
    "step_index": context.step_index,
    "step_name": "crop"
})
```

**Missing Information Problem:**
`apply_json_edits()` doesn't have access to:
- `processing_result_id` (needed to find ProcessingOutput)
- `collection_id` (needed for ExtractedMetadata)
- `item_id` (needed for events)

**Solution:** Enhance RenderContext to include these IDs:
```python
# In base_renderer.py
@dataclass
class RenderContext:
    # ... existing fields ...

    # PHASE 6: Add library context
    collection_id: Optional[str] = None
    processing_result_id: Optional[str] = None
```

---

## Part 4: Implementation Instructions

### Phase 1: Fix Critical Bugs (1 session)

**Agent Context:**
"You are fixing critical bugs in the Fichero crop tool to enable interactive editing. Focus on coordinate system consistency and validation."

**Tasks:**

1. **Fix coordinate system mismatch** (BUG-001)
   - File: `src/fichero/library/renderers/tool_renderers/crop_renderer.py`
   - In `validate_json()` (line 201-267):
     ```python
     # OLD (lines 218-243)
     if 'crop_box' not in json_data:
         return False, "Missing 'crop_box' field"
     crop_box = json_data['crop_box']
     required_fields = ['x', 'y', 'width', 'height']

     # NEW
     # Accept both coordinate formats
     details = json_data.get('details', {})
     box = details.get('box', {})

     if not box:
         return False, "Missing 'details.box' field"

     # Validate x1, y1, x2, y2 format (used by crop tool)
     required_fields = ['x1', 'y1', 'x2', 'y2']
     for field in required_fields:
         if field not in box:
             return False, f"Missing '{field}' in box"
         if not isinstance(box[field], (int, float)):
             return False, f"box.{field} must be a number"
         if box[field] < 0:
             return False, f"box.{field} must be non-negative"

     # Validate box is sane (x2 > x1, y2 > y1)
     if box['x2'] <= box['x1']:
         return False, "box.x2 must be greater than box.x1"
     if box['y2'] <= box['y1']:
         return False, "box.y2 must be greater than box.y1"
     ```

2. **Fix _extract_crop_data to return only editable fields** (BUG-006)
   - File: `src/fichero/library/renderers/tool_renderers/crop_renderer.py`
   - Replace `_extract_crop_data()` (line 184-199):
     ```python
     def _extract_crop_data(self, manifest_entry: Dict[str, Any]) -> Dict[str, Any]:
         """Extract crop-specific editable data"""
         details = manifest_entry.get('details', {})

         # Return only editable crop fields
         crop_data = {
             'details': {
                 'box': details.get('box', {}),
                 'method': details.get('method', 'auto'),
                 'padding': details.get('padding', 30),
                 'original_size': details.get('original_size', [0, 0]),
             },
             'source': manifest_entry.get('source', ''),
         }

         # Include contour settings if method is contour
         if details.get('method') == 'contour' and 'contour_settings' in details:
             crop_data['details']['contour_settings'] = details['contour_settings']

         return crop_data
     ```

3. **Add bounds validation to apply_json_edits** (BUG-007)
   - File: `src/fichero/library/renderers/tool_renderers/crop_renderer.py`
   - In `apply_json_edits()` after line 305, add:
     ```python
     # Load original image to get dimensions
     from PIL import Image
     img = Image.open(source_path)
     img_width, img_height = img.size

     # Validate box is within image bounds
     if x1 < 0 or y1 < 0:
         return False, f"Crop box coordinates must be non-negative (got x1={x1}, y1={y1})"
     if x2 > img_width or y2 > img_height:
         return False, f"Crop box exceeds image dimensions ({img_width}x{img_height}): x2={x2}, y2={y2}"
     if x2 <= x1 or y2 <= y1:
         return False, f"Crop box must have positive area (x1={x1}, y1={y1}, x2={x2}, y2={y2})"
     ```

**Testing:**
```python
# Test coordinate validation
crop_data = {
    'details': {
        'box': {'x1': 100, 'y1': 50, 'x2': 900, 'y2': 650}
    },
    'source': 'test.jpg'
}
is_valid, error = renderer.validate_json(crop_data)
assert is_valid, f"Validation failed: {error}"
```

---

### Phase 2: Add Interactive Crop Support (2 sessions)

**Agent Context:**
"You are implementing interactive crop editing in Fichero. The rubber-band crop viewer HTML exists but needs Python integration. Follow the message handler pattern from OutputPane."

**Session 1: JavaScript Message Integration**

1. **Add message handler registration in crop viewer**
   - File: `src/fichero/library/renderers/html_templates_crop.py`
   - Find: `function applyCrop()` (line 434)
   - Replace TODO comment with:
     ```javascript
     function applyCrop() {
         if (!selection) return;

         // Round coordinates to integers
         const cropData = {
             x1: Math.round(selection.x1),
             y1: Math.round(selection.y1),
             x2: Math.round(selection.x2),
             y2: Math.round(selection.y2),
             width: Math.round(selection.x2 - selection.x1),
             height: Math.round(selection.y2 - selection.y1)
         };

         console.log('Applying crop:', cropData);

         // Send to Python via WKWebView message handler
         try {
             if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.cropEdit) {
                 window.webkit.messageHandlers.cropEdit.postMessage(JSON.stringify({
                     action: 'apply_crop',
                     box: {
                         x1: cropData.x1,
                         y1: cropData.y1,
                         x2: cropData.x2,
                         y2: cropData.y2
                     },
                     item_id: '${item_id}',  // Template variable
                     step_index: ${step_index}  // Template variable
                 }));
                 console.log('Crop data sent to Python backend');
             } else {
                 console.warn('Python message handler not available');
                 alert('Crop applied!\\n\\n' +
                       `x1=${cropData.x1}, y1=${cropData.y1}\\n` +
                       `x2=${cropData.x2}, y2=${cropData.y2}\\n\\n` +
                       `Size: ${cropData.width}×${cropData.height}`);
             }
         } catch (err) {
             console.error('Error sending crop data:', err);
             alert('Error: ' + err.message);
         }
     }
     ```

2. **Update get_rubberband_crop_viewer() to accept item context**
   - File: `src/fichero/library/renderers/html_templates_crop.py`
   - Find: `def get_rubberband_crop_viewer` (line 16)
   - Add parameters:
     ```python
     def get_rubberband_crop_viewer(
         image_path: Path,
         crop_box: dict,
         title: Optional[str] = None,
         use_base64: bool = True,
         item_id: Optional[str] = None,  # NEW
         step_index: Optional[int] = None  # NEW
     ) -> str:
     ```
   - In template string, replace hardcoded values with f-string variables

3. **Update CropRenderer to pass item context**
   - File: `src/fichero/library/renderers/tool_renderers/crop_renderer.py`
   - Find: `render_html()` call to `get_rubberband_crop_viewer()` (line 96-106)
   - Add parameters:
     ```python
     html = get_rubberband_crop_viewer(
         image_path=source_path,
         crop_box=crop_box,
         title=f"Crop Editor: {context.step_name}",
         use_base64=True,
         item_id=context.item_id,  # NEW
         step_index=context.step_index  # NEW
     )
     ```

**Session 2: Python Message Handler**

1. **Add cropEdit handler to OutputPane**
   - File: `src/fichero/windows/main/views/preview/output_pane.py`
   - Find: `_setup_click_detection()` (line 202)
   - After click handler registration (line 242), add:
     ```python
     # Add crop edit handler
     try:
         from rubicon.objc import ObjCClass

         # Create separate handler for crop edits
         CropEditHandler = type('CropEditHandler', (NSObject,), {
             'pane': None,
             'userContentController_didReceiveScriptMessage_': objc_method(
                 lambda self, controller, message: self.pane._handle_crop_edit_message(str(message.body))
             )
         })

         self._crop_handler = CropEditHandler.alloc().init()
         self._crop_handler.pane = self

         user_content_controller.addScriptMessageHandler(
             self._crop_handler,
             name='cropEdit'
         )

         self.logger.info(f"✅ Pane {self._pane_id}: Crop edit handler registered")
     except Exception as e:
         self.logger.error(f"Could not setup crop edit handler: {e}")
     ```

2. **Add _handle_crop_edit_message method**
   - File: `src/fichero/windows/main/views/preview/output_pane.py`
   - Add new method after `_handle_webview_interaction()`:
     ```python
     def _handle_crop_edit_message(self, message_body: str):
         """Handle crop edit message from JavaScript"""
         try:
             import json
             crop_data = json.loads(message_body)

             self.logger.info(f"📐 Received crop edit: {crop_data}")

             # Validate required fields
             if 'action' not in crop_data or crop_data['action'] != 'apply_crop':
                 self.logger.warning(f"Unknown crop action: {crop_data.get('action')}")
                 return

             if 'box' not in crop_data:
                 self.logger.error("Crop data missing 'box' field")
                 return

             # Get item and step context
             item_id = crop_data.get('item_id')
             step_index = crop_data.get('step_index')

             if not item_id or step_index is None:
                 self.logger.error("Crop data missing item_id or step_index")
                 return

             # Apply the crop via renderer
             self._apply_crop_edit(item_id, step_index, crop_data['box'])

         except json.JSONDecodeError as e:
             self.logger.error(f"Invalid crop message JSON: {e}")
         except Exception as e:
             self.logger.error(f"Error handling crop edit: {e}")
             import traceback
             self.logger.error(traceback.format_exc())

     async def _apply_crop_edit(self, item_id: str, step_index: int, box: dict):
         """Apply crop edit by calling renderer's apply_json_edits"""
         try:
             # Get step data
             from fichero.library.step_editor import StepEditor
             step_editor = StepEditor(self.library_manager)
             step_data = await step_editor.get_step_data(item_id, step_index)

             if not step_data:
                 self.logger.error(f"Could not find step data for item {item_id}, step {step_index}")
                 return

             # Get renderer for this step
             renderer = self.renderer_registry.get_renderer(step_data.tool_name)

             if not renderer:
                 self.logger.error(f"No renderer found for tool: {step_data.tool_name}")
                 return

             # Create render context
             context = step_editor.create_render_context(
                 step_data,
                 show_metadata=True,
                 show_content=True,
                 interactive=True
             )

             # Prepare JSON data for renderer (must match crop tool format)
             json_data = {
                 'details': {
                     'box': box  # {x1, y1, x2, y2}
                 },
                 'source': step_data.manifest_entry.get('source', '')
             }

             # Apply the edit
             success, error = renderer.apply_json_edits(context, json_data)

             if success:
                 self.logger.info(f"✅ Crop applied successfully")
                 # Reload the step to show updated crop
                 await self.set_step(item_id, step_index)
             else:
                 self.logger.error(f"❌ Failed to apply crop: {error}")
                 # TODO: Show error to user in UI

         except Exception as e:
             self.logger.error(f"Error applying crop edit: {e}")
             import traceback
             self.logger.error(traceback.format_exc())
     ```

3. **Make _apply_crop_edit async-safe**
   - Since message handler is synchronous but _apply_crop_edit is async:
     ```python
     def _handle_crop_edit_message(self, message_body: str):
         # ... parse message ...

         # Schedule async task
         import asyncio
         asyncio.create_task(self._apply_crop_edit(item_id, step_index, crop_data['box']))
     ```

**Testing:**
1. Open crop step in preview
2. Draw new crop box
3. Click "Apply Crop"
4. Check console for messages
5. Verify image updates
6. Check JSONL manifest updated
7. Reload item and verify crop persisted

---

### Phase 3: Implement Library Backend Integration (1 session)

**Agent Context:**
"You are integrating crop edits with Fichero's library database. When a user manually adjusts a crop, it must be saved to both the JSONL manifest AND the SQLite database."

**Tasks:**

1. **Enhance RenderContext with library IDs**
   - File: `src/fichero/library/renderers/base_renderer.py`
   - Find: `@dataclass class RenderContext` (around line 20)
   - Add fields:
     ```python
     @dataclass
     class RenderContext:
         # ... existing fields ...

         # Library context for database updates
         collection_id: Optional[str] = None
         processing_result_id: Optional[str] = None
         library_manager: Optional[Any] = None  # Avoid circular import
     ```

2. **Update OutputPane to provide library context**
   - File: `src/fichero/windows/main/views/preview/output_pane.py`
   - In `_apply_crop_edit()`, enhance context creation:
     ```python
     # Get collection ID from item
     item = await self.library_manager.get_item(item_id)
     collection_id = item.collection_id if item else None

     # Get processing result ID from step data
     # (Need to query processing_history for this item)
     processing_results = self.library_manager.storage.get_processing_history(item_id)
     processing_result_id = processing_results[0].id if processing_results else None

     # Create render context with library IDs
     context = step_editor.create_render_context(
         step_data,
         show_metadata=True,
         show_content=True,
         interactive=True
     )
     context.collection_id = collection_id
     context.processing_result_id = processing_result_id
     context.library_manager = self.library_manager
     ```

3. **Implement database update in CropRenderer.apply_json_edits**
   - File: `src/fichero/library/renderers/tool_renderers/crop_renderer.py`
   - After manifest file update (line 372), add:
     ```python
     # Update library database if we have context
     if hasattr(context, 'library_manager') and context.library_manager:
         try:
             await self._update_library_database(context, box, source_file)
         except Exception as db_error:
             logger.error(f"Failed to update library database: {db_error}")
             # Continue anyway - manifest was updated

     logger.info("Manual crop applied successfully")
     return True, None
     ```

4. **Add _update_library_database helper method**
   - File: `src/fichero/library/renderers/tool_renderers/crop_renderer.py`
   - Add new method:
     ```python
     async def _update_library_database(self, context: RenderContext, box: dict, source_file: str):
         """Update library database after manual crop edit"""
         library_manager = context.library_manager

         # Find the ProcessingOutput record for this crop
         if not context.processing_result_id:
             logger.warning("No processing_result_id in context - cannot update database")
             return

         outputs = library_manager.storage.get_processing_outputs(context.processing_result_id)

         # Find the output matching this source file
         crop_output = None
         for output in outputs:
             if output.source_file == source_file:
                 crop_output = output
                 break

         if not crop_output:
             logger.warning(f"Could not find ProcessingOutput for source {source_file}")
             return

         # Update output metadata
         from datetime import datetime
         if not crop_output.metadata:
             crop_output.metadata = {}

         crop_output.metadata.update({
             'crop_manually_edited': True,
             'crop_edited_at': datetime.now().isoformat(),
             'crop_box': box,
             'crop_method': 'manual',
         })
         crop_output.file_modified = datetime.now()

         library_manager.storage.update_processing_output(crop_output)
         logger.info(f"Updated ProcessingOutput {crop_output.id} in database")

         # Add ExtractedMetadata for searchability
         from fichero.library.models import ExtractedMetadata
         import uuid

         metadata = ExtractedMetadata(
             id=str(uuid.uuid4()),
             processing_output_id=crop_output.id,
             collection_id=context.collection_id,
             item_id=context.item_id,
             metadata_type='crop',
             key='manual_box',
             value=json.dumps(box),
             confidence=1.0,
             context='User manually adjusted crop',
             created_at=datetime.now()
         )

         library_manager.storage.add_extracted_metadata(metadata)
         logger.info(f"Added ExtractedMetadata for manual crop")

         # Emit navigation event to refresh UI
         from fichero.shared.navigation.navigation_event_bus import emit_navigation_event
         emit_navigation_event("output_updated", {
             "item_id": context.item_id,
             "step_index": context.step_index,
             "step_name": "crop",
             "collection_id": context.collection_id
         })
     ```

5. **Make apply_json_edits async**
   - File: `src/fichero/library/renderers/tool_renderers/crop_renderer.py`
   - Change signature (line 269):
     ```python
     async def apply_json_edits(
         self,
         context: RenderContext,
         json_data: Dict[str, Any]
     ) -> tuple[bool, Optional[str]]:
     ```
   - Update all renderers' base class to support async:
     ```python
     # In base_renderer.py
     async def apply_json_edits(...):
         # Default implementation
         return False, "Not implemented"
     ```

**Testing:**
1. Apply manual crop
2. Check database:
   ```sql
   SELECT metadata FROM processing_outputs
   WHERE id = '...';
   -- Should contain crop_manually_edited: true

   SELECT * FROM extracted_metadata
   WHERE metadata_type = 'crop' AND key = 'manual_box';
   -- Should have new entry with crop coordinates
   ```
3. Restart app and verify crop persists
4. Check that UI refreshes after edit

---

### Phase 4: Add Crop Settings Editor (2 sessions)

**Agent Context:**
"You are adding a settings panel to the crop renderer so users can adjust crop method, padding, and contour detection template."

**Session 1: Settings UI**

1. **Create crop settings HTML template**
   - File: `src/fichero/library/renderers/html_templates_crop_settings.py` (NEW)
   - Content:
     ```python
     """
     Crop Settings Editor Template

     Provides UI for editing crop method, padding, and contour settings
     """

     def get_crop_settings_panel(current_settings: dict) -> str:
         """Generate HTML for crop settings editor panel

         Args:
             current_settings: Dict with current crop settings
                 {
                     'method': 'auto|yolo|contour|manual',
                     'padding': int,
                     'contour_template': 'auto|dark_background|light_background|...',
                     'contour_settings': {...}
                 }
         """
         method = current_settings.get('method', 'auto')
         padding = current_settings.get('padding', 30)
         template = current_settings.get('contour_template', 'auto')

         return f"""
         <div id="cropSettingsPanel" class="settings-panel">
             <h3>Crop Settings</h3>

             <div class="setting-group">
                 <label for="cropMethod">Detection Method:</label>
                 <select id="cropMethod" onchange="updateCropSettings()">
                     <option value="auto" {'selected' if method == 'auto' else ''}>Auto (YOLO + Contour Fallback)</option>
                     <option value="yolo" {'selected' if method == 'yolo' else ''}>YOLO Only</option>
                     <option value="contour" {'selected' if method == 'contour' else ''}>Contour Detection</option>
                     <option value="manual" {'selected' if method == 'manual' else ''}>Manual (No Auto-Detect)</option>
                 </select>
             </div>

             <div class="setting-group">
                 <label for="cropPadding">Padding: <span id="paddingValue">{padding}</span>px</label>
                 <input type="range" id="cropPadding" min="0" max="100" value="{padding}"
                        oninput="document.getElementById('paddingValue').textContent = this.value; updateCropSettings()">
             </div>

             <div id="contourSettings" class="setting-group" style="display: {'block' if method == 'contour' else 'none'}">
                 <label for="contourTemplate">Contour Template:</label>
                 <select id="contourTemplate" onchange="updateCropSettings()">
                     <option value="auto" {'selected' if template == 'auto' else ''}>Auto-Detect Background</option>
                     <option value="dark_background" {'selected' if template == 'dark_background' else ''}>Dark Background</option>
                     <option value="light_background" {'selected' if template == 'light_background' else ''}>Light Background</option>
                     <option value="edge_detection" {'selected' if template == 'edge_detection' else ''}>Edge Detection</option>
                     <option value="high_contrast" {'selected' if template == 'high_contrast' else ''}>High Contrast</option>
                 </select>
             </div>

             <div class="setting-actions">
                 <button onclick="reprocessWithSettings()">Reprocess with New Settings</button>
                 <button onclick="resetToOriginal()">Reset to Original</button>
             </div>
         </div>

         <style>
             .settings-panel {{
                 background: #f5f5f5;
                 border: 1px solid #ccc;
                 border-radius: 4px;
                 padding: 15px;
                 margin: 10px 0;
             }}
             .setting-group {{
                 margin: 10px 0;
             }}
             .setting-group label {{
                 display: block;
                 font-weight: bold;
                 margin-bottom: 5px;
             }}
             .setting-group select,
             .setting-group input[type="range"] {{
                 width: 100%;
             }}
             .setting-actions {{
                 margin-top: 15px;
                 display: flex;
                 gap: 10px;
             }}
             .setting-actions button {{
                 flex: 1;
                 padding: 8px;
                 background: #4CAF50;
                 color: white;
                 border: none;
                 border-radius: 4px;
                 cursor: pointer;
             }}
             .setting-actions button:hover {{
                 background: #45a049;
             }}
         </style>

         <script>
         function updateCropSettings() {{
             const method = document.getElementById('cropMethod').value;
             const contourPanel = document.getElementById('contourSettings');

             // Show/hide contour settings based on method
             contourPanel.style.display = (method === 'contour') ? 'block' : 'none';
         }}

         function reprocessWithSettings() {{
             const settings = {{
                 method: document.getElementById('cropMethod').value,
                 padding: parseInt(document.getElementById('cropPadding').value),
                 contour_template: document.getElementById('contourTemplate').value
             }};

             console.log('Reprocessing with settings:', settings);

             // Send to Python
             if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.cropSettings) {{
                 window.webkit.messageHandlers.cropSettings.postMessage(JSON.stringify({{
                     action: 'reprocess',
                     settings: settings,
                     item_id: '{{item_id}}',
                     step_index: {{step_index}}
                 }}));
             }} else {{
                 alert('Settings updated:\\n' + JSON.stringify(settings, null, 2));
             }}
         }}

         function resetToOriginal() {{
             if (confirm('Reset to original auto-detected crop?')) {{
                 if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.cropSettings) {{
                     window.webkit.messageHandlers.cropSettings.postMessage(JSON.stringify({{
                         action: 'reset',
                         item_id: '{{item_id}}',
                         step_index: {{step_index}}
                     }}));
                 }}
             }}
         }}
         </script>
         """
     ```

2. **Integrate settings panel into crop viewer**
   - File: `src/fichero/library/renderers/html_templates_crop.py`
   - Modify `get_rubberband_crop_viewer()`:
     - Add `crop_settings: dict` parameter
     - Import `get_crop_settings_panel`
     - Inject panel HTML above toolbar

**Session 2: Settings Backend**

1. **Add cropSettings message handler**
   - File: `src/fichero/windows/main/views/preview/output_pane.py`
   - Similar to cropEdit handler, add in `_setup_click_detection()`:
     ```python
     # Add crop settings handler
     self._settings_handler = CropSettingsHandler.alloc().init()
     self._settings_handler.pane = self
     user_content_controller.addScriptMessageHandler(
         self._settings_handler,
         name='cropSettings'
     )
     ```

2. **Implement reprocess with settings**
   - File: `src/fichero/library/renderers/tool_renderers/crop_renderer.py`
   - Add method:
     ```python
     async def reprocess_with_settings(
         self,
         context: RenderContext,
         settings: Dict[str, Any]
     ) -> tuple[bool, Optional[str]]:
         """Reprocess crop with new settings

         Args:
             context: Render context
             settings: New crop settings dict

         Returns:
             (success, error_message)
         """
         try:
             # Get source image
             source_file = context.manifest_entry.get('source', '')
             item_dir = context.file_path.parent.parent.parent
             source_path = self._find_source_image(item_dir, source_file)

             if not source_path:
                 return False, f"Source image not found: {source_file}"

             # Load source image
             from PIL import Image
             img = Image.open(source_path)

             # Apply crop with new settings
             from fichero.tools.crop import crop_with_contours, crop_with_yolo, ContourSettings

             method = settings.get('method', 'auto')

             if method == 'yolo':
                 result = crop_with_yolo(img, {}, conf_threshold=0.35)
             elif method == 'contour':
                 # Build ContourSettings from template
                 template = settings.get('contour_template', 'auto')
                 from fichero.tools.crop import get_contour_template
                 template_data = get_contour_template(template)
                 contour_settings = template_data['settings']
                 contour_settings.padding = settings.get('padding', 30)

                 result = crop_with_contours(img, {}, settings=contour_settings)
             else:
                 return False, f"Cannot reprocess with method: {method}"

             if not result:
                 return False, "Crop detection failed with new settings"

             cropped_img, crop_info = result

             # Save new cropped image
             output_path = context.file_path
             cropped_img.save(output_path, quality=95)

             # Update manifest
             await self._update_manifest_with_crop_info(
                 context,
                 crop_info,
                 source_file
             )

             # Update database
             if hasattr(context, 'library_manager') and context.library_manager:
                 await self._update_library_database(
                     context,
                     crop_info['box'],
                     source_file
                 )

             logger.info(f"Reprocessed crop with settings: {settings}")
             return True, None

         except Exception as e:
             logger.error(f"Error reprocessing crop: {e}")
             import traceback
             logger.error(traceback.format_exc())
             return False, str(e)
     ```

**Testing:**
1. Open crop settings panel
2. Change method to "Contour"
3. Select "Dark Background" template
4. Adjust padding
5. Click "Reprocess"
6. Verify new crop applied
7. Check manifest shows new settings
8. Restart and verify persistence

---

### Phase 5: Add Manual Crop Tool Function (1 session)

**Agent Context:**
"You are adding a manual crop function to the crop tool so it can crop a single image with user-provided coordinates, bypassing YOLO/contour detection."

**Tasks:**

1. **Add crop_with_manual_box function**
   - File: `src/fichero/tools/crop.py`
   - Add after `crop_with_fallback()` (line 489):
     ```python
     def crop_with_manual_box(
         image: Image.Image,
         box: Dict[str, int],
         padding: int = 0,
         metadata: dict = None
     ) -> Tuple[Image.Image, Dict[str, Any]]:
         """Crop image using manually specified box coordinates

         Args:
             image: PIL Image to crop
             box: Crop box with {x1, y1, x2, y2} coordinates
             padding: Additional padding to add around box
             metadata: Optional metadata dict

         Returns:
             Tuple of (cropped_image, crop_info)
         """
         try:
             # Apply EXIF rotation first
             image, rotation_details = apply_exif_rotation(image)
             orig_width, orig_height = image.size

             # Extract box coordinates
             x1 = box.get('x1', 0)
             y1 = box.get('y1', 0)
             x2 = box.get('x2', orig_width)
             y2 = box.get('y2', orig_height)

             # Validate coordinates
             if x1 < 0 or y1 < 0:
                 raise ValueError(f"Crop coordinates must be non-negative: x1={x1}, y1={y1}")
             if x2 > orig_width or y2 > orig_height:
                 raise ValueError(f"Crop box exceeds image dimensions ({orig_width}x{orig_height}): x2={x2}, y2={y2}")
             if x2 <= x1 or y2 <= y1:
                 raise ValueError(f"Crop box must have positive area: x1={x1}, y1={y1}, x2={x2}, y2={y2}")

             # Apply padding
             if padding > 0:
                 x1 = max(0, x1 - padding)
                 y1 = max(0, y1 - padding)
                 x2 = min(orig_width, x2 + padding)
                 y2 = min(orig_height, y2 + padding)

             # Crop the image using PIL
             cropped = image.crop((x1, y1, x2, y2))

             # Create crop info
             crop_info = create_crop_info(
                 box={"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                 method="manual",
                 confidence=1.0,
                 padding=padding,
                 original_size=[orig_width, orig_height],
                 cropped_size=[x2 - x1, y2 - y1],
                 rotation=rotation_details
             )

             tool_logger.info(f"Manual crop successful: {x1},{y1} -> {x2},{y2}")
             return cropped, crop_info

         except Exception as e:
             tool_logger.error(f"Manual crop failed: {e}")
             raise
     ```

2. **Export function in __init__.py**
   - File: `src/fichero/tools/__init__.py`
   - Add to exports:
     ```python
     from .crop import crop_batch, crop_with_manual_box
     ```

3. **Update CropRenderer to use manual crop function**
   - File: `src/fichero/library/renderers/tool_renderers/crop_renderer.py`
   - In `apply_json_edits()`, replace PIL crop code (lines 323-340) with:
     ```python
     from fichero.tools.crop import crop_with_manual_box

     # Load original image
     logger.info(f"Loading original image from: {source_path}")
     from PIL import Image
     img = Image.open(source_path)

     # Get box from json_data
     details = json_data.get('details', {})
     box = details.get('box', {})
     padding = details.get('padding', 0)

     # Crop using tool function
     cropped_img, crop_info = crop_with_manual_box(
         image=img,
         box=box,
         padding=padding,
         metadata={}
     )

     # Save cropped image
     output_path = context.file_path
     logger.info(f"Saving cropped image to: {output_path}")

     ext = output_path.suffix.lower()
     if ext in ['.jpg', '.jpeg']:
         cropped_img.save(output_path, 'JPEG', quality=95)
     elif ext == '.png':
         cropped_img.save(output_path, 'PNG')
     elif ext in ['.tif', '.tiff']:
         cropped_img.save(output_path, 'TIFF')
     else:
         cropped_img.save(output_path)
     ```

**Testing:**
```python
# Unit test for manual crop
from PIL import Image
from fichero.tools.crop import crop_with_manual_box

# Create test image
img = Image.new('RGB', (1000, 800), color='white')

# Manual crop
box = {'x1': 100, 'y1': 50, 'x2': 900, 'y2': 750}
cropped, info = crop_with_manual_box(img, box, padding=10)

assert cropped.size == (820, 720)  # 800+20 x 700+20
assert info['method'] == 'manual'
assert info['confidence'] == 1.0
```

---

### Phase 6: Integration Testing & Documentation (1 session)

**Agent Context:**
"You are performing end-to-end integration testing of the interactive crop feature and documenting the complete workflow."

**Tasks:**

1. **Create integration test script**
   - File: `tests/test_crop_integration.py` (NEW)
   - Test full workflow:
     ```python
     """
     Integration test for interactive crop editing

     Tests the complete flow:
     1. Load item with crop step
     2. Simulate HTML viewer sending crop edit
     3. Verify manifest updated
     4. Verify database updated
     5. Verify persistence across reload
     """

     import pytest
     import json
     from pathlib import Path
     from fichero.library.library_manager import LibraryManager
     from fichero.library.renderers.tool_renderers.crop_renderer import CropRenderer
     from fichero.library.renderers.base_renderer import RenderContext

     @pytest.mark.asyncio
     async def test_manual_crop_full_workflow(tmp_path, library_manager):
         # Create test collection and item
         collection_id = await library_manager.add_collection(
             name="Test Crop Collection",
             collection_type="local"
         )

         # Add test image
         # (setup code here)

         # Simulate crop edit from HTML
         renderer = CropRenderer()
         context = RenderContext(
             item_id=item_id,
             step_index=1,
             step_name="crop",
             tool_name="crop",
             file_path=cropped_path,
             file_type="image",
             manifest_entry=manifest_entry,
             collection_id=collection_id,
             processing_result_id=result_id,
             library_manager=library_manager
         )

         json_data = {
             'details': {
                 'box': {'x1': 150, 'y1': 100, 'x2': 850, 'y2': 700}
             },
             'source': 'test.jpg'
         }

         # Apply edit
         success, error = await renderer.apply_json_edits(context, json_data)

         assert success, f"Crop edit failed: {error}"

         # Verify manifest updated
         manifest_path = cropped_path.parent / "crop_manifest.jsonl"
         with open(manifest_path) as f:
             entries = [json.loads(line) for line in f if line.strip()]

         assert any(
             e['details']['box'] == {'x1': 150, 'y1': 100, 'x2': 850, 'y2': 700}
             for e in entries
         ), "Manifest not updated"

         # Verify database updated
         outputs = library_manager.storage.get_processing_outputs(result_id)
         crop_output = next(
             (o for o in outputs if o.source_file == 'test.jpg'),
             None
         )

         assert crop_output is not None
         assert crop_output.metadata.get('crop_manually_edited') == True

         # Verify metadata searchable
         metadata_records = library_manager.storage.search_metadata(
             collection_id,
             query='150',
             metadata_type='crop',
             key='manual_box'
         )

         assert len(metadata_records) > 0
     ```

2. **Document crop workflow**
   - File: `/Users/dtubb/code/fichero_main/fichero/docs/crop_tool_usage.md` (NEW)
   - Content:
     ```markdown
     # Crop Tool Usage Guide

     ## Interactive Crop Editing

     ### Overview
     The crop tool supports both automatic detection (YOLO/contour) and manual adjustment
     via an interactive HTML viewer.

     ### Workflow

     1. **Automatic Crop**
        - Select item in library
        - Process with crop step
        - Tool auto-detects document boundaries
        - Saves crop to JSONL and database

     2. **Manual Adjustment**
        - Click crop step in preview pane
        - HTML viewer shows original image with current crop
        - Drag to draw new crop box
        - Resize handles to adjust
        - Click "Apply Crop" to save

     3. **Settings Adjustment**
        - Open crop settings panel
        - Change detection method (YOLO/Contour/Manual)
        - Adjust padding
        - Select contour template
        - Click "Reprocess" to re-run crop with new settings

     ### Data Persistence

     Crop data is saved in three locations:

     1. **Cropped Image File**
        - Location: `{item}/assets/cropped/{filename}`
        - Format: JPG/PNG/TIFF

     2. **JSONL Manifest**
        - Location: `{item}/assets/cropped/crop_manifest.jsonl`
        - Fields: `box`, `method`, `padding`, `confidence`, `contour_settings`

     3. **SQLite Database**
        - Table: `processing_outputs`
        - Metadata: `crop_manually_edited`, `crop_box`, `crop_method`
        - Table: `extracted_metadata`
        - Searchable: Crop coordinates, method, confidence

     ### Coordinate System

     All crop boxes use absolute pixel coordinates:
     ```json
     {
       "box": {
         "x1": 100,  // Left edge
         "y1": 50,   // Top edge
         "x2": 900,  // Right edge
         "y2": 650   // Bottom edge
       }
     }
     ```

     Width = x2 - x1
     Height = y2 - y1

     ### API Reference

     **Manual Crop Function:**
     ```python
     from fichero.tools.crop import crop_with_manual_box
     from PIL import Image

     img = Image.open('input.jpg')
     cropped, crop_info = crop_with_manual_box(
         image=img,
         box={'x1': 100, 'y1': 50, 'x2': 900, 'y2': 650},
         padding=10
     )
     cropped.save('output.jpg')
     ```

     **Apply Crop Edit:**
     ```python
     renderer = CropRenderer()
     context = RenderContext(...)
     json_data = {
         'details': {
             'box': {'x1': 100, 'y1': 50, 'x2': 900, 'y2': 650}
         },
         'source': 'original.jpg'
     }
     success, error = await renderer.apply_json_edits(context, json_data)
     ```

     ### Troubleshooting

     **Crop not saving:**
     - Check browser console for JavaScript errors
     - Verify message handler registered (look for log: "Crop edit handler registered")
     - Check Python logs for "Received crop edit" message

     **Source image not found:**
     - Check that source path in manifest matches actual file location
     - Verify item directory structure: `{item}/assets/original/` or `{item}/documents/`

     **Database not updating:**
     - Verify `processing_result_id` in RenderContext
     - Check that `library_manager` is passed in context
     - Look for database errors in logs
     ```

3. **Update main README with crop feature**
   - File: `/Users/dtubb/code/fichero_main/fichero/CLAUDE.md`
   - Add section about interactive crop editing

4. **Create migration script for existing crops**
   - File: `scripts/migrate_crop_metadata.py` (NEW)
   - Backfill `processing_outputs` metadata for existing crops

**Testing Checklist:**
- [ ] Load item with existing crop
- [ ] Draw new crop box in HTML viewer
- [ ] Click "Apply Crop"
- [ ] Verify image updates in viewer
- [ ] Verify manifest file updated
- [ ] Check database record updated
- [ ] Restart app
- [ ] Verify crop persists
- [ ] Test with different image formats (JPG, PNG, TIFF)
- [ ] Test boundary conditions (crop at image edge)
- [ ] Test invalid coordinates (error handling)
- [ ] Test settings panel (change method/padding)
- [ ] Test reprocess with new settings
- [ ] Test reset to original

---

## Part 5: Reference Patterns

### Pattern 1: JavaScript-to-Python Message Passing

**File:** `src/fichero/windows/main/views/preview/output_pane.py` (lines 227-249)

```python
# 1. Define message handler class
class ScriptMessageHandler(NSObject):
    pane = None

    @objc_method
    def userContentController_didReceiveScriptMessage_(self, controller, message):
        # Parse message
        data = json.loads(str(message.body))
        # Handle action
        self.pane.handle_action(data)

# 2. Register handler with WebView
handler = ScriptMessageHandler.alloc().init()
handler.pane = self
native_webview.configuration.userContentController.addScriptMessageHandler(
    handler,
    name='messageHandlerName'
)

# 3. JavaScript sends message
# window.webkit.messageHandlers.messageHandlerName.postMessage(JSON.stringify(data))
```

### Pattern 2: Manifest Update Flow

**File:** `src/fichero/library/step_editor.py` (lines 270-330)

```python
# 1. Read manifest
entries = []
with open(manifest_path, 'r') as f:
    for line in f:
        if line.strip():
            entries.append(json.loads(line))

# 2. Find and update entry
for entry in entries:
    if entry.get('file') == target_file:
        entry['details'].update(new_data)
        break

# 3. Backup original
backup_path = manifest_path.with_suffix('.jsonl.backup')
shutil.copy2(manifest_path, backup_path)

# 4. Write atomically
temp_path = manifest_path.with_suffix('.tmp')
with open(temp_path, 'w') as f:
    for entry in entries:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
temp_path.replace(manifest_path)
```

### Pattern 3: Library Database Update

**File:** `src/fichero/library/storage.py` (lines 1057-1081)

```python
# 1. Get existing record
output = self.storage.get_processing_outputs(result_id)[0]

# 2. Update fields
output.metadata['new_field'] = value
output.file_modified = datetime.now()

# 3. Save to database
self.storage.update_processing_output(output)

# 4. Add searchable metadata
metadata = ExtractedMetadata(
    id=str(uuid.uuid4()),
    processing_output_id=output.id,
    collection_id=collection_id,
    item_id=item_id,
    metadata_type='crop',
    key='manual_box',
    value=json.dumps(box),
    confidence=1.0,
    created_at=datetime.now()
)
self.storage.add_extracted_metadata(metadata)
```

### Pattern 4: Renderer Integration

**File:** `src/fichero/library/renderers/tool_renderers/rotate_renderer.py` (lines 140-254)

```python
class ToolRenderer(ImageRenderer):
    def get_editable_json(self, context):
        # Extract only editable fields
        return {
            'field1': context.manifest_entry.get('field1'),
            'field2': context.manifest_entry.get('field2'),
        }

    def validate_json(self, json_data):
        # Validate edits
        if 'field1' not in json_data:
            return False, "Missing field1"
        return True, None

    async def apply_json_edits(self, context, json_data):
        # 1. Validate
        is_valid, error = self.validate_json(json_data)
        if not is_valid:
            return False, error

        # 2. Process data
        result = await self._process(context, json_data)

        # 3. Update manifest
        await self._update_manifest(context, result)

        # 4. Update database
        if hasattr(context, 'library_manager'):
            await self._update_database(context, result)

        return True, None
```

---

## Conclusion

The crop tool is a solid batch processing system but needs significant work to support interactive editing. The architecture is sound - the missing pieces are:

1. **JavaScript bridge** to send crop edits from HTML to Python
2. **Database integration** to persist edits beyond JSONL manifests
3. **Settings UI** to adjust crop parameters
4. **Manual crop function** in the tool itself

All required patterns exist elsewhere in the codebase (OutputPane, StepEditor, RotateRenderer). The implementation is straightforward following the 6-phase plan.

**Estimated Effort:**
- Phase 1 (Bug fixes): 2-3 hours
- Phase 2 (Interactive crop): 4-6 hours
- Phase 3 (Database integration): 2-3 hours
- Phase 4 (Settings editor): 4-5 hours
- Phase 5 (Manual crop tool): 2 hours
- Phase 6 (Testing/docs): 3-4 hours

**Total: 17-23 hours** across 6 implementation sessions.
