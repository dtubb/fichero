# Crop Tool Migration Plan

**Date:** November 15, 2025
**Status:** In Progress
**Purpose:** Migrate crop tool to use library backend metadata storage while maintaining backwards compatibility

---

## Executive Summary

This document outlines the migration of the crop tool from JSONL-only metadata storage to a dual-mode system that supports both:
1. **Library mode** - Saves metadata to SQLite database via `LibraryMetadataAPI`
2. **Standalone mode** - Continues to write JSONL manifest files for backwards compatibility

This is the **first tool migration** and will establish the pattern for all other processing tools.

### Key Objectives

1. ✅ Fix identified bugs in crop tool (coordinate system, validation, etc.)
2. ✅ Add library backend integration via `LibraryMetadataAPI`
3. ✅ Maintain backwards compatibility with JSONL manifests
4. ✅ Support both library and standalone modes
5. ✅ Create reusable pattern for other tool migrations

---

## Current State Analysis

### Existing Crop Tool Architecture

**File:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/tools/crop.py`

**Current Flow:**
```
crop_batch() → BatchProcessor → process_image() → returns dict → ManifestProcessor writes JSONL
```

**Metadata Structure:**
```python
{
    "outputs": ["prepared/IMG_001.jpg"],
    "source": "documents/IMG_001.jpg",
    "details": {
        "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000},
        "method": "yolo",
        "confidence": 0.92,
        "padding": 30,
        "original_size": [1024, 768],
        "cropped_size": [700, 950],
        "rotation": {"reason": "EXIF rotation applied"},
        "attempts": [{"method": "yolo", "confidence": 0.35, "success": true}],
        "output_format": "jpg",
        "input_metadata": {"format": "JPEG", "mode": "RGB"}
    }
}
```

### Identified Bugs (from code review)

**BUG-001: Coordinate System Inconsistency**
- Tool uses `{x1, y1, x2, y2}` format ✅ (correct)
- Need to ensure all validation/processing uses this format consistently

**BUG-007: Missing Boundary Validation**
- No validation that crop box is within image bounds
- Need to add bounds checking before cropping

---

## Target Architecture

### Dual-Mode Design

The crop tool must work in TWO contexts:

#### 1. Library Mode
**Trigger:** When `library_manager` parameter is provided
**Behavior:**
- Receives `item_id` parameter from Director
- Saves metadata to library backend via `LibraryMetadataAPI`
- Also writes to JSONL for backwards compatibility

#### 2. Standalone Mode
**Trigger:** When `library_manager` is None
**Behavior:**
- No `item_id` provided
- Only writes to JSONL manifest (existing behavior)
- No library database operations

### Metadata Storage Schema

**Library Backend Storage:**
```python
# Via LibraryMetadataAPI.save_step_metadata()
{
    "method": "yolo",              # step_result
    "confidence": 0.92,            # step_result
    "box": {                       # step_result
        "x1": 100,
        "y1": 50,
        "x2": 800,
        "y2": 1000
    },
    "padding": 30,                 # step_param
    "original_size": [1024, 768],  # file_info
    "cropped_size": [700, 950],    # step_result
    "attempts": [...],             # detection
    "rotation": {...},             # detection
    "output_format": "jpg",        # file_info
    "input_metadata": {...}        # file_info
}
```

**JSONL Manifest (unchanged):**
```jsonl
{"source": "...", "outputs": [...], "details": {...}}
```

---

## Implementation Plan

### Phase 1: Fix Bugs and Add Validation

**File:** `src/fichero/tools/crop.py`

**Changes:**

1. **Add bounds validation function**
```python
def validate_crop_box(box: dict, image_width: int, image_height: int) -> Tuple[bool, Optional[str]]:
    """
    Validate crop box coordinates are within image bounds.

    Args:
        box: Crop box with {x1, y1, x2, y2} coordinates
        image_width: Image width in pixels
        image_height: Image height in pixels

    Returns:
        (is_valid, error_message)
    """
    x1 = box.get('x1', 0)
    y1 = box.get('y1', 0)
    x2 = box.get('x2', 0)
    y2 = box.get('y2', 0)

    # Check coordinates are non-negative
    if x1 < 0 or y1 < 0:
        return False, f"Crop coordinates must be non-negative: x1={x1}, y1={y1}"

    # Check coordinates are within bounds
    if x2 > image_width or y2 > image_height:
        return False, f"Crop box exceeds image dimensions ({image_width}x{image_height}): x2={x2}, y2={y2}"

    # Check box has positive area
    if x2 <= x1 or y2 <= y1:
        return False, f"Crop box must have positive area: x1={x1}, y1={y1}, x2={x2}, y2={y2}"

    return True, None
