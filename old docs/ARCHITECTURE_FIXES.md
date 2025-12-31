# Architecture Fixes - Before SwiftUI Cleanup

**Date:** 2025-12-30
**Status:** MUST DO FIRST - Before SWIFTUI_AUDIT_PLAN.md
**Priority:** P0 (Critical - Architectural issues must be fixed first)

---

## Executive Summary

Before fixing SwiftUI code quality issues, we need to fix **fundamental architectural problems**:

1. ❌ **No ImportService** - file import logic is scattered across 3 files
2. ❌ **Toolbar jumping** - inconsistent toolbar patterns across views
3. ❌ **File import in wrong place** - FicheroApp.swift has business logic
4. ❓ **Models folder organization** - needs review

**Key Principle:** The Swift app is a **pure UI layer**. ALL business logic should be in the Python backend or Swift Services that call the backend.

---

## Problem 1: No ImportService (CRITICAL)

### Current State ❌

File import logic is **scattered across 3 files**:

1. **FicheroApp.swift:252-277** - Menu commands use NSOpenPanel directly
   ```swift
   private func importFiles() {
       let panel = NSOpenPanel()  // ❌ Business logic in app file
       // ...
   }
   ```

2. **ContentView.swift:494-556** - Drag-and-drop handling
   ```swift
   func handleFileDrop(urls: [URL]) {
       // ❌ Import logic mixed with view code
       _ = try await documentStore.importFile(at: url, parentId: targetParentId)
   }
   ```

3. **DocumentStore.swift** - API calls
   ```swift
   func importFile(at url: URL, parentId: String?) async throws -> Document {
       // ❌ DocumentStore shouldn't handle import directly
   }
   ```

### Problems

- **Duplication**: Import logic in 3 places
- **Inconsistency**: Menu import vs drag-and-drop import may diverge
- **Testing**: Can't test import logic independently
- **Maintainability**: Changes require updating multiple files
- **Architecture violation**: Business logic in views

### Solution ✅

**Create `ImportService.swift`** - Single source of truth for all file import:

```swift
// Fichero/Fichero/Services/ImportService.swift
import Foundation
import UniformTypeIdentifiers

/// Service for file and folder import
/// Wraps the Python backend ingest API
@MainActor
class ImportService: ObservableObject {
    // MARK: - Published State

    @Published var isImporting: Bool = false
    @Published var importProgress: ImportProgress?
    @Published var lastError: ImportError?

    private let api = APIClient.shared

    // MARK: - Import Files

    /// Import multiple files from URLs
    /// - Parameters:
    ///   - urls: File URLs to import
    ///   - mode: LINK or COPY mode
    ///   - parentId: Optional parent collection ID
    ///   - extractText: Extract searchable text
    ///   - autoEmbed: Create vector embeddings
    /// - Returns: Array of imported documents
    func importFiles(
        _ urls: [URL],
        mode: IngestMode = .link,
        parentId: String? = nil,
        extractText: Bool = false,
        autoEmbed: Bool = false,
        onProgress: ((Int, Int) -> Void)? = nil
    ) async throws -> [Document] {
        isImporting = true
        defer { isImporting = false }

        var imported: [Document] = []
        var errors: [ImportError] = []

        for (index, url) in urls.enumerated() {
            do {
                // Update progress
                onProgress?(index + 1, urls.count)
                importProgress = ImportProgress(
                    current: index + 1,
                    total: urls.count,
                    currentFile: url.lastPathComponent
                )

                // Call Python backend: POST /api/ingest/file
                let doc = try await importFile(
                    url,
                    mode: mode,
                    parentId: parentId,
                    extractText: extractText,
                    autoEmbed: autoEmbed
                )
                imported.append(doc)

            } catch {
                errors.append(ImportError(url: url, error: error))
            }
        }

        importProgress = nil

        if !errors.isEmpty {
            lastError = errors.first
            // Could aggregate errors into a single error
        }

        return imported
    }

    /// Import a single file
    private func importFile(
        _ url: URL,
        mode: IngestMode,
        parentId: String?,
        extractText: Bool,
        autoEmbed: Bool
    ) async throws -> Document {
        // Call Python backend: POST /api/ingest/file
        let params: [String: Any] = [
            "path": url.path,
            "mode": mode.rawValue,
            "parent_id": parentId as Any,
            "extract_text": extractText,
            "auto_embed": autoEmbed
        ]

        return try await api.post("/ingest/file", body: params)
    }

    // MARK: - Import Folder

    /// Import an entire folder
    func importFolder(
        _ url: URL,
        mode: IngestMode = .link,
        parentId: String? = nil,
        recursive: Bool = true,
        extractText: Bool = false,
        autoEmbed: Bool = false,
        onProgress: ((Int, Int) -> Void)? = nil
    ) async throws -> [Document] {
        isImporting = true
        defer { isImporting = false }

        // Call Python backend: POST /api/ingest/folder
        let params: [String: Any] = [
            "folder": url.path,
            "mode": mode.rawValue,
            "parent_id": parentId as Any,
            "recursive": recursive,
            "extract_text": extractText,
            "auto_embed": autoEmbed
        ]

        return try await api.post("/ingest/folder", body: params)
    }
}

// MARK: - Supporting Types

enum IngestMode: String, Codable {
    case link = "LINK"  // Create bookmark reference
    case copy = "COPY"  // Copy file into library
}

struct ImportProgress {
    let current: Int
    let total: Int
    let currentFile: String

    var percentage: Double {
        Double(current) / Double(total) * 100
    }
}

struct ImportError: Error {
    let url: URL
    let error: Error

    var localizedDescription: String {
        "Failed to import \(url.lastPathComponent): \(error.localizedDescription)"
    }
}
```

