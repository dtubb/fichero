# PHASE 4: WORKFLOW/PLAN AUDIT - AGENT INSTRUCTIONS

**Phase:** 4 of 7
**Agent Type:** general-purpose
**Estimated Duration:** 45 minutes
**Prerequisites:** Read `TOOL_REFERENCE.md`, `RENDERER_STATUS.md`, `GUI_INTEGRATION_STATUS.md`

---

## OBJECTIVE

Audit all workflow plan YAML files to verify:
1. All 20 tools have executable workflows
2. Workflows properly chain tool inputs/outputs
3. Plan configurations valid and complete
4. Missing plan files identified
5. Common workflow patterns documented

Create `WORKFLOW_STATUS.md` with complete audit results and workflow test recommendations.

**IMPORTANT:** This phase is AUDIT ONLY. Do not execute workflows or make changes. Document current state.

---

## INPUT FILES

**Required Reading:**
1. `TOOL_REFERENCE.md` - Tool parameters and manifest formats
2. `GUI_INTEGRATION_STATUS.md` - Which tools have TOOL_CONFIGS entries
3. `TOOL_INTEGRATION_ARCHITECTURE_REPORT.md` - Architecture overview

**Files to Audit:**
1. `src/fichero/resources/config_defaults/plans/*.yml` - All plan YAML files
2. `src/fichero/director/workflow_executor.py` - Workflow execution logic
3. `src/fichero/director/coordinator.py` - Director coordination

---

## TASK BREAKDOWN

### Task 1: Inventory All Plan Files

List all YAML files in `src/fichero/resources/config_defaults/plans/`:

For each plan file, document:
1. **Filename** - e.g., `Crop.yml`
2. **Title** - Human-readable plan name
3. **Description** - Plan purpose
4. **Workflows** - List of workflows defined
5. **Commands** - List of tool commands in workflows
6. **File size** - Complexity indicator

Create inventory table:

| # | Filename | Title | Workflows | Commands | Tools Used | Status |
|---|----------|-------|-----------|----------|------------|--------|
| 1 | Crop.yml | Crop | CropTest | 2 | build_documents_manifest, crop | ✅ Valid |
| 2 | Rotate.yml | Rotate | RotateTest | 2 | build_documents_manifest, rotate | ✅ Valid |
| ... | ... | ... | ... | ... | ... | ... |

### Task 2: Audit Plan Structure

For each plan file, verify YAML structure is valid:

**Required sections:**
```yaml
title: "Plan Title"
description: "Plan description"
workflows:
  WorkflowName:
    - command1
    - command2
commands:
  - name: command1
    worker_type: "cpu"
    function: "fichero.tools.{tool}.{tool}_batch"
    args:
      # ... parameters
    outputs:
      # ... output paths
```

**Check for:**
1. Valid YAML syntax
2. All required fields present
3. Workflow references commands that exist
4. Command functions reference actual tool modules
5. Args match tool parameter expectations
6. Output paths follow convention

### Task 3: Map Tool Coverage

For each of the 20 tools, identify:

1. **Has single-tool test plan** - e.g., `Crop.yml` for crop tool
2. **Appears in multi-step workflows** - e.g., crop in "Default.yml"
3. **Plan file naming** - Follows convention?
4. **Workflow naming** - Consistent with TOOL_CONFIGS?

Create tool-to-plan mapping:

| # | Tool | Test Plan File | Workflow Name | Multi-step Plans | Status |
|---|------|----------------|---------------|------------------|--------|
| 1 | crop | Crop.yml | CropTest | Default.yml, Enhance_Images_and_Catalogue.yml | ✅ Complete |
| 2 | rotate | Rotate.yml | RotateTest | Default.yml | ✅ Complete |
| ... | ... | ... | ... | ... | ... |

### Task 4: Verify Workflow Chaining

For multi-step workflows (e.g., "Default.yml"), verify:

1. **Manifest propagation** - Output manifest of step N becomes input of step N+1
   ```yaml
   # Step 1 outputs:
   outputs:
     - "assets/cropped/crop_manifest.jsonl"

   # Step 2 inputs:
   args:
     source_manifest: "assets/cropped/crop_manifest.jsonl"
   ```

