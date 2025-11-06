# OutputView Refactoring Plan

## Goal
Refactor OutputView from a monolithic 3,039-line file into a modular, testable, maintainable system with CLI-first development.

## Current Problems
1. **Monolithic** - Everything in one 3,039-line file
2. **Multiple code paths** - Legacy file-based vs library-based navigation
3. **Tight coupling** - HTML generation mixed with business logic
4. **No extensibility** - Hard to add new tool visualizations
5. **Missing features** - Can't edit steps, view plans/prompts, or have flexible layouts

## Architecture Layers

### 1. Data Layer (Library - Source of Truth)
**Location:** `src/fichero/library/`

**Responsibilities:**
- Store all workflow outputs in SQLite
- Parse manifests and provide step data
- **NEW**: Edit and save step data back
- **NEW**: Provide JSON for editing

**Key Methods:**
```python
# Existing
async get_item_output_data(item_id) -> dict

# New - to add
async get_step_data(item_id, step_index) -> Step
async save_step_data(item_id, step_index, data) -> bool
async get_step_json(item_id, step_index) -> dict
async save_step_json(item_id, step_index, json_data) -> bool
```

### 2. CLI Layer (Test Everything Here First)
**Location:** `src/fichero/cli/library_commands.py`

**New Commands:**
```bash
# View a step's output
briefcase dev -- library view-step <item_id> --step 2

# Edit a step (opens in $EDITOR or shows JSON)
briefcase dev -- library edit-step <item_id> --step 2

# Save edited step back
briefcase dev -- library save-step <item_id> --step 2 --file edited.json

# Test a tool's renderer
briefcase dev -- library test-renderer prepare_images --item-id <id> --step 0

# Render step to HTML file
briefcase dev -- library render-step <item_id> --step 2 --output test.html
```

### 3. Renderer System (One Per Tool)
**Location:** `src/fichero/library/renderers/`

**Architecture:**
```
BaseRenderer (abstract)
├── render_html() - Generate HTML view
├── render_json() - Get editable JSON
├── validate_json() - Validate edited JSON
└── apply_edits() - Apply JSON edits back to files

ImageRenderer (base for image tools)
├── PrepareImagesRenderer
├── RotateRenderer
├── CropRenderer
├── EnhanceRenderer
├── RemoveBackgroundRenderer
└── SegmentRenderer

TextRenderer (base for text)
├── TranscribeQwenRenderer
├── TranscribeLMStudioRenderer
├── FuzzyCleanRenderer
└── RecombineSegmentsRenderer

JsonRenderer (base for JSON/data)
├── LlmProcessRenderer (catalog JSON)
├── ExtractMetadataRenderer
└── BuildDocumentsManifestRenderer

DocumentRenderer (Word docs)
├── ConvertToWordRenderer
├── JsonToWordRenderer
└── JsonToExcelRenderer

SvgRenderer
└── ConvertToSvgRenderer

FolderRenderer (folder-level views)
├── AnalyzeDocumentGroupsRenderer
└── DescribeImagesRenderer
```

**Total:** 24 renderers (one per tool)

**RendererRegistry:**
- Auto-discovers renderers
- Maps tool names to renderer classes
- Provides fallbacks based on file type

### 4. UI Layer (After CLI Works)
**Location:** `src/fichero/windows/main/views/output/`

**Components:**

1. **StepManager** (`step_manager.py`)
   - UI state only (current step index, nav state)
   - Interfaces with library for data
   - NOT a data layer (library handles that)

2. **LayoutManager** (`layout_manager.py`)
   - Manages split view configurations:
     - Single: `[Output]`
     - Two pane: `[Output | Inspector]`
     - Three pane: `[Output | Inspector | Output]`
     - Four pane: `[Output | Inspector | Output | Inspector]`
   - Toolbar buttons for layout changes
   - Detached window support

3. **OutputPane** (`output_pane.py`)
   - Single reusable output pane
   - Uses renderers to display content
   - Handles zoom, rotation, scrolling