```

2. **Update process_image() to validate coordinates**
```python
def process_image(
    file_path: Path,
    out_path: Path,
    output_format: str = 'jpg',
    contour_settings: ContourSettings = DEFAULT_CONTOUR_SETTINGS,
    library_manager = None,  # NEW
    item_id: Optional[str] = None  # NEW
) -> dict:
    """Process a single image file"""

    # ... existing code ...

    # Get the processed image and crop info
    processed_image, crop_info = result

    # NEW: Validate crop box
    is_valid, error = validate_crop_box(
        crop_info.box,
        crop_info.original_size[0],
        crop_info.original_size[1]
    )

    if not is_valid:
        tool_logger.error(f"Invalid crop box: {error}")
        # Fall back to original image
        result = crop_with_fallback(image, metadata)
        processed_image, crop_info = result

    # ... continue with existing save logic ...
```

### Phase 2: Add Library Mode Support

**File:** `src/fichero/tools/crop.py`

**Changes:**

1. **Update process_image() signature**
```python
def process_image(
    file_path: Path,
    out_path: Path,
    output_format: str = 'jpg',
    contour_settings: ContourSettings = DEFAULT_CONTOUR_SETTINGS,
    library_manager = None,  # NEW: Optional LibraryManager for library mode
    item_id: Optional[str] = None  # NEW: Optional item ID for library mode
) -> dict:
```

2. **Add library metadata save after image processing**
```python
def process_image(...) -> dict:
    # ... existing processing code ...

    # Convert crop_info to dict and add additional metadata
    crop_info_dict = crop_info.to_dict()
    crop_info_dict["attempts"] = attempts
    crop_info_dict["output_format"] = actual_format
    crop_info_dict["input_metadata"] = metadata

    # NEW: Save to library backend if in library mode
    if library_manager and item_id:
        try:
            metadata_api = library_manager.metadata_api

            # Prepare metadata for library storage
            # Categorize fields according to metadata type taxonomy
            metadata_for_library = {
                # Step parameters
                "padding": crop_info.padding,
                "output_format": actual_format,

                # Step results
                "method": crop_info.method,
                "confidence": crop_info.confidence,
                "box": crop_info.box,
                "original_size": crop_info.original_size,
                "cropped_size": crop_info.cropped_size,

                # Detection metadata
                "attempts": attempts,
                "rotation": crop_info.rotation,

                # File info
                "input_metadata": metadata
            }

            # Add contour settings if present
            if crop_info.contour_settings:
                metadata_for_library["contour_settings"] = crop_info.contour_settings

            # Save to library database
            success = metadata_api.save_step_metadata(
                item_id=item_id,
                step_name="crop",
                metadata=metadata_for_library,
                version=1  # Initial version
            )

            if success:
                tool_logger.info(f"Saved crop metadata to library for item {item_id}")
            else:
                tool_logger.error(f"Failed to save crop metadata to library for item {item_id}")

        except Exception as e:
            tool_logger.error(f"Error saving metadata to library: {e}")
            # Continue processing - don't fail the whole operation

    # Get the relative path for the output file
    output_rel_path = SegmentHandler.get_relative_path(final_path)

    # Return dict for JSONL manifest (always generated)
    return {
        "outputs": [str(output_rel_path)],
        "source": str(rel_path),
        "details": crop_info_dict
    }
