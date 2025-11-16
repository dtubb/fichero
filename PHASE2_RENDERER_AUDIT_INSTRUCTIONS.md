# PHASE 2: RENDERER COMPLETENESS AUDIT - AGENT INSTRUCTIONS

**Phase:** 2 of 7
**Agent Type:** general-purpose
**Estimated Duration:** 30 minutes
**Prerequisites:** Read `TOOL_REFERENCE.md` and `TOOL_INTEGRATION_ARCHITECTURE_REPORT.md`

---

## OBJECTIVE

Verify that all 20 tools have functional renderers with proper HTML templates for viewing/editing outputs in the Fichero GUI.

Create `RENDERER_STATUS.md` documenting renderer coverage, HTML template quality, and interactive editing capabilities.

---

## INPUT FILES

**Required Reading:**
1. `TOOL_REFERENCE.md` - Complete tool inventory from Phase 1
2. `TOOL_INTEGRATION_ARCHITECTURE_REPORT.md` - Architecture overview
3. `src/fichero/library/renderers/renderer_registry.py` - Renderer registration
4. `src/fichero/library/renderers/base_renderer.py` - BaseRenderer interface
5. `src/fichero/library/renderers/type_renderers.py` - Type-based renderers
6. `src/fichero/library/renderers/tool_renderers/*.py` - Tool-specific renderers

---

## TASK BREAKDOWN

### Task 1: Verify Renderer Registry

Read `renderer_registry.py` and verify:

1. **Registry completeness** - All 20 tools have registered renderer
2. **Renderer class mapping** - Tool name → Renderer class
3. **Base renderer types** - Which type renderer each tool extends
4. **Priority/fallback logic** - How renderer selection works

Create table:

| Tool | Renderer Class | Base Type | Registered | Priority |
|------|----------------|-----------|------------|----------|
| crop | CropRenderer | ImageRenderer | ✅ | Tool-specific |
| rotate | RotateRenderer | ImageRenderer | ✅ | Tool-specific |
| ... | ... | ... | ... | ... |

### Task 2: Audit Renderer Implementations

For each tool renderer in `tool_renderers/*.py`, verify:

1. **File exists** - Renderer class file present
2. **Inherits from base** - Extends appropriate type renderer
3. **Implements required methods**:
   - `render_html(context)` - Returns HTML for GUI display
   - `render_cli(context)` - Returns text for CLI display
   - `get_editable_json(context)` - Returns editable parameters (optional)

4. **HTML template integration**:
   - Which template file is used (if any)
   - Template variables required
   - Template rendering tested

5. **Interactive features**:
   - Toolbar commands declared
   - JavaScript handlers present
   - User interaction capabilities

### Task 3: Audit HTML Templates

Check HTML template files:

1. **Template files**:
   - `html_templates.py` - General text/JSON viewer
   - `html_templates_crop.py` - Crop editor
   - `html_templates_rotate.py` - Rotation editor
   - `html_templates_split.py` - Split editor
   - `html_templates_image_editor.py` - General image viewer

2. **Template quality**:
   - Responsive design (mobile + desktop)
   - Accessibility features
   - Error handling
   - Loading states

3. **Template coverage**:
   - Which tools use which templates
   - Gaps in template coverage
   - Opportunities for template reuse

### Task 4: Test Renderer Outputs

For a sample of tools (at least 5 from different categories), verify:

1. **HTML rendering works**:
   - Create mock context with sample data
   - Call `render_html(context)`
   - Verify HTML output is valid
   - Check all required elements present

2. **CLI rendering works**:
   - Call `render_cli(context)`
   - Verify text output is readable
   - Check formatting appropriate

3. **Editable JSON works** (if implemented):
   - Call `get_editable_json(context)`
   - Verify JSON structure valid
   - Check all parameters present

### Task 5: Document Interactive Editing Capabilities

For tools with interactive editors (crop, rotate, split, etc.):

1. **Toolbar buttons** - What actions available
2. **JavaScript functions** - What interactions supported
3. **Parameter editing** - What can be adjusted
4. **Re-run capability** - Can tool be re-executed with new params
5. **Preview updates** - Does preview refresh after edits

---

## OUTPUT FORMAT

Create `RENDERER_STATUS.md` with this structure:

```markdown
# FICHERO RENDERER STATUS REPORT

**Generated:** 2025-11-15
**Phase:** 2 of 7
**Purpose:** Verify renderer coverage and functionality for all 20 tools

---

## EXECUTIVE SUMMARY

- **Renderer Coverage:** 20/20 tools have registered renderers ✅
- **HTML Templates:** 5 templates covering all 20 tools ✅
- **Interactive Editors:** 4 tools with full editing (crop, rotate, split, segment)
- **CLI Rendering:** All 20 tools support CLI text output ✅
- **Gaps Identified:** [List any issues found]

---

## RENDERER REGISTRY MAPPING

| # | Tool | Renderer Class | Base Type | Template | Interactive | Status |
|---|------|----------------|-----------|----------|-------------|--------|
| 1 | crop | CropRenderer | ImageRenderer | html_templates_crop.py | ✅ Full | ✅ |
| 2 | rotate | RotateRenderer | ImageRenderer | html_templates_rotate.py | ✅ Full | ✅ |
| 3 | enhance | EnhanceRenderer | ImageRenderer | html_templates_image_editor.py | ⚠️ View only | ✅ |
| 4 | split | SplitRenderer | FolderRenderer | html_templates_split.py | ✅ Full | ✅ |
| ... | ... | ... | ... | ... | ... | ... |

---

## RENDERER IMPLEMENTATION DETAILS

### Image Processing Tools (9)

#### 1. CropRenderer (crop.py)

**File:** `src/fichero/library/renderers/tool_renderers/crop_renderer.py`
**Base Class:** ImageRenderer
**Template:** `html_templates_crop.py`

**Methods Implemented:**
- ✅ `render_html(context)` - Returns interactive crop editor
- ✅ `render_cli(context)` - Returns text summary
- ✅ `get_editable_json(context)` - Returns crop parameters

**HTML Features:**
- Draggable crop box overlay
- Visual crop boundary display
- Adjustable padding controls
- Before/after image comparison
- Re-crop button to apply new parameters

**Toolbar Commands:**
```python
[
    {'id': 'reset_crop', 'icon': 'arrow.counterclockwise', 'label': 'Reset'},
    {'id': 'apply_crop', 'icon': 'checkmark', 'label': 'Apply'},
]
```

**Interactive Capabilities:**
- ✅ Drag to adjust crop box
- ✅ Modify padding value
- ✅ Re-run crop with new parameters
- ✅ Preview updates in real-time

**Testing Results:**
- ✅ HTML rendering verified with sample data
- ✅ CLI rendering verified
- ✅ Editable JSON verified
- ✅ Toolbar integration verified

**Status:** ✅ Fully functional

---

(Repeat for all 20 tools)

---

## HTML TEMPLATE COVERAGE

### html_templates_crop.py
**Used by:** crop
**Features:** Draggable crop box, parameter controls, before/after view
**Mobile Support:** ✅ Responsive
**Accessibility:** ⚠️ Needs keyboard navigation
**Status:** ✅ Functional

### html_templates_rotate.py
**Used by:** rotate
**Features:** Rotation angle slider, preview, straightening guides
**Mobile Support:** ✅ Responsive
**Accessibility:** ✅ Full keyboard support
**Status:** ✅ Functional

### html_templates_split.py
**Used by:** split
**Features:** Split position markers, page preview grid
**Mobile Support:** ✅ Responsive
**Accessibility:** ⚠️ Needs keyboard navigation
**Status:** ✅ Functional

### html_templates_image_editor.py
**Used by:** enhance, remove_background, prepare_images, segment, recombine_segments
**Features:** Image viewer with toolbar (rotate, crop, reset)
**Mobile Support:** ✅ Responsive
**Accessibility:** ✅ Full keyboard support
**Status:** ✅ Functional

### html_templates.py (General viewer)
**Used by:** transcribe_qwen_max, transcribe_lmstudio, fuzzy_clean, describe_images, llm_process, analyze_document_groups, extract_library_metadata, build_documents_manifest
**Features:** Text viewer, JSON formatter, syntax highlighting
**Mobile Support:** ✅ Responsive
**Accessibility:** ✅ Full support
**Status:** ✅ Functional

---

## INTERACTIVE EDITING CAPABILITIES

### Full Interactive Editors (4 tools)

| Tool | Editor Features | Re-run Support | Preview Updates |
|------|-----------------|----------------|-----------------|
| crop | Drag crop box, adjust padding | ✅ | ✅ Real-time |
| rotate | Angle slider, manual entry | ✅ | ✅ Real-time |
| split | Position markers, method selector | ✅ | ✅ Real-time |
| segment | Grid overlay, threshold controls | ⚠️ Planned | ❌ Manual refresh |

### View-Only Renderers (16 tools)

Tools with view-only renderers (no interactive editing):
- enhance, remove_background, prepare_images, recombine_segments
- transcribe_qwen_max, transcribe_lmstudio, describe_images, llm_process
- convert_to_word, json_to_word, json_to_excel, convert_to_svg
- analyze_document_groups, extract_library_metadata, build_documents_manifest, fuzzy_clean

**Recommended enhancements:**
- Add parameter editors for tools with configurable options
- Implement re-run capability for all tools
- Add preview refresh mechanism

---

## GAPS & RECOMMENDATIONS

### Gaps Identified

1. **Limited Interactive Editing:**
   - Only 4/20 tools have full interactive editors
   - 16 tools are view-only despite having editable parameters

2. **Re-run Capability:**
   - Only 3/4 interactive editors support re-running
   - No mechanism for re-running view-only tools from GUI

3. **Parameter Editing UI:**
   - `get_editable_json()` implemented but not connected to GUI
   - No form-based parameter editor (only JSON editing)

4. **Template Accessibility:**
   - Some templates missing keyboard navigation
   - Screen reader support incomplete

5. **Documentation:**
   - Renderer capabilities not documented
   - No developer guide for creating renderers
   - Template variables not documented

### Recommendations

**Phase 6 Priorities:**
1. Implement form-based parameter editors for high-value tools:
   - enhance (quality settings)
   - transcribe_qwen_max (model selection)
   - llm_process (prompt configuration)

2. Add re-run capability to all renderers:
   - Integrate with DirectorIntegrationService
   - Add "Re-run with new parameters" button
   - Implement parameter validation

3. Enhance accessibility:
   - Add keyboard navigation to crop/split editors
   - Add ARIA labels to all interactive elements
   - Test with screen readers

4. Create renderer developer guide:
   - Document BaseRenderer interface
   - Provide template creation guide
   - Show best practices

---

## TESTING SUMMARY

**Renderers Tested:** 5 (crop, rotate, enhance, transcribe_qwen_max, llm_process)

**Test Results:**
- ✅ All tested renderers produce valid HTML
- ✅ All tested renderers produce readable CLI output
- ✅ Editable JSON returns valid parameter structures
- ✅ Templates render correctly with sample data
- ✅ Toolbar commands properly declared

**Test Coverage:** 25% (5/20 tools tested)

**Recommendation:** Phase 4 should include comprehensive renderer testing for all 20 tools.

---

## PHASE 2 STATUS

- [x] Renderer registry verified (20/20 tools registered)
- [x] Renderer implementations audited
- [x] HTML templates documented
- [x] Interactive capabilities assessed
- [x] Sample testing completed (5 tools)
- [x] Gaps identified and documented

**Output:** RENDERER_STATUS.md complete
**Next Phase:** Phase 3 (GUI Integration Audit)

---

**Generated by:** Claude Code Phase 2 Agent
**Date:** 2025-11-15
**Quality:** Production-ready documentation
```

