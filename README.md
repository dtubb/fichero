# Fichero

*Fichero*, which is Spanish for a filing cabinet or a card index, is an application to manage documents, to read them, and to process them with AI tools for macOS, iPadOS, and iOS. Its audience is researchers with a collection of images of primary sources, historical documents, PDFs of books and articles, archival materials, handwritten fieldwork notes, audio interviews, video recordings, and other sources such as maps and photographs. It offers a single home for research materials, and then a way to build a semantic understanding using AI tools, to allow researchers to read, transcribe, and ask questions of their materials, while always being able to easily find the relevant source document. Fichero aims to let you build the steps yourself, for example visually, repeatably, across a whole corpus, and to work with a collection. It moves beyond a chat box as a kind of delphic opaque agent, to make visible how AI tools work. The aim is that the AI becomes a tool for the researcher, rather than a plagiarism machine or oracle of truth. Fichero offers tools to surface facts and provenance, but it does not do the interpretation.

Fichero is built primarily for historians, anthropologists, archivists and others in the humanities who work with handwritten documents, archival materials, and ethnographic materials. It allows you to deploy transcription with vision AI models, catalogue production using different workflows, and is ultimately a tool for letting anyone use large language models in a programmatic, methodical, step-by-step way over tens or hundreds of thousands of documents.

Fichero is a work in progress. At its core, it's an app that lets you use
cutting-edge machine-learning techniques and prompts in a repeatable,
programmatic way on documents.

It is built it to do transcription of handwritten documents using vision language
models, and to produce catalogues. However, this approach could be used for other
tasks. The basic idea: rather than having an AI control how things are done, in
ways that are harder to understand, Fichero gives you, the user, ways
visually build these steps yourself. It also gives you a vector database, a
knowledge graph, an ontological layer, MCP tools, etc.

Under the hood, the Fichero app talks to fichero-engine, a server that connects to a
DuckDB database. It is a tool to experiment with using large language models in a programmatic, methodological,
step-by-step way that helps you with your work.

Fichero is model-agnostic. It works with open-source models as well as
commercial providers, you only need to get yourself an API key. If you want to
run models locally, you can. 

The aim of Fichero is to move beyond the chat, and beyond the agentic model. It aims to let you give you more control and insight into how AI does its work: steps you want to be
able to reproduce across multiple documents. This is an app that aims to make the
power of AI accessible, but also searchable and readable. AIs are incredibly
powerful; the aim here is to make them more navigable and transparent. Transparent to you as a user, but also to you as you explain your methods to other people.

Too much AI work is invisible, hidden in opaque websites, with a distant database, where it is hard to know what is going on under the covers. Fichero aims to make how it works more visible, and therefore more accessible.

Fichero is a work in progress. It is 100% coded by Claude, Codex, and other models.

**One engine, many surfaces.**

## Installing and using Fichero

Fichero is a Mac app, with an iPad and iPhone app in the same project (in progress).