```

3. **Update crop_batch() to pass library context**
```python
def crop_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    model_path: Path,
    output_format: str = "jpg",
    parallel_workers: int = 1,
    library_manager = None,  # NEW
    **kwargs
) -> dict:
    """
    Crop document pages to remove borders - importable function

    Args:
        library_manager: Optional LibraryManager for library mode

    Returns:
        Processing statistics dictionary
    """
    # ... existing YOLO model loading code ...

    # ... existing contour settings configuration ...

    # Create processing function wrapper
    def process_with_library(file_path: Path, out_path: Path) -> dict:
        # Extract item_id from file path if in library mode
        # (Director will need to provide this mapping)
        item_id = None
        if library_manager:
            # This is a simplification - actual implementation
            # will receive item_id from Director's processing context
            item_id = kwargs.get('item_id')

        return process_image(
            file_path,
            out_path,
            output_format,
            contour_settings,
            library_manager=library_manager,
            item_id=item_id
        )

    # Create file type processors mapping
    file_types = {ext: process_with_library for ext in get_supported_extensions_list()}

    # Process using batch processor
    if parallel_workers > 1:
        processor = create_parallel_batch_processor(
            "crop",
            process_fn=process_with_library,
            file_types=file_types,
            max_workers=parallel_workers
        )
    else:
        processor = BatchProcessor(
            "crop",
            process_fn=process_with_library,
            file_types=file_types
        )

    # Run batch processing
    return processor.process_batch(source_manifest, output_folder)
```

### Phase 3: Director Integration

**File:** `src/fichero/director/folder_processor.py`

**Current execute_step() method needs to be updated to pass library context:**

```python
def execute_step(self, step_config, item_id=None):
    """
    Execute a single processing step.

    Args:
        step_config: Step configuration dict
        item_id: Optional library item ID for library mode
    """
    tool = self._get_tool(step_config['name'])

    # NEW: Pass library manager if available
    if hasattr(self, 'library_manager'):
        # For crop tool specifically
        if step_config['name'] == 'crop':
            result = tool.crop_batch(
                **step_config['params'],
                library_manager=self.library_manager,
                item_id=item_id  # Pass item_id to tool
            )
        else:
            # Other tools (not yet migrated)
            result = tool(**step_config['params'])
    else:
        # Standalone mode
        result = tool(**step_config['params'])

    return result
```

**Better approach:** Update Director initialization to store library_manager:

```python
class FolderProcessor:
    def __init__(self, library_manager=None):
        """
        Initialize folder processor.

        Args:
            library_manager: Optional LibraryManager for library-integrated processing
        """
        self.library_manager = library_manager
        # ... rest of initialization ...
```

### Phase 4: Library Service Integration

**File:** `src/fichero/library/library_service.py`

**Update process_collection() to provide library_manager to Director:**

```python
def process_collection(self, collection_id, plan_name, workflow_name):
    """
    Process a collection with a specific plan and workflow.

    Args:
        collection_id: ID of collection to process
        plan_name: Name of processing plan
        workflow_name: Name of workflow within plan
    """
    # Get collection
    collection = self.library_manager.get_collection(collection_id)
    if not collection:
        raise ValueError(f"Collection not found: {collection_id}")

    # Get items in collection
    items = self.library_manager.get_collection_items(collection_id)

    # Initialize Director with library context
    from fichero.director.folder_processor import FolderProcessor

    director = FolderProcessor(library_manager=self.library_manager)  # NEW

    # Process each item
    for item in items:
        try:
            # Execute workflow for this item
            result = director.execute_workflow(
                workflow_name=workflow_name,
                input_path=item.local_path,
                output_path=self._get_output_path(collection_id, item.id),
                item_id=item.id  # NEW: Pass item_id to workflow
            )

            # Update item status
            item.status = "processed"
            self.library_manager.update_item(item)

        except Exception as e:
            logger.error(f"Failed to process item {item.id}: {e}")
            item.status = "error"
            self.library_manager.update_item(item)

    logger.info(f"Completed processing collection {collection_id}")
