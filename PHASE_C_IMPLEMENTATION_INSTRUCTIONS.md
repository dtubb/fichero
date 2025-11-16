# PHASE C: FULL DIRECT EXECUTION IMPLEMENTATION INSTRUCTIONS

**Objective:** Enable ToolExecutor direct execution for remaining 17 tools

**Current Status:** 3/20 tools have ToolExecutor methods (15%)
**Target Status:** 20/20 tools have ToolExecutor methods (100%)

---

## CONTEXT

From Phase A & B, we already have:
- ✅ 19/20 tools in TOOL_CONFIGS (95% menu coverage)
- ✅ 10/20 tools with parameter schemas (50% parameter UI)
- ✅ All 20 tools executable via workflow system (Pattern 1)
- ⚠️ Only 3/20 tools have ToolExecutor direct execution (Pattern 3)

**Phase C Goal:** Implement direct execution for remaining 17 tools

---

## WHAT IS TOOLEXECUTOR?

**File:** `src/fichero/windows/main/views/shared/tool_executor.py`

**Purpose:** Direct single-item tool execution (Pattern 3 from GUI_INTEGRATION_STATUS.md)

**Pattern 3: ToolExecutor Direct Execution**
```
User → CollectionView → ToolExecutor._run_{tool}() → Backend Tool → Result
```

**Current Implementation (3 tools):**
1. `_run_crop()` - Direct crop execution
2. `_run_rotate()` - Direct rotate execution
3. `_run_transcribe_qwen()` - Direct transcribe execution

**Need to Add (17 tools):**
- enhance, split, remove_background, prepare_images, segment, convert_to_svg
- transcribe_lmstudio, describe, llm_process, analyze_document_groups
- convert_to_word, json_to_word, json_to_excel
- recombine, fuzzy_clean
- extract_library_metadata, build_documents_manifest

---

## TOOLEXECUTOR ARCHITECTURE

### Main Methods

**`execute_tool(tool_name, item, params)`** (Lines 50-138)
- Entry point for all tool executions
- Validates item type and parameters
- Dispatches to specific `_run_{tool}()` method

**`_run_tool(tool_name, item, params)`** (Lines 159-178)
- Router that calls appropriate `_run_{tool}()` method
- Uses dynamic method lookup: `getattr(self, f"_run_{tool_name}")`

**Individual `_run_{tool}()` methods** (Lines 184-259)
- Tool-specific execution logic
- Handle single items (not batch)
- Return results or raise exceptions

### Execution Flow

```python
# 1. CollectionView calls ToolExecutor
result = await self.tool_executor.execute_tool(
    tool_name='crop',
    item={'id': '123', 'path': '/path/to/image.jpg'},
    params={'template': 'auto', 'padding': 30}
)

# 2. execute_tool validates and dispatches
def execute_tool(self, tool_name, item, params):
    # Validation
    if not item or 'path' not in item:
        raise ValueError("Invalid item")

    # Dispatch
    return await self._run_tool(tool_name, item, params)

# 3. _run_tool routes to specific method
def _run_tool(self, tool_name, item, params):
    method = getattr(self, f"_run_{tool_name}")
    return await method(item, params)

# 4. Specific method executes tool
async def _run_crop(self, item, params):
    from fichero.tools.crop import crop_single
    result = await asyncio.to_thread(
        crop_single,
        image_path=item['path'],
        **params
    )
    return result
```

---

## IMPLEMENTATION PATTERN

Each tool needs a `_run_{tool}()` method following this template:

```python
async def _run_{tool}(self, item, params):
    """Execute {tool} on a single item

    Args:
        item: Dict with 'id', 'path', and metadata
        params: Dict of tool parameters from schema

    Returns:
        Dict with execution results

    Raises:
        ValueError: If parameters invalid
        RuntimeError: If execution fails
    """
    try:
        # Import tool function (single-item, not batch)
        from fichero.tools.{tool} import {tool}_single

        # Execute tool in thread (if CPU-bound)
        result = await asyncio.to_thread(
            {tool}_single,
            input_path=item['path'],
            **params
        )

        # Return result
        return {
            'success': True,
            'output_path': result.get('output_path'),
            'metadata': result.get('metadata', {}),
        }

    except Exception as e:
        self.logger.error(f"{tool} execution failed: {e}")
        raise RuntimeError(f"Failed to execute {tool}: {str(e)}")
```