1. **Download** the latest Alpha for macOS from the
   [releases page](https://github.com/dtubb/fichero-releases/releases/latest).
2. **Requirements:** macOS 26 Tahoe or later, on Apple Silicon (M1 or later).
3. **Open it**, create a library, and import your documents by dragging files
   and folders in. The embedded engine starts automatically, so there is no
   server to install.

From there you read and transcribe sources, search by meaning, extract entities,
and run workflows across a whole collection. The user manual walks through every
part of the app:

- [Getting Started](docs/user/getting-started.md): create a library and learn the window.
- [The Interface (Window Tour)](docs/user/interface-tour.md): every major UI element.
- [Importing Documents](docs/user/importing-documents.md), [Reading & Editing](docs/user/reading-and-editing.md), [Search & Knowledge Graph](docs/user/search-knowledge-graph.md), and [AI & Privacy](docs/user/ai-and-privacy.md).

Fichero is Alpha software in active daily development. Keep originals of anything
you import, and treat each release as an experiment.

## Architecture

fichero-engine is a single server that holds the logic; the Fichero app and the other surfaces sit on top of it and display what it returns.

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  SwiftUI app     │  │  fichero CLI     │  │  MCP server      │
│  (fichero/)      │  │  (fichero-engine/src/fichero/cli/)  │  │  (fichero-mcp)   │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                     │
         └─────────────────────┴─────────────────────┘
                              │
              HTTPS 127.0.0.1:8765  (TLS, pinned fail-closed)
                              │
                              ▼
              ┌──────────────────────────────┐
              │  fichero-engine (FastAPI)    │
              │  (fichero-engine/src/fichero)│
              └──┬─────────┬─────────┬───────┘
                 │         │         │
                 ▼         ▼         ▼
           ┌─────────┐ ┌────────┐ ┌─────────┐
           │ DuckDB  │ │LangGr. │ │LangChain│
           │+Lance   │ │workflw │ │100+ LLMs│
           └─────────┘ └────────┘ └─────────┘
```

> LLM calls go through LangChain provider integrations (one per provider).
> LiteLLM is used **only** for model discovery and cost/pricing, not for
> routing or inference.

### Surfaces

All surfaces sit on top of fichero-engine. They render and accept input; they do not contain logic.

| Surface | Path | Status |
|---|---|---|
| SwiftUI app (macOS) | `fichero/` (Xcode project: `fichero/fichero.xcodeproj`) | Live |
| `fichero` CLI | `fichero-engine/src/fichero/cli/` | Live (typed, end-to-end verified) |
| MCP server | `fichero-engine/src/fichero/mcp_server.py` (`fichero-mcp`) | Live |
| iOS / iPad app | `fichero/fichero/FicheroApp_iOS.swift` (same project) | In progress |

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

## Building from source (for developers)

Most people should just download the app (see [Installing and using
Fichero](#installing-and-using-fichero) above). This section is for working on
Fichero itself.

**Start fichero-engine** (serves HTTPS on `127.0.0.1:8765`; the app pins it fail-closed, so a plain-HTTP engine cannot connect):
```bash
bash fichero-engine/scripts/start_backend.sh
```

**Run the SwiftUI app:**
Open `fichero/fichero.xcodeproj` in Xcode and run.

To launch an already-built `.app` from the terminal, use the helper, **not**
a direct exec of the binary:
```bash
scripts/launch-release.sh            # Release build
scripts/launch-release.sh --debug    # Debug build
```
> **Debugging note (#760):** direct-exec'ing the binary
> (`./fichero/build/xcode/Products/Release/Fichero.app/Contents/MacOS/Fichero &`)
> from a terminal does **not** draw a window on macOS 26; AppKit's scene
> activation runs but nothing appears, and the embedded engine never spawns.
> This is a known macOS behavior for GUI apps exec'd by a non-Aqua parent.
> Launch through `open` (which the helper does) or via Finder/Spotlight/Dock.
> App logs go to the unified log: `log stream --predicate 'process == "Fichero"'`.

**Use the CLI (against a running fichero-engine):**
```bash
fichero --help
fichero workflow list
```

**Lint the SwiftUI app:**
```bash
swiftlint lint fichero/fichero/
```

## Releases

The release lane is documented in [docs/release/release-lane.md](docs/release/release-lane.md).
It covers the notarized DMG/Sparkle/GitHub path and the separate Mac TestFlight
archive/upload path. The wrapper script is:

```bash
scripts/release-all.sh --help
```

## Features

- **Library**: Hierarchical document storage with collections
- **Search**: Semantic search via LanceDB embeddings
- **Chat**: RAG-based document Q&A
- **Workflows**: Visual node editor for document processing pipelines (LangGraph)
- **Knowledge Graph**: Entities, claims, and relationships extracted from documents (owned by fichero-engine; surfaces render)
- **Ingest**: Comprehensive file ingestion with 37+ supported formats
- **CLI / MCP**: Engine endpoints driven from the terminal (`fichero`) and from MCP-aware agents (`fichero-mcp`)
- **Privacy / offline-first**: Model-agnostic via LangChain provider integrations; run local models (Ollama, LM Studio, MLX) with no internet, or bring your own cloud API key

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

- `fichero-engine/`: the server (FastAPI), workflow runner, KG, ingest ([README](fichero-engine/README.md))
- `fichero/`: SwiftUI app, Xcode project, and `fichero` CLI under `fichero-engine/src/fichero/cli/`
- `docs/`: published documentation site and contributor reference
- `agent-work/`: agent working material (notes, handoffs, proposals); not published

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the worktree workflow and issue-claim
rules. Folder-specific notes live in [fichero/AGENTS.md](fichero/AGENTS.md) and
[fichero-engine/AGENTS.md](fichero-engine/AGENTS.md).

### Top-level folder ownership

- `runtime`: `fichero-engine/`, `fichero/`
- `generated/local`: `.build/`, `build/`, `dist/`, `logs/`, `fichero/derived_data/`
- `reference`: `docs/`

### fichero-engine: Python server (`fichero-engine/src/fichero/`)

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

Typed Python CLI mirroring the engine's HTTP surface. Used as the engine-quality comparison loop against the SwiftUI app. Every endpoint reachable from the app should be reachable from the CLI.

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

## Documentation

- **End users**: [`docs/user/`](docs/user/), getting started, importing, reading & editing, search & knowledge graph, AI & privacy. (Published on the docs site.)
- **Developers / contributors**: [`docs/contributor/`](docs/contributor/), architecture overview, setup & contributing, OpenAPI & clients, security model, workflows, the action registry. (Published on the docs site.)
- **Architecture deep-dives**: [`docs/architecture/`](docs/architecture/) and the canonical agent guide [`docs/CLAUDE.md`](docs/CLAUDE.md).
- Component READMEs: [`fichero/`](fichero/README.md) (SwiftUI app) and [`fichero-engine/`](fichero-engine/README.md) (Python engine).

## License

MIT. See [`LICENSE`](LICENSE). Copyright (c) 2025 Daniel Tubb.
