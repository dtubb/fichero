(AI generated. Not reviewed.)

# CLAUDE.md — Architecture & Development Guide

The durable architecture reference for agents working in this repo: how the system is shaped, the conventions, and the pitfalls. Operational rules (build/test/lint, commit discipline, lanes), the hard rules, and the code-navigation policy all live in `AGENTS.md` (the canonical operational manual); the product north-star in `CONSTITUTION.md`. User-facing run/build docs are in `README.md`.

## Project Overview

Fichero is a macOS document management application with AI processing capabilities. It provides:
- Document organization, search, and RAG-based chat
- Visual workflow editor for document processing pipelines (LangGraph)
- Support for 37+ file types with intelligent ingestion
- Model-agnostic LLM providers, local and commercial, via LangChain integrations

**Architecture:**
- **Swift/SwiftUI frontend** (`fichero/`) - SwiftUI-first native macOS app; AppKit via `NSViewRepresentable` where SwiftUI can't reach (PDFKit, image magnifier/zoom, rich-text editing)
- **Python/FastAPI backend** (`fichero-engine/src/fichero/`) - Document processing, AI workflows, and data storage
- **Dual database system**: DuckDB for metadata + LanceDB for vector embeddings
- **Communication**: HTTP/REST on localhost:8765 with type-safe Swift client

Multi-window, multi-library (per-library service instances). Each window is a resizable multi-pane layout: sidebar · document list · content/PDF reading view · tabbed inspector (Info / Metadata / Content / Artifacts / Knowledge Graph).

## Development Commands

