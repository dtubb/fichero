<!-- Verified against fichero-server/src (2026-07-18): api/main.py, workflows/, loaders/, engine/. -->

# Backend Overview

## What Fichero Backend Does

Fichero's Python backend provides:
- **Document Management**: File storage, organisation, and metadata handling
- **AI Processing**: Document analysis, transcription, and workflow execution
- **Search**: Full-text and semantic (vector) search
- **Knowledge Graph**: Entity/claim extraction, graph reasoning, link prediction
- **REST API**: FastAPI endpoints consumed by the Swift UI

## Architecture

```
Swift UI App → HTTPS/REST (127.0.0.1:8765, loopback, cert-pinned) → FastAPI
                                          ├── DuckDB  (structured metadata)
                                          ├── LanceDB (vector embeddings)
                                          ├── LangGraph (workflow engine)
                                          └── LangChain (LLM providers)
```

## Package Layout

```
fichero-server/src/
├── fichero/   # Main library — API, database, AI, workflows
└── engine/    # Briefcase entry-point wrapper (app lifecycle only)
```

`engine` exists solely because Briefcase requires a named app-slug package as the bundle entry point. Its `__main__.py` handles environment detection, TLS/bind-host setup, hot-reload, and port checks. Do not put business logic there.

## API Route Tiers

Routes are registered at startup based on the `FICHERO_FEATURE_TIER` environment variable (`release` | `dev`, default `release`).

### Core Routes (always registered — 23 total)

| Prefix | Module | Purpose |
|---|---|---|
| `/api` | `activity` | Workflow execution event stream |
| `/api/artifacts` | `artifacts` | Document artifact metadata |
| `/api` | `batch` | Bulk document operations |
| `/api/chat` | `chat` | RAG conversation interface |
| `/api` | `claim_links` | Knowledge graph claim relationships |
| `/api` | `claims` | Knowledge graph claim nodes |
| `/api/documents` | `documents` | Document CRUD, hierarchy |
| `/api` | `entities` | Semantic entity management |
| `/api/folders` | `folders` | Folder hierarchy |
| `/api/ingest` | `ingest` | File ingestion (LINK/COPY/MOVE modes) |
| `/api/migrations` | `migrations` | Database schema upgrades |
| `/api/mcp/tools` | `mcp_tools` | MCP tool registration |
| `/api` | `multilingual` | Language detection and normalisation |
| `/api/providers` | `providers` | LLM provider config |
| `/api` | `review_queue` | Content review workflow |
| `/api/search` | `search` | Full-text and vector search |
| `` | `settings` | App settings |
| `/api/sources` | `sources` | Bibliographic source management |
| `/api/models` | `models` | AI model management |
| `/api/storage` | `storage` | File storage operations |
| `/api/tasks` | `tasks` | Async task queue |
| `/api/workflow-execution` | `workflow_execution` | Workflow runtime endpoints |
| `/api/workflows` | `workflows` | Workflow CRUD |

### Dev-Tier Routes (`FICHERO_FEATURE_TIER=dev`)

KG analytics + curation surfaces live under `/api/kg/*` after the
1587a1b6 namespace consolidation. The old monolithic
`/api/knowledge-graph/*` sub-package and the stand-alone
`/api/interpretations` router were deleted; their unique features
were ported into focused single-purpose modules below.

| Prefix | Module | Purpose |
|---|---|---|
| `/api/kg/search` | `kg_search` | General KG semantic search |
| `/api/kg/claim-search` | `kg_claim_search` | Claim embed + similarity |
| `/api/kg/claim-analysis` | `kg_claim_analysis` | Contradictions + evidence-chain |
| `/api/kg/entity-curation` | `kg_entity_curation` | Entity merge/split/audit + semantic |
| `/api/kg/graph` | `kg_graph` | Centrality, traverse, path, co-occurrence, metrics |
| `/api/kg/triangulation` | `kg_triangulation` | Cross-source SVO support |
| `/api/kg/predictions` | `kg_predictions` | Heuristic predictions + run management |
| `/api/kg/pykeen` | `kg_pykeen` | PyKEEN train + predict (KGE) |
| `/api/kg/review` | `kg_review` | Entity-pair review queue |
| `/api/kg/mutations` | `kg_mutations` | Undo individual mutations |
| `/api/kg/inclusion` | `kg_inclusion` | Declarative scope rules |
| `/api/kg/interpretations` | `kg_interpretations` | Interpretation CRUD + frameworks + taxonomy |
| `/api/kg/rebuild` | `kg_rebuild` | Rebuild kg.nt materialization |
| `/api/citations` | `kg_citations` | BibTeX export (cross-cuts entities) |
| `/api/hermeneutics` | `hermeneutics` | Textual interpretation (PatternInstance + hermeneutic circle) |
| `/api/research` | `research_agents` | Autonomous research workflows |
| `/api/iiif` | `iiif` | IIIF image interoperability |
| `/api` | `search_explain` | Search algorithm explanation |
| `/api` | `graph_exploration` | Multi-entity neighborhood + paths-between (uniquely covers compound queries not in `kg_graph`) |
| `/api` | `graph_traversal` | Subgraph extraction (uniquely covers custom subgraph not in `kg_graph`) |

