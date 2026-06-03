# Fichero

Document management and AI processing for macOS. One engine, many surfaces.

## Architecture

Fichero is a single backend engine ("engine is logic; clients are display surfaces") with multiple thin clients on top of it.

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  SwiftUI app     │  │  fichero CLI     │  │  MCP server      │
│  (fichero/)      │  │  (fichero-engine/src/fichero/cli/)  │  │  (planned)       │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                     │
         └─────────────────────┴─────────────────────┘
                              │
                  HTTP localhost:8765
                              │
                              ▼
              ┌──────────────────────────────┐
              │  FastAPI engine              │
              │  (fichero-engine/src/fichero)│
              └──┬─────────┬─────────┬───────┘
                 │         │         │
                 ▼         ▼         ▼
           ┌─────────┐ ┌────────┐ ┌─────────┐
           │ DuckDB  │ │LangGr. │ │ LiteLLM │
           │+Lance   │ │workflw │ │100+ LLMs│
           └─────────┘ └────────┘ └─────────┘
```

### Surfaces

All surfaces are thin clients on the engine. They render and accept input; they do not contain logic.

| Surface | Path | Status |
|---|---|---|
| SwiftUI app | `fichero/` (Xcode project: `fichero/fichero.xcodeproj`) | Live |
| `fichero` CLI | `fichero-engine/src/fichero/cli/` | Live (typed, end-to-end verified) |
| MCP server | `fichero-engine/` (planned / in flight) | Coming |
| iPad app | future | Planned |
| Web client | future | Planned |

### Example Workflow: Catalogue

```
[Files] ──▶ [Loaders] ──▶ [Transcribe] ──▶ [Extract Entities] ──┬──▶ [Timelines]
              pdf/img       (vision)        people/places/       │
              docx/txt                      dates/orgs           ├──▶ [Keywords]
                                                                 │
                                                                 ├──▶ [Events]
                                                                 │
                                                                 └──▶ [Summarize]
                                                                          │
                                                                          ▼
                                                                    [Catalogue]
                                                                          │
                                         ┌────────────────┬───────────────┼───────────────┐
                                         ▼                ▼               ▼               ▼
                                   [Save to         [To Word]      [To JSON]      [To PDF]
                                    Library]
```

## Running

**Start the backend:**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765
```

**Run the SwiftUI app:**
Open `fichero/fichero.xcodeproj` in Xcode and run.

To launch an already-built `.app` from the terminal, use the helper — **not**
a direct exec of the binary:
```bash
scripts/launch-release.sh            # Release build
scripts/launch-release.sh --debug    # Debug build
```
> **Debugging note (#760):** direct-exec'ing the binary
> (`./fichero/build/xcode/Products/Release/Fichero.app/Contents/MacOS/Fichero &`)
> from a terminal does **not** draw a window on macOS 26 — AppKit's scene
> activation runs but nothing appears, and the embedded engine never spawns.
> This is a known macOS behavior for GUI apps exec'd by a non-Aqua parent.
> Launch through `open` (which the helper does) or via Finder/Spotlight/Dock.
> App logs go to the unified log: `log stream --predicate 'process == "Fichero"'`.

**Use the CLI (against a running backend):**
```bash
fichero --help
fichero workflow list
```

**Lint the SwiftUI app:**
```bash
swiftlint lint fichero/fichero/
```

## Features

- **Library**: Hierarchical document storage with collections
- **Search**: Semantic search via LanceDB embeddings
- **Chat**: RAG-based document Q&A
- **Workflows**: Visual node editor for document processing pipelines (LangGraph)
- **Knowledge Graph**: Entities, claims, and relationships extracted from documents (backend-owned; surfaces render)
- **Ingest**: Comprehensive file ingestion with 37+ supported formats
- **CLI / MCP**: Engine endpoints driven from terminal and (soon) MCP-aware agents

## Ingest Module

The ingest module provides powerful file import capabilities:

- **Dual Modes**: LINK (bookmark-based) or COPY (file import) modes
- **37+ File Types**: Support for documents, images, audio, video, and more
- **Metadata Extraction**: Automatic extraction of file metadata and EXIF data
- **Text Extraction**: Searchable text extraction from PDFs, Word docs, and more
- **APFS Optimization**: Instant file copying using macOS APFS cloning
- **Folder Processing**: Recursive folder ingestion with hierarchy preservation

**Documentation:**
- [Ingest Overview](docs/ingest_overview.md)
- [Supported File Types](docs/supported_file_types.md)
- [API Documentation](docs/ingest_api.md)
- [Best Practices](docs/ingest_best_practices.md)

**Quick Start:**
```python
from fichero.ingest import ingest_file, ingest_folder, IngestMode

# Single file
doc = ingest_file(Path("/path/to/document.pdf"), extract_text=True)

# Folder with progress
docs = ingest_folder(
    Path("/path/to/folder"),
    mode=IngestMode.COPY,
    recursive=True,
    on_progress=lambda current, total: print(f"{current}/{total}")
)
```

## Project Structure

- `fichero-engine/` — FastAPI backend, workflow runner, KG, ingest ([README](fichero-engine/README.md))
- `fichero/` — SwiftUI app, Xcode project, and `fichero` CLI under `fichero-engine/src/fichero/cli/`
- `docs/agent-workflow/` — Agent workflow docs, task list, and templates

### Top-level folder ownership

- `runtime`: `fichero-engine/`, `fichero/`
- `generated/local`: `.build/`, `build/`, `dist/`, `logs/`, `fichero/derived_data/`
- `reference`: `docs/`

### Python Backend (`fichero-engine/src/fichero/`)

```
api/               # FastAPI routes (documents, search, chat, workflows, kg, providers)
workflows/         # LangGraph engine, tool registry, builder
kg/                # Knowledge graph: entities, claims, aggregation
loaders/           # Text extraction (pdf, docx, images, etc.)
db.py              # DuckDB + LanceDB storage
models.py          # Pydantic models
ingest.py          # File ingestion pipeline
storage.py         # Thumbnails, file storage
llm.py             # LangChain LLM interface
providers.py       # LLM provider definitions
keychain.py        # macOS keychain for API keys
bookmarks.py       # macOS security-scoped bookmarks
resources/         # Config defaults, locales
```

### SwiftUI App (`fichero/fichero/`)

```
Views/             # ~234 files across ~19 feature domains
├── ContentView.swift (+5 ext)  # Resizable multi-pane reading layout
├── Sidebar/        # Multi-mode nav: Library, Search, Chat, Workflows, Activity, …
├── Library/        # Document browser + PDF reading view + inspector V2 (tabbed)
├── KnowledgeGraph/ # Entity/claim digests, graph views
├── Chat/           # RAG conversation UI
├── Workflow/       # Visual node editor, canvas
└── Search/ Activity/ Settings/ AIProviders/ Automation/ …

Services/          # ~49 files: APIClient + 14 *Generated.swift (OpenAPI) + wrappers
Models/            # ~42 Swift data models
App/               # FicheroApp entry, AppState, window scaffolding
```

### CLI (`fichero-engine/src/fichero/cli/`)

Typed Python CLI mirroring the engine's HTTP surface. Used as the engine-quality comparison loop against the SwiftUI app — every endpoint reachable from the app should be reachable from the CLI.

## Tests

```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ \
  --ignore=fichero-engine/tests/unit/_archived
```

## Local cleanup

```bash
./fichero-engine/scripts/clean_local_artifacts.sh
```

## Validation

```bash
./fichero-engine/scripts/validate_repo.sh
```

See `docs/VALIDATION.md` for details and current known blockers.
