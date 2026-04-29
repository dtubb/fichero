# CLAUDE.md

**Last Updated:** 2026-04-13
**Status:** Canonical Agent Guidance

This file provides guidance to coding agents when working with code in this repository.

Scope: this is agent workflow guidance. User/developer run/build docs live in `README.md` and folder-level READMEs.

## Project Overview

Fichero is a macOS document management application with AI processing capabilities. It provides:
- Document organization, search, and RAG-based chat
- Visual workflow editor for document processing pipelines (LangGraph)
- Support for 37+ file types with intelligent ingestion
- Integration with 100+ LLM providers (local and commercial)

**Architecture:**
- **Swift/SwiftUI frontend** (`fichero/`) - 100% pure SwiftUI native macOS app
- **Python/FastAPI backend** (`fichero-engine/src/fichero/`) - Document processing, AI workflows, and data storage
- **Dual database system**: DuckDB for metadata + LanceDB for vector embeddings
- **Communication**: HTTP/REST on localhost:8765 with type-safe Swift client

**Key Statistics:**
- 189 Swift files (44 services, 118 views, 27 models)
- 16 auto-generated service files from OpenAPI schema
- Multi-window, multi-library support with per-library service instances
- Three-column layout (Sidebar | Content | Inspector)

## Development Commands

### Backend (Python FastAPI)

```bash
# Start the FastAPI backend server (required for Swift app to function)
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765
```

The backend must be running on port 8765 before launching the Swift app.

### Frontend (Swift/SwiftUI)

```bash
# Build the Swift app
xcodebuild -project fichero/fichero.xcodeproj -scheme Fichero -configuration Debug

# Run SwiftLint (code quality)
swiftlint lint fichero/fichero/
```

**Preferred method**: Open `fichero/fichero.xcodeproj` in Xcode and run (⌘R).

### Testing

```bash
# Python unit tests (ignore archived tests)
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived

# Python integration tests
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/integration/

# Swift tests (run from Xcode or command line)
xcodebuild test -project fichero/fichero.xcodeproj -scheme Fichero

# OpenAPI contract tests (verify schema alignment)
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_api_contracts.py
```

### Code Quality

```bash
# SwiftLint (MANDATORY before commit) — installed via Homebrew
swiftlint lint fichero/fichero/

# Ruff — Python linting (MANDATORY before commit)
ruff check fichero-engine/src/
ruff check fichero-engine/tests/

# Sync OpenAPI schema after Python API changes
./fichero-engine/scripts/sync_openapi_schema.sh
```

## Architecture

### Backend Communication Flow

```
SwiftUI App → HTTP/REST → FastAPI (port 8765) → DuckDB/LanceDB
                                   → LangGraph (workflows)
                                   → LLM Providers (via LiteLLM)
```

The Swift app is a **pure UI layer** - all business logic, data persistence, and AI processing happens in the Python backend.

### Key Backend Modules

- **`api/main.py`**: FastAPI app with 23 core routes + 8 dev-tier routes (31 total). Active tier controlled by `FICHERO_FEATURE_TIER` env var (`release` | `dev`, default `release`).
  - **Core (always on):** activity, artifacts, batch, chat, claim-links, claims, documents, entities, folders, ingest, migrations, mcp-tools, multilingual, providers, review-queue, search, settings, sources, models, storage, tasks, workflow-execution, workflows
  - **Dev tier** (`FICHERO_FEATURE_TIER=dev`): knowledge-graph, search-explanation, hermeneutics, interpretations, graph-exploration, mind-palace, research, iiif
  - **Also dev-tier (staged features):** actions, chains, graph-reasoning, integrations, local-models, mcp-servers, model-comparison, orchestration, predictions, schedules, triggers
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
- **`llm.py`**: LangChain interface with LiteLLM for 100+ LLM providers
- **`providers.py`**: LLM provider definitions (local: Ollama, LM Studio, Apple Vision; commercial: OpenAI, Anthropic, Google)

### Key Swift Modules

**Entry Point:**
- **`FicheroApp.swift`** (223 lines): App lifecycle, backend startup, library manager, command menu structure, window management

