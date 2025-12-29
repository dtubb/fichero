# SidebarView SwiftUI Code Review

**Date:** 2025-12-29
**Reviewer:** Claude
**File:** `Fichero/Fichero/Views/Sidebar/SidebarView.swift`
**Lines:** 943

---

## Executive Summary

SidebarView is **generally well-structured** but has **4 critical performance issues** and **2 anti-patterns** that violate SwiftUI best practices documented in `SWIFTUI_PRINCIPLES.md` and `development_standards.md`.

**Priority Issues:**
- ❌ **P0**: Rebuilding sidebar hierarchy on every view update (lines 20-34, 37-41)
- ❌ **P0**: Creating `DocumentService` instances in views (lines 341, 429, 805)
- ⚠️ **P1**: Using NSOpenPanel (AppKit) instead of SwiftUI `.fileImporter` (line 326)
- ⚠️ **P1**: File is 943 lines (SwiftLint limit: 400, recommendation: <300)

---

## ✅ What SidebarView Does Well

### 1. Proper State Management
```swift
@ObservedObject var documentStore: DocumentStore
@StateObject private var renameState = RenameStateManager()
@StateObject private var deleteState = DeleteStateManager()
```
✅ Uses `@ObservedObject` for passed-in state
✅ Uses `@StateObject` for owned state
✅ No service instantiation in `body`

### 2. @FocusedValue for Menu Commands (Lines 256-265)
```swift
.focusedValue(\.sidebarActions, SidebarActions(
    createFolder: handleCreateNewFolder,
    renameItem: handleRenameSelectedItem,
    deleteItem: handleDeleteSelectedItem
))
```
✅ **EXCELLENT**: Follows P0 pattern from `SWIFTUI_PRINCIPLES.md`
✅ Type-safe menu command routing
✅ No NotificationCenter anti-pattern

### 3. Observable Pattern for Delete/Rename
```swift
class RenameStateManager: ObservableObject {
    @Published var renamingItemId: String?
    @Published var editingName: String = ""
}
```
✅ Proper `ObservableObject` pattern
✅ Clear separation of concerns

### 4. Drag & Drop with documentStore (Lines 705-707)
```swift
_ = try await documentStore.moveDocument(actualItemId, toParent: actualTargetId)
NSLog("[SidebarView] ✅ Move successful - UI updates automatically via @Published")
```
✅ **EXCELLENT**: Uses documentStore pattern (consistent with rename/delete)
✅ UI updates automatically via @Published properties

---

## ❌ Critical Issues (P0)

### Issue #1: Rebuilding Sidebar Hierarchy on Every View Update

**Location:** Lines 20-41

**Current Code (❌ BAD):**
```swift
private var libraryItems: [SidebarItem] {
    SidebarItemBuilder.buildLibraryHierarchy(from: documentStore.collections)
}

private var searchItems: [SidebarItem] {
    SidebarItemBuilder.buildSearchHierarchy(from: savedSearchService.savedSearches)
}

private var chatItems: [SidebarItem] {
    SidebarItemBuilder.buildChatHierarchy(from: conversationService.conversations)
}

private var workflowItems: [SidebarItem] {
    SidebarItemBuilder.buildWorkflowHierarchy(from: workflowStore.workflows)
}

private var selectedItem: SidebarItem? {
    guard let id = selectedItemId else { return nil }
    let allItems = libraryItems + searchItems + chatItems + workflowItems
    return findItemById(id, in: allItems)
}
```

**Problem:**
- `libraryItems`, `searchItems`, `chatItems`, `workflowItems` are **computed properties**
- Called **EVERY TIME** SwiftUI re-evaluates the view (on selection changes, hover, etc.)
- Builds **ENTIRE** sidebar tree from scratch on every update
- **Massive performance hit** with large libraries

**Evidence from SWIFTUI_PRINCIPLES.md (Lines 100-124):**
```swift
### 3. ❌ Rebuilding Hierarchies on Every Update

**Bad:**
var items: [Item] {
    buildComplexHierarchy(from: data)  // Called constantly!
}

**Good:**
@State private var cachedItems: [Item] = []

.onChange(of: data) { _, _ in
    cachedItems = buildComplexHierarchy(from: data)
}
```

**Solution (✅ GOOD):**
```swift
@State private var cachedLibraryItems: [SidebarItem] = []
@State private var cachedSearchItems: [SidebarItem] = []
@State private var cachedChatItems: [SidebarItem] = []
@State private var cachedWorkflowItems: [SidebarItem] = []

private func rebuildCaches() {
    cachedLibraryItems = SidebarItemBuilder.buildLibraryHierarchy(from: documentStore.collections)
    cachedSearchItems = SidebarItemBuilder.buildSearchHierarchy(from: savedSearchService.savedSearches)
    cachedChatItems = SidebarItemBuilder.buildChatHierarchy(from: conversationService.conversations)
    cachedWorkflowItems = SidebarItemBuilder.buildWorkflowHierarchy(from: workflowStore.workflows)
}

// In body
.task {
    rebuildCaches()
}
.onChange(of: documentStore.collections) { _, _ in rebuildCaches() }
.onChange(of: savedSearchService.savedSearches) { _, _ in rebuildCaches() }
.onChange(of: conversationService.conversations) { _, _ in rebuildCaches() }
.onChange(of: workflowStore.workflows) { _, _ in rebuildCaches() }
```