2. **Folder paths** - Output folders correctly referenced
3. **Dependencies** - Steps run in correct order
4. **Data flow** - Images → Enhanced → Cropped → Transcribed → Document

Document common workflow patterns:

**Pattern: Image Preparation**
```
build_documents_manifest → prepare_images → crop → enhance
```

**Pattern: Transcription**
```
[image preparation] → transcribe_qwen_max → llm_process
```

**Pattern: Document Generation**
```
[transcription] → convert_to_word
```

**Pattern: Segmentation**
```
prepare_images → segment → transcribe_qwen_max → recombine_segments
```

### Task 5: Identify Missing Plan Files

Cross-reference with GUI_INTEGRATION_STATUS.md:

**Tools in TOOL_CONFIGS but missing plan files:**
- Should have corresponding .yml files
- Workflow name should match TOOL_CONFIGS entry

**Tools NOT in TOOL_CONFIGS and missing plan files:**
- transcribe_lmstudio
- json_to_excel
- json_to_word
- convert_to_svg
- analyze_document_groups
- extract_library_metadata
- build_documents_manifest (internal - may not need plan)
- fuzzy_clean

Document which tools need plan files created.

### Task 6: Validate Command Configurations

For each command in plan files, verify:

1. **Function path** - `fichero.tools.{tool}.{function}` is valid
   - Check function name matches (e.g., `crop_batch` not `crop`)
   - Verify module exists

2. **Worker type** - Appropriate for tool
   - `cpu` - Most tools
   - `gpu` - AI tools (transcribe, describe, llm_process)
   - `python` - General

3. **Arguments** - Match tool parameters from TOOL_REFERENCE.md
   - All required parameters present
   - Optional parameters have valid defaults
   - Data types correct

4. **Output paths** - Follow convention
   - Relative to processing root
   - Consistent naming (e.g., `assets/cropped`, `assets/transcriptions`)

Create validation table:

| Plan | Command | Function Valid | Worker Type | Args Valid | Outputs Valid | Status |
|------|---------|----------------|-------------|------------|---------------|--------|
| Crop.yml | crop | ✅ | ✅ cpu | ✅ | ✅ | ✅ |
| ... | ... | ... | ... | ... | ... | ... |

### Task 7: Document Common Workflows

Identify and document the standard workflows:

1. **Default.yml** - Full processing pipeline
2. **Default_English.yml** - English transcription variant
3. **Enhance_Images_and_Catalogue.yml** - Image quality + cataloging
4. **Segment_and_Catalogue.yml** - Large document processing
5. **Generic_Catalogue.yml** - Cataloging only
6. **Quotations.yml** - Specialized extraction

For each, document:
- Purpose
- Steps involved
- Input requirements
- Output products
- Use cases

---

## OUTPUT FORMAT

Create `WORKFLOW_STATUS.md` with this structure:

```markdown
# FICHERO WORKFLOW/PLAN STATUS REPORT

**Generated:** 2025-11-15
**Phase:** 4 of 7
**Purpose:** Audit workflow plan configurations for all tools

---

## EXECUTIVE SUMMARY

**Plan File Coverage:**
- Total plan files: [count]
- Single-tool test plans: [count]/20
- Multi-step workflows: [count]
- Valid plans: [count]/[total]
- Invalid plans: [count]/[total]
- Missing plans: [count] tools

**Workflow Validation:**
- All workflows have valid YAML ✅
- Tool functions exist ✅
- Manifest chaining verified ✅
- Output paths consistent ✅
- Parameter validation: [issues if any]

**Gaps Identified:**
1. [List major gaps]
2. [...]

---

## PLAN FILE INVENTORY

| # | Filename | Title | Workflows | Commands | Tools Used | Size | Status |
|---|----------|-------|-----------|----------|------------|------|--------|
| 1 | Crop.yml | Crop | CropTest | 2 | build_documents_manifest, crop | 47 lines | ✅ Valid |
| 2 | Rotate.yml | Rotate | RotateTest | 2 | build_documents_manifest, rotate | 45 lines | ✅ Valid |
| 3 | Split.yml | Split | SplitTest | 2 | build_documents_manifest, split | 48 lines | ✅ Valid |
| 4 | Enhance.yml | Enhance | EnhanceTest | 2 | build_documents_manifest, enhance | 44 lines | ✅ Valid |
| ... | ... | ... | ... | ... | ... | ... | ... |

**Total:** [count] plan files

---

## TOOL COVERAGE ANALYSIS

### Tools with Complete Plan Coverage

| # | Tool | Test Plan | Workflow Name | Multi-step Plans | Status |
|---|------|-----------|---------------|------------------|--------|
| 1 | crop | Crop.yml | CropTest | Default, Enhance_Images_and_Catalogue, Segment_and_Catalogue | ✅ Complete |
| 2 | rotate | Rotate.yml | RotateTest | Default | ✅ Complete |
| 3 | enhance | Enhance.yml | EnhanceTest | Default, Enhance_Images_and_Catalogue, Enhance_Segment_and_Catalogue | ✅ Complete |
| ... | ... | ... | ... | ... | ... |

### Tools Missing Plan Files

| # | Tool | In TOOL_CONFIGS | Has Plan File | Recommended Plan Name | Priority |
|---|------|-----------------|---------------|-----------------------|----------|
| 13 | transcribe_lmstudio | ❌ | ❌ | TranscribeLMStudio.yml | High |
| 14 | json_to_excel | ❌ | ❌ | JsonToExcel.yml | High |
| 15 | json_to_word | ❌ | ❌ | JsonToWord.yml | Medium |
| 16 | convert_to_svg | ❌ | ❌ | ConvertToSVG.yml | Medium |
| 17 | analyze_document_groups | ❌ | ❌ | AnalyzeGroups.yml | Low |
| 18 | extract_library_metadata | ❌ | ❌ | ExtractMetadata.yml | Low |
| 19 | build_documents_manifest | N/A | N/A | (Internal - auto-generated) | N/A |
| 20 | fuzzy_clean | ❌ | ❌ | FuzzyClean.yml | Medium |

**Missing Plans:** 8 tools (40%)

---

## PLAN STRUCTURE VALIDATION

### Sample Plan: Crop.yml

```yaml
title: "Crop"
description: "Minimal workflow for testing crop tool"
workflows:
  CropTest:
    - build_documents_manifest
    - crop
commands:
  - name: build_documents_manifest
    worker_type: "cpu"
    function: "fichero.tools.build_documents_manifest.build_manifest_batch"
    args:
      source_folder: "documents"
      output_manifest: "assets/manifests/documents_manifest.jsonl"
    outputs:
      - "assets/manifests/documents_manifest.jsonl"

  - name: crop
    worker_type: "cpu"
    function: "fichero.tools.crop.crop_batch"
    args:
      source_folder: "documents"
      source_manifest: "assets/manifests/documents_manifest.jsonl"
      output_folder: "assets/cropped"
      model_path: "models/yolov8_trained_best.pt"
      output_format: "jpg"
      contour_template: "auto"
      contour_padding: 30
    outputs:
      - "assets/cropped"
      - "assets/cropped/crop_manifest.jsonl"
```

**Validation Results:**
- ✅ Valid YAML syntax
- ✅ All required fields present
- ✅ Workflow references existing commands
- ✅ Function paths valid (checked against tool modules)
- ✅ Args match tool parameters (cross-referenced with TOOL_REFERENCE.md)
- ✅ Output paths follow convention

### Validation Issues Found

**None** - All audited plans have valid structure

---

## WORKFLOW CHAINING ANALYSIS

### Multi-step Workflow: Default.yml

**Purpose:** Complete document processing pipeline

**Workflow Steps:**
```
1. build_documents_manifest
   ↓ documents_manifest.jsonl
2. prepare_images
   ↓ prepare_manifest.jsonl
3. crop
   ↓ crop_manifest.jsonl
4. enhance
   ↓ enhance_manifest.jsonl
5. transcribe_qwen_max
   ↓ transcribe_manifest.jsonl
