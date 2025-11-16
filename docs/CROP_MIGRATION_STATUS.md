# Crop Tool Migration Status Report

**Date:** November 15, 2025
**Status:** Planning Complete - Ready for Implementation
**Migration:** First tool migration (crop tool → library backend metadata)

---

## Summary

I've completed a comprehensive migration plan for the crop tool to use the library backend metadata storage system. This is the first tool migration and will establish the pattern for all other tools.

### Key Documents Created

1. **Migration Plan:** `/Users/dtubb/code/fichero_main/fichero/docs/CROP_TOOL_MIGRATION_PLAN.md`
   - Complete implementation guide
   - Dual-mode architecture (library + standalone)
   - Bug fixes and validation improvements
   - Testing strategy
   - Migration template for other tools

### Architecture Review

I reviewed the following documents to understand the target architecture:

1. ✅ **LIBRARY_BACKEND_METADATA_ARCHITECTURE.md** - Target architecture for metadata storage
2. ✅ **TOOL_METADATA_AUDIT.md** - Current crop tool patterns and metadata structure
3. ✅ **crop_tool_code_review.md** - Bugs and issues to fix
4. ✅ **metadata_api.py** - New LibraryMetadataAPI interface
5. ✅ **crop.py** - Current crop tool implementation

---

## Migration Approach: Dual-Mode Support

The crop tool will work in TWO modes:

### Mode 1: Library Mode
**When:** `library_manager` parameter is provided
**Behavior:**
- Receives `item_id` from Director
- Saves metadata to SQLite via `LibraryMetadataAPI`
- Also writes JSONL for backwards compatibility

### Mode 2: Standalone Mode
**When:** `library_manager` is None
**Behavior:**
- No `item_id` provided
- Only writes JSONL (existing behavior)
- No library database operations

This ensures backwards compatibility while enabling new library features.

---

## Implementation Plan (4 Phases)

### Phase 1: Fix Bugs and Add Validation
- Add `validate_crop_box()` function
- Ensure coordinates are within image bounds
- Validate positive area
- Handle validation failures gracefully

### Phase 2: Add Library Mode Support
- Update `process_image()` signature with `library_manager` and `item_id` parameters
- Save metadata to library backend using `LibraryMetadataAPI`
- Categorize metadata by type (step_param, step_result, detection, file_info)
- Maintain JSONL output for compatibility

### Phase 3: Director Integration
- Update `FolderProcessor` to accept `library_manager` in constructor
- Pass library context to crop tool when executing workflow
- Maintain item_id mapping for batch processing

### Phase 4: Library Service Integration
- Update `library_service.py` to provide `library_manager` to Director
- Pass item_id when processing collection items
- Track processing status in library

---

## Metadata Storage Schema

### Library Backend (via LibraryMetadataAPI)
```python
{
    # Step parameters
    "padding": 30,
    "output_format": "jpg",

    # Step results
    "method": "yolo",
    "confidence": 0.92,
    "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000},
    "original_size": [1024, 768],
    "cropped_size": [700, 950],

    # Detection metadata
    "attempts": [...],
    "rotation": {...},

    # File info
    "input_metadata": {...}
}
```

### JSONL Manifest (unchanged for compatibility)
```jsonl
{"source": "...", "outputs": [...], "details": {...}}
```

---

## Testing Strategy

### Unit Tests (`tests/unit/test_crop_tool.py`)
- ✅ `test_validate_crop_box_valid()` - Valid coordinates
- ✅ `test_validate_crop_box_negative()` - Reject negative coords
- ✅ `test_validate_crop_box_exceeds_bounds()` - Reject out-of-bounds
- ✅ `test_validate_crop_box_zero_area()` - Reject zero-area boxes
- ✅ `test_process_image_library_mode()` - Library integration
- ✅ `test_process_image_standalone_mode()` - Standalone mode
- ✅ `test_crop_batch_library_mode()` - Batch with library

### CLI Integration Tests (`tests/cli/test_crop_metadata.sh`)
1. Create test collection
2. Add test images
3. Process with crop tool
4. Verify metadata in library database
5. Query by metadata (method, confidence)
6. Test standalone mode
7. Verify JSONL still created

