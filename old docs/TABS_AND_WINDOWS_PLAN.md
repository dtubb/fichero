# Tabs and Multiple Windows Plan

**Date:** 2025-12-30
**Priority:** Phase 0.5 (After ARCHITECTURE_FIXES.md, before backend integrations)
**Goal:** Native macOS tabs and multiple windows support

---

## Current State ❌

**Single Window, Single View**
- One WindowGroup with ContentView
- User can only see one mode at a time (Library OR Workflow OR Chat)
- Can't compare views side-by-side
- Can't open multiple documents
- Not using native macOS window management

**Issues:**
- Poor multitasking UX
- Can't reference one view while working in another
- Not utilizing macOS strengths

---

## Desired State ✅

**Multiple Tabs + Multiple Windows**

User can:
- ✅ Open multiple tabs in same window
  - Tab 1: Library view
  - Tab 2: Workflow editor
  - Tab 3: Chat conversation
  - Tab 4: Another library collection

- ✅ Open multiple windows
  - Window 1: Main library
  - Window 2: Workflow editor (full screen on second monitor)
  - Window 3: Chat (floating window)

- ✅ Native macOS tab bar
  - ⌘T for new tab
  - ⌘W to close tab
  - ⌘{ and ⌘} to switch tabs
  - Drag tabs to reorder or tear off to new window

---

## SwiftUI Architecture Options

### Option 1: DocumentGroup (Document-Based App) ⭐ RECOMMENDED

**Best for apps where each window/tab represents a "document"**

```swift
@main
struct FicheroApp: App {
    var body: some Scene {
        DocumentGroup(viewing: FicheroDocument.self) { file in
            DocumentView(document: file.document)
        }

        // Settings window
        Settings {
            SettingsView()
        }
    }
}

struct FicheroDocument: FileDocument {
    static var readableContentTypes: [UTType] = [.json]

    var viewMode: ViewMode  // .library, .workflow, .chat
    var context: ViewContext  // What to display

    init() {
        self.viewMode = .library
        self.context = .root
    }

    init(configuration: ReadConfiguration) throws {
        // Load document from file
    }

    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        // Save document to file
    }
}
```

**Pros:**
- ✅ Native macOS document management
- ✅ Automatic save/restore of window state
- ✅ Native tabs (⌘T, ⌘W work automatically)
- ✅ Version browsing
- ✅ iCloud sync support
- ✅ Autosave
- ✅ Multiple windows automatically supported

**Cons:**
- ⚠️ Each tab/window must represent a saveable "document"
- ⚠️ More complex state management

### Option 2: Multiple WindowGroups ⚠️ NOT RECOMMENDED

```swift
@main
struct FicheroApp: App {
    var body: some Scene {
        WindowGroup("Library") {
            LibraryRootView()
        }

        WindowGroup("Workflows") {
            WorkflowRootView()
        }

        WindowGroup("Chat") {
            ChatRootView()
        }
    }
}
```

**Pros:**
- ✅ Simple implementation
- ✅ Each window type is separate

**Cons:**
- ❌ No tabs within windows
- ❌ State sharing is complex
- ❌ User can't create new tabs easily
- ❌ Not standard macOS UX

### Option 3: WindowGroup with TabView ⚠️ NOT RECOMMENDED

```swift
WindowGroup {
    TabView {
        LibraryView()
            .tabItem { Label("Library", systemImage: "folder") }

        WorkflowView()
            .tabItem { Label("Workflows", systemImage: "arrow.triangle.branch") }

        ChatView()
            .tabItem { Label("Chat", systemImage: "bubble.left.and.bubble.right") }
    }
}
```

**Pros:**
- ✅ Simple tabs

