# PHASE C: FIX IMPLEMENTATION INSTRUCTIONS

**Objective:** Fix all critical and major issues identified in Phase C code review

**Input:** `PHASE_C_CODE_REVIEW_REPORT.md`

---

## ISSUES TO FIX (15 Total)

### CRITICAL Issues (7)

#### CRITICAL-1: convert_to_svg Wrong Function Signature
**Location:** `_run_convert_to_svg()` method

**Problem:** Implementation calls function with wrong parameters. Tool requires transcription data but implementation doesn't provide it.

**Fix:**
```python
async def _run_convert_to_svg(self, item, params):
    """Execute convert_to_svg on a single item

    Note: This tool requires both image and transcription data.
    For single-item execution, we need to check if transcription exists.
    """
    try:
        from fichero.tools.convert_to_svg import convert_to_svg_batch
        import tempfile
        import json
        import os

        # Create temporary manifest
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            manifest_path = f.name
            json.dump(item, f)

        # Create temporary output folder
        with tempfile.TemporaryDirectory() as output_folder:
            try:
                # Check if transcription exists
                transcription_path = item.get('transcription_path')
                if not transcription_path or not os.path.exists(transcription_path):
                    raise ValueError("Transcription required for SVG conversion")

                # Execute batch function with transcription
                result = await asyncio.to_thread(
                    convert_to_svg_batch,
                    source_folder=os.path.dirname(item['path']),
                    source_manifest=manifest_path,
                    output_folder=output_folder,
                    transcription_folder=os.path.dirname(transcription_path),
                    transcription_manifest=manifest_path,  # Same manifest works
                    use_potrace=params.get('use_potrace', True),
                    svg_format=params.get('svg_format', 'simple'),
                )

                return {
                    'success': result.get('success', 0) > 0,
                    'output_folder': output_folder,
                }
            finally:
                os.unlink(manifest_path)

    except Exception as e:
        self.logger.error(f"convert_to_svg execution failed: {e}")
        raise RuntimeError(f"Failed to execute convert_to_svg: {str(e)}")
```

#### CRITICAL-2: transcribe_lmstudio Invalid Parameter
**Location:** `_run_transcribe_lmstudio()` method

**Problem:** Passes `prompt` parameter but actual function uses `model_name` and `api_url` only.

**Fix:** Remove `prompt` parameter:
```python
result = await asyncio.to_thread(
    transcribe_lmstudio_batch,
    source_folder=os.path.dirname(item['path']),
    source_manifest=manifest_path,
    output_folder=output_folder,
    api_url=params.get('api_url', 'http://localhost:1234'),
    model_name=params.get('model_name', 'llava-1.5-7b-hf'),
    # REMOVED: prompt parameter doesn't exist
)
```

#### CRITICAL-3: json_to_excel Invalid Parameter
**Location:** `_run_json_to_excel()` method

**Problem:** Passes `flatten` parameter but function doesn't accept it.

**Fix:** Remove `flatten` parameter:
```python
result = await asyncio.to_thread(
    json_to_excel,
    json_file=item['path'],
    output_file=output_path,
    # REMOVED: flatten parameter
    # REMOVED: max_depth parameter (also doesn't exist)
)
```

#### CRITICAL-4: SpreadManager Missing temp_dir
**Location:** `_run_recombine()` method

**Problem:** SpreadManager requires `temp_dir` parameter.

**Fix:**
```python
from fichero.tools.recombine import SpreadManager

with tempfile.TemporaryDirectory() as temp_dir:
    manager = SpreadManager(
        source_folder=item['path'],
        temp_dir=temp_dir  # ADD THIS
    )
    result = await asyncio.to_thread(manager.recombine_segments)
```

#### CRITICAL-5: Async Pattern Inconsistency
**Location:** Multiple methods using `loop.run_in_executor()`

**Problem:** Should use `asyncio.to_thread()` consistently (Python 3.9+).

