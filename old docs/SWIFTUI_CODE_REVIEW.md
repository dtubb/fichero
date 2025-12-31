# SwiftUI Code Review: Best Practices Analysis

**Date:** 2025-12-28
**Files Reviewed:** `FicheroApp.swift`, `ContentView.swift`, `SidebarView.swift`
**Status:** Comprehensive analysis with actionable recommendations

---

## Executive Summary

The codebase demonstrates **solid SwiftUI fundamentals** with proper use of `@StateObject`, `@Published`, and observable patterns. However, there are several **anti-patterns** and **opportunities for improvement** that would make the code more maintainable, performant, and idiomatic.

### Overall Assessment

**✅ Strengths:**
- Proper state management with `@StateObject` and `@ObservedObject`
- Good separation of concerns (models, services, views)
- Consistent use of `@MainActor` for thread safety
- Observable pattern with DocumentStore/Combine publishers

**⚠️ Areas for Improvement:**
- Overuse of NotificationCenter (anti-pattern in SwiftUI)
- Large view files (SidebarView.swift: 983 lines)
- Some computed properties recalculated too frequently
- Manual task cancelation not handled in `.task {}`
- Missing `@ViewBuilder` in some computed properties
- Inconsistent error handling patterns

---

## Critical Issues 🔴

### 1. NotificationCenter Anti-Pattern (FicheroApp.swift & SidebarView.swift)

**Problem:** Using NotificationCenter for app-wide communication is an **Objective-C pattern** that breaks SwiftUI's declarative data flow.

**FicheroApp.swift:20-24**
```swift
// ❌ Anti-pattern: Menu posts notification
Button("New Folder") {
    NotificationCenter.default.post(name: .createNewFolder, object: nil)
}

// ❌ Anti-pattern: View listens for notification
.onReceive(NotificationCenter.default.publisher(for: .createNewFolder)) { _ in
    handleCreateNewFolder()
}
```

**Why This Is Bad:**
- Breaks SwiftUI's reactive data flow
- Hard to debug (actions happen indirectly)
- Creates hidden dependencies
- Doesn't work with SwiftUI previews
- Violates single source of truth principle

**SwiftUI Solution:** Use `@FocusedValue` or `@Environment` for commands

**Recommended Fix:**
```swift
// Define focused value for selection
struct FocusedItemKey: FocusedValueKey {
    typealias Value = SidebarSelection
}

extension FocusedValues {
    var sidebarSelection: FocusedItemKey.Value? {
        get { self[FocusedItemKey.self] }
        set { self[FocusedItemKey.self] = newValue }
    }
}

// In SidebarView:
.focusedValue(\.sidebarSelection, SidebarSelection(
    selectedItem: selectedItem,
    createFolder: handleCreateNewFolder,
    renameItem: handleRenameSelectedItem,
    deleteItem: handleDeleteSelectedItem
))

// In FicheroApp menu:
Button("New Folder") {
    // Uses focused value - no notification needed!
}
.keyboardShortcut("n", modifiers: [.command])
```

**Impact:** High - affects app architecture and testability

---

### 2. Large View Files (SidebarView.swift: 983 lines)

