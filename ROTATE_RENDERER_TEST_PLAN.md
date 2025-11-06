# RotateRenderer Test Plan

## Overview

This test plan provides step-by-step instructions for testing the RotateRenderer, which handles the `rotate` tool output.

## Prerequisites

1. Fichero application installed and running
2. Test image available (any JPG, PNG, or TIFF file)
3. Terminal access for running workflows

## Test Setup

### Step 1: Prepare Test Data

Create a test image or use an existing one:
```bash
# Use any test image you have
TEST_IMAGE="/path/to/your/test/image.jpg"
OUTPUT_DIR="/path/to/output"
```

### Step 2: Create Rotate Workflow

Create a workflow file that rotates an image:

**File**: `src/fichero/resources/plans/rotate_test.yaml`

```yaml
name: "Rotate Test"
description: "Test workflow for rotating images"

workflows:
  - name: "rotate_only"
    description: "Simple rotation test"
    steps:
      - name: "Rotate 90° Clockwise"
        tool: "rotate"
        params:
          angle: 90
          direction: "clockwise"

  - name: "rotate_180"
    description: "Rotate 180 degrees"
    steps:
      - name: "Rotate 180°"
        tool: "rotate"
        params:
          angle: 180
          direction: "clockwise"

  - name: "rotate_counterclockwise"
    description: "Rotate counter-clockwise"
    steps:
      - name: "Rotate 90° CCW"
        tool: "rotate"
        params:
          angle: 90
          direction: "counterclockwise"
```

## Test 1: CLI Rendering

Test the RotateRenderer in CLI mode to verify text output.

### Run Test

```bash
cd /Users/dtubb/code/fichero_main/fichero
python -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))

from fichero.library.renderers.base_renderer import RenderContext
from fichero.library.renderers.renderer_registry import RendererRegistry

# Create render context for rotate step
context = RenderContext(
    item_id='test-rotate-001',
    step_index=1,
    step_name='rotate',
    tool_name='rotate',
    file_path=Path('/path/to/rotated/image.jpg'),
    file_type='image',
    manifest_entry={
        'path': 'rotated/image.jpg',
        'type': 'file',
        'rotation_angle': 90,
        'direction': 'clockwise'
    },
    show_metadata=True,
    show_content=True,
    interactive=False
)

# Get rotate renderer
renderer = RendererRegistry.get_renderer('rotate')
print(f'Renderer: {renderer.__class__.__name__}')
print()

# Render CLI
output = renderer.render_cli(context)
print(output.text)
"
```

### Expected Output

```
Renderer: RotateRenderer

Step 1: rotate
============================================================

File: /path/to/rotated/image.jpg
Type: image

Rotation Angle: 90°
Direction: clockwise
```

### ✅ Pass Criteria
- Renderer class is `RotateRenderer`
- Step information displays correctly
- Rotation angle shows: `90°`
- Direction shows: `clockwise`

## Test 2: JSON Editing - Get Editable JSON

Test that the renderer provides editable JSON parameters.

### Run Test

```bash
cd /Users/dtubb/code/fichero_main/fichero
python -c "
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))

from fichero.library.renderers.base_renderer import RenderContext
from fichero.library.renderers.renderer_registry import RendererRegistry

context = RenderContext(
    item_id='test-rotate-001',
    step_index=1,
    step_name='rotate',
    tool_name='rotate',
    file_path=Path('/path/to/rotated.jpg'),
    file_type='image',
    manifest_entry={
        'path': 'rotated/image.jpg',
        'type': 'file',
        'rotation_angle': 90,
        'direction': 'clockwise'
    },
    show_metadata=True,
    show_content=True,
    interactive=False
)

renderer = RendererRegistry.get_renderer('rotate')

# Get editable JSON
editable_json = renderer.get_editable_json(context)
print('Editable JSON:')
print(json.dumps(editable_json, indent=2))
"
```

### Expected Output

```
Editable JSON:
{
  "rotation_angle": 90,
  "direction": "clockwise"
}
```

### ✅ Pass Criteria
- JSON contains `rotation_angle` field
- JSON contains `direction` field
- Values match manifest entry

## Test 3: JSON Validation

Test validation of rotation parameters.

### Run Test

