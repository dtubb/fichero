# SwiftUI-Only Development Principles

**Last Updated:** 2025-12-31
**Status:** Mandatory Guidelines | ✅ Swift 6 Compatible

---

## Core Philosophy

Fichero's Swift frontend is **100% SwiftUI**. We do NOT use:
- ❌ AppKit views or controls
- ❌ NSView wrapping
- ❌ UIViewRepresentable (except for absolutely unavoidable cases)
- ❌ Custom drawing that can be done with SwiftUI
- ❌ Legacy Cocoa patterns

**If something seems hard in SwiftUI, the solution is to:**
1. Use MCP tools (Ref, Sosumi) to look up the proper SwiftUI API
2. Search Apple documentation for SwiftUI equivalents
3. Rethink the approach to fit SwiftUI's declarative model

---

## SwiftUI Best Practices (Mandatory)

### 1. Use Proper State Management

**✅ DO:**
```swift
// @StateObject for owning the state
@StateObject private var documentStore = DocumentStore()

// @ObservedObject for passed-in state
@ObservedObject var documentStore: DocumentStore

// @EnvironmentObject for dependency injection
@EnvironmentObject var appState: AppState

// @State for local view state
@State private var isExpanded = false

// @Binding for two-way bindings
@Binding var selectedItem: String?
```

**❌ DON'T:**
```swift
// Creating objects in body - recreated on every view update!
var body: some View {
    let service = DocumentService()  // ❌ Wrong!
}

// Using NotificationCenter for state changes
NotificationCenter.default.post(...)  // ❌ Anti-pattern!

// Manual DispatchQueue.main.async
DispatchQueue.main.async {  // ❌ Use @MainActor instead
    self.updateUI()
}
```

---

### 2. Use @FocusedValue for Menu Commands

**✅ DO:**
```swift
// Define focused value
extension FocusedValues {
    var sidebarActions: SidebarActions? {
        get { self[SidebarActionsKey.self] }
        set { self[SidebarActionsKey.self] = newValue }
    }
}

// Provide from view
.focusedValue(\.sidebarActions, SidebarActions(
    createFolder: handleCreate,
    deleteItem: handleDelete
))

// Consume in menu
@FocusedValue(\.sidebarActions) private var actions

Button("New Folder") {
    actions?.createFolder()
}
```

**❌ DON'T:**
```swift
// Using NotificationCenter
Button("New Folder") {
    NotificationCenter.default.post(name: .create, object: nil)  // ❌
}
```

---

### 3. Cache Expensive Computations

**✅ DO:**
```swift
@State private var cachedItems: [Item] = []

private var selectedItem: Item? {
    // Fast lookup from cache
    cachedItems.first { $0.id == selectedId }
}

.onChange(of: sourceData) { _, _ in
    // Rebuild cache only when data changes
    cachedItems = buildItemTree(from: sourceData)
}
```

**❌ DON'T:**
```swift
private var selectedItem: Item? {
    // Rebuilds ENTIRE tree on EVERY view update!
    let items = buildItemTree(from: sourceData)  // ❌
    return items.first { $0.id == selectedId }
}
```

---

### 4. Handle Task Cancellation

**✅ DO:**
```swift
.task {
    // Structured concurrency - auto-cancels
    await withTaskGroup(of: Void.self) { group in
        group.addTask {
            guard !Task.isCancelled else { return }
            await loadData()
        }
    }
}
```

**❌ DON'T:**
```swift
.task {
    await loadData()  // ❌ Won't cancel if view disappears
}
```

---

### 5. Use @ViewBuilder for Complex Views

**✅ DO:**
```swift
@ViewBuilder
private var contentView: some View {
    switch mode {
    case .list:
        ListView()
    case .grid:
        GridView()
    }
}
```

**❌ DON'T:**
```swift
private var contentView: some View {
    // Missing @ViewBuilder - limits flexibility
}
```

---

### 6. Split Large Views

**✅ DO:**
```swift
// Main view < 200 lines
struct ContentView: View {
    var body: some View {
        NavigationSplitView {
            sidebarContent
        } content: {
            centerContent
        } detail: {
            detailContent
        }
    }
}

// Extract to computed properties or separate files
@ViewBuilder
private var sidebarContent: some View {
    SidebarView(...)
}
```

**❌ DON'T:**
```swift
// 1000+ line view file
struct MassiveView: View {
    var body: some View {
        // Tons of nested views...
    }
}
```

---

### 7. Use Proper Logging

**✅ DO:**
```swift
import OSLog

extension Logger {
    static let ui = Logger(subsystem: "com.tubb.Fichero", category: "ui")
    static let data = Logger(subsystem: "com.tubb.Fichero", category: "data")
}

Logger.ui.info("User selected item: \(itemId)")
Logger.data.debug("Loaded \(count) documents")
```