**Models Layer (`Models/`, 29 files):**
- **`Document.swift`**: Core data model with DocType, FileType, Status enums
- **`DocumentStore.swift`** (185 lines): Document hierarchy, CRUD operations, file import, folder ingestion
- **`LibraryManager.swift`** (198 lines): Multi-library management, per-library service instances
- **`WorkflowTypes.swift`** (272 lines): Workflow definitions, nodes, edges, ports, input/output mapping
- **`SidebarItem.swift`** (184 lines): Navigation structure, hierarchical sidebar items
- **`FicheroDocument.swift`**: Per-window document state
- **`WorkflowStore.swift`**: Workflow list, create, update, duplicate, export operations

**Service Layer (`Services/`, 44 files):**
- **`APIClient.swift`** (396 lines): HTTP client with library path injection, per-window instances
- **16 Generated Services** (`*Generated.swift`): Auto-generated from OpenAPI (Workflow, Provider, Search, Chat, Document, etc.)
- **`WorkflowStreamService.swift`** (294 lines): Server-Sent Events for real-time workflow execution
- **`EmbeddedBackendService.swift`**: Backend process management
- **`ProviderService.swift`**: Provider validation wrapper around generated service

**Views Layer (`Views/`, 118 files in 14 feature domains):**
- **`ContentView.swift`**: Three-column layout with 5 extensions (State, ViewBuilders, Navigation, Actions, Persistence)
- **`DocumentTabView.swift`**: Per-window entry point, service initialization
- **`Sidebar/`** (14 files, 868 lines main): Multi-mode navigation (Library, Search, Chat, Workflows, Activity, Automation, Batches)
- **`Library/`** (13 files, 805 lines main): Document browser, grid/list/table views, inspector
- **`Workflow/`** (8 files, 1024-1136 lines main): Visual node editor canvas, workflow library, node configuration
- **`Chat/`** (7 files): RAG conversation interface
- **`Search/`** (3 files): Semantic search interface
- **`Activity/`** (12 files): Execution history and real-time progress
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

See `docs/architecture/swiftui/api_client.md` for detailed documentation

### Ingest System

The ingest module is a core feature for importing files into the library:

- **Dual modes**: LINK (bookmark-based, zero disk usage) or COPY (file import with APFS instant cloning)
- **37+ file types**: Documents (PDF, DOCX, TXT), images (JPG, PNG, RAW), audio, video, archives
- **Metadata extraction**: Automatic EXIF, file attributes, dimensions, duration
- **Text extraction**: Searchable text from PDFs, Office docs, images (OCR)
- **Folder processing**: Recursive ingestion with hierarchy preservation

See `docs/ingest_api.md` for detailed API documentation.

## Code Quality Standards

### Swift - 100% SwiftUI (MANDATORY)

**⚠️ CRITICAL: Pure SwiftUI - NO AppKit**

This project uses **100% SwiftUI**. We do NOT use:
- ❌ AppKit views or controls
- ❌ NSView wrapping or UIViewRepresentable
- ❌ NotificationCenter for state changes
- ❌ Manual `DispatchQueue.main` dispatching
- ❌ Custom drawing that can be done with SwiftUI

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

**Refactoring Status (Feb 2026):**
- 35/37 oversized files refactored to target sizes
- SwiftLint violations: 330 → 69
- See `agents/progress.md` for full tracker

