# Toolks Menu - Complete Implementation Plan

## Overview

Add all major processing tools to the Toolks submenu with:
- Individual plan YAML files for each tool
- Menu commands in collection_view.py
- Handler methods for each tool
- Integration with workflow chaining system
- Interactive renderers (where applicable)

## Available Tools Analysis

Based on `src/fichero/tools/` and existing renderers:

### ✅ Already Implemented (3 tools)
1. **Crop** - Document detection and cropping
2. **Rotate** - Image rotation correction
3. **Split** - Split double-page images

### 📋 Core Processing Tools to Add (5 tools)

4. **Enhance** - Image quality enhancement (contrast, clarity)
   - Tool: `enhance.py` ✅
   - Renderer: `enhance_renderer.py` ✅
   - Plan: Need to create `Enhance.yml`

5. **Remove Background** - Background removal
   - Tool: `remove_background.py` ✅
   - Renderer: `remove_background_renderer.py` ✅
   - Plan: Need to create `RemoveBackground.yml`

6. **Segment** - Segment images into regions
   - Tool: `segment.py` ✅
   - Renderer: `segment_renderer.py` ✅
   - Plan: Need to create `Segment.yml`

7. **Transcribe** - OCR/AI transcription
   - Tool: `transcribe_qwen_max.py`, `transcribe_lmstudio.py` ✅
   - Renderer: `transcribe_renderer.py` ✅
   - Plan: Need to create `Transcribe.yml`

8. **Describe** - AI image description
   - Tool: `describe_images.py` ✅
   - Renderer: `describe_renderer.py` ✅
   - Plan: Need to create `Describe.yml`

### 🔧 Utility Tools (Optional - Lower Priority)

9. **Prepare Images** - Image preparation/standardization
   - Tool: `prepare_images.py` ✅
   - Renderer: `prepare_images_renderer.py` ✅

10. **Convert to Word** - Generate Word documents
    - Tool: `convert_to_word.py` ✅
    - Renderer: `convert_to_word_renderer.py` ✅

11. **Convert to SVG** - SVG conversion
    - Tool: `convert_to_svg.py` ✅
    - Renderer: `convert_to_svg_renderer.py` ✅

12. **LLM Process** - Catalogue generation
    - Tool: `llm_process.py` ✅
    - Renderer: `llm_process_renderer.py` ✅

## Implementation Strategy

### Phase 1: Core Image Processing Tools (Priority 1)
**Target: 5 tools that form a complete processing pipeline**

1. ✅ Crop (done)
2. ✅ Split (done)
3. ✅ Rotate (done)
4. **Enhance** ← START HERE
5. **Remove Background**

### Phase 2: AI/ML Tools (Priority 2)
**Target: Transcription and analysis tools**

6. **Segment**
7. **Transcribe**
8. **Describe**

### Phase 3: Output/Utility Tools (Priority 3)
**Target: Document generation and export**

9. Convert to Word
10. LLM Process (Catalogue)
11. Prepare Images
12. Convert to SVG

---

## Per-Tool Implementation Checklist

For EACH tool, we need:

### 1. Plan YAML File
**Location**: `src/fichero/resources/config_defaults/plans/{ToolName}.yml`

**Template Structure**:
```yaml
title: "{Tool Name}"
description: >
  Brief description of what this tool does.

vars:
  name: "Fichero"
  language: "es"
  version: "0.1.0"
  project_folder: ''
  documents_folder: ''
  assets_folder: ''

workflows:
  {ToolName}Test:
    - build_documents_manifest
    - {tool_command}

commands:
  - name: build_documents_manifest
    worker_type: "io"
    help: "Generate the documents manifest listing"
    function: "fichero.tools.build_documents_manifest.build_documents_manifest_batch"
    args:
      source_folder: "documents"
      output_manifest: "assets/manifests/documents_manifest.jsonl"
    outputs:
      - "assets/manifests/documents_manifest.jsonl"

  - name: {tool_command}
    worker_type: "cpu" or "io"
    help: "{description}"
    function: "fichero.tools.{tool_file}.{tool_function}_batch"
    args:
      source_folder: "documents"
      source_manifest: "assets/manifests/documents_manifest.jsonl"
      output_folder: "assets/{tool_folder}"
      # ... tool-specific args
    outputs:
      - "assets/{tool_folder}"
      - "assets/{tool_folder}/{tool}_manifest.jsonl"
```

### 2. Menu Command
**Location**: `src/fichero/windows/main/views/collection/collection_view.py`

