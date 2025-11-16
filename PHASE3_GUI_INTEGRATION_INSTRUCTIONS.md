# PHASE 3: GUI INTEGRATION AUDIT - AGENT INSTRUCTIONS

**Phase:** 3 of 7
**Agent Type:** general-purpose
**Estimated Duration:** 60 minutes
**Prerequisites:** Read `TOOL_REFERENCE.md` and `RENDERER_STATUS.md`

---

## OBJECTIVE

Audit and document the current state of GUI integration for all 20 tools, identifying gaps in:
1. CollectionView tool menu configuration
2. ToolRegistry parameter schemas
3. ToolExecutor direct execution support
4. FicheroCommand definitions
5. Toolbar button placement

Create `GUI_INTEGRATION_STATUS.md` with complete audit results and actionable recommendations.

**IMPORTANT:** This phase is AUDIT ONLY. Do not make code changes. Document current state and recommend changes for future implementation.

---

## INPUT FILES

**Required Reading:**
1. `TOOL_REFERENCE.md` - Complete tool parameter documentation
2. `RENDERER_STATUS.md` - Renderer audit results
3. `TOOL_INTEGRATION_ARCHITECTURE_REPORT.md` - Architecture overview

**Files to Audit:**
1. `src/fichero/windows/main/views/collection/collection_view.py` - Tool menu configuration
2. `src/fichero/windows/main/views/shared/tool_registry.py` - Parameter schemas
3. `src/fichero/windows/main/views/shared/tool_executor.py` - Direct execution
4. `src/fichero/shared/commands/command.py` - FicheroCommand system
5. `src/fichero/shared/commands/command_manager.py` - Command registration
6. `src/fichero/windows/main/views/library/library_view.py` - Library commands

---

## TASK BREAKDOWN

### Task 1: Audit CollectionView Tool Configuration

Read `collection_view.py` and document:

1. **TOOL_CONFIGS dictionary** - Which tools are configured
   ```python
   TOOL_CONFIGS = {
       'crop': ('Crop', 'CropTest'),
       'rotate': ('Rotate', 'RotateTest'),
       # ... list all entries
   }
   ```

2. **Dynamic handler generation** - How `_create_tool_handlers()` works

3. **Quick process integration** - Which tools have quick-access buttons

4. **Process dialog integration** - How full process dialog selects tools

5. **Missing tools** - Which of the 20 tools are NOT in TOOL_CONFIGS

Create comparison table:

| # | Tool Name | In TOOL_CONFIGS | Plan Name | Workflow Name | Quick Button | Status |
|---|-----------|-----------------|-----------|---------------|--------------|--------|
| 1 | crop | ✅ | Crop | CropTest | ✅ | Complete |
| 2 | rotate | ✅ | Rotate | RotateTest | ✅ | Complete |
| 3 | enhance | ✅ | Enhance | EnhanceTest | ⚠️ Missing | Partial |
| ... | ... | ... | ... | ... | ... | ... |

### Task 2: Audit ToolRegistry Parameter Schemas

Read `tool_registry.py` and document:

1. **Current tools registered** - Which tools have parameter schemas
   ```python
   self.tools = {
       'crop': self._create_crop_schema(),
       'rotate': self._create_rotate_schema(),
       # ... list all entries
   }
   ```

2. **Schema creation methods** - How schemas are built (introspection vs manual)

3. **Parameter validation** - What validation rules exist

4. **UI generation** - How schemas drive parameter UI

5. **Missing tools** - Which of the 20 tools are NOT in registry

For each registered tool, document:
- Schema structure
- Parameters included
- Validation rules
- Default values
- UI hints (e.g., dropdown, slider, checkbox)

Create status table:

| # | Tool Name | Schema Exists | Parameters Count | Validation | UI Hints | Status |
|---|-----------|---------------|------------------|------------|----------|--------|
| 1 | crop | ✅ | 4 | ✅ Ranges | ✅ Dropdowns | Complete |
| 2 | rotate | ✅ | 0 | N/A | N/A | Minimal |
| ... | ... | ... | ... | ... | ... | ... |

### Task 3: Audit ToolExecutor Direct Execution

Read `tool_executor.py` and document:

