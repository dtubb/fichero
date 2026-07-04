# Contributing

Fichero is written by AI coding agents that Daniel directs. He is an
anthropologist, not a software engineer, so he does not write Swift or Python from
scratch. He decides what to build, what is broken, and what ships; the agents do
the typing.

## How the work runs

- A **manager** agent (`session-start-manager`) holds the control lane. It triages
  GitHub issues, picks the next batch, and dispatches it. It does not write source
  code.
- Each **worker** agent runs in its own git worktree under
  `~/code/fichero-worktrees/<name>`, in a separate tmux window (an interactive
  `claude` or `codex` session). A worker grinds one milestone's GitHub issues and
  commits as itself (Claude or Codex), crediting Daniel with a `Co-Authored-By`
  trailer.
- The manager **reviews** each worker's output, **build-gates** it, runs
  `verify_all`, then **merges via PR**, closes the issues, and dispatches the next
  batch. Daniel reviews the result and judges every release by using the app.

GitHub Issues plus Milestones is the source of truth for the backlog. Work lands on
the milestone branch; there are no per-task branches.

## More detail

See [AGENTS.md](AGENTS.md) for the operational manual (hard rules, commit
attribution, docs placement, worker orchestration), and the folder-specific
guidance in [fichero/AGENTS.md](fichero/AGENTS.md) and
[fichero-engine/AGENTS.md](fichero-engine/AGENTS.md). For the fuller repo
conventions, see
[docs/contributor/setup-and-contributing.md](docs/contributor/setup-and-contributing.md).

If you would like to contribute to Fichero, please make a pull request. Outstanding Milestones and Issues that the Fichero Manager is working on are on GitHub. Please make a pull request for our consideration.

Milestones and Issues are coded by AI. The Forum is for human discussion.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to contribute. Folder-specific notes live in [fichero/AGENTS.md](fichero/AGENTS.md) and
[fichero-engine/AGENTS.md](fichero-engine/AGENTS.md).

## Building from source (for developers)

Most people should just download the app (see [Installing and using
Fichero](#installing-and-using-fichero) in the reader). This section is for working on
Fichero itself.

First, you’ll need to clone Fichero.

Then create a virtual environment.

Then install the fichero engine requirements.

Vegetarian bug build to connect to a Fucito engine running on uvicorn on the local host. This means changes to the engine are updated directly.  

**Start fichero-engine** (serves HTTPS on `127.0.0.1:8765`; the app pins it fail-closed, so a plain-HTTP engine cannot connect):
```bash
bash fichero-engine/scripts/start_backend.sh
```

**Run the SwiftUI app:**
Open `fichero/fichero.xcodeproj` in Xcode and run.

## Architecture

Fichero has two components. A front end and a back end. The front end is written in SwiftUI, and the back end (the Engine) is a FastAPI server that holds the data and logic. 

The Fichero Mac, iPhone, iOS (and the CLI app, and other front ends in the future) connect to the Fichero Engine and display what it returns.

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

All surfaces sit on top of fichero-engine. They render and accept input; they do not contain logic.

| Surface | Path | Status |
|---|---|---|
| SwiftUI app (macOS, iOS, iPad) | `fichero/` (Xcode project: `fichero/fichero.xcodeproj`) | Live |
| `fichero` CLI | `fichero-engine/src/fichero/cli/` | Live (typed, end-to-end verified) |
| MCP server | `fichero-engine/src/fichero/mcp_server.py` (`fichero-mcp`) | Live |


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

## Project Structure

- `fichero-engine/`: the server (FastAPI), workflow runner, KG, ingest ([README](fichero-engine/README.md))
- `fichero/`: SwiftUI app, Xcode project, and `fichero` CLI under `fichero-engine/src/fichero/cli/`
- `docs/`: published documentation site and contributor reference

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