**Other Requirements:**
- **SwiftLint is MANDATORY** - run before every commit
- Use `@StateObject` for owned state, `@EnvironmentObject` for dependency injection
- Use OSLog for logging (categories: `com.tubb.Fichero`)
- Cache expensive computations (don't rebuild hierarchies on every view update)
- Keyboard shortcuts: Ulysses-style (⌃⌘1-5 for sidebar modes, ⌘1-4 for view modes)

**Required Reading:** `docs/architecture/swiftui/SWIFTUI_PRINCIPLES.md` - Mandatory patterns and examples

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

### LiteLLM Integration

All LLM calls go through LangGraph. But, we use LiteLLM (`llm.py`), for:
- Automatic cost tracking
- Model capability detection

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

See `docs/architecture/swiftui/api_migration_guide.md` and `docs/architecture/swiftui/api_client.md` for current API-client cleanup context.

## Git Workflow

### Current Branch Context

**Active Branch:** `0.0.2` — all milestone work happens here. Commit directly; do not create per-task feature branches.

**Main Branch:** `main` — stable releases only. Never push to main without explicit approval.

### Commit Message Conventions

Follow conventional commits with these prefixes:
- `fix:` - Bug fixes, API migrations (29% of commits)
- `style:` - Linting, formatting, SwiftLint compliance (24%)
- `test:` - Test improvements, stability fixes (17%)
- `docs:` - Documentation updates (14%)
- `chore:` - Tooling, maintenance, build scripts (12%)
- `refactor:` - Code restructuring without behavior changes (2%)
- `feat:` - New features and capabilities (2%)

**Commit Message Format:**
```bash
<type>: <concise description focusing on "why" not "what">

# Good examples:
style: resolve schedule editor and action picker lint warnings
fix: replace deprecated coroutine callback check
test: align swift contract tests with generated workflow schema
docs: clarify backend script ownership and ignore local artifacts

# Bad examples:
fix: fixed stuff
update: changes
refactor: made it better
```

### Branching Strategy

- **Active branch:** `0.0.2` — all implementation work goes here
- **Main branch:** Always stable, ready for release — never push directly

### Pre-Commit Checklist for `0.0.2`

Run before each commit:
```bash
swiftlint lint fichero/fichero/
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived
PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/
```

### Pre-Commit Checklist

- [ ] SwiftLint passes with zero warnings
- [ ] Ruff passes with zero errors (`ruff check fichero-engine/src/ fichero-engine/tests/`)
- [ ] All tests pass (Python unit/integration + Swift tests)
- [ ] OpenAPI schema synced if backend API changed
- [ ] TODO.md updated with task status
- [ ] Commit message follows conventions
- [ ] No debug code or commented-out blocks
- [ ] File sizes within guidelines (< 400 lines recommended)

## Current Development Focus

**Branch `0.0.2`** consolidates all milestone work from 0.0.3–0.1.0 backend issues and SwiftUI bug fixes. See `STATE.md` for next session entry point and `HISTORY.md` for completed work log.

## AI Task Management System

This project uses GitHub for execution tracking.
Canonical location: GitHub Issues + Milestones + Project board.

### Task Management Workflow

1. **Pick from milestone queue**: choose from open issues in the active milestone
2. **Track execution in project**: set project item status (`Todo`/`In Progress`/`Done`)
3. **Keep issue state accurate**: move through open/closed with comments and linked PRs
4. **Use local state only for handoff**: `STATE.md` is continuity context, not roadmap authority

### Important Rules

- **GitHub is source of truth** for scope, prioritization, and status
- **Local planning files are non-authoritative** (`PLAN.md`, `TASKS.md`, `docs/agent-workflow/TODO.md`)
- **One task at a time** - complete fully before moving to next
- **Small, focused tasks** - break complex work into manageable pieces
- **Keep root clean** - put summaries and docs in task folders, not root

## Available MCP Tools for Claude Code

This project has the following MCP (Model Context Protocol) servers configured:

### Xcode Development (3 servers)

**1. XcodeBuildMCP** (`npx -y xcodebuildmcp@latest`) - Primary Xcode automation:

- **Project Discovery**: `discover_projs` - Find .xcodeproj and .xcworkspace files
- **Scheme Management**: `list_schemes` - List available build schemes
- **Build Settings**: `show_build_settings` - View xcodebuild configuration

**Building & Running:**
- `build_macos` - Build macOS app
- `build_run_macos` - Build and run macOS app
- `build_sim` - Build for iOS Simulator
- `build_run_sim` - Build and run on iOS Simulator
- `build_device` - Build for physical device
- `clean` - Clean build artifacts

**Testing:**
- `test_macos` - Run macOS tests
- `test_sim` - Run iOS Simulator tests
- `test_device` - Run tests on physical device

**Simulator Management:**
- `list_sims` - List available simulators
- `boot_sim` - Boot a simulator
- `open_sim` - Open Simulator.app
- `erase_sims` - Reset simulator state
- `screenshot` - Capture simulator screenshot
- `record_sim_video` - Record simulator video

**Simulator Interaction:**
- `describe_ui` - Get UI hierarchy with coordinates (use before UI automation)
- `tap` - Tap at coordinates or by accessibility id/label
- `swipe` - Swipe between coordinates
- `type_text` - Type text into focused field
- `button` - Press hardware buttons (home, lock, siri, etc.)
- `gesture` - Perform preset gestures (scroll, swipe from edge)
- `set_sim_appearance` - Toggle dark/light mode
- `set_sim_location` - Set GPS coordinates

**App Management:**
- `get_mac_bundle_id` / `get_app_bundle_id` - Extract bundle identifier
- `launch_mac_app` / `launch_app_sim` - Launch applications
- `stop_mac_app` / `stop_app_sim` - Stop running apps
- `install_app_sim` - Install app on simulator

**Device Support:**
- `list_devices` - List connected physical devices
- `run_on_device` - Build and run on physical device
- `install_app_device` - Install app on device
- `launch_app_device` - Launch app on device

**Logging:**
- `start_sim_log_cap` / `stop_sim_log_cap` - Capture simulator logs
- `start_device_log_cap` / `stop_device_log_cap` - Capture device logs

**Swift Package Manager:**
- `swift_package_build` - Build Swift packages
- `swift_package_run` - Run executable targets
- `swift_package_test` - Run package tests
- `swift_package_clean` - Clean package artifacts

**Project Scaffolding:**
- `scaffold_ios_project` - Create new iOS project from templates
- `scaffold_macos_project` - Create new macOS project from templates

**Session Management:**
- `session-set-defaults` - Configure default project/workspace, scheme, simulator
- `session-show-defaults` - View current session settings
- `session-clear-defaults` - Clear session configuration

**2. xcode-mcp** (`npx -y @devyhan/xcode-mcp`) - Additional Xcode utilities:
- `xcode-project-info` - Get project/workspace information
- `xcode-build` - Build with custom configurations
- `xcode-test` - Run tests with advanced options
- `xcode-archive` - Create archives and export IPAs
- `xcode-codesign-info` - View code signing details
- `xcode-list-schemes` - List available schemes
- `swift-package-manager` - SPM commands (init, update, resolve, reset, clean)
- `simctl-manager` - Direct simulator control (list, create, boot, shutdown, erase, install, launch, delete)
- `run-on-device` - Comprehensive device deployment with environment variables and logging

**3. sosumi** (`https://sosumi.docs/agent-workflow/mcp`) - Official Apple documentation:
- `searchAppleDocumentation` - Search Apple Developer docs
- `fetchAppleDocumentation` - Fetch docs by path (Swift, SwiftUI, HIG)

**IMPORTANT**: Use Sosumi MCP BEFORE implementing custom SwiftUI solutions!
Examples:
- Finding SwiftUI drag & drop APIs: `searchAppleDocumentation("swiftui drag drop")`
- Learning NavigationSplitView: `searchAppleDocumentation("NavigationSplitView")`
- Checking HIG guidelines: `searchAppleDocumentation("human interface guidelines color")`
- Then fetch full doc: `fetchAppleDocumentation("path/from/search/result")`

### App Store & Distribution

**app-store-connect** (`npx -y appstore-connect-mcp-server`) - App Store Connect integration:
- Manage app metadata, builds, and releases
- Access TestFlight and App Store submission workflows
- Query app analytics and sales data

### File System Operations

**filesystem** (`@modelcontextprotocol/server-filesystem`) - Scoped to `/Users/danieltubb/code/fichero-0.0.2/`:
- `read_text_file` - Read file contents (supports head/tail)
- `read_multiple_files` - Read multiple files efficiently
- `write_file` - Create or overwrite files
- `edit_file` - Line-based edits with diff preview
- `create_directory` - Create directories
- `list_directory` - List directory contents
- `directory_tree` - Recursive JSON tree view
- `search_files` - Glob pattern file search
- `get_file_info` - File metadata and stats
- `move_file` - Move or rename files

### Knowledge Management

**memory** (`@modelcontextprotocol/server-memory`) - Persistent knowledge graph:
- `create_entities` - Store project entities (people, concepts, patterns)
- `create_relations` - Link related concepts with typed relationships
- `add_observations` - Add details and notes to existing entities
- `delete_entities` / `delete_relations` / `delete_observations` - Remove outdated info
- `search_nodes` - Search knowledge graph by query
- `open_nodes` - Retrieve specific entities by name
- `read_graph` - View entire knowledge graph
- **Use for**: Remembering architectural decisions, user preferences, recurring patterns

### AI & Reasoning

**sequential-thinking** (`@modelcontextprotocol/server-sequential-thinking`) - Advanced problem-solving:
- `sequentialthinking` - Break down complex problems with iterative reasoning
- Supports branching, revision, hypothesis generation/verification
- **Use for**: Multi-step technical analysis, debugging complex issues, architectural planning

### Utilities

**time-server** (`python -m mcp_server_time`) - Configured for America/Halifax timezone:
- `get_current_time` - Get current time in any IANA timezone
- `convert_time` - Convert times between timezones

### Reference Documentation (MCP)

**Ref** - Search documentation from web, GitHub, private resources:
- `ref_search_documentation` - Search for docs (include language/framework in query)
- `ref_read_url` - Read documentation page as markdown

**Examples:**
- Swift language features: `ref_search_documentation("Swift @Observable macro")`
- SwiftUI patterns: `ref_search_documentation("SwiftUI MVVM pattern")`
- Third-party libraries: `ref_search_documentation("Swift Combine framework")`

### Local Documentation

The `docs/` folder contains detailed API documentation:
- `ingest_api.md` - File ingestion API reference
- `ingest_best_practices.md` - Ingestion patterns and recommendations
- `ingest_overview.md` - High-level system overview
- `supported_file_types.md` - Complete list of supported file formats

### Disconnected Servers

- **github** - Currently not connected (authentication required)

### Typical Swift Development Workflow

1. **Session setup**: `session-set-defaults` with projectPath, scheme, simulatorName
2. **Build**: `build_sim` or `build_macos`
3. **Run**: `build_run_sim` or `build_run_macos`
4. **Test**: `test_sim` or `test_macos`
5. **UI automation**: `describe_ui` → `tap`/`swipe`/`type_text`
6. **Debug**: `start_sim_log_cap` → reproduce issue → `stop_sim_log_cap`

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
      └── ... (16 other generated services)

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
3. **Generated Services:** 16 `*Generated.swift` files wrap generated client with typed methods
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
- **TODO.md updates**: NEVER rewrite entire file - use targeted search/replace edits only
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
- **`docs/CLAUDE.md`** (this file) - Canonical agent guidance
- **`docs/architecture/swiftui/SWIFTUI_PRINCIPLES.md`** - MANDATORY SwiftUI patterns (18KB)
- **`docs/architecture/swiftui/api_migration_guide.md`** - OpenAPI client migration guide
- **`docs/architecture/swiftui/development_standards.md`** - File size limits, Swift 6 guidelines
- **`docs/architecture/api/development_standards.md`** - Backend development standards
- **`docs/agent-workflow/TODO.md`** - Master task list
- **`docs/agent-workflow/workflows/INBOX_WORKFLOW.md`** - Task processing workflow
- **`README.md`** - User-facing setup and run instructions

### Critical Swift Files (Frequently Modified)
- **`FicheroApp.swift`** (223 lines) - App lifecycle, menu structure
- **`DocumentStore.swift`** (185 lines) - Document CRUD, state management
- **`LibraryManager.swift`** (198 lines) - Multi-library orchestration
- **`APIClient.swift`** (396 lines) - HTTP client with library path injection
- **`ContentView.swift`** - Three-column layout (split into 5 extensions)
- **`WorkflowTypes.swift`** (272 lines) - Workflow data models

### Critical Python Files (Backend)
- **`fichero-engine/src/fichero/api/main.py`** - FastAPI app, route registration
- **`fichero-engine/src/fichero/db.py`** - Database layer (DuckDB + LanceDB)
- **`fichero-engine/src/fichero/models.py`** - Pydantic models (source of truth)
- **`fichero-engine/src/fichero/workflows/registry.py`** - Tool registry (30+ tools)
- **`fichero-engine/src/fichero/workflows/executor.py`** - Workflow execution with streaming
- **`fichero-engine/src/fichero/ingest.py`** - File ingestion pipeline

### Generated Files (DO NOT EDIT MANUALLY)
- **`fichero/fichero-api-client/`** - Generated Swift OpenAPI client
- **`fichero/Services/*Generated.swift`** - 16 generated service wrappers
- **`fichero-engine/tests/contracts/openapi.json`** - OpenAPI schema (regenerated from Python)

### Refactoring Complete
All 35 oversized files refactored to target sizes (completed Feb 2026).

## Additional Resources

### Architecture Documentation
Full architectural context is in `docs/architecture/`:

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
- **`docs/ingest_api.md`** - File ingestion API reference
- **`docs/ingest_best_practices.md`** - Ingestion patterns
- **`docs/supported_file_types.md`** - 37+ supported file formats
- **`docs/BUNDLING_BACKEND.md`** - Backend deployment strategy

### Manual QA
- **`docs/qa_matrix.md`** - View-by-view manual testing checklist

---

**Note:** This document is the canonical source of agent guidance. When in doubt, refer to the architecture documentation in `docs/architecture/` for detailed implementation patterns and examples.
