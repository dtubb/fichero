# Fichero

Document management and AI processing for macOS. Organize, search, chat, and run AI workflows on documents.

## Architecture

```
┌─────────────────┐         ┌─────────────────┐        ┌─────────────────┐
│  Swift UI App   │────────▶│  Python API     │        │    LiteLLM      │
│  library/browser│         │  (FastAPI)      │        │(prices/models/  │
│  metadata/search│         └────────┬────────┘        │ provider info)  │
│  chat/workflows │                  │                 └─────────────────┘
│  activity/compare│                 │
└─────────────────┘                  │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
        ▼                            ▼                            ▼
┌───────────────┐          ┌─────────────────┐          ┌─────────────────┐
│ DuckDB+Lance  │          │    LangGraph    │          │    LangChain    │
│ (storage)     │          │   (workflows)   │          │  (llm calls)    │
│               │          │  visual node    │          │                 │
│               │          │    editor       │          │                 │
└───────┬───────┘          └────────┬────────┘          └────────┬────────┘
        │                           │                            │
        ▼                           ▼                            ▼
┌───────────────┐          ┌─────────────────┐          ┌─────────────────┐
│  FastEmbed    │          │  Tool Registry  │          │  LLM Providers  │
│ (embeddings)  │          │ vision/transform│          ├─────────────────┤
└───────────────┘          │ llm/convert     │          │ Local:          │
                           │ logic/conditions│          │  Apple Vision   │
                           └─────────────────┘          │  Ollama/LMStudio│
                                                        │  Hugging Face   │
                                                        ├─────────────────┤
                                                        │ Commercial:     │
                                                        │  OpenAI/Anthropic│
                                                        │  Google/Groq/etc│
                                                        └─────────────────┘
```

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
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765
```

**Run the Swift app:**
Open `fichero-swiftui/fichero-swiftui.xcodeproj` in Xcode and run.

**Lint the Swift app:**
```bash
swiftlint lint fichero-swiftui/fichero-swiftui/
```

## Features

- **Library**: Hierarchical document storage with collections
- **Search**: Semantic search via LanceDB embeddings
- **Chat**: RAG-based document Q&A
- **Workflows**: Visual node editor for document processing pipelines
- **Ingest**: Comprehensive file ingestion with 37+ supported formats

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

- `fichero-api/` - Backend package and Briefcase config ([README](fichero-api/README.md))
- `fichero-swiftui/` - SwiftUI app and Xcode project ([README](fichero-swiftui/README.md))
- `ai/` - Canonical AI task/workflow workspace

### Top-level folder ownership

- `runtime`: `fichero-api/`, `fichero-swiftui/`
- `generated/local`: `.build/`, `build/`, `dist/`, `logs/`, `fichero-swiftui/derived_data/`
- `reference`: `docs/`, `ai/`
- `archive/delete-candidate`: moved under `/Users/danieltubb/code/fichero_main/to-delete/`

### Python Backend (`fichero-api/src/fichero/`)

```
api/               # FastAPI routes (documents, search, chat, workflows, providers)
workflows/         # LangGraph engine, tool registry, builder
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

### Swift App (`fichero-swiftui/fichero-swiftui/`)

```
Views/
├── ContentView.swift      # Main 3-column layout
├── Sidebar/               # Library, search, chat, workflow sections
├── Browser/               # Document grid/list/table views
├── Inspector/             # Metadata, preview
├── Chat/                  # RAG conversation UI
└── Workflow/              # Visual node editor, canvas, inspector

Services/          # API client, document store, providers
Models/            # Swift data models
Resources/         # Assets, config
```

## Tests

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived
```

## Local cleanup

```bash
./fichero-api/scripts/clean_local_artifacts.sh
```

## Validation

```bash
./fichero-api/scripts/validate_repo.sh
```

See `docs/VALIDATION.md` for details and current known blockers.