### Additional Dev-Tier Routes (staged features)

These are also gated behind `FICHERO_FEATURE_TIER=dev`. They are complete but not yet promoted to core:

| Prefix | Module | Purpose |
|---|---|---|
| `/api` | `actions` | Action definitions and library |
| `/api` | `chains` | Sequential workflow chaining |
| `` | `graph_reasoning` | NetworkX graph analysis (centrality, communities) |
| `/api` | `integrations` | DEVONthink, Bookends, Tinderbox sync |
| `/api` | `local_models` | Local model (Whisper, embeddings, spaCy) management |
| `/api` | `mcp_servers` | MCP server lifecycle management |
| `/api` | `model_comparison` | Multi-model response comparison |
| `` | `orchestration` | Orchestration policy rules |
| `` | `predictions` | PyKEEN link prediction |
| `/api` | `schedules` | Cron-style workflow scheduling |
| `/api` | `triggers` | Event-driven workflow triggers |

## Core Modules

| Module | Purpose |
|---|---|
| `api/main.py` | FastAPI app, route registration, feature-tier resolver |
| `db.py` | Database layer — DuckDB (relational) + LanceDB (vectors) |
| `models.py` | Pydantic models shared across API and database |
| `app_db.py` | App-level settings database (separate from per-library DB) |
| `ingest.py` | File ingestion pipeline (LINK/COPY/MOVE modes, 50+ file extensions); re-exported from `importers/ingest.py` |
| `llm.py` | LangChain provider integrations. LiteLLM = cost/model metadata only, never routing |
| `providers.py` | LLM provider definitions (Ollama, OpenAI, Anthropic, etc.) |
| `storage.py` | Thumbnail, archive, and file path management |
| `keychain.py` | macOS Keychain credential storage |
| `bookmarks.py` | macOS security-scoped bookmark management |
| `logging.py` | Structured logging with request context |
| `migrations.py` | Database schema migration runner |
| `multilingual.py` | Language detection, normalisation, transliteration |
| `knowledge_models.py` | Pydantic models for entities, claims, links |
| `research_models.py` | Models for research agent workflows |
| `spatial_models.py` | Models for spatial reasoning |
| `hermeneutics_models.py` | Models for interpretation features |
| `graph_reasoning.py` | NetworkX graph analysis (centrality, communities) |
| `pykeen_inference.py` | PyKEEN knowledge graph embedding and link prediction |
| `mcp_manager.py` | MCP server lifecycle management |
| `local_models.py` | Local LLM (Ollama, LM Studio) management |
| `orchestration_policy.py` | Workflow orchestration rules and policies |

## Workflow System

| Module | Purpose |
|---|---|
| `workflows/registry.py` | 118+ tools / 135+ tool defs with port specs (single source of truth) |
| `workflows/builder.py` | Converts frontend graph JSON to executable LangGraph |
| `workflows/executor.py` | Runs workflow graphs with SSE streaming |
| `workflows/types.py` | NodeDef, EdgeDef, WorkflowDef, WorkflowState models |
| `workflows/workflow_store.py` | Workflow persistence (DuckDB) |
| `workflows/tasks.py` | Async background task runner |
| `workflows/scheduler.py` | Cron-style workflow scheduling |
| `workflows/activity.py` | Execution event tracking and streaming |
| `workflows/chaining.py` | Sequential and conditional workflow chaining |
| `workflows/batch.py` | Bulk workflow execution |
| `workflows/resolver.py` | Parameter reference resolution at runtime |
| `workflows/state.py` | Workflow state management |
| `workflows/file_watcher.py` | File system watch triggers |
| `workflows/model_comparison.py` | Multi-model response comparison |

## Loaders

Text extraction engines in `loaders/`:
- `document_loader.py` — DOCX/XLSX/PPTX/EPUB/RTF/ODT and similar office formats
- `pdf_loader.py` — PDF text extraction
- `docling_loader.py` — Docling-based structured document parsing
- `image_loader.py` — JPEG, PNG, HEIC, JPEG-XL with OCR
- `iiif_loader.py` — IIIF manifest fetching
- `unified.py` — Dispatcher across all loader types

(Audio/video transcription is not in `loaders/`; it runs via the workflow
tools, e.g. `workflows/tools/audio_base.py`.)

## Development

```bash
# Start server
PYTHONPATH=fichero-server/src .venv/bin/uvicorn fichero_server.api.main:app --port 8765

# Start with dev-tier routes
FICHERO_FEATURE_TIER=dev PYTHONPATH=fichero-server/src .venv/bin/uvicorn fichero_server.api.main:app --port 8765

# Tests
PYTHONPATH=fichero-server/src .venv/bin/pytest fichero-server/tests/unit/ --ignore=fichero-server/tests/unit/_archived

# Lint
ruff check fichero-server/src/

# Sync OpenAPI schema to Swift client (after any API change)
./fichero-server/scripts/sync_openapi_schema.sh
```

## Related Contract Docs

- `docs/contributor/architecture/fichero-server/capture_sessions_resumable_upload_contract.md` — mobile/offline capture session and resumable-upload contract slice (`#2352`)
