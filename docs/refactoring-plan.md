# SwiftUI Views Refactoring Plan

**Created:** 2026-02-19
**Status:** Planning Phase
**Goal:** Reduce all Swift view files to < 400 lines (recommended) or < 1000 lines (hard limit)

## Executive Summary

Found **29 files** exceeding the 400-line guideline, ranging from 401 to 1144 lines.

**Impact:**
- Improves maintainability and code review
- Reduces SwiftLint violations
- Enables better code reuse
- Simplifies testing and preview creation

**Timeline:** 5-7 days of focused refactoring work

---

## Priority Classification

### P0 - Critical (PRODUCTION BLOCKERS)
Files > 1000 lines that block production readiness:

1. **NodePopover.swift** - 1144 lines
   - **Current state:** Monolithic popover with all node configuration logic
   - **Target:** Split into 4 files (< 350 lines each)
   - **Effort:** HIGH (3-4 hours)

2. **ImageViewerComponents.swift** - 1034 lines
   - **Current state:** All image viewing components in one file
   - **Target:** Split into 5 separate component files (< 250 lines each)
   - **Effort:** MEDIUM (2-3 hours)

### P1 - High Priority
Files 800-1000 lines requiring significant refactoring:

3. **WorkflowEditor.swift** - 1007 lines
   - **Current state:** Main workflow editor with canvas, toolbar, inspector
   - **Target:** Split into 3 files: Editor, Toolbar, State Management
   - **Effort:** HIGH (3-4 hours)

4. **SidebarView.swift** - 868 lines
   - **Current state:** Main sidebar with mode switching logic
   - **Target:** Extract mode-specific helpers, reduce to < 400 lines
   - **Effort:** MEDIUM (2 hours)

5. **WorkflowLibraryView.swift** - 818 lines
   - **Target:** Extract list/grid view components
   - **Effort:** MEDIUM (2 hours)

6. **LibraryView.swift** - 805 lines
   - **Target:** Split into view modes (Icons, List, Table)
   - **Effort:** MEDIUM (2-3 hours)

### P2 - Medium Priority
Files 600-800 lines:

7. **SearchView.swift** - 698 lines
8. **ChatView.swift** - 681 lines
9. **DocumentInspector.swift** - 605 lines
10. **TriggerEditorView.swift** - 605 lines
11. **SettingsView.swift** - 589 lines

### P3 - Low Priority
Files 400-600 lines (just over limit, can be deferred):

12-29. Various files between 401-589 lines

---

## Refactoring Strategies

### Strategy 1: Extract View Components
**When to use:** File contains multiple distinct UI sections

**Pattern:**
```swift
// Before: LibraryView.swift (805 lines)
struct LibraryView: View {
    var body: some View {
        // Icon grid logic (200 lines)
        // List view logic (200 lines)
        // Table view logic (200 lines)
        // Toolbar (100 lines)
    }
}

// After: Split into 4 files
// LibraryView.swift (< 200 lines) - main coordinator
// LibraryIconGrid.swift (< 250 lines)
// LibraryListView.swift (< 250 lines)
// LibraryTableView.swift (< 250 lines)
```

### Strategy 2: Extract View Extensions
**When to use:** File has helper methods, computed properties

**Pattern:**
```swift
// Before: NodePopover.swift (1144 lines)
struct NodePopover: View {
    var body: some View { ... }
    private func buildToolSection() { ... }
    private func buildParametersSection() { ... }
    private func buildConnectionsSection() { ... }
}

// After:
// NodePopover.swift (< 300 lines) - main view
// NodePopover+Tools.swift (< 300 lines)
// NodePopover+Parameters.swift (< 300 lines)
// NodePopover+Connections.swift (< 300 lines)
```

### Strategy 3: Extract View Models
**When to use:** Complex state management logic

**Pattern:**
```swift
// Before: WorkflowEditor.swift (1007 lines)
struct WorkflowEditor: View {
    @State private var selectedNodes: Set<String> = []
    @State private var dragState: DragState = .idle
    // ... 50+ @State variables

    private func handleNodeSelection() { ... }
    private func handleDragGesture() { ... }
    // ... 30+ helper methods
}

// After:
// WorkflowEditor.swift (< 350 lines) - view only
// WorkflowEditorViewModel.swift (< 350 lines) - state + logic
// WorkflowEditorActions.swift (< 300 lines) - event handlers
```

