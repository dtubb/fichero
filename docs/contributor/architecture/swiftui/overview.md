(AI generated. Not reviewed.)

# Frontend Overview

**Last Updated**: 2026-05-24
**Status**: ✅ Swift 6 Compatible | SwiftUI-first (AppKit only behind contained `NSViewRepresentable` bridges — see `swiftui-principles.md` §8)

## What Fichero Frontend Does

Fichero is a **macOS document management application with AI processing capabilities**. The Swift frontend provides a native, high-performance interface to the Python/FastAPI backend.

### Core Features

**📚 Document Library**
- Hierarchical document organization with folders
- Grid and list views with Quick Look preview
- Security-scoped bookmarks for file access (macOS sandbox)
- Dual import modes: LINK (bookmark) and COPY (APFS clone)
- Support for 37+ file types (PDF, DOCX, images, audio, video, archives)

**💬 AI Chat Interface**
- Multi-model conversations with document context
- Scoped chat: query specific documents or entire library
- Model-agnostic LLM providers via LangChain integrations (LiteLLM is metadata only)
- Streaming responses with message history

**🔧 Visual Workflow Editor**
- Node-based LangGraph workflow builder
- 30+ tools organized by category (vision, transform, LLM, convert, logic)
- Real-time execution with streaming output logs
- Drag-and-drop tool palette

**🔍 Search**
- Full-text search across all documents
- Semantic vector search with LanceDB
- Advanced filters and saved searches
- Hybrid search combining text and embeddings

**🤖 AI Provider Management**
- Configure local and commercial LLM providers
- Ollama, LM Studio, Apple Vision (local)
- OpenAI, Anthropic, Google (commercial)
- Model browser with capability filtering

## Architecture

### High-Level Flow
```
SwiftUI Views → @Observable State → API Client (HTTP) → FastAPI Backend (port 8765)
                                                              ↓
                                                    DuckDB (metadata) + LanceDB (vectors)
```

### Feature Wiring Pattern

New backend capability is wired into SwiftUI one testable surface at a time:

1. Backend route/model is typed in OpenAPI and the generated client is synced when the API shape changes.
2. Swift service wrapper calls OpenAPI-typed fields, never `additionalProperties` for declared schema fields.
3. UI state lives in the owning store or `ContentView` extension already responsible for that surface.
4. Feature gates are checked through the existing `FeatureManager`; do not add a second flag registry.
5. Verification is the smallest relevant loop: Swift logic tests for state/predicates/builders, `swiftlint` for worker changes, and manager-owned Xcode build/test for integration.

Preview, screenshot, and human-test evidence belong on the feature or release-gate issue when the change affects rendered UI.

### Resizable Multi-Pane Layout

The window is a resizable multi-pane reading layout (pane widths persist via `@SceneStorage`).
Panes adapt to the active mode — not all are shown at once.
```
┌──────────┬───────────────┬─────────────────────┬────────────────────┐
│ Sidebar  │ Document list │ Content / reading   │ Inspector (tabbed) │
│ (modes)  │ (grid/list)   │ pane                │                    │
├──────────┼───────────────┼─────────────────────┼────────────────────┤
│ Navigate │ • documents   │ • PDF / page view   │ • Info             │
│ Search   │ • folders     │ • image / preview   │ • Metadata         │
│ Chat     │ • search hits │ • chat interface    │ • Content (edit)   │
│ Workflows│               │ • workflow canvas   │ • Artifacts        │
│ Activity │               │                     │ • Knowledge Graph  │
└──────────┴───────────────┴─────────────────────┴────────────────────┘
```

### Key Components

#### 1. **App Layer** (`App/`)
- **FicheroApp.swift** - Entry point, menu bar, window management
- **AppState.swift** - Global state with `@Observable` (Swift 5.9+)
- **ViewSettings.swift** - Layout preferences and view configuration

#### 2. **Views Layer** (`Views/`)

**Layout**:
- **ContentView.swift** - Three-column `NavigationSplitView` container
- **DocumentTabView.swift** - Tab/window management for documents

**Sidebar** (`Views/Sidebar/`):
- Multi-mode navigation (5 modes)
- Hierarchical document tree with drag-and-drop
- Section headers with collapsible state
- Context menus for quick actions