---

## QUALITY CHECKLIST

Before completing, verify:

- [ ] All 20 tools have renderer mapping documented
- [ ] Renderer class inheritance verified
- [ ] HTML template usage documented
- [ ] Interactive capabilities assessed
- [ ] Sample testing completed (minimum 5 tools)
- [ ] Gaps identified with recommendations
- [ ] Status section added to master plan

---

## COMPLETION CRITERIA

**Output file created:** `RENDERER_STATUS.md`

**File contents:**
- Complete renderer mapping for all 20 tools
- HTML template coverage analysis
- Interactive editing capabilities assessment
- Testing results for sample renderers
- Gap analysis with recommendations

**Status update:** Update `TOOL_INTEGRATION_MASTER_PLAN.md`:
```markdown
## CURRENT STATUS

- [x] Phase 0: Architecture investigation complete
- [x] Phase 1: Tool inventory complete
- [x] Phase 2: Renderer audit complete
- [ ] Phase 3: GUI integration (NEXT)
```

---

## IMPORTANT NOTES

- **READ-ONLY:** Do not modify renderer files, only read and document
- **Sample Testing:** Test at least 5 renderers from different categories
- **Completeness:** Document all 20 renderers even if some are duplicates
- **Recommendations:** Provide actionable recommendations for Phase 6

---

**When complete, report:** "Phase 2 complete. RENDERER_STATUS.md created with audit of all 20 tool renderers. Interactive editing capabilities documented. Ready for Phase 3 (GUI Integration)."