**Add to commands dict** (around line 207-256):
```python
'process_{tool_name}': FicheroCommand(
    id='collection.process_{tool_name}',
    label=_("{Tool Display Name}"),
    action=self._on_quick_process_{tool_name},
    parent='collection.quick_tools',  # Nest under Toolks
    section=1,
    order={order_number},  # Increment for each tool
    show_in_menu=True,
    show_in_toolbar=False,
    desktop_only=True,
    context='normal'
),
```

### 3. Handler Method
**Location**: Same file, after line 2129

**Template**:
```python
async def _on_quick_process_{tool_name}(self, widget):
    """Handler for {Tool Display Name} quick tool"""
    await self._on_quick_process('{PlanName}', '{WorkflowName}')
```

### 4. Interactive Renderer (Optional, for visual tools)
**Location**: `src/fichero/library/renderers/tool_renderers/{tool}_renderer.py`

**Required methods**:
- `render_html()` - HTML visualization
- `get_editable_json()` - Parameters for JSON editor
- `validate_json()` - Validation logic
- `apply_json_edits()` - Re-run with new parameters

**Already exist for**:
- ✅ enhance_renderer.py
- ✅ remove_background_renderer.py
- ✅ segment_renderer.py
- ✅ transcribe_renderer.py
- ✅ describe_renderer.py

### 5. HTML Template (If interactive editing needed)
**Location**: `src/fichero/library/renderers/html_templates_{tool}.py`

**Pattern**: Like `html_templates_crop.py`, `html_templates_rotate.py`, `html_templates_split.py`

**Required for interactive editing**:
- Enhance: Slider controls for contrast, brightness, sharpness
- Remove Background: Threshold controls, method selection
- Segment: Segment boundary adjustment
- Transcribe: Text editing (maybe just use JSON inspector?)
- Describe: Description editing

---

## Detailed Tool Specifications

### 4. Enhance Tool

**Plan**: `Enhance.yml`
```yaml
title: "Enhance"
description: >
  Image quality enhancement - improve contrast, clarity, and brightness.

workflows:
  EnhanceTest:
    - build_documents_manifest
    - enhance

commands:
  - name: enhance
    worker_type: "cpu"
    help: "Enhance image quality with contrast and clarity improvements"
    function: "fichero.tools.enhance.enhance_batch"
    args:
      source_folder: "documents"
      source_manifest: "assets/manifests/documents_manifest.jsonl"
      output_folder: "assets/enhanced"
      output_format: "jpg"
    outputs:
      - "assets/enhanced"
      - "assets/enhanced/enhance_manifest.jsonl"
```

**Menu Order**: 3 (after Split)
**Handler**: `_on_quick_process_enhance`
**Interactive**: Slider controls for enhancement parameters

---

### 5. Remove Background Tool

**Plan**: `RemoveBackground.yml`
```yaml
title: "Remove Background"
description: >
  Remove background from images using OpenCV or AI models.

vars:
  background_removal_method: "opencv"  # "opencv" or "ai"
  background_removal_ai_model: ""  # "default", "u2net", etc.

workflows:
  RemoveBackgroundTest:
    - build_documents_manifest
    - remove_background

commands:
  - name: remove_background
    worker_type: "cpu"
    help: "Remove background from images"
    function: "fichero.tools.remove_background.remove_background_batch"
    args:
      source_folder: "documents"
      source_manifest: "assets/manifests/documents_manifest.jsonl"
      output_folder: "assets/background_removed"
      output_format: "png"
      method: "{background_removal_method}"
      ai_model: "{background_removal_ai_model}"
    outputs:
      - "assets/background_removed"
      - "assets/background_removed/background_removed_manifest.jsonl"
```

**Menu Order**: 4
**Handler**: `_on_quick_process_remove_background`
**Interactive**: Method selection, threshold controls

---

### 6. Segment Tool

**Plan**: `Segment.yml`
```yaml
title: "Segment"
description: >
  Segment images into regions for detailed processing.

workflows:
  SegmentTest:
    - build_documents_manifest
    - segment

commands:
  - name: segment
    worker_type: "cpu"
    help: "Segment images into regions"
    function: "fichero.tools.segment.segment_batch"
    args:
      source_folder: "documents"
      source_manifest: "assets/manifests/documents_manifest.jsonl"
      output_folder: "assets/segments"
      output_format: "jpg"
    outputs:
      - "assets/segments"
      - "assets/segments/segment_manifest.jsonl"
```

**Menu Order**: 5
**Handler**: `_on_quick_process_segment`
**Interactive**: Segment boundary editing

---

### 7. Transcribe Tool