### Strategy 4: Extract Configuration Views
**When to use:** Large switch/if-else blocks for different types

**Pattern:**
```swift
// Before: NodePopover.swift
switch node.tool {
    case "llm": /* 100 lines */
    case "files": /* 80 lines */
    case "search": /* 90 lines */
    // ... 15+ cases
}

// After:
// NodePopover.swift - delegates to specific configs
// Configs/LLMNodeConfig.swift
// Configs/FilesNodeConfig.swift
// Configs/SearchNodeConfig.swift
```

---

## Detailed Refactoring Plans

### P0-1: NodePopover.swift (1144 lines)

**Current Structure:**
- Main popover view (100 lines)
- Tool configuration (400 lines)
- Parameter forms (300 lines)
- Connection management (200 lines)
- Validation logic (144 lines)

**Refactoring Plan:**

#### Phase 1: Extract Tool Configurations (Day 1)
Create `Views/Workflow/NodeConfigs/` directory:

1. **NodeConfigProtocol.swift** (< 50 lines)
   ```swift
   protocol NodeConfigView: View {
       var node: Binding<WorkflowNode> { get }
   }
   ```

2. **LLMNodeConfig.swift** (< 150 lines)
   - Model selection
   - Temperature/top_p sliders
   - System prompt

3. **FilesNodeConfig.swift** (< 120 lines)
   - File picker
   - File filters
   - Recursive options

4. **SearchNodeConfig.swift** (< 150 lines)
   - Search query builder
   - Filter options
   - Result limits

5. **ToolNodeConfig.swift** (< 150 lines)
   - Generic tool config for remaining tools

**Files created:** 5 files, ~620 lines total (was 400 lines inline)

#### Phase 2: Extract Parameter Management (Day 1-2)
1. **NodeParameterForm.swift** (< 250 lines)
   - Dynamic parameter form generation
   - Type-specific input fields
   - Validation display

2. **NodeParameterHelpers.swift** (< 150 lines)
   - Parameter validation functions
   - Default value generation
   - Type conversion utilities

**Files created:** 2 files, ~400 lines total (was 300 lines inline)

#### Phase 3: Extract Connection UI (Day 2)
1. **NodeConnectionView.swift** (< 200 lines)
   - Port listing
   - Connection status
   - Edge management

**Files created:** 1 file, 200 lines (was 200 lines inline)

#### Phase 4: Main File Cleanup (Day 2)
**NodePopover.swift** → < 300 lines
- Popover shell
- Tab navigation
- Delegates to extracted views

**Result:**
- **Before:** 1 file, 1144 lines
- **After:** 9 files, ~1520 lines total (but each < 300 lines)
- **SwiftLint:** Compliant (all files < 400 lines)

---

### P0-2: ImageViewerComponents.swift (1034 lines)

**Current Structure:**
- ImageCanvasView (300 lines)
- ImageNavigatorView (200 lines)
- ImageControlsView (150 lines)
- Zoom/Pan handlers (200 lines)
- Drawing overlays (184 lines)

**Refactoring Plan:**

#### Phase 1: Split into Component Files (Day 3)

1. **ImageCanvasView.swift** (< 300 lines)
   - Main image display canvas
   - Gesture handling
   - Zoom/pan state

2. **ImageNavigatorView.swift** (< 250 lines)
   - Thumbnail navigator
   - Page selection
   - Multi-page navigation

3. **ImageControlsToolbar.swift** (< 200 lines)
   - Zoom controls
   - Rotation controls
   - Fit/fill buttons

4. **ImageDrawingOverlay.swift** (< 200 lines)
   - Annotation rendering
   - Selection boxes
   - Measurement tools

5. **ImageZoomHandler.swift** (< 150 lines)
   - Zoom calculations
   - Pan boundaries
   - Gesture state management

**Result:**
- **Before:** 1 file, 1034 lines
- **After:** 5 files, ~1100 lines total (but each < 300 lines)
- **SwiftLint:** Compliant

---

### P1-1: WorkflowEditor.swift (1007 lines)

**Current Structure:**
- Main editor view (200 lines)
- Toolbar (150 lines)
- Canvas integration (300 lines)
- Inspector panel (200 lines)
- State management (157 lines)

