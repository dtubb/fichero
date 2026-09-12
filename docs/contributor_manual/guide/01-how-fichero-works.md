# 1. How Fichero Works


Fichero is not a single-process desktop app. It is a two-part system:

- `fichero/fichero/` — the native Apple client, one SwiftUI codebase for macOS, iPhone, and iPad (Xcode project: `fichero/fichero.xcodeproj`)
- `fichero-server/src/fichero_server/` — the Python FastAPI engine

The Swift app is a rendering layer, not the source of truth. Storage, ingest, search, workflows, the knowledge graph, and all validation live in the engine. The app talks to the engine over a typed API (a Unix domain socket locally, or pinned HTTPS — see Transport below); it never reads or writes the library directly.

### One engine, many clients

The same engine is consumed by more than one surface:

    SwiftUI app    fichero CLI    MCP server
           \           |            /
            \          |           /
          Unix domain socket (local)
        or HTTPS on 127.0.0.1:8765
                (TLS, pinned)
                       |
                       v
                FastAPI engine
            (fichero-server/src/fichero_server)
               | DuckDB + LanceDB
               | LangGraph workflows
               | LLM providers via LangChain

| Surface | Path | Status |
|----|----|----|
| SwiftUI app (macOS, iOS, iPad) | `fichero/` | Live |
| `fichero` CLI | `fichero-cli/src/fichero_cli/` | Live (typed, end-to-end verified) |
| MCP server | `fichero-mcp/src/fichero_mcp/server.py` (`fichero-mcp`) | Live |

All surfaces sit on top of the engine. They render and accept input; they do not contain logic. `fichero-cli` and `fichero-mcp` are deliberately thin — every command or tool is one or two HTTP calls; if a client needs logic, the logic belongs in the engine.

Why the split is load-bearing, not stylistic: other clients exist and must agree. The moment a client *decides* an outcome, every other client is wrong until it recomputes the same way. Two clients with the same logic drift; two clients rendering the same server state cannot. Clients send what the user pointed at; the server resolves what that means. The corollary is real-time propagation: `api/change_stream.py` carries a domain-typed event vocabulary (`entity.updated`, `claim.updated`, `document.updated`, plus `stream.gap` / `stream.resync_required`), and Swift stores observe it. A mutation that does not emit is invisible to every other client — emit at the write, not at each caller.

### Transport

Clients connect over a **Unix domain socket** locally, or **pinned HTTPS on** `https://127.0.0.1:8765` otherwise. The app pins the engine certificate fail-closed, so a plain-HTTP engine cannot connect. Never run a bare `uvicorn`; use `bash fichero-server/scripts/start_backend.sh`. iPhone and iPad cannot embed the engine — they connect to one running on a Mac (configured through `EngineConfig`).

### Frontend shape

The frontend owns windows, panes, and navigation; document browsing and selection state; reading surfaces for images and PDFs; the inspector tabs; workflow launch and activity display; and hand-written service wrappers around the generated OpenAPI client.

Key client files: `EngineConfig.swift` defines the engine host and `/api` base URL; `EmbeddedBackendService.swift` (and its `+Spawn`, `+Lifecycle`, `+TLS`, … extensions) manages the embedded/local-engine path on macOS; `FicheroApp.swift` mounts `LibraryWindow`, which injects per-library services and opens `DocumentTabView`; `ContentView` manages the four-part workspace (sidebar, browser, reading pane, inspector). Each open library has its own service instances, shared across the windows and tabs working against that library.

### Backend shape

The engine entry point is `fichero_server.api.main`. Feature behavior is split by route package under `fichero-server/src/fichero_server/api/routes/`:

- documents and folders: `api/routes/document/documents.py` (plus siblings — `annotations.py`, `artifacts.py`, `notes.py`, `view.py`, …)
- search and saved searches: `api/routes/search/core.py`
- entities: `api/routes/entity/entities.py`
- claims: `api/routes/claim/claims.py`; claim curation: `api/routes/claim/curation.py`
- workflows: the `api/routes/workflow/` package; execution runtime: `api/routes/workflow_execution/`

The route layer sits on top of shared storage and workflow modules rather than each route owning its own persistence strategy.

### Storage

The db layer is the `fichero-server/src/fichero_server/db/` package:

- `db/__init__.py` defines the `Database` class, the central abstraction over both stores
- `db/manager.py` manages per-library `Database` instances
- `db/embeddings.py` owns the canonical embedding write/search helpers

DuckDB stores the typed library rows and queryable metadata; LanceDB stores vector indexes for semantic search and KG embeddings. One process owns a library read-write.

### Workflows and the LLM path

The workflow engine is LangGraph-backed: `execution/runner.py` builds and compiles a LangGraph `StateGraph`; tool definitions live under `workflows/tools/` with registration in `workflows/registry.py`; `workflows/builder.py` converts stored workflow definitions into executable graphs. The route layer accepts workflow requests, the runner builds the graph, and the tools do the real document/AI/search/KG work.

The centralized LLM surface is `fichero-server/src/fichero_server/llm/`. The public helpers are `chat(...)`, `chat_structured(...)`, `chat_with_tools(...)`, and `chat_workflow(...)` — the workflow/tool dispatcher that delegates into the shared entry points rather than each workflow constructing its own provider path.

### KG extraction and curation

KG extraction is a workflow/tool pipeline that produces persistent `KnowledgeEntity` and `KnowledgeClaim` rows: `workflows/tools/extract_all.py` (combined extraction, can emit `kg_payload`), `extractors.py` (typed extractor logic and persistence helpers), `_entity_writer.py` (shared dedup/upsert/claim-save path), and `kg_writer.py` (downstream writer when a workflow splits extraction from persistence). Curation is a second, reviewer-facing layer: CRUD and curation routes for entities and claims, plus workflow cleanup/merge passes (`cleanup.py`, `merge_dedup_only.py`).

What this architecture means for contributor tasks: UI work usually means SwiftUI views and hand-written service wrappers; data, AI, ingest, and search work means FastAPI routes and backend modules; and any contract change requires an OpenAPI sync so the Swift side compiles again (chapter 4).
