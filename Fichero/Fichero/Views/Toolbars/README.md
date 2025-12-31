# Toolbar Components Guide

This directory contains all toolbar components for the Fichero app, following a consistent pattern based on Apple's Liquid Glass principles.

## Architecture

```
┌────────────────────────────────────────────┐
│ Main Toolbar (ContentView)                │  ← Stable, never changes
│ [Inspector Toggle]                        │     Uses .toolbar {}
├────────────────────────────────────────────┤
│ ┌──────────────────────────────────────┐  │
│ │ View-Specific Mini Toolbar           │  │  ← Liquid Glass layer
│ │ [Controls for current view]          │  │     Uses .ultraThinMaterial
│ ├──────────────────────────────────────┤  │
│ │ Content Area                         │  │  ← Content layer
│ └──────────────────────────────────────┘  │
└────────────────────────────────────────────┘
```

## Design Principles

1. **Main Toolbar** (ContentView) - Stable controls that never change between views
   - Inspector toggle (⌘⌥I)
   - Uses SwiftUI's `.toolbar {}` modifier
   - System-standard appearance

2. **View-Specific Mini Toolbars** - Contextual controls for each view
   - View mode pickers, filters, actions specific to the view
   - Uses `.ultraThinMaterial` background
   - Consistent spacing: `padding(.horizontal, 12)` + `padding(.vertical, 6)`
   - Always positioned at top of view in VStack

3. **Liquid Glass Pattern** - Controls float above content with translucent material
   - Clear visual hierarchy
   - Content peeks through material
   - Maintains legibility with vibrancy

## File Organization

```
Views/Toolbars/
├── MiniToolbar.swift           # Reusable toolbar component + patterns
├── LibraryViewToolbar.swift    # Library: view mode + column config
├── WorkflowToolbar.swift       # Workflow: run controls + canvas controls
├── ChatViewToolbar.swift       # Chat: model picker + document scope
├── SearchViewToolbar.swift     # Search: results + save
└── README.md                   # This file
```

## Creating New Mini Toolbars

### Option 1: Use MiniToolbar Component (Recommended)

For simple toolbars, use the `MiniToolbar` component or view extension:

```swift
import SwiftUI

VStack(spacing: 0) {
    // Option A: Direct component
    MiniToolbar {
        Button("Filter") { }
        Spacer()
        Text("5 items").font(.caption)
    }

    // Your content
    ScrollView {
        // ...
    }
}

// Option B: View extension
ScrollView {
    // content
}
.miniToolbar {
    Button("Filter") { }
    Spacer()
    Text("5 items").font(.caption)
}
```

### Option 2: Use Pre-Built Patterns

For common toolbar patterns, use the included templates:

#### Action Toolbar
Simple toolbar with optional title and action button:

```swift
ActionMiniToolbar(
    title: "Inspector",
    actionTitle: "Add Field",
    actionIcon: "plus"
) {
    addField()
}
```

#### Status Toolbar
Toolbar with status text and optional actions:

```swift
StatusMiniToolbar(
    statusText: "\(items.count) items",
    isLoading: isSearching,
    actions: [
        .init(title: "Filter", icon: "line.3.horizontal.decrease.circle") {
            showFilters()
        },
        .init(title: "Sort", icon: "arrow.up.arrow.down") {
            showSortOptions()
        }
    ]
)
```

#### Picker Toolbar
Toolbar with segmented picker and optional actions:

```swift
PickerMiniToolbar(
    title: "View",
    selection: $viewMode,
    options: [
        (.grid, "Grid", "square.grid.2x2"),
        (.list, "List", "list.bullet"),
        (.detail, "Detail", "list.bullet.below.rectangle")
    ],
    actions: [
        .init(title: "Settings", icon: "gear") {
            showSettings()
        }
    ]
)
```

### Option 3: Create Custom Toolbar Component

For complex toolbars with unique requirements, create a dedicated component:

```swift
import SwiftUI

/// Toolbar for MyView with specific controls
struct MyViewToolbar: View {
    // State bindings
    @Binding var someState: Bool
    let someValue: String

    // Actions
    let onAction: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            // Left side controls
            Toggle("Option", isOn: $someState)

            Spacer()

            // Right side controls
            Text(someValue)
                .font(.caption)
                .foregroundStyle(.secondary)

            Button(action: onAction) {
                Label("Action", systemImage: "star")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.ultraThinMaterial)
    }
}

// Usage in your view:
VStack(spacing: 0) {
    MyViewToolbar(
        someState: $myState,
        someValue: "Info",
        onAction: handleAction
    )

    // Content below
}
```

## Standard Styling

All mini toolbars follow these conventions:

### Spacing
- **HStack spacing**: `12` points between items
- **Horizontal padding**: `12` points
- **Vertical padding**: `6` points

### Material
- **Background**: `.ultraThinMaterial`
- Automatically adapts to light/dark mode
- Provides proper vibrancy for foreground content

### Colors
- Use semantic colors: `.secondary`, `.accent`, `.primary`
- Never use fixed colors (e.g., `Color.blue`)
- Let system handle appearance adaptation

### Typography
- **Status text**: `.font(.caption)` + `.foregroundStyle(.secondary)`
- **Labels**: Default font or explicit `.caption`/`.subheadline`
- **Emphasis**: Use `.bold()` or `.semibold()` sparingly