---

## TOOL-SPECIFIC IMPLEMENTATION DETAILS

### Image Processing Tools

**enhance** - `_run_enhance()`
```python
from fichero.tools.enhance import enhance_single

result = await asyncio.to_thread(
    enhance_single,
    image_path=item['path'],
    contrast=params.get('contrast', 1.2),
    brightness=params.get('brightness', 1.1),
)
```

**split** - `_run_split()`
```python
from fichero.tools.split import split_single

result = await asyncio.to_thread(
    split_single,
    image_path=item['path'],
    method=params.get('method', 'auto'),
)
```

**remove_background** - `_run_remove_background()`
```python
from fichero.tools.remove_background import remove_background_single

result = await asyncio.to_thread(
    remove_background_single,
    image_path=item['path'],
    method=params.get('method', 'opencv'),
    ai_model=params.get('ai_model', 'u2net'),
)
```

**prepare_images** - `_run_prepare_images()`
```python
from fichero.tools.prepare_images import prepare_single

result = await asyncio.to_thread(
    prepare_single,
    image_path=item['path'],
    compression_quality=params.get('compression_quality', 85),
    output_format=params.get('output_format', 'jpg'),
    max_size=params.get('max_size', 4096),
)
```

**segment** - `_run_segment()`
```python
from fichero.tools.segment import segment_single

result = await asyncio.to_thread(
    segment_single,
    image_path=item['path'],
    skip_processing=params.get('skip_processing', True),
)
```

**convert_to_svg** - `_run_convert_to_svg()`
```python
from fichero.tools.convert_to_svg import convert_single

result = await asyncio.to_thread(
    convert_single,
    image_path=item['path'],
    use_potrace=params.get('use_potrace', True),
    svg_format=params.get('svg_format', 'simple'),
)
```

---

### AI Processing Tools

**transcribe_lmstudio** - `_run_transcribe_lmstudio()`
```python
from fichero.tools.transcribe_lmstudio import transcribe_single

result = await asyncio.to_thread(
    transcribe_single,
    image_path=item['path'],
    api_url=params.get('api_url', 'http://localhost:1234'),
    model_name=params.get('model_name', 'llava-1.5-7b-hf'),
    prompt=params.get('prompt', 'default_transcription'),
)
```

**describe** - `_run_describe()`
```python
from fichero.tools.describe import describe_single

result = await asyncio.to_thread(
    describe_single,
    image_path=item['path'],
    llm=params.get('llm', 'qwen-max'),
    prompt=params.get('prompt', 'default_description'),
)
```

**llm_process** - `_run_llm_process()`
```python
from fichero.tools.llm_process import process_single

result = await asyncio.to_thread(
    process_single,
    transcription_path=item.get('transcription_path'),
    prompt_config=params.get('prompt_config', 'catalogue_generic'),
    llm=params.get('llm', 'qwen-max'),
    folder_mode=params.get('folder_mode', False),
)
```

**analyze_document_groups** - `_run_analyze_document_groups()`
```python
from fichero.tools.analyze_document_groups import analyze_single

result = await asyncio.to_thread(
    analyze_single,
    folder_path=item['path'],
    llm=params.get('llm', 'qwen-max'),
    prompt=params.get('prompt', 'default_analysis'),
)
```

---

### Document Generation Tools

**convert_to_word** - `_run_convert_to_word()`
```python
from fichero.tools.convert_to_word import convert_single

result = await asyncio.to_thread(
    convert_single,
    image_path=item['path'],
    transcription_path=item.get('transcription_path'),
    template=params.get('template', 'side_by_side'),
)
```

**json_to_word** - `_run_json_to_word()`
```python
from fichero.tools.json_to_word import json_to_word_single

result = await asyncio.to_thread(
    json_to_word_single,
    json_path=item['path'],
    template=params.get('template', 'default'),
)
```

**json_to_excel** - `_run_json_to_excel()`
```python
from fichero.tools.json_to_excel import json_to_excel

result = await asyncio.to_thread(
    json_to_excel,
    json_file=item['path'],
    output_file=params.get('output_file', '/tmp/output.xlsx'),
    flatten=params.get('flatten', True),
)
```

---

### Text Processing Tools

**recombine** - `_run_recombine()`
```python
from fichero.tools.recombine import recombine_single

result = await asyncio.to_thread(
    recombine_single,
    segments_folder=item['path'],
)
```

