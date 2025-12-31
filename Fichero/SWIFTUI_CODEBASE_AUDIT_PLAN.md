# SwiftUI Codebase Audit Plan

**Date**: 2025-12-31
**Objective**: Systematic review of entire codebase for SwiftUI best practices, modern patterns, and proper organization
**Scope**: 67 files across App, Views, Models, and Services layers

---

## Audit Criteria

### 1. SwiftUI Best Practices

**View Architecture**:
- [ ] Pure SwiftUI (no AppKit unless absolutely necessary)
- [ ] Proper state management (@State, @Binding, @StateObject, @ObservedObject, @EnvironmentObject)
- [ ] ViewBuilder used for computed views
- [ ] @MainActor used for UI updates (not DispatchQueue.main)
- [ ] Small, focused views (< 300 lines recommended)
- [ ] Proper use of Preview providers

**State Management**:
- [ ] @State for view-owned state
- [ ] @Binding for parent-child communication
- [ ] @StateObject for view-owned ObservableObject
- [ ] @ObservedObject for passed-in ObservableObject
- [ ] @EnvironmentObject for app-wide state
- [ ] @FocusedValue for menu commands (not NotificationCenter)

**Navigation**:
- [ ] NavigationSplitView for multi-column layouts (not deprecated NavigationView)
- [ ] Proper column visibility management
- [ ] Correct use of selection bindings

**Materials & Colors**:
- [ ] .ultraThinMaterial for translucent backgrounds
- [ ] Semantic colors (.secondary, .accent) not fixed colors
- [ ] Adapts to light/dark mode automatically

### 2. Code Organization

**File Structure**:
- [ ] Menus in Views/Menu/ (not mixed with content views)
- [ ] Toolbars in Views/Toolbars/ (not inline in views)
- [ ] Components properly separated
- [ ] Models in Models/ layer
- [ ] Services in Services/ layer
- [ ] Clear separation of concerns

**File Size**:
- [ ] Files < 400 lines (split if larger)
- [ ] Functions < 40 lines
- [ ] Clear logical sections with MARK comments

**Organization Within Files**:
```swift
// 1. Imports
import SwiftUI

// 2. Main struct/class
struct MyView: View {
    // 3. MARK: - Properties
    // Environment
    @EnvironmentObject var settings: ViewSettings

    // State
    @State private var selection: String?

    // Constants
    private let columns = 3

    // 4. MARK: - Initialization
    init() { }

    // 5. MARK: - Body
    var body: some View { }

    // 6. MARK: - Subviews
    private var toolbar: some View { }

    // 7. MARK: - Actions
    private func handleAction() { }

    // 8. MARK: - Helpers
    private func computeValue() -> Int { }
}

// 9. MARK: - Preview
#Preview { }
```

### 3. Modern Apple Patterns

**macOS 13+ Features**:
- [ ] Uses NavigationSplitView (not NavigationView)
- [ ] Uses .searchable for search fields
- [ ] Uses .toolbar for window toolbars
- [ ] Uses .commands for menu bar

**macOS 14+ Features** (if available):
- [ ] @Observable for simple observable objects
- [ ] @Bindable for binding to observable objects
- [ ] @FocusedBinding for menu state

**Async/Await**:
- [ ] Task { } for async work in views
- [ ] async functions properly marked
- [ ] Cancellation handling with Task.isCancelled
- [ ] MainActor for UI updates

**OSLog**:
- [ ] Uses Logger (not NSLog or print)
- [ ] Proper subsystem and category
- [ ] Appropriate log levels (debug, info, error)

### 4. AppKit Usage Audit

**Necessary AppKit**:
- ✅ NSSavePanel / NSOpenPanel (no SwiftUI equivalent)
- ✅ NSImage for image manipulation
- ✅ NSPasteboard for clipboard (no SwiftUI equivalent)
- ✅ Security-scoped bookmarks (macOS sandbox feature)

**Unnecessary AppKit** (Check for):
- ❌ NSView wrapping (use SwiftUI views)
- ❌ NSTextField (use TextField)
- ❌ NSButton (use Button)
- ❌ NSColor (use Color)
- ❌ NSFont (use Font)
- ❌ NotificationCenter for menu commands (use @FocusedValue)

### 5. Constants & Configuration

**Constants Pattern**:
```swift
// Good - Centralized constants
enum SidebarConstants {
    static let minWidth: CGFloat = 200
    static let maxWidth: CGFloat = 300
    static let itemHeight: CGFloat = 28
}

// Bad - Magic numbers scattered in code
.frame(minWidth: 200, maxWidth: 300)
.frame(height: 28)
```

