# PHASE B: CODE REVIEW INSTRUCTIONS

**Objective:** Review Phase B implementation for correctness and quality

**Input:** `PHASE_B_IMPLEMENTATION_REPORT.md`

---

## REVIEW CHECKLIST

### 1. Parameter Accuracy
For each of 5 tools, verify:
- [ ] All parameter names match TOOL_REFERENCE.md exactly
- [ ] No misspelled parameter names
- [ ] No missing required parameters
- [ ] No extra parameters not in reference

### 2. Type Validation
For each parameter, check:
- [ ] Type appropriate for parameter (enum/int/float/string/bool)
- [ ] Enum values complete and correct
- [ ] Min/max ranges sensible
- [ ] Default values within valid range

### 3. UI Usability
Review all labels and descriptions:
- [ ] Labels clear and concise (<20 chars)
- [ ] Descriptions helpful for users
- [ ] Technical jargon explained
- [ ] Units specified (px, %, MB, etc.)

### 4. Code Quality
Check implementation:
- [ ] Python syntax valid
- [ ] Follows existing patterns
- [ ] Consistent formatting
- [ ] Docstrings present
- [ ] No code duplication

### 5. Integration Verification
Verify registration:
- [ ] All 5 tools registered in __init__
- [ ] No duplicate keys
- [ ] Method names follow convention
- [ ] Existing tools unchanged

---

## DETAILED PARAMETER REVIEW

### transcribe_lmstudio
**Check against TOOL_REFERENCE.md:**
- [ ] api_url parameter exists (should be lmstudio_url?)
- [ ] model_name values include all supported models
- [ ] prompt values match available templates
- [ ] max_size range appropriate

### llm_process
**Check against TOOL_REFERENCE.md:**
- [ ] prompt_config values match available configs
- [ ] llm backend values include all supported models
- [ ] hierarchical parameter type is boolean
- [ ] folder_mode parameter type is boolean

### prepare_images
**Check against TOOL_REFERENCE.md:**
- [ ] compression_quality range 1-100
- [ ] output_format includes jpg/png/webp
- [ ] max_size range appropriate for images

### remove_background
**Check against TOOL_REFERENCE.md:**
- [ ] method values are rembg and opencv
- [ ] default value is appropriate

### segment
**Check against TOOL_REFERENCE.md:**
- [ ] max_pixels range appropriate
- [ ] overlap percentage range 0-50
- [ ] defaults match tool expectations

---

## CODE STYLE REVIEW

### Consistency Checks
- [ ] All methods follow _create_{tool}_schema() pattern
- [ ] All docstrings follow same format
- [ ] All return dictionaries have same structure
- [ ] Indentation consistent (4 spaces)

### Documentation Quality
- [ ] Method docstrings describe purpose
- [ ] Parameter descriptions are helpful
- [ ] Complex parameters have detailed explanations
- [ ] Units clearly specified

---

## POTENTIAL ISSUES TO IDENTIFY

Look for:
1. **Type mismatches** - Parameter needs int but schema says string
2. **Invalid defaults** - Default outside min/max range
3. **Missing enum values** - Not all options listed
4. **Unclear labels** - User won't understand what it does
5. **Wrong parameter names** - Doesn't match tool signature
6. **Missing required flags** - Required params marked optional

---

## CROSS-REFERENCE VALIDATION

For each parameter, verify against TOOL_REFERENCE.md:
1. Read tool function signature
2. Check parameter name exact match
3. Verify parameter type matches usage
4. Confirm default value is valid
5. Ensure enum values complete

---

## OUTPUT DELIVERABLE

Create: `PHASE_B_CODE_REVIEW_REPORT.md`

Include:
1. **Summary:** Overall quality assessment
2. **Issues Found:** Categorized by severity
3. **Parameter-by-Parameter Review:** Detailed findings
4. **Recommendations:** Specific fixes needed
5. **Approval Status:** Ready for fixes / Ready for testing

---

## SEVERITY CATEGORIES

**CRITICAL:** Will cause runtime errors or crashes
**MAJOR:** Wrong behavior, incorrect results
**MINOR:** Suboptimal but functional
**SUGGESTION:** Potential improvements

---

## REVIEW APPROACH

1. Read PHASE_B_IMPLEMENTATION_REPORT.md
2. Read all 5 schema methods in tool_registry.py
3. Cross-reference each parameter with TOOL_REFERENCE.md
4. Check code style and consistency
5. Validate UI usability
6. Document all findings

Be thorough and identify any discrepancies between implementation and reference documentation.

**When complete, report findings and readiness for fix implementation.**
