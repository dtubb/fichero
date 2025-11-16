# Crop Tool Migration Implementation Report

**Date:** November 15, 2025
**Status:** Complete (Tool Ready - Infrastructure Deferred)
**Purpose:** Document the implementation of crop tool migration to support library backend metadata storage

---

## Executive Summary

The crop tool has been successfully migrated to support dual-mode operation:
1. **Library Mode** - Saves metadata to SQLite database via `LibraryMetadataAPI`
2. **Standalone Mode** - Continues to write JSONL manifest files for backwards compatibility

This is the **first tool migration** and establishes the pattern for all other processing tools.

### Implementation Status

✅ **Completed:**
- Phase 1: Bug fixes and validation
- Phase 2: Library mode support in crop.py
- Comprehensive unit tests (14 tests, all passing)
- CLI integration test framework

⚠️ **Deferred:**
- Phase 3: Director workflow system integration
- Phase 4: Full library service integration

The crop tool is now **ready to receive library context** when the workflow infrastructure is updated.

---

## Implementation Details

### Phase 1: Bug Fixes and Validation

**File:** `src/fichero/tools/crop.py`

**Added:**
1. `validate_crop_box()` function to validate coordinates
2. Boundary checking for crop boxes
3. Positive area validation
4. Non-negative coordinate validation

**Code:**
```python
def validate_crop_box(box: dict, image_width: int, image_height: int) -> Tuple[bool, Optional[str]]:
    """Validate crop box coordinates are within image bounds."""
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

**Validation Integration:**
```python
# In process_image()
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
```

### Phase 2: Library Mode Support

**File:** `src/fichero/tools/crop.py`

**Updated Function Signatures:**

1. **process_image()** - Core processing function
```python
def process_image(
    file_path: Path,
    out_path: Path,
    output_format: str = 'jpg',
    contour_settings: ContourSettings = DEFAULT_CONTOUR_SETTINGS,
    library_manager = None,  # NEW
    item_id: Optional[str] = None  # NEW
) -> dict:
```

2. **process_document()** - Document wrapper
```python
def process_document(
    file_path: str,
    output_folder: Path,
    output_format: str = 'jpg',
    contour_settings: ContourSettings = DEFAULT_CONTOUR_SETTINGS,
    library_manager = None,  # NEW
    item_id: Optional[str] = None  # NEW
) -> dict:
```

3. **crop_batch()** - Batch processing function
```python
def crop_batch(
    # ... existing parameters ...
    library_manager = None,  # NEW
    **kwargs
) -> dict:
```

**Library Metadata Save Logic:**
```python
# In process_image() after image processing and validation
if library_manager and item_id:
    try:
        metadata_api = library_manager.metadata_api

        # Prepare metadata categorized by type
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
            version=1
        )

        if success:
            tool_logger.info(f"Saved crop metadata to library for item {item_id}")
        else:
            tool_logger.error(f"Failed to save crop metadata to library for item {item_id}")

    except Exception as e:
        tool_logger.error(f"Error saving metadata to library: {e}")
        # Continue processing - don't fail the whole operation
