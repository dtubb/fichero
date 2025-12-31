# Fichero Naming Conventions

**Last Updated:** 2025-12-30
**Based On:** Apple's Official SwiftUI Guidelines, WWDC23, and macOS HIG

This document establishes the naming conventions for all views, models, and components in Fichero, following Apple's official patterns from Xcode, Finder, and SwiftUI sample code.

---

## Core Principles

1. **Follow Apple's macOS conventions** - Use terminology from Xcode, Finder, Pages
2. **Clarity over brevity** - `DocumentInspector` not `DocInsp`
3. **Functional naming** - Names describe purpose, not location
4. **Consistency** - Same patterns across similar components

---

## View Naming Patterns

### Inspector Pattern (Right Column)

**Apple Convention:** "Inspector" is the official term for views showing detail of selected content.

| Current Name | Correct Name | Rationale |
|--------------|--------------|-----------|
| `InspectorView` | **Keep as `InspectorView`** | Generic container - correct per Apple |
| `ChatInspectorView` | **Rename to `ChatInspector`** | Drop redundant "View" suffix when context is clear |
| `WorkflowInspectorView` | **Rename to `WorkflowInspector`** | Consistent with Xcode pattern (File Inspector, Quick Help Inspector) |
| *(new)* | **`DocumentInspector`** | For library/search modes showing document metadata |

**Pattern:** `{Context}Inspector` - follows Xcode's File Inspector, Attributes Inspector, etc.

**Container Pattern:**
```swift
// Generic container with mode-switching
struct InspectorView: View {
    let mode: AppViewMode
    let selection: Selection?

    var body: some View {
        switch mode {
        case .library, .search:
            DocumentInspector(document: selection?.document)
        case .chat:
            ChatInspector(conversation: selection?.conversation)
        case .workflow:
            WorkflowInspector(workflow: selection?.workflow)
        }
    }
}
```

**Why this works:**
- ✅ Follows Apple's official terminology
- ✅ Scalable - adding `AgentInspector`, `MCPToolInspector` is natural
- ✅ Generic container stays generic, specific inspectors are specific
- ✅ Future-proof - if ChatInspector needs to show settings/model selection, name still makes sense

---

### Content Views (Center Column)

**Apple Convention:** Content views describe what they display, not how.

| Current Name | Correct Name | Rationale |
|--------------|--------------|-----------|
| `BrowserView` | **`LibraryView`** | Shows library content, "browser" is ambiguous |
| `SearchView` | **Keep as `SearchView`** | Correct - describes function |
| `ChatView` | **Keep as `ChatView`** | Correct - describes function |
| `WorkflowView` | **`WorkflowEditor`** | "Editor" is clearer - describes editing workflows |
| `EditorView` | **Keep as `EditorView`** | Correct - standard macOS term |

**Alternative for BrowserView:**
- `LibraryView` - Simple, clear (⭐ **Recommended**)
- `DocumentGalleryView` - More visual/descriptive
- `CollectionView` - Too generic, conflicts with UIKit

**Why LibraryView:**
- ✅ Matches sidebar section name ("Library")
- ✅ Parallel naming: Library section shows LibraryView
- ✅ Clear purpose - displays library documents
- ✅ Consistent with ContentView mode switching: `.library` → `LibraryView`

---

### Layout Modes (Inside LibraryView)

**Apple Convention:** Layout/presentation modes describe the visual structure.

| Current Name | Correct Name | Rationale |
|--------------|--------------|-----------|
| `BrowserViewMode` enum | **`LibraryLayout`** enum | Describes layout options, not view mode |
| `.icons` | **Keep `.icons`** | Standard term (Finder uses this) |
| `.list` | **Keep `.list`** | Standard term |
| `.table` | **Keep `.table`** | Standard term |
| `.map` | **Keep `.map`** | Descriptive for canvas/spatial layout |

**Type definition:**
```swift
enum LibraryLayout: String, CaseIterable {
    case icons  // Grid of thumbnails
    case list   // Mail-style list with preview
    case table  // Sortable table with columns
    case map    // Spatial canvas (Tinderbox-style)
}
```

**Usage:**
```swift
struct LibraryView: View {
    var layout: LibraryLayout = .icons

    var body: some View {
        switch layout {
        case .icons: IconsLayoutView(...)
        case .list: ListLayoutView(...)
        case .table: TableLayoutView(...)
        case .map: MapLayoutView(...)
        }
    }
}
```

---

### Model Browser / AI Catalog

**Apple Convention:** Avoid ambiguous "Model" term - be specific.

