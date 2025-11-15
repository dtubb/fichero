# Tools > Process Menu Implementation Plan

**Status:** In Progress
**Start Date:** 2025-11-15
**Goal:** Implement complete Tools > Process menu with all 20 processing tools

---

## Overview

Build a comprehensive Tools > Process menu system where users can run individual processing tools on the current item, with each tool automatically using the last completed step as input.

---

## Core Architecture

### "Last Step as Input" Pattern

```
Current Item: document_001.jpg
Steps Completed:
  0. Original (documents/document_001.jpg)
  1. Prepared (assets/prepared/document_001.jpg)
  2. Cropped (assets/crops/document_001.jpg)  ← LAST STEP

User Action: Tools > Process > Rotate

System Behavior:
  - Reads: assets/crops/crop_manifest.jsonl (last step manifest)
  - Executes: rotate tool on assets/crops/ folder
  - Outputs: assets/rotated/document_001.jpg + rotate_manifest.jsonl
  - Updates: Step browser with new step #3
```

---

## Tool Inventory (20 Tools)

### Phase 1: Image Preparation (7 tools)
1. **prepare_images** - EXIF rotation, compression, standardization
2. **crop** - Contour/YOLO-based document boundary detection
3. **split** - Divide multi-page images (fold/center detection)
4. **rotate** - Auto-straighten text orientation (Hough transform)
5. **enhance** - Contrast, clarity, brightness (CLAHE)
6. **remove_background** - Remove non-document content
7. **segment** - Tile large images for better transcription

### Phase 2: AI Processing (5 tools)
8. **transcribe_qwen_max** - Alibaba Cloud AI transcription
9. **transcribe_lmstudio** - Local LLM transcription
10. **describe_images** - Generate image descriptions
11. **recombine_segments** - Merge segmented transcriptions
12. **fuzzy_clean** - Remove duplicate text from overlaps

### Phase 3: Document Generation (5 tools)
13. **convert_to_word** - Generate Word docs (image + text side-by-side)
14. **json_to_word** - Word docs from catalog JSON
15. **json_to_excel** - Excel spreadsheets from catalog
16. **convert_to_svg** - SVG vector documents
17. **llm_process** - Metadata extraction & cataloging

### Phase 4: Utilities (3 tools)
18. **analyze_document_groups** - Document grouping analysis
19. **extract_library_metadata** - Library integration
20. **build_documents_manifest** - Create inventory manifest

---

## Tool Workflow Order

Standard processing pipeline:
```
documents/
  ↓ build_documents_manifest
  ↓ prepare_images
  ↓ crop
  ↓ split
  ↓ rotate
  ↓ enhance
  ↓ remove_background
  ↓ segment
  ↓ transcribe_qwen_max
  ↓ recombine_segments
  ↓ fuzzy_clean
  ↓ llm_process (catalog)
  ↓ convert_to_word
  ↓ json_to_word
  ↓ json_to_excel
```

---

## Menu Structure

```
Tools > Process
├─ Prepare
│  ├─ Prepare Images
│  ├─ Crop Document
│  ├─ Split Pages
│  │  ├─ Auto-detect
│  │  ├─ Center Split
│  │  └─ Fold Detection
│  └─ Rotate/Straighten
│
├─ Enhance
│  ├─ Enhance Quality
│  ├─ Remove Background
│  └─ Segment Large Images
│
├─ Process
│  ├─ Transcribe (Qwen Max)
│  ├─ Transcribe (LM Studio)
│  ├─ Describe Images
│  ├─ Recombine Segments
│  └─ Clean Duplicates
│
├─ Generate
│  ├─ Convert to Word
│  ├─ Catalog to Word
│  ├─ Convert to Excel
│  └─ Convert to SVG
│
└─ Workflows (Quick Presets)
   ├─ Simple: Transcribe & Catalog
   ├─ Segment: Large Images
   └─ Full: Complete Pipeline
```

---

## Implementation Phases

### ✅ Phase 1: Infrastructure (Foundation)
**Duration:** 2 days
**Status:** In Progress