```

**Metadata Taxonomy:**
The metadata is categorized according to the library system's taxonomy:
- `step_param`: Input parameters (padding, output_format)
- `step_result`: Output results (method, confidence, box, sizes)
- `detection`: Detection/recognition results (attempts, rotation)
- `file_info`: File metadata (input_metadata)

**Backwards Compatibility:**
The JSONL manifest is ALWAYS generated, regardless of library mode:
```python
# Always return JSONL-compatible dict
return {
    "outputs": [str(output_rel_path)],
    "source": str(rel_path),
    "details": crop_info_dict
}
```

### Phase 3 & 4: Infrastructure Integration (Deferred)

**Current Architecture Discovery:**

During implementation, we discovered that the actual Director architecture is more complex than the migration plan assumed:

1. **Workflow Executor** (`src/fichero/director/workflow_executor.py`)
   - Executes tools via dynamic import: `importlib.import_module()`
   - Calls tools with expanded arguments from YAML config
   - No built-in mechanism to pass library_manager context

2. **Director Service** (`src/fichero/director/director_service.py`)
   - Singleton pattern manages workflow processing
   - Uses TaskManager and ProcessingCoordinator
   - Currently no library_manager integration

3. **Library Integration** (`src/fichero/library/director_integration.py`)
   - Coordinates between Library and Director
   - Processes collections via Director workflows
   - Could be enhanced to pass library context

**Why Deferred:**
- Passing `library_manager` and `item_id` through the workflow system requires changes to:
  - `WorkflowExecutor._execute_step()` to accept library context
  - YAML workflow configuration to specify library mode
  - TaskManager to track item-to-file mapping
  - ProcessingCoordinator to provide library context

- These changes affect the entire workflow system and all tools
- Should be implemented as a separate infrastructure update

**Tool is Ready:**
The crop tool will automatically use library mode when the infrastructure provides:
1. `library_manager` parameter to `crop_batch()`
2. `item_id` parameter via kwargs

---

## Testing

### Unit Tests

**File:** `tests/unit/test_crop_tool.py`

**Test Coverage:**
- ✅ 14 tests, all passing
- ✅ Validation function (7 tests)
- ✅ Standalone mode (2 tests)
- ✅ Library mode (4 tests)
- ✅ Error handling (1 test)

**Test Results:**
```
tests/unit/test_crop_tool.py::TestValidateCropBox::test_valid_crop_box PASSED
tests/unit/test_crop_tool.py::TestValidateCropBox::test_negative_coordinates PASSED
tests/unit/test_crop_tool.py::TestValidateCropBox::test_exceeds_bounds_width PASSED
tests/unit/test_crop_tool.py::TestValidateCropBox::test_exceeds_bounds_height PASSED
tests/unit/test_crop_tool.py::TestValidateCropBox::test_zero_width PASSED
tests/unit/test_crop_tool.py::TestValidateCropBox::test_zero_height PASSED
tests/unit/test_crop_tool.py::TestValidateCropBox::test_inverted_coordinates PASSED
tests/unit/test_crop_tool.py::TestProcessImageStandalone::test_process_image_standalone_no_library PASSED
tests/unit/test_crop_tool.py::TestProcessImageStandalone::test_process_image_creates_output_directory PASSED
tests/unit/test_crop_tool.py::TestProcessImageLibraryMode::test_process_image_library_mode_saves_metadata PASSED
tests/unit/test_crop_tool.py::TestProcessImageLibraryMode::test_process_image_library_mode_handles_save_failure PASSED
tests/unit/test_crop_tool.py::TestProcessImageLibraryMode::test_process_image_library_mode_handles_exception PASSED
tests/unit/test_crop_tool.py::TestProcessImageLibraryMode::test_process_image_without_item_id_skips_library_save PASSED
tests/unit/test_crop_tool.py::TestProcessImageValidation::test_invalid_crop_box_falls_back_to_original PASSED

============================== 14 passed in 3.99s
```

**Key Test Scenarios:**

1. **Validation Tests:**
   - Valid coordinates accepted
   - Negative coordinates rejected
   - Out-of-bounds coordinates rejected
   - Zero-area boxes rejected
   - Inverted coordinates rejected

2. **Standalone Mode Tests:**
   - JSONL manifest created correctly
   - Output directory created automatically
   - Metadata structure correct
   - No library operations attempted

3. **Library Mode Tests:**
   - Metadata saved to library backend
   - Correct item_id and step_name used
   - Metadata contains all required fields
   - Processing continues if metadata save fails
   - Processing continues if metadata save raises exception
   - Library save skipped if item_id not provided

4. **Error Handling:**
   - Invalid crop box triggers fallback to original image

### CLI Integration Tests

**File:** `tests/cli/test_crop_metadata.sh`

**Test Features:**
- Standalone mode JSONL creation
- Validation function verification
- Library mode placeholder (requires full setup)
- Colored output for test results
- Optional cleanup

**Manual Testing Required:**
For full library mode testing:
```bash
# 1. Create test collection
briefcase dev -- library add 'Test Collection' --type local --source /path/to/images

# 2. Add test items
briefcase dev -- library add-item <collection_id> folder /path/to/folder

# 3. Process with crop tool
briefcase dev -- library process <collection_id> --plan 'Crop Only' --workflow 'crop'

# 4. Verify metadata
briefcase dev -- library metadata-show <item_id> --step crop
```

---

## Migration Pattern for Other Tools

Based on the crop tool migration, here's the pattern for other tools:

### Step 1: Update Tool Function Signature

```python
def process_image(
    file_path: Path,
    out_path: Path,
    # ... existing params ...
    library_manager = None,  # NEW
    item_id: Optional[str] = None  # NEW
) -> dict:
```

### Step 2: Add Library Metadata Save

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
            # - catalogue_field: Catalogue metadata
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

### Step 3: Update Batch Function

```python
def tool_batch(
    # ... existing params ...
    library_manager = None,  # NEW
    **kwargs
) -> dict:

    # Extract item_id from kwargs if in library mode
    item_id = kwargs.get('item_id')

    # Create processing function wrapper
    def process_with_library(file_path: Path, out_path: Path) -> dict:
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

### Step 4: Write Tests

Follow the test pattern in `tests/unit/test_crop_tool.py`:
- Validation tests (if applicable)
- Standalone mode tests
- Library mode tests
- Error handling tests

---

## Issues and Deviations

### Issue 1: Workflow Infrastructure Not Ready

**Problem:** The Director workflow system doesn't have a built-in mechanism to pass library context to tools.

**Impact:** Phases 3 and 4 of the migration plan cannot be completed without infrastructure changes.

**Solution:** Deferred to separate infrastructure update. The crop tool is ready to receive library context when provided.

**Recommendation:**
1. Create a workflow system update plan
2. Design library context passing mechanism
3. Update all affected components (WorkflowExecutor, TaskManager, etc.)
4. Test with crop tool first
5. Roll out to other tools

