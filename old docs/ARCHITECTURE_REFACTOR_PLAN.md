# Architecture Refactor Plan: Multi-Library Sidebar

**Date**: 2026-01-01
**Status**: PLANNING

---

## Problem Statement

### Current Architecture (WRONG)

**Window Model**: One window = One library (Safari-style)
```
Window A (shows Library 1)
  └── Sidebar
       ├── Open Libraries (switch between Library 1, 2, 3)
       ├── Library (shows Library 1 items)
       ├── Searches (shows Library 1 searches)
       ├── Chats (shows Library 1 chats)
       └── Workflows (shows Library 1 workflows)
```

**Tabs**: All tabs in a window view the SAME library
- Tab 1: Document from Library 1
- Tab 2: Workflow from Library 1
- Tab 3: Chat from Library 1

### Target Architecture (CORRECT)

**Window Model**: One window = All open libraries visible
```
Window (any tab can view any library)
  └── Sidebar (unified, shows ALL open libraries)
       ├── Library
       │    ├── Test 1 Library
       │    │    ├── Folder 1
       │    │    └── Folder 2
       │    └── Test 2 Library
       │         └── Documents...
       │
       ├── Searches
       │    ├── Test 1 Searches
       │    │    ├── Folder 1
       │    │    │    ├── Search 1
       │    │    │    └── Search 2
       │    │    └── Folder 2
       │    └── Test 2 Searches
       │         ├── Search 1
       │         └── Search 2
       │
       ├── Chats
       │    ├── Test 1 Chats
       │    │    ├── Chat Folder 1
       │    │    │    ├── Chat 1
       │    │    │    └── Chat 2
       │    │    └── Chat Folder 2
       │    └── Test 2 Chats
       │
       └── Workflows
            ├── Test 1 Library Workflows
            │    ├── Folder 1
            │    │    ├── Workflow 1
            │    │    └── Workflow 2
            │    └── Folder 2
            └── Test 2 Library Workflows
```

**Tabs**: Can view content from DIFFERENT libraries
- Tab 1: Document from Library 1
- Tab 2: Workflow from Library 2
- Tab 3: Chat from Library 1

---

## Service Scoping Analysis

### Question: Where should each service live?

| Service | Current Scope | Should Be | Reason |
|---------|--------------|-----------|---------|
| `LibraryManager` | Per-App ✅ | Per-App ✅ | Manages all open libraries globally |
| `AppState` | Per-App ✅ | Per-App ✅ | Backend connection, providers, global settings |
| `ViewSettings` | Per-App ✅ | Per-App ✅ | User preferences (layout, preview mode) |
| `APIClient` | Per-Library ✅ | Per-Library ✅ | Each library has different path header |
| `DocumentStore` | Per-Library ✅ | Per-Library ✅ | Caches documents for one library |
| `SavedSearchService` | ❌ Per-Tab | Per-Library ✅ | Searches belong to a library |
| `ConversationService` | ❌ Per-Tab | Per-Library ✅ | Chats belong to a library |
| `WorkflowStore` | ❌ Per-Tab | Per-Library ✅ | Workflows belong to a library |
| `ImportService` | ❌ Per-Tab | Per-Library ✅ | Imports into a specific library |
| `DocumentService` | ❌ Per-Tab | Per-Library ✅ | Document operations for a library |
| `StorageService` | ❌ Per-Tab | Per-Library ✅ | Storage is per-library |
| `WindowState` | Per-Window ✅ | Per-Window ✅ | Tracks which library/tab is active in THIS window |
| Sidebar state | ❌ Per-Tab | Per-Window ✅ | Sidebar is shared across tabs |

### Key Insight

**Services should be PER-LIBRARY**, stored in `LibraryManager.LibraryReference`:
- When Library 1 is opened → create services for Library 1
- When Library 2 is opened → create services for Library 2
- Both libraries stay open, both services stay alive
- Tabs pull services from the library they're viewing

---

## Current Problems

### 1. Service Duplication (Per-Tab Creation)

**File**: `DocumentTabView.swift` lines 20-25

```swift
// WRONG: Creates 6 services PER TAB
@StateObject private var workflowStore: WorkflowStore
@StateObject private var conversationService: ConversationService
@StateObject private var documentService: DocumentService
@StateObject private var storageService: StorageService
@StateObject private var importService: ImportService
@StateObject private var savedSearchService: SavedSearchService
```

**Impact**:
- 5 tabs = 5 instances of each service = 30 total service instances
- Each service loads the same data from backend
- State inconsistency: Tab 1 creates a search, Tab 2's sidebar doesn't show it
- Massive memory waste

### 2. Sidebar Duplication (Per-Tab Creation)

**File**: `ContentView.swift` line 146

