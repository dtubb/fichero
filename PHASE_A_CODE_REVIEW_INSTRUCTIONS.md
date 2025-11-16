# PHASE A: CODE REVIEW INSTRUCTIONS

**Objective:** Review Phase A implementation for quality, correctness, and potential issues

**Input:** `PHASE_A_IMPLEMENTATION_REPORT.md`

---

## REVIEW CHECKLIST

### 1. YAML Syntax & Structure
- [ ] All 7 plan files have valid YAML syntax
- [ ] Proper indentation (2 spaces, no tabs)
- [ ] All required fields present (title, description, workflows, commands)
- [ ] Workflow names match TOOL_CONFIGS entries
- [ ] Command names referenced in workflows exist

### 2. Function Paths & Module Imports
- [ ] All function paths valid (fichero.tools.{tool}.{function}_batch)
- [ ] Function names match actual tool implementations
- [ ] Worker types appropriate (cpu vs gpu)
- [ ] Cross-reference with TOOL_REFERENCE.md

### 3. Parameter Validation
- [ ] All required parameters present in args
- [ ] Parameter types correct (strings, ints, paths)
- [ ] Default values reasonable
- [ ] Optional parameters documented
- [ ] No missing critical parameters

### 4. Output Paths & Manifests
- [ ] Output folder paths follow convention
- [ ] Manifest files properly referenced
- [ ] Manifest chaining correct (output → next input)
- [ ] No path conflicts

### 5. CollectionView Integration
- [ ] TOOL_CONFIGS entries syntactically correct
- [ ] No duplicate keys
- [ ] Plan names match workflow files
- [ ] Workflow names match within plans
- [ ] Existing entries unchanged

### 6. Edge Cases & Error Handling
- [ ] What if plan file missing?
- [ ] What if function doesn't exist?
- [ ] What if parameters invalid?
- [ ] What if output folder can't be created?

### 7. Cross-Platform Compatibility
- [ ] Paths work on macOS/Windows/Linux
- [ ] No hardcoded absolute paths
- [ ] Worker type availability checked

---

## SPECIFIC CHECKS PER TOOL

### transcribe_lmstudio
- [ ] Function name: `transcribe_batch` (not transcribe_lmstudio_batch)
- [ ] Worker type: "gpu" appropriate
- [ ] Parameters: lmstudio_url, model_name, prompt all present
- [ ] LMStudio availability not assumed

### json_to_excel
- [ ] Function signature matches (uses output_file not output_folder)
- [ ] Requires JSON input from previous step
- [ ] Excel library dependency available

### json_to_word
- [ ] Similar to convert_to_word but different templates
- [ ] JSON input properly referenced
- [ ] Word document library available

### convert_to_svg
- [ ] Potrace dependency noted
- [ ] Image + text input both required
- [ ] SVG output path correct

### analyze_document_groups
- [ ] GPU worker type for AI model
- [ ] Prompt parameter included
- [ ] Group analysis logic matches tool

### extract_library_metadata
- [ ] Library database path required
- [ ] Collection ID parameter needed
- [ ] Metadata extraction doesn't modify DB

### fuzzy_clean
- [ ] Text input properly referenced
- [ ] Phrase length thresholds included
- [ ] Output preserves original structure

---

## CODE QUALITY REVIEW

### Consistency
- [ ] All plans follow same template structure
- [ ] Naming conventions consistent
- [ ] Indentation consistent across files
- [ ] Comment style consistent

### Maintainability
- [ ] Plans easy to modify
- [ ] Parameters clearly documented
- [ ] Function paths easily traceable
- [ ] Error messages would be helpful

### Performance
- [ ] No unnecessary steps
- [ ] Efficient workflow ordering
- [ ] Reasonable default parameters
- [ ] No performance bottlenecks

---

## INTEGRATION TESTING REVIEW

### Prerequisites Check
- [ ] All tools exist in src/fichero/tools/
- [ ] All renderers exist in renderers/tool_renderers/
- [ ] All dependencies installed
- [ ] Backend integration verified

### Workflow Execution
- [ ] Can plans be loaded by Director?
- [ ] Can workflows be executed?
- [ ] Do manifests propagate correctly?
- [ ] Are outputs created properly?

---

## ISSUES TO IDENTIFY

Document any:
1. **Critical Issues** - Prevents execution
2. **Major Issues** - Causes errors or wrong results
3. **Minor Issues** - Works but suboptimal
4. **Suggestions** - Potential improvements

For each issue:
- Description
- Location (file:line)
- Severity
- Recommended fix

---

## OUTPUT DELIVERABLE

Create: `PHASE_A_CODE_REVIEW_REPORT.md`

Include:
1. **Summary:** Overall code quality assessment
2. **Issues Found:** Categorized by severity
3. **Verification Results:** All checklist items
4. **Recommendations:** Specific fixes needed
5. **Approval Status:** Ready for fixes / Ready for testing

---

## REVIEW APPROACH

1. Read all 7 plan YAML files completely
2. Read collection_view.py changes
3. Cross-reference with TOOL_REFERENCE.md
4. Verify function paths exist
5. Check parameter completeness
6. Assess integration quality
7. Document all findings

**Be thorough but pragmatic. Focus on correctness and reliability.**

When complete, report findings and readiness for fix implementation.