1. **Supported tools** - Which tools have `_run_{tool}()` methods
   ```python
   def _run_crop(self, input_path, output_folder, parameters):
       from fichero.tools.crop import process_image
       # ...
   ```

2. **Execution flow** - How tool execution works
   - Input path resolution
   - Output folder creation
   - Parameter passing
   - Result handling
   - UI updates

3. **Integration with renderers** - How outputs are displayed

4. **Error handling** - How failures are managed

5. **Missing tools** - Which of the 20 tools are NOT supported

Create execution support table:

| # | Tool Name | Execution Method | Input Handling | Output Handling | Error Handling | Status |
|---|-----------|------------------|----------------|-----------------|----------------|--------|
| 1 | crop | `_run_crop()` | ✅ | ✅ | ✅ | Complete |
| 2 | rotate | `_run_rotate()` | ✅ | ✅ | ✅ | Complete |
| 3 | enhance | `_run_enhance()` | ✅ | ✅ | ✅ | Complete |
| ... | ... | ... | ... | ... | ... | ... |

### Task 4: Audit FicheroCommand System

Read `command.py`, `command_manager.py`, and view files to document:

1. **Command definitions** - All tool-related FicheroCommands
   ```python
   FicheroCommand(
       id="collection.quick_crop",
       label="Crop",
       action=self._on_quick_process_crop,
       show_in_toolbar=True,
       toolbar_icon="crop@10x.png",
       category="tools"
   )
   ```

2. **Command registration** - How commands are registered
   - View-level registration
   - Global command registry
   - Menu integration
   - Toolbar integration

3. **Command categories** - How tools are organized
   - Image processing
   - AI processing
   - Document generation
   - Metadata/analysis

4. **Toolbar placement** - Current toolbar layout
   ```
   [Library] [Collection] [New Collection] [Import ▾] [FlexSpace] [Settings] [Inspector] [Process] [Adjust]
   ```

5. **Missing commands** - Which tools don't have FicheroCommands

Create command mapping table:

| # | Tool Name | Command ID | Command Label | Toolbar | Menu | Category | Status |
|---|-----------|------------|---------------|---------|------|----------|--------|
| 1 | crop | collection.quick_crop | Crop | ✅ | ✅ | Image | Complete |
| ... | ... | ... | ... | ... | ... | ... | ... |

### Task 5: Document Integration Patterns

Identify and document the integration patterns:

1. **Quick Process Pattern** - Single-button tool execution
   - User clicks toolbar button
   - Pre-configured plan/workflow executes
   - Progress shown
   - Outputs displayed

2. **Dialog Process Pattern** - Full process dialog
   - User clicks "Process" button
   - Dialog shows plan/workflow picker
   - User selects options
   - Execution begins

3. **Direct Execution Pattern** - ToolExecutor
   - User selects item
   - User clicks tool button
   - Parameter dialog (if needed)
   - Tool executes on current step
   - Output added as new step

4. **Menu Command Pattern** - Menu integration
   - Command registered globally
   - Appears in menus
   - Optionally in toolbar
   - Action handler executes

### Task 6: Identify Integration Gaps

For each of the 20 tools, assess integration completeness:

**Integration Checklist:**
- [ ] In TOOL_CONFIGS (CollectionView menu)
- [ ] Has ToolRegistry schema (parameter UI)
- [ ] Has ToolExecutor method (direct execution)
- [ ] Has FicheroCommand (command system)
- [ ] Has toolbar icon
- [ ] Has plan/workflow YAML
- [ ] Documented in UI

Create gap analysis table showing which tools need which integration work.

---

## OUTPUT FORMAT

Create `GUI_INTEGRATION_STATUS.md` with this structure:

