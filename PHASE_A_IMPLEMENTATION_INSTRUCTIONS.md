# PHASE A: COMPLETE MENU COVERAGE - IMPLEMENTATION INSTRUCTIONS

**Objective:** Add 8 missing tools to CollectionView.TOOL_CONFIGS and create 2 missing plan files

**Current Status:** 12/20 tools in GUI menus (60%)
**Target Status:** 19/20 tools in GUI menus (95%)

---

## TOOLS TO ADD

### HIGH PRIORITY (Need both plan file + menu entry)

1. **transcribe_lmstudio** - Local AI transcription
   - Create `src/fichero/resources/config_defaults/plans/TranscribeLMStudio.yml`
   - Add to TOOL_CONFIGS as: `'transcribe_lmstudio': ('TranscribeLMStudio', 'TranscribeLMStudioTest')`

2. **json_to_excel** - Excel export
   - Create `src/fichero/resources/config_defaults/plans/JsonToExcel.yml`
   - Add to TOOL_CONFIGS as: `'json_to_excel': ('JsonToExcel', 'JsonToExcelTest')`

### MEDIUM PRIORITY (Need menu entry only - workflows exist in Generic_Catalogue.yml)

3. **json_to_word** - Word export alternative
   - Add to TOOL_CONFIGS as: `'json_to_word': ('JsonToWord', 'JsonToWordTest')`
   - Create simple plan file referencing tool

4. **convert_to_svg** - SVG generation
   - Add to TOOL_CONFIGS as: `'convert_to_svg': ('ConvertToSVG', 'ConvertToSVGTest')`
   - Create simple plan file

5. **analyze_document_groups** - Document grouping
   - Add to TOOL_CONFIGS as: `'analyze_document_groups': ('AnalyzeGroups', 'AnalyzeGroupsTest')`
   - Create simple plan file

6. **extract_library_metadata** - Metadata extraction
   - Add to TOOL_CONFIGS as: `'extract_library_metadata': ('ExtractMetadata', 'ExtractMetadataTest')`
   - Create simple plan file

7. **fuzzy_clean** - OCR cleanup
   - Add to TOOL_CONFIGS as: `'fuzzy_clean': ('FuzzyClean', 'FuzzyCleanTest')`
   - Create simple plan file

**SKIP:** build_documents_manifest (internal tool, auto-included in workflows)

---

## FILES TO MODIFY/CREATE

### 1. CollectionView TOOL_CONFIGS
**File:** `src/fichero/windows/main/views/collection/collection_view.py`

**Location:** Around line 80-90, in the TOOL_CONFIGS dictionary

**Add entries:**
```python
TOOL_CONFIGS = {
    # ... existing 12 tools ...
    'transcribe_lmstudio': ('TranscribeLMStudio', 'TranscribeLMStudioTest'),
    'json_to_excel': ('JsonToExcel', 'JsonToExcelTest'),
    'json_to_word': ('JsonToWord', 'JsonToWordTest'),
    'convert_to_svg': ('ConvertToSVG', 'ConvertToSVGTest'),
    'analyze_document_groups': ('AnalyzeGroups', 'AnalyzeGroupsTest'),
    'extract_library_metadata': ('ExtractMetadata', 'ExtractMetadataTest'),
    'fuzzy_clean': ('FuzzyClean', 'FuzzyCleanTest'),
}
```

### 2. Plan YAML Files

**Directory:** `src/fichero/resources/config_defaults/plans/`

**Template for each plan:**
```yaml
title: "{Tool Name}"
description: "Minimal workflow for testing {tool} tool"
workflows:
  {Tool}Test:
    - build_documents_manifest
    - {tool_name}
commands:
  - name: build_documents_manifest
    worker_type: "cpu"
    function: "fichero.tools.build_documents_manifest.build_manifest_batch"
    args:
      source_folder: "documents"
      output_manifest: "assets/manifests/documents_manifest.jsonl"
    outputs:
      - "assets/manifests/documents_manifest.jsonl"

  - name: {tool_name}
    worker_type: "{cpu|gpu}"  # Use "gpu" for AI tools
    function: "fichero.tools.{tool_name}.{function_name}_batch"
    args:
      source_folder: "documents"
      source_manifest: "assets/manifests/documents_manifest.jsonl"
      output_folder: "assets/{tool_output}"
      # Add tool-specific parameters from TOOL_REFERENCE.md
    outputs:
      - "assets/{tool_output}"
      - "assets/{tool_output}/{tool}_manifest.jsonl"
```

