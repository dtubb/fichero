# PHASE C: TESTING INSTRUCTIONS

**Objective:** Verify Phase C implementation works correctly after all fixes

**Input:** `PHASE_C_FIX_REPORT.md`

---

## TESTING SCOPE

### What to Test
1. **Module Import** - Can tool_executor.py be imported?
2. **Method Completeness** - Do all 20 tools have _run_{tool}() methods?
3. **Method Signatures** - Are all signatures correct?
4. **Parameter Validation** - Do parameters match Phase B schemas?
5. **Router Integration** - Does _run_tool() dispatch correctly?
6. **Error Handling** - Are exceptions handled properly?

### What NOT to Test (Runtime Execution)
- Do NOT execute actual tools with real data
- Do NOT test with actual collections/documents
- Do NOT verify tool outputs
- Focus on code structure validation, not functionality

---

## TEST CASES

### TEST 1: Module Import Validation
**Objective:** Verify tool_executor.py can be imported without errors

**Method:**
```python
import sys
sys.path.insert(0, 'src')

try:
    from fichero.windows.main.views.shared.tool_executor import ToolExecutor
    print("✅ Module import successful")
except ImportError as e:
    print(f"❌ Import failed: {e}")
except Exception as e:
    print(f"❌ Unexpected error: {e}")
```

**Expected Result:** Module imports successfully, no syntax errors

---

### TEST 2: Method Completeness Check
**Objective:** Verify all 20 tools have dedicated _run_{tool}() methods

**Method:**
```python
from fichero.windows.main.views.shared.tool_executor import ToolExecutor
import inspect

# Expected tools from all phases
expected_tools = [
    'crop', 'rotate', 'enhance', 'split',
    'remove_background', 'prepare_images', 'segment', 'convert_to_svg',
    'transcribe_qwen_max', 'transcribe_lmstudio', 'describe',
    'llm_process', 'analyze_document_groups',
    'convert_to_word', 'json_to_word', 'json_to_excel',
    'recombine', 'fuzzy_clean',
    'extract_library_metadata', 'build_documents_manifest'
]

# Check each tool has method
executor_methods = [m for m in dir(ToolExecutor) if m.startswith('_run_')]
missing = []

for tool in expected_tools:
    method_name = f'_run_{tool}'
    if method_name not in executor_methods:
        missing.append(tool)

if missing:
    print(f"❌ Missing methods: {missing}")
else:
    print(f"✅ All 20 tools have methods")
```

**Expected Result:** All 20 tools have corresponding methods

---

### TEST 3: Method Signature Validation
**Objective:** Verify all methods have correct async signature

**Method:**
```python
import inspect

executor = ToolExecutor(None, None)  # Mock initialization

for tool in expected_tools:
    method = getattr(executor, f'_run_{tool}', None)
    if not method:
        print(f"❌ {tool}: Method not found")
        continue

    # Check async
    if not inspect.iscoroutinefunction(method):
        print(f"❌ {tool}: Not async")
        continue

    # Check signature
    sig = inspect.signature(method)
    params = list(sig.parameters.keys())

    if params != ['self', 'item', 'params']:
        print(f"❌ {tool}: Wrong signature {params}")
        continue

    print(f"✅ {tool}: Signature correct")
```

**Expected Result:** All methods are async with (self, item, params) signature

---

### TEST 4: Parameter Alignment Validation
**Objective:** Cross-reference parameters with Phase B schemas

**Method:**
For each of the 10 tools with Phase B schemas, verify parameters match:

```python
from fichero.windows.main.views.shared.tool_registry import ToolRegistry

registry = ToolRegistry()

# Tools with schemas from Phase B
schema_tools = {
    'transcribe_lmstudio': ['api_url', 'model_name'],
    'llm_process': ['prompt_config', 'llm', 'folder_mode'],
    'prepare_images': ['compression_quality', 'output_format', 'max_size'],
    'remove_background': ['method', 'ai_model'],
    'segment': ['skip_processing'],
}

# Read tool_executor.py and verify parameters used match schemas
# (Static analysis - parse source code to find params.get() calls)
```

**Expected Result:** All parameters in code match Phase B schema definitions

---

### TEST 5: Router Dispatch Validation
**Objective:** Verify _run_tool() correctly routes all 20 tools

**Method:**
```python
# Check router implementation
import inspect

executor = ToolExecutor(None, None)
source = inspect.getsource(executor._run_tool)

# Verify uses dynamic dispatch
if 'getattr' in source and 'f"_run_{tool_name}"' in source:
    print("✅ Router uses dynamic dispatch")
else:
    print("❌ Router not using dynamic dispatch")

# Verify error handling for unknown tools
if 'hasattr' in source or 'AttributeError' in source:
    print("✅ Router has unknown tool handling")
else:
    print("⚠️  Router may not handle unknown tools")
```

**Expected Result:** Router uses dynamic dispatch with error handling

---

### TEST 6: Error Handling Validation
**Objective:** Verify comprehensive error handling in all methods

**Method:**
```python
import inspect

errors_found = []

for tool in expected_tools:
    method = getattr(executor, f'_run_{tool}')
    source = inspect.getsource(method)

    # Check for try/except
    if 'try:' not in source or 'except' not in source:
        errors_found.append(f"{tool}: No try/except")

    # Check for finally (cleanup)
    if 'finally:' in source:
        # Good - has cleanup
        pass
    elif 'tempfile' in source or 'temp' in source.lower():
        errors_found.append(f"{tool}: Temp files but no finally")

    # Check for logging
    if 'self.logger' not in source:
        errors_found.append(f"{tool}: No logging")

if errors_found:
    for error in errors_found:
        print(f"⚠️  {error}")
else:
    print("✅ All methods have proper error handling")
```