**Impact:**
- 🚀 **Massive performance improvement**
- 🔥 Sidebar tree built once, not on every selection change
- ✅ Follows exact pattern from `SWIFTUI_PRINCIPLES.md` line 100-124
- ✅ Same pattern as ContentView.swift:58-65 (already implemented)

---

### Issue #2: Creating DocumentService Instances in Views

**Locations:**
- Line 341: `let documentService = DocumentService()`
- Line 429: `let documentService = DocumentService()`
- Line 805: `let documentService = DocumentService()`

**Current Code (❌ BAD):**
```swift
// Line 341 - importFiles()
Task {
    let documentService = DocumentService()  // ❌ Created in view!
    for url in panel.urls {
        _ = try await documentService.importFile(at: url, parentId: parentId)
    }
}

// Line 429 - performDelete()
let documentService = DocumentService()  // ❌ Created in view!
try await documentService.deleteDocument(actualId)

// Line 805 - performRename()
let documentService = DocumentService()  // ❌ Created in view!
_ = try await documentService.renameDocument(actualId, newName: newName)
```

**Problem:**
- Violates `SWIFTUI_PRINCIPLES.md` line 359-371
- Creates new service instances instead of using injected services
- Inconsistent with rename/delete for documents (which correctly use `documentStore`)

**Evidence from SWIFTUI_PRINCIPLES.md:**
```swift
### 3. ❌ Creating Service Instances in Views

**Bad:**
var body: some View {
    let service = DocumentService()  // Recreated every update!
}

**Good:**
@EnvironmentObject var documentService: DocumentService
```

**Solution (✅ GOOD):**

**Option 1: Use existing documentStore for everything**
```swift
// For imports (already have documentStore as @ObservedObject)
Task {
    for url in panel.urls {
        _ = try await documentStore.importFile(at: url, parentId: parentId)  // ✅
    }
}

// For deletes (already correct for documents)
try await documentStore.deleteDocument(actualId)  // ✅

// For renames (already correct for documents)
_ = try await documentStore.renameDocument(actualId, newName: newName)  // ✅
```

**Option 2: Inject DocumentService via @EnvironmentObject**
```swift
@EnvironmentObject var documentService: DocumentService

// Then use it everywhere instead of creating new instances
```

**Recommendation:** Use Option 1 (documentStore) since it's already injected and already used for document operations.

---

## ⚠️ High Priority Issues (P1)

### Issue #3: Using NSOpenPanel (AppKit) Instead of SwiftUI

**Location:** Line 326-354

**Current Code (❌ BAD):**
```swift
private func importFiles() {
    let panel = NSOpenPanel()  // ❌ AppKit!
    panel.allowsMultipleSelection = true
    panel.canChooseDirectories = false
    panel.canChooseFiles = true
    panel.allowedContentTypes = [.image, .pdf, .plainText, .data]

    if panel.runModal() == .OK {
        // ...
    }
}
```

**Problem:**
- Uses AppKit `NSOpenPanel` instead of SwiftUI `.fileImporter`
- Violates `development_standards.md` line 6-17
- Not following SwiftUI-only policy

**Evidence from development_standards.md:**
```markdown
## SwiftUI-Only Policy

**NO AppKit** - We use pure SwiftUI except in absolutely unavoidable cases:
- ❌ No NSView wrapping
- ❌ No AppKit controls
- ❌ No manual layout constraints

**Before using AppKit:**
1. Look in demo code
2. Check Sosumi MCP Tool for SwiftUI equivalent
3. Search Ref MCP Tool for documentation
4. Verify there's no SwiftUI-native solution
```

**Solution (✅ GOOD):**
```swift
@State private var showingFileImporter = false

// In body
.fileImporter(
    isPresented: $showingFileImporter,
    allowedContentTypes: [.image, .pdf, .plainText, .data],
    allowsMultipleSelection: true
) { result in
    switch result {
    case .success(let urls):
        importFiles(urls: urls)
    case .failure(let error):
        NSLog("[SidebarView] File import failed: \(error)")
    }
}

// In importFiles button
Button(action: { showingFileImporter = true }) {
    Image(systemName: "square.and.arrow.down")
}
```

**Impact:**
- ✅ Pure SwiftUI solution
- ✅ No AppKit dependency
- ✅ Works in SwiftUI previews
- ✅ Follows project SwiftUI-only policy

---

### Issue #4: File Length (943 lines)

**Problem:**
- File is 943 lines (SwiftLint limit: 400)
- Recommendation from `development_standards.md`: < 300 lines
- Makes code hard to navigate and maintain