**Refactoring Plan:**

#### Phase 1: Extract Toolbar (Day 4)
1. **WorkflowEditorToolbar.swift** (< 200 lines)
   - Play/pause/stop buttons
   - Zoom controls
   - Grid toggle
   - Export/import

#### Phase 2: Extract State Management (Day 4)
2. **WorkflowEditorState.swift** (< 250 lines)
   - Observable state container
   - Selection management
   - Undo/redo state
   - Validation state

#### Phase 3: Main File Cleanup (Day 4)
**WorkflowEditor.swift** → < 350 lines
- Main coordinator view
- Canvas integration
- Inspector integration
- Delegates to toolbar and state

**Result:**
- **Before:** 1 file, 1007 lines
- **After:** 3 files, ~800 lines total
- **SwiftLint:** Compliant

---

### P1-2: SidebarView.swift (868 lines)

**Current Structure:**
- Main sidebar (150 lines)
- Mode switching (200 lines)
- Context menus (250 lines)
- Drag/drop handlers (200 lines)
- State updates (68 lines)

**Refactoring Plan:**

#### Already Partially Refactored
Good news: Mode-specific content already extracted to `Sidebar/Modes/` directory:
- ✅ ActivitySidebarContent.swift
- ✅ ChatSidebarContent.swift
- ✅ LibrarySidebarContent.swift
- ✅ WorkflowsSidebarContent.swift
- ✅ BatchesSidebarContent.swift
- ✅ AutomationSidebarContent.swift
- ✅ SearchSidebarContent.swift

#### Remaining Refactoring (Day 5)
1. **Extract SidebarDragDropHandlers.swift** (< 200 lines)
   - File drop handling
   - Document drop handling
   - Reordering logic

2. **Extract SidebarContextMenus.swift** (< 250 lines)
   - Item context menus
   - Folder context menus
   - Collection context menus

3. **SidebarView.swift** → < 350 lines
   - Mode bar
   - Content routing
   - Delegates to handlers

**Result:**
- **Before:** 1 file, 868 lines
- **After:** 3 files, ~800 lines total
- **SwiftLint:** Compliant

---

### P1-3: LibraryView.swift (805 lines)

**Current Structure:**
- Main view (150 lines)
- Icon grid (250 lines)
- List view (200 lines)
- Table view (205 lines)

**Refactoring Plan:**

#### Phase 1: Extract View Modes (Day 5-6)

1. **LibraryIconGridView.swift** (< 300 lines)
   - Grid layout
   - Icon rendering
   - Selection handling

2. **LibraryListView.swift** (< 250 lines)
   - List layout
   - Row views
   - Hierarchical display

3. **LibraryTableView.swift** (< 250 lines)
   - Table columns
   - Sorting
   - Column configuration

4. **LibraryView.swift** → < 250 lines
   - View mode switcher
   - Toolbar integration
   - Delegates to view modes

**Result:**
- **Before:** 1 file, 805 lines
- **After:** 4 files, ~1050 lines total (but each < 300 lines)
- **SwiftLint:** Compliant

---

## Implementation Order

### Week 1 (Days 1-5)
**Day 1:**
- [x] Create refactoring plan
- [ ] P0-1 Phase 1: Extract NodePopover tool configs
- [ ] P0-1 Phase 2: Extract NodePopover parameters

**Day 2:**
- [ ] P0-1 Phase 3: Extract NodePopover connections
- [ ] P0-1 Phase 4: Cleanup NodePopover main file
- [ ] Test NodePopover refactoring
- [ ] Build verification

**Day 3:**
- [ ] P0-2: Refactor ImageViewerComponents
- [ ] Test ImageViewer refactoring
- [ ] Build verification

**Day 4:**
- [ ] P1-1: Refactor WorkflowEditor
- [ ] Test WorkflowEditor refactoring
- [ ] Build verification

**Day 5:**
- [ ] P1-2: Refactor SidebarView
- [ ] P1-3: Start LibraryView refactoring
- [ ] Build verification

### Week 2 (Days 6-7)
**Day 6:**
- [ ] P1-3: Complete LibraryView refactoring
- [ ] Test all P0-P1 refactoring
- [ ] SwiftLint verification

