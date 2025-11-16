# PHASE B: FIX IMPLEMENTATION INSTRUCTIONS

**Objective:** Fix critical and major issues identified in Phase B code review

**Input:** `PHASE_B_CODE_REVIEW_REPORT.md`

---

## ISSUES TO FIX

### CRITICAL-1: transcribe_lmstudio Parameter Name Mismatch

**Problem:** Schema uses `api_url` but actual tool function uses `lmstudio_url`

**Location:** `tool_registry.py` - `_create_transcribe_lmstudio_schema()`

**Fix:**
```python
# BEFORE:
'api_url': {
    'type': 'string',
    'default': 'http://localhost:1234',
    'label': 'LM Studio URL',
    'description': 'URL of running LM Studio server',
    'required': True,
},

# AFTER:
'lmstudio_url': {
    'type': 'string',
    'default': 'http://localhost:1234',
    'label': 'LM Studio URL',
    'description': 'URL of running LM Studio server',
    'required': True,
},
```

**Verification:** Cross-reference with `src/fichero/tools/transcribe_lmstudio.py` function signature

---

### CRITICAL-2: llm_process Function Name Discovery

**Problem:** TOOL_REFERENCE.md shows `llm_process_batch()` but code review found actual function is `process_documents_batch()`

**Location:** Need to verify actual function signature in `src/fichero/tools/llm_process.py`

**Investigation Required:**
1. Read `src/fichero/tools/llm_process.py` completely
2. Find the actual batch processing function name
3. Identify all parameters with exact names
4. Update schema to match reality

**Expected Fix:** Schema parameter names must match actual function parameters

---

### CRITICAL-3: prepare_images Parameter Verification

**Problem:** TOOL_REFERENCE.md may have wrong parameter names

**Location:** `tool_registry.py` - `_create_prepare_images_schema()`

**Investigation Required:**
1. Read `src/fichero/tools/prepare_images.py`
2. Verify actual parameter names (compression_quality, output_format, max_size)
3. Confirm these are correct or need adjustment

**Expected Fix:** Ensure all parameter names match actual tool signature

---

### MAJOR-1: segment.overlap Type Mismatch

**Problem:** Schema says integer percentage (0-50), but tool may expect pixels or decimal

**Location:** `tool_registry.py` - `_create_segment_schema()`

**Investigation Required:**
1. Read `src/fichero/tools/segment.py`
2. Check if overlap is percentage (0-50) or decimal (0.0-0.5) or pixels
3. Update schema type and range accordingly

**Possible Fix:**
```python
# If it's decimal percentage:
'overlap': {
    'type': 'float',
    'min': 0.0,
    'max': 0.5,
    'default': 0.1,
    'label': 'Overlap',
    'description': 'Overlap fraction between segments (0.0-0.5)',
    'required': False,
},
```

---

### MAJOR-2: segment.max_pixels Default Value

**Problem:** Default of 25,000,000 (25MP) may be too aggressive

**Investigation Required:**
1. Check tool implementation for recommended default
2. Consider typical image sizes in Fichero workflows
3. Adjust default to safer value if needed

**Possible Fix:**
```python
'max_pixels': {
    'type': 'integer',
    'min': 1000000,
    'max': 100000000,
    'default': 10000000,  # 10MP might be safer
    'label': 'Max Pixels',
    'description': 'Maximum pixels before segmenting',
    'required': False,
},
```

---

### MAJOR-3: llm_process Undocumented Parameters

**Problem:** Schema includes `hierarchical` and `folder_mode` but TOOL_REFERENCE.md doesn't document them

**Investigation Required:**
1. Verify these parameters exist in actual tool
2. If they don't exist, remove them from schema
3. If they do exist, verify types and defaults are correct

**Possible Fix:** Remove if not in actual function signature

---

### MAJOR-4: remove_background Missing ai_model Parameter

**Problem:** Schema only has `method`, but tool may have `ai_model` for rembg backend

**Investigation Required:**
1. Read `src/fichero/tools/remove_background.py`
2. Check if ai_model parameter exists
3. Add to schema if it exists

**Possible Fix:**
```python
def _create_remove_background_schema(self):
    return {
        'method': {
            'type': 'enum',
            'values': ['rembg', 'opencv'],
            'default': 'rembg',
            'label': 'Removal Method',
            'description': 'Algorithm to use (rembg is AI-based, opencv is simple)',
            'required': False,
        },
        'ai_model': {  # ADD THIS if it exists
            'type': 'enum',
            'values': ['u2net', 'u2netp', 'u2net_human_seg'],
            'default': 'u2net',
            'label': 'AI Model',
            'description': 'Model to use for rembg method',
            'required': False,
        },
    }
```

---

## IMPLEMENTATION APPROACH

### Phase 1: Investigation (Read All Tool Files)

**Read these files completely:**
1. `src/fichero/tools/transcribe_lmstudio.py`
2. `src/fichero/tools/llm_process.py`
3. `src/fichero/tools/prepare_images.py`
4. `src/fichero/tools/remove_background.py`
5. `src/fichero/tools/segment.py`

**For each file, document:**
- Actual function name used for batch processing
- Complete parameter list with exact names
- Parameter types (from docstrings or type hints)
- Default values (from function signature)
- Required vs optional parameters

---

### Phase 2: Schema Corrections

**For each schema method, apply fixes:**
1. Update parameter names to match actual function
2. Correct parameter types (int/float/enum/string/boolean)
3. Adjust min/max ranges to match tool expectations
4. Update default values to match tool defaults
5. Add missing parameters that exist in tool
6. Remove parameters that don't exist in tool

---

### Phase 3: Verification

**After all fixes:**
1. Read modified `tool_registry.py` completely
2. Verify Python syntax valid
3. Check all parameter names match tools
4. Ensure types appropriate for UI generation
5. Confirm defaults are reasonable

---

## QUALITY CHECKLIST

After fixes applied:
- [ ] All 5 schema methods corrected
- [ ] Parameter names match actual tool signatures
- [ ] Types match tool expectations
- [ ] Min/max values appropriate
- [ ] Default values match tools or are sensible
- [ ] Required flags match tool requirements
- [ ] All parameters documented with labels/descriptions
- [ ] Python syntax valid
- [ ] No CRITICAL issues remaining
- [ ] No MAJOR issues remaining

---

## OUTPUT DELIVERABLE

Create: `PHASE_B_FIX_REPORT.md`

Include:
1. **Investigation Summary:** What actual function signatures were found
2. **Fixes Applied:** Detailed list of all changes made
3. **Parameter Comparison Tables:** Before/After for each tool
4. **Verification Results:** All quality checks passed
5. **Files Modified:** Complete file paths
6. **Remaining Issues:** Any unfixed items (should be none)
7. **Ready for Testing:** Confirmation

---

## IMPORTANT NOTES

- **Source of truth:** Actual tool implementation files, NOT TOOL_REFERENCE.md
- **Cross-reference:** Check against existing plan YAML files for consistency
- **Preserve UI quality:** Keep labels clear, descriptions helpful
- **Backward compatibility:** Don't break existing functionality
- **Document thoroughly:** Code review agent needs clear report

**When complete, report fixes applied and readiness for testing agent.**