Build, test, lint, and OpenAPI-sync commands — and who runs which — live in **`AGENTS.md`** (the operational manual). The backend must be running on `localhost:8765` before the Swift app works, and it **must serve HTTPS** — the app pins `https://127.0.0.1:8765` fail-closed (#2376/#2370), so a plain-HTTP engine is unreachable (Activity SSE + all loopback calls die, #2538). Use the supported launcher, which prepares loopback TLS + persists the pin:

```bash
bash fichero-engine/scripts/start_backend.sh   # serves HTTPS; never bare `uvicorn ... --port 8765`
```

Two build notes worth keeping here: prefer the **Xcode MCP** (`mcp__xcode__BuildProject`) so the build shares Xcode.app's cache and avoids `build.db` lock contention; CLI `xcodebuild` needs `-skipPackagePluginValidation` (the OpenAPIGenerator SPM plugin fails without it) and should build into the default DerivedData, not an isolated `-derivedDataPath`, to keep the user's ⌘R incremental.

## Architecture

### Backend Communication Flow

```
SwiftUI App → HTTP/REST → FastAPI (port 8765) → DuckDB/LanceDB
                                   → LangGraph (workflows)
                                   → LLM Providers (via LangChain)
```

The Swift app is a **pure UI layer** - all business logic, data persistence, and AI processing happens in the Python backend.

### Key Backend Modules

- **`api/main.py`**: FastAPI app. Which routes are active is controlled by the `FICHERO_FEATURE_TIER` env var (`release` | `dev`, default `release`) — `release` registers the stable core, `dev` adds staged features.
  - **Core (always on):** activity, artifacts, batch, chat, claims/claim-links, documents, entities, folders, ingest, providers, review-queue, search, settings, sources, models, storage, tasks, workflows/workflow-execution, …
  - **Dev tier** (`FICHERO_FEATURE_TIER=dev`): knowledge-graph, hermeneutics, interpretations, graph-exploration, mind-palace, research, iiif, and other staged features (actions, chains, integrations, model-comparison, orchestration, schedules, triggers, …)
- **`db.py`**: Dual database layer (DuckDB for relational data, LanceDB for vector embeddings)
- **`models.py`**: Pydantic models shared between API and database
- **`workflows/`**: LangGraph-based visual workflow engine with tool registry, execution engine, and state management
  - `executor.py`: Runs workflow graphs with streaming support
  - `registry.py`: 30+ tools organized by category (vision, transform, llm, convert, logic, conditions)
  - `builder.py`: Converts frontend graph definitions to executable LangGraph
- **`ingest.py`**: File ingestion pipeline supporting 37+ file types with two modes:
  - LINK mode: Creates bookmarks to files in place (uses macOS security-scoped bookmarks)
  - COPY mode: Imports files using APFS cloning for instant copying
- **`loaders/`**: Text extraction engines for PDFs, DOCX, images, etc.
- **`llm.py`**: LangChain provider integrations. Every chat/completion call is routed
  by LangChain. `litellm` is imported here but only for `get_model_info()` and
  `cost_per_token()` — it never sends a request.
- **`providers.py`**: LLM provider definitions (local: Ollama, LM Studio, Apple Vision; commercial: OpenAI, Anthropic, Google)

### Key Swift Modules

**Entry Point:**
- **`FicheroApp.swift`**: App lifecycle, backend startup, library manager, command menu structure, window management

**Models Layer (`Models/`):**
- **`Document.swift`**: Core data model with DocType, FileType, Status enums
- **`DocumentStore.swift`**: Document hierarchy, CRUD operations, file import, folder ingestion
- **`LibraryManager.swift`**: Multi-library management, per-library service instances
- **`WorkflowTypes.swift`**: Workflow definitions, nodes, edges, ports, input/output mapping
- **`SidebarItem.swift`**: Navigation structure, hierarchical sidebar items
- **`FicheroDocument.swift`**: Per-window document state
- **`WorkflowStore.swift`**: Workflow list, create, update, duplicate, export operations

**Service Layer (`Services/`):**
- **`APIClient.swift`**: HTTP client with library path injection, per-window instances
- **`*Generated.swift` service wrappers**: hand-written wrappers over the generated OpenAPI client (Workflow, Provider, Search, Chat, Document, …) — editable despite the suffix; the *generated* code lives in `fichero-api-client/`
- **`WorkflowStreamService.swift`**: Server-Sent Events for real-time workflow execution
- **`EmbeddedBackendService.swift`**: Backend process management
- **`ProviderService.swift`**: Provider validation wrapper around the generated service

**Views Layer (`Views/`, organized by feature domain — incl. `KnowledgeGraph/`, `ModelComparison/`, `MCPServers/`, `Settings/`):**
- **`ContentView.swift`**: Resizable multi-pane layout, split into extensions (State, ViewBuilders, Navigation, Actions, Persistence) + `ContentViewModifiers`
- **`DocumentTabView.swift`**: Per-window entry point, service initialization
- **`Sidebar/`**: Multi-mode navigation (Library, Search, Chat, Workflows, Activity, Automation, Batches)
- **`Library/`**: Document browser, grid/list/table views, inspector
- **`Workflow/`**: Visual node editor canvas, workflow library, node configuration
- **`Chat/`**: RAG conversation interface
- **`Search/`**: Semantic search interface
- **`Activity/`**: Execution history and real-time progress
- **`AIProviders/`, `Automation/`, `Batch/`, `Agents/`, `Integrations/`, `Components/`, `Toolbars/`, etc.

**Generated API Client:**
- **`fichero-api-client/`**: Local Swift package with type-safe API client from OpenAPI schema

### Swift API Client (OpenAPI Generator)

The Swift frontend uses **Apple's Swift OpenAPI Generator** to create type-safe API clients from the Python backend's OpenAPI schema. This ensures Swift and Python stay in sync.

**Key files:**
- `fichero/fichero-api-client/` - Local Swift package with generated client
- `fichero-engine/tests/contracts/openapi.json` - OpenAPI schema (source of truth)
- `fichero-engine/scripts/sync_openapi_schema.sh` - Syncs schema from Python to Swift

**Usage:**
```swift
import FicheroAPIClient
import OpenAPIURLSession

let client = Client(
    serverURL: URL(string: "http://localhost:8765/api")!,
    transport: URLSessionTransport()
)

// Type-safe API calls
let response = try await client.listWorkflowsApiWorkflowsGet(.init())
let workflows = try response.ok.body.json
```

**When Python API changes:**
```bash
./fichero-engine/scripts/sync_openapi_schema.sh
```

See `docs/contributor/architecture/swiftui/api_client.md` for detailed documentation

### Ingest System

The ingest module is a core feature for importing files into the library:

- **Dual modes**: LINK (bookmark-based, zero disk usage) or COPY (file import with APFS instant cloning)
- **37+ file types**: Documents (PDF, DOCX, TXT), images (JPG, PNG, RAW), audio, video, archives
- **Metadata extraction**: Automatic EXIF, file attributes, dimensions, duration
- **Text extraction**: Searchable text from PDFs, Office docs, images (OCR)
- **Folder processing**: Recursive ingestion with hierarchy preservation

See `docs/contributor/ingest-api.md` for detailed API documentation.

## Code Quality Standards

### Swift - SwiftUI-first (AppKit only where SwiftUI can't reach)

**Default to SwiftUI. Reach for AppKit only when SwiftUI genuinely lacks the capability** — and isolate it in an `NSViewRepresentable` / `NSViewControllerRepresentable` bridge, never sprinkled through view code. Sanctioned bridges today (≈8 conformers, ~18 files `import AppKit`): PDFKit rendering + zoom (`PDFThumbnailView`, `PDFZoomController`), the image magnifier / cursor tracking (`MagnifierPanel`, `ImageWithCursorTracking`), scroll-wheel zoom (`ScrollWheelZoom`), Quick Look previews, and rich/plain-text editors (`AttributedTextEditor`, `MacPlainTextEditor`). Trackpad-swipe detection uses `NSEvent.addLocalMonitorForEvents` (no SwiftUI equivalent on macOS 15).

Still avoid these — SwiftUI has the answer:
- ❌ `NotificationCenter` for state changes → use `@FocusedValue` / `@Published` / Combine
- ❌ Manual `DispatchQueue.main` dispatching → use `@MainActor`
- ❌ Reaching for AppKit when a SwiftUI view/control already exists — check Apple docs (sosumi) first

**Before implementing anything, check Apple docs:**
- Use `sosumi.searchAppleDocumentation()` for SwiftUI equivalents FIRST
- Use `ref.searchDocumentation()` for Swift language features
- Read Human Interface Guidelines for macOS patterns

**State Management (Swift 6 Concurrency):**
```swift
// ✅ DO: Use @MainActor for UI-related classes
@MainActor
class DocumentStore: ObservableObject {
    @Published var documents: [Document] = []

    func updateUI() {
        // Already on main thread - no dispatch needed
        self.documents.append(newDoc)
    }
}

// ✅ DO: Use @FocusedValue for menu commands (NOT NotificationCenter)
extension FocusedValues {
    var sidebarActions: SidebarActions? {
        get { self[SidebarActionsKey.self] }
        set { self[SidebarActionsKey.self] = newValue }
    }
}

// ✅ DO: Check Task cancellation in all .task blocks
.task {
    guard !Task.isCancelled else { return }
    await loadData()
}

// ❌ DON'T: Use DispatchQueue.main
DispatchQueue.main.async {  // ❌ Use @MainActor instead
    self.updateUI()
}
```

**File Size Guidelines (CRITICAL):**
- **Recommended:** < 400 lines per file
- **Hard Limit:** < 1,000 lines (MUST split if exceeded)
- **Type Body:** < 250 lines per struct/class
- **Functions:** < 50 lines each

**Other Requirements:**
- **SwiftLint is MANDATORY** - run before every commit
- Use `@StateObject` for owned state, `@EnvironmentObject` for dependency injection
- Use OSLog for logging (categories: `com.tubb.Fichero`)
- Cache expensive computations (don't rebuild hierarchies on every view update)
- Keyboard shortcuts: Ulysses-style (⌃⌘1-5 for sidebar modes, ⌘1-4 for view modes)

**Required Reading:** `docs/contributor/swiftui-principles.md` - Mandatory patterns and examples

### Python

- Use Pydantic v2 models for all data structures
- Follow FastAPI patterns: routes in `api/routes/`, business logic in core modules
- Database operations go through `db.py` - never query DuckDB/LanceDB directly
- Workflow tools must be registered in `workflows/registry.py` with proper metadata

## Important Notes

### Backend Dependency

The Swift app **cannot function without the Python backend running**. Always start the backend server before testing the Swift app.

### Database Locations

- DuckDB: `~/Library/Application Support/Fichero/fichero.duckdb`
- LanceDB: `~/Library/Application Support/Fichero/lance/`

### Security-Scoped Bookmarks

In LINK mode, the app uses macOS security-scoped bookmarks (`bookmarks.py`) to maintain access to files outside the sandbox. This requires proper entitlements in `fichero/fichero/Fichero.entitlements`.

### LangChain routes; LiteLLM is metadata only

Every LLM call goes through **LangChain** provider integrations (invoked from
LangGraph workflow nodes). `litellm` is imported in `llm.py` / `llm_models.py` for
exactly two things:

- `litellm.cost_per_token()` — cost estimates
- `litellm.get_model_info()` — model capability/catalog lookup

It is **not** a router. `litellm.completion` / `acompletion` / `Router` appear
nowhere in the engine. Do not route a call through it. See
`docs/contributor/architecture/ai_infrastructure.md`.

### Workflow System

Workflows are defined as visual graphs in the Swift UI but executed in Python via LangGraph. The frontend sends workflow definitions as JSON to `/api/workflows/execute`, which:
1. Validates the graph structure
2. Resolves parameter references
3. Builds a LangGraph executable
4. Streams results back to the frontend

**Architecture Principles:**

1. **Tool Registry is Single Source of Truth for Ports**
   - Port definitions (input/output) belong in `workflows/registry.py`
   - NodeDef should NOT store ports - only reference the tool name
   - Ports are enriched from registry when needed for execution or UI display

2. **Minimal NodeDef Format**
   - Store only: `id`, `tool`, `position_x`, `position_y`, `label`, `config`, `enabled`
   - Do NOT duplicate port definitions in stored workflows

3. **LangGraph Conversion in Backend Only**
   - All graph-to-LangGraph conversion happens in `workflows/builder.py`
   - Swift should never construct LangGraph structures
   - Swift sends minimal workflow definitions, Python handles all execution logic

4. **Generated Types Over Manual Types**
   - Use Swift OpenAPI Generator types (`Components.Schemas.*`) directly in views
   - Avoid creating manual Swift types that shadow generated types
   - Keep `GeneratedTypeExtensions.swift` minimal (just Identifiable conformances)

See `docs/contributor/architecture/swiftui/api_migration_guide.md` and `docs/contributor/architecture/swiftui/api_client.md` for current API-client cleanup context.

## Git Workflow, Commits, Tasks, Parallelism

These are operational and owned elsewhere — not restated here:
- **Branch discipline + conventional-commit format + pre-commit gate** → `AGENTS.md` ("Rules I Don't Break"). In short: commit milestone work directly to the milestone branch (no per-task branches); never push to `main` without approval; regenerate the OpenAPI client before committing any backend API change.
- **Task tracking** → GitHub Issues + Milestones + Project board are the source of truth; local planning files (`PLAN.md`, `TASKS.md`) are not. `STATE.md` is continuity context only. (See `CONSTITUTION.md` → Execution Governance.)
- **Lanes, delegation, the QA review gate** → the session-start / manager skills and `agent-work/agent-workflow/parallel-execution.md`.
- **Current focus / next entry point** → `STATE.md`; completed-work log → `HISTORY.md`.

## MCP Tools

Only **`XcodeBuildMCP`** is pinned by the repo (`.mcp.json`). Every other MCP server comes from
the agent's own global / plugin config — it varies per agent (Claude Code, Codex, …) and changes
over time, so **the live tool list in your session is authoritative**. Don't rely on a roster here;
there isn't one on purpose.

Two project-specific notes you can't infer from the tool list:
- **Code navigation goes through jcodemunch first** — policy in `AGENTS.md` ("Code Navigation"). If it isn't connected, fall back to Read/Grep and say so.
- **Xcode builds**: prefer the `xcode` MCP over raw `xcodebuild` (see Development Commands above). `XcodeBuildMCP`'s tools mostly target iOS simulators — Fichero is macOS, so use the macOS / device-less variants.

## Architecture Patterns Reference

### Multi-Window & Multi-Library Architecture

```
AppState (global singleton)
  ├── ProviderService
  ├── MCPService
  └── ModelService

LibraryManager (singleton)
  └── LibraryReference (per library)
      ├── APIClient (per window, shared in library)
      ├── FicheroClient (per library)
      ├── DocumentStore (per window)
      ├── WorkflowStore
      ├── SearchServiceGenerated
      ├── ChatServiceGenerated
      └── ... (other generated service wrappers)

ContentView (per window)
  ├── ViewSettings
  ├── AppState (@EnvironmentObject)
  ├── DocumentStore (@EnvironmentObject)
  └── All library services via @EnvironmentObject
```

**Key Principle:** Each window has its own `DocumentStore` and `APIClient`, but services are shared per library.

### Library Path Isolation

Every API request includes `X-Fichero-Library-Path` header (except app-wide endpoints):
- Different libraries in different windows are isolated
- `APIClient.configureRequest()` injects header based on endpoint category
- App-wide endpoints (health, providers/catalog, settings) skip header

### Generated Code Pattern

The project uses **Swift OpenAPI Generator** for type-safe API clients:

1. **Source of Truth:** Python FastAPI exports OpenAPI schema (`fichero-engine/tests/contracts/openapi.json`)
2. **Generation:** Swift OpenAPI Generator creates `Client.swift` and `Types.swift`
3. **Generated Services:** 14 `*Generated.swift` files wrap generated client with typed methods
4. **Manual Extensions:** Business logic goes in manual service wrappers (e.g., `ProviderService` wraps `ProviderServiceGenerated`)

**Pattern Example:**
```swift
// Generated service (auto-generated from OpenAPI)
class WorkflowServiceGenerated {
    func listWorkflows() async throws -> [WorkflowDefinition] {
        let response = try await client.listWorkflowsApiWorkflowsGet(.init())
        return try response.ok.body.json
    }
}

// Manual wrapper (for validation, business logic)
class WorkflowService {
    private let generated: WorkflowServiceGenerated

    func listWorkflows() async throws -> [WorkflowDefinition] {
        // Add validation, error handling, caching, etc.
        return try await generated.listWorkflows()
    }
}
```

### Reactive State Updates

```swift
// DocumentStore uses Combine publishers
class DocumentStore: ObservableObject {
    @Published var documents: [Document] = []
    let documentChangePublisher = PassthroughSubject<DocumentChange, Error>()

    func updateDocument(_ doc: Document) {
        // Update triggers SwiftUI re-render via @Published
        documents[index] = doc

        // Notify subscribers via Combine
        documentChangePublisher.send(.updated(doc))
    }
}

// Views subscribe automatically via @EnvironmentObject
struct DocumentListView: View {
    @EnvironmentObject var documentStore: DocumentStore

    var body: some View {
        // Automatic re-render when documentStore.documents changes
        List(documentStore.documents) { doc in
            DocumentRow(doc)
        }
    }
}
```

### Async/Await with @MainActor

All services and models are `@MainActor` for thread-safe UI updates:

```swift
@MainActor
class APIClient: ObservableObject {
    func get<T: Decodable>(_ endpoint: String) async throws -> T {
        // Already on main thread - no dispatch needed
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode(T.self, from: data)
    }
}

// Usage in views
.task {
    do {
        // Automatically runs on main actor context
        let workflows = try await apiClient.get("/api/workflows")
        self.workflows = workflows
    } catch {
        self.error = error
    }
}
```

## Common Pitfalls

### Critical Issues
- **Port conflicts**: Backend MUST run on port 8765 (hardcoded in Swift app at `APIClient.swift`)
- **Backend dependency**: Swift app cannot function without Python backend running
- **PYTHONPATH**: MUST be set to `fichero-engine/src` when running backend or tests
- **Archived tests**: ALWAYS ignore `fichero-engine/tests/unit/_archived` directory
- **New .swift files require pbxproj registration**: The `Fichero` main target uses traditional PBX file references (NOT `PBXFileSystemSynchronizedRootGroup`). A new `.swift` file written to disk is invisible to the compiler until registered. Use the helper script:
  ```bash
  # Write the file first, then register it:
  ruby scripts/add-swift-file.rb fichero/fichero/Views/MyFolder/MyView.swift
  ```
  `scripts/add-swift-file.rb` uses the `xcodeproj` Ruby gem (already installed at `~/.gem/ruby/2.6.0/gems/xcodeproj-1.27.0/`). Do NOT edit `project.pbxproj` by hand. Test-target files are the exception — those use sync'd groups and just work.

### SwiftUI Anti-Patterns
- **Don't use DispatchQueue.main**: Use `@MainActor` instead for Swift 6 concurrency
- **Don't use NotificationCenter**: Use `@FocusedValue` for menu commands
- **Don't create objects in body**: Objects recreated on every view update - use `@StateObject` or `@State`
- **Don't rebuild hierarchies**: Cache expensive computations, don't rebuild on every view update
- **Don't ignore Task.isCancelled**: All `.task {}` blocks MUST check cancellation

### API & Backend
- **OpenAPI schema sync**: Run `./fichero-engine/scripts/sync_openapi_schema.sh` after Python API changes
- **Library path header**: Multi-library operations require `X-Fichero-Library-Path` header
- **Workflow parameters**: Always validate parameter types match tool expectations in registry
- **Database access**: NEVER query DuckDB/LanceDB directly - always use `db.py`

### Development Workflow
- **Status tracking**: update task state in GitHub Issues / Project board, not local files
- **SwiftLint**: Run before EVERY commit - zero warnings required
- **File sizes**: Keep files < 400 lines (hard limit: 1,000 lines)
- **Session defaults**: Set project/workspace and scheme with `session-set-defaults` before using MCP build tools
- **UI automation**: Always use `describe_ui` to get precise coordinates - never guess from screenshots

### Testing
- **Python 3.14**: Register pytest async markers in `pyproject.toml`
- **Contract tests**: Verify Swift types align with OpenAPI schema via `test_api_contracts.py`
- **Integration tests**: Separate from unit tests, run full backend stack

## Quick Reference: Key Files

### Essential Documentation
- **`docs/ai/CLAUDE.md`** (this file) - Canonical agent guidance
- **`docs/contributor/swiftui-principles.md`** - MANDATORY SwiftUI patterns (18KB)
- **`docs/contributor/architecture/swiftui/api_migration_guide.md`** - OpenAPI client migration guide
- **`docs/contributor/swiftui-development-standards.md`** - File size limits, Swift 6 guidelines
- **`docs/contributor/backend-development-standards.md`** - Backend development standards
- **GitHub Issues + Milestones + Project board** - task backlog & source of truth (`gh issue list`)
- **`README.md`** - User-facing setup and run instructions

### Critical Swift Files (Frequently Modified)
- **`FicheroApp.swift`** - App lifecycle, menu structure
- **`DocumentStore.swift`** - Document CRUD, state management
- **`LibraryManager.swift`** - Multi-library orchestration
- **`APIClient.swift`** - HTTP client with library path injection
- **`ContentView.swift`** - Resizable multi-pane layout (split into extensions)
- **`WorkflowTypes.swift`** - Workflow data models

### Critical Python Files (Backend)
- **`fichero-engine/src/fichero/api/main.py`** - FastAPI app, route registration
- **`fichero-engine/src/fichero/db.py`** - Database layer (DuckDB + LanceDB)
- **`fichero-engine/src/fichero/models.py`** - Pydantic models (source of truth)
- **`fichero-engine/src/fichero/workflows/registry.py`** - Tool registry
- **`fichero-engine/src/fichero/workflows/executor.py`** - Workflow execution with streaming
- **`fichero-engine/src/fichero/ingest.py`** - File ingestion pipeline

### Generated Files (regenerated, never hand-edited)
- **`fichero/fichero-api-client/`** - generated Swift OpenAPI client package
- **`fichero-engine/tests/contracts/openapi.json`** - OpenAPI schema (regenerated from Python via `sync_openapi_schema.sh`)

> Note: `fichero/Services/*Generated.swift` are **hand-written** service wrappers over the generated client — editable despite the suffix. Only the api-client package and `openapi.json` are truly generated.

## Additional Resources

### Architecture Documentation
Full architectural context is in `docs/contributor/architecture/`:

**SwiftUI Documentation:**
- `overview.md` - Frontend architecture overview
- `key_files.md` - Essential Swift files with navigation tips
- `workflow_checklist.md` - Daily development workflow
- `api_client.md` - Swift OpenAPI Generator patterns

**API Documentation:**
- `api/overview.md` - Backend architecture, core components
- `api/key_files.md` - Essential Python files
- `api/workflow_checklist.md` - Backend development checklists

### Specialized Guides
- **`docs/contributor/ingest-api.md`** - File ingestion API reference
- **`docs/contributor/ingest-best-practices.md`** - Ingestion patterns
- **`docs/user/supported-file-types.md`** - 37+ supported file formats
- **`docs/contributor/bundling-backend.md`** - Backend deployment strategy

### Manual QA
- **`docs/qa_matrix.md`** - View-by-view manual testing checklist

---

**Note:** This document is the canonical source of agent guidance. When in doubt, refer to the architecture documentation in `docs/contributor/architecture/` for detailed implementation patterns and examples.