**Library** (`Views/Library/`):
- Grid/list document browser
- Quick Look preview with security-scoped access
- Metadata inspector panel
- Folder access manager for sandbox permissions

**Chat** (`Views/Chat/`):
- Message list with markdown rendering
- Model selector and temperature controls
- Document scope selector
- Streaming message support

**Workflow** (`Views/Workflow/`):
- Node-based canvas with pan/zoom
- Tool palette in inspector
- Port connections for data flow
- Execution log panel

**AI Providers** (`Views/AIProviders/`):
- Provider configuration sheets
- Model browser (standard + Hugging Face)
- API key management
- Connection testing

**Menu & Toolbars**:
- @FocusedValue for menu commands (NO NotificationCenter)
- Per-view toolbars (Library, Chat, Workflow, Search)
- Keyboard shortcuts (⌘1-4 for views, ⌃⌘1-5 for sidebar modes)

#### 3. **Services Layer** (`Services/`)

**Core Services**:
- **APIClient.swift** - HTTP client with streaming support
- **DocumentService.swift** - Document CRUD operations
- **ChatService.swift** - Chat/conversation management
- **WorkflowService.swift** - Workflow execution
- **SearchService.swift** - Search operations
- **ProviderService.swift** - AI provider configuration

**Specialized**:
- **DragDropService.swift** - Drag-and-drop handling (Swift 6 compliant)
- **ErrorService.swift** - Centralized error reporting
- **PerformanceService.swift** - Benchmarking and monitoring
- **ImportService.swift** - File ingestion pipeline

#### 4. **Models Layer** (`Models/`)

**Data Models**:
- **Document.swift** - Core document model
- **DocumentStore.swift** - Document state management
- **Workflow.swift** - Workflow definition
- **Provider.swift** - Provider configuration

**UI State**:
- **ViewContexts.swift** - View mode contexts (Library, Chat, Workflow, Search)
- **SidebarState.swift** - Sidebar navigation state
- **DragDropModel.swift** - Drag-and-drop state (Swift 6 compliant)
- **WindowState.swift** - Window/tab state

## State Management Patterns

### Modern SwiftUI State (iOS 17+/macOS 14+)

**✅ Use `@Observable` for view models**:
```swift
@Observable
class DocumentStore {
    var documents: [Document] = []
    var selectedDocument: Document?
}

// In view
@State private var store = DocumentStore()
```

**✅ Use `@EnvironmentObject` for shared state**:
```swift
// Inject at app level
.environmentObject(AppState())

// Access in views
@EnvironmentObject var appState: AppState
```

**✅ Use `@FocusedValue` for menu commands**:
```swift
// Define
extension FocusedValues {
    var sidebarActions: SidebarActions? {
        get { self[SidebarActionsKey.self] }
        set { self[SidebarActionsKey.self] = newValue }
    }
}

// Provide from view
.focusedValue(\.sidebarActions, actions)

// Consume in menu
@FocusedValue(\.sidebarActions) private var actions
```

### Swift 6 Concurrency

**Main Actor Isolation**:
- All `ObservableObject` and `@Observable` types are `@MainActor`
- UI updates automatically run on main thread
- Use `Task { @MainActor in ... }` to hop to main actor from background

**Sendable**:
- Use `@unchecked Sendable` for classes with internal thread safety
- All service closures properly isolated with `Task { @MainActor in ... }`

**Task Cancellation**:
- All `.task {}` blocks check `Task.isCancelled`
- Proper cleanup in defer blocks

## KG Graph Renderer Decision

- Canonical decision: `Cytoscape.js` via WebKit.
- Decision record: [kg_renderer_decision.md](./kg_renderer_decision.md)
- Swift source of truth: `KGGraphRendererFramework.selected` in `DocumentKGSurface.swift`.

## Development Workflow

### Prerequisites
```bash
# 1. Start Python backend (REQUIRED)
cd "$(git rev-parse --show-toplevel)"
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# 2. Open Xcode project
open Fichero/Fichero.xcodeproj

# 3. Build and run (⌘R)
```

### Code Quality Checks