### Refactor Plan

1. **Create ImportService.swift** in `Services/`
2. **Update FicheroApp.swift**:
   ```swift
   @StateObject private var importService = ImportService()
   @State private var showingFileImporter = false
   @State private var showingFolderImporter = false

   // Replace NSOpenPanel with SwiftUI fileImporter
   .fileImporter(
       isPresented: $showingFileImporter,
       allowedContentTypes: [.image, .pdf, .plainText],
       allowsMultipleSelection: true
   ) { result in
       Task {
           switch result {
           case .success(let urls):
               _ = try await importService.importFiles(urls)
           case .failure(let error):
               // Handle error
           }
       }
   }
   ```

3. **Update ContentView.swift**:
   ```swift
   @EnvironmentObject var importService: ImportService

   func handleFileDrop(urls: [URL]) {
       Task {
           _ = try await importService.importFiles(
               urls,
               parentId: currentParentId
           )
       }
   }
   ```

4. **Remove import methods from DocumentStore** - it should only handle document CRUD, not import

---

## Problem 2: Toolbar Jumping (UI Consistency Issue)

### Current State ❌

Multiple views define their own toolbars independently:

1. **ContentView.swift:405** - `libraryToolbar`
2. **WorkflowEditor.swift:45** - `workflowToolbar`
3. **SidebarViewExtensions.swift** - `sidebarToolbar`

Each toolbar uses different:
- Placement strategies
- Item groupings
- Button styles
- Divider placement

### Problems

- **Visual jumping**: Toolbar changes size/position when switching modes
- **Inconsistent UX**: Different button styles across views
- **Hard to maintain**: Changes require updating multiple files

### Root Cause

SwiftUI NavigationSplitView toolbars are applied at different levels:

```swift
// ContentView.swift
NavigationSplitView {
    SidebarView()
        .toolbar { sidebarToolbar }  // ❌ Toolbar on sidebar
} content: {
    LibraryView()
        .toolbar { libraryToolbar }  // ❌ Toolbar on content
} detail: {
    EditorView()
        .toolbar { editorToolbar }   // ❌ Toolbar on detail
}
```

### Solution ✅

**Apply toolbar at NavigationSplitView level**, not on child views:

```swift
// ContentView.swift
NavigationSplitView {
    sidebarContent
} content: {
    centerContent
} detail: {
    detailContent
}
.toolbar {
    // ✅ Single toolbar definition at NavigationSplitView level
    ToolbarItemGroup(placement: .navigation) {
        // Navigation items (left side)
        sidebarToolbarItems
    }

    ToolbarItemGroup(placement: .primaryAction) {
        // Primary actions (right side)
        switch viewMode {
        case .library, .search:
            libraryToolbarItems
        case .workflow:
            workflowToolbarItems
        case .chat:
            chatToolbarItems
        }
    }
}
```

### Benefits

- ✅ **No jumping**: Toolbar position stays consistent
- ✅ **Smooth transitions**: Only toolbar content changes, not structure
- ✅ **Single source of truth**: One toolbar definition
- ✅ **Easier maintenance**: Update in one place

### Implementation Steps

1. **Remove all `.toolbar {}` from child views**:
   - SidebarView
   - LibraryView
   - WorkflowEditor
   - ChatView