**Check for**:
- [ ] Constants grouped in enums or structs
- [ ] No magic numbers in view code
- [ ] Consistent spacing/sizing values
- [ ] Reusable values extracted

### 6. Comments & Documentation

**Required Comments**:
```swift
/// Brief description of what this view does
///
/// Longer explanation if needed. Include:
/// - What it displays
/// - Key interactions
/// - Important state dependencies
struct MyView: View {
    // MARK: - Properties

    /// The currently selected item ID
    @State private var selection: String?

    // MARK: - Body

    var body: some View {
        // Complex logic deserves inline comments
    }
}
```

**Check for**:
- [ ] File-level doc comments on public types
- [ ] MARK comments for logical sections
- [ ] Complex logic explained with inline comments
- [ ] TODO/FIXME addressed or removed
- [ ] No commented-out code

### 7. Error Handling

**Proper Error Handling**:
```swift
Task {
    do {
        let data = try await apiClient.fetch()
        // Handle success
    } catch {
        // Log error
        Logger.error("Failed to fetch: \(error)")
        // Update UI state
        await MainActor.run {
            errorMessage = error.localizedDescription
        }
    }
}
```

**Check for**:
- [ ] All async operations have error handling
- [ ] Errors logged appropriately
- [ ] User-facing error messages
- [ ] No force-unwraps (!)
- [ ] Optional handling with proper defaults

---

## Audit Checklist by Layer

### Layer 1: App (3 files)

**FicheroApp.swift**:
- [ ] Proper Scene structure
- [ ] .commands properly organized
- [ ] No inline menu code (use extracted components)
- [ ] Environment objects properly injected
- [ ] Window management correct

**AppState.swift**:
- [ ] ObservableObject pattern correct
- [ ] @Published properties appropriate
- [ ] No business logic (belongs in services)
- [ ] Proper initialization

**ViewSettings.swift**:
- [ ] ObservableObject pattern correct
- [ ] @Published properties for UI state
- [ ] Could use @AppStorage for persistence?
- [ ] No business logic

### Layer 2: Views/Menu (3 files)

**All menu files**:
- [ ] Proper @FocusedValue or @EnvironmentObject usage
- [ ] No NotificationCenter
- [ ] Keyboard shortcuts on buttons
- [ ] Proper disabled states
- [ ] Checkmarks for toggle items
- [ ] No inline code in FicheroApp.swift

### Layer 3: Views/Toolbars (6 files)

**All toolbar files**:
- [ ] Uses .ultraThinMaterial
- [ ] Consistent padding (12h, 6v)
- [ ] @Binding for parent communication
- [ ] Actions via closures
- [ ] No nested toolbars
- [ ] SwiftLint compliant

### Layer 4: Views/Sidebar (8 files)

**Check for**:
- [ ] Proper List usage
- [ ] Selection binding correct
- [ ] Drag & drop SwiftUI-native
- [ ] Context menus SwiftUI-native
- [ ] No NSOutlineView
- [ ] Hierarchical data properly handled
- [ ] Constants extracted to SidebarConstants.swift
- [ ] State management clear

### Layer 5: Views/Library (3 files)

**LibraryView.swift**:
- [ ] File size (currently large, may need splitting)
- [ ] Multiple view modes handled correctly
- [ ] Toolbar integrated
- [ ] No AppKit
- [ ] Proper Grid/List/Table patterns

**EditorView.swift**:
- [ ] Proper text editing
- [ ] No NSTextView unless necessary
- [ ] Focus management correct

**DocumentInspector.swift**:
- [ ] Mini toolbar usage
- [ ] Form layout proper
- [ ] Binding management correct

### Layer 6: Views/Chat (2 files)

**ChatView.swift**:
- [ ] Toolbar extracted (done)
- [ ] ScrollView + messages pattern correct
- [ ] @MainActor for UI updates
- [ ] Error handling proper
- [ ] File size acceptable

**ChatInspector.swift**:
- [ ] Mini toolbar usage
- [ ] Binding management correct
- [ ] Document scope handling

### Layer 7: Views/Search (1 file)

**SearchView.swift**:
- [ ] Toolbar extracted (done)
- [ ] HSplitView usage correct
- [ ] Search state management
- [ ] Results display proper

### Layer 8: Views/Workflow (10 files)

**Check all**:
- [ ] Canvas view SwiftUI-native (no AppKit drawing)
- [ ] Node/edge rendering proper
- [ ] Drag & drop SwiftUI
- [ ] Toolbar extracted (done)
- [ ] Inspector proper
- [ ] State management clear
- [ ] File sizes acceptable

### Layer 9: Views/Components (4 files)

