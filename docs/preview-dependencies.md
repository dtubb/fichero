# SwiftUI Preview Dependencies Guide

**Last Updated:** 2026-02-18

This guide documents required `@EnvironmentObject` dependencies for each view category in the Fichero app.

---

## Prerequisites

**Backend Required:** YES

```bash
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765
```

All services connect to `localhost:8765`. Previews will timeout without the backend running.

---

## Architecture Overview

```
AppState (global singleton)
  ├── ProviderService
  ├── MCPService
  └── ModelService

LibraryManager (singleton)
  └── LibraryReference (per library)
      ├── APIClient
      ├── FicheroClient
      ├── DocumentStore
      ├── WorkflowStore
      ├── SearchServiceGenerated
      ├── ChatServiceGenerated
      ├── ConversationServiceGenerated
      ├── WorkflowServiceGenerated
      ├── WorkflowStreamService
      ├── StorageServiceGenerated
      ├── ActivityServiceGenerated
      ├── AutomationServiceGenerated
      ├── BatchServiceGenerated
      ├── ArtifactServiceGenerated
      ├── ImportServiceGenerated
      ├── DocumentServiceGenerated
      ├── SavedSearchServiceGenerated
      ├── ModelServiceGenerated
      └── ChainService

ContentView (per window)
  ├── ViewSettings
  ├── AppState (@EnvironmentObject)
  ├── DocumentStore (@EnvironmentObject)
  └── All library services via @EnvironmentObject
```

---

## View Categories & Dependencies

### 1. Library Views

**Examples:** LibraryView, DocumentInspector, EditorView, ArtifactsBrowserView

**Required Environment Objects:**
```swift
@EnvironmentObject var libraryManager: LibraryManager
@EnvironmentObject var documentStore: DocumentStore
@EnvironmentObject var artifactService: ArtifactServiceGenerated  // For DocumentInspector
@EnvironmentObject var storageService: StorageServiceGenerated    // For image views
```

**Preview Pattern:**
```swift
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    LibraryView(
        documents: [],
        selection: .constant([]),
        detailDocument: .constant(nil),
        viewMode: .constant(.icons),
        displayMode: .icon
    )
    .environmentObject(libraryManager)
    .environmentObject(library.documentStore)
    .frame(width: 800, height: 600)
}
```

**Special Cases:**
- **DocumentInspector:** Needs `ArtifactServiceGenerated`
- **LibraryImageView:** Needs `StorageServiceGenerated`
- **ImageViewerComponents:** Needs `StorageServiceGenerated`

---

### 2. Chat Views

**Examples:** ChatView, ChatInspector, MessageBubble

**Required Environment Objects:**
```swift
@EnvironmentObject var chatService: ChatServiceGenerated
@EnvironmentObject var conversationService: ConversationServiceGenerated
@EnvironmentObject var documentStore: DocumentStore  // For document scope
```

**Preview Pattern:**
```swift
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    ChatView(
        conversation: nil,
        selectedDocuments: .constant([]),
        displayMode: .list
    )
    .environmentObject(library.chatServiceGenerated)
    .environmentObject(library.conversationServiceGenerated)
    .environmentObject(library.documentStore)
    .frame(width: 800, height: 600)
}
```

**Note:** Chat views have 100% preview coverage - use as reference!

---

### 3. Workflow Views

**Examples:** WorkflowEditor, WorkflowCanvasView, NodePopover, WorkflowInspector

**Required Environment Objects:**
```swift
@EnvironmentObject var workflowStore: WorkflowStore
@EnvironmentObject var workflowServiceGenerated: WorkflowServiceGenerated
@EnvironmentObject var workflowStreamService: WorkflowStreamService
@EnvironmentObject var documentStore: DocumentStore
@EnvironmentObject var libraryManager: LibraryManager
@Environment(WorkflowExecutionObserver.self) var executionObserver  // Note: .environment()
```

**Preview Pattern:**
```swift
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!
    let executionObserver = WorkflowExecutionObserver()

    WorkflowEditor(
        workflow: nil,
        editingWorkflow: .constant(Workflow(name: "Test", description: "")),
        displayMode: .map
    )
    .environmentObject(library.workflowStore)
    .environmentObject(library.workflowServiceGenerated)
    .environmentObject(library.workflowStreamService)
    .environmentObject(library.documentStore)
    .environmentObject(libraryManager)
    .environment(executionObserver)
    .frame(width: 1000, height: 700)
}
```