**❌ DON'T:**
```swift
NSLog("[View] User did thing")  // ❌ Unstructured, slow
print("Debug info")  // ❌ Lost on app termination
```

---

### 8. Avoid AppKit Unless Absolutely Necessary

**✅ DO:**
```swift
// Use SwiftUI native controls
List {
    ForEach(items) { item in
        Text(item.name)
    }
}

// Use SwiftUI animations
.animation(.easeInOut, value: isExpanded)

// Use SwiftUI layout
HStack(spacing: 8) { ... }
```

**❌ DON'T:**
```swift
// Wrapping NSView
struct NSViewWrapper: NSViewRepresentable { ... }  // ❌ Only if unavoidable

// Using NSColor/NSFont
.foregroundColor(Color(nsColor: .labelColor))  // ❌ Use Color.primary

// AppKit layout constraints
NSLayoutConstraint.activate(...)  // ❌ Use SwiftUI layout
```

**When AppKit IS Required:**
- Native system file pickers (use .fileImporter)
- Advanced text editing (use TextEditor first)
- System integrations not available in SwiftUI

**Before using AppKit:**
1. Check Sosumi MCP for SwiftUI equivalent
2. Search Ref MCP for documentation
3. Ask if there's a SwiftUI-native way

---

### 9. Swift 6 Concurrency Patterns

**CRITICAL**: Fichero is Swift 6 compliant with strict concurrency checking enabled.

#### Main Actor Isolation

**Rule**: If a class is marked `@MainActor`, all its methods and properties automatically run on the main thread. Don't use dispatch queues for serialization.

**✅ DO:**
```swift
@MainActor
class DragDropModel: ObservableObject {
    @Published var isProcessing: Bool = false
    private var operations: Set<UUID> = []

    func startOperation() -> UUID {
        let id = UUID()
        operations.insert(id)  // Already on main actor
        return id
    }

    func endOperation(_ id: UUID) {
        operations.remove(id)  // Already on main actor
    }
}
```

**❌ DON'T:**
```swift
@MainActor
class DragDropModel: ObservableObject {
    private let queue = DispatchQueue(...)  // ❌ Unnecessary!

    func startOperation() -> UUID {
        queue.async(flags: .barrier) {  // ❌ Wrong! Already on main actor
            self.operations.insert(id)  // Will cause concurrency warning
        }
    }
}
```

**Why This Matters**: `@MainActor` provides automatic serialization. Adding a dispatch queue creates an "actor hopping" problem where you're trying to access main actor state from a different execution context.

---

#### Calling Main Actor Methods from Background Contexts

**Pattern**: Use `Task { @MainActor in ... }` to hop to the main actor from non-isolated closures.

**✅ DO:**
```swift
// In a non-isolated closure (e.g., NSItemProvider callback)
provider.loadItem(...) { [weak self] data, error in
    guard let self = self else { return }

    // Hop to main actor before calling main-actor-isolated methods
    Task { @MainActor in
        self.dragDropModel.endOperation(operationId)
        self.dragDropModel.updateProgress(0.5)

        if let error = error {
            self.handleError(error)  // handleError is @MainActor
        }
    }
}
```

**❌ DON'T:**
```swift
// Direct call from non-isolated context
provider.loadItem(...) { data, error in
    self.dragDropModel.endOperation(operationId)  // ❌ Concurrency warning!

    DispatchQueue.main.async {  // ❌ Wrong pattern for Swift 6
        self.updateUI()
    }
}
```

---

#### Sendable Conformance

**Use `@unchecked Sendable` for classes that implement their own thread safety**.

**✅ DO:**
```swift
final class AtomicCounter: @unchecked Sendable {
    private var value: Int
    private let lock = NSLock()  // Provides thread safety

    init(value: Int) {
        self.value = value
    }

    func incrementAndGet() -> Int {
        lock.lock()
        defer { lock.unlock() }
        value += 1
        return value
    }

    func get() -> Int {
        lock.lock()
        defer { lock.unlock() }
        return value
    }
}
```

**Why `@unchecked`**: The lock provides thread safety, but Swift can't verify it statically. We use `@unchecked` to tell the compiler "trust us, this is thread-safe."

**❌ DON'T:**
```swift
class AtomicCounter {  // ❌ Not Sendable
    private var value: Int  // ❌ Can cause data races
}
```

---

#### Task Cancellation (MANDATORY)

**All `.task {}` blocks MUST check for cancellation**.