**Evidence from development_standards.md (Line 26):**
```markdown
- **View Composition**: Break complex views into < 300 line files
```

**Solution:**
Split into separate files:

```
Sidebar/
├── SidebarView.swift (main view, ~200 lines)
├── SidebarItemRow.swift (row rendering, ~150 lines)
├── SidebarItemContextMenu.swift (context menu, ~50 lines)
├── SidebarStateManagers.swift (RenameStateManager, DeleteStateManager, ~100 lines)
└── SidebarActions.swift (action handlers, ~200 lines)
```

---

## 🟡 Medium Priority Issues (P2)

### Issue #5: Unused parentId Variable

**Location:** Line 358

**Current Code:**
```swift
var parentId: String?
if let selected = selectedItem, case .document(let doc) = selected.itemType {
    parentId = doc.id  // ⚠️ Written but never used
}
```

**SwiftLint Warning:**
```
warning: variable 'parentId' was written to, but never read
```

**Solution:**
Remove unused variable or pass to `createCollection`:
```swift
try await documentStore.createCollection(name: "New Folder", parentId: parentId)
```

---

### Issue #6: Missing OSLog Instead of NSLog

**Locations:** Throughout file (40+ instances)

**Current Code (❌ BAD):**
```swift
NSLog("[SidebarView] Created new folder")
```

**Evidence from SWIFTUI_PRINCIPLES.md (Line 212-231):**
```swift
### 7. Use Proper Logging

**✅ DO:**
import OSLog

extension Logger {
    static let ui = Logger(subsystem: "ca.tubb.Fichero", category: "ui")
}

Logger.ui.info("User selected item: \(itemId)")

**❌ DON'T:**
NSLog("[View] User did thing")  // ❌ Unstructured, slow
```

**Solution:**
```swift
import OSLog

extension Logger {
    static let sidebar = Logger(subsystem: "ca.tubb.Fichero", category: "sidebar")
}

// Replace all NSLog with:
Logger.sidebar.info("Created new folder")
Logger.sidebar.error("Failed to delete: \(error.localizedDescription)")
```

---

## 📊 Code Quality Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| File Length | 943 lines | 400 lines | ❌ Exceeds |
| Computed Properties Cached | 0/4 | 4/4 | ❌ None |
| Service Injection | Partial | Complete | ⚠️ Inconsistent |
| AppKit Usage | 1 (NSOpenPanel) | 0 | ❌ Present |
| Logging | NSLog | OSLog | ❌ Wrong |

---

## 🎯 Recommended Fix Order

### Phase 1: P0 Performance Fixes (Critical)
1. **Cache sidebar item hierarchies** (Issue #1)
   - Add `@State` caches for all 4 item types
   - Add `rebuildCaches()` function
   - Add `.onChange()` handlers for source data
   - **Impact:** Massive performance improvement

2. **Remove DocumentService instantiation** (Issue #2)
   - Use `documentStore` for all operations
   - Remove `let documentService = DocumentService()` lines
   - **Impact:** Consistent pattern, follows SwiftUI best practices

### Phase 2: P1 SwiftUI Compliance
3. **Replace NSOpenPanel with .fileImporter** (Issue #3)
   - Add `@State private var showingFileImporter`
   - Replace AppKit code with SwiftUI `.fileImporter` modifier
   - **Impact:** Pure SwiftUI, works in previews

4. **Split into smaller files** (Issue #4)
   - Extract SidebarItemRow to separate file
   - Extract state managers to separate file
   - Extract action handlers to separate file
   - **Impact:** Better maintainability

### Phase 3: P2 Code Quality
5. **Fix unused parentId** (Issue #5)
6. **Replace NSLog with OSLog** (Issue #6)

---

## 📝 Summary

SidebarView has **excellent @FocusedValue usage** and **proper drag & drop patterns**, but suffers from **critical performance issues** due to rebuilding hierarchies on every view update.

**Key Fixes Needed:**
1. ✅ Cache sidebar item hierarchies (same pattern as ContentView)
2. ✅ Use documentStore instead of creating DocumentService
3. ✅ Replace NSOpenPanel with SwiftUI .fileImporter
4. ✅ Split into smaller files (< 300 lines each)
5. ✅ Replace NSLog with OSLog

**Estimated Impact:**
- 🚀 10-100x performance improvement for large libraries
- ✅ 100% SwiftUI compliance
- ✅ Follows all patterns from SWIFTUI_PRINCIPLES.md
- ✅ Ready for SwiftLint approval

---

## 📖 References

- `ai/contexts/frontend/SWIFTUI_PRINCIPLES.md` - Lines 100-124 (caching), 212-231 (logging), 359-371 (service injection)
- `ai/contexts/frontend/development_standards.md` - Lines 6-17 (SwiftUI-only), 26 (file size)
- `Fichero/Fichero/Views/ContentView.swift` - Lines 48-65 (caching example already implemented)
- `P0_FIXES_SUMMARY.md` - Lines 64-122 (caching pattern precedent)
