# Menu Bar Reorganization Plan

**Date**: 2025-12-31
**Status**: Planning
**Issue**: View menu commands are inline and inconsistent with File/Edit menu patterns

---

## Problem Statement

The menu bar implementation has an architectural inconsistency:

### Current State

**File Menu** (✅ Good):
```swift
CommandGroup(replacing: .newItem) {
    FocusedNewFolderButton()      // ← Extracted component
    FocusedImportFilesButton()    // ← Uses @FocusedValue
}
```

**Edit Menu** (✅ Good):
```swift
CommandGroup(after: .pasteboard) {
    FocusedRenameButton()         // ← Extracted component
    FocusedDeleteButton()         // ← Uses @FocusedValue
}
```

**View Menu** (❌ Bad):
```swift
CommandGroup(after: .toolbar) {
    Section("Sidebar") {
        Button { viewSettings.sidebarMode = .navigate } label: { ... }  // ← 150+ lines
        Button { viewSettings.sidebarMode = .search } label: { ... }     // ← of inline
        Button { viewSettings.sidebarMode = .chat } label: { ... }       // ← button code
        // ... 9 more buttons, all inline
    }
}
```

### Issues

1. **Inconsistent patterns**: File/Edit use extracted components, View uses inline code
2. **Code bloat**: 150+ lines of repetitive button code in `FicheroApp.swift`
3. **Not focus-aware**: Direct `viewSettings` access bypasses focus system
4. **Hard to maintain**: Inline code scattered across .commands block
5. **Not reusable**: Can't use these buttons elsewhere (toolbars, context menus)
6. **Violates DRY**: 12 nearly-identical button definitions

---

## Solution Architecture

### Pattern: Extract Menu Commands to Components

Following the established pattern from `FocusedCommandButtons.swift`:

```
Views/Menu/
├── FocusedCommandButtons.swift       # Existing: File/Edit commands
├── ImagePreviewMenuCommands.swift    # Existing: Image preview section
└── ViewMenuCommands.swift            # NEW: View menu sections
```

### Design Decision: @FocusedBinding vs Direct Access

**Two approaches:**

#### Option 1: Use @FocusedBinding (More Proper)
```swift
// ViewMenuCommands.swift
struct SidebarModeCommands: View {
    @FocusedBinding(\.sidebarMode) var sidebarMode

    var body: some View {
        Section("Sidebar") {
            Button { sidebarMode = .navigate } label: { ... }
            Button { sidebarMode = .search } label: { ... }
        }
    }
}

// ContentView.swift
.focusedSceneValue(\.sidebarMode, $viewSettings.sidebarMode)
```