**Expected Result:** All methods have try/except, cleanup, and logging

---

### TEST 7: Async Pattern Validation
**Objective:** Verify all methods use asyncio.to_thread (not old pattern)

**Method:**
```python
import inspect

old_pattern_found = []

for tool in expected_tools:
    method = getattr(executor, f'_run_{tool}')
    source = inspect.getsource(method)

    # Check for old pattern
    if 'run_in_executor' in source or 'get_event_loop()' in source:
        old_pattern_found.append(tool)

    # Should have asyncio.to_thread
    if 'asyncio.to_thread' not in source and 'await' in source:
        # Might be calling another async function
        pass

if old_pattern_found:
    print(f"❌ Old async pattern found in: {old_pattern_found}")
else:
    print("✅ All methods use modern async pattern")
```

**Expected Result:** No old `run_in_executor` pattern, all use `asyncio.to_thread`

---

### TEST 8: Import Path Validation
**Objective:** Verify all tool imports use correct paths

**Method:**
```python
import inspect

import_errors = []

for tool in expected_tools:
    method = getattr(executor, f'_run_{tool}')
    source = inspect.getsource(method)

    # Extract import statement
    import_lines = [line for line in source.split('\n') if 'from fichero.tools' in line]

    if not import_lines:
        import_errors.append(f"{tool}: No import found")
        continue

    # Verify path format
    for line in import_lines:
        if f'from fichero.tools.{tool}' not in line:
            # Some tools have different module names
            # Verify manually or check against known mappings
            pass

if import_errors:
    for error in import_errors:
        print(f"⚠️  {error}")
else:
    print("✅ All imports look correct")
```

**Expected Result:** All imports use correct module paths

---

### TEST 9: Return Value Structure Validation
**Objective:** Verify return values follow consistent structure

**Method:**
```python
import inspect
import re

return_patterns = []

for tool in expected_tools:
    method = getattr(executor, f'_run_{tool}')
    source = inspect.getsource(method)

    # Find return statements
    returns = re.findall(r'return\s+{[^}]+}', source)

    for ret in returns:
        # Check has 'success' key
        if "'success'" not in ret and '"success"' not in ret:
            print(f"⚠️  {tool}: Return missing 'success' key")

        # Should not check for 'outputs' (that was the bug)
        if "'outputs' in result" in source or '"outputs" in result' in source:
            print(f"❌ {tool}: Still checking for 'outputs' in result")

print("✅ Return value validation complete")
```

**Expected Result:** Returns have 'success', don't check for 'outputs'

---

### TEST 10: Cross-Reference with Phase B Schemas
**Objective:** Verify parameter usage matches schema definitions exactly

**For each tool with Phase B schema:**

**transcribe_lmstudio:**
- [ ] Uses `api_url` parameter (correct name from schema)
- [ ] Uses `model_name` parameter
- [ ] Does NOT use `prompt` parameter (was bug, should be removed)

**llm_process:**
- [ ] Uses `prompt_config` parameter
- [ ] Uses `llm` parameter
- [ ] Uses `folder_mode` parameter

**prepare_images:**
- [ ] Uses `compression_quality` with default 85
- [ ] Uses `output_format` parameter
- [ ] Uses `max_size` parameter

**remove_background:**
- [ ] Uses `method` parameter with values 'ai'/'opencv'
- [ ] Uses `ai_model` parameter

**segment:**
- [ ] Uses `skip_processing` parameter
- [ ] Does NOT use `max_pixels` or `overlap` (were removed)

**Expected Result:** Perfect alignment with Phase B schemas

---

## INTEGRATION CHECKS

### Check 1: Integration Score Calculation
**Before Phase C:** 3/20 tools (15%)
**After Phase C:** Should be 20/20 tools (100%)

**Verify:** Count _run_{tool} methods = 20

---

### Check 2: No Regressions
**Verify:**
- [ ] _run_crop() still works (existing method)
- [ ] _run_rotate() still works (existing method)
- [ ] _run_transcribe_qwen() still works (existing method)
- [ ] No changes to working methods

---

### Check 3: Phase B Compatibility
**Verify:**
- [ ] All 10 Phase B schema tools have compatible implementations
- [ ] Parameter names match exactly
- [ ] Default values match schemas

---

## QUALITY METRICS

Calculate and report:
1. **Method Completeness Rate:** Should be 100% (20/20 methods exist)
2. **Signature Correctness Rate:** Should be 100% (all async with correct params)
3. **Error Handling Rate:** Should be 100% (all have try/except)
4. **Parameter Alignment Rate:** Should be 100% (all match Phase B schemas)
5. **Integration Score:** Should be 100% (20/20 tools)
6. **Regression Rate:** Should be 0% (no existing features broken)

---

## OUTPUT DELIVERABLE

Create: `PHASE_C_TESTING_REPORT.md`

Include:
1. **Test Results Summary:** Pass/fail for each of 10 tests
2. **Metrics:** All quality metrics calculated
3. **Issues Found:** Any problems discovered (should be none after fixes)
4. **Integration Verification:** Coverage check (15% → 100%)
5. **Phase B Alignment:** Parameter matching verification
6. **Approval Status:** APPROVED / REJECTED with reasons
7. **Recommendations:** Any final suggestions

---

## TESTING APPROACH

1. **Static Analysis:** Parse and validate without execution
2. **Import Testing:** Verify module can be imported
3. **Signature Validation:** Check method signatures correct
4. **Parameter Cross-Reference:** Verify against Phase B schemas
5. **Code Pattern Analysis:** Check async, error handling, cleanup
6. **Integration Verification:** Confirm 100% coverage achieved

**DO NOT execute actual tools** - focus on code structure validation only

---

**When complete, report test results and final approval status.**
