# Renderer Test Plan

## Overview

This document provides step-by-step test plans for each renderer in the Fichero renderer system.
Each test plan covers CLI rendering, HTML rendering, JSON editing, and UI integration.

## Test Environment Setup

### Prerequisites
```bash
# 1. Navigate to project directory
cd /Users/dtubb/code/fichero_main/fichero

# 2. Ensure virtual environment is activated
source .venv/bin/activate

# 3. Run a simple crop workflow to generate test data
briefcase dev -- process /path/to/test/image.jpg /path/to/output --plan "Simple Crop" --workflow "Crop Only"
```

### Test Data Locations

After running workflows, test data will be available at:
```
~/Library/Application Support/ca.tubb.fichero/library/collections/<collection-id>/outputs/<timestamp>/<item-name>/
```

## Priority 1: Core Image Processing Renderers

### Test 1: CropRenderer

**Status**: ✅ Implemented and tested

**Test Data**: Run crop workflow first
```bash
briefcase dev -- process /path/to/test/image.jpg /path/to/output --plan "Crop Test" --workflow "CropWorkflow"
```

**CLI Test**:
```python
python test_renderer.py  # Will run test_crop_renderer_cli()
```

**Expected CLI Output**:
```
Step 1: crop
============================================================

File: /path/to/cropped/image.jpg
Type: image

Crop Parameters:
  Crop Box: x=100, y=50, width=800, height=600
  Padding: 30px
  Method: contour
  Template: auto
```

**HTML Test**:
```python
python test_renderer.py  # Will run test_crop_renderer_html()
```