**Problem:** SwiftUI views should be **small and focused**. Large views are hard to:
- Read and maintain
- Test
- Reuse
- Optimize (SwiftUI can't diff efficiently)

**Current Structure:**
```swift
SidebarView (983 lines)
  ├─ SectionHeader
  ├─ SidebarItemRow
  ├─ SidebarItemContextMenu
  ├─ RenameStateManager
  └─ DeleteStateManager
```

**Recommended Refactor:**
```
Views/Sidebar/
  ├─ SidebarView.swift           (< 200 lines - main structure)
  ├─ SidebarItemRow.swift        (row rendering + drag/drop)
  ├─ SidebarContextMenu.swift    (context menu logic)
  ├─ SidebarStateManagers.swift  (RenameStateManager, DeleteStateManager)
  └─ SidebarActions.swift        (create, rename, delete, move logic)
```

**Benefits:**
- Easier to test individual components
- Better SwiftUI diffing performance
- Clearer separation of concerns
- Easier to navigate codebase

---

### 3. Computed Properties Without Memoization (ContentView.swift)

**Problem:** Expensive computed properties recalculate on **every view update**.

**ContentView.swift:49-59**
```swift
// ❌ Recalculates entire tree on EVERY view update
private var selectedSidebarItem: SidebarItem? {
    guard let id = selectedSidebarItemId else { return nil }

    // Rebuilds entire hierarchy every time!
    let libraryItems = SidebarItemBuilder.buildLibraryHierarchy(from: documentStore.collections)
    let searchItems = SidebarItemBuilder.buildSearchHierarchy(from: savedSearchService.savedSearches)
    let chatItems = SidebarItemBuilder.buildChatHierarchy(from: conversationService.conversations)
    let workflowItems = SidebarItemBuilder.buildWorkflowHierarchy(from: workflowStore.workflows)

    let allItems = libraryItems + searchItems + chatItems + workflowItems
    return findItemById(id, in: allItems)
}
```

**Why This Is Bad:**
- Builds entire sidebar tree **on every view update**
- Triggers when *any* `@Published` property changes
- O(n) tree traversal on every render
- Wastes CPU cycles and battery

**Recommended Fix:** Use `@State` with `.onChange` to cache results

```swift
// ✅ Cache the built tree
@State private var sidebarItemsCache: [SidebarItem] = []

// ✅ Only rebuild when sources change
.onChange(of: documentStore.collections) { _, _ in
    rebuildSidebarCache()
}
.onChange(of: savedSearchService.savedSearches) { _, _ in
    rebuildSidebarCache()
}

private func rebuildSidebarCache() {
    let libraryItems = SidebarItemBuilder.buildLibraryHierarchy(from: documentStore.collections)
    let searchItems = SidebarItemBuilder.buildSearchHierarchy(from: savedSearchService.savedSearches)
    let chatItems = SidebarItemBuilder.buildChatHierarchy(from: conversationService.conversations)
    let workflowItems = SidebarItemBuilder.buildWorkflowHierarchy(from: workflowStore.workflows)
    sidebarItemsCache = libraryItems + searchItems + chatItems + workflowItems
}

// ✅ Fast lookup from cache
private var selectedSidebarItem: SidebarItem? {
    guard let id = selectedSidebarItemId else { return nil }
    return findItemById(id, in: sidebarItemsCache)
}
```

**Impact:** High - affects performance with large libraries

---

## Architectural Issues 🟡

### 4. Mixed State Management Patterns

**Problem:** Inconsistent use of `@StateObject` vs creating service instances directly.

**ContentView.swift:35**
```swift
// ✅ Good: Service as @StateObject
@StateObject private var documentService = DocumentService()

// But then in SidebarView:
private func handleImportFiles() {
    // ❌ Bad: Creates new instance instead of using @ObservedObject
    let documentService = DocumentService()
}
```

**Recommended Pattern:**
All services should be:
1. Created as `@StateObject` in app/scene root
2. Passed down via `.environmentObject()` or parameters
3. Never instantiated locally in views

**Fix:**
```swift
// ContentView creates once
@StateObject private var documentService = DocumentService()

// Sidebar receives reference
struct SidebarView: View {
    @EnvironmentObject var documentService: DocumentService

    private func handleImportFiles() {
        // Uses existing instance
        Task {
            _ = try await documentService.importFile(at: url, parentId: parentId)
        }
    }
}
```

---

### 5. Task Cancellation Not Handled

**Problem:** `.task {}` modifiers don't handle cancellation, leading to memory leaks and wasted work.

**ContentView.swift:263-295**
```swift
.task {
    await documentStore.loadCollections()
    await workflowStore.loadWorkflows()

    // ❌ If view disappears, these tasks keep running!
    // ❌ No cancellation check
}
```

**Recommended Fix:**
```swift
.task {
    // ✅ Check for cancellation
    guard !Task.isCancelled else { return }
    await documentStore.loadCollections()

    guard !Task.isCancelled else { return }
    await workflowStore.loadWorkflows()

    guard !Task.isCancelled else { return }
    try? await conversationService.loadConversations()
}
```

**Or better - use structured concurrency:**
```swift
.task {
    await withTaskGroup(of: Void.self) { group in
        group.addTask { await documentStore.loadCollections() }
        group.addTask { await workflowStore.loadWorkflows() }
        group.addTask { try? await conversationService.loadConversations() }
        group.addTask { try? await savedSearchService.loadSavedSearches() }
    }
    // Auto-cancels all tasks if view disappears
}
```

---

### 6. Excessive Use of NSLog

**Problem:** Using `NSLog` for every operation clutters logs and impacts performance.

**Examples throughout:**
```swift
NSLog("[SidebarView] ✅ Move successful - UI updates automatically via @Published")
NSLog("[DocumentStore] Loaded %d collections", collections.count)
NSLog("[ContentView] Files dropped: \(urls.map { $0.lastPathComponent })")
```

**Recommended:** Use OSLog with categories and levels

```swift
import OSLog

extension Logger {
    static let sidebar = Logger(subsystem: "ca.tubb.Fichero", category: "sidebar")
    static let documentStore = Logger(subsystem: "ca.tubb.Fichero", category: "documentStore")
}

// Usage:
Logger.sidebar.info("Move successful - UI updates automatically")
Logger.documentStore.debug("Loaded \(collections.count) collections")

// Benefits:
// - Structured logging
// - Filterable by category
// - Better performance
// - Survives app termination (can review in Console.app)
```

---

### 7. Missing @ViewBuilder Annotations

**Problem:** Computed properties that return views should use `@ViewBuilder` for flexibility.

**ContentView.swift:414**
```swift
// ❌ Missing @ViewBuilder
var contentView: some View {
    switch viewMode {
    case .library:
        BrowserView(...)
    case .search:
        SearchView(...)
    }
}
```

**Fix:**
```swift
// ✅ Allows multiple views, if-let, etc.
@ViewBuilder
var contentView: some View {
    switch viewMode {
    case .library:
        BrowserView(...)
    case .search:
        SearchView(...)
    }
}
```

---

## Best Practice Violations 🟠

### 8. Thread Safety Issues

**Problem:** Some operations not explicitly on `@MainActor` that manipulate UI state.

**ContentView.swift:90-99**
```swift
// ⚠️ Dispatching to main thread manually is a code smell in SwiftUI
private func handleDocumentChange(_ change: DocumentChange) {
    if !Thread.isMainThread {
        DispatchQueue.main.async {
            self.handleDocumentChangeOnMain(change)
        }
        return
    }
    handleDocumentChangeOnMain(change)
}
```

**Recommended Fix:**
```swift
// ✅ Mark function as @MainActor - Swift enforces thread safety
@MainActor
private func handleDocumentChange(_ change: DocumentChange) {
    // No manual dispatching needed
    switch change {
    case .collectionsUpdated:
        break
    }
}
```

---

### 9. Hardcoded Paths (ContentView.swift:190)

**Problem:** Hardcoded file paths make app not portable.

```swift
Text("cd /Users/dtubb/code/fichero_main/fichero")
    .font(.system(.body, design: .monospaced))
```

**Fix:**
```swift
// ✅ Use dynamic path based on app location
let projectPath = Bundle.main.bundleURL
    .deletingLastPathComponent()
    .deletingLastPathComponent()
    .path

Text("cd \(projectPath)")
```

---

### 10. Missing Accessibility Labels

**Problem:** Many buttons and controls missing accessibility labels.

**FicheroApp.swift:230**
```swift
// ❌ No accessibility label
Button(action: { handleCreateNewFolder() }) {
    Image(systemName: "folder.badge.plus")
}
```

**Fix:**
```swift
// ✅ Accessible
Button(action: { handleCreateNewFolder() }) {
    Image(systemName: "folder.badge.plus")
}
.help("New Folder")  // ✅ Tooltip
.accessibilityLabel("Create New Folder")  // ✅ VoiceOver
```

---

### 11. Inconsistent Error Handling

**Problem:** Some async calls use `try await`, others use `try?`, some ignore errors entirely.

**ContentView.swift:271-282**
```swift
// ✅ Logs error
try await conversationService.loadConversations()
} catch {
    NSLog("[ContentView] Failed to load conversations: %@", error.localizedDescription)
}

// ❌ Silently ignores error
try? await savedSearchService.loadSavedSearches()
```

**Recommended Pattern:**
```swift
// Define error handling strategy
@StateObject private var errorHandler = ErrorHandler()

// Use consistent pattern
Task {
    do {
        try await conversationService.loadConversations()
    } catch {
        errorHandler.handle(error, context: "Loading conversations")
    }
}

// Show errors to user
.alert("Error", isPresented: $errorHandler.showingError) {
    Button("OK") { errorHandler.dismiss() }
} message: {
    Text(errorHandler.currentError?.localizedDescription ?? "Unknown error")
}
```

---

## Performance Issues ⚡

### 12. Inefficient List Rendering (SidebarView.swift)

**Problem:** Nested `ForEach` with recursive children can cause performance issues.

**SidebarView.swift:592-606**
```swift
DisclosureGroup {
    ForEach(children) { child in
        SidebarItemRow(...)  // ← Can recursively render hundreds of items
    }
}
```

**Recommendation:** Use `List` with `OutlineGroup` for better performance

```swift
// ✅ SwiftUI optimizes OutlineGroup rendering
List(libraryItems, children: \.children) { item in
    SidebarItemRow(item: item, ...)
}
.listStyle(.sidebar)
```

---

### 13. Repeated API Calls on View Appearance

**Problem:** Multiple `.task {}` modifiers loading data independently.

**Better Pattern:**
```swift
// ✅ Single entry point for all data loading
.task {
    await loadAllData()
}

@MainActor
private func loadAllData() async {
    // Load in parallel where possible
    async let collections = documentStore.loadCollections()
    async let workflows = workflowStore.loadWorkflows()
    async let conversations = try? conversationService.loadConversations()
    async let searches = try? savedSearchService.loadSavedSearches()

    // Await all
    await collections
    await workflows
    await conversations
    await searches
}
```

---

## Code Organization 📁

### 14. File Structure Recommendations

**Current:**
```
Views/
  ├─ ContentView.swift (682 lines)
  └─ Sidebar/
      └─ SidebarView.swift (983 lines)
```

**Recommended:**
```
Views/
  ├─ ContentView.swift (< 300 lines)
  ├─ Root/
  │   ├─ AppRootView.swift (backend check, provider setup)
  │   └─ MainSplitView.swift (3-column navigation)
  └─ Sidebar/
      ├─ SidebarView.swift (< 200 lines - structure only)
      ├─ SidebarItemRow.swift (row rendering)
      ├─ SidebarSection.swift (section rendering)
      ├─ SidebarContextMenu.swift (context menus)
      ├─ SidebarStateManagers.swift (rename, delete state)
      └─ SidebarActions.swift (create, rename, delete, move)
```

---

## SwiftUI Best Practices Checklist

### ✅ Already Following

- [x] `@StateObject` for object creation
- [x] `@ObservedObject` for passed-in objects
- [x] `@Published` for reactive properties
- [x] `@MainActor` for UI-touching code
- [x] Combine publishers for events
- [x] `.environmentObject()` for app-wide state
- [x] `.task {}` for async work tied to view lifecycle
- [x] Proper use of `Binding<T>`

### ⚠️ Needs Improvement

- [ ] Remove NotificationCenter - use `@FocusedValue`
- [ ] Split large views into smaller components
- [ ] Add `@ViewBuilder` to computed view properties
- [ ] Handle Task cancellation in `.task {}`
- [ ] Cache expensive computed properties
- [ ] Use OSLog instead of NSLog
- [ ] Add accessibility labels to all controls
- [ ] Consistent error handling pattern
- [ ] Remove hardcoded paths
- [ ] Use `OutlineGroup` for hierarchical lists

---

## Priority Fixes

### P0 - Critical (Do First)

1. **Remove NotificationCenter pattern** (Replace with `@FocusedValue`)
   - Files: `FicheroApp.swift`, `SidebarView.swift`
   - Impact: Architecture, testability, SwiftUI idioms

2. **Cache computed sidebar items** (Performance issue)
   - File: `ContentView.swift:49-59`
   - Impact: Performance with large libraries

3. **Handle Task cancellation** (Memory leaks)
   - File: `ContentView.swift`, various `.task {}` blocks
   - Impact: Memory usage, battery life

### P1 - High Priority

4. **Refactor large view files**
   - File: `SidebarView.swift` (983 lines → multiple files)
   - Impact: Maintainability, testing

5. **Use OSLog instead of NSLog**
   - Files: All files with logging
   - Impact: Performance, debuggability

6. **Consistent service instantiation**
   - Issue: Mix of `@StateObject` and `let service = Service()`
   - Impact: Memory usage, state management

### P2 - Medium Priority

7. **Add `@ViewBuilder` annotations**
   - Files: `ContentView.swift`, view helpers
   - Impact: Code flexibility

8. **Add accessibility labels**
   - Files: All views with buttons/controls
   - Impact: Accessibility compliance

9. **Fix thread safety** (Remove manual `DispatchQueue.main`)
   - File: `ContentView.swift:90-99`
   - Impact: Code clarity, Swift 6 compatibility

### P3 - Nice to Have

10. **Use `OutlineGroup` for hierarchies**
11. **Remove hardcoded paths**
12. **Implement structured error handling**

---

## Implementation Plan

### Phase 1: Quick Wins (1-2 hours)
- Add `@ViewBuilder` to computed view properties
- Replace `NSLog` with `OSLog`
- Add Task cancellation checks
- Remove hardcoded paths

### Phase 2: Architectural Fixes (4-6 hours)
- Implement `@FocusedValue` for menu commands
- Remove all NotificationCenter usage
- Cache computed sidebar items
- Consistent service instantiation pattern

### Phase 3: Refactoring (1-2 days)
- Split `SidebarView.swift` into multiple files
- Split `FicheroApp.swift` provider settings into separate file
- Implement centralized error handling
- Add comprehensive accessibility labels

---

## Code Examples

### Example 1: FocusedValue for Menu Commands

**Before (Anti-pattern):**
```swift
// FicheroApp.swift
Button("New Folder") {
    NotificationCenter.default.post(name: .createNewFolder, object: nil)
}

// SidebarView.swift
.onReceive(NotificationCenter.default.publisher(for: .createNewFolder)) { _ in
    handleCreateNewFolder()
}
```

**After (SwiftUI Pattern):**
```swift
// Define focused value
struct SidebarActions {
    var createFolder: () -> Void
    var renameItem: () -> Void
    var deleteItem: () -> Void
}

struct SidebarActionsKey: FocusedValueKey {
    typealias Value = SidebarActions
}

extension FocusedValues {
    var sidebarActions: SidebarActionsKey.Value? {
        get { self[SidebarActionsKey.self] }
        set { self[SidebarActionsKey.self] = newValue }
    }
}

// SidebarView.swift
.focusedValue(\.sidebarActions, SidebarActions(
    createFolder: handleCreateNewFolder,
    renameItem: handleRenameSelectedItem,
    deleteItem: handleDeleteSelectedItem
))

// FicheroApp.swift
CommandGroup(replacing: .newItem) {
    Button("New Folder") {
        // SwiftUI automatically calls the focused view's action!
    }
    .keyboardShortcut("n", modifiers: [.command])
}
```

**Benefits:**
- ✅ Declarative - clear data flow
- ✅ Type-safe - compile-time checking
- ✅ Testable - can inject mock actions
- ✅ Works in previews
- ✅ Follows SwiftUI patterns

---

### Example 2: Cached Computed Properties

**Before:**
```swift
private var selectedSidebarItem: SidebarItem? {
    // Rebuilds ENTIRE tree on EVERY view update!
    let libraryItems = SidebarItemBuilder.buildLibraryHierarchy(from: documentStore.collections)
    ...
}
```

**After:**
```swift
@State private var cachedSidebarItems: [SidebarItem] = []

private var selectedSidebarItem: SidebarItem? {
    // Fast lookup from cache
    guard let id = selectedSidebarItemId else { return nil }
    return findItemById(id, in: cachedSidebarItems)
}

private func updateSidebarCache() {
    cachedSidebarItems = SidebarItemBuilder.buildLibraryHierarchy(from: documentStore.collections)
        + SidebarItemBuilder.buildSearchHierarchy(from: savedSearchService.savedSearches)
        + SidebarItemBuilder.buildChatHierarchy(from: conversationService.conversations)
        + SidebarItemBuilder.buildWorkflowHierarchy(from: workflowStore.workflows)
}

.onChange(of: documentStore.collections) { _, _ in
    updateSidebarCache()
}
.onChange(of: savedSearchService.savedSearches) { _, _ in
    updateSidebarCache()
}
.task {
    updateSidebarCache()  // Initial build
}
```

---

## Conclusion

The codebase demonstrates **solid SwiftUI fundamentals** but has several **anti-patterns** that should be addressed:

**Most Critical:**
1. Remove NotificationCenter (use `@FocusedValue`)
2. Cache computed properties
3. Handle Task cancellation
4. Refactor large view files

**These fixes will:**
- ✅ Make code more maintainable
- ✅ Improve performance
- ✅ Follow SwiftUI best practices
- ✅ Prepare for Swift 6 strict concurrency
- ✅ Make app more testable

**Estimated Effort:**
- P0 fixes: 6-8 hours
- P1 fixes: 8-12 hours
- P2 fixes: 4-6 hours
- **Total: 18-26 hours of focused work**

Would you like me to implement any of these fixes?