**✅ DO:**
```swift
.task {
    for item in items {
        guard !Task.isCancelled else {
            logger.debug("Task cancelled, cleaning up...")
            return
        }
        await processItem(item)
    }
}

// Or with defer for cleanup
.task {
    defer {
        if Task.isCancelled {
            cleanup()
        }
    }

    await loadData()
}
```

**❌ DON'T:**
```swift
.task {
    // Never checks cancellation - keeps running after view disappears!
    await loadData()
}
```

---

#### Pattern: Background Work → Main Actor Update

**Common scenario**: Load data in background, update UI on main actor.

**✅ DO:**
```swift
func loadDocuments() {
    Task {
        // Background work
        let documents = try await apiClient.fetchDocuments()

        // Hop to main actor for UI update
        await MainActor.run {
            self.documents = documents
            self.isLoading = false
        }
    }
}

// Or if the whole function is main-actor-isolated:
@MainActor
func loadDocuments() async {
    // Automatically on main actor
    let documents = try await apiClient.fetchDocuments()
    self.documents = documents
    self.isLoading = false
}
```

**❌ DON'T:**
```swift
func loadDocuments() {
    Task {
        let documents = try await apiClient.fetchDocuments()

        // Missing main actor isolation!
        self.documents = documents  // ❌ Potential crash or data race
    }
}
```

---

#### Common Concurrency Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| "Main actor-isolated property cannot be mutated from Sendable closure" | Accessing @MainActor property from background | Wrap in `Task { @MainActor in ... }` |
| "Capture of 'self' with non-sendable type" | Using non-Sendable type in Task | Make type conform to Sendable or use `@unchecked Sendable` |
| "Call to main actor-isolated method in synchronous nonisolated context" | Calling @MainActor method from background | Wrap in `Task { @MainActor in ... }` or mark function `@MainActor` |
| Task keeps running after view disappears | Missing cancellation check | Add `guard !Task.isCancelled else { return }` |

---

#### Real Example from Fichero

**Before (Swift 5 - Has concurrency warnings)**:
```swift
@MainActor
class DragDropModel: ObservableObject {
    private var activeOperations: Set<UUID> = []
    private let operationQueue = DispatchQueue(...)  // ❌ Conflict with @MainActor

    func startOperation() -> UUID {
        let id = UUID()
        operationQueue.async(flags: .barrier) {  // ❌ Wrong actor!
            self.activeOperations.insert(id)  // Warning: main actor property from sendable closure
        }
        return id
    }
}
```

**After (Swift 6 - Compliant)**:
```swift
@MainActor
class DragDropModel: ObservableObject {
    private var activeOperations: Set<UUID> = []
    // No dispatch queue needed - @MainActor provides serialization

    func startOperation() -> UUID {
        let id = UUID()
        activeOperations.insert(id)  // ✅ Already on main actor
        return id
    }
}
```

---

## MCP Tools for SwiftUI Development

### 1. Sosumi - Apple Documentation

**Use Cases:**
- Finding SwiftUI view modifiers
- Learning proper SwiftUI patterns
- Checking Human Interface Guidelines

**Examples:**
```swift
// Want to know how to do drag & drop in SwiftUI?
// Use: sosumi.searchAppleDocumentation("swiftui drag drop")
// Then: sosumi.fetchAppleDocumentation("path/from/search")

// Want to know proper SwiftUI navigation?
// Use: sosumi.searchAppleDocumentation("NavigationSplitView")
```

### 2. Ref - General Documentation

**Use Cases:**
- Swift language features
- SwiftUI API reference
- Third-party Swift libraries

**Examples:**
```swift
// Need to understand @Observable?
// Use: ref.searchDocumentation("Swift @Observable macro")

// Want to learn about structured concurrency?
// Use: ref.searchDocumentation("Swift TaskGroup")
```

### 3. When to Use Each

| Question | Tool |
|----------|------|
| "How do I do X in SwiftUI?" | Sosumi |
| "What's the SwiftUI equivalent of Y?" | Sosumi |
| "How does Swift feature Z work?" | Ref |
| "What are the HIG guidelines for...?" | Sosumi |
| "How do I use library X?" | Ref |

---

## Anti-Patterns to Avoid

### 1. ❌ NotificationCenter for App Logic

**Bad:**
```swift
NotificationCenter.default.post(name: .didSelectItem, object: item)
```

**Good:**
```swift
@FocusedValue(\.selection) var selection
```

---

### 2. ❌ Manual Thread Dispatching

**Bad:**
```swift
DispatchQueue.main.async {
    self.updateUI()
}
```

**Good:**
```swift
@MainActor
func updateUI() {
    // Swift ensures this runs on main thread
}
```

---

### 3. ❌ Creating Service Instances in Views

**Bad:**
```swift
var body: some View {
    let service = DocumentService()  // Recreated every update!
}
```