### Controls
- **Buttons**: `.buttonStyle(.bordered)` + `.controlSize(.small)`
- **Icons**: SF Symbols preferred (auto-scale, localize)
- **Pickers**: `.pickerStyle(.segmented)` for 2-4 options
- **Toggles**: `.toggleStyle(.button)` for toolbar toggles

## When to Add a Mini Toolbar

Add a mini toolbar when a view needs:

1. **Mode selection** (grid/list/table views)
2. **Filtering/sorting** controls
3. **Status information** (item counts, loading states)
4. **Quick actions** specific to the view
5. **View-specific settings** (column config, display options)

**Don't add a toolbar for:**
- Single-button actions (use main toolbar or contextual menu)
- Infrequently used settings (use dedicated settings view)
- Actions that apply to selected items (use context menu)

## Examples from Existing Toolbars

### LibraryViewToolbar
```swift
// View mode picker + column configuration
LibraryViewToolbar(
    viewMode: $viewMode,
    showColumnConfig: true,
    showName: $showName,
    // ... other column bindings
    onResetColumns: resetColumns
)
```

### WorkflowToolbar
```swift
// Canvas controls (left) + workflow controls (right)
WorkflowToolbar(
    isRunning: $isRunning,
    showOutputLog: $showOutputLog,
    canRun: !workflow.nodes.isEmpty,
    scale: $scale,
    snapToGrid: $snapToGrid,
    onRun: runWorkflow,
    onSave: saveWorkflow,
    onExport: exportWorkflow,
    onResetZoom: resetZoom
)
```

### ChatViewToolbar
```swift
// Document scope (left) + model picker + new chat (right)
ChatViewToolbar(
    selectedDocumentsCount: selectedDocuments.count,
    onClearDocuments: { selectedDocuments.removeAll() },
    providers: providers,
    selectedProvider: $selectedProvider,
    selectedModel: $selectedModel,
    onNewChat: startNewChat
)
```

## SwiftUI Best Practices

### State Management
```swift
// ✅ Parent owns state
@State private var viewMode: ViewMode = .grid

MyViewToolbar(viewMode: $viewMode)  // Pass binding

// ❌ Don't duplicate state in child
struct MyViewToolbar: View {
    @State private var viewMode: ViewMode = .grid  // Wrong!
}
```

### Bindings
```swift
// ✅ Accept bindings from parent
struct MyToolbar: View {
    @Binding var someValue: String
}

// ✅ Accept closures for actions
let onAction: () -> Void
```

### Composition
```swift
// ✅ Small, focused components
struct LibraryViewToolbar: View { }  // One responsibility

// ❌ Don't create monolithic toolbars
struct MegaToolbar: View {  // Does everything!
    // 500 lines of code
}
```

## Testing in Previews

Always include previews for your toolbars:

```swift
#Preview("My Toolbar") {
    VStack(spacing: 0) {
        MyViewToolbar(
            someValue: .constant("Test"),
            onAction: { print("Action") }
        )

        Text("Preview content")
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(.textBackgroundColor))
    }
    .frame(width: 600, height: 400)
}
```

## SwiftLint Compliance

All toolbar files must pass SwiftLint:

```bash
swiftlint lint Fichero/Fichero/Views/Toolbars/ --quiet
```

Common issues to avoid:
- File length > 400 lines → Split into multiple components
- Trailing whitespace → Clean up before committing
- Trailing commas in collections → Remove extra comma
- Multiple closures with trailing syntax → Use labeled parameters

## Accessibility

Toolbars automatically provide good accessibility:

- **Materials** adapt to system appearance and contrast settings
- **SF Symbols** scale with text size preferences
- **Semantic colors** respect high contrast mode
- **Button labels** provide VoiceOver hints

Always include `.help()` modifiers on icon-only buttons:

```swift
Button(action: save) {
    Image(systemName: "square.and.arrow.down")
}
.help("Save Workflow")  // Important for accessibility
```

## Migration Guide

### Moving from .toolbar {} to Mini Toolbar

**Before:**
```swift
var body: some View {
    ContentView()
        .toolbar {
            ToolbarItem {
                Button("Action") { }
            }
        }
}
```

**After:**
```swift
var body: some View {
    VStack(spacing: 0) {
        MiniToolbar {
            Button("Action") { }
        }
        ContentView()
    }
}
```

### Moving from Inline HStack to Component

**Before:**
```swift
var body: some View {
    VStack {
        HStack {
            Button("A") { }
            Spacer()
            Button("B") { }
        }
        .padding()
        .background(Color.gray.opacity(0.2))

        // content
    }
}
```

**After:**
```swift
var body: some View {
    VStack(spacing: 0) {
        MiniToolbar {
            Button("A") { }
            Spacer()
            Button("B") { }
        }

        // content
    }
}
```

## Resources

- [Apple HIG - Materials](https://developer.apple.com/design/human-interface-guidelines/materials)
- [SwiftUI Material Documentation](https://developer.apple.com/documentation/swiftui/material)
- [Liquid Glass Overview](https://developer.apple.com/documentation/technologyoverviews/liquid-glass)
- [Toolbar Content Builder](https://developer.apple.com/documentation/swiftui/toolbarcontentbuilder)