**Pros**: Truly focus-aware, follows @FocusedValue pattern
**Cons**: Requires macOS 14+ (we're targeting macOS 13+)

#### Option 2: Use @AppStorage (Simpler, Backwards Compatible)
```swift
struct SidebarModeCommands: View {
    @AppStorage("sidebar.mode") private var sidebarMode: SidebarMode = .navigate

    var body: some View {
        Section("Sidebar") {
            Button { sidebarMode = .navigate } label: { ... }
        }
    }
}
```

**Pros**: Works on all macOS versions, persists user preference
**Cons**: Not focus-aware, but acceptable for app-scoped settings

#### Option 3: Hybrid - @EnvironmentObject (Current Pattern)

Since `viewSettings` is already an `@EnvironmentObject` and these are **app-scoped settings** (not document-scoped), we can extract the components while keeping the same data flow:

```swift
struct ViewMenuCommands: View {
    @EnvironmentObject var viewSettings: ViewSettings

    var body: some View {
        SidebarModeSection()
        Divider()
        LibraryLayoutSection()
        Divider()
        PreviewModeSection()
        Divider()
        QuickLookButton()
        Divider()
        InspectorButton()
    }
}
```

**Pros**:
- No architectural changes needed
- Backwards compatible
- Consistent with existing ImagePreviewMenuCommands pattern
- Appropriate for app-wide settings (not document-specific)

**Cons**: Not focus-aware (but these are app settings, not document actions)

**RECOMMENDED: Option 3** - These are app preferences, not document operations.

---

## Implementation Plan

### Phase 1: Create ViewMenuCommands.swift

Extract all View menu sections to `Views/Menu/ViewMenuCommands.swift`:

1. **SidebarModeSection** - 5 buttons for sidebar modes
2. **LibraryLayoutSection** - 4 buttons for view layouts
3. **PreviewModeSection** - 3 buttons for preview modes
4. **QuickLookButton** - Single Quick Look toggle
5. **InspectorButton** - Show/Hide Inspector toggle

Each section will be a separate struct for clarity.

### Phase 2: Update FicheroApp.swift

Replace inline View menu code with:

```swift
CommandGroup(after: .toolbar) {
    ViewMenuCommands()
}
```

Reduces FicheroApp.swift by ~150 lines.

### Phase 3: Consider Future Enhancements

Once extracted, these components can be:
- Reused in context menus
- Reused in toolbar overflow menus
- Tested independently
- Modified without touching FicheroApp.swift

---

## File Organization

### Before
```
Views/Menu/
├── FocusedCommandButtons.swift       # File/Edit menu commands
└── ImagePreviewMenuCommands.swift    # Image preview commands

FicheroApp.swift
└── .commands { ... 283 lines ... }   # ← 150 lines of View menu code
```

### After
```
Views/Menu/
├── FocusedCommandButtons.swift       # File/Edit menu commands
├── ImagePreviewMenuCommands.swift    # Image preview commands
└── ViewMenuCommands.swift            # NEW: View menu commands

FicheroApp.swift
└── .commands { ... ~130 lines ... }  # ← Simplified, consistent
```

---

## Detailed Component Design

### ViewMenuCommands.swift Structure

```swift
import SwiftUI

/// All View menu commands organized into sections
struct ViewMenuCommands: View {
    @EnvironmentObject var viewSettings: ViewSettings

    var body: some View {
        SidebarModeSection(viewSettings: viewSettings)
        Divider()
        LibraryLayoutSection(viewSettings: viewSettings)
        Divider()
        PreviewModeSection(viewSettings: viewSettings)
        Divider()
        QuickLookButton(viewSettings: viewSettings)
        Divider()
        InspectorButton(viewSettings: viewSettings)
    }
}

// MARK: - Sidebar Mode Section

struct SidebarModeSection: View {
    @ObservedObject var viewSettings: ViewSettings

    var body: some View {
        Section("Sidebar") {
            SidebarModeButton(mode: .navigate, icon: "list.bullet.indent",
                            shortcut: "1", current: viewSettings.sidebarMode,
                            onSelect: { viewSettings.sidebarMode = $0 })

            SidebarModeButton(mode: .search, icon: "magnifyingglass",
                            shortcut: "2", current: viewSettings.sidebarMode,
                            onSelect: { viewSettings.sidebarMode = $0 })
            // ... etc
        }
    }
}

// MARK: - Reusable Button Component

struct SidebarModeButton: View {
    let mode: SidebarMode
    let icon: String
    let shortcut: String
    let current: SidebarMode
    let onSelect: (SidebarMode) -> Void

    var body: some View {
        Button {
            onSelect(mode)
        } label: {
            HStack {
                if current == mode {
                    Image(systemName: "checkmark")
                }
                Label(mode.rawValue.capitalized, systemImage: icon)
            }
        }
        .keyboardShortcut(
            KeyEquivalent(Character(shortcut)),
            modifiers: [.control, .command]
        )
    }
}
```

This pattern eliminates repetition and makes each button definition 1-2 lines instead of 10.

---

## Code Quality Benefits

1. **Reduced line count**: FicheroApp.swift: 283 → ~130 lines
2. **Consistent pattern**: All menus use extracted components
3. **DRY principle**: Reusable button components eliminate duplication
4. **Discoverable**: All View menu code in `Views/Menu/ViewMenuCommands.swift`
5. **Testable**: Can test each section independently
6. **Maintainable**: Adding new view modes is 1-2 lines, not 10

---

## Migration Strategy

### Step 1: Create ViewMenuCommands.swift
- Extract all View menu sections
- Create reusable button components
- Keep exact same behavior (no functional changes)

### Step 2: Update FicheroApp.swift
- Replace inline View menu code with `ViewMenuCommands()`
- Verify keyboard shortcuts still work
- Verify checkmarks show correctly

### Step 3: Verification
- Run SwiftLint on new file
- Test all View menu items
- Test all keyboard shortcuts
- Verify menu state updates correctly

---

## SwiftLint Compliance

Expected warnings to address:
- File length (FicheroApp.swift should drop below warning threshold)
- Function body length (no more large .commands blocks)

New file should pass with 0 warnings.

---

## Future Enhancements (Out of Scope)

Once extracted, we could:
1. Add these commands to context menus (right-click on sidebar)
2. Add toolbar overflow menu with view options
3. Create a View Options popover (like Finder)
4. Add keyboard shortcut customization

But for now, focus on **extraction and consistency**.

---

## Success Criteria

- ✅ All View menu commands extracted to `ViewMenuCommands.swift`
- ✅ FicheroApp.swift reduced by ~150 lines
- ✅ Consistent pattern across all menus (File/Edit/View)
- ✅ All keyboard shortcuts working
- ✅ All checkmarks showing correctly
- ✅ SwiftLint compliant (0 warnings)
- ✅ No functional changes (exact same behavior)

---

## References

- Current implementation: `FicheroApp.swift` lines 101-256
- Pattern to follow: `FocusedCommandButtons.swift`
- Similar extraction: `ImagePreviewMenuCommands.swift`
- SwiftUI Commands documentation: [Menus and Commands](https://developer.apple.com/documentation/swiftui/menus-and-commands)

---

**Next Steps**: Begin implementation with ViewMenuCommands.swift creation
