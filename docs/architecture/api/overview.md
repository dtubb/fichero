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
Swift UI App → HTTP/REST (port 8765) → FastAPI
                                          ├── DuckDB  (structured metadata)
                                          ├── LanceDB (vector embeddings)
                                          ├── LangGraph (workflow engine)
                                          └── LiteLLM (100+ LLM providers)
```

## Package Layout

```
fichero-api/src/
├── fichero/           # Main library — API, database, AI, workflows
└── fichero_backend/   # Briefcase entry-point wrapper (app lifecycle only)
```

`fichero_backend` exists solely because Briefcase requires a named app-slug package as the bundle entry point. Its `__main__.py` handles environment detection, hot-reload, and port checks. Do not put business logic there.

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
| `/api/ingest` | `ingest` | File ingestion (LINK + COPY modes) |
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

### Dev-Tier Routes (`FICHERO_FEATURE_TIER=dev` — 8 additional)

| Prefix | Module | Purpose |
|---|---|---|
| `/api/knowledge-graph` | `knowledge_graph` | Semantic graph CRUD and queries |
| `/api` | `search_explain` | Search algorithm explanation |
| `/api/hermeneutics` | `hermeneutics` | Textual interpretation |
| `/api` | `interpretations` | Document interpretation |
| `/api` | `graph_exploration` | Graph traversal and path finding |
| `/api/mind-palace` | `mind_palace` | Memory/context management |
| `/api/research` | `research_agents` | Autonomous research workflows |
| `/api/iiif` | `iiif` | IIIF image interoperability |

### Staged Routes (built, not yet registered — 11)

These modules are complete but not wired into `main.py` yet. They represent features in progress or awaiting milestone prioritisation:

`actions`, `chains`, `graph_reasoning`, `integrations`, `local_models`, `mcp_servers`, `model_comparison`, `orchestration`, `predictions`, `schedules`, `triggers`

## Core Modules

| Module | Purpose |
|---|---|
| `api/main.py` | FastAPI app, route registration, feature-tier resolver |
| `db.py` | Database layer — DuckDB (relational) + LanceDB (vectors) |
| `models.py` | Pydantic models shared across API and database |
| `app_db.py` | App-level settings database (separate from per-library DB) |
| `ingest.py` | File ingestion pipeline (LINK/COPY modes, 37+ file types) |
| `llm.py` | LangChain interface with LiteLLM for 100+ providers |
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
| `workflows/registry.py` | 30+ tool definitions with port specs (single source of truth) |
| `workflows/builder.py` | Converts frontend graph JSON to executable LangGraph |
| `workflows/executor.py` | Runs workflow graphs with SSE streaming |
| `workflows/types.py` | NodeDef, EdgeDef, WorkflowDef, WorkflowState models |
| `workflows/store.py` | Workflow persistence (DuckDB) |
| `workflows/tasks.py` | Async background task runner |
| `workflows/scheduler.py` | Cron-style workflow scheduling |
| `workflows/activity.py` | Execution event tracking and streaming |
| `workflows/chaining.py` | Sequential and conditional workflow chaining |
| `workflows/batch.py` | Bulk workflow execution |
| `workflows/resolver.py` | Parameter reference resolution at runtime |
| `workflows/state.py` | Workflow state management |
| `workflows/file_watcher.py` | File system watch triggers |
| `workflows/action_library.py` | Pre-built action definitions |
| `workflows/model_comparison.py` | Multi-model response comparison |

## Loaders

Text extraction engines in `loaders/`:
- `document_loader.py` — PDFs, DOCX, TXT, Markdown
- `image_loader.py` — JPEG, PNG, HEIC, JPEG-XL with OCR
- `audio_loader.py`, `video_loader.py` — Media transcription
- `iiif_loader.py` — IIIF manifest fetching
- `unified.py` — Dispatcher across all loader types

## Development

```bash
# Start server
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Start with dev-tier routes
FICHERO_FEATURE_TIER=dev PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Tests
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived

# Lint
ruff check fichero-api/src/

# Sync OpenAPI schema to Swift client (after any API change)
./fichero-api/scripts/sync_openapi_schema.sh
```