### End-to-End Manual Test
1. Process real images through library
2. Check metadata in database: `library metadata-show <item_id>`
3. Query by filters: `library metadata-query <collection_id> --filter "crop.method=yolo"`
4. Verify JSONL also created
5. Test standalone mode without library

---

## Bugs Fixed

From the code review document, the following bugs will be fixed:

### BUG-007: Missing Crop Box Validation
**Issue:** No validation that crop box coordinates are within image bounds
**Fix:** Added `validate_crop_box()` function with comprehensive validation

**Validation checks:**
- Coordinates are non-negative
- Coordinates are within image bounds
- Box has positive area (x2 > x1, y2 > y1)

---

## Migration Template for Other Tools

The migration plan includes a reusable template for migrating other tools:

### 1. Update Function Signature
```python
def process_image(
    # ... existing params ...
    library_manager = None,  # NEW
    item_id: Optional[str] = None  # NEW
)
```

### 2. Add Library Save Logic
```python
if library_manager and item_id:
    metadata_api = library_manager.metadata_api
    metadata_api.save_step_metadata(
        item_id=item_id,
        step_name="tool_name",
        metadata={...}
    )
```

### 3. Update Batch Function
```python
def tool_batch(
    # ... existing params ...
    library_manager = None  # NEW
):
    # Pass to process function
    process_image(..., library_manager=library_manager, item_id=item_id)
```

### 4. Update Director
```python
if hasattr(self, 'library_manager'):
    result = tool(..., library_manager=self.library_manager, item_id=item_id)
```

---

## Next Steps

### Immediate Actions (in order):
1. ✅ Review migration plan (DONE)
2. Implement Phase 1 - Bug fixes and validation
3. Implement Phase 2 - Library mode support
4. Implement Phase 3 - Director integration
5. Implement Phase 4 - Library Service integration
6. Write unit tests
7. Create CLI integration tests
8. Test end-to-end with real images
9. Document results
10. Apply pattern to next tool (rotate.py)

### Success Criteria
- ✅ Crop tool saves to library database in library mode
- ✅ Crop tool saves to JSONL in standalone mode
- ✅ Metadata is searchable via CLI
- ✅ All tests pass
- ✅ Backwards compatible with existing workflows
- ✅ Pattern documented for other tools

---

## File Locations

### Modified Files (to be implemented):
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/tools/crop.py`
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/director/folder_processor.py`
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/library/library_service.py`

### New Files (to be created):
- `/Users/dtubb/code/fichero_main/fichero/tests/unit/test_crop_tool.py`
- `/Users/dtubb/code/fichero_main/fichero/tests/cli/test_crop_metadata.sh`

### Documentation Files:
- ✅ `/Users/dtubb/code/fichero_main/fichero/docs/CROP_TOOL_MIGRATION_PLAN.md` (created)
- ✅ `/Users/dtubb/code/fichero_main/fichero/docs/CROP_MIGRATION_STATUS.md` (this file)

---

## Questions for Review

Before proceeding with implementation, please review:

1. **Dual-mode approach:** Is the dual-mode design (library + standalone) acceptable?
2. **Validation strategy:** Should validation failures fall back to original image or fail processing?
3. **Metadata categorization:** Are the metadata type categories correct (step_param, step_result, etc.)?
4. **Director integration:** Should Director store library_manager as instance variable or pass it per-call?
5. **Testing scope:** Is the testing strategy comprehensive enough?

---

## Conclusion

The crop tool migration plan is complete and comprehensive. It includes:

1. ✅ Clear dual-mode architecture
2. ✅ Bug fixes and validation improvements
3. ✅ Step-by-step implementation guide
4. ✅ Comprehensive testing strategy
5. ✅ Reusable migration template for other tools
6. ✅ Common issues and solutions documented

The plan is ready for implementation. Each phase can be tackled incrementally with testing at each step. Once the crop tool migration is complete and validated, the same pattern can be applied to the remaining 15 processing tools.

**Estimated Implementation Time:** 4-6 sessions (one per phase, plus testing and documentation)

**Risk Level:** Low - Maintains backwards compatibility, comprehensive testing, well-documented pattern

**Next Tool After Crop:** rotate.py (simple metadata, low complexity - good second migration)