| Current Name | Correct Name | Rationale |
|--------------|--------------|-----------|
| `ModelBrowserView` | **`AIModelCatalog`** | "Model" is ambiguous (data model vs AI model) |
| `ModelBrowserContent` | **`AIModelSelectionView`** | AI prefix for consistency |
| `ProviderModelBrowserSheet` | **`AIProviderAddModelsSheet`** | Clear intent - add models to a provider |

**Why AIModelCatalog:**
- ✅ No confusion with data models
- ✅ "Catalog" implies browsing/discovery
- ✅ Parallels App Store, Mac App Store naming
- ✅ Consistent: AI models live in AI domain, not generic "models"

**Alternative names considered:**
- `HuggingFaceModelBrowser` - Too specific to one source
- `ModelDiscoveryView` - Okay but "Discovery" is Apple Music term
- `ModelExplorer` - Good but "Explorer" isn't standard macOS term

---

### Workflow Components

**Apple Convention:** Component hierarchy should be clear from names.

| Current Name | Correct Name | Rationale |
|--------------|--------------|-----------|
| `WorkflowCanvasView` | **Keep as `WorkflowCanvasView`** | "Canvas" is correct term for node editor |
| `WorkflowNodeView` | **Keep as `WorkflowNodeView`** | Clear component hierarchy |
| `PortView` | **`WorkflowPortView`** | Add prefix for clarity (port is ambiguous) |
| `EdgeView` | **`WorkflowEdgeView`** | Consistent with WorkflowNodeView, WorkflowPortView |
| `SimpleWorkflowView` | **Clarify or Remove** | Purpose unclear - what's "simple" about it? |

**Component Hierarchy:**
```
WorkflowEditor (container)
├── WorkflowCanvasView (canvas with zoom/pan)
│   ├── WorkflowNodeView (individual nodes)
│   │   └── WorkflowPortView (input/output ports)
│   └── WorkflowEdgeView (connections between nodes)
└── WorkflowOutputLog (execution results)
```

---

### Sidebar Components

**Apple Convention:** Sidebar is Apple's official term (not "Navigator", "Organizer").

| Current Name | Correct Name | Status |
|--------------|--------------|--------|
| `SidebarView` | **Keep as `SidebarView`** | ✅ Correct |
| `SidebarItemRow` | **Keep as `SidebarItemRow`** | ✅ Correct |
| `SidebarItemContextMenu` | **Keep as `SidebarItemContextMenu`** | ✅ Correct |
| `SidebarSectionHeader` | **Keep as `SidebarSectionHeader`** | ✅ Correct |

**Why this is already correct:**
- ✅ Apple uses "Sidebar" in NavigationSplitView API
- ✅ Consistent with Xcode, Finder terminology
- ✅ Clear component relationships

---

## Future Views (Not Yet Implemented)

Based on Apple conventions and planned features:

| Feature | View Name | Inspector Name | Notes |
|---------|-----------|----------------|-------|
| **MCP Tools** | `MCPToolsView` | `MCPToolInspector` | Follows workflow pattern |
| **Agents** | `AgentsView` | `AIAgentInspector` | AI prefix for consistency with other AI features |
| **CLI/Terminal** | `TerminalView` | N/A (modal) | Sheet-based, not in main window |
| **Export** | `ExportView` | N/A (sheet) | Modal sheet with steps |
| **Comparison** | `ComparisonView` | N/A (overlay) | HSplitView of two EditorViews |
| **Web Preview** | `WebPreviewView` | N/A (integrated) | Part of EditorView for web content |
| **LangGraph Runner** | *(use WorkflowEditor)* | `WorkflowInspector` | Already implemented in WorkflowOutputLog |

---

## Enum Naming

**Apple Convention:** Enums should describe what they represent, not where they're used.

| Current Name | Correct Name | Rationale |
|--------------|--------------|-----------|
| `AppViewMode` | **Keep as `AppViewMode`** | Describes app-level view modes |
| `SidebarMode` | **Keep as `SidebarMode`** | Describes sidebar states |
| `BrowserViewMode` | **`LibraryLayout`** | Describes layout options |
| `PreviewMode` | **Keep as `PreviewMode`** | Describes preview behavior |

---

## Component Suffixes

**When to use "View" suffix:**

✅ **Use "View" when:**
- It's a top-level, standalone view (`LibraryView`, `ChatView`, `SearchView`)
- Component could be confused with a model (`DocumentView` vs `Document`)
- Following Apple's naming (e.g., `ContentUnavailableView`)

❌ **Omit "View" when:**
- Context makes it obvious (`DocumentInspector` - clearly a view)
- Part of a clear hierarchy (`WorkflowNode` inside `WorkflowCanvasView`)
- Using Apple's standard terms (`Toolbar`, `Menu`, `Button` - never `ToolbarView`)