**Before every commit**:
```bash
cd Fichero
swiftlint  # Must pass with zero errors
```

**Common violations to avoid**:
- File length > 400 lines
- Function complexity > 10
- Identifier names like `x`, `y`, `i`
- Line length > 120 characters

### Testing

**Unit Tests**:
```bash
# Run in Xcode: ⌘U
# Or via command line:
xcodebuild test -project Fichero.xcodeproj -scheme Fichero
```

**Preview Testing**:
- Use `#Preview` for visual testing
- Test in Xcode preview canvas
- Interactive testing with sample data

## Code Organization Standards

### File Size Limits
- **Recommended**: < 400 lines per file
- **Hard Limit**: < 1,000 lines (requires split)
- **Type Body**: < 250 lines per struct/class
- **Functions**: < 50 lines per function

### Naming Conventions
- **Files**: `PascalCase` (DocumentView.swift)
- **Variables**: `camelCase` (selectedDocument)
- **Functions**: Verb-first (loadDocument(), saveWorkflow())
- **NO single-letter names**: Never use `x`, `y`, `i`, `a`, `b`

### Standard File Structure
```swift
import SwiftUI
import OSLog

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "FileName")

struct MyView: View {
    // MARK: - Properties
    @State private var ...

    // MARK: - Body
    var body: some View { ... }

    // MARK: - Subviews
    private var toolbar: some View { ... }

    // MARK: - Actions
    private func handleAction() { ... }
}

#Preview {
    MyView()
}
```

## Current Status

### ✅ Completed
- All Swift 6 concurrency warnings fixed
- Build succeeds with zero errors
- OSLog migration complete (88/88 NSLog instances replaced)
- AppKit audit complete (6 files justified)
- Pure SwiftUI compliance maintained

### ✅ Refactoring Complete (Feb 2026)
35 of 37 oversized files refactored across 13 batches:
- All view files reduced to <200 lines
- All model/service files reduced to <300 lines
- Historical note: old audits found skipped files outside the Xcode project; the registration guardrail now owns this check.
- 1 file blocked: ActionLibraryView.swift (dependency issue)
- SwiftLint violations reduced from 330 to 69

See `agents/progress.md` for full tracker with before/after line counts.

### 🚧 Missing Features
- **Hierarchical searches/chats/workflows** - Sidebar only supports hierarchical documents
- **Persistent sidebar items** - Cannot save searches, chats, or workflows to sidebar
- **Backend auto-start** - Must manually start backend before running app

## Key Principles

### 100% Pure SwiftUI
**NO AppKit** except for unavoidable cases:
- ✅ NSSavePanel / NSOpenPanel (file dialogs)
- ✅ QLPreviewView (Quick Look)
- ✅ NSEvent (scroll wheel for zoom)
- ❌ NO NSView wrapping
- ❌ NO AppKit controls
- ❌ NO NotificationCenter for logic

### Performance
- Cache expensive computations
- Don't recreate objects in view body
- Use `@StateObject` for view models
- Profile regularly with Instruments

### Accessibility
- Add labels to all interactive elements
- Support keyboard navigation
- Provide accessibility hints
- Test with VoiceOver

## Backend Integration

**API Endpoints** (FastAPI on port 8765):
- `/api/documents` - Document CRUD
- `/api/chat` - Chat/conversation
- `/api/workflows` - Workflow execution
- `/api/search` - Search operations
- `/api/providers` - Provider configuration
- `/api/models` - Model management
- `/api/ingest` - File import
- `/api/storage` - File storage

**Data Flow**:
```
SwiftUI → Service → APIClient → HTTP Request → FastAPI
                                                   ↓
                                           DuckDB + LanceDB
                                                   ↓
                                           JSON Response
                                                   ↓
SwiftUI ← @Observable ← Service ← APIClient ← HTTP Response
```

## Resources

- **SwiftUI Principles**: `docs/contributor/swiftui-principles.md`
- **Development Standards**: `docs/contributor/swiftui-development-standards.md`
- **Key Files**: `docs/contributor/architecture/swiftui/key_files.md`
- **Workflow Checklist**: `docs/contributor/architecture/swiftui/workflow_checklist.md`
- **Sample Code**: `fichero/sample_code`