6. llm_process
   ↓ catalogue_manifest.jsonl
7. convert_to_word
   ↓ .docx files
```

**Manifest Propagation:**
- ✅ Each step outputs manifest for next step
- ✅ Folder paths correctly referenced
- ✅ No broken chains

**Data Flow:**
- Input: Raw document images (JPG, PNG, TIFF)
- Step 1-4: Image preparation and enhancement
- Step 5: AI transcription
- Step 6: Structured data extraction
- Step 7: Word document generation
- Output: Side-by-side Word documents

### Common Workflow Patterns

**Pattern 1: Image Preparation**
```
build_documents_manifest → prepare_images → crop → enhance
```
**Used in:** Default, Enhance_Images_and_Catalogue, Segment_and_Catalogue

**Purpose:** Prepare raw scans for processing
- EXIF rotation correction
- Border cropping
- Contrast/brightness enhancement

---

**Pattern 2: Transcription Pipeline**
```
[prepared images] → transcribe_qwen_max → llm_process
```
**Used in:** Default, Generic_Catalogue, Quotations

**Purpose:** Extract text and structured data
- AI vision transcription
- LLM-based data extraction
- Metadata generation

---

**Pattern 3: Segmentation Workflow**
```
prepare_images → segment → transcribe_qwen_max → recombine_segments
```
**Used in:** Segment_and_Catalogue, Enhance_Segment_and_Catalogue

**Purpose:** Handle oversized documents
- Split large images into segments
- Process each segment
- Recombine results

---

**Pattern 4: Document Generation**
```
[transcriptions + images] → convert_to_word
```
**Used in:** Default, Enhance_Images_and_Catalogue

**Purpose:** Create deliverable documents
- Side-by-side image + text layout
- Professional formatting
- Export to .docx

---

## COMMAND CONFIGURATION VALIDATION

### Function Path Verification

| Plan | Command | Function Path | Module Exists | Function Exists | Status |
|------|---------|---------------|---------------|-----------------|--------|
| Crop.yml | crop | fichero.tools.crop.crop_batch | ✅ | ✅ | ✅ Valid |
| Rotate.yml | rotate | fichero.tools.rotate.rotate_batch | ✅ | ✅ | ✅ Valid |
| Enhance.yml | enhance | fichero.tools.enhance.enhance_batch | ✅ | ✅ | ✅ Valid |
| ... | ... | ... | ... | ... | ... |

**Validation Method:**
```python
# Checked each function path:
from fichero.tools.crop import crop_batch  # ✅ Works
from fichero.tools.rotate import rotate_batch  # ✅ Works
# etc.
```

**Issues Found:** None

### Worker Type Validation

| Worker Type | Tools Using | Appropriate | Notes |
|-------------|-------------|-------------|-------|
| cpu | crop, rotate, enhance, split, segment, prepare_images, remove_background, recombine_segments, build_documents_manifest, fuzzy_clean, convert_to_word, json_to_word, json_to_excel, convert_to_svg | ✅ | Image/document processing |
| gpu | transcribe_qwen_max, transcribe_lmstudio, describe_images, llm_process | ✅ | AI models benefit from GPU |
| python | analyze_document_groups, extract_library_metadata | ✅ | General computation |

**All worker types appropriate** ✅

### Parameter Validation

Cross-referenced all plan args with TOOL_REFERENCE.md parameters:

**Sample: crop command args**
```yaml
args:
  source_folder: "documents"          # ✅ Required parameter
  source_manifest: "..."              # ✅ Optional (can be None)
  output_folder: "assets/cropped"     # ✅ Required parameter
  model_path: "models/..."            # ✅ Optional with default
  output_format: "jpg"                # ✅ Valid enum value
  contour_template: "auto"            # ✅ Valid enum value
  contour_padding: 30                 # ✅ Integer in valid range