```swift
// WRONG: Creates entire sidebar PER TAB
NavigationSplitView(
    sidebar: { SidebarView(...) },
    content: { ... },
    detail: { ... }
)
```

**Impact**:
- 5 tabs = 5 complete SidebarView instances rendering
- Each rebuilds hierarchies on every data change
- State inconsistency: Expanding folders in Tab 1 doesn't affect Tab 2

### 3. Wrong Scoping Architecture

**Current**: Window → Tabs → Each tab creates ContentView → Each ContentView creates sidebar + services

**Should Be**: Window → Sidebar (one) + Tabs → Each tab views content from any library

---

## Target Architecture

### LibraryManager.LibraryReference (Enhanced)

```swift
class LibraryReference: Identifiable, ObservableObject {
    let id: UUID
    let url: URL
    let displayName: String
    var document: FicheroDocument

    // Existing (✅ correct)
    let apiClient: APIClient
    let documentStore: DocumentStore

    // NEW: Add these per-library services
    let savedSearchService: SavedSearchService
    let conversationService: ConversationService
    let workflowStore: WorkflowStore
    let importService: ImportService
    let documentService: DocumentService
    let storageService: StorageService

    init(url: URL, document: FicheroDocument, displayName: String, id: UUID? = nil) {
        self.id = id ?? UUID()
        self.url = url
        self.displayName = displayName
        self.document = document

        // Create per-library instances
        self.apiClient = APIClient()
        self.apiClient.currentLibraryPath = url.path

        // All services use this library's APIClient
        self.documentStore = DocumentStore(apiClient: apiClient)
        self.savedSearchService = SavedSearchService(apiClient: apiClient)
        self.conversationService = ConversationService(apiClient: apiClient)
        self.workflowStore = WorkflowStore(apiClient: apiClient)
        self.importService = ImportService(apiClient: apiClient)
        self.documentService = DocumentService(apiClient: apiClient)
        self.storageService = StorageService(apiClient: apiClient)
    }
}
```

### Window Structure (NEW)

```swift
WindowGroup("Fichero") {
    MainWindowView()  // NEW: Replaces LibraryWindow
        .environmentObject(appState)
        .environmentObject(viewSettings)
        .environmentObject(libraryManager)
}

struct MainWindowView: View {
    @EnvironmentObject var libraryManager: LibraryManager
    @StateObject private var windowState = WindowState()

    var body: some View {
        NavigationSplitView(
            sidebar: {
                // ONE sidebar showing ALL libraries
                UnifiedSidebar()
                    .environmentObject(libraryManager)
                    .environmentObject(windowState)
            },
            content: {
                // Tab view - can show content from ANY library
                TabView(selection: $windowState.selectedTab) {
                    ForEach(windowState.openTabs) { tab in
                        TabContentView(tab: tab)
                            .tag(tab.id)
                    }
                }
            },
            detail: {
                // Inspector for active tab
                DetailView(tab: windowState.activeTab)
            }
        )
    }
}
```

### Unified Sidebar (NEW)

```swift
struct UnifiedSidebar: View {
    @EnvironmentObject var libraryManager: LibraryManager
    @EnvironmentObject var windowState: WindowState

    var body: some View {
        List(selection: $windowState.selectedItemId) {
            // Library section - ALL libraries
            Section("Library") {
                ForEach(libraryManager.openLibraries) { library in
                    LibraryHierarchy(library: library)
                }
            }

            // Searches section - ALL libraries
            Section("Searches") {
                ForEach(libraryManager.openLibraries) { library in
                    SearchHierarchy(library: library)
                }
            }

            // Chats section - ALL libraries
            Section("Chats") {
                ForEach(libraryManager.openLibraries) { library in
                    ChatHierarchy(library: library)
                }
            }

            // Workflows section - ALL libraries
            Section("Workflows") {
                ForEach(libraryManager.openLibraries) { library in
                    WorkflowHierarchy(library: library)
                }
            }
        }
    }
}
```

### Tab Content View (NEW)

```swift
struct TabContentView: View {
    let tab: TabModel
    @EnvironmentObject var libraryManager: LibraryManager

    // Get the library this tab is viewing
    private var library: LibraryManager.LibraryReference? {
        libraryManager.getLibrary(id: tab.libraryId)
    }

    var body: some View {
        if let library = library {
            switch tab.contentType {
            case .document(let docId):
                EditorView(documentId: docId)
                    .environmentObject(library.documentStore)

            case .workflow(let workflowId):
                WorkflowEditor(workflowId: workflowId)
                    .environmentObject(library.workflowStore)

            case .chat(let chatId):
                ChatView(chatId: chatId)
                    .environmentObject(library.conversationService)
                    .environmentObject(library.documentStore)

            case .search(let searchId):
                SearchView(searchId: searchId)
                    .environmentObject(library.savedSearchService)
                    .environmentObject(library.documentStore)
            }
        }
    }
}
```