**Examples:**
```swift
// ✅ Good - top-level views
struct LibraryView: View
struct ChatView: View
struct WorkflowView: View

// ✅ Good - inspectors (Apple pattern from Xcode)
struct DocumentInspector: View
struct ChatInspector: View
struct WorkflowInspector: View

// ✅ Good - components with clear context
struct WorkflowNode: View  // Inside WorkflowCanvasView
struct DocumentThumbnail: View  // Inside LibraryView
struct MessageBubble: View  // Inside ChatView

// ❌ Bad - unnecessary suffix
struct DocumentInspectorView: View  // Redundant "View"
struct WorkflowNodeView: View  // Keep for now, but could drop
```

---

## Service Naming

**Apple Convention:** Services end in "Service" or use domain-specific terms.

| Pattern | Example | When to Use |
|---------|---------|-------------|
| `{Domain}Service` | `DocumentService`, `ChatService` | API/business logic |
| `{Domain}Store` | `DocumentStore`, `WorkflowStore` | State management (@ObservableObject) |
| `{Domain}Manager` | `ClipboardManager`, `ImportManager` | System-level coordination |

---

## File Organization

**Final structure after renaming:**

```
Views/
├── ContentView.swift
├── Library/
│   ├── LibraryView.swift (was BrowserView)
│   └── Layouts/
│       ├── IconsLayoutView.swift
│       ├── ListLayoutView.swift
│       ├── TableLayoutView.swift
│       └── MapLayoutView.swift
├── Search/
│   └── SearchView.swift
├── Chat/
│   └── ChatView.swift
├── Workflow/
│   ├── WorkflowView.swift
│   ├── WorkflowCanvasView.swift
│   ├── WorkflowNodeView.swift → WorkflowNode.swift
│   ├── WorkflowPortView.swift → WorkflowPort.swift
│   └── WorkflowEdgeView.swift → WorkflowEdge.swift
├── Editor/
│   └── EditorView.swift
├── Sidebar/
│   └── [existing - already correct]
├── Inspector/
│   ├── InspectorView.swift (container)
│   ├── DocumentInspector.swift (new)
│   ├── ChatInspector.swift (was ChatInspectorView)
│   └── WorkflowInspector.swift (was WorkflowInspectorView)
└── AIModels/
    ├── AIModelCatalog.swift (was ModelBrowserView)
    └── ModelSelectionView.swift (was ModelBrowserContent)
```

---

## Migration Checklist

### Phase 1: Inspectors (Low Risk)
- [ ] Rename `ChatInspectorView` → `ChatInspector`
- [ ] Rename `WorkflowInspectorView` → `WorkflowInspector`
- [ ] Create `DocumentInspector` (extract from InspectorView)
- [ ] Update `InspectorView` to switch between inspectors
- [ ] Update all imports

### Phase 2: Library/Browser (Medium Risk)
- [ ] Rename `BrowserView` → `LibraryView`
- [ ] Rename `BrowserViewMode` → `LibraryLayout`
- [ ] Update ContentView mode switching
- [ ] Update all references in ContentView, Sidebar
- [ ] Test all 4 layout modes

### Phase 3: AI Models (Low Risk)
- [ ] Rename `ModelBrowserView` → `AIModelCatalog`
- [ ] Rename `ModelBrowserContent` → `ModelSelectionView`
- [ ] Rename `ProviderModelBrowserSheet` → `AddModelsSheet`
- [ ] Update imports in Settings/Providers

### Phase 4: Workflow Components (Low Risk)
- [ ] Rename `PortView` → `WorkflowPortView`
- [ ] Rename `EdgeView` → `WorkflowEdgeView`
- [ ] Consider dropping "View" suffix: `WorkflowNode`, `WorkflowPort`, `WorkflowEdge`
- [ ] Clarify or remove `SimpleWorkflowView`

---

## Validation

After renaming, verify:
1. ✅ Build succeeds with no errors
2. ✅ All view modes switch correctly
3. ✅ Inspectors show correct content per mode
4. ✅ SwiftLint passes
5. ✅ No broken references in Storyboards/XIBs (N/A for pure SwiftUI)
6. ✅ Git history preserved (use `git mv` for renames)

---

## References

- [WWDC23: Inspectors in SwiftUI](https://developer.apple.com/videos/play/wwdc2023/10161/)
- [Apple Human Interface Guidelines: Panels](https://developer.apple.com/design/human-interface-guidelines/panels)
- [Swift API Design Guidelines](https://www.swift.org/documentation/api-design-guidelines/)
- [Apple Food Truck Sample Code](https://github.com/apple/sample-food-truck)
- Xcode Inspector Panel naming (File Inspector, Quick Help Inspector, Attributes Inspector)

---

**Status:** Ready for Implementation
**Next Step:** Begin Phase 1 (Inspector renaming)
