# SwiftUI-Only Development Principles

**Last Updated:** 2025-12-28
**Status:** Mandatory Guidelines

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
    static let ui = Logger(subsystem: "ca.tubb.Fichero", category: "ui")
    static let data = Logger(subsystem: "ca.tubb.Fichero", category: "data")
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

- [ ] ✅ No AppKit usage (except where absolutely necessary)
- [ ] ✅ Using @FocusedValue instead of NotificationCenter
- [ ] ✅ Expensive computations are cached
- [ ] ✅ Tasks handle cancellation
- [ ] ✅ Using @ViewBuilder on computed view properties
- [ ] ✅ View files < 300 lines
- [ ] ✅ Using OSLog instead of NSLog/print
- [ ] ✅ Services injected via @EnvironmentObject
- [ ] ✅ Using @MainActor for UI updates
- [ ] ✅ No memory leaks from uncancelled tasks

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
3. **Proper state** - @Published, @FocusedValue, @Observable
4. **Cache expensive work** - Don't rebuild on every update
5. **Handle cancellation** - Tasks must check cancellation
6. **Small views** - Break up large files
7. **OSLog** - Structured logging only
8. **No NotificationCenter** - Use SwiftUI patterns

When in doubt: **Check Sosumi for the SwiftUI way!**
