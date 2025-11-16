# PHASE A: TESTING INSTRUCTIONS

**Objective:** Verify Phase A implementation works correctly after fixes

**Input:** `PHASE_A_FIX_REPORT.md`

---

## TESTING SCOPE

### What to Test
1. **Plan File Validity** - Can Director load all 7 plans?
2. **TOOL_CONFIGS Integration** - Are all 7 tools in GUI menus?
3. **Function Resolution** - Can all tool functions be imported?
4. **Parameter Validation** - Are all parameters valid for tools?
5. **YAML Syntax** - Do all plans parse without errors?

### What NOT to Test (Runtime Execution)
- Do NOT actually execute workflows
- Do NOT test with real data
- Do NOT verify tool outputs
- Focus on integration, not functionality

---

## TEST CASES

### TEST 1: YAML Syntax Validation
**Objective:** Verify all 7 plan files have valid YAML syntax

**Method:**
```python
import yaml
plan_files = [
    'TranscribeLMStudio.yml',
    'JsonToExcel.yml',
    'JsonToWord.yml',
    'ConvertToSVG.yml',
    'AnalyzeGroups.yml',
    'ExtractMetadata.yml',
    'FuzzyClean.yml'
]
for plan_file in plan_files:
    with open(f'src/fichero/resources/config_defaults/plans/{plan_file}') as f:
        yaml.safe_load(f)  # Should not raise exception
```

**Expected Result:** All files parse without errors

---

### TEST 2: Plan Structure Validation
**Objective:** Verify all plans have required fields

**Check for each plan:**
- [ ] Has `title` field
- [ ] Has `description` field
- [ ] Has `workflows` dictionary
- [ ] Has `commands` list
- [ ] Workflow references all commands
- [ ] All referenced commands exist

**Method:** Parse YAML and validate structure

---

### TEST 3: Function Path Verification
**Objective:** Verify all tool functions can be imported

**Method:**
```python
function_paths = {
    'transcribe_lmstudio': 'fichero.tools.transcribe_lmstudio.transcribe_batch',
    'json_to_excel': 'fichero.tools.json_to_excel.json_to_excel',
    'json_to_word': 'fichero.tools.json_to_word.json_to_word_batch',
    'convert_to_svg': 'fichero.tools.convert_to_svg.convert_to_svg_batch',
    'analyze_document_groups': 'fichero.tools.analyze_document_groups.analyze_document_groups_batch',
    'extract_library_metadata': 'fichero.tools.extract_library_metadata.extract_metadata_batch',
    'fuzzy_clean': 'fichero.tools.fuzzy_clean.fuzzy_clean_batch',
}

for tool, func_path in function_paths.items():
    module_path, func_name = func_path.rsplit('.', 1)
    module = __import__(module_path, fromlist=[func_name])
    func = getattr(module, func_name)  # Should not raise AttributeError
```

**Expected Result:** All functions importable

---

### TEST 4: TOOL_CONFIGS Validation
**Objective:** Verify CollectionView has all 7 new tools

**Method:**
1. Read `collection_view.py`
2. Parse TOOL_CONFIGS dictionary
3. Verify entries exist:
   - `'transcribe_lmstudio': ('TranscribeLMStudio', 'TranscribeLMStudioTest')`
   - `'json_to_excel': ('JsonToExcel', 'JsonToExcelTest')`
   - `'json_to_word': ('JsonToWord', 'JsonToWordTest')`
   - `'convert_to_svg': ('ConvertToSVG', 'ConvertToSVGTest')`
   - `'analyze_document_groups': ('AnalyzeGroups', 'AnalyzeGroupsTest')`
   - `'extract_library_metadata': ('ExtractMetadata', 'ExtractMetadataTest')`
   - `'fuzzy_clean': ('FuzzyClean', 'FuzzyCleanTest')`

**Expected Result:** All 7 entries present with correct values

---

