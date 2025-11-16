# Interactive Crop Editor - User Guide

**Last Updated:** November 15, 2025

---

## Overview

The Interactive Crop Editor allows you to manually adjust crop boxes on your scanned documents directly within the Fichero preview pane. Instead of reprocessing images, you can fine-tune crops with an intuitive visual interface.

---

## Opening the Crop Editor

1. **Navigate to your library**
   - Click the Library button in the sidebar
   - Select a collection

2. **Select an item**
   - Click on any item that has been processed with the crop tool

3. **View the crop step**
   - In the Step Browser (right sidebar), click on the "crop" step
   - The interactive crop editor will load automatically

---

## Using the Crop Editor

### Visual Interface

When the crop editor loads, you'll see:

- **Original Image:** The unprocessed source image
- **Gray Dashed Box:** The current crop (from automatic detection)
- **Green Solid Box:** Your new crop selection (when drawing)
- **Resize Handles:** 8 green circles on the selection box for precise adjustment
- **Toolbar:** Coordinate display and action buttons at the bottom

### Drawing a New Crop

**Method 1: Drag to Create**
1. Click and drag anywhere on the image
2. A green box will appear as you drag
3. Release to complete the selection

**Method 2: Resize Existing**
1. If a selection already exists, grab any of the 8 handles
2. Drag to resize in that direction
3. Release when satisfied

### Moving the Crop

1. Click inside the green selection box
2. Drag to move the entire box
3. The box will stay within image boundaries

### Navigation Controls

- **Pan:** Hold Space, then click and drag
- **Zoom:** Use mousewheel up/down
- **Fit to Window:** Double-click the image (planned feature)

### Coordinate Display

The bottom toolbar shows:
- Current selection coordinates: `x1, y1, x2, y2`
- Selection dimensions: `width × height`

Example: `x1=100, y1=50, x2=900, y2=750 | 800×700`

---

## Saving Your Changes

### Apply Crop

1. Click the **"Apply Crop"** button (green)
2. The button will briefly show "Saved!" confirmation
3. The image will reload with your new crop
4. Changes are saved to both:
   - JSONL manifest file (for processing history)
   - SQLite database (for searchability)

### Clear Selection

1. Click the **"Clear"** button (gray)
2. Your current selection will be removed
3. You can draw a new one

---

## Tips and Best Practices

### Getting the Best Crop

1. **Start with automatic crop**
   - The gray dashed box shows what automatic detection found
   - Use this as a starting point

2. **Leave padding**
   - Don't crop too tightly to the content
   - Leave 10-30 pixels of margin to avoid clipping

3. **Check all corners**
   - Ensure the crop includes all important content
   - Zoom in to verify edges

### Common Use Cases

**Fixing Over-Cropping**
If automatic detection cut off content:
1. Drag from the gray box outward
2. Expand to include missing areas
3. Apply the crop

**Removing Margins**
If automatic detection left too much border:
1. Start inside the gray box
2. Draw a tighter crop
3. Apply the crop

**Correcting Skewed Crops**
For documents that weren't detected correctly:
1. Clear any existing selection
2. Draw a new crop from scratch
3. Align with the actual document edges
4. Apply the crop

---

## Keyboard Shortcuts (Planned)

The following shortcuts are planned for future releases:

- **Enter:** Apply crop and save
- **Escape:** Clear current selection
- **Space + Drag:** Pan the image (already implemented)
- **Arrow Keys:** Nudge selection by 1 pixel
- **Shift + Arrow Keys:** Nudge by 10 pixels
- **Cmd + Z:** Undo last change

---

## Troubleshooting

### "The image doesn't load"

**Cause:** Source image file may have been moved or deleted

**Solution:**
1. Check that original documents are in the collection
2. Verify the item's source path in the library
3. Re-import the document if necessary

### "Apply Crop button is disabled"

**Cause:** No selection has been made yet

**Solution:**
1. Draw a crop box by dragging on the image
2. The button will enable once you have a selection

### "Changes don't persist after restarting"

**Cause:** Database may not be saving correctly

**Solution:**
1. Check logs for "Saved crop metadata to library" message
2. Verify library database file has write permissions
3. Report bug if issue persists

### "Crop looks different after saving"

**Cause:** Coordinate rounding or image format conversion

**Solution:**
1. Crop coordinates are rounded to nearest pixel
2. Check that selection coordinates match saved values
3. Zoom in to verify exact boundaries before saving

---

## Advanced Features

### Viewing Crop History (Coming Soon)

Future versions will allow you to:
- View all previous crop versions
- Compare automatic vs. manual crops
- Revert to earlier crop settings

### Batch Crop Editing (Coming Soon)

Apply the same crop to multiple similar images:
1. Perfect your crop on one image
2. Save as a crop template
3. Apply template to other images in the collection

---

## Technical Details

### Coordinate System

Crops use absolute pixel coordinates:

```
{
  "x1": 100,  // Left edge
  "y1": 50,   // Top edge
  "x2": 900,  // Right edge
  "y2": 650   // Bottom edge
}
```

Width = x2 - x1 = 800 pixels
Height = y2 - y1 = 600 pixels

### Where Changes Are Saved

Your crop edits are saved in two places:

1. **JSONL Manifest**
   - Location: `{item}/assets/cropped/crop_manifest.jsonl`
   - Format: One JSON line per processed file
   - Used for: Processing history and reproducibility

2. **SQLite Database**
   - Table: `extracted_metadata`
   - Used for: Searching and filtering by crop parameters
   - Includes: Method, confidence, box coordinates, edit timestamp

### Metadata Stored

When you save a manual crop, the system stores:

- `method`: "manual"
- `box`: Crop coordinates {x1, y1, x2, y2}
- `cropped_size`: Dimensions [width, height]
- `manually_edited`: true
- `edited_at`: Timestamp of edit

This allows you to:
- Query items by crop method
- Find all manually edited crops
- Track when crops were modified
- Maintain edit history

---

## Getting Help

### Log Messages

To see detailed information about crop operations:

1. Open the Fichero logs: `logs/fichero.log`
2. Look for messages containing "crop" or "📐"
3. Successful saves show: "✅ Saved crop metadata to library"
4. Errors show: "❌ Failed to apply crop" with details

### Support Channels

If you encounter issues:

1. Check this user guide
2. Review the implementation report: `docs/CROP_EDITOR_IMPLEMENTATION_REPORT.md`
3. Check existing issues in the GitHub repository
4. Create a new issue with:
   - Screenshot of the problem
   - Relevant log messages
   - Steps to reproduce

---

## Feedback

We welcome feedback on the crop editor! Please share:

- Feature requests
- Usability improvements
- Bug reports
- Workflow suggestions

Your input helps make Fichero better for everyone.