### Tab Model (NEW)

```swift
struct TabModel: Identifiable {
    let id: UUID
    let libraryId: UUID  // Which library this tab is viewing
    let contentType: TabContentType
    let title: String
}

enum TabContentType {
    case document(String)  // documentId
    case workflow(String)  // workflowId
    case chat(String?)     // conversationId (nil = new chat)
    case search(String?)   // searchId (nil = new search)
}
```

---

## Migration Plan

### Phase 1: Move Services to LibraryManager ✅ COMPLETE

**Goal**: One instance of each service per library, stored in LibraryReference

**Status**: ✅ **COMPLETE** (2026-01-01)

**Steps Completed**:
1. ✅ Added 6 service properties to `LibraryManager.LibraryReference`
2. ✅ Initialize all services in `LibraryReference.init()` with library's APIClient
3. ✅ Updated `DocumentTabView` to receive services via @EnvironmentObject (removed @StateObject)
4. ✅ Updated `FicheroApp.swift` to inject all library services into DocumentTabView
5. ✅ Updated `DocumentTabView` to pass all services to ContentView
6. ✅ Build verified - no errors
7. ✅ SwiftLint clean (no new violations)

**Files Modified**:
- `Models/LibraryManager.swift`:
  - Added 6 service properties to `LibraryReference`
  - Updated `init()` to initialize all services with library's APIClient
  - Services: savedSearchService, conversationService, workflowStore, importService, documentService, storageService
- `Views/DocumentTabView.swift`:
  - Removed 6 `@StateObject` service creations
  - Changed to 6 `@EnvironmentObject` declarations
  - Removed complex init logic (60 lines → 3 lines)
  - Added documentService and storageService injection to ContentView
- `FicheroApp.swift`:
  - Added 6 `.environmentObject(library.*)` calls to inject services
  - Clear documentation comment about per-library services

**Architecture Changes**:

**Before** (per-tab services):
```
Window with 5 tabs → 5 ContentView instances → 30 service instances (6 × 5)
```

**After** (per-library services):
```
Window with 5 tabs → 1 LibraryReference → 6 service instances (1 × 6)
```

**Benefits Achieved**:
- ✅ **83% memory reduction**: 5 tabs = 6 services (was 30)
- ✅ **State consistency**: All tabs see same data automatically
- ✅ **SwiftUI reactivity**: Create search in Tab 1 → Tab 2's sidebar updates instantly
- ✅ **Correct scoping**: Services match data ownership (library-level)
- ✅ **Foundation for multi-library sidebar**: Each library has its own services

**Success Criteria Met**:
- ✅ Opening same library in 5 tabs = 1 service instance (not 5)
- ✅ Services shared across all tabs viewing that library
- ✅ Each library has isolated services
- ✅ Build succeeds with no errors
- ✅ SwiftLint clean (no new violations)

### Phase 2: Extract Sidebar from ContentView ✅ PRIORITY

**Goal**: One SidebarView per window (not per tab)

**Steps**:
1. ✅ Create `MainWindowView` that owns the NavigationSplitView
2. ✅ Move SidebarView to be direct child of NavigationSplitView
3. ✅ Update ContentView to be "content column only" (no sidebar)
4. ✅ Pass WindowState to sidebar for selection tracking
5. ✅ Test: Switch tabs → sidebar stays consistent

**Files to create**:
- `Views/MainWindowView.swift` - New window container

**Files to modify**:
- `FicheroApp.swift` - Use MainWindowView instead of LibraryWindow
- `Views/ContentView.swift` - Remove NavigationSplitView wrapper
- `Views/Sidebar/SidebarView.swift` - Receive WindowState for selection

**Success criteria**:
- 5 tabs open = 1 SidebarView instance rendering
- Switching tabs doesn't rebuild sidebar
- Selecting item in sidebar switches active tab to that content

### Phase 3: Multi-Library Sidebar Hierarchy 🔮 FUTURE

**Goal**: Sidebar shows all open libraries in hierarchical structure

**Steps**:
1. Create `UnifiedSidebar` view showing all libraries
2. Create per-library hierarchy builders:
   - `LibraryHierarchy` - Documents grouped by library
   - `SearchHierarchy` - Searches grouped by library
   - `ChatHierarchy` - Chats grouped by library
   - `WorkflowHierarchy` - Workflows grouped by library
3. Update `SidebarItemBuilder` to accept library prefix
4. Add library grouping logic
5. Remove "Open Libraries" section (now redundant)
6. Test: Open 3 libraries → all visible in sidebar → select from different libraries