```

**Validation Results:**
- ✅ All required parameters present
- ✅ Optional parameters have valid defaults
- ✅ Enum values within allowed sets
- ✅ Numeric values within ranges
- ✅ Path references follow convention

**Issues Found:** None

---

## MULTI-STEP WORKFLOW DOCUMENTATION

### Default.yml - Complete Processing

**Title:** "Default"
**Description:** "Complete processing workflow with transcription and cataloging"

**Workflow:** Default
- build_documents_manifest
- prepare_images
- crop
- enhance
- transcribe_qwen_max
- llm_process
- convert_to_word

**Purpose:** Full document digitization pipeline

**Input Requirements:**
- Raw document scans (JPG/PNG/TIFF)
- Folder structure: `documents/` with images

**Output Products:**
- Enhanced images: `assets/enhanced/`
- Transcriptions: `assets/transcriptions/*.txt`
- Catalogues: `assets/catalogues/*.json`
- Word documents: `assets/word_documents/*.docx`
- Manifests at each step

**Use Cases:**
- Archival digitization
- Historical document processing
- Manuscript transcription and cataloging

---

### Enhance_Images_and_Catalogue.yml

**Title:** "Enhance Images and Catalogue"
**Description:** "Image enhancement with AI cataloging"

**Workflow:** EnhanceAndCatalogue
- build_documents_manifest
- prepare_images
- crop
- enhance
- transcribe_qwen_max
- llm_process
- convert_to_word

**Differences from Default:**
- (Same steps, different configuration/prompts)

**Purpose:** Quality-focused processing with cataloging

---

### Segment_and_Catalogue.yml

**Title:** "Segment and Catalogue"
**Description:** "Large document processing with segmentation"

**Workflow:** SegmentAndCatalogue
- build_documents_manifest
- prepare_images
- segment
- transcribe_qwen_max
- recombine_segments
- llm_process

**Purpose:** Handle oversized documents (>10MB images)

**Special Features:**
- Automatic segmentation for large images
- Per-segment transcription
- Intelligent recombination

---

### Generic_Catalogue.yml

**Title:** "Generic Catalogue"
**Description:** "Cataloging without image enhancement"

**Workflow:** GenericCatalogue
- build_documents_manifest
- transcribe_qwen_max
- llm_process

**Purpose:** Quick cataloging of already-prepared images

**Use Cases:**
- Pre-processed archives
- Digital-born documents
- Quick metadata extraction

---

### Quotations.yml

**Title:** "Quotations"
**Description:** "Extract quotations and dialogue"

**Workflow:** ExtractQuotations
- build_documents_manifest
- transcribe_qwen_max
- llm_process (specialized prompt for quotations)

**Purpose:** Extract quoted speech and dialogue

**Special Features:**
- Custom LLM prompt for quotation extraction
- Structured quotation metadata

---

## WORKFLOW TESTING RECOMMENDATIONS

### Test Plan for Each Workflow

**For each workflow, recommend testing:**

1. **Happy Path Test**
   - Provide sample inputs
   - Execute full workflow
   - Verify all outputs created
   - Check manifest propagation

2. **Error Handling Test**
   - Missing inputs
   - Invalid parameters
   - Tool failures
   - Partial completion

3. **Performance Test**
   - Small batch (1-10 images)
   - Medium batch (50-100 images)
   - Large batch (500+ images)
   - Monitor progress tracking

4. **Output Quality Test**
   - Verify image quality
   - Check transcription accuracy
   - Validate JSON structure
   - Test Word document formatting

### Recommended Test Data

**Sample Documents:**
- 1-2 page modern typed document (easy)
- 5-10 page handwritten manuscript (medium)
- 50+ page archival collection (hard)
- Oversized fold-out map/poster (segmentation test)

---

## GAPS & RECOMMENDATIONS

### Missing Plan Files (8 tools)

**High Priority:**
1. **TranscribeLMStudio.yml** - Local transcription alternative
2. **JsonToExcel.yml** - Excel export for catalogues
3. **FuzzyClean.yml** - OCR cleanup workflow

**Medium Priority:**
4. **JsonToWord.yml** - Alternative Word export
5. **ConvertToSVG.yml** - SVG generation workflow

**Low Priority:**
6. **AnalyzeGroups.yml** - Document boundary detection
7. **ExtractMetadata.yml** - Library integration workflow

**Not Needed:**
8. build_documents_manifest - Internal tool, auto-included

### Plan File Template

For missing plans, recommend this structure:

```yaml
title: "{Tool Name}"
description: "Minimal workflow for testing {tool} tool"
workflows:
  {Tool}Test:
    - build_documents_manifest
    - {tool}
commands:
  - name: build_documents_manifest
    worker_type: "cpu"
    function: "fichero.tools.build_documents_manifest.build_manifest_batch"
    args:
      source_folder: "documents"
      output_manifest: "assets/manifests/documents_manifest.jsonl"
    outputs:
      - "assets/manifests/documents_manifest.jsonl"

  - name: {tool}
    worker_type: "cpu"  # or "gpu" for AI tools
    function: "fichero.tools.{tool}.{tool}_batch"
    args:
      source_folder: "documents"
      source_manifest: "assets/manifests/documents_manifest.jsonl"
      output_folder: "assets/{tool}_output"
      # Add tool-specific parameters from TOOL_REFERENCE.md
    outputs:
      - "assets/{tool}_output"
      - "assets/{tool}_output/{tool}_manifest.jsonl"
```

### Workflow Enhancement Recommendations

1. **Add workflow variants:**
   - Fast mode (skip enhancement, basic transcription)
   - Quality mode (multiple AI models, verification)
   - Batch mode (optimized for large collections)

2. **Add conditional steps:**
   - Skip crop if already cropped
   - Skip transcribe if text files exist
   - Dynamic tool selection based on input

3. **Add error recovery:**
   - Resume from last completed step
   - Skip failed items, continue processing
   - Retry with different parameters

4. **Add progress reporting:**
   - Estimated time remaining
   - Current step details
   - Success/failure statistics

---

## PHASE 4 STATUS

- [x] All plan files inventoried ([count] files)
- [x] YAML structure validated
- [x] Tool coverage mapped (12/20 tools with plans)
- [x] Workflow chaining verified
- [x] Command configurations validated
- [x] Multi-step workflows documented
- [x] Missing plans identified (8 tools)
- [x] Recommendations provided

**Output:** WORKFLOW_STATUS.md complete
**Next Phase:** Phase 5 (CLI Integration Audit)

---

**Generated by:** Claude Code Phase 4 Agent
**Date:** 2025-11-15
**Quality:** Production-ready workflow audit
```

---

## QUALITY CHECKLIST

Before completing, verify:

- [ ] All plan files inventoried
- [ ] YAML syntax validated for each
- [ ] Tool coverage mapped for all 20 tools
- [ ] Workflow chaining verified with examples
- [ ] Command configurations cross-referenced with TOOL_REFERENCE.md
- [ ] Multi-step workflows documented with data flow
- [ ] Missing plans identified with priorities
- [ ] Test recommendations provided
- [ ] Status section added to master plan

---

## COMPLETION CRITERIA

**Output file created:** `WORKFLOW_STATUS.md`

**File contents:**
- Complete plan file inventory
- YAML structure validation
- Tool coverage analysis
- Workflow chaining verification
- Command configuration validation
- Multi-step workflow documentation
- Gap analysis with priorities
- Testing recommendations

**Status update:** Update `TOOL_INTEGRATION_MASTER_PLAN.md`:
```markdown
## CURRENT STATUS

- [x] Phase 0: Architecture investigation complete
- [x] Phase 1: Tool inventory complete
- [x] Phase 2: Renderer audit complete
- [x] Phase 3: GUI integration audit complete
- [x] Phase 4: Workflow audit complete
- [ ] Phase 5: CLI integration audit (NEXT)
```

---

## IMPORTANT NOTES

- **READ-ONLY:** Do not execute workflows or modify plan files
- **Cross-reference:** Use TOOL_REFERENCE.md to validate parameters
- **Complete Coverage:** Audit all plan files found
- **Actionable:** Provide template for missing plans

---

**When complete, report:** "Phase 4 complete. WORKFLOW_STATUS.md created with complete audit of all workflow plan files. Workflow chaining verified. Missing plans identified with recommended structure. Ready for Phase 5 (CLI Integration Audit)."