**All components**:
- [ ] Reusable and focused
- [ ] Proper @ViewBuilder usage
- [ ] No AppKit unless necessary
- [ ] Clear responsibility
- [ ] Well documented

### Layer 10: Views/AIProviders (6 files)

**Check all**:
- [ ] Form layouts proper
- [ ] Sheet presentation correct
- [ ] State management clear
- [ ] Error handling proper

### Layer 11: Views/Settings (1 file)

**SettingsView.swift**:
- [ ] Settings Scene pattern correct
- [ ] TabView usage proper
- [ ] @AppStorage for persistence?

### Layer 12: Models (17 files)

**All models**:
- [ ] Struct for value types
- [ ] Class + ObservableObject for reference types
- [ ] Codable implementations correct
- [ ] No business logic (belongs in services)
- [ ] Clear data modeling
- [ ] Proper Identifiable conformance

### Layer 13: Services (13 files)

**All services**:
- [ ] Clear service responsibility
- [ ] Async/await patterns
- [ ] Error handling proper
- [ ] No UI code
- [ ] Testable architecture
- [ ] APIClient integration correct

---

## Audit Process

### Phase 1: Planning & Setup
1. ✅ Create audit plan (this document)
2. ✅ Create todo list
3. [ ] Set up audit tracking spreadsheet

### Phase 2: Systematic Review (By Layer)
1. [ ] Review App layer (3 files)
2. [ ] Review Views/Menu (3 files)
3. [ ] Review Views/Toolbars (6 files)
4. [ ] Review Views/Sidebar (8 files)
5. [ ] Review Views/Library (3 files)
6. [ ] Review Views/Chat (2 files)
7. [ ] Review Views/Search (1 file)
8. [ ] Review Views/Workflow (10 files)
9. [ ] Review Views/Components (4 files)
10. [ ] Review Views/AIProviders (6 files)
11. [ ] Review Views/Settings (1 file)
12. [ ] Review Models (17 files)
13. [ ] Review Services (13 files)

### Phase 3: Implementation
For each file with issues:
1. [ ] Document issues found
2. [ ] Research Apple documentation (sosumi) if needed
3. [ ] Create fix plan
4. [ ] Implement fixes
5. [ ] Test with Xcode build
6. [ ] Run SwiftLint
7. [ ] Mark as complete

### Phase 4: Verification
1. [ ] Full Xcode build succeeds
2. [ ] All SwiftLint warnings addressed
3. [ ] All TODOs resolved or documented
4. [ ] Manual testing of major features
5. [ ] Create final audit report

---

## Issue Tracking Template

For each file audited, track:

```markdown
### FileName.swift

**Issues Found**:
1. [ ] Issue description
   - Location: Line XX
   - Severity: Critical / Warning / Enhancement
   - Fix: Description of what needs to change

**Fixes Applied**:
1. [x] Issue description
   - Fix: What was changed
   - Test: How it was verified

**Notes**:
- Any additional observations
```

---

## Sosumi Documentation Queries

When encountering patterns to verify, search:

1. **Navigation**: "NavigationSplitView macOS SwiftUI"
2. **State Management**: "SwiftUI state management best practices"
3. **Toolbars**: "SwiftUI toolbar macOS"
4. **Menu Commands**: "SwiftUI commands FocusedValue"
5. **Drag & Drop**: "SwiftUI drag drop onDrag onDrop"
6. **Materials**: "SwiftUI materials ultraThinMaterial"
7. **List**: "SwiftUI List selection macOS"
8. **Forms**: "SwiftUI Form macOS"

---

## Success Criteria

- [ ] 100% pure SwiftUI (AppKit only where necessary)
- [ ] All files follow organization standards
- [ ] All files < 400 lines (split if needed)
- [ ] All files have proper MARK sections
- [ ] All constants extracted
- [ ] All TODOs addressed
- [ ] SwiftLint 0 warnings
- [ ] Xcode builds successfully
- [ ] Modern Apple patterns used throughout
- [ ] Proper documentation/comments

---

## Timeline

**Estimated effort**: 67 files to audit
- Phase 1 (Planning): Complete
- Phase 2 (Review): ~4-6 hours
- Phase 3 (Implementation): ~6-8 hours
- Phase 4 (Verification): ~1-2 hours

**Total**: ~11-16 hours of focused work

---

## Output Deliverables

1. **Audit reports** - One per layer with findings
2. **Fixed code** - All files meeting criteria
3. **Build verification** - Xcode build passing
4. **SwiftLint report** - 0 warnings
5. **Final summary** - Complete audit results

---

**Status**: Ready to begin systematic audit
**Next Step**: Start with App layer (FicheroApp.swift, AppState.swift, ViewSettings.swift)