**Cons:**
- ❌ Fixed tabs (can't add/remove)
- ❌ Not native macOS tabs
- ❌ Can't tear off tabs
- ❌ iOS-style, not macOS-style

---

## Recommended Solution: DocumentGroup

### Architecture

Each "document" in Fichero represents a **view session**:

```swift
// Fichero/Fichero/Models/FicheroDocument.swift
import SwiftUI
import UniformTypeIdentifiers

/// A Fichero view session - can be saved/restored
struct FicheroDocument: FileDocument, Codable {
    static var readableContentTypes: [UTType] = [.ficheroSession]

    // View state
    var viewMode: ViewMode
    var sessionId: UUID

    // Mode-specific context
    var libraryContext: LibraryContext?
    var workflowContext: WorkflowContext?
    var chatContext: ChatContext?

    // Timestamp
    var createdAt: Date
    var lastModified: Date

    // MARK: - FileDocument

    init() {
        self.sessionId = UUID()
        self.viewMode = .library(nil)
        self.createdAt = Date()
        self.lastModified = Date()
    }

    init(configuration: ReadConfiguration) throws {
        guard let data = configuration.file.regularFileContents else {
            throw CocoaError(.fileReadCorruptFile)
        }
        self = try JSONDecoder().decode(FicheroDocument.self, from: data)
    }

    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        let data = try JSONEncoder().encode(self)
        return FileWrapper(regularFileWithContents: data)
    }
}

// Define custom UTType
extension UTType {
    static var ficheroSession: UTType {
        UTType(exportedAs: "ca.tubb.fichero.session")
    }
}

// Context types
struct LibraryContext: Codable {
    var selectedCollectionId: String?
    var selectedDocumentIds: Set<String>
    var viewLayout: LibraryLayout
}

struct WorkflowContext: Codable {
    var workflowId: String
    var canvasPosition: CGPoint
    var zoom: CGFloat
}

struct ChatContext: Codable {
    var conversationId: String
    var selectedDocuments: Set<String>
}
```

### Updated App Structure

```swift
// Fichero/Fichero/FicheroApp.swift
import SwiftUI

@main
struct FicheroApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        // Main document-based interface
        DocumentGroup(viewing: FicheroDocument.self) { file in
            DocumentTabView(document: file.$document)
                .environmentObject(appState)
        }
        .commands {
            // File menu
            CommandGroup(replacing: .newItem) {
                Button("New Library Tab") {
                    // Creates new document with library view
                    newDocument(mode: .library)
                }
                .keyboardShortcut("n", modifiers: [.command])

                Button("New Workflow Tab") {
                    newDocument(mode: .workflow)
                }
                .keyboardShortcut("n", modifiers: [.command, .shift])

                Button("New Chat Tab") {
                    newDocument(mode: .chat)
                }
                .keyboardShortcut("n", modifiers: [.command, .option])

                Divider()

                // Import commands stay the same
            }

            // Standard edit, view menus
            CommandGroup(after: .pasteboard) { ... }

            // Window menu (automatic tabs support)
            CommandGroup(after: .windowArrangement) {
                Button("Merge All Windows") {
                    // Native macOS functionality
                }
            }
        }
        .defaultSize(width: 1200, height: 800)

        // Settings window (not tabbed)
        Settings {
            SettingsView()
                .environmentObject(appState)
        }
    }

    private func newDocument(mode: ViewMode) {
        // SwiftUI handles document creation automatically
        // Just need to set initial mode
    }
}
```

### Document Tab View

```swift
// Fichero/Fichero/Views/DocumentTabView.swift
import SwiftUI

/// Main view for a document tab
struct DocumentTabView: View {
    @Binding var document: FicheroDocument
    @EnvironmentObject var appState: AppState

    // Services
    @StateObject private var documentStore = DocumentStore()
    @StateObject private var workflowStore = WorkflowStore()
    @StateObject private var conversationService = ConversationService()

    var body: some View {
        Group {
            if appState.isBackendRunning {
                contentView
            } else {
                BackendConnectionView(appState: appState)
            }
        }
        .task {
            // Load data for this tab's context
            await loadContext()
        }
        .onChange(of: document.viewMode) { _, newMode in
            // Save document when view mode changes
            document.lastModified = Date()
        }
    }

    @ViewBuilder
    private var contentView: some View {
        switch document.viewMode {
        case .library:
            LibraryTabView(
                document: $document,
                documentStore: documentStore
            )

        case .workflow:
            WorkflowTabView(
                document: $document,
                workflowStore: workflowStore
            )

        case .chat:
            ChatTabView(
                document: $document,
                conversationService: conversationService
            )

        case .search:
            SearchTabView(
                document: $document
            )
        }
    }

    private func loadContext() async {
        // Load appropriate data based on document.viewMode
        switch document.viewMode {
        case .library:
            if let context = document.libraryContext {
                await documentStore.loadCollection(context.selectedCollectionId)
            }
        case .workflow:
            if let context = document.workflowContext {
                await workflowStore.loadWorkflow(context.workflowId)
            }
        case .chat:
            if let context = document.chatContext {
                await conversationService.loadConversation(context.conversationId)
            }
        case .search:
            break
        }
    }
}
```

### Individual Tab Views

```swift
// Fichero/Fichero/Views/Tabs/LibraryTabView.swift
struct LibraryTabView: View {
    @Binding var document: FicheroDocument
    @ObservedObject var documentStore: DocumentStore

    var body: some View {
        NavigationSplitView {
            // Sidebar
            LibrarySidebar(
                collections: documentStore.collections,
                selection: binding(for: \.libraryContext?.selectedCollectionId)
            )
        } content: {
            // Main content
            LibraryBrowser(
                documents: documentStore.currentDocuments,
                layout: binding(for: \.libraryContext?.viewLayout)
            )
        } detail: {
            // Detail/Inspector
            DocumentDetailView(
                document: selectedDocument
            )
        }
        .toolbar {
            libraryToolbar
        }
    }

    private func binding<T>(for keyPath: WritableKeyPath<FicheroDocument, T?>) -> Binding<T?> {
        Binding(
            get: { document[keyPath: keyPath] },
            set: {
                document[keyPath: keyPath] = $0
                document.lastModified = Date()
            }
        )
    }
}

// Similar for WorkflowTabView.swift, ChatTabView.swift, etc.
```

---

## User Experience

### Opening New Tabs

**⌘N - New Library Tab**
- Opens new tab with Library view
- Starts at root level
- Fresh selection state

**⌘⇧N - New Workflow Tab**
- Opens new tab with blank workflow
- Or prompts to select existing workflow

**⌘⌥N - New Chat Tab**
- Opens new tab with new conversation
- Or select existing conversation

### Tab Interactions

**⌘T - Duplicate Current Tab**
- Creates new tab with same view/context
- Useful for comparing two collections

**⌘W - Close Tab**
- Saves tab state automatically
- Warns if unsaved workflow changes

**⌘{ / ⌘} - Switch Tabs**
- Native macOS tab switching

**Drag Tab to New Window**
- Tears off tab into separate window
- Great for multi-monitor setups

### Window Management

**File > New Window**
- Opens new window with new Library tab
- Independent state from other windows

**Window > Merge All Windows**
- Combines all windows into tabs
- Native macOS feature

---

## Migration Plan

### Step 1: Create Document Model

1. Create `Models/FicheroDocument.swift`
2. Define view contexts (LibraryContext, WorkflowContext, etc.)
3. Implement Codable for save/restore
4. Add custom UTType for `.ficheroSession` files

### Step 2: Refactor App Structure

1. Change WindowGroup to DocumentGroup in FicheroApp.swift
2. Create DocumentTabView as main container
3. Update commands for tab creation

### Step 3: Create Tab Views

1. Extract LibraryTabView from ContentView
2. Create WorkflowTabView
3. Create ChatTabView
4. Create SearchTabView

### Step 4: State Management

1. Move shared state to appState
2. Move tab-specific state to FicheroDocument
3. Update bindings to save document on changes

### Step 5: Testing

1. Test creating multiple tabs
2. Test saving/restoring tab state
3. Test window management
4. Test multi-monitor workflows

---

## Benefits

### For Users
- ✅ **Better multitasking**: Work on workflow while referencing library
- ✅ **Multi-monitor support**: Workflow on main display, library on second
- ✅ **Session persistence**: Tabs restore on app relaunch
- ✅ **Native macOS UX**: Familiar keyboard shortcuts
- ✅ **Flexible workspace**: Arrange tabs/windows as needed

### For Development
- ✅ **Cleaner architecture**: Each tab is independent
- ✅ **State isolation**: Tab state doesn't interfere
- ✅ **Easier testing**: Test individual tab views
- ✅ **Better performance**: Inactive tabs can suspend work
- ✅ **Future-proof**: Easy to add new tab types

---

## Implementation Order

This is **Phase 0.5** - After ARCHITECTURE_FIXES.md, before backend integrations:

1. **Phase 0: Architecture Fixes** (ARCHITECTURE_FIXES.md)
   - ImportService
   - Folder reorganization
   - Toolbar unification

2. **Phase 0.5: Tabs & Windows** (THIS DOCUMENT) ← **DO SECOND**
   - Create FicheroDocument model
   - Refactor to DocumentGroup
   - Create tab views
   - Test multi-window workflows

3. **Phase 1: Backend Integrations** (BACKEND_COVERAGE_AUDIT.md)
   - DocumentService
   - StorageService
   - Enhanced services

4. **Phase 2: GUI Organization**
   - Code organization
   - View refactoring

5. **Phase 3: AppKit Removal** (SWIFTUI_AUDIT_PLAN.md)
   - Remove NSOpenPanel
   - Remove NSAlert
   - SwiftLint cleanup

---

## Files to Create

```
Models/
├── FicheroDocument.swift ← CREATE (document model)
├── ViewContexts.swift ← CREATE (LibraryContext, WorkflowContext, etc.)

Views/
├── DocumentTabView.swift ← CREATE (main tab container)
└── Tabs/
    ├── LibraryTabView.swift ← REFACTOR from ContentView
    ├── WorkflowTabView.swift ← REFACTOR from ContentView
    ├── ChatTabView.swift ← REFACTOR from ContentView
    └── SearchTabView.swift ← CREATE

App/
├── FicheroApp.swift ← UPDATE to DocumentGroup
├── AppState.swift ← UPDATE for multi-tab state
└── ViewSettings.swift ← UPDATE for per-tab settings
```

---

## Success Criteria

- [ ] User can create new Library tab with ⌘N
- [ ] User can create new Workflow tab with ⌘⇧N
- [ ] User can create new Chat tab with ⌘⌥N
- [ ] Tabs show appropriate icons and titles
- [ ] ⌘W closes current tab
- [ ] ⌘{ / ⌘} switches between tabs
- [ ] Drag tab to new window works
- [ ] Multiple windows can be open simultaneously
- [ ] Tab state persists across app relaunches
- [ ] Window > Merge All Windows combines windows
- [ ] Each tab has independent state
- [ ] Backend connection shared across all tabs
- [ ] Clean build with no errors

---

**Created By:** Claude Code
**Last Updated:** 2025-12-30
**Status:** Ready for Phase 0.5 implementation
**Dependencies:** Requires Phase 0 (ARCHITECTURE_FIXES.md) to be complete first
