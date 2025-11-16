# PHASE C: Key Changes Examples

## Example 1: CRITICAL-1 - convert_to_svg Function Signature

### BEFORE (Lines 341-368):
```python
async def _run_convert_to_svg(self, input_path: Path, output_folder: Path,
                             parameters: Dict[str, Any]) -> bool:
    """Run convert_to_svg tool"""
    from fichero.tools.convert_to_svg import convert_to_svg_batch
    import tempfile
    import json

    # Create temporary manifest for single item
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        manifest_entry = {'source': str(input_path), 'outputs': [str(input_path)]}
        f.write(json.dumps(manifest_entry) + '\n')
        temp_manifest = f.name

    try:
        loop = asyncio.get_event_loop()                    # ❌ OLD PATTERN
        result = await loop.run_in_executor(
            None,
            convert_to_svg_batch,
            input_path.parent,
            Path(temp_manifest),
            output_folder,
            parameters.get('llm', 'qwen-max'),            # ❌ WRONG PARAMETER
            parameters.get('use_potrace', True)           # ❌ WRONG PARAMETER
        )
        return result.get('success', 0) > 0
    finally:
        Path(temp_manifest).unlink(missing_ok=True)       # ❌ NO ERROR HANDLING
```

### AFTER (Lines 335-387):
```python
async def _run_convert_to_svg(self, input_path: Path, output_folder: Path,
                             parameters: Dict[str, Any]) -> bool:
    """
    Run convert_to_svg tool

    CRITICAL-1: This tool requires both image and transcription data.
    For single-item execution, transcription_folder and transcription_manifest
    must be provided in parameters.
    """
    from fichero.tools.convert_to_svg import convert_to_svg_batch
    import tempfile
    import json
    import os

    # ✅ CRITICAL-1: Check for required transcription parameters
    transcription_folder = parameters.get('transcription_folder')
    transcription_manifest = parameters.get('transcription_manifest')

    if not transcription_folder or not transcription_manifest:
        self.logger.error("convert_to_svg requires transcription_folder and transcription_manifest parameters")
        return False

    # Create temporary manifest for single item
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        manifest_entry = {'source': str(input_path), 'outputs': [str(input_path)]}
        f.write(json.dumps(manifest_entry) + '\n')
        temp_manifest = f.name

    try:
        # ✅ CRITICAL-1: Fix function signature - add transcription parameters
        # ✅ CRITICAL-5: Use asyncio.to_thread
        result = await asyncio.to_thread(
            convert_to_svg_batch,
            input_path.parent,              # source_folder
            Path(temp_manifest),            # source_manifest
            Path(transcription_folder),     # transcription_folder (ADDED)
            Path(transcription_manifest),   # transcription_manifest (ADDED)
            output_folder,                  # output_folder
            # Optional parameters
            None,  # metadata_manifest
            None,  # visual_descriptions_manifest
            None,  # api_key_cli
            parameters.get('skip_processing', False)
        )
        # ✅ CRITICAL-6: Fix return value structure (returns success/failed counts)
        return result.get('success', 0) > 0
    finally:
        # ✅ CRITICAL-7: Proper cleanup error handling
        try:
            if os.path.exists(temp_manifest):
                Path(temp_manifest).unlink()
        except Exception as e:
            self.logger.warning(f"Failed to cleanup temp manifest: {e}")
```

**Changes:**
1. Added validation for required transcription parameters
2. Fixed function call signature (removed wrong params, added required params)
3. Changed async pattern to asyncio.to_thread
4. Added proper cleanup error handling
5. Added comprehensive docstring

---

## Example 2: CRITICAL-4 - SpreadManager Missing temp_dir

### BEFORE (Lines 472-491):
```python
async def _run_convert_to_word(self, input_path: Path, output_folder: Path,
                              parameters: Dict[str, Any]) -> bool:
    """Run convert_to_word tool"""
    from fichero.tools.convert_to_word import process_document, SpreadManager

    # Create SpreadManager instance
    spread_manager = SpreadManager()                      # ❌ MISSING temp_dir
    transcription_folder = parameters.get('transcription_folder', None)

    loop = asyncio.get_event_loop()                       # ❌ OLD PATTERN
    result = await loop.run_in_executor(
        None,
        process_document,
        str(input_path),
        output_folder,
        spread_manager,
        transcription_folder
    )

    return 'outputs' in result and len(result.get('outputs', [])) > 0
```

