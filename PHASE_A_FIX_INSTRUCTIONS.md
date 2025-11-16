# PHASE A: FIX IMPLEMENTATION INSTRUCTIONS

**Objective:** Fix critical and major issues identified in code review

**Input:** `PHASE_A_CODE_REVIEW_REPORT.md`

---

## ISSUES TO FIX

### CRITICAL-1, 2, 3: ConvertToSVG (All Related)

**Problem:** Function signature mismatch - tool was upgraded to AI-powered semantic SVG but plan uses old Potrace-only approach

**Solution:** Update plan to use simpler Potrace-based conversion (no AI dependencies)

**Fix ConvertToSVG.yml:**
```yaml
title: "Convert to SVG"
description: "Minimal workflow for testing convert_to_svg tool (Potrace-based vectorization)"
workflows:
  ConvertToSVGTest:
    - build_documents_manifest
    - convert_to_svg
commands:
  - name: build_documents_manifest
    worker_type: "cpu"
    function: "fichero.tools.build_documents_manifest.build_manifest_batch"
    args:
      source_folder: "documents"
      output_manifest: "assets/manifests/documents_manifest.jsonl"
    outputs:
      - "assets/manifests/documents_manifest.jsonl"

  - name: convert_to_svg
    worker_type: "cpu"  # Changed from gpu (no AI)
    function: "fichero.tools.convert_to_svg.convert_to_svg_batch"
    args:
      source_folder: "documents"
      source_manifest: "assets/manifests/documents_manifest.jsonl"
      output_folder: "assets/svg_output"
      # Use basic Potrace vectorization (no transcriptions needed)
      use_potrace: true
      svg_format: "simple"
    outputs:
      - "assets/svg_output"
      - "assets/svg_output/convert_to_svg_manifest.jsonl"
```

**Rationale:**
- Removes AI dependencies
- Uses simple Potrace vectorization
- Works as standalone test
- Can still be used in complex workflows with transcriptions

---

### MAJOR-1: JsonToExcel Non-Standard Signature

**Problem:** Tool uses `output_file` instead of `output_folder`, doesn't create manifest

**Solution:** Update plan to work with tool's actual signature

**Fix JsonToExcel.yml:**
```yaml
title: "JSON to Excel"
description: "Minimal workflow for testing json_to_excel tool"
workflows:
  JsonToExcelTest:
    - build_documents_manifest
    - json_to_excel
commands:
  - name: build_documents_manifest
    worker_type: "cpu"
    function: "fichero.tools.build_documents_manifest.build_manifest_batch"
    args:
      source_folder: "documents"
      output_manifest: "assets/manifests/documents_manifest.jsonl"
    outputs:
      - "assets/manifests/documents_manifest.jsonl"

  - name: json_to_excel
    worker_type: "cpu"
    function: "fichero.tools.json_to_excel.json_to_excel"  # Note: NOT _batch
    args:
      json_file: "assets/catalogues/catalogue.json"  # Input JSON file
      output_file: "assets/excel_exports/catalogue.xlsx"  # Output Excel file
      flatten: true
      max_depth: 3
    outputs:
      - "assets/excel_exports/catalogue.xlsx"
```

**Note:** This tool expects single JSON file input, not a batch operation. In real workflows, it should come after llm_process which creates catalogue JSON files.

---

### MINOR IMPROVEMENTS (Optional but Recommended)

**1. AnalyzeGroups.yml - Add output_format parameter:**
```yaml
args:
  # ... existing args ...
  output_format: "json"  # Add this
```

**2. ExtractMetadata.yml - Use null instead of empty string:**
```yaml
args:
  library_db_path: null  # Will use default
  collection_id: null    # Will process all collections
```

**3. FuzzyClean.yml - Add all parameters:**
```yaml
args:
  # ... existing args ...
  min_phrase_length: 3
  min_occurrences: 2
```

---

## IMPLEMENTATION STEPS

### Step 1: Fix Critical Issues
1. Read `ConvertToSVG.yml`
2. Replace entire file with corrected version
3. Verify YAML syntax

### Step 2: Fix Major Issues
1. Read `JsonToExcel.yml`
2. Replace with corrected version
3. Note the function name change (no _batch)

### Step 3: Apply Minor Improvements (Optional)
1. Update AnalyzeGroups.yml
2. Update ExtractMetadata.yml
3. Update FuzzyClean.yml

### Step 4: Verify All Changes
1. Validate YAML syntax for all modified files
2. Check function paths exist
3. Ensure parameter names match tool signatures
4. Test manifest chaining logic

---

## VERIFICATION CHECKLIST

After fixes:
- [ ] ConvertToSVG.yml uses cpu worker type
- [ ] ConvertToSVG.yml has use_potrace parameter
- [ ] JsonToExcel.yml uses json_to_excel (not _batch)
- [ ] JsonToExcel.yml has output_file (not output_folder)
- [ ] All YAML syntax valid
- [ ] All function paths correct
- [ ] All parameters match tool signatures

---

## QUALITY STANDARDS

- Preserve file formatting
- Match existing plan file style
- Keep comments clear and helpful
- Maintain alphabetical ordering where applicable
- Use 2-space indentation consistently

---

## OUTPUT DELIVERABLE

Create: `PHASE_A_FIX_REPORT.md`

Include:
1. **Fixes Applied:** List of changes made
2. **Files Modified:** With before/after snippets
3. **Verification Results:** All checks passed
4. **Remaining Issues:** Any unfixed items (should be none)
5. **Ready for Testing:** Confirmation

---

## IMPORTANT NOTES

- ConvertToSVG can still be used in complex workflows (with transcriptions)
- JsonToExcel is designed for single-file conversion, not batch
- These are minimal test workflows - real workflows can be more complex
- All fixes preserve backward compatibility

**When complete, report fixes applied and readiness for testing agent.**
