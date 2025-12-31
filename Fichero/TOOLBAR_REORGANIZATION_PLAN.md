# Toolbar Reorganization Plan

## Current Problems

1. **Nested toolbars**: WorkflowCanvasView has a toolbar inside WorkflowEditor which also has a toolbar
2. **Scattered code**: Toolbars defined in 5+ different files
3. **Inconsistent patterns**: Some use `.toolbar {}`, some define `@ToolbarContentBuilder` vars
4. **View-dependent main toolbar**: ContentView's libraryToolbar changes based on view mode
5. **Poor discoverability**: Hard for open source contributors to find toolbar code

## Target Pattern (DEVONthink Model)

```
┌─────────────────────────────────────────────────────────┐
│ Main Window Toolbar (STABLE - never changes)           │
│ [Standard controls] [Inspector toggle]                 │
├─────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────┐ │
│ │ View-Specific Toolbar (small buttons)              │ │
│ │ [View mode] [Sort] [Filter] [Actions]             │ │
│ ├─────────────────────────────────────────────────────┤ │
│ │                                                     │ │
│ │          Content Area                              │ │
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Solution Architecture

### 1. Main Toolbar (Stable)
**Location**: `ContentView.swift`
**Never changes**, available across all views:
- Inspector toggle (⌘⌥I)
- Quick Look toggle (⌘Y)
- Standard window controls

### 2. View-Specific Toolbars (Small Button Bars)
Each major view gets its own small toolbar at the TOP of the view:

**LibraryView Toolbar**
- File: `Views/Toolbars/LibraryViewToolbar.swift`
- Controls: View mode picker (icons/list/table/map), sort, filter

**ChatView Toolbar**
- File: `Views/Toolbars/ChatViewToolbar.swift`
- Controls: New chat, model selector, clear chat

**SearchView Toolbar**
- File: `Views/Toolbars/SearchViewToolbar.swift`
- Controls: Search scope, filters, save search

**WorkflowEditor Toolbar**
- File: `Views/Toolbars/WorkflowToolbar.swift`
- Controls: Run, output log toggle, zoom, snap-to-grid
- **Remove** nested toolbar from WorkflowCanvasView

### 3. Sidebar Toolbar (Unchanged)
**Location**: `Views/Sidebar/SidebarViewExtensions.swift`
**Keep as-is**: Small buttons (New Folder, Import)

## File Organization

```
Fichero/Views/
├── Toolbars/                    # NEW directory
│   ├── LibraryViewToolbar.swift
│   ├── ChatViewToolbar.swift
│   ├── SearchViewToolbar.swift
│   └── WorkflowToolbar.swift
├── ContentView.swift            # Main stable toolbar only
├── Library/
│   └── LibraryView.swift        # Uses LibraryViewToolbar
├── Chat/
│   └── ChatView.swift           # Uses ChatViewToolbar
├── Search/
│   └── SearchView.swift         # Uses SearchViewToolbar
└── Workflow/
    ├── WorkflowEditor.swift     # Uses WorkflowToolbar
    └── WorkflowCanvasView.swift # NO toolbar
```

## Implementation Steps

1. ✅ Create `Views/Toolbars/` directory
2. ✅ Extract LibraryView toolbar → `LibraryViewToolbar.swift`
3. ✅ Extract WorkflowEditor toolbar → `WorkflowToolbar.swift`
4. ✅ **Remove** WorkflowCanvasView toolbar (merge into WorkflowToolbar)
5. ✅ Create ChatViewToolbar.swift
6. ✅ Create SearchViewToolbar.swift
7. ✅ Simplify ContentView main toolbar to stable controls (Inspector toggle only)
8. ✅ Update LibraryView to use LibraryViewToolbar component
9. ✅ Update WorkflowEditor to use WorkflowToolbar component
10. ✅ Run SwiftLint - all toolbar files pass ✓
11. ⚠️ Update Xcode project file (manual step - add new toolbar files)
12. ⚠️ Update ChatView and SearchView to use new toolbar components (optional enhancement)

## SwiftUI Best Practices

### ❌ OLD Pattern (Scattered, Nested)
```swift
// WorkflowEditor.swift
var body: some View {
    WorkflowCanvasView()
        .toolbar { workflowToolbar }  // Parent toolbar
}

// WorkflowCanvasView.swift
var body: some View {
    Canvas()
        .toolbar { canvasToolbar }  // NESTED toolbar - BAD!
}
```

### ✅ NEW Pattern (Consolidated, Top-of-View)
```swift
// WorkflowEditor.swift
var body: some View {
    VStack(spacing: 0) {
        WorkflowToolbar(...)  // Small button bar at top
        WorkflowCanvasView()  // No toolbar
    }
}

// WorkflowToolbar.swift (separate file)
struct WorkflowToolbar: View {
    var body: some View {
        HStack {
            // Small icon buttons
        }
        .padding(6)
        .background(.ultraThinMaterial)
    }
}
```

## SwiftLint Compliance

- Each toolbar in its own file (file length limit)
- Clear naming: `*Toolbar.swift`
- Logical grouping in `Toolbars/` directory
- No nested toolbars (complexity reduction)

## Benefits

1. **Consistent**: All view toolbars follow same pattern
2. **Discoverable**: Contributors know to look in `Views/Toolbars/`
3. **Maintainable**: Each toolbar isolated in its own file
4. **SwiftUI-native**: Follows Apple's recommended patterns
5. **Stable main toolbar**: Never jumps around between views
6. **Clean separation**: Main controls vs view-specific controls