### AFTER (Lines 521-543):
```python
async def _run_convert_to_word(self, input_path: Path, output_folder: Path,
                              parameters: Dict[str, Any]) -> bool:
    """Run convert_to_word tool"""
    from fichero.tools.convert_to_word import process_document, SpreadManager
    import tempfile

    # ✅ CRITICAL-4: SpreadManager requires temp_dir parameter
    # ✅ MAJOR-7: Use context manager for temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        spread_manager = SpreadManager(temp_dir=Path(temp_dir))
        transcription_folder = parameters.get('transcription_folder', None)

        # ✅ CRITICAL-5: Use asyncio.to_thread
        result = await asyncio.to_thread(
            process_document,
            str(input_path),
            output_folder,
            spread_manager,
            transcription_folder
        )

        # ✅ CRITICAL-6: Return value structure (convert_to_word returns 'outputs')
        return 'outputs' in result and len(result.get('outputs', [])) > 0
```

**Changes:**
1. Added temp_dir parameter to SpreadManager
2. Used context manager for automatic cleanup
3. Changed async pattern to asyncio.to_thread
4. Added comments documenting fixes

---

## Example 3: CRITICAL-2 & CRITICAL-3 - Invalid Parameters

### BEFORE: transcribe_lmstudio (Lines 369-396)
```python
result = await loop.run_in_executor(
    None,
    transcribe_batch,
    input_path.parent,
    Path(temp_manifest),
    output_folder,
    parameters.get('api_url', 'http://localhost:1234'),
    parameters.get('model_name', 'llava-1.5-7b-hf'),
    parameters.get('prompt', 'default_transcription')     # ❌ DOESN'T EXIST
)
```

### AFTER: transcribe_lmstudio (Lines 389-423)
```python
result = await asyncio.to_thread(
    transcribe_batch,
    input_path.parent,
    Path(temp_manifest),
    output_folder,
    parameters.get('api_url', 'http://localhost:1234'),
    parameters.get('model_name', 'llava-1.5-7b-hf')
    # ✅ REMOVED: prompt parameter doesn't exist in function signature
)
```

### BEFORE: json_to_excel (Lines 508-525)
```python
output_file = output_folder / f"{input_path.stem}.xlsx"
flatten = parameters.get('flatten', True)

result = await loop.run_in_executor(
    None,
    json_to_excel,
    input_path.parent,
    output_file,
    flatten                                               # ❌ DOESN'T EXIST
)
```

### AFTER: json_to_excel (Lines 560-577)
```python
output_file = output_folder / f"{input_path.stem}.xlsx"

result = await asyncio.to_thread(
    json_to_excel,
    input_path.parent,
    output_file
    # ✅ REMOVED: flatten parameter doesn't exist in function signature
)
```

---

## Summary of Pattern Changes

### Async Pattern (CRITICAL-5)
```python
# BEFORE (19 methods):
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, function, args)

# AFTER (19 methods):
result = await asyncio.to_thread(function, args)
```

### Cleanup Pattern (CRITICAL-7)
```python
# BEFORE (4 methods):
finally:
    Path(temp_manifest).unlink(missing_ok=True)

# AFTER (4 methods):
finally:
    try:
        if os.path.exists(temp_manifest):
            Path(temp_manifest).unlink()
    except Exception as e:
        self.logger.warning(f"Failed to cleanup temp manifest: {e}")
```

### Return Value Pattern (CRITICAL-6)
```python
# Tools returning {'outputs': [...]}:
return 'outputs' in result and len(result.get('outputs', [])) > 0

# Tools returning {'success': N, 'failed': M}:
return result.get('success', 0) > 0

# Tools returning {'success': bool}:
return result.get('success', False)
```

---

**All 15 critical and major issues fixed!**
See PHASE_C_FIX_REPORT.md for complete details.