**Day 7:**
- [ ] P2 files: Quick wins (SearchView, ChatView)
- [ ] Final build verification
- [ ] Update documentation
- [ ] Create PR

---

## Testing Strategy

### Per-File Testing
After each refactoring:
1. ✅ Build passes
2. ✅ SwiftLint passes (zero warnings)
3. ✅ Preview renders
4. ✅ Manual smoke test (if possible)

### Integration Testing
After each priority level:
1. Full app build
2. Run Swift tests: `xcodebuild test -project fichero-swiftui/fichero-swiftui.xcodeproj -scheme Fichero`
3. Manual testing of affected features

---

## Risk Mitigation

### Risks
1. **Breaking existing functionality** - High
2. **Preview crashes** - Medium
3. **Environment object issues** - Medium
4. **Build time increase** - Low

### Mitigation
1. **Git branches:** Create feature branch for each P0/P1 file
2. **Incremental commits:** Commit after each phase
3. **Testing:** Test after each file
4. **Rollback plan:** Keep original files as `.backup` until verified
5. **Pair review:** Review file structure before implementation

---

## Success Criteria

### Phase 1 (P0 files) - Week 1
- [ ] NodePopover.swift < 400 lines
- [ ] ImageViewerComponents.swift < 400 lines (main file)
- [ ] All extracted files < 400 lines
- [ ] Build passes
- [ ] SwiftLint passes (zero warnings)
- [ ] Previews work

### Phase 2 (P1 files) - Week 1-2
- [ ] WorkflowEditor.swift < 400 lines
- [ ] SidebarView.swift < 400 lines
- [ ] LibraryView.swift < 400 lines
- [ ] Build passes
- [ ] SwiftLint passes (zero warnings)
- [ ] Tests pass

### Phase 3 (P2 files) - Week 2
- [ ] SearchView.swift < 400 lines
- [ ] ChatView.swift < 400 lines
- [ ] At least 15 files reduced below 400 lines
- [ ] Total lines reduced by 20%
- [ ] All tests passing

---

## File Organization Conventions

### Directory Structure
```
Views/
├── Workflow/
│   ├── NodePopover.swift (< 300 lines)
│   ├── NodeConfigs/
│   │   ├── LLMNodeConfig.swift
│   │   ├── FilesNodeConfig.swift
│   │   ├── SearchNodeConfig.swift
│   │   └── ToolNodeConfig.swift
│   ├── NodeParameterForm.swift
│   ├── NodeConnectionView.swift
│   └── WorkflowEditor.swift (< 350 lines)
├── Library/
│   ├── LibraryView.swift (< 250 lines)
│   ├── LibraryIconGridView.swift
│   ├── LibraryListView.swift
│   └── LibraryTableView.swift
└── ...
```

### Naming Conventions
- **Main views:** Keep original name (e.g., `LibraryView.swift`)
- **Extracted components:** `<Parent><ComponentName>.swift` (e.g., `LibraryIconGridView.swift`)
- **Extensions:** `<Parent>+<Feature>.swift` (e.g., `NodePopover+Tools.swift`)
- **View models:** `<View>ViewModel.swift` or `<View>State.swift`
- **Helpers:** `<View>Helpers.swift`

### Import Strategy
```swift
// In main file (LibraryView.swift)
import SwiftUI

// In extracted file (LibraryIconGridView.swift)
import SwiftUI
// Import parent if needed, but prefer protocols/dependency injection
```

---

## SwiftLint Configuration

Current guidelines:
- **File length:** < 400 lines recommended, < 1000 hard limit
- **Type body length:** < 250 lines
- **Function length:** < 50 lines
- **Cyclomatic complexity:** < 10

After refactoring, all files should:
- ✅ Pass file length (< 400)
- ✅ Pass type body length (< 250)
- ✅ Pass function length (< 50)
- ⚠️ Reduce cyclomatic complexity where possible

---

## Next Steps

1. **Get user approval** for this plan
2. **Create feature branch:** `refactor/reduce-large-files`
3. **Start with P0-1:** NodePopover.swift
4. **Commit incrementally:** Each phase gets its own commit
5. **Test continuously:** Build + lint after each file

**Estimated Total Effort:** 30-35 hours over 5-7 days

---

**Status:** 📋 Plan Complete - Ready for Implementation
**Last Updated:** 2026-02-19