**fuzzy_clean** - `_run_fuzzy_clean()`
```python
from fichero.tools.fuzzy_clean import fuzzy_clean_single

result = await asyncio.to_thread(
    fuzzy_clean_single,
    text_path=item['path'],
    similarity_threshold=params.get('similarity_threshold', 0.8),
)
```

---

### Utility Tools

**extract_library_metadata** - `_run_extract_library_metadata()`
```python
from fichero.tools.extract_library_metadata import extract_metadata_single

result = await asyncio.to_thread(
    extract_metadata_single,
    collection_id=item.get('collection_id'),
    library_db_path=params.get('library_db_path'),
)
```

**build_documents_manifest** - `_run_build_documents_manifest()`
```python
from fichero.tools.build_documents_manifest import build_manifest_single

result = await asyncio.to_thread(
    build_manifest_single,
    folder_path=item['path'],
)
```

---

## IMPLEMENTATION STEPS

### Step 1: Verify Tool Functions Exist

For each tool, check if `{tool}_single()` function exists:
1. Read tool implementation file
2. Look for single-item function (not batch)
3. If only batch exists, note need to create single-item wrapper

**Note:** Most tools may only have `{tool}_batch()` functions. You may need to create `{tool}_single()` wrappers.

### Step 2: Add _run_{tool}() Methods

In `tool_executor.py`:
1. Read current file completely
2. Add 17 new `_run_{tool}()` methods
3. Follow existing pattern (see `_run_crop()` example)
4. Use proper imports and error handling

### Step 3: Update _run_tool() Router

Ensure `_run_tool()` method properly routes all 20 tools:
```python
def _run_tool(self, tool_name, item, params):
    """Route to specific tool execution method"""
    method_name = f"_run_{tool_name}"
    if not hasattr(self, method_name):
        raise ValueError(f"Tool {tool_name} not implemented in ToolExecutor")

    method = getattr(self, method_name)
    return await method(item, params)
```

### Step 4: Verify Implementation

After adding all methods:
1. Check Python syntax valid
2. Verify all imports correct
3. Ensure error handling consistent
4. Test method dispatch works

---

## IMPORTANT CONSIDERATIONS

### Single vs Batch Functions

**Most tools only have batch functions.** You may need to:

**Option A: Call batch function with single item**
```python
async def _run_enhance(self, item, params):
    from fichero.tools.enhance import enhance_batch

    # Create temporary manifest with single item
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl') as f:
        json.dump({'path': item['path']}, f)
        f.flush()

        result = await asyncio.to_thread(
            enhance_batch,
            source_manifest=f.name,
            output_folder='/tmp/enhance_output',
            **params
        )
```

**Option B: Extract core logic into shared function** (better, but more work)
```python
# In fichero/tools/enhance.py - add new function:
def enhance_single(image_path, **params):
    """Enhance a single image"""
    # Core enhancement logic here
    return result

def enhance_batch(source_manifest, output_folder, **params):
    """Enhance batch of images"""
    for item in read_manifest(source_manifest):
        enhance_single(item['path'], **params)
```

**Recommendation:** Use Option A for Phase C (faster). Option B can be done in future refactor.

---

## QUALITY CHECKLIST

After implementation:
- [ ] All 17 new _run_{tool}() methods created
- [ ] All methods have docstrings
- [ ] All methods follow async pattern
- [ ] All methods use asyncio.to_thread for CPU-bound work
- [ ] All methods have proper error handling
- [ ] All imports are correct
- [ ] All parameter names match schemas
- [ ] Python syntax valid
- [ ] No code duplication

---

## OUTPUT DELIVERABLE

Create: `PHASE_C_IMPLEMENTATION_REPORT.md`

Include:
1. **Methods Created:** List of 17 new _run_{tool}() methods
2. **Implementation Approach:** Single vs batch function strategy
3. **Verification Results:** All checks passed
4. **Integration Score:** New percentage (should be 100%)
5. **Code Statistics:** Lines added, methods count
6. **Testing Instructions:** How to test direct execution

---

## TESTING STRATEGY

For Phase C Testing Agent:
- Import tool_executor module successfully
- Verify all 20 methods exist
- Check method signatures correct
- Validate error handling works
- Cross-reference with parameter schemas

**DO NOT execute actual tools** - focus on code structure validation

---

**When complete, report ready for Phase C Code Review.**