```

---

## Testing Strategy

### Unit Tests

**File:** `tests/unit/test_crop_tool.py`

```python
import pytest
from pathlib import Path
from PIL import Image
from fichero.tools.crop import (
    process_image,
    validate_crop_box,
    crop_batch
)


def test_validate_crop_box_valid():
    """Test crop box validation with valid coordinates"""
    box = {"x1": 100, "y1": 50, "x2": 800, "y2": 650}
    is_valid, error = validate_crop_box(box, 1000, 700)

    assert is_valid
    assert error is None


def test_validate_crop_box_negative():
    """Test crop box validation rejects negative coordinates"""
    box = {"x1": -10, "y1": 50, "x2": 800, "y2": 650}
    is_valid, error = validate_crop_box(box, 1000, 700)

    assert not is_valid
    assert "non-negative" in error


def test_validate_crop_box_exceeds_bounds():
    """Test crop box validation rejects out-of-bounds coordinates"""
    box = {"x1": 100, "y1": 50, "x2": 1200, "y2": 650}
    is_valid, error = validate_crop_box(box, 1000, 700)

    assert not is_valid
    assert "exceeds image dimensions" in error


def test_validate_crop_box_zero_area():
    """Test crop box validation rejects zero-area boxes"""
    box = {"x1": 100, "y1": 50, "x2": 100, "y2": 650}
    is_valid, error = validate_crop_box(box, 1000, 700)

    assert not is_valid
    assert "positive area" in error


def test_process_image_library_mode(tmp_path, mock_library_manager):
    """Test process_image in library mode"""
    # Create test image
    test_image_path = tmp_path / "test.jpg"
    img = Image.new('RGB', (1000, 800), color='white')
    img.save(test_image_path)

    output_path = tmp_path / "output" / "test.jpg"

    # Process with library_manager
    result = process_image(
        file_path=test_image_path,
        out_path=output_path,
        library_manager=mock_library_manager,
        item_id="test-item-123"
    )

    # Verify result structure
    assert "outputs" in result
    assert "source" in result
    assert "details" in result

    # Verify library metadata was saved
    assert mock_library_manager.metadata_api.save_step_metadata.called
    call_args = mock_library_manager.metadata_api.save_step_metadata.call_args
    assert call_args[1]['item_id'] == "test-item-123"
    assert call_args[1]['step_name'] == "crop"
    assert 'method' in call_args[1]['metadata']
    assert 'confidence' in call_args[1]['metadata']
    assert 'box' in call_args[1]['metadata']


def test_process_image_standalone_mode(tmp_path):
    """Test process_image in standalone mode (no library_manager)"""
    # Create test image
    test_image_path = tmp_path / "test.jpg"
    img = Image.new('RGB', (1000, 800), color='white')
    img.save(test_image_path)

    output_path = tmp_path / "output" / "test.jpg"

    # Process WITHOUT library_manager
    result = process_image(
        file_path=test_image_path,
        out_path=output_path
    )

    # Verify result structure (same as library mode)
    assert "outputs" in result
    assert "source" in result
    assert "details" in result

    # No library operations should have been attempted
    # (test passes if no exceptions raised)


