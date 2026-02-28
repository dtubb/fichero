# SwiftUI Preview Patterns & Examples

**Last Updated:** 2026-02-18

This document contains working preview patterns and examples from the Fichero codebase.

---

## Table of Contents

1. [Basic Patterns](#basic-patterns)
2. [Environment Object Patterns](#environment-object-patterns)
3. [Common Service Initialization](#common-service-initialization)
4. [Advanced Patterns](#advanced-patterns)
5. [Anti-Patterns to Avoid](#anti-patterns-to-avoid)

---

## Basic Patterns

### Simple View with No Dependencies

```swift
#Preview {
    BackendConnectionView(appState: AppState())
        .frame(width: 600, height: 400)
}
```

**Use when:**
- View has minimal or no `@EnvironmentObject` dependencies
- Can create dependencies inline
- No backend data needed

---

### View with `.constant()` Bindings

```swift
#Preview("Empty State") {
    LibraryView(
        documents: [],
        selection: .constant(Set<String>()),
        detailDocument: .constant(nil),
        viewMode: .constant(.icons),
        displayMode: .icon
    )
    .frame(width: 600, height: 500)
}

#Preview("With Documents") {
    LibraryView(
        documents: [
            Document(id: "1", name: "Test.pdf", docType: .file, fileType: .pdf),
            Document(id: "2", name: "Folder", docType: .folder)
        ],
        selection: .constant(Set<String>()),
        detailDocument: .constant(nil),
        viewMode: .constant(.list),
        displayMode: .list
    )
    .frame(width: 800, height: 600)
}
```

**Use when:**
- View accepts `@Binding` parameters
- You want to test different states (empty, populated, etc.)
- No interactive state updates needed in preview

**Pattern:**
- Use multiple `#Preview` blocks for different scenarios
- Name previews descriptively: "Empty State", "With Documents", "Error State"
- Provide realistic mock data

---

### View with @Previewable (Modern Approach)

```swift
#Preview {
    @Previewable @State var viewMode: ViewDisplayMode = .icon
    @Previewable @State var layoutMode: LayoutMode = .standard
    @Previewable @State var showSidebar: Bool = true
    @Previewable @State var searchText: String = ""

    let registry = ItemTypeRegistry()

    MainToolbar(
        viewMode: $viewMode,
        layoutMode: $layoutMode,
        showSidebar: $showSidebar,
        itemRegistry: registry,
        searchText: $searchText
    )
    .frame(height: 44)
    .onAppear {
        registry.createFolder = { print("Create folder") }
        registry.createSearch = { print("Create search") }
    }
}
```

**Use when:**
- Need mutable state in preview (iOS 17+/macOS 14+)
- Want to test interactive behavior
- Cleaner than PreviewWrapper pattern

**Advantages:**
- Flat code structure
- Real state management
- Interactive previews work

---

## Environment Object Patterns

### Pattern 1: Using LibraryManager.shared

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

**Use when:**
- View needs real service instances
- Backend is running
- Want to test with actual API calls

**Required:**
- Backend must be running on localhost:8765
- LibraryManager singleton provides global library by default

---

### Pattern 2: Custom Service Initialization

```swift
#Preview {
    let ficheroClient = FicheroClient(libraryPath: "/tmp/preview.fichero")

    return AgentConfigurationView(
        node: .constant(WorkflowNode(
            tool: "agent",
            label: "Test Agent",
            positionX: 100,
            positionY: 100
        ))
    )
    .environmentObject(WorkflowServiceGenerated(ficheroClient: ficheroClient))
    .frame(width: 600, height: 500)
}
```

**Use when:**
- Need specific service configuration
- Testing with temporary file paths
- Want isolated preview environment

**Note:** Temporary paths like `/tmp/preview.fichero` won't persist data

---

### Pattern 3: Multiple Environment Objects

```swift
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!
    let executionObserver = WorkflowExecutionObserver()

    WorkflowEditor(
        workflow: nil,
        editingWorkflow: .constant(Workflow(
            name: "Test Workflow",
            description: "A test workflow for preview",
            nodes: [],
            edges: []
        )),
        displayMode: .map
    )
    .environmentObject(library.workflowStore)
    .environmentObject(library.workflowServiceGenerated)
    .environmentObject(library.workflowStreamService)
    .environmentObject(library.documentStore)
    .environmentObject(libraryManager)
    .environment(executionObserver)  // Note: .environment() not .environmentObject()
    .frame(width: 1000, height: 700)
}
```

**Key Points:**
- Use `LibraryManager.shared` as entry point
- Extract services from `library` reference
- Use `.environment()` for `@Observable` objects (WorkflowExecutionObserver)
- Use `.environmentObject()` for `ObservableObject` classes

---

## Common Service Initialization

### Complete Library Services Setup

```swift
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    MyView()
        // Core services
        .environmentObject(library.documentStore)
        .environmentObject(library.workflowStore)
        .environmentObject(libraryManager)

        // Generated services
        .environmentObject(library.searchServiceGenerated)
        .environmentObject(library.chatServiceGenerated)
        .environmentObject(library.conversationServiceGenerated)
        .environmentObject(library.workflowServiceGenerated)
        .environmentObject(library.workflowStreamService)
        .environmentObject(library.storageServiceGenerated)
        .environmentObject(library.activityServiceGenerated)
        .environmentObject(library.automationServiceGenerated)
        .environmentObject(library.batchServiceGenerated)
        .environmentObject(library.artifactServiceGenerated)

        // App-wide services
        .environmentObject(AppState())

        .frame(width: 800, height: 600)
}
```

**Use this as a template** when a view needs many services.

---

### AppState Initialization

```swift
#Preview {
    let appState = AppState()
    appState.isBackendRunning = true
    appState.providers = [
        // Mock provider data if needed
    ]

    ProvidersView()
        .environmentObject(appState)
        .environmentObject(appState.providerService)
        .frame(width: 600, height: 400)
}
```

**For provider/settings views** that need global app state.

---

## Advanced Patterns

### PreviewWrapper Pattern (Complex State)

```swift
#Preview {
    struct PreviewWrapper: View {
        @State private var scale: CGFloat = 1.0
        @State private var snapToGrid: Bool = true
        @State private var executionObserver = WorkflowExecutionObserver()

        var body: some View {
            let libraryManager = LibraryManager.shared
            let library = libraryManager.globalLibrary!

            WorkflowCanvasView(
                workflow: .constant(Workflow(
                    name: "Test Workflow",
                    nodes: [
                        WorkflowNode(
                            id: "node1",
                            tool: "files",
                            label: "Input Files",
                            positionX: 150,
                            positionY: 200
                        ),
                        WorkflowNode(
                            id: "node2",
                            tool: "llm",
                            label: "Process with LLM",
                            positionX: 400,
                            positionY: 200
                        )
                    ],
                    edges: [
                        WorkflowEdge(
                            source: "node1",
                            sourcePort: "output",
                            target: "node2",
                            targetPort: "input"
                        )
                    ]
                )),
                scale: $scale,
                snapToGrid: $snapToGrid
            )
            .environmentObject(library.workflowStore)
            .environment(executionObserver)
            .frame(width: 800, height: 500)
        }
    }

    return PreviewWrapper()
}
```

**Use when:**
- Need real `@State` behavior in previews
- Want interactive previews
- Testing complex state interactions

**Why it works:**
- Nested `PreviewWrapper` struct manages state
- Can use real `@State`, `@StateObject`, etc.
- More verbose but more functional

---

### Multiple Preview Variants

```swift
#Preview("Idle Node") {
    WorkflowNodeView(
        node: .constant(WorkflowNode(
            id: "1",
            tool: "files",
            label: "Get Files",
            positionX: 100,
            positionY: 100,
            status: .idle
        )),
        isSelected: false,
        onSelect: {},
        onDeselect: {}
    )
    .frame(width: 200, height: 100)
}

#Preview("Running Node") {
    WorkflowNodeView(
        node: .constant(WorkflowNode(
            id: "2",
            tool: "llm",
            label: "Process Text",
            positionX: 100,
            positionY: 100,
            status: .running
        )),
        isSelected: false,
        onSelect: {},
        onDeselect: {}
    )
    .frame(width: 200, height: 100)
}

#Preview("Error Node") {
    WorkflowNodeView(
        node: .constant(WorkflowNode(
            id: "3",
            tool: "api",
            label: "API Call",
            positionX: 100,
            positionY: 100,
            status: .error,
            errorMessage: "Connection timeout"
        )),
        isSelected: true,
        onSelect: {},
        onDeselect: {}
    )
    .frame(width: 200, height: 100)
}
```

**Best practice:**
- Test all visual states (idle, running, error, success, etc.)
- Name previews descriptively
- Use realistic data for each state

---

## Anti-Patterns to Avoid

### ❌ Missing Environment Objects

```swift
// BAD - Will crash at runtime
#Preview {
    DocumentInspector(document: nil)
        .frame(width: 280, height: 400)
}
// Missing: .environmentObject(ArtifactServiceGenerated(...))
```

**Fix:**
```swift
// GOOD - Provides required environment objects
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    DocumentInspector(document: nil)
        .environmentObject(library.artifactServiceGenerated)
        .frame(width: 280, height: 400)
}
```

---

### ❌ Creating Objects in body

```swift
// BAD - Service recreated on every view update!
var body: some View {
    let service = DocumentService()  // ❌ Wrong!
    // ...
}
```

**Fix:**
```swift
// GOOD - Create in preview block or use @StateObject
#Preview {
    let service = DocumentService()

    MyView()
        .environmentObject(service)
}
```

---

### ❌ Incomplete Preview Comments

```swift
// BAD - Comment instead of implementation
#Preview {
    // Preview requires app context (APIClient, WorkflowStore)
}
```

**Fix:**
```swift
// GOOD - Provide the required context!
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    MyView()
        .environmentObject(library.workflowStore)
        .environmentObject(library.apiClient)
}
```

---

### ❌ No Backend Running

**Problem:** Previews timeout when services try to connect to localhost:8765

**Fix:** Always run backend before using previews:
```bash
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765
```

---

## Mock Data Examples

### Mock Document

```swift
Document(
    id: UUID().uuidString,
    name: "Sample Document.pdf",
    docType: .file,
    fileType: .pdf,
    path: "/path/to/document.pdf",
    pageContent: "Sample content for testing",
    status: .completed,
    createdAt: Date(),
    updatedAt: Date()
)
```

### Mock Workflow

```swift
Workflow(
    id: UUID().uuidString,
    name: "Sample Workflow",
    description: "A test workflow for previews",
    nodes: [
        WorkflowNode(
            id: "input",
            tool: "files",
            label: "Input Files",
            positionX: 100,
            positionY: 200,
            inputPorts: [],
            outputPorts: [
                PortInfo(
                    id: "files",
                    name: "Files",
                    type: "array",
                    required: false
                )
            ]
        ),
        WorkflowNode(
            id: "process",
            tool: "llm",
            label: "Process with LLM",
            positionX: 400,
            positionY: 200,
            inputPorts: [
                PortInfo(
                    id: "input",
                    name: "Input",
                    type: "string",
                    required: true
                )
            ],
            outputPorts: [
                PortInfo(
                    id: "output",
                    name: "Output",
                    type: "string",
                    required: false
                )
            ]
        )
    ],
    edges: [
        WorkflowEdge(
            source: "input",
            sourcePort: "files",
            target: "process",
            targetPort: "input"
        )
    ]
)
```

### Mock Conversation

```swift
Conversation(
    id: UUID().uuidString,
    title: "Sample Chat",
    messages: [
        ChatMessage(
            id: UUID().uuidString,
            role: .user,
            content: "Hello, can you help me?"
        ),
        ChatMessage(
            id: UUID().uuidString,
            role: .assistant,
            content: "Of course! I'd be happy to help. What do you need?"
        )
    ],
    documentScope: []
)
```

---

## Quick Reference

### Standard Preview Template

```swift
#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    MyView(/* parameters */)
        .environmentObject(library.documentStore)
        // Add other required services
        .frame(width: 600, height: 400)
}
```

### Standard Preview with Mock Data

```swift
#Preview("Empty State") {
    MyView(items: [])
        .frame(width: 600, height: 400)
}

#Preview("With Data") {
    MyView(items: mockItems)
        .frame(width: 600, height: 400)
}
```

---

**Remember:**
1. Always run backend before testing previews
2. Use `LibraryManager.shared` as entry point for services
3. Provide ALL required `@EnvironmentObject` dependencies
4. Create multiple preview variants for different states
5. Use descriptive names for previews
6. Frame previews with realistic dimensions

---

**Last Updated:** 2026-02-18
**Generated by:** Agent team analysis