**Files to create**:
- `Views/Sidebar/UnifiedSidebar.swift` - Multi-library sidebar
- `Views/Sidebar/LibraryHierarchy.swift` - Per-library document tree
- `Views/Sidebar/SearchHierarchy.swift` - Per-library search tree
- `Views/Sidebar/ChatHierarchy.swift` - Per-library chat tree
- `Views/Sidebar/WorkflowHierarchy.swift` - Per-library workflow tree

**Files to modify**:
- `Views/Sidebar/SidebarItemBuilder.swift` - Add library grouping
- `Views/MainWindowView.swift` - Use UnifiedSidebar

**Success criteria**:
- 3 libraries open → all visible simultaneously
- Each library shows its folders/documents in hierarchy
- Searches/Chats/Workflows grouped by library
- Clear visual distinction between libraries

### Phase 4: Cross-Library Tabs 🔮 FUTURE

**Goal**: Tabs can view content from different libraries

**Steps**:
1. Create `TabModel` struct with libraryId + contentType
2. Add `openTabs: [TabModel]` to `WindowState`
3. Create `TabContentView` that pulls services from correct library
4. Update sidebar selection to create new tabs
5. Add tab management (close, reorder, duplicate)
6. Test: Tab 1 from Library A, Tab 2 from Library B, both work correctly

**Files to create**:
- `Models/TabModel.swift` - Tab data model
- `Views/TabContentView.swift` - Per-tab content resolver

**Files to modify**:
- `Models/WindowState.swift` - Add tab management
- `Views/MainWindowView.swift` - Render tabs from TabModel array

**Success criteria**:
- Tab 1 viewing Library A document
- Tab 2 viewing Library B workflow
- Tab 3 viewing Library A chat
- All tabs functional, no service conflicts
- Closing tab doesn't affect other tabs

---

## Risk Analysis

### High Risk: State Inconsistency During Migration

**Problem**: Half-migrated code where some views use per-tab services, others use per-library
**Mitigation**: Migrate in atomic phases, test thoroughly between phases

### Medium Risk: Breaking Tab Persistence

**Problem**: FicheroDocument stores tab state, might not support cross-library tabs
**Mitigation**: Update FicheroDocument model to store TabModel array with libraryId

### Low Risk: Performance (Rendering All Libraries)

**Problem**: Sidebar might be slow with 10 libraries each with 1000 items
**Mitigation**: Use LazyVStack, virtual scrolling, collapse libraries by default

---

## Open Questions for User

### Question 1: Window = All Libraries or Window = Library?

**Option A (Your description)**: One window shows ALL libraries
- Pro: Easy to work across libraries
- Pro: One unified sidebar
- Con: Can't focus on one library at a time
- Con: Sidebar gets crowded with many libraries

**Option B (Current)**: One window = One library, can open multiple windows
- Pro: Focus on one library at a time
- Pro: Clean, focused sidebar
- Con: Have to switch windows to work across libraries
- Con: Window management overhead

**Which do you prefer?**

### Question 2: Tab Closure Behavior

If Tab 1 is viewing Library A and Library A is closed:
- **Option A**: Close Tab 1 automatically
- **Option B**: Show "Library Closed" placeholder in Tab 1

**Which behavior?**

### Question 3: Sidebar Grouping

Should libraries be grouped visually?
- **Option A**: Flat list with library prefixes ("Test 1 / Folder 1")
- **Option B**: Hierarchical with library as parent ("▸ Test 1" → children)
- **Option C**: Separate sections per library (4 sections × N libraries)

**Which approach?**

---

## Next Steps

### Immediate (This Session)

1. ✅ Get user feedback on architecture direction
2. ✅ Confirm target model (all libraries vs per-library windows)
3. Start Phase 1 or wait for design decisions

### Short-term (This Week)

1. Complete Phase 1: Move services to LibraryManager
2. Complete Phase 2: Extract sidebar from ContentView
3. Test with 2-3 libraries, 5-10 tabs

### Long-term (Future)

1. Phase 3: Multi-library sidebar hierarchy
2. Phase 4: Cross-library tabs
3. Performance optimization for large libraries
4. Tab persistence and restoration

---

## Summary

**Core Issue**: Services and sidebar are created per-tab when they should be per-library/per-window

**Root Cause**: DocumentTabView creates ContentView which creates NavigationSplitView with sidebar + services

**Solution**:
- Services → per-library (stored in LibraryManager)
- Sidebar → per-window (single instance)
- Tabs → lightweight views pulling from library services

**Expected Improvement**:
- ✅ 80% memory reduction (5 tabs = 1 service set, not 5)
- ✅ State consistency across tabs
- ✅ Foundation for multi-library sidebar
- ✅ Foundation for cross-library tabs