**Good:**
```swift
@EnvironmentObject var documentService: DocumentService
```

---

### 4. ❌ Rebuilding Hierarchies on Every Update

**Bad:**
```swift
var items: [Item] {
    buildComplexHierarchy(from: data)  // Called constantly!
}
```

**Good:**
```swift
@State private var cachedItems: [Item] = []

.onChange(of: data) { _, _ in
    cachedItems = buildComplexHierarchy(from: data)
}
```

---

### 5. ❌ Ignoring Task Cancellation

**Bad:**
```swift
.task {
    await loadData()  // Keeps running if view disappears
}
```

**Good:**
```swift
.task {
    guard !Task.isCancelled else { return }
    await loadData()
}
```

---

## SwiftUI Patterns to Follow

### Observable Pattern (New in iOS 17)

```swift
@Observable
class DocumentStore {
    var documents: [Document] = []
    var selectedId: String?

    func loadDocuments() async {
        documents = try await api.fetchDocuments()
    }
}

// In view
@State private var store = DocumentStore()

var body: some View {
    List(store.documents) { doc in
        Text(doc.name)
    }
}
```

### Dependency Injection

```swift
// App level
@main
struct App: App {
    @StateObject private var documentStore = DocumentStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(documentStore)
        }
    }
}

// Child view
struct ContentView: View {
    @EnvironmentObject var documentStore: DocumentStore
}
```

### Proper Navigation

```swift
// Use NavigationSplitView for 3-column layouts
NavigationSplitView {
    SidebarView()
} content: {
    ContentView()
} detail: {
    DetailView()
}

// Use NavigationStack for hierarchical navigation
NavigationStack(path: $navPath) {
    ListView()
        .navigationDestination(for: Item.self) { item in
            DetailView(item: item)
        }
}
```

---

## Code Review Checklist

Before committing Swift code, verify:

**SwiftUI Compliance**:
- [ ] ✅ No AppKit usage (except where absolutely necessary)
- [ ] ✅ Using @FocusedValue instead of NotificationCenter
- [ ] ✅ View files < 400 lines
- [ ] ✅ Using @ViewBuilder on computed view properties
- [ ] ✅ Services injected via @EnvironmentObject (never created in views)

**Performance**:
- [ ] ✅ Expensive computations are cached
- [ ] ✅ No view hierarchies rebuilt on every update
- [ ] ✅ Using @StateObject (not inline object creation)

**Swift 6 Concurrency**:
- [ ] ✅ All `.task {}` blocks check `Task.isCancelled`
- [ ] ✅ Using @MainActor for UI-related classes (not DispatchQueue.main)
- [ ] ✅ Non-isolated closures use `Task { @MainActor in ... }` for UI updates
- [ ] ✅ Thread-safe types conform to `Sendable` or `@unchecked Sendable`
- [ ] ✅ No dispatch queues in @MainActor classes
- [ ] ✅ No concurrency warnings in Xcode build

**Code Quality**:
- [ ] ✅ Using OSLog instead of NSLog/print
- [ ] ✅ Descriptive variable names (no `x`, `y`, `i`, etc.)
- [ ] ✅ Functions < 50 lines
- [ ] ✅ Cyclomatic complexity < 10
- [ ] ✅ SwiftLint passes with zero errors

---

## Resources

### Always Check First
1. **Sosumi MCP** - Official Apple SwiftUI docs
2. **Ref MCP** - Swift language and libraries
3. **SWIFTUI_CODE_REVIEW.md** - Detailed best practices analysis

### Reference Documentation
- `SWIFTUI_CODE_REVIEW.md` - Complete anti-pattern analysis
- `DRAG_DROP_CODE_REVIEW.md` - Drag & drop patterns
- `P0_FIXES_SUMMARY.md` - Critical fixes implemented

---

## Summary

**Golden Rules:**
1. **SwiftUI-only** - Avoid AppKit unless unavoidable
2. **Use MCP tools** - Sosumi & Ref before guessing
3. **Proper state** - @Observable, @FocusedValue, @EnvironmentObject
4. **Cache expensive work** - Don't rebuild on every update
5. **Swift 6 concurrency** - @MainActor, Task cancellation, Sendable
6. **Small files** - Keep views < 400 lines
7. **OSLog** - Structured logging only
8. **No NotificationCenter** - Use SwiftUI patterns
9. **No DispatchQueue in @MainActor** - Main actor provides serialization

**Swift 6 Quick Reference:**
- `@MainActor` class → All access already on main thread
- Background closure → Use `Task { @MainActor in ... }` for UI updates
- Thread-safe class → Conform to `@unchecked Sendable`
- `.task {}` → Always check `Task.isCancelled`

When in doubt: **Check Sosumi for the SwiftUI way!**