**Expected HTML Features**:
- ✅ Interactive image viewer with zoom controls
- ✅ Rotation controls
- ✅ Base64-encoded image data (no file:// URLs)
- ✅ Responsive layout

**JSON Editing Test**:
1. Open Fichero GUI
2. Navigate to Library → Collections → CropTest
3. Click on processed item
4. View crop step
5. Click "Edit" button
6. Verify JSON editor shows:
   ```json
   {
     "crop_box": {
       "x": 100,
       "y": 50,
       "width": 800,
       "height": 600
     },
     "padding": 30,
     "method": "contour",
     "template": "auto"
   }
   ```
7. Edit values and click "Save"
8. Verify validation works (e.g., negative values rejected)

**Pass Criteria**:
- ✅ CLI output matches expected format
- ✅ HTML renders correctly with interactive viewer
- ✅ JSON editor shows editable parameters
- ✅ Validation catches invalid inputs
- ✅ CropRenderer is used (check logs for "Using renderer: CropRenderer")

---

### Test 2: RotateRenderer

**Status**: ✅ Implemented, needs testing

**Test Data**: Run rotate workflow
```bash
# Create test workflow file: rotate_test.yaml
workflows:
  - name: "rotate"
    steps:
      - name: "Rotate 90°"
        tool: "rotate"
        params:
          angle: 90
          direction: "clockwise"
```

**CLI Test**:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.renderers.base_renderer import RenderContext
from fichero.library.renderers.renderer_registry import RendererRegistry

# Create context
context = RenderContext(
    item_id="test-item",
    step_index=1,
    step_name="rotate",
    tool_name="rotate",
    file_path=Path("/path/to/rotated.jpg"),
    file_type="image",
    manifest_entry={
        "path": "rotated/test.jpg",
        "type": "file",
        "rotation_angle": 90,
        "direction": "clockwise"
    },
    show_metadata=True,
    show_content=True,
    interactive=False
)

# Get renderer
renderer = RendererRegistry.get_renderer('rotate')

# Render CLI
output = renderer.render_cli(context)
print(output.text)
```

**Expected CLI Output**:
```
Step 1: rotate
============================================================

File: /path/to/rotated.jpg
Type: image

Rotation Angle: 90°
Direction: clockwise
```

**JSON Parameters**:
```json
{
  "rotation_angle": 90,
  "direction": "clockwise"
}
```

**Validation Tests**:
- ✅ `rotation_angle` must be multiple of 90
- ✅ `direction` must be clockwise/counterclockwise/cw/ccw
- ❌ `rotation_angle: 45` should fail
- ❌ `direction: "invalid"` should fail

**Pass Criteria**:
- ✅ CLI output shows rotation parameters
- ✅ HTML viewer shows rotated image
- ✅ JSON editor allows editing angle and direction
- ✅ Validation rejects invalid angles

---

### Test 3: EnhanceRenderer

**Status**: ✅ Implemented, needs testing

**Test Data**: Run enhance workflow
```bash
# Test with enhance step
briefcase dev -- process /path/to/test/image.jpg /path/to/output --plan "Enhance Test" --workflow "EnhanceWorkflow"
```

**CLI Test Template**:
```python
context = RenderContext(
    item_id="test-item",
    step_index=1,
    step_name="enhance",
    tool_name="enhance",
    file_path=Path("/path/to/enhanced.jpg"),
    file_type="image",
    manifest_entry={
        "path": "enhanced/test.jpg",
        "type": "file",
        "contrast": 1.5,
        "brightness": 1.1,
        "sharpness": 1.2,
        "method": "auto"
    },
    show_metadata=True,
    show_content=True,
    interactive=False
)

renderer = RendererRegistry.get_renderer('enhance')
output = renderer.render_cli(context)
print(output.text)
```

**Expected CLI Output**:
```
Step 1: enhance
============================================================

File: /path/to/enhanced.jpg
Type: image

Enhancement Parameters:
  Contrast: 1.5
  Brightness: 1.1
  Sharpness: 1.2
  Method: auto
```

**JSON Parameters**:
```json
{
  "contrast": 1.5,
  "brightness": 1.1,
  "sharpness": 1.2,
  "method": "auto"
}
```

**Validation Tests**:
- ✅ All parameters must be positive numbers
- ✅ `method` must be 'auto' or 'manual'
- ❌ `contrast: -1.0` should fail
- ❌ `brightness: 0` should fail
- ❌ `method: "invalid"` should fail

**Special UI Features**:
- Compare Before/After button (toggle between original and enhanced)
- Histogram overlay (show brightness/contrast distribution)

**Pass Criteria**:
- ✅ CLI output shows all enhancement parameters
- ✅ HTML viewer shows enhanced image
- ✅ JSON editor allows editing all parameters
- ✅ Validation rejects invalid values

---

### Test 4: RemoveBackgroundRenderer

**Status**: ✅ Implemented, needs testing

**Test Data**: Run remove_background workflow
```bash
# Note: Requires rembg library installed
pip install rembg
```

**CLI Test Template**:
```python
context = RenderContext(
    item_id="test-item",
    step_index=1,
    step_name="remove_background",
    tool_name="remove_background",
    file_path=Path("/path/to/no_bg.png"),
    file_type="image",
    manifest_entry={
        "path": "no_bg/test.png",
        "type": "file",
        "method": "rembg",
        "model": "u2net",
        "alpha_matting": True,
        "alpha_matting_foreground_threshold": 240,
        "alpha_matting_background_threshold": 10
    },
    show_metadata=True,
    show_content=True,
    interactive=False
)

renderer = RendererRegistry.get_renderer('remove_background')
output = renderer.render_cli(context)
print(output.text)
```

**Expected CLI Output**:
```
Step 1: remove_background
============================================================

File: /path/to/no_bg.png
Type: image

Background Removal Parameters:
  Method: rembg
  Model: u2net
  Alpha Matting: True
  Foreground Threshold: 240
  Background Threshold: 10
```

**JSON Parameters**:
```json
{
  "method": "rembg",
  "model": "u2net",
  "alpha_matting": true,
  "alpha_matting_foreground_threshold": 240,
  "alpha_matting_background_threshold": 10
}
```

**Validation Tests**:
- ✅ `method` must be 'rembg' or 'custom'
- ✅ `model` must be valid model name
- ✅ `alpha_matting` must be boolean
- ✅ Thresholds must be 0-255
- ❌ `alpha_matting_foreground_threshold: 300` should fail
- ❌ `model: "invalid_model"` should fail

**Special UI Features**:
- Toggle Background Preview (show checkerboard behind transparent areas)
- Background color picker (preview image on different backgrounds)

**Pass Criteria**:
- ✅ CLI output shows all parameters
- ✅ HTML viewer shows image with transparency
- ✅ JSON editor allows editing all parameters
- ✅ Validation rejects invalid thresholds

---

### Test 5: PrepareImagesRenderer

**Status**: ✅ Implemented, needs testing

**Test Data**: Run prepare_images workflow
```bash
briefcase dev -- process /path/to/test/folder /path/to/output --plan "Prepare Test" --workflow "PrepareWorkflow"
```

**CLI Test Template**:
```python
context = RenderContext(
    item_id="test-item",
    step_index=1,
    step_name="prepare_images",
    tool_name="prepare_images",
    file_path=Path("/path/to/prepared/"),
    file_type="folder",
    manifest_entry={
        "path": "prepared/",
        "type": "folder",
        "resize_mode": "fit",
        "target_size": [1200, 1600],
        "quality": 95,
        "format": "jpg",
        "dpi": 300,
        "processed_count": 50
    },
    show_metadata=True,
    show_content=True,
    interactive=False
)

renderer = RendererRegistry.get_renderer('prepare_images')
output = renderer.render_cli(context)
print(output.text)
```

**Expected CLI Output**:
```
Step 1: prepare_images
============================================================

Folder: /path/to/prepared/
Type: folder

Preparation Parameters:
  Resize Mode: fit
  Target Size: 1200x1600
  Quality: 95
  Format: jpg
  DPI: 300
  Processed: 50 images
```

**JSON Parameters**:
```json
{
  "resize_mode": "fit",
  "target_size": [1200, 1600],
  "quality": 95,
  "format": "jpg",
  "dpi": 300,
  "processed_count": 50
}
```

**Validation Tests**:
- ✅ `resize_mode` must be 'fit', 'fill', or 'exact'
- ✅ `target_size` must be [width, height]
- ✅ `quality` must be 1-100
- ✅ `format` must be 'jpg', 'png', or 'tiff'
- ✅ `dpi` must be positive integer
- ❌ `quality: 150` should fail
- ❌ `target_size: [1200]` should fail

**Special UI Features**:
- Gallery view showing all prepared images
- Thumbnail grid with click-to-enlarge
- Batch settings editor

**Pass Criteria**:
- ✅ CLI output shows all parameters
- ✅ HTML shows gallery of prepared images
- ✅ JSON editor allows editing all parameters
- ✅ Validation rejects invalid values

---

## Integration Testing

### Test: Complete Workflow with All Renderers

1. Create a workflow that uses all 5 renderers:
```yaml
workflows:
  - name: "full_test"
    steps:
      - name: "Prepare"
        tool: "prepare_images"
      - name: "Crop"
        tool: "crop"
      - name: "Enhance"
        tool: "enhance"
      - name: "Rotate"
        tool: "rotate"
      - name: "Remove Background"
        tool: "remove_background"
```

2. Run workflow:
```bash
briefcase dev -- process /path/to/test/folder /path/to/output --plan "Full Test" --workflow "full_test"
```

3. Open Fichero GUI and navigate through all steps

4. Verify:
- ✅ Each step uses correct renderer (check logs)
- ✅ Each step displays correctly in OutputView
- ✅ Edit button shows appropriate JSON for each step
- ✅ Toolbar items are correct for each renderer
- ✅ Navigation between steps works smoothly

---

## Summary Checklist

**Implemented Renderers**:
- ✅ CropRenderer (tested)
- ✅ RotateRenderer (needs testing)
- ✅ EnhanceRenderer (needs testing)
- ✅ RemoveBackgroundRenderer (needs testing)
- ✅ PrepareImagesRenderer (needs testing)

**Next Steps**:
1. Run CLI tests for each renderer
2. Run HTML tests for each renderer
3. Test JSON editing for each renderer
4. Test full workflow integration
5. Document any issues found
6. Create remaining renderers (segment, split, transcribe, etc.)

**Known Issues**:
- Inspector panel visibility (being investigated)
- Toolbar initialization order (fixed)
- `apply_json_edits()` not implemented yet (all renderers have placeholder)

**Future Enhancements**:
- Renderer-specific toolbar actions
- Before/after comparison for enhancement tools
- Gallery view for multi-output tools (segment, split)
- Real-time preview while editing parameters