```bash
cd /Users/dtubb/code/fichero_main/fichero
python -c "
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))

from fichero.library.renderers.renderer_registry import RendererRegistry

renderer = RendererRegistry.get_renderer('rotate')

# Test valid JSON
test_cases = [
    # Valid cases
    ({'rotation_angle': 90, 'direction': 'clockwise'}, True, 'Valid: 90° clockwise'),
    ({'rotation_angle': 180, 'direction': 'counterclockwise'}, True, 'Valid: 180° CCW'),
    ({'rotation_angle': 270, 'direction': 'cw'}, True, 'Valid: 270° cw'),
    ({'rotation_angle': -90, 'direction': 'clockwise'}, True, 'Valid: -90°'),
    ({'rotation_angle': 360, 'direction': 'clockwise'}, True, 'Valid: 360°'),

    # Invalid cases
    ({'rotation_angle': 45, 'direction': 'clockwise'}, False, 'Invalid: 45° (not multiple of 90)'),
    ({'rotation_angle': 90, 'direction': 'invalid'}, False, 'Invalid: bad direction'),
    ({'rotation_angle': 'ninety', 'direction': 'clockwise'}, False, 'Invalid: string angle'),
]

print('Validation Tests:')
print('=' * 70)
for json_data, should_pass, description in test_cases:
    is_valid, error = renderer.validate_json(json_data)

    if should_pass and is_valid:
        print(f'✅ {description}')
    elif not should_pass and not is_valid:
        print(f'✅ {description}')
        print(f'   Error: {error}')
    else:
        print(f'❌ {description}')
        if error:
            print(f'   Unexpected error: {error}')
"
```

### Expected Output

```
Validation Tests:
======================================================================
✅ Valid: 90° clockwise
✅ Valid: 180° CCW
✅ Valid: 270° cw
✅ Valid: -90°
✅ Valid: 360°
✅ Invalid: 45° (not multiple of 90)
   Error: rotation_angle must be a multiple of 90, got 45
✅ Invalid: bad direction
   Error: direction must be one of ['clockwise', 'counterclockwise', 'cw', 'ccw'], got 'invalid'
✅ Invalid: string angle
   Error: rotation_angle must be a number, got str
```

### ✅ Pass Criteria
- All valid cases pass validation
- All invalid cases fail validation
- Error messages are clear and helpful
- Angle must be multiple of 90
- Direction must be valid value

## Test 4: Run Actual Rotate Workflow

Test the complete workflow with actual image rotation.

### Run Workflow

```bash
cd /Users/dtubb/code/fichero_main/fichero

# Process an image with rotation
briefcase dev -- process "$TEST_IMAGE" "$OUTPUT_DIR" \
    --plan "Rotate Test" \
    --workflow "rotate_only"
```

### Expected Behavior

1. **Processing Output:**
   ```
   Processing: /path/to/test/image.jpg
   Running workflow: rotate_only
   Step 1/1: Rotate 90° Clockwise
   ✅ Completed
   ```

2. **Output Files:**
   - Rotated image created in output directory
   - Manifest file created with rotation metadata

3. **Check Output:**
   ```bash
   # Find the rotated image
   find "$OUTPUT_DIR" -name "*.jpg" -o -name "*.png"

   # Check the manifest
   find "$OUTPUT_DIR" -name "*.jsonl" -exec cat {} \;
   ```

### ✅ Pass Criteria
- Workflow completes without errors
- Rotated image is created
- Image is actually rotated 90° clockwise
- Manifest contains rotation metadata

## Test 5: GUI Display

Test the RotateRenderer in the GUI.

### Steps

1. **Launch Fichero GUI:**
   ```bash
   briefcase dev
   ```

2. **Navigate to Output:**
   - Click on **Library** tab
   - Find the collection from the rotate workflow
   - Click on the processed item
   - View should show the rotated image

3. **Verify Display:**
   - Check that image displays in OutputView
   - Image should be rotated correctly
   - Zoom controls should work
   - Rotation controls should work

4. **Check Logs:**
   Look for these log messages:
   ```
   INFO - Using tool-specific renderer for rotate: RotateRenderer
   INFO - Using renderer: RotateRenderer for tool 'rotate'
   DEBUG - HTML content length: XXXXX bytes
   ```

### ✅ Pass Criteria
- RotateRenderer is used (check logs)
- Image displays correctly
- Image is visually rotated
- Interactive controls work (zoom, pan)

## Test 6: HTML Rendering

Test the HTML output of the renderer.

### Run Test

```bash
cd /Users/dtubb/code/fichero_main/fichero
python -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))

from fichero.library.renderers.base_renderer import RenderContext
from fichero.library.renderers.renderer_registry import RendererRegistry

# Use actual rotated image path from workflow output
context = RenderContext(
    item_id='test-rotate-001',
    step_index=1,
    step_name='rotate',
    tool_name='rotate',
    file_path=Path('$OUTPUT_DIR/path/to/rotated/image.jpg'),  # Update with actual path
    file_type='image',
    manifest_entry={
        'path': 'rotated/image.jpg',
        'type': 'file',
        'rotation_angle': 90,
        'direction': 'clockwise'
    },
    show_metadata=True,
    show_content=True,
    interactive=True  # GUI mode
)

renderer = RendererRegistry.get_renderer('rotate')

# Render HTML
output = renderer.render_html(context)

# Check HTML content
print(f'HTML Output: {len(output.html)} bytes')
print(f'Title: {output.title}')
print(f'Description: {output.description}')
print()

# Check for expected elements
checks = [
    ('<!DOCTYPE html>', 'DOCTYPE declaration'),
    ('<html>', 'HTML tag'),
    ('function zoomIn()', 'Zoom in function'),
    ('function zoomOut()', 'Zoom out function'),
    ('function rotateLeft()', 'Rotate left function'),
    ('function rotateRight()', 'Rotate right function'),
]

print('HTML Element Checks:')
for check_str, check_name in checks:
    if check_str in output.html:
        print(f'  ✅ {check_name} found')
    else:
        print(f'  ❌ {check_name} NOT found')
"
```