```markdown
# FICHERO GUI INTEGRATION STATUS REPORT

**Generated:** 2025-11-15
**Phase:** 3 of 7
**Purpose:** Audit GUI integration for all 20 tools

---

## EXECUTIVE SUMMARY

**Current Integration Status:**
- CollectionView TOOL_CONFIGS: 12/20 tools (60%)
- ToolRegistry schemas: 5/20 tools (25%)
- ToolExecutor methods: 3/20 tools (15%)
- FicheroCommand definitions: [Count]/20 tools
- Complete integration: [Count]/20 tools

**Critical Gaps:**
1. [List major gaps found]
2. [...]

**Recommendations:**
1. [Prioritized recommendations]
2. [...]

---

## COLLECTIONVIEW TOOL MENU

### Current Configuration

**TOOL_CONFIGS Dictionary (collection_view.py:XXX):**

| # | Tool Name | In Config | Plan Name | Workflow Name | Handler Method | Status |
|---|-----------|-----------|-----------|---------------|----------------|--------|
| 1 | crop | ✅ | Crop | CropTest | `_on_quick_process_crop()` | ✅ Complete |
| 2 | rotate | ✅ | Rotate | RotateTest | `_on_quick_process_rotate()` | ✅ Complete |
| 3 | enhance | ✅ | Enhance | EnhanceTest | `_on_quick_process_enhance()` | ✅ Complete |
| 4 | split | ✅ | Split | SplitTest | `_on_quick_process_split()` | ✅ Complete |
| 5 | remove_background | ✅ | RemoveBackground | RemoveBackgroundTest | `_on_quick_process_remove_background()` | ✅ Complete |
| 6 | prepare_images | ✅ | PrepareImages | PrepareTest | `_on_quick_process_prepare()` | ✅ Complete |
| 7 | segment | ✅ | Segment | SegmentTest | `_on_quick_process_segment()` | ✅ Complete |
| 8 | recombine_segments | ✅ | RecombineSegments | RecombineTest | `_on_quick_process_recombine()` | ✅ Complete |
| 9 | transcribe_qwen_max | ✅ | Transcribe | TranscribeTest | `_on_quick_process_transcribe()` | ✅ Complete |
| 10 | describe_images | ✅ | Describe | DescribeTest | `_on_quick_process_describe()` | ✅ Complete |
| 11 | llm_process | ✅ | LLMProcess | LLMProcessTest | `_on_quick_process_llm()` | ✅ Complete |
| 12 | convert_to_word | ✅ | ConvertToWord | ConvertToWordTest | `_on_quick_process_convert_word()` | ✅ Complete |
| 13 | transcribe_lmstudio | ❌ | - | - | - | ⚠️ Missing |
| 14 | json_to_excel | ❌ | - | - | - | ⚠️ Missing |
| 15 | json_to_word | ❌ | - | - | - | ⚠️ Missing |
| 16 | convert_to_svg | ❌ | - | - | - | ⚠️ Missing |
| 17 | analyze_document_groups | ❌ | - | - | - | ⚠️ Missing |
| 18 | extract_library_metadata | ❌ | - | - | - | ⚠️ Missing |
| 19 | build_documents_manifest | ❌ | - | - | - | ⚠️ Missing |
| 20 | fuzzy_clean | ❌ | - | - | - | ⚠️ Missing |

**Integration Coverage:** 12/20 (60%)

**Missing Tools (8):**
1. transcribe_lmstudio - Local AI transcription alternative
2. json_to_excel - Excel export for catalogues
3. json_to_word - Word export for catalogues (alternative to convert_to_word)
4. convert_to_svg - SVG generation with searchable text
5. analyze_document_groups - AI visual document grouping
6. extract_library_metadata - Library DB metadata extraction
7. build_documents_manifest - Initial manifest creation
8. fuzzy_clean - OCR text cleanup

### Integration Mechanism

**Dynamic Handler Creation (_create_tool_handlers, line XXX):**
```python
def _create_tool_handlers(self):
    for tool_key, (plan_name, workflow_name) in self.TOOL_CONFIGS.items():
        handler_name = f'_on_quick_process_{tool_key}'
        handler = lambda p=plan_name, w=workflow_name: self._on_quick_process(p, w)
        setattr(self, handler_name, handler)
