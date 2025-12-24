# Workflow Editor Layout Plan

## Current Problem

The workflow editor has its own 3-pane horizontal layout (Blocks | Canvas | Inspector) that doesn't integrate with the NavigationSplitView properly. It should follow the same pattern as Library mode.

## Current Layout (Wrong)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Toolbar                                                          [Export][▶]│
├──────────┬──────────┬─────────────────────────────┬─────────────────────────┤
│ SIDEBAR  │ BLOCKS   │         CANVAS              │      PROVIDERS          │
│          │          │                             │                         │
│ Library  │ Transcr. │    ┌───┐   ┌───┐   ┌───┐   │  [DashScope     ▾]     │
│ Searches │ Entities │    │ S │───│ T │───│ E │   │  [Qwen VL Max   ▾]     │
│ Workflows│ Summary  │    └───┘   └───┘   └───┘   │                         │
│  > Full  │ etc...   │                             │  [+ Add Provider]       │
│  > Quick │          │                             │                         │
│          │          │                             │  No Step Selected       │
└──────────┴──────────┴─────────────────────────────┴─────────────────────────┘
```

**Problems:**
- Blocks palette is between sidebar and canvas (should be on right)
- Canvas doesn't fill the main content area
- Doesn't match library view pattern

## Desired Layout (Correct)

Match the Library mode layout pattern:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Toolbar                                                     [Export] [▶ Run]│
├──────────┬──────────────────────────────────────────────┬───────────────────┤
│ SIDEBAR  │              NODE CANVAS                      │    INSPECTOR     │
│          │                                               │                  │
│ Library  │   ┌─────────────────────────────────────┐    │  ▼ Blocks        │
│ Searches │   │                                     │    │   [Transcribe]   │
│ Workflows│   │    ┌───────┐      ┌───────┐        │    │   [Entities]     │
│  > Full  │   │    │ START │──────│  OCR  │─┐      │    │   [Summary]      │
│  > Quick │   │    │       │      │       │ │      │    │   ...            │
│  > Local │   │    └───────┘      └───────┘ │      │    │                  │
│          │   │                              │      │    │  ▼ Step Config   │
│          │   │    ┌───────┐      ┌───────┐ │      │    │   Name: [OCR   ] │
│          │   │    │ END   │◄─────│SUMMARY│◄┘      │    │   Provider: [▾]  │
│          │   │    │       │      │       │        │    │   Model: [▾]     │
│          │   │    └───────┘      └───────┘        │    │                  │
│          │   │                                     │    │  ▼ Providers     │
│          │   └─────────────────────────────────────┘    │   [+ Add]        │
│          │                                               │   DashScope ●    │
│          ├───────────────────────────────────────────────┤   OpenAI ●       │
│          │  OUTPUT LOG (collapsible)                     │                  │
│          │  Document        │ Transcribe │ Summary │     │  [Delete Step]   │
│          │  letter_001.jpg  │ ✓ 2.3s     │ ○ pend  │     │                  │
│          │  letter_002.jpg  │ 🔄 running │ ○ pend  │     │                  │
└──────────┴───────────────────────────────────────────────┴───────────────────┘
```

## Layout Components

### 1. Sidebar (Unchanged)
- Same as library view
- Shows Library, Searches, Workflows sections
- Selecting a workflow switches to workflow mode

### 2. Main Content Area (Canvas + Output)
Split vertically into:

**A. Node Canvas (Top, expandable)**
- Grid background with pan/zoom
- START node (green) - represents input documents
- Step nodes (colored by type) - draggable, selectable
- END node (red) - represents output
- Connection lines between nodes
- Click node to select and configure in inspector
- Drag from Blocks palette to add new steps

**B. Output Log (Bottom, collapsible)**
- Table showing processing progress
- Columns: Document | Step1 | Step2 | Step3...
- Status icons: ✓ done, 🔄 running, ○ pending, ✗ failed
- Collapsible - can hide when not running
- Shows only during/after workflow execution

### 3. Inspector (Right Side)
Collapsible sections:

**A. Blocks Palette**
- Draggable blocks to add to workflow
- Categories: Processing, Enhancement, Export
- Compact view (icons + names)

**B. Step Configuration** (when step selected)
- Step name (editable)
- Tool type (read-only)
- Provider dropdown
- Model dropdown
- Custom prompt (optional)

**C. Providers**
- List of configured providers
- [+ Add] button to add new provider
- Status indicator (connected/error)

**D. Actions**
- [Delete Step] button (when step selected)
- [Duplicate Step] button

### 4. Toolbar
- Standard macOS toolbar position
- [Export] - Export workflow definition
- [▶ Run] - Execute workflow (prominent, green)

## Implementation Plan

### Phase 1: Restructure Layout
1. Move WorkflowView content into NavigationSplitView pattern
2. Canvas goes in "content" column (like BrowserView)
3. Blocks + Inspector go in "detail" column (like EditorView + InspectorView)

### Phase 2: Create Inspector Sections
1. `WorkflowBlocksPalette` - compact draggable blocks
2. `WorkflowStepConfig` - configuration for selected step
3. `WorkflowProvidersList` - provider management
4. Combine into `WorkflowInspectorView`

### Phase 3: Canvas Improvements
1. Proper node layout algorithm
2. Connection line routing
3. Pan and zoom gestures
4. Node selection and drag

### Phase 4: Output Log
1. Create `WorkflowOutputLog` view
2. VSplitView to split canvas and log
3. Collapsible behavior
4. Progress tracking during execution

## File Changes

```
Views/Workflow/
├── WorkflowView.swift           # Main view (simplified)
├── WorkflowCanvasView.swift     # Node canvas only
├── WorkflowInspectorView.swift  # Right panel with sections
├── WorkflowOutputLog.swift      # Bottom output table
├── Components/
│   ├── NodeView.swift           # Individual node
│   ├── ConnectionLine.swift     # Lines between nodes
│   ├── BlocksPalette.swift      # Draggable blocks
│   └── StepConfigView.swift     # Step configuration
```

## Questions to Resolve

1. **Output Log Position**: Bottom of canvas area, or separate panel?
2. **Output Log Visibility**: Always visible, or only during/after run?
3. **Canvas Zoom Controls**: Buttons? Pinch gesture? Both?
4. **Multiple Selection**: Allow selecting multiple steps?
5. **Undo/Redo**: Support for workflow editing?