**Reference:** Use `TOOL_REFERENCE.md` for exact parameters

---

## IMPLEMENTATION STEPS

### Step 1: Read Current Files
1. Read `collection_view.py` to find TOOL_CONFIGS location
2. Read existing plan files to understand structure
3. Read `TOOL_REFERENCE.md` for tool parameters

### Step 2: Create Plan Files (7 files)
For each tool, create plan YAML using template:
1. TranscribeLMStudio.yml
2. JsonToExcel.yml
3. JsonToWord.yml
4. ConvertToSVG.yml
5. AnalyzeGroups.yml
6. ExtractMetadata.yml
7. FuzzyClean.yml

**Tool-Specific Details:**

**TranscribeLMStudio.yml:**
- worker_type: "gpu"
- function: "fichero.tools.transcribe_lmstudio.transcribe_batch"
- output_folder: "assets/transcriptions"
- Parameters: lmstudio_url, model_name, prompt

**JsonToExcel.yml:**
- worker_type: "cpu"
- function: "fichero.tools.json_to_excel.json_to_excel_batch"
- output_folder: "assets/excel_exports"
- input: JSON catalogues from previous step

**JsonToWord.yml:**
- worker_type: "cpu"
- function: "fichero.tools.json_to_word.json_to_word_batch"
- output_folder: "assets/word_catalogues"

**ConvertToSVG.yml:**
- worker_type: "cpu"
- function: "fichero.tools.convert_to_svg.convert_to_svg_batch"
- output_folder: "assets/svg_output"

**AnalyzeGroups.yml:**
- worker_type: "gpu"
- function: "fichero.tools.analyze_document_groups.analyze_groups_batch"
- output_folder: "assets/document_groups"

**ExtractMetadata.yml:**
- worker_type: "cpu"
- function: "fichero.tools.extract_library_metadata.extract_metadata_batch"
- output_folder: "assets/library_metadata"

**FuzzyClean.yml:**
- worker_type: "cpu"
- function: "fichero.tools.fuzzy_clean.fuzzy_clean_batch"
- output_folder: "assets/cleaned_text"

### Step 3: Update TOOL_CONFIGS
Edit `collection_view.py`:
1. Find TOOL_CONFIGS dictionary
2. Add 7 new entries
3. Maintain alphabetical order (optional but clean)
4. Preserve existing formatting

### Step 4: Verify Changes
1. Check YAML syntax valid (no tabs, proper indentation)
2. Verify all function paths match tool modules
3. Ensure workflow names match TOOL_CONFIGS entries
4. Check all required fields present

---

## QUALITY CHECKLIST

- [ ] 7 plan YAML files created
- [ ] All YAML files have valid syntax
- [ ] Function paths verified against TOOL_REFERENCE.md
- [ ] Worker types appropriate (cpu/gpu)
- [ ] 7 entries added to TOOL_CONFIGS
- [ ] TOOL_CONFIGS dictionary syntax valid
- [ ] Workflow names match plan file workflows
- [ ] No duplicate entries
- [ ] Existing tools unchanged

---

## OUTPUT DELIVERABLES

Create markdown report: `PHASE_A_IMPLEMENTATION_REPORT.md`

Include:
1. **Files Created:** List of 7 plan files with line counts
2. **Files Modified:** collection_view.py changes
3. **Verification Results:** YAML validation, function path checks
4. **Testing Instructions:** How to test each new tool
5. **Integration Score:** New percentage (should be ~95%)

---

## IMPORTANT NOTES

- Use TOOL_REFERENCE.md for accurate parameter documentation
- Follow existing plan file patterns exactly
- Preserve code formatting in collection_view.py
- Test YAML syntax before saving
- Dynamic handler generation will auto-create methods

**When complete, report ready for Phase A Code Review.**