4. **OutputView** (`output_view.py` - refactored to ~300 lines)
   - Orchestrator only
   - Creates layout with panes
   - Delegates rendering to renderers
   - No HTML generation
   - No legacy code paths

**Shared Components:**

5. **JsonEditor** (`src/fichero/shared/components/json_editor.py`)
   - Standalone JSON editor
   - Can be embedded in inspector OR output view
   - Save callback for persistence

6. **MetadataViewer** (`src/fichero/shared/components/metadata_viewer.py`)
   - Display metadata in structured way
   - Reusable across views

## Implementation Phases

### PHASE 1: Library Enhancement (CLI-testable)
**Goal:** Add edit/save capabilities to library, test in CLI

**Files to modify:**
- `src/fichero/library/library_manager.py`
- `src/fichero/cli/library_commands.py`

**Deliverables:**
- `library view-step` command
- `library edit-step` command
- `library save-step` command
- Unit tests for edit/save

### PHASE 2: Renderer System (CLI-testable)
**Goal:** Create pluggable renderer architecture, test each renderer in CLI

**Files to create:**
- `src/fichero/library/renderers/base_renderer.py`
- `src/fichero/library/renderers/image_renderer.py`
- `src/fichero/library/renderers/text_renderer.py`
- `src/fichero/library/renderers/json_renderer.py`
- `src/fichero/library/renderers/svg_renderer.py`
- `src/fichero/library/renderers/folder_renderer.py`
- 24 tool-specific renderer files
- `src/fichero/library/renderer_registry.py`

**CLI Commands:**
- `library test-renderer <tool_name>`
- `library render-step <item_id> --step N --output file.html`

**Deliverables:**
- All 24 renderers implemented
- Each renderer tested in CLI
- Unit tests for each renderer

### PHASE 3: Reusable UI Components
**Goal:** Create inspector components that work standalone

**Files to create:**
- `src/fichero/shared/components/json_editor.py`
- `src/fichero/shared/components/metadata_viewer.py`

**Deliverables:**
- Standalone JSON editor component
- Metadata viewer component
- Can be embedded anywhere

### PHASE 4: OutputView Refactor
**Goal:** Refactor GUI to use new architecture

**Files to create:**
- `src/fichero/windows/main/views/output/step_manager.py`
- `src/fichero/windows/main/views/output/layout_manager.py`
- `src/fichero/windows/main/views/output/output_pane.py`

**Files to refactor:**
- `src/fichero/windows/main/views/output/output_view.py` (3039 → ~300 lines)

**Deliverables:**
- Clean separation of concerns
- Reusable output panes
- Flexible layout system
- Inspector sidebar integrated
- All legacy code removed

### PHASE 5: Advanced Features
**Goal:** Multiple views, detached windows, edit workflows

**Features:**
- Multiple output views side-by-side
- Detached output windows
- Edit-save-reprocess workflow
- Toolbar buttons for layout control

## Key Principles

1. **CLI-First Development**
   - Build and test everything in CLI first
   - Unit test each component
   - Then integrate into GUI

2. **Single Source of Truth**
   - Library stores all data
   - No file scanning in UI
   - No manifest parsing in UI

3. **Separation of Concerns**
   - Library = Data (what to show)
   - StepManager = State (where we are)
   - Renderers = Presentation (how to show it)
   - LayoutManager = Layout (how to arrange it)

4. **Plugin Architecture**
   - Each tool has its own renderer
   - Easy to add new tools
   - Renderers are self-contained

5. **Reusable Components**
   - Inspector can be used standalone or embedded
   - Output panes are reusable
   - JSON editor is reusable

## Success Criteria

1. **Maintainability**
   - No file over 500 lines
   - Clear separation of concerns
   - Easy to find code

2. **Testability**
   - All components unit tested
   - CLI commands for manual testing
   - Renderers testable independently

3. **Extensibility**
   - Adding new tool = adding one renderer file
   - No changes to core OutputView

4. **Flexibility**
   - Multiple layout configurations
   - Detached windows
   - Edit and save workflow

5. **No Legacy Code**
   - Single code path (library-based)
   - No file-based navigation
   - No mixed concerns
