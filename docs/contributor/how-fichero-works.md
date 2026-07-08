(AI generated. Not reviewed.)

# How Fichero Works

This page describes the current shipped architecture on `main`. It is grounded
in the SwiftUI app under `fichero/fichero/` and the FastAPI engine under
`fichero-engine/src/fichero/`.

## 1. Top-level runtime model

Fichero is a two-part system:

- `fichero/fichero/`: the Apple client, built in SwiftUI
- `fichero-engine/src/fichero/`: the Python FastAPI engine

The normal app path is not "Swift reads and writes the library directly." The
app talks to the engine over the HTTP API and the engine owns persistence,
workflows, search, and AI behavior.

On the client side:

- `EngineConfig.swift` defines the engine host and `/api` base URL
- `EmbeddedBackendService.swift` manages the embedded/local-engine path on macOS
- `FicheroApp.swift` mounts `LibraryWindow`
- `LibraryWindow.swift` injects the per-library environment and opens
  `DocumentTabView`
- `DocumentTabView.swift` hosts `ContentView`, which is the main workspace shell

On current `main`, macOS can use a local engine host, while iPhone and iPad use
the configured external-host path rather than starting an embedded engine.

## 2. Frontend → backend contract

The frontend uses the generated OpenAPI client plus hand-written Swift service
wrappers:

- `fichero/fichero/Services/APIClient.swift` is the shared client wrapper
- many domain services are generated wrappers such as
  `DocumentServiceGenerated.swift`, `SearchServiceGenerated.swift`,
  `WorkflowServiceGenerated.swift`, and `ChatServiceGenerated.swift`
- some richer surfaces use hand-written wrappers around the same client, such as
  `AnnotationService.swift`, `NoteService.swift`, and stores under
  `fichero/fichero/Models/`

The important architectural rule is that the app does not invent a second
backend protocol. The contract is the engine's OpenAPI surface plus the typed
Swift wrappers built on top of it.

## 3. Backend shape

The engine entry point is `fichero.api.main`. Feature behavior is mostly split
by route module under `fichero/api/routes/`.

Examples:

- documents and folders: `api/routes/documents.py`
- search and saved searches: `api/routes/search.py`
- entities: `api/routes/entities.py`
- claims: `api/routes/claims.py`
- claim curation: `api/routes/claim_curation.py`
- entity curation: `api/routes/kg_entity_curation.py`
- workflows: `api/routes/workflows.py`

That route layer sits on top of shared storage and workflow modules rather than
each route owning its own persistence strategy.

## 4. Storage: DuckDB + LanceDB

`fichero-engine/src/fichero/db.py` is the main storage wrapper.

Current built split:

- DuckDB stores the typed library rows and most queryable metadata
- LanceDB stores vector indexes used for semantic search and KG embeddings

The `Database` class in `db.py` wraps both layers. The database comments and
helper methods on current `main` are explicit that one process owns a library
read-write, DuckDB is the structured store, and LanceDB is the vector store.

Related pieces:

- `db_manager.py` manages per-library `Database` instances
- `db_embeddings.py` owns the canonical embedding write/search helpers

## 5. Workflows and the execution engine

The workflow engine is LangGraph-backed on current `main`.

Grounded code points:

- `fichero-engine/src/fichero/execution/runner.py` builds and compiles a
  LangGraph `StateGraph`
- workflow tools live under `fichero-engine/src/fichero/workflows/tools/`
- tool registration lives in `fichero-engine/src/fichero/workflows/registry.py`
- `workflows/tools/agent.py` wraps workflow tools for LangChain/LangGraph agent
  use

So the accurate description is:

- route layer accepts workflow requests
- execution runner builds the LangGraph graph
- tools do the real document/AI/search/KG work

## 6. LLM path

The centralized LLM entry surface is `fichero-engine/src/fichero/llm.py`.

For current workflow/tool code, the important public helpers are:

- `chat(...)`
- `chat_structured(...)`
- `chat_with_tools(...)`
- `chat_workflow(...)`

`chat_workflow(...)` is the shared workflow/tool dispatcher. It delegates to
the same centralized helpers rather than each workflow constructing its own
provider path. `get_langchain_model(...)` still exists, but as the LangChain
model factory under those higher-level entry points.

## 7. Knowledge-graph extraction path

The current KG extraction pipeline is not one monolithic "KG route." It is a
workflow/tool pipeline that produces and persists `KnowledgeEntity` and
`KnowledgeClaim` rows.

The main shipped path is:

- extract text/records from documents
- run extractor tools
- turn extracted items into entity/claim rows
- optionally write or finalize KG payloads for downstream workflow steps

Grounded code points:

- `workflows/tools/extract_all.py` is the combined extraction tool and can emit
  `kg_payload`
- `workflows/tools/extractors.py` contains the typed extractor logic and the
  persistence helpers that turn extractor output into `KnowledgeEntity` and
  `KnowledgeClaim` rows
- `workflows/tools/_entity_writer.py` is the shared entity/claim write path for
  deduping, upserting entities, and saving claims
- `workflows/tools/kg_writer.py` is the downstream writer for `kg_payload` when
  a workflow splits extraction from persistence

That means "KG extraction" is currently a workflow/tool concern first, and a
query/render concern second.

## 8. Entity and claim curation

Entity/claim curation is built as explicit API and workflow surfaces, not just
an internal post-processing step.

Current built pieces include:

- CRUD and query routes for entities in `api/routes/entities.py`
- CRUD and query routes for claims in `api/routes/claims.py`
- entity curation routes in `api/routes/kg_entity_curation.py`
- claim curation routes in `api/routes/claim_curation.py`
- workflow cleanup/merge passes in `workflows/tools/cleanup.py` and
  `workflows/tools/merge_dedup_only.py`

So there are two complementary layers:

- the route layer for reviewer-facing curation and API access
- the workflow/tool layer for extraction cleanup, dedup, and merge flows

## 9. Where to read next

Use this page as the short mental model, then drill down:

- deeper backend/frontend split: [../contributor/architecture-overview.md](../contributor/architecture-overview.md)
- OpenAPI client path: [../contributor/openapi-and-clients.md](../contributor/openapi-and-clients.md)
- storage and KG details: [../contributor/data-search-and-kg.md](../contributor/data-search-and-kg.md)
- workflows and curation: [../contributor/workflows-activity-and-curation.md](../contributor/workflows-activity-and-curation.md)
