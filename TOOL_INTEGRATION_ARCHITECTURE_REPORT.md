# FICHERO TOOL INTEGRATION ARCHITECTURE - INVESTIGATION REPORT

**Generated:** 2025-11-15
**Purpose:** Base reference for systematic tool integration review
**Status:** READ-ONLY REFERENCE

---

## EXECUTIVE SUMMARY

Comprehensive investigation of Fichero's 20 processing tools and their integration across GUI, CLI, renderer, and backend systems.

**Key Findings:**
- ✅ All 20 tools have dedicated renderers
- ✅ Backend integration fully functional (GUI + CLI → Director → Tools)
- ⚠️ GUI integration ~60% complete (12/20 tools in menus)
- ⚠️ ToolRegistry only has 5/20 tools
- ⚠️ ToolExecutor only supports 3/20 tools

---

## 1. TOOL INVENTORY (20 Tools)

### Image Processing Tools (9)

1. **crop.py** - Crop document borders using YOLO/contour detection
   - Parameters: `contour_template`, `contour_padding`, `model_path`
   - Input → Output: Images → Cropped images + JSONL

2. **rotate.py** - Auto-straighten using Hough line transform
   - Parameters: `blur_kernel`, `canny_threshold1/2`
   - Input → Output: Images → Rotated images + JSONL

3. **enhance.py** - Improve contrast/clarity using CLAHE
   - Parameters: Document type detection (auto)
   - Input → Output: Images → Enhanced images + JSONL

4. **split.py** - Split double-page scans into single pages
   - Parameters: `method` (auto/center/fold)
   - Input → Output: Images → Split pages + JSONL

5. **segment.py** - Deskew and segment document regions
   - Parameters: Confidence thresholds (auto)
   - Input → Output: Images → Segments + JSONL

6. **remove_background.py** - Remove black backgrounds
   - Parameters: `method` (rembg/opencv)
   - Input → Output: Images → RGBA images + JSONL

7. **prepare_images.py** - Apply EXIF rotation + compression
   - Parameters: `compression_quality`, `output_format`
   - Input → Output: Images → Prepared images + JSONL

8. **recombine_segments.py** - Merge segments back into pages
   - Parameters: Segment manifest input
   - Input → Output: Segments → Combined images + JSONL

9. **convert_to_svg.py** - Create searchable SVG from image + text
   - Parameters: Image + transcription + metadata
   - Input → Output: Images + text → SVG files

### AI/Text Processing Tools (4)

10. **transcribe_qwen_max.py** - AI transcription via Qwen VL Max
    - Parameters: `max_size`, API key
    - Input → Output: Images → Text files + JSONL

11. **transcribe_lmstudio.py** - Local AI transcription via LMStudio
    - Parameters: `prompt`, LMStudio URL/model
    - Input → Output: Images → Text files + JSONL

12. **describe_images.py** - Visual description via Qwen VL Max
    - Parameters: Visual description prompt
    - Input → Output: Images → JSON descriptions

13. **llm_process.py** - LLM-based content processing/cataloging
    - Parameters: `prompt_config`, `llm` backend, `hierarchical`, `folder_mode`
    - Input → Output: Text/JSON → Processed JSON + JSONL

### Document Generation Tools (3)

14. **convert_to_word.py** - Side-by-side image + text Word docs
    - Parameters: Images + transcriptions
    - Input → Output: Images + text → .docx files

15. **json_to_word.py** - Formatted Word docs from JSON
    - Parameters: JSON structure mapping
    - Input → Output: JSON → .docx files

16. **json_to_excel.py** - Excel spreadsheets from JSON
    - Parameters: Flattening options
    - Input → Output: JSON → .xlsx files

### Metadata/Analysis Tools (4)

17. **build_documents_manifest.py** - Generate file inventory manifest
    - Parameters: `source_folder`
    - Input → Output: File system → JSONL manifest

18. **analyze_document_groups.py** - AI-based document boundary detection
    - Parameters: Video analysis prompt
    - Input → Output: Images + text → Document groups JSON

19. **extract_library_metadata.py** - Extract library DB metadata for files
    - Parameters: `library_db_path`, `collection_id`
    - Input → Output: Library DB → Metadata JSONL

20. **fuzzy_clean.py** - Clean repeated phrases from OCR text
    - Parameters: Min phrase length thresholds
    - Input → Output: Text → Cleaned text + JSONL

---

## 2. ARCHITECTURE LAYERS

```
┌─────────────────────────────────────────────────────────────┐
│ GUI Layer                                                    │
│  - CollectionView (bulk processing)                         │
│  - ToolExecutor (single-item processing)                    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Service Layer                                                │
│  - DirectorIntegrationService                               │
│  - LibraryManager                                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Director Layer (Workflow Orchestration)                     │
│  - FicheroDirector                                           │
│  - WorkflowExecutor                                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Tool Layer (Processing Implementation)                      │
│  - fichero.tools.{tool_name}.{tool_name}_batch()            │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. RENDERER SYSTEM

**All 20 tools have dedicated renderers** ✅

**Renderer Types:**
- `ImageRenderer` - For image processing tools (crop, rotate, enhance, etc.)
- `TextRenderer` - For transcription outputs
- `JsonRenderer` - For catalog/metadata outputs
- `DocumentRenderer` - For Word/Excel outputs
- `SvgRenderer` - For SVG outputs
- `FolderRenderer` - For folder-level operations

**Interactive HTML Templates:**
- `html_templates_crop.py` - Crop editor with draggable box
- `html_templates_rotate.py` - Rotation editor with angle controls
- `html_templates_split.py` - Split editor with position markers
- `html_templates_image_editor.py` - General image viewer with toolbar

---

## 4. INTEGRATION STATUS

### Menu Integration (CollectionView)

**Configured (12/20):**
- crop, rotate, split, enhance, remove_background, prepare, segment, recombine
- transcribe, describe, llm, convert_word

**Missing (8/20):**
- transcribe_lmstudio, json_to_excel, convert_to_svg
- analyze_document_groups, extract_library_metadata, build_documents_manifest
- fuzzy_clean

### ToolRegistry Parameter Schemas

**Configured (5/20):**
- crop, rotate, enhance, split, transcribe_qwen_max

**Missing (15/20):**
- All others

### ToolExecutor Direct Execution

**Configured (3/20):**
- crop, rotate, enhance

**Missing (17/20):**
- All others

---

## 5. GAPS IDENTIFIED

1. **ToolRegistry Gaps** - 15/20 tools missing parameter schemas
2. **ToolExecutor Gaps** - 17/20 tools missing direct execution
3. **CollectionView Gaps** - 8/20 tools missing from menu
4. **Documentation Gaps** - Tool parameters not fully documented
5. **Naming Inconsistencies** - Mix of `{tool}_batch()` and `process_documents_batch()`

---

## 6. VERIFICATION NEEDED

Each tool needs verification of:
1. ✅ Renderer exists and renders correctly
2. ✅ Backend execution works (via Director workflows)
3. ⚠️ GUI menu integration complete
4. ⚠️ Parameter schema in ToolRegistry
5. ⚠️ Direct execution in ToolExecutor
6. ⚠️ CLI documentation complete
7. ⚠️ Interactive editing features (where applicable)

---

**Next Steps:** See `TOOL_INTEGRATION_MASTER_PLAN.md` for systematic review approach.