2. **Create single toolbar in ContentView.swift**:
   ```swift
   @ToolbarContentBuilder
   private var unifiedToolbar: some ToolbarContent {
       // Navigation items (left)
       ToolbarItemGroup(placement: .navigation) {
           Button(action: { /* toggle sidebar */ }) {
               Image(systemName: "sidebar.left")
           }
       }

       // Primary actions (right) - changes based on viewMode
       ToolbarItemGroup(placement: .primaryAction) {
           switch viewMode {
           case .library, .search:
               libraryToolbarContent
           case .workflow:
               workflowToolbarContent
           case .chat:
               chatToolbarContent
           }
       }
   }

   @ToolbarContentBuilder
   private var libraryToolbarContent: some ToolbarContent {
       // View mode picker
       Picker("View", selection: $viewSettings.libraryLayout) { ... }
       Divider()
       Button(action: { viewSettings.showInspector.toggle() }) {
           Image(systemName: "sidebar.right")
       }
   }

   @ToolbarContentBuilder
   private var workflowToolbarContent: some ToolbarContent {
       // Workflow-specific buttons
   }
   ```

3. **Apply toolbar to NavigationSplitView**:
   ```swift
   NavigationSplitView { ... }
   .toolbar { unifiedToolbar }
   ```

---

## Problem 3: File Import in FicheroApp.swift (Architecture Violation)

### Current State ❌

FicheroApp.swift has business logic:

```swift
// FicheroApp.swift:252-277
private func importFiles() {
    let panel = NSOpenPanel()  // ❌ AppKit
    panel.allowsMultipleSelection = true
    // ... business logic in app file
}
```

### Problems

- **Separation of concerns**: App file should only define app structure
- **Testing**: Can't test import without launching entire app
- **Reusability**: Import logic tied to app lifecycle

### Solution ✅

**Move ALL business logic to ImportService**:

```swift
// FicheroApp.swift - ONLY UI structure
@main
struct FicheroApp: App {
    @StateObject private var appState = AppState()
    @StateObject private var viewSettings = ViewSettings()
    @StateObject private var importService = ImportService()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
                .environmentObject(viewSettings)
                .environmentObject(importService)  // ✅ Inject service
        }
        .commands {
            CommandGroup(replacing: .newItem) {
                // ✅ Commands just trigger UI state
                Button("Import Files...") {
                    appState.showFileImporter = true
                }
                Button("Import Folder...") {
                    appState.showFolderImporter = true
                }
            }
        }
    }
}

// ✅ Actual import happens in ContentView with service
```

---

## Problem 4: Models Folder Organization

### Current State

```
Models/
├── Document.swift ✅
├── Provider.swift ✅
├── Workflow.swift ✅
├── WorkflowTypes.swift ✅
├── WorkflowStore.swift ⚠️ (Service, not Model)
├── DocumentStore.swift ⚠️ (Service, not Model)
├── SidebarItem.swift ✅
├── SidebarItemBuilder.swift ⚠️ (Utility, not Model)
├── SidebarState.swift ✅
├── DragDropModel.swift ✅
├── CacheModel.swift ⚠️ (Service, not Model)
├── ErrorModel.swift ✅
└── WorkflowExporter.swift ⚠️ (Utility, not Model)
```

### Problems

- **Stores in Models**: WorkflowStore, DocumentStore should be in Services/
- **Utilities in Models**: SidebarItemBuilder, WorkflowExporter should be in Utilities/
- **CacheModel**: Should be deleted or moved to Services/

### Solution ✅

**Reorganize into proper folders**:

```
Models/               # Pure data models only
├── Document.swift
├── Provider.swift
├── Workflow.swift
├── WorkflowTypes.swift
├── SidebarItem.swift
├── SidebarState.swift
├── DragDropModel.swift
└── ErrorModel.swift

Services/             # ObservableObject services
├── APIClient.swift
├── DocumentStore.swift     ← MOVE HERE
├── WorkflowStore.swift     ← MOVE HERE
├── ImportService.swift     ← CREATE NEW
├── ChatService.swift
├── ModelService.swift
├── ProviderService.swift
├── SearchService.swift
├── SavedSearchService.swift
├── ConversationService.swift
├── DragDropService.swift
├── ErrorService.swift
└── PerformanceService.swift

Utilities/            # Pure functions, builders
├── SidebarItemBuilder.swift  ← MOVE HERE
├── WorkflowExporter.swift    ← MOVE HERE
└── ImageCache.swift          ← RENAME from CacheModel (if needed)

App/                  # App-level state
├── FicheroApp.swift
├── AppState.swift
└── ViewSettings.swift
```

### Migration Steps