```

**Quick Process Flow:**
1. User clicks toolbar/menu button
2. Handler calls `_on_quick_process(plan_name, workflow_name)`
3. Plan YAML loaded from `resources/config_defaults/plans/{plan_name}.yml`
4. DirectorIntegrationService.process_collection() called
5. Workflow executes via FicheroDirector
6. Outputs stored and displayed

---

## TOOLREGISTRY PARAMETER SCHEMAS

### Current Schemas

**Registered Tools (tool_registry.py):**

| # | Tool Name | Schema Method | Parameters | Validation | UI Hints | Status |
|---|-----------|---------------|------------|------------|----------|--------|
| 1 | crop | `_create_crop_schema()` | 4 params | ✅ Enums, ranges | ✅ Dropdowns | ✅ Complete |
| 2 | rotate | `_create_rotate_schema()` | 0 params | N/A | N/A | ✅ Minimal |
| 3 | enhance | `_create_enhance_schema()` | 0 params | N/A | N/A | ✅ Minimal |
| 4 | split | `_create_split_schema()` | 1 param | ✅ Enum | ✅ Dropdown | ✅ Complete |
| 5 | transcribe_qwen_max | `_create_transcribe_schema()` | 1 param | ✅ Enum | ✅ Dropdown | ✅ Complete |
| 6-20 | [All others] | - | - | - | - | ❌ Missing |

**Schema Coverage:** 5/20 (25%)

### Schema Examples

**crop Schema:**
```python
{
    'contour_template': {
        'type': 'enum',
        'values': ['auto', 'white_bg', 'dark_bg'],
        'default': 'auto',
        'label': 'Detection Mode',
        'description': 'Contour detection algorithm'
    },
    'contour_padding': {
        'type': 'integer',
        'min': 0,
        'max': 100,
        'default': 30,
        'label': 'Padding (px)',
        'description': 'Border padding around detected area'
    },
    # ... etc
}
```

**split Schema:**
```python
{
    'method': {
        'type': 'enum',
        'values': ['auto', 'center', 'fold'],
        'default': 'auto',
        'label': 'Split Method',
        'description': 'How to detect page boundary'
    }
}
```

### Missing Schemas (15 tools)

Tools needing parameter schemas:
- remove_background (method selection)
- prepare_images (quality, format)
- segment (confidence thresholds)
- recombine_segments (merge options)
- transcribe_lmstudio (model, prompt)
- describe_images (prompt selection)
- llm_process (prompt config, hierarchical mode)
- convert_to_word (layout options)
- json_to_word (template selection)
- json_to_excel (flatten options)
- convert_to_svg (SVG parameters)
- analyze_document_groups (analysis prompt)
- extract_library_metadata (filter options)
- build_documents_manifest (source folder)
- fuzzy_clean (phrase length thresholds)

---

## TOOLEXECUTOR DIRECT EXECUTION

### Current Implementation

**Supported Tools (tool_executor.py):**

| # | Tool Name | Execution Method | Line # | Status |
|---|-----------|------------------|--------|--------|
| 1 | crop | `_run_crop()` | XXX | ✅ Complete |
| 2 | rotate | `_run_rotate()` | XXX | ✅ Complete |
| 3 | enhance | `_run_enhance()` | XXX | ✅ Complete |
| 4-20 | [All others] | - | - | ❌ Missing |

**Execution Coverage:** 3/20 (15%)

### Execution Pattern

**Example: _run_crop() implementation:**
```python
def _run_crop(self, input_path: Path, output_folder: Path, parameters: dict):
    from fichero.tools.crop import process_image

    # Execute tool
    result = process_image(
        str(input_path),
        str(output_folder),
        **parameters
    )

    # Handle result
    if result.get('success'):
        output_path = result['output_file']
        return {'success': True, 'output_path': output_path}
    else:
        return {'success': False, 'error': result.get('error')}