### Issue 2: Item-to-File Mapping

**Problem:** Batch processing handles multiple files, but doesn't know which library item each file belongs to.

**Impact:** In library mode, we need to know which item_id corresponds to which file.

**Solution:** This will be handled by the workflow infrastructure update. The Director will need to maintain an item-to-file mapping and pass the correct item_id for each file processed.

**Current Workaround:** The `kwargs.get('item_id')` pattern allows the Director to pass item_id when ready.

### Issue 3: Testing Limitations

**Problem:** Full end-to-end library mode testing requires the complete infrastructure.

**Impact:** Cannot test actual library metadata storage without Director integration.

**Solution:**
- Unit tests use mocks to verify the code path works correctly
- CLI tests verify standalone mode works
- Manual testing required for library mode once infrastructure is ready

---

## Files Modified

1. **src/fichero/tools/crop.py**
   - Added `validate_crop_box()` function
   - Updated `process_image()` signature and implementation
   - Updated `process_document()` signature and implementation
   - Updated `crop_batch()` signature and implementation
   - Added library metadata save logic
   - Added validation logic with fallback

2. **tests/unit/test_crop_tool.py** (NEW)
   - 14 comprehensive unit tests
   - Tests validation, standalone mode, library mode
   - Tests error handling

3. **tests/cli/test_crop_metadata.sh** (NEW)
   - CLI integration test framework
   - Standalone mode tests
   - Validation function tests
   - Library mode placeholder

---

## Next Steps

### Immediate (This Tool)
- ✅ Implementation complete
- ✅ Tests pass
- ✅ Documentation complete

### Short Term (Next Tools)
1. Use this pattern to migrate `rotate.py`
2. Use this pattern to migrate `enhance.py`
3. Build confidence in the pattern with 2-3 tools

### Medium Term (Infrastructure)
1. Design workflow system update
2. Implement library context passing in WorkflowExecutor
3. Add item-to-file mapping in TaskManager
4. Update DirectorIntegrationService
5. Test with migrated tools

### Long Term (All Tools)
1. Migrate all remaining tools using established pattern
2. Update all YAML workflow configs
3. Deprecate JSONL-only mode (keep for backwards compatibility)
4. Add migration guide for third-party tools

---

## Success Criteria

### Functional Requirements
- ✅ Crop tool saves metadata to library backend when `library_manager` provided
- ✅ Crop tool continues to write JSONL in standalone mode
- ✅ Coordinate validation prevents invalid crops
- ✅ Fallback to original image on validation failure
- ✅ Backwards compatible with existing workflows
- ⚠️ Metadata queryable via `library metadata-query` (infrastructure not ready)

### Testing Requirements
- ✅ Unit tests pass for library mode
- ✅ Unit tests pass for standalone mode
- ✅ CLI integration tests pass for standalone mode
- ⚠️ End-to-end processing with real images (requires infrastructure)
- ⚠️ Metadata queries return expected results (requires infrastructure)

### Documentation Requirements
- ✅ Migration plan documented
- ✅ Migration pattern created for other tools
- ✅ Common issues and solutions documented
- ✅ Testing procedures documented

---

## Lessons Learned

### Architecture Understanding is Critical
The original migration plan assumed a simpler architecture. Always investigate the actual codebase structure before planning.

### Tool-First Approach Works
Implementing library mode in the tool first, then deferring infrastructure, allows incremental progress without blocking.

### Mock Testing is Valuable
Even without full infrastructure, comprehensive unit tests with mocks verify the code works correctly.

### Pattern Documentation is Key
Documenting the migration pattern now will make future tool migrations much faster.

### Separation of Concerns
The crop tool handles its own validation and metadata preparation. The infrastructure handles routing. This separation works well.

---

## Conclusion

The crop tool migration is **complete and ready**. The tool:
- ✅ Validates crop boxes correctly
- ✅ Supports dual-mode operation (library + standalone)
- ✅ Saves metadata correctly when library context provided
- ✅ Maintains backwards compatibility
- ✅ Has comprehensive test coverage
- ✅ Provides a clear pattern for other tools

The infrastructure integration (Phases 3-4) is **deferred** but the groundwork is complete. When the workflow system is updated to pass library context, the crop tool will automatically use library mode.

**Recommendation:** Proceed with migrating 2-3 more tools using this pattern to validate the approach, then plan the infrastructure update.

---

## Appendix: Code Locations

- **Crop Tool:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/tools/crop.py`
- **LibraryMetadataAPI:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/library/metadata_api.py`
- **WorkflowExecutor:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/director/workflow_executor.py`
- **DirectorIntegrationService:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/library/director_integration.py`
- **Unit Tests:** `/Users/dtubb/code/fichero_main/fichero/tests/unit/test_crop_tool.py`
- **CLI Tests:** `/Users/dtubb/code/fichero_main/fichero/tests/cli/test_crop_metadata.sh`