1. Create `Utilities/` folder
2. Move `SidebarItemBuilder.swift` → `Utilities/`
3. Move `WorkflowExporter.swift` → `Utilities/`
4. Move `DocumentStore.swift` → `Services/` (update imports)
5. Move `WorkflowStore.swift` → `Services/` (update imports)
6. Delete or refactor `CacheModel.swift` (not needed - SwiftUI caches Images)
7. Update all imports across project
8. Test build

---

## Implementation Order

### Phase 0: Architecture Fixes (THIS DOCUMENT)

**DO FIRST** - before SWIFTUI_AUDIT_PLAN.md:

1. ✅ **Create ImportService.swift** (Services/)
   - Centralize all file import logic
   - Implement importFiles() and importFolder()
   - Add progress tracking
   - Add error handling

2. ✅ **Reorganize folder structure**
   - Move stores to Services/
   - Move utilities to Utilities/
   - Update all imports
   - Test build

3. ✅ **Fix toolbar jumping**
   - Remove toolbars from child views
   - Create unified toolbar in ContentView
   - Test all view mode transitions

4. ✅ **Refactor FicheroApp.swift**
   - Remove NSOpenPanel logic
   - Add @State for file importers
   - Use SwiftUI .fileImporter()
   - Inject ImportService

### Phase 1-4: SwiftUI Cleanup (SWIFTUI_AUDIT_PLAN.md)

**DO SECOND** - after architecture is fixed:

1. Phase 1: Critical AppKit removals
2. Phase 2: Anti-pattern fixes
3. Phase 3: Task cancellation
4. Phase 4: SwiftLint cleanup

---

## Validation Checklist

After Phase 0 (Architecture Fixes):

- [ ] ImportService.swift exists in Services/
- [ ] All file import goes through ImportService
- [ ] No import logic in FicheroApp.swift
- [ ] No import logic in ContentView.swift
- [ ] DocumentStore only handles document CRUD
- [ ] Folder structure matches plan above
- [ ] All imports updated and working
- [ ] Toolbar doesn't jump when switching modes
- [ ] Clean build with no errors
- [ ] File import still works (test manually)
- [ ] Folder import still works (test manually)
- [ ] Drag-and-drop still works (test manually)

After Phase 1-4 (SwiftUI Cleanup):

- [ ] All items from SWIFTUI_AUDIT_PLAN.md checklist

---

## Why This Order Matters

**Architecture First:**
- Fixes fundamental design flaws
- Makes SwiftUI fixes cleaner
- Easier to test
- Better separation of concerns

**SwiftUI Second:**
- Fixes code quality
- Removes AppKit
- Fixes anti-patterns
- Clean up linting

**If we do SwiftUI fixes first:**
- We'll still have scattered import logic
- We'll still have toolbar jumping
- We'll still have wrong folder organization
- We'll have to refactor again later

---

## Success Criteria

### Architecture (Phase 0)

1. ✅ **Single Import Source**: All import through ImportService
2. ✅ **Proper Folder Structure**: Models/Services/Utilities/App
3. ✅ **No Toolbar Jumping**: Smooth transitions between modes
4. ✅ **Pure UI Layer**: No business logic in views

### Code Quality (Phase 1-4)

1. ✅ **No AppKit**: 100% SwiftUI (except unavoidable)
2. ✅ **No Anti-patterns**: No DispatchQueue.main, NotificationCenter, NSLog
3. ✅ **Task Cancellation**: All .task{} blocks handle cancellation
4. ✅ **SwiftLint Clean**: 0 warnings

---

## Time Estimates

| Phase | Tasks | Time | Risk |
|-------|-------|------|------|
| **Phase 0: Architecture** | 4 major refactors | 4-6 hours | MEDIUM-HIGH |
| - Create ImportService | New file + tests | 1-2 hours | MEDIUM |
| - Reorganize folders | Move files + imports | 1 hour | LOW |
| - Fix toolbar jumping | Refactor toolbar code | 1-2 hours | MEDIUM |
| - Refactor FicheroApp | fileImporter migration | 1-2 hours | MEDIUM |
| **Phase 1-4: SwiftUI** | Code quality fixes | 4-6 hours | MEDIUM |
| **TOTAL** | Architecture + Quality | **8-12 hours** | **MEDIUM-HIGH** |

---

## References

- **Backend Ingest API**: `docs/ingest_api.md`
- **SwiftUI Principles**: `ai/contexts/frontend/SWIFTUI_PRINCIPLES.md`
- **SwiftUI Audit Plan**: `SWIFTUI_AUDIT_PLAN.md` (DO SECOND)
- **Project Architecture**: `CLAUDE.md`

---

**Created By:** Claude Code
**Last Updated:** 2025-12-30
**Status:** Ready for Phase 0 implementation
**Next Step:** Review with user, then start Phase 0
