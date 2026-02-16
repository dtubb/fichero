# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fichero is a macOS document management application with AI processing capabilities. It uses a **hybrid architecture**:
- **Swift/SwiftUI frontend** (`fichero-swiftui/`) for the native macOS app
- **Python/FastAPI backend** (`fichero-api/src/fichero/`) for document processing, AI workflows, and data storage
- **Dual database system**: DuckDB for metadata + LanceDB for vector embeddings

## Development Commands

### Backend (Python FastAPI)

```bash
# Start the FastAPI backend server (required for Swift app to function)
cd /Users/danieltubb/code/fichero_main/fichero
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765
```

The backend must be running on port 8765 before launching the Swift app.

### Frontend (Swift/SwiftUI)

```bash
# Build the Swift app
xcodebuild -project fichero-swiftui/Fichero.xcodeproj -scheme Fichero -configuration Debug

# Run SwiftLint (code quality)
swiftlint lint --path fichero-swiftui/fichero-swiftui/
```

**Preferred method**: Open `fichero-swiftui/Fichero.xcodeproj` in Xcode and run (⌘R).

### Testing

```bash
# Python unit tests (ignore archived tests)
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived

# Swift tests (run from Xcode or command line)
xcodebuild test -project fichero-swiftui/Fichero.xcodeproj -scheme Fichero
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

- **`api/main.py`**: FastAPI app with 8 route modules (documents, search, chat, workflows, providers, models, ingest, storage)
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

- **`FicheroApp.swift`**: Main app entry point with menu bar commands and keyboard shortcuts
- **`Views/ContentView.swift`**: 3-column layout (Sidebar | Browser | Inspector)
- **`Views/Sidebar/`**: Multi-mode sidebar (Navigate, Search, Chat, Workflows, Activity)
- **`Views/Workflow/`**: Visual node editor for building LangGraph workflows
- **`Services/`**: API client communicating with FastAPI backend
- **`Models/`**: Swift data models mirroring Python Pydantic models
- **`FicheroAPIClient/`**: Generated type-safe API client (local Swift package)

### Swift API Client (OpenAPI Generator)

The Swift frontend uses **Apple's Swift OpenAPI Generator** to create type-safe API clients from the Python backend's OpenAPI schema. This ensures Swift and Python stay in sync.

**Key files:**
- `fichero-swiftui/FicheroAPIClient/` - Local Swift package with generated client
- `fichero-api/tests/contracts/openapi.json` - OpenAPI schema (source of truth)
- `fichero-api/scripts/sync_openapi_schema.sh` - Syncs schema from Python to Swift

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
./fichero-api/scripts/sync_openapi_schema.sh
```

See `ai/contexts/frontend/api_client.md` for detailed documentation

### Ingest System

The ingest module is a core feature for importing files into the library:

- **Dual modes**: LINK (bookmark-based, zero disk usage) or COPY (file import with APFS instant cloning)
- **37+ file types**: Documents (PDF, DOCX, TXT), images (JPG, PNG, RAW), audio, video, archives
- **Metadata extraction**: Automatic EXIF, file attributes, dimensions, duration
- **Text extraction**: Searchable text from PDFs, Office docs, images (OCR)
- **Folder processing**: Recursive ingestion with hierarchy preservation

See `docs/ingest_api.md` for detailed API documentation.

## Code Quality

### Swift

**⚠️ CRITICAL: 100% SwiftUI - NO AppKit**

- **Pure SwiftUI Only**: Do NOT use AppKit views, NSView wrapping, or AppKit controls
- **Before using AppKit**: Check Sosumi MCP for SwiftUI equivalent, verify it's truly unavoidable
- **Use MCP Tools for Documentation**:
  - `sosumi.searchAppleDocumentation()` - Official Apple SwiftUI docs
  - `ref.searchDocumentation()` - Swift language reference