**Plan**: `Transcribe.yml`
```yaml
title: "Transcribe"
description: >
  OCR and AI transcription of document images.

vars:
  transcription_model: "qwen_max"  # "qwen_max" or "lmstudio"

workflows:
  TranscribeTest:
    - build_documents_manifest
    - transcribe

commands:
  - name: transcribe
    worker_type: "io"
    help: "Transcribe images using AI models"
    function: "fichero.tools.transcribe_qwen_max.transcribe_batch"
    args:
      source_folder: "documents"
      source_manifest: "assets/manifests/documents_manifest.jsonl"
      output_folder: "assets/transcriptions"
    outputs:
      - "assets/transcriptions"
      - "assets/transcriptions/transcriptions_manifest.jsonl"
```

**Menu Order**: 6
**Handler**: `_on_quick_process_transcribe`
**Interactive**: Text editing via JSON inspector (transcription field)

---

### 8. Describe Tool

**Plan**: `Describe.yml`
```yaml
title: "Describe"
description: >
  Generate AI descriptions of document images.

workflows:
  DescribeTest:
    - build_documents_manifest
    - describe

commands:
  - name: describe
    worker_type: "io"
    help: "Generate AI descriptions of images"
    function: "fichero.tools.describe_images.describe_batch"
    args:
      source_folder: "documents"
      source_manifest: "assets/manifests/documents_manifest.jsonl"
      output_folder: "assets/descriptions"
    outputs:
      - "assets/descriptions"
      - "assets/descriptions/descriptions_manifest.jsonl"
```

**Menu Order**: 7
**Handler**: `_on_quick_process_describe`
**Interactive**: Description editing via JSON inspector

---

## Implementation Order

### Step 1: Create All Plan Files (Quick)
Create 5 YAML files in batch:
1. `Enhance.yml`
2. `RemoveBackground.yml`
3. `Segment.yml`
4. `Transcribe.yml`
5. `Describe.yml`

### Step 2: Add Menu Commands (Quick)
Add 5 command entries to `collection_view.py` commands dict

### Step 3: Add Handler Methods (Quick)
Add 5 simple handler methods to `collection_view.py`

### Step 4: Test Basic Functionality
Test each tool's basic execution (without interactive editing)

### Step 5: Add Interactive Editing (If Needed)
Create HTML templates for:
- Enhance (sliders)
- Remove Background (method/threshold controls)
- Others as needed

---

## Files to Create/Modify

### New Files (5 plan YAMLs):
1. `src/fichero/resources/config_defaults/plans/Enhance.yml`
2. `src/fichero/resources/config_defaults/plans/RemoveBackground.yml`
3. `src/fichero/resources/config_defaults/plans/Segment.yml`
4. `src/fichero/resources/config_defaults/plans/Transcribe.yml`
5. `src/fichero/resources/config_defaults/plans/Describe.yml`

### Modified Files (1):
1. `src/fichero/windows/main/views/collection/collection_view.py`
   - Add 5 menu commands (lines ~207-256)
   - Add 5 handler methods (lines ~2129+)

### Optional Interactive Templates (5):
1. `src/fichero/library/renderers/html_templates_enhance.py`
2. `src/fichero/library/renderers/html_templates_remove_background.py`
3. `src/fichero/library/renderers/html_templates_segment.py`
4. `src/fichero/library/renderers/html_templates_transcribe.py`
5. `src/fichero/library/renderers/html_templates_describe.py`

---

## Testing Checklist

For each tool:
- [ ] Plan YAML loads without errors
- [ ] Menu command appears in Toolks submenu
- [ ] Clicking command triggers handler
- [ ] Handler calls `_on_quick_process` correctly
- [ ] Tool executes and creates output folder
- [ ] Workflow chaining works (uses previous output as input)
- [ ] Manifest includes tool-specific metadata
- [ ] Renderer displays output correctly
- [ ] JSON inspector shows editable parameters (if applicable)
- [ ] Interactive editor works (if applicable)

---

## Success Criteria

✅ **Complete when**:
- All 5 core tools (Enhance, RemoveBackground, Segment, Transcribe, Describe) are in Toolks menu
- Each tool can be run independently
- Each tool chains from previous step's output
- Workflow: Crop → Split → Rotate → Enhance → RemoveBackground → Transcribe works end-to-end
- All renderers display outputs correctly
- Activity Monitor shows progress for each tool

---

## Time Estimate

- **Step 1** (Plan YAMLs): ~15 minutes
- **Step 2** (Menu commands): ~5 minutes
- **Step 3** (Handlers): ~5 minutes
- **Step 4** (Testing): ~15 minutes
- **Step 5** (Interactive editors): ~30-60 minutes (optional)

**Total Core Implementation**: ~40 minutes
**With Interactive Editing**: ~1.5 hours