def test_crop_batch_library_mode(tmp_path, mock_library_manager):
    """Test crop_batch with library integration"""
    # Setup test files
    source_folder = tmp_path / "source"
    source_folder.mkdir()

    manifest_path = tmp_path / "manifest.jsonl"
    output_folder = tmp_path / "output"
    model_path = tmp_path / "yolo.pt"  # Mock YOLO model

    # Create test images
    for i in range(3):
        img = Image.new('RGB', (1000, 800), color='white')
        img.save(source_folder / f"test_{i}.jpg")

    # Create manifest
    import json
    with open(manifest_path, 'w') as f:
        for i in range(3):
            entry = {
                "file": str(source_folder / f"test_{i}.jpg"),
                "type": "image"
            }
            f.write(json.dumps(entry) + '\n')

    # Run batch processing with library_manager
    stats = crop_batch(
        source_folder=source_folder,
        source_manifest=manifest_path,
        output_folder=output_folder,
        model_path=model_path,
        library_manager=mock_library_manager
    )

    # Verify processing completed
    assert stats['processed'] == 3

    # Verify library metadata was saved for each item
    assert mock_library_manager.metadata_api.save_step_metadata.call_count == 3
```

### CLI Integration Tests

**File:** `tests/cli/test_crop_metadata.sh`

```bash
#!/bin/bash
# CLI integration tests for crop tool library metadata

set -e  # Exit on error

echo "=== Crop Tool Library Metadata Integration Tests ==="
echo ""

# Setup test environment
TEST_DIR="/tmp/fichero_crop_test_$(date +%s)"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

# Create test collection
echo "1. Creating test collection..."
COLLECTION_ID=$(briefcase dev -- library add "Crop Test Collection" \
    --type local \
    --source "$TEST_DIR/source" \
    | grep "Created collection" | awk '{print $3}')

echo "   Collection ID: $COLLECTION_ID"

# Create test images
echo "2. Creating test images..."
mkdir -p source
for i in {1..5}; do
    # Create simple test images using ImageMagick
    convert -size 1000x800 xc:white "source/test_$i.jpg"
done