- **No NotificationCenter**: Use `@FocusedValue` for menu commands (see `ai/contexts/frontend/SWIFTUI_PRINCIPLES.md`)
- **Cache Expensive Work**: Don't rebuild hierarchies on every view update
- **Handle Cancellation**: All `.task {}` blocks must check `Task.isCancelled`
- **SwiftLint is configured and required** - run before committing Swift changes
- Use `@StateObject` for view models, `@EnvironmentObject` for app-wide state
- Use `@MainActor` for UI updates (not `DispatchQueue.main`)
- Keep view files < 300 lines, use `@ViewBuilder` on computed views
- Use OSLog for logging (not NSLog or print)
- Keyboard shortcuts follow Ulysses-style conventions (⌃⌘1-5 for sidebar modes, ⌘1-4 for view modes)

**Required Reading**: `ai/contexts/frontend/SWIFTUI_PRINCIPLES.md` - Mandatory SwiftUI patterns

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

In LINK mode, the app uses macOS security-scoped bookmarks (`bookmarks.py`) to maintain access to files outside the sandbox. This requires proper entitlements in `fichero-swiftui/fichero-swiftui/Fichero.entitlements`.

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

See `ai/tasks/TODO-125/` and `ai/tasks/TODO-126/` for current cleanup tasks.

## AI Task Management System

This project uses a structured task management system in the `ai/` folder for organizing development work.

### Directory Structure

```
ai/
├── TODO.md                  # Master task list (never rewrite from scratch)
├── AI_README.md             # Quick start guide for AI agents
├── inbox/                   # New ideas before becoming tasks
├── tasks/                   # Individual task folders (TODO-XXX/)
│   └── TODO-XXX/
│       ├── task.md          # Step-by-step instructions
│       ├── context.md       # Background information
│       └── summaries/       # Completion reports
├── workflows/               # Process documentation
│   ├── INBOX_WORKFLOW.md    # How to process inbox items
│   └── TASK_WORKFLOW.md     # How to execute tasks
├── contexts/                # System architecture documentation
└── templates/               # Templates for new tasks
```

### Task Management Workflow

1. **Check inbox first**: `ls ai/inbox/` - if files exist, process them via `ai/workflows/INBOX_WORKFLOW.md`
2. **Pick a task**: Choose from `ai/TODO.md` - tasks marked `[ ]` are available
3. **Follow task file**: Each task has a `task.md` with step-by-step instructions
4. **Update status**: Change `[ ]` to `[>]` when starting, `[x]` when complete
5. **Save summaries**: Document completion in `tasks/TODO-XXX/summaries/`

### Important Rules

- **NEVER rewrite TODO.md from scratch** - always use search/replace or careful edits
- **Don't reorder tasks** - preserve existing structure
- **One task at a time** - complete fully before moving to next
- **Small, focused tasks** - break complex work into manageable pieces
- **Keep root clean** - put summaries and docs in task folders, not root

### Task Status Legend

- `[ ]` = Available (ready to implement)
- `[>]` = In Progress (currently working on)
- `[x]` = Completed (done, kept for reference)
- `[!]` = Blocked (dependent on other tasks)

### Priority Levels

- `P0` = Critical path, must be done immediately
- `P1` = High priority, should be done soon
- `P2` = Medium priority, can wait
- `P3` = Low priority, nice to have

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

**3. sosumi** (`https://sosumi.ai/mcp`) - Official Apple documentation:
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

**filesystem** (`@modelcontextprotocol/server-filesystem`) - Scoped to `/Users/danieltubb/code/fichero_main/fichero/`:
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

## Common Pitfalls

- **Port conflicts**: Backend must run on port 8765 (hardcoded in Swift app)
- **PYTHONPATH**: Must be set to `src` when running backend or tests
- **Archived tests**: Always ignore `fichero-api/tests/unit/_archived` directory
- **SwiftUI state**: Use `@MainActor` for view models that update UI state
- **Workflow parameters**: Always validate parameter types match tool expectations
- **TODO.md updates**: Never rewrite the entire file - use targeted edits only
- **Session defaults**: Set project/workspace and scheme with `session-set-defaults` before using build tools
- **UI automation**: Always use `describe_ui` to get precise coordinates - never guess from screenshots