**Special Case - NodePopover (1,136 lines):**
```swift
// NodePopover needs MANY services:
.environmentObject(library.chatServiceGenerated)
.environmentObject(library.documentStore)
.environmentObject(library.savedSearchServiceGenerated)
.environmentObject(library.workflowServiceGenerated)
```

---

### 4. Sidebar Views

**Examples:** SidebarView, LibrarySidebarContent, ChatSidebarContent

**Required Environment Objects:**
```swift
@EnvironmentObject var windowState: WindowState
@EnvironmentObject var libraryManager: LibraryManager
@EnvironmentObject var documentStore: DocumentStore
// Plus mode-specific services
```

**Preview Pattern:**
```swift
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    LibrarySidebarContent(
        selectedItemId: .constant(nil),
        libraryManager: libraryManager,
        sidebarState: SidebarState(),
        renameState: RenameStateManager(),
        deleteState: DeleteStateManager(),
        cachedLibraryHeaders: []
    )
    .environmentObject(WindowState(libraryId: LibraryManager.globalLibraryId))
    .environmentObject(library.documentStore)
    .frame(width: 280, height: 500)
}
```

---

### 5. Activity Views

**Examples:** ActivityDetailView, ActivityProgressView, ActivityLogView

**Required Environment Objects:**
```swift
@EnvironmentObject var activityService: ActivityServiceGenerated
```

**Preview Pattern:**
```swift
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    ActivityDetailView(activity: mockActivity)
        .environmentObject(library.activityServiceGenerated)
        .frame(width: 800, height: 600)
}
```

**Mock Activity:**
```swift
let mockActivity = Activity(
    id: UUID().uuidString,
    type: .workflow,
    status: .running,
    startTime: Date(),
    progress: 0.5
)
```

**Note:** 90% of Activity views lack previews - HIGH PRIORITY

---

### 6. Automation Views

**Examples:** ScheduleDetailView, TriggerDetailView, ScheduleEditorView

**Required Environment Objects:**
```swift
@EnvironmentObject var automationService: AutomationServiceGenerated
@EnvironmentObject var workflowStore: WorkflowStore  // For editors
```

**Preview Pattern:**
```swift
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    ScheduleDetailView(schedule: mockSchedule)
        .environmentObject(library.automationServiceGenerated)
        .frame(width: 600, height: 500)
}
```

**Note:** ScheduleEditorView and TriggerEditorView have commented-out previews

---

### 7. Batch Views

**Examples:** BatchDetailView

**Required Environment Objects:**
```swift
@EnvironmentObject var batchService: BatchServiceGenerated
```

**Preview Pattern:**
```swift
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    BatchDetailView(batch: mockBatch)
        .environmentObject(library.batchServiceGenerated)
        .frame(width: 800, height: 600)
}
```

---

### 8. AI Provider Views

**Examples:** ProvidersView, AddProviderSheet, AIModelSelectionView

**Required Environment Objects:**
```swift
@EnvironmentObject var appState: AppState
@EnvironmentObject var providerService: ProviderServiceGenerated
```

**Preview Pattern:**
```swift
#Preview {
    let appState = AppState()
    appState.providers = []  // Mock provider data

    ProvidersView()
        .environmentObject(appState)
        .environmentObject(appState.providerService)
        .frame(width: 600, height: 400)
}
```

**Note:** AppState is global, not per-library

---

### 9. MCP Server Views

**Examples:** MCPServersView, MCPToolsCatalogView, AddMCPServerSheet

**Required Environment Objects:**
```swift
@EnvironmentObject var appState: AppState
@EnvironmentObject var mcpService: MCPService
```

**Preview Pattern:**
```swift
#Preview {
    let appState = AppState()

    MCPServersView()
        .environmentObject(appState)
        .environmentObject(appState.mcpService)
        .frame(width: 600, height: 500)
}
```

**Note:** 100% of MCP views lack previews - CRITICAL PRIORITY

---

### 10. Search Views

**Examples:** SearchView

**Required Environment Objects:**
```swift
@EnvironmentObject var searchService: SearchServiceGenerated
@EnvironmentObject var savedSearchService: SavedSearchServiceGenerated
```

**Preview Pattern:**
```swift
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    SearchView()
        .environmentObject(library.searchServiceGenerated)
        .environmentObject(library.savedSearchServiceGenerated)
        .frame(width: 800, height: 600)
}
```

---

### 11. Settings Views

**Examples:** SettingsView

**Required Environment Objects:**
```swift
@EnvironmentObject var appState: AppState
// Plus potentially many service-specific settings
```