**Deliverables:**
1. `ToolParameterDialog` - Base class for tool parameter input
   - Generic form builder from tool signatures
   - Validation and defaults
   - Modal dialog with OK/Cancel

2. `ToolExecutor` - Tool execution service
   - Connects to Director backend
   - Async execution with progress callbacks
   - Error handling and result reporting

3. OutputView enhancements
   - `get_last_completed_step()` method
   - Returns (folder_path, manifest_path) of most recent step
   - Integrates with StepManager

**Files:**
- Create: `src/fichero/windows/main/views/shared/tool_dialog.py`
- Create: `src/fichero/windows/main/views/shared/tool_executor.py`
- Create: `src/fichero/windows/main/views/shared/progress_dialog.py`
- Modify: `src/fichero/windows/main/views/{preview,output}/output_view.py`

---

### ⬜ Phase 2: Menu Organization (Structure)
**Duration:** 1 day
**Status:** Not Started

**Deliverables:**
1. Restructure `_build_process_commands()` with 5 sections
2. Add Toga command groups for each category
3. Add placeholder commands for all 20 tools
4. Test menu structure renders correctly

**Files:**
- Modify: `src/fichero/windows/main/views/{preview,output}/tools_menu_manager.py`

---

### ⬜ Phase 3: Tool Implementation (20 Tools)
**Duration:** 4 weeks
**Status:** Not Started

**Week 1: Image Preparation (Days 1-7)**
- [ ] Day 1: Crop (complete existing stub)
- [ ] Day 2: Rotate
- [ ] Day 3: Split
- [ ] Day 4: Enhance
- [ ] Day 5: Remove Background
- [ ] Day 6: Segment
- [ ] Day 7: Prepare Images

**Week 2: AI Processing (Days 8-12)**
- [ ] Day 8: Transcribe Qwen Max
- [ ] Day 9: Transcribe LM Studio
- [ ] Day 10: Describe Images
- [ ] Day 11: Recombine Segments
- [ ] Day 12: Fuzzy Clean

**Week 3: Document Generation (Days 13-17)**
- [ ] Day 13: Convert to Word
- [ ] Day 14: JSON to Word
- [ ] Day 15: JSON to Excel
- [ ] Day 16: Convert to SVG
- [ ] Day 17: LLM Process (Catalog)

**Week 4: Utilities & Polish (Days 18-20 + buffer)**
- [ ] Day 18: Analyze Document Groups
- [ ] Day 19: Extract Library Metadata
- [ ] Day 20: Build Documents Manifest
- [ ] Days 21-24: Buffer for issues, testing, refinement

---

### ⬜ Phase 4: Execution Flow (Wiring)
**Duration:** 1 week
**Status:** Not Started

**Deliverables:**
1. Standardize execution pattern across all tools
2. Async/await integration with Toga
3. Background task management
4. Result handling and error recovery

---

### ⬜ Phase 5: Progress & Feedback (UX)
**Duration:** 3 days
**Status:** Not Started

**Deliverables:**
1. Progress dialog with cancel button
2. Success/failure summary dialogs
3. Step browser auto-update
4. Notification system

---

## File Structure

```
src/fichero/windows/main/views/
├── shared/
│   ├── tool_dialog.py          # NEW: Base dialog for parameters
│   ├── tool_executor.py        # NEW: Execution service
│   └── progress_dialog.py      # NEW: Progress feedback
├── preview/
│   ├── tools_menu_manager.py   # MODIFY: Add all 20 tools
│   └── preview_view.py         # MODIFY: Add get_last_step()
└── output/
    ├── tools_menu_manager.py   # MODIFY: Add all 20 tools
    └── output_view.py          # MODIFY: Add get_last_step()
```

---

## Tool Implementation Template

Each tool follows this pattern:

```python
def _process_<toolname>(self):
    """Process current item with <toolname> tool"""

    # 1. Validate
    if not self._validate_item_selected():
        return

    # 2. Get last step
    last_folder, last_manifest = self.output_view.get_last_completed_step()

    # 3. Show dialog
    dialog = <ToolName>Dialog(
        default_input=last_folder,
        default_manifest=last_manifest
    )
    params = await dialog.show_modal()
    if not params:
        return

    # 4. Execute
    executor = ToolExecutor(
        tool_name='<toolname>',
        input_folder=last_folder,
        input_manifest=last_manifest,
        output_folder=self._get_next_output_folder('<toolname>'),
        params=params,
        progress_callback=self._on_tool_progress
    )

    result = await executor.execute()

    # 5. Update UI
    if result.success:
        self.output_view.add_step(...)
        self.output_view.step_browser.select_step(result.step_index)
    else:
        self.app.main_window.error_dialog('Failed', result.error)
```

---

## Tool Parameters Reference

### Crop
- `contour_template`: auto|dark_background|light_background|edge_detection|custom
- `contour_padding`: int (default: 30)
- `model_path`: Path to YOLO model (optional)
- `output_format`: jpg|png|jxl

### Rotate
- `blur_kernel`: tuple (default: (5,5))
- `canny_threshold1`: int (default: 50)
- `canny_threshold2`: int (default: 150)
- `output_format`: jpg|png|jxl

### Split
- `method`: auto|center|fold
- `fold_threshold`: float (default: 0.5)
- `output_format`: jpg|png|jxl

### Enhance
- `skip_processing`: bool (for fast testing)
- `output_format`: jpg|png|jxl

### Segment
- `tile_size`: int (default: 2048)
- `overlap`: int (default: 256)
- `output_format`: jpg|png|jxl

### Transcribe Qwen Max
- `api_key`: str (from settings)
- `model`: str (default: qwen-max)
- `prompt_template`: str (dropdown from templates)

### Convert to Word
- `layout`: side_by_side|stacked
- `font_size`: int (default: 11)
- `include_images`: bool (default: true)

---

## Testing Strategy

**Per Tool:**
1. Unit test: Parameter validation
2. Integration test: Execute on 1 sample image
3. UI test: Dialog shows/dismisses
4. Chain test: Output becomes next input

**Integration:**
1. Create test collection (3 images)
2. Run chain: Crop → Rotate → Enhance
3. Verify manifests chain correctly
4. Verify step browser updates

---

## Success Criteria

- [ ] All 20 tools have menu commands
- [ ] Each tool has parameter dialog
- [ ] "Last step as input" works automatically
- [ ] Progress feedback during execution
- [ ] Step browser updates with results
- [ ] Tools can be chained manually
- [ ] Quick workflow presets work
- [ ] Errors handled gracefully

---

## Timeline

| Phase | Duration | Target Date |
|-------|----------|-------------|
| Phase 1: Infrastructure | 2 days | 2025-11-17 |
| Phase 2: Menu Structure | 1 day | 2025-11-18 |
| Phase 3: Tools (Week 1) | 1 week | 2025-11-25 |
| Phase 3: Tools (Week 2) | 1 week | 2025-12-02 |
| Phase 3: Tools (Week 3) | 1 week | 2025-12-09 |
| Phase 3: Tools (Week 4) | 1 week | 2025-12-16 |
| Phase 4: Execution Flow | 1 week | 2025-12-23 |
| Phase 5: Progress/UX | 3 days | 2025-12-26 |

**Total:** ~6 weeks
**MVP (Image Pipeline):** ~1 week

---

## Progress Tracking

### Session 1: 2025-11-15
- ✅ Research completed
- ✅ Plan created and approved
- 🔄 Phase 1 infrastructure started
  - ToolParameterDialog - Not started
  - ToolExecutor - Not started
  - OutputView enhancements - Not started

---

## Notes

- All tools already work from CLI/Director backend
- Just need UI integration
- Manifest chaining is the key pattern
- StepManager already tracks workflow state
- Progress callbacks already exist in Director

---

## References

- Workflow YAML files: `src/fichero/resources/plans/`
- Tool implementations: `src/fichero/tools/`
- Director coordinator: `src/fichero/director/coordinator.py`
- Step browser: `src/fichero/windows/main/views/output/step_browser.py`