### Expected Output

```
HTML Output: XXXXX bytes
Title: rotate
Description: Image: filename.jpg

HTML Element Checks:
  ✅ DOCTYPE declaration found
  ✅ HTML tag found
  ✅ Zoom in function found
  ✅ Zoom out function found
  ✅ Rotate left function found
  ✅ Rotate right function found
```

### ✅ Pass Criteria
- HTML is generated (non-zero bytes)
- All expected HTML elements present
- Interactive functions included
- Uses base64 image data (secure)

## Test 7: Multiple Rotation Angles

Test different rotation angles.

### Test Cases

Run workflows with different angles:

```bash
# Test 180° rotation
briefcase dev -- process "$TEST_IMAGE" "$OUTPUT_DIR/test180" \
    --plan "Rotate Test" \
    --workflow "rotate_180"

# Test counter-clockwise
briefcase dev -- process "$TEST_IMAGE" "$OUTPUT_DIR/testccw" \
    --plan "Rotate Test" \
    --workflow "rotate_counterclockwise"
```

### Verify

For each test:
1. Check output image is rotated correctly
2. Verify manifest has correct angle
3. View in GUI and verify display

### ✅ Pass Criteria
- 90° clockwise: Image rotated 90° right
- 180°: Image upside down
- 90° CCW: Image rotated 90° left
- All display correctly in GUI

## Test 8: Inspector Panel (JSON Editor)

Test the JSON editor integration.

### Steps

1. **Open GUI and navigate to rotated image**

2. **Click "Edit" button**
   - Inspector panel should slide in from right
   - JSON editor should show rotation parameters

3. **Expected JSON in Editor:**
   ```json
   {
     "rotation_angle": 90,
     "direction": "clockwise"
   }
   ```

4. **Edit Values:**
   - Change `rotation_angle` to `180`
   - Click "Save"

5. **Verify Validation:**
   - Try invalid angle (e.g., `45`)
   - Should show error: "rotation_angle must be a multiple of 90"

### ✅ Pass Criteria
- Inspector panel appears on Edit click
- JSON shows current rotation parameters
- Can edit values
- Validation prevents invalid values
- Error messages are clear

## Summary Checklist

| Test | Description | Status |
|------|-------------|--------|
| 1 | CLI Rendering | ⬜ |
| 2 | Get Editable JSON | ⬜ |
| 3 | JSON Validation | ⬜ |
| 4 | Run Workflow | ⬜ |
| 5 | GUI Display | ⬜ |
| 6 | HTML Rendering | ⬜ |
| 7 | Multiple Angles | ⬜ |
| 8 | Inspector Panel | ⬜ |

## Common Issues and Solutions

### Issue: Renderer not found
**Solution**: Verify RendererRegistry has loaded renderers:
```bash
python -c "from fichero.library.renderers.renderer_registry import RendererRegistry; print(RendererRegistry.list_registered_tools())"
```

### Issue: Image not rotating
**Solution**: Check rotate tool is working:
```bash
# Test rotate tool directly
python -m fichero.tools.rotate --help
```

### Issue: Inspector not showing
**Solution**: Check OutputView logs for toolbar/inspector errors:
```bash
briefcase dev 2>&1 | grep -i "inspector\|edit\|toolbar"
```

## Expected Files After Testing

After running all tests, you should have:

```
$OUTPUT_DIR/
├── test_rotate_90/
│   └── [collection]/
│       └── outputs/
│           └── [timestamp]/
│               └── [filename]/
│                   ├── rotated/
│                   │   └── [filename].jpg  # Rotated 90° CW
│                   └── manifest.jsonl
├── test180/
│   └── ...  # Rotated 180°
└── testccw/
    └── ...  # Rotated 90° CCW
```

## Next Steps

After completing these tests:

1. ✅ Verify all tests pass
2. 📝 Document any issues found
3. 🔧 Fix any bugs discovered
4. 🎯 Test other renderers using similar plans
5. 🚀 Move on to testing enhance, split, segment, etc.

## Notes

- The RotateRenderer extends ImageRenderer, so it inherits all image display functionality
- Rotation is typically done in 90° increments (90, 180, 270)
- Both positive and negative angles are supported
- Direction can be specified as 'clockwise', 'counterclockwise', 'cw', or 'ccw'
- The renderer validates angles are multiples of 90