**Fix:** Replace all instances:
```python
# BEFORE:
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, function, *args)

# AFTER:
result = await asyncio.to_thread(function, *args)
```

**Affected methods:**
- `_run_split()`
- `_run_describe()`
- `_run_json_to_word()`
- `_run_recombine()`
- `_run_fuzzy_clean()`

#### CRITICAL-6: Wrong Return Value Structure
**Location:** Multiple methods checking `'outputs' in result`

**Problem:** Batch functions return `{'success': N, 'failed': M}`, not `{'outputs': [...]}`

**Fix Pattern:**
```python
# BEFORE:
if 'outputs' in result:
    return {'success': True, 'outputs': result['outputs']}

# AFTER:
return {
    'success': result.get('success', 0) > 0,
    'processed': result.get('success', 0),
    'failed': result.get('failed', 0),
}
```

**Affected methods:**
- `_run_split()`
- `_run_remove_background()`
- `_run_prepare_images()`
- `_run_segment()`
- `_run_transcribe_lmstudio()`
- `_run_describe()`
- `_run_analyze_document_groups()`
- `_run_convert_to_word()`
- `_run_json_to_word()`

#### CRITICAL-7: Missing Cleanup Error Handling
**Location:** All methods using `os.unlink(manifest_path)`

**Problem:** Cleanup happens outside finally block or without error handling.

**Fix Pattern:**
```python
try:
    # ... execution code ...
finally:
    # Cleanup temp files
    try:
        if os.path.exists(manifest_path):
            os.unlink(manifest_path)
    except Exception as e:
        self.logger.warning(f"Failed to cleanup temp file: {e}")
```

---

### MAJOR Issues (8)

#### MAJOR-1: llm_process Missing folder_mode
**Location:** `_run_llm_process()` method

**Problem:** Phase B schema includes `folder_mode` but not passed to function.

**Fix:** Add `folder_mode` parameter:
```python
result = await asyncio.to_thread(
    process_documents_batch,
    source_folder=source_folder,
    source_manifest=manifest_path,
    output_folder=output_folder,
    prompt_config=params.get('prompt_config', 'catalogue_generic'),
    llm=params.get('llm', 'qwen-max'),
    folder_mode=params.get('folder_mode', False),  # ADD THIS
)
```

#### MAJOR-2: prepare_images Wrong Default
**Location:** `_run_prepare_images()` method

**Problem:** Default compression_quality is 95, but Phase B schema says 85.

**Fix:** Change default:
```python
compression_quality=params.get('compression_quality', 85),  # Was 95
```

#### MAJOR-3: remove_background Parameter Mismatch
**Location:** `_run_remove_background()` method

**Problem:** Passes `method='rembg'` but Phase B schema says method values are 'ai' and 'opencv'.

**Fix:**
```python
result = await asyncio.to_thread(
    remove_background_batch,
    source_folder=os.path.dirname(item['path']),
    source_manifest=manifest_path,
    output_folder=output_folder,
    method=params.get('method', 'opencv'),  # Default from Phase B
    ai_model=params.get('ai_model', 'u2net'),  # From Phase B schema
)
```

#### MAJOR-4: segment Missing skip_processing
**Location:** `_run_segment()` method

**Problem:** Phase B schema has `skip_processing` parameter but it's not passed.

**Fix:**
```python
result = await asyncio.to_thread(
    segment_batch,
    source_folder=os.path.dirname(item['path']),
    source_manifest=manifest_path,
    output_folder=output_folder,
    skip_processing=params.get('skip_processing', True),  # ADD THIS
)
```

#### MAJOR-5: analyze_document_groups Wrong Parameters
**Location:** `_run_analyze_document_groups()` method

**Problem:** Passes individual parameters but function may expect different structure.

**Fix:** Verify function signature and adjust:
```python
# Read src/fichero/tools/analyze_document_groups.py to confirm signature
# Then adjust parameters accordingly
```