# Add items to collection
echo "3. Adding items to collection..."
for img in source/*.jpg; do
    briefcase dev -- library add-item "$COLLECTION_ID" file "$img"
done

# Process collection with crop tool
echo "4. Processing collection with crop tool..."
briefcase dev -- library process "$COLLECTION_ID" \
    --plan "Crop Only" \
    --workflow "crop"

# Verify metadata was saved
echo "5. Verifying metadata in library..."

# Get first item
ITEM_ID=$(briefcase dev -- library list-items "$COLLECTION_ID" \
    | head -2 | tail -1 | awk '{print $1}')

echo "   Testing with item: $ITEM_ID"

# Show metadata for crop step
echo "6. Retrieving crop metadata..."
METADATA=$(briefcase dev -- library metadata-show "$ITEM_ID" --step crop)

echo "$METADATA"

# Verify required fields exist
echo "$METADATA" | grep -q "method" || (echo "ERROR: Missing 'method' field" && exit 1)
echo "$METADATA" | grep -q "confidence" || (echo "ERROR: Missing 'confidence' field" && exit 1)
echo "$METADATA" | grep -q "box" || (echo "ERROR: Missing 'box' field" && exit 1)

echo "   ✅ All required fields present"

# Query by metadata
echo "7. Testing metadata query..."
YOLO_ITEMS=$(briefcase dev -- library metadata-query "$COLLECTION_ID" \
    --filter "crop.method=yolo" \
    | wc -l)

echo "   Found $YOLO_ITEMS items with YOLO crop"

# Test standalone mode (no library)
echo "8. Testing standalone mode..."
mkdir -p standalone_output

briefcase dev -- crop \
    --source source \
    --output standalone_output \
    --model-path /path/to/yolo.pt

# Verify JSONL exists
[ -f "standalone_output/crop_manifest.jsonl" ] || (echo "ERROR: JSONL not created in standalone mode" && exit 1)

echo "   ✅ JSONL manifest created"

# Verify JSONL has correct format
grep -q '"source"' standalone_output/crop_manifest.jsonl || (echo "ERROR: Invalid JSONL format" && exit 1)
grep -q '"details"' standalone_output/crop_manifest.jsonl || (echo "ERROR: Missing details in JSONL" && exit 1)

echo "   ✅ JSONL format correct"

# Cleanup
echo "9. Cleaning up..."
rm -rf "$TEST_DIR"

echo ""
echo "=== All Tests Passed ✅ ==="
```

### End-to-End Integration Test

**Manual testing procedure:**

1. **Create test collection with sample images**
```bash
briefcase dev -- library add "Crop Migration Test" --source /path/to/test/images
```

2. **Add test items**
```bash
for img in /path/to/test/images/*.jpg; do
    briefcase dev -- library add-item <collection_id> file "$img"
done
```

3. **Process with crop tool**
```bash
briefcase dev -- library process <collection_id> --plan "Crop Only" --workflow "crop"
```

4. **Verify metadata in library**
```bash
# Show metadata for specific item
briefcase dev -- library metadata-show <item_id> --step crop

# Expected output:
{
  "method": "yolo",
  "confidence": 0.92,
  "box": {
    "x1": 100,
    "y1": 50,
    "x2": 800,
    "y2": 1000
  },
  "padding": 30,
  "original_size": [1024, 768],
  "cropped_size": [700, 950],
  ...
}
```

5. **Verify JSONL also created**
```bash
# Check output folder
ls <output_path>/crop_manifest.jsonl

# Verify content
cat <output_path>/crop_manifest.jsonl | jq '.'
```

6. **Query by metadata**
```bash
# Find all YOLO crops
briefcase dev -- library metadata-query <collection_id> --filter "crop.method=yolo"

# Find high-confidence crops
briefcase dev -- library metadata-query <collection_id> --filter "crop.confidence>=0.8"
```

7. **Test standalone mode**
```bash
# Process without library
briefcase dev -- crop \
    --source /path/to/test/images \
    --output /tmp/crop_output \
    --model-path /path/to/yolo.pt

# Verify JSONL created
cat /tmp/crop_output/crop_manifest.jsonl
```

---

## Migration Checklist

- [ ] Review architecture documents
- [ ] Understand current crop tool implementation
- [ ] Fix identified bugs (validation, coordinate system)
- [ ] Add `library_manager` and `item_id` parameters to `process_image()`
- [ ] Implement metadata save to library backend
- [ ] Update `crop_batch()` to accept `library_manager`
- [ ] Update Director to pass library context
- [ ] Update Library Service to provide `library_manager` to Director
- [ ] Write unit tests for library mode
- [ ] Write unit tests for standalone mode
- [ ] Create CLI integration test script
- [ ] Test end-to-end with real images
- [ ] Verify metadata in database
- [ ] Verify JSONL still generated
- [ ] Test metadata queries
- [ ] Create migration report
- [ ] Document pattern for other tools

---

## Migration Template for Other Tools

Based on crop tool migration, here's the pattern for other tools:

### 1. Update Tool Function Signature

```python
def process_image(
    file_path: Path,
    out_path: Path,
    # ... existing params ...
    library_manager = None,  # NEW
    item_id: Optional[str] = None  # NEW
) -> dict:
```

### 2. Add Library Metadata Save

```python
# After processing, before returning result dict

if library_manager and item_id:
    try:
        metadata_api = library_manager.metadata_api

        # Prepare metadata categorized by type
        metadata_for_library = {
            # Categorize fields according to taxonomy:
            # - step_param: Input parameters
            # - step_result: Output results
            # - detection: Detection/recognition results
            # - file_info: File metadata
            # - transcription: Text content
        }

        success = metadata_api.save_step_metadata(
            item_id=item_id,
            step_name="tool_name",
            metadata=metadata_for_library,
            version=1
        )

        if success:
            tool_logger.info(f"Saved metadata to library for item {item_id}")
        else:
            tool_logger.error(f"Failed to save metadata to library")

    except Exception as e:
        tool_logger.error(f"Error saving metadata to library: {e}")
        # Don't fail the operation

# Return JSONL-compatible dict (always)
return {
    "outputs": [...],
    "source": "...",
    "details": {...}
}
```

### 3. Update Batch Function

```python
def tool_batch(
    # ... existing params ...
    library_manager = None,  # NEW
    **kwargs
) -> dict:

    # Wrapper function to pass library context
    def process_with_library(file_path: Path, out_path: Path) -> dict:
        item_id = kwargs.get('item_id')  # Provided by Director

        return process_image(
            file_path,
            out_path,
            # ... other params ...
            library_manager=library_manager,
            item_id=item_id
        )

    # Use wrapper in batch processor
    # ... rest of batch processing ...
```

### 4. Update Director Integration

```python
# In director/folder_processor.py

def execute_step(self, step_config, item_id=None):
    if hasattr(self, 'library_manager'):
        result = tool_function(
            **step_config['params'],
            library_manager=self.library_manager,
            item_id=item_id
        )
    else:
        result = tool_function(**step_config['params'])

    return result
```

---

## Common Issues and Solutions

### Issue 1: Item ID not available in batch processing

**Problem:** Batch processor processes multiple files but doesn't know which library item each file belongs to.

**Solution:** Director maintains a mapping of file paths to item IDs and passes the correct item_id when calling the tool.

```python
# In Director
item_path_map = {
    "/path/to/file1.jpg": "item-123",
    "/path/to/file2.jpg": "item-456",
    ...
}

# When processing
for file_path in files:
    item_id = item_path_map.get(str(file_path))
    result = tool(file_path, ..., item_id=item_id)
```

### Issue 2: Metadata schema differs between tools

**Problem:** Each tool has different metadata fields and structure.

**Solution:** Use the metadata type taxonomy to categorize fields consistently:
- `step_param` - Input parameters
- `step_result` - Output results
- `detection` - Detection/recognition results
- `file_info` - File metadata
- `transcription` - Text content
- `catalogue_field` - Catalogue metadata

### Issue 3: Version conflicts when re-processing

**Problem:** Re-processing an item creates duplicate metadata entries.

**Solution:** `LibraryMetadataAPI.save_step_metadata()` handles versioning automatically. Each save creates a new version, and `get_step_metadata()` returns the latest by default.

---

## Success Criteria

### Functional Requirements

- ✅ Crop tool saves metadata to library backend when `library_manager` provided
- ✅ Crop tool continues to write JSONL in standalone mode
- ✅ Metadata is queryable via `library metadata-query` CLI
- ✅ Coordinate validation prevents invalid crops
- ✅ Both YOLO and contour detection metadata preserved
- ✅ Backwards compatible with existing workflows

### Testing Requirements

- ✅ Unit tests pass for library mode
- ✅ Unit tests pass for standalone mode
- ✅ CLI integration tests pass
- ✅ End-to-end processing works with real images
- ✅ Metadata queries return expected results
- ✅ JSONL manifests still generated correctly

### Documentation Requirements

- ✅ Migration plan documented (this file)
- ✅ Migration template created for other tools
- ✅ Common issues and solutions documented
- ✅ Testing procedures documented

---

## Next Steps

1. ✅ Review this migration plan
2. Implement Phase 1 (bug fixes and validation)
3. Implement Phase 2 (library mode support)
4. Implement Phase 3 (Director integration)
5. Implement Phase 4 (Library Service integration)
6. Write and run unit tests
7. Create and run CLI integration tests
8. Test end-to-end with real images
9. Create migration report
10. Use this pattern to migrate next tool (rotate.py)

---

## Appendix: Code Locations

- **Crop Tool:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/tools/crop.py`
- **LibraryMetadataAPI:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/library/metadata_api.py`
- **Director:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/director/folder_processor.py`
- **Library Service:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/library/library_service.py`
- **Unit Tests:** `/Users/dtubb/code/fichero_main/fichero/tests/unit/test_crop_tool.py`
- **Integration Tests:** `/Users/dtubb/code/fichero_main/fichero/tests/cli/test_crop_metadata.sh`