```

### Missing Implementations (17 tools)

All tools except crop, rotate, enhance need:
1. `_run_{tool}()` method in ToolExecutor
2. Tool import statement
3. Parameter passing logic
4. Result handling
5. Error handling
6. UI update integration

---

## FICHEROCOMMAND SYSTEM

### Command Definitions

**Tool Commands Found:**

| # | Tool Name | Command ID | Label | Toolbar | Menu | Icon | Category |
|---|-----------|------------|-------|---------|------|------|----------|
| [Document all tool commands found] |

### Toolbar Layout

**Current Toolbar (macOS):**
```
[Library] [Collection] [New Collection] [Import ▾] [FlexSpace] [Settings] [Inspector] [Process] [Adjust]
```

**Tool Access Points:**
- Process button → Opens full process dialog with all workflows
- Import menu → Bulk import options
- (Individual tool buttons not on main toolbar currently)

### Command Integration Pattern

**Example Command Definition:**
```python
FicheroCommand(
    id="collection.quick_crop",
    label="Crop",
    action=self._on_quick_process_crop,
    show_in_toolbar=False,  # Not on main toolbar
    show_in_menu=True,      # In "Tools" menu
    toolbar_icon="crop@10x.png",
    category="image_processing",
    enabled=lambda: self.has_selection(),
    keyboard_shortcut="Cmd+Shift+C"
)
```

---

## INTEGRATION PATTERNS

### Pattern 1: Quick Process (Workflow-based)

**Used by:** 12 tools currently in TOOL_CONFIGS

**Flow:**
1. User clicks toolbar/menu button
2. Pre-configured plan/workflow specified
3. DirectorIntegrationService executes workflow
4. All workflow steps run in sequence
5. Outputs saved to collection cache
6. UI refreshed to show outputs

**Advantages:**
- Robust (uses proven Director system)
- Supports multi-step workflows
- Progress tracking built-in
- Handles large batches

**Disadvantages:**
- Heavyweight for single tool
- Requires plan YAML file
- Less interactive

### Pattern 2: Direct Execution (ToolExecutor)

**Used by:** 3 tools currently

**Flow:**
1. User selects item in collection
2. User clicks tool button
3. Parameter dialog shown (if tool has parameters)
4. Tool executes directly on last completed step
5. Output added as new step in same item
6. UI refreshed to show new step

**Advantages:**
- Fast for single items
- Interactive parameter selection
- Immediate feedback
- Step-by-step refinement

**Disadvantages:**
- Single item only (no batch)
- Tool execution in GUI thread (can freeze)
- Requires per-tool implementation
- No progress tracking

### Pattern 3: Full Process Dialog

**Used by:** All tools (via "Process" button)

**Flow:**
1. User clicks "Process" button
2. Dialog shows plan picker
3. User selects plan + workflow
4. Optional: Select items or whole collection
5. DirectorIntegrationService executes
6. Outputs displayed

**Advantages:**
- Flexible (any plan/workflow)
- User controls execution scope
- Supports complex workflows

**Disadvantages:**
- More clicks required
- Requires plan understanding
- Not quick access

---

## INTEGRATION GAP ANALYSIS

### Complete Integration Scorecard

| # | Tool | TOOL_CONFIGS | ToolRegistry | ToolExecutor | Command | Plan YAML | Total | Status |
|---|------|--------------|--------------|--------------|---------|-----------|-------|--------|
| 1 | crop | ✅ | ✅ | ✅ | ⚠️ | ✅ | 4.5/5 | 90% |
| 2 | rotate | ✅ | ✅ | ✅ | ⚠️ | ✅ | 4.5/5 | 90% |
| 3 | enhance | ✅ | ✅ | ✅ | ⚠️ | ✅ | 4.5/5 | 90% |
| 4 | split | ✅ | ✅ | ❌ | ⚠️ | ✅ | 3.5/5 | 70% |
| 5 | transcribe_qwen_max | ✅ | ✅ | ❌ | ⚠️ | ✅ | 3.5/5 | 70% |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |

### Critical Gaps

**High Priority (User-facing tools):**
1. **transcribe_lmstudio** - Missing from menu, no schema, no executor
   - Use case: Local transcription alternative to cloud
   - Impact: Medium (alternative to transcribe_qwen_max)

2. **json_to_excel** - Missing from menu, no schema, no executor
   - Use case: Export catalogues to Excel
   - Impact: High (requested export format)

3. **convert_to_svg** - Missing from menu, no schema, no executor
   - Use case: Searchable SVG generation
   - Impact: Medium (advanced feature)

**Medium Priority (Workflow tools):**
4. **fuzzy_clean** - Missing from menu, no schema, no executor
   - Use case: Clean OCR artifacts
   - Impact: Medium (quality improvement)

5. **analyze_document_groups** - Missing from menu, no schema, no executor
   - Use case: AI-powered document boundary detection
   - Impact: Low (specialized use case)

**Low Priority (Backend tools):**
6. **extract_library_metadata** - Backend integration tool
7. **build_documents_manifest** - Automatic (part of all workflows)
8. **json_to_word** - Duplicate of convert_to_word functionality

### Recommended Additions

**Phase 6 Implementation Priorities:**

**Priority 1: Add to TOOL_CONFIGS (8 tools)**
- All missing tools should be added to TOOL_CONFIGS
- Requires creating plan YAML files for each
- Enables workflow-based execution

**Priority 2: Add ToolRegistry Schemas (15 tools)**
- Focus on tools with user-configurable parameters
- High value: transcribe_lmstudio, llm_process, prepare_images, remove_background
- Medium value: segment, json_to_excel, convert_to_svg
- Low value: Tools with no parameters or automatic operation

**Priority 3: Add ToolExecutor Methods (17 tools)**
- Focus on single-item interactive tools
- High value: split, segment, remove_background, prepare_images
- Medium value: transcribe_lmstudio, describe_images
- Low value: Batch-only tools (build_documents_manifest, etc.)

**Priority 4: Create FicheroCommands (all tools)**
- Standardize command definitions
- Add to appropriate menus (Tools → Image Processing, etc.)
- Add keyboard shortcuts for common tools
- Consider adding most-used tools to toolbar

---

## RECOMMENDATIONS

### Immediate Actions

1. **Complete TOOL_CONFIGS coverage:**
   - Add 8 missing tools to CollectionView.TOOL_CONFIGS
   - Create plan YAML files for new tools
   - Test workflow execution

2. **Document command system:**
   - Create developer guide for FicheroCommand usage
   - Define command categories/organization
   - Standardize icon naming

3. **Prioritize schema additions:**
   - Add schemas for high-value configurable tools
   - Focus on transcribe_lmstudio, llm_process, prepare_images

### Long-term Improvements

1. **Unified tool menu:**
   - Create "Tools" menu with categorized submenus:
     - Image Processing (9 tools)
     - AI Processing (4 tools)
     - Document Generation (3 tools)
     - Analysis & Cleanup (4 tools)

2. **Toolbar customization:**
   - Allow users to add favorite tools to toolbar
   - Implement toolbar item priorities
   - Add tool search/command palette

3. **Smart defaults:**
   - Auto-detect best tool for selected content
   - Suggest next steps based on current processing state
   - Remember user's most-used tools

---

## PHASE 3 STATUS

- [x] CollectionView TOOL_CONFIGS audited (12/20 complete)
- [x] ToolRegistry schemas audited (5/20 complete)
- [x] ToolExecutor methods audited (3/20 complete)
- [x] FicheroCommand system documented
- [x] Integration patterns identified
- [x] Gap analysis completed
- [x] Recommendations provided

**Output:** GUI_INTEGRATION_STATUS.md complete
**Next Phase:** Phase 4 (Workflow/Plan Audit)

---

**Generated by:** Claude Code Phase 3 Agent
**Date:** 2025-11-15
**Quality:** Production-ready audit report
```