#### MAJOR-6: extract_library_metadata Incomplete
**Location:** `_run_extract_library_metadata()` method

**Problem:** Implementation too simple, may need collection_id handling.

**Fix:** Add collection_id parameter:
```python
result = await asyncio.to_thread(
    extract_metadata_batch,
    library_db_path=params.get('library_db_path'),
    collection_id=item.get('collection_id'),  # ADD THIS
)
```

#### MAJOR-7: Temp Directory Handling
**Location:** Multiple methods create temp folders but don't verify cleanup

**Problem:** Should use context managers consistently.

**Fix Pattern:**
```python
with tempfile.TemporaryDirectory() as temp_dir:
    # All work here
    # Auto-cleanup on exit
```

#### MAJOR-8: Error Messages Not Specific
**Location:** All exception handlers

**Problem:** Generic error messages don't help debugging.

**Fix Pattern:**
```python
except ValueError as e:
    self.logger.error(f"{tool_name} parameter error: {e}")
    raise
except FileNotFoundError as e:
    self.logger.error(f"{tool_name} file not found: {e}")
    raise
except Exception as e:
    self.logger.error(f"{tool_name} unexpected error: {e}", exc_info=True)
    raise RuntimeError(f"Failed to execute {tool_name}: {str(e)}")
```

---

### MINOR Issues (3)

#### MINOR-1: Import Organization
**Problem:** Imports inside methods instead of top of file.

**Fix:** Move to top where appropriate (but lazy loading is OK for optional deps).

#### MINOR-2: Docstring Completeness
**Problem:** Some docstrings don't document all exceptions.

**Fix:** Add complete Raises section to all docstrings.

#### MINOR-3: Code Duplication
**Problem:** Temp manifest creation code duplicated in many methods.

**Fix (Future):** Extract to helper method:
```python
async def _execute_batch_tool(self, tool_function, item, params, **kwargs):
    """Helper to execute batch tool on single item"""
    # Common temp manifest + execution logic
```

---

## IMPLEMENTATION STEPS

### Step 1: Critical Fixes (Must Fix)
1. Fix convert_to_svg signature (CRITICAL-1)
2. Remove invalid parameters (CRITICAL-2, 3)
3. Fix SpreadManager instantiation (CRITICAL-4)
4. Standardize async pattern (CRITICAL-5)
5. Fix return value checks (CRITICAL-6)
6. Add cleanup error handling (CRITICAL-7)

### Step 2: Major Fixes (Should Fix)
1. Add missing parameters (MAJOR-1, 4)
2. Fix parameter defaults (MAJOR-2, 3)
3. Verify function signatures (MAJOR-5, 6)
4. Improve error handling (MAJOR-7, 8)

### Step 3: Minor Fixes (Optional)
1. Organize imports (MINOR-1)
2. Complete docstrings (MINOR-2)
3. Note code duplication for future (MINOR-3)

---

## VERIFICATION CHECKLIST

After fixes:
- [ ] All CRITICAL issues resolved
- [ ] All MAJOR issues resolved
- [ ] Python syntax valid
- [ ] All imports correct
- [ ] Parameter names match Phase B schemas
- [ ] Return values consistent
- [ ] Error handling comprehensive
- [ ] Cleanup code safe

---

## OUTPUT DELIVERABLE

Create: `PHASE_C_FIX_REPORT.md`

Include:
1. **Fixes Applied:** Complete list of changes
2. **Method-by-Method Changes:** Before/After for each fix
3. **Verification Results:** All quality checks
4. **Parameter Alignment:** Confirmation matches Phase B schemas
5. **Remaining Issues:** Any unfixed items
6. **Ready for Testing:** Confirmation

---

## TESTING NOTES

After fixes, the testing agent should:
- Import tool_executor successfully
- Verify all method signatures correct
- Check parameter mappings against Phase B schemas
- Validate error handling works
- Test with mock data (not actual execution)

**When complete, report fixes applied and readiness for testing.**
