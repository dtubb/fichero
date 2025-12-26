# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fichero is a macOS document management application with AI processing capabilities. It uses a **hybrid architecture**:
- **Swift/SwiftUI frontend** (`Fichero/`) for the native macOS app
- **Python/FastAPI backend** (`src/fichero/`) for document processing, AI workflows, and data storage
- **Dual database system**: DuckDB for metadata + LanceDB for vector embeddings

## Development Commands

### Backend (Python FastAPI)

```bash
# Start the FastAPI backend server (required for Swift app to function)
cd /Users/dtubb/code/fichero_main/fichero
PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --port 8765
```

The backend must be running on port 8765 before launching the Swift app.

### Frontend (Swift/SwiftUI)

```bash
# Build the Swift app
xcodebuild -project Fichero/Fichero.xcodeproj -scheme Fichero -configuration Debug

# Run SwiftLint (code quality)
swiftlint lint --path Fichero/Fichero/
```

**Preferred method**: Open `Fichero/Fichero.xcodeproj` in Xcode and run (⌘R).

### Testing

```bash
# Python unit tests (ignore archived tests)
PYTHONPATH=src .venv/bin/pytest tests/unit/ --ignore=tests/unit/_archived

# Swift tests (run from Xcode or command line)
xcodebuild test -project Fichero/Fichero.xcodeproj -scheme Fichero
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

- **SwiftLint is configured and required** - run before committing Swift changes
- Follow existing patterns in `SidebarView.swift` for hierarchical UI components
- Use `@StateObject` for view models, `@EnvironmentObject` for app-wide state
- Keyboard shortcuts follow Ulysses-style conventions (⌃⌘1-5 for sidebar modes, ⌘1-4 for view modes)

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

In LINK mode, the app uses macOS security-scoped bookmarks (`bookmarks.py`) to maintain access to files outside the sandbox. This requires proper entitlements in `Fichero/Fichero.entitlements`.

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

## Common Pitfalls

- **Port conflicts**: Backend must run on port 8765 (hardcoded in Swift app)
- **PYTHONPATH**: Must be set to `src` when running backend or tests
- **Archived tests**: Always ignore `tests/unit/_archived` directory
- **SwiftUI state**: Use `@MainActor` for view models that update UI state
- **Workflow parameters**: Always validate parameter types match tool expectations
- **TODO.md updates**: Never rewrite the entire file - use targeted edits only