**Preview Pattern:**
```swift
#Preview {
    let appState = AppState()

    SettingsView()
        .environmentObject(appState)
        .frame(width: 700, height: 500)
}
```

---

### 12. Simple Component Views

**Examples:** StatusBadge, ProviderLogoView, BackendConnectionView

**Required Environment Objects:**
Usually none or minimal

**Preview Pattern:**
```swift
#Preview {
    VStack(spacing: 20) {
        StatusBadge(status: .pending)
        StatusBadge(status: .processing)
        StatusBadge(status: .completed)
        StatusBadge(status: .failed)
    }
    .padding()
}
```

**Note:** These are the easiest to add previews to!

---

## Common Dependency Patterns

### Pattern A: Library Services Only

```swift
let libraryManager = LibraryManager.shared
let library = libraryManager.globalLibrary!

MyView()
    .environmentObject(library.documentStore)
    .environmentObject(library.workflowStore)
```

**Use for:** Library, Workflow, Chat, Search views

---

### Pattern B: App-Wide Services

```swift
let appState = AppState()

MyView()
    .environmentObject(appState)
    .environmentObject(appState.providerService)
```

**Use for:** Providers, MCP Servers, Settings views

---

### Pattern C: Mixed (Library + App)

```swift
let libraryManager = LibraryManager.shared
let library = libraryManager.globalLibrary!
let appState = AppState()

MyView()
    .environmentObject(libraryManager)
    .environmentObject(library.documentStore)
    .environmentObject(appState)
```

**Use for:** Complex views that need both library and app-wide state

---

## Observable vs ObservableObject

**Important Distinction:**

```swift
// ObservableObject - Use .environmentObject()
@EnvironmentObject var documentStore: DocumentStore  // ObservableObject

// @Observable - Use .environment()
@Environment(WorkflowExecutionObserver.self) var executionObserver  // @Observable
```

**Key Classes:**
- **ObservableObject:** DocumentStore, WorkflowStore, all `*ServiceGenerated` classes, AppState
- **@Observable:** WorkflowExecutionObserver

---

## Dependency Quick Reference

| View Category | Primary Dependencies |
|---------------|---------------------|
| Library | LibraryManager, DocumentStore |
| Chat | ChatServiceGenerated, ConversationServiceGenerated |
| Workflow | WorkflowStore, WorkflowServiceGenerated, WorkflowStreamService, WorkflowExecutionObserver |
| Sidebar | WindowState, LibraryManager, DocumentStore |
| Activity | ActivityServiceGenerated |
| Automation | AutomationServiceGenerated, WorkflowStore |
| Batch | BatchServiceGenerated |
| AI Providers | AppState, ProviderServiceGenerated |
| MCP Servers | AppState, MCPService |
| Search | SearchServiceGenerated, SavedSearchServiceGenerated |
| Settings | AppState |
| Components | Usually none |

---

## Troubleshooting

### Preview crashes with "Missing EnvironmentObject"

**Fix:** Add the missing environment object:
```swift
.environmentObject(library.serviceName)
```

### Preview times out during preflight

**Cause:** Backend not running

**Fix:** Start backend:
```bash
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765
```

### "Cannot find 'LibraryManager' in scope"

**Cause:** Missing import

**Fix:** Add at top of file:
```swift
import Foundation  // For LibraryManager
```

### Preview shows wrong data

**Cause:** Services are connecting to live backend with real data

**Solution:** This is expected! Backend provides the data. To test with specific data, mock the service or use `.constant()` bindings.

---

## Complete Example

Here's a complete preview with all common dependencies:

```swift
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!
    let appState = AppState()
    let executionObserver = WorkflowExecutionObserver()

    MyComplexView()
        // Library services
        .environmentObject(libraryManager)
        .environmentObject(library.documentStore)
        .environmentObject(library.workflowStore)

        // Generated services
        .environmentObject(library.chatServiceGenerated)
        .environmentObject(library.conversationServiceGenerated)
        .environmentObject(library.workflowServiceGenerated)
        .environmentObject(library.workflowStreamService)
        .environmentObject(library.searchServiceGenerated)
        .environmentObject(library.storageServiceGenerated)
        .environmentObject(library.activityServiceGenerated)
        .environmentObject(library.automationServiceGenerated)
        .environmentObject(library.batchServiceGenerated)
        .environmentObject(library.artifactServiceGenerated)

        // App-wide
        .environmentObject(appState)

        // Observable (not ObservableObject)
        .environment(executionObserver)

        .frame(width: 1000, height: 700)
}
```

---

**Last Updated:** 2026-02-18
**Generated by:** Agent team dependency analysis
