# PHASE C: CODE REVIEW INSTRUCTIONS

**Objective:** Review Phase C implementation for correctness and quality

**Input:** `PHASE_C_IMPLEMENTATION_REPORT.md`

---

## REVIEW CHECKLIST

### 1. Method Completeness
For all 20 tools, verify:
- [ ] _run_{tool}() method exists in tool_executor.py
- [ ] Method signature correct: `async def _run_{tool}(self, item, params)`
- [ ] Method has docstring
- [ ] Method properly documented with Args/Returns/Raises

### 2. Implementation Correctness
For each method, check:
- [ ] Correct tool import path
- [ ] Function name matches actual implementation
- [ ] async/await pattern used correctly
- [ ] asyncio.to_thread used for CPU-bound operations
- [ ] Parameter names match schema definitions

### 3. Error Handling
Review all methods for:
- [ ] try/except blocks present
- [ ] Specific exceptions caught (ValueError, RuntimeError, etc.)
- [ ] Error messages informative
- [ ] Logging used appropriately
- [ ] Failures don't crash application

### 4. Code Quality
Check implementation:
- [ ] Python syntax valid
- [ ] Consistent code style
- [ ] No code duplication
- [ ] Proper indentation (4 spaces)
- [ ] Import statements organized

### 5. Router Integration
Verify _run_tool() dispatch:
- [ ] Routes all 20 tools correctly
- [ ] Handles unknown tools gracefully
- [ ] Error message helpful if tool not found
- [ ] Method lookup uses proper Python idioms

### 6. Single vs Batch Strategy
For each tool implementation:
- [ ] Document whether using single or batch function
- [ ] If batch, verify manifest handling correct
- [ ] If single, verify function exists in tool module
- [ ] Temporary file handling safe (if needed)

---

## DETAILED CHECKS PER CATEGORY

### Image Processing Tools (7 tools)

**enhance, split, remove_background, prepare_images, segment, convert_to_svg**

Verify:
- [ ] Correct import: `from fichero.tools.{tool} import ...`
- [ ] Parameters match Phase B schemas
- [ ] Image path handling correct
- [ ] Output path handling correct

**crop, rotate** (already implemented)
- [ ] Verify not modified accidentally
- [ ] Confirm still working

### AI Processing Tools (5 tools)

**transcribe_lmstudio, describe, llm_process, analyze_document_groups**

Verify:
- [ ] API URLs/endpoints correct
- [ ] Model parameters match schemas
- [ ] GPU/CPU worker consideration
- [ ] Async handling for network calls

**transcribe_qwen_max** (already implemented)
- [ ] Verify not modified

### Document Generation Tools (3 tools)

**convert_to_word, json_to_word, json_to_excel**

Verify:
- [ ] Input file type correct (image/json)
- [ ] Output file path handling
- [ ] Template parameters correct

### Text Processing Tools (2 tools)

**recombine, fuzzy_clean**

Verify:
- [ ] Text file handling
- [ ] Encoding considerations
- [ ] Output format correct

### Utility Tools (3 tools)

**extract_library_metadata, build_documents_manifest**

Verify:
- [ ] Database path handling (if applicable)
- [ ] Manifest format correct
- [ ] Collection ID handling

---

## CROSS-REFERENCE VALIDATION

For each tool, verify against actual implementation:

1. **Read tool source file** (`src/fichero/tools/{tool}/`)
2. **Identify function used** (single vs batch)
3. **Check function signature** matches call in _run_{tool}()
4. **Verify parameter names** match exactly
5. **Confirm return value** structure expected

---

## COMMON ISSUES TO IDENTIFY

Look for:
1. **Import errors** - Wrong module path or function name
2. **Parameter mismatches** - Name doesn't match tool signature
3. **Missing error handling** - No try/except block
4. **Incorrect async pattern** - Using sync when should be async
5. **Resource leaks** - Temp files not cleaned up
6. **Type errors** - Passing wrong type to function
7. **Missing validation** - Not checking required parameters

---

## INTEGRATION VERIFICATION

Check:
- [ ] All 20 tools in _run_tool() routing
- [ ] No duplicate method names
- [ ] No orphaned code
- [ ] Import statements at top of file
- [ ] No circular imports

---

## PERFORMANCE CONSIDERATIONS

Review:
- [ ] CPU-bound operations use asyncio.to_thread
- [ ] I/O-bound operations use async/await
- [ ] No blocking operations in async methods
- [ ] Reasonable timeout handling (if applicable)

---

## OUTPUT DELIVERABLE

Create: `PHASE_C_CODE_REVIEW_REPORT.md`

Include:
1. **Summary:** Overall quality assessment
2. **Issues Found:** Categorized by severity
   - CRITICAL: Will cause crashes
   - MAJOR: Wrong behavior
   - MINOR: Suboptimal but works
   - SUGGESTION: Improvements
3. **Method-by-Method Review:** Findings for each of 17 new methods
4. **Implementation Strategy Review:** Single vs batch approach assessment
5. **Recommendations:** Specific fixes needed
6. **Approval Status:** Ready for fixes / Ready for testing

---

## SEVERITY CATEGORIES

**CRITICAL:** Prevents execution, causes crashes, data loss
**MAJOR:** Wrong results, incorrect behavior, poor error handling
**MINOR:** Works but suboptimal, style issues
**SUGGESTION:** Potential improvements, future enhancements

---

## REVIEW APPROACH

1. Read PHASE_C_IMPLEMENTATION_REPORT.md completely
2. Read tool_executor.py completely
3. For each new method:
   - Verify imports correct
   - Check function calls match reality
   - Validate parameter handling
   - Review error handling
4. Cross-reference with tool source files
5. Check integration with existing code
6. Document all findings

**Be thorough - this is the foundation for direct execution.**

**When complete, report findings and readiness for fix implementation.**