---

## QUALITY CHECKLIST

Before completing, verify:

- [ ] All 20 tools audited in each integration area
- [ ] Line numbers referenced for code locations
- [ ] Integration patterns documented with examples
- [ ] Gap analysis shows specific missing implementations
- [ ] Recommendations prioritized by impact
- [ ] Status section added to master plan

---

## COMPLETION CRITERIA

**Output file created:** `GUI_INTEGRATION_STATUS.md`

**File contents:**
- Complete audit of CollectionView, ToolRegistry, ToolExecutor
- FicheroCommand system documentation
- Integration pattern analysis
- Gap analysis with priorities
- Actionable recommendations

**Status update:** Update `TOOL_INTEGRATION_MASTER_PLAN.md`:
```markdown
## CURRENT STATUS

- [x] Phase 0: Architecture investigation complete
- [x] Phase 1: Tool inventory complete
- [x] Phase 2: Renderer audit complete
- [x] Phase 3: GUI integration audit complete
- [ ] Phase 4: Workflow audit (NEXT)
```

---

## IMPORTANT NOTES

- **READ-ONLY:** Do not modify any code files, only read and document
- **Complete Coverage:** Audit all 20 tools in each integration area
- **Actionable:** Recommendations should be specific and implementable
- **Prioritized:** Gap analysis should show high/medium/low priorities

---

**When complete, report:** "Phase 3 complete. GUI_INTEGRATION_STATUS.md created with complete audit of tool integration across CollectionView, ToolRegistry, ToolExecutor, and FicheroCommand systems. Integration gaps identified and prioritized. Ready for Phase 4 (Workflow Audit)."