### TEST 5: Plan-TOOL_CONFIGS Consistency
**Objective:** Verify plan names match TOOL_CONFIGS references

**For each tool:**
- [ ] Plan file name matches TOOL_CONFIGS plan name
- [ ] Workflow name in plan matches TOOL_CONFIGS workflow name
- [ ] Workflow exists in plan file

**Example:**
```
TOOL_CONFIGS: 'transcribe_lmstudio': ('TranscribeLMStudio', 'TranscribeLMStudioTest')
Plan file: TranscribeLMStudio.yml
Workflow in file: TranscribeLMStudioTest
```

**Expected Result:** Perfect alignment for all 7 tools

---

### TEST 6: Parameter Completeness Check
**Objective:** Verify all required parameters present

**For each plan, check:**
- [ ] source_folder parameter (if batch tool)
- [ ] output_folder or output_file parameter
- [ ] source_manifest parameter (if needed)
- [ ] Tool-specific required parameters

**Cross-reference with TOOL_REFERENCE.md**

**Expected Result:** All required parameters present

---

### TEST 7: Dynamic Handler Generation Test
**Objective:** Verify _create_tool_handlers() will work

**Check:**
- [ ] TOOL_CONFIGS keys are valid Python identifiers (or convertible)
- [ ] Plan names don't have special characters
- [ ] Workflow names don't have special characters

**Expected Result:** All names valid for Python method generation

---

## INTEGRATION CHECKS

### Check 1: Menu Coverage Calculation
**Before Phase A:** 12/20 tools (60%)
**After Phase A:** Should be 19/20 tools (95%)

**Verify:** Count entries in TOOL_CONFIGS

---

### Check 2: Plan File Count
**Before Phase A:** 14 standalone test plans
**After Phase A:** Should be 21 standalone test plans

**Verify:** Count .yml files in plans/ directory

---

### Check 3: No Regressions
**Verify:**
- [ ] All 12 existing TOOL_CONFIGS entries unchanged
- [ ] All existing plan files unchanged
- [ ] No syntax errors introduced
- [ ] No duplicate entries created

---

## EDGE CASE TESTING

### Edge Case 1: Missing Dependencies
**What if:** Tool dependency not installed (e.g., LMStudio)
**Expected:** Plan loads, but execution would fail gracefully
**Test:** Verify plan can be loaded without dependency present

### Edge Case 2: Invalid Paths
**What if:** Output folder doesn't exist
**Expected:** Tool should create folder or fail gracefully
**Test:** Check if paths are relative (good) or absolute (bad)

### Edge Case 3: Empty Inputs
**What if:** No files in source_folder
**Expected:** Tool should handle gracefully
**Test:** Verify manifest chaining allows empty results

---

## QUALITY METRICS

Calculate and report:
1. **YAML Validity Rate:** Should be 100% (7/7 valid)
2. **Function Resolution Rate:** Should be 100% (7/7 importable)
3. **Parameter Completeness Rate:** Should be 100%
4. **Integration Score:** Should reach 90%
5. **Regression Rate:** Should be 0% (no existing features broken)

---

## OUTPUT DELIVERABLE

Create: `PHASE_A_TESTING_REPORT.md`

Include:
1. **Test Results Summary:** Pass/fail for each test
2. **Metrics:** All quality metrics calculated
3. **Issues Found:** Any problems discovered (should be none)
4. **Integration Verification:** Coverage and plan count checks
5. **Approval Status:** APPROVED / REJECTED with reasons
6. **Recommendations:** Any final suggestions

---

## TESTING APPROACH

1. **Static Analysis:** Parse and validate without execution
2. **Import Testing:** Verify functions exist and are importable
3. **Structure Validation:** Check YAML and code structure
4. **Integration Verification:** Confirm menu coverage increase
5. **Regression Testing:** Ensure no existing features broken

**DO NOT execute actual workflows - focus on integration testing only**

**When complete, report test results and final approval status.**
