(AI generated. Not reviewed.)

# Backend Key Files

## Entry Points

| File | Purpose |
|---|---|
| `src/fichero/api/main.py` | FastAPI app — route registration, feature-tier resolver, lifespan |
| `src/fichero_backend/__main__.py` | Briefcase bundle entry point — env detection, hot-reload, port checks |
| `src/fichero/__init__.py` | Package version |

## API Routes (`src/fichero/api/routes/`)

### Core (always registered)
- `activity.py` — Workflow execution event stream (SSE)
- `artifacts.py` — Document artifact metadata
- `batch.py` — Bulk document operations
- `chat.py` — RAG conversation interface
- `claim_links.py` — Knowledge graph claim relationships
- `claims.py` — Knowledge graph claim nodes
- `documents.py` — Document CRUD, file hierarchy
- `entities.py` — Semantic entity management
- `folders.py` — Folder hierarchy
- `ingest.py` — File ingestion (LINK + COPY modes)
- `migrations.py` — Database schema upgrade runner
- `mcp_tools.py` — MCP tool registration
- `models.py` — AI model management
- `multilingual.py` — Language detection and normalisation
- `providers.py` — LLM provider configuration
- `review_queue.py` — Content review workflow
- `search.py` — Full-text and semantic search
- `settings.py` — App settings
- `sources.py` — Bibliographic source management
- `storage.py` — File storage operations
- `tasks.py` — Async task queue
- `workflow_execution.py` — Workflow runtime (execute, stream, cancel)
- `workflows.py` — Workflow CRUD

### Dev-tier (`FICHERO_FEATURE_TIER=dev`)
- `graph_exploration.py` — Graph traversal and path finding
- `hermeneutics.py` — Textual interpretation
- `iiif.py` — IIIF image interoperability
- `interpretations.py` — Document interpretation
- `knowledge_graph.py` — Semantic knowledge graph CRUD
- `mind_palace.py` — Memory/context management
- `research_agents.py` — Autonomous research workflows
- `search_explain.py` — Search algorithm explanation

### Additional dev-tier (staged features, `FICHERO_FEATURE_TIER=dev`)
- `actions.py` — Action definitions and library
- `chains.py` — Sequential workflow chaining
- `graph_reasoning.py` — NetworkX graph analysis
- `integrations.py` — DEVONthink, Bookends, Tinderbox sync
- `local_models.py` — Local model management (Whisper, embeddings, spaCy)
- `mcp_servers.py` — MCP server lifecycle
- `model_comparison.py` — Multi-model response comparison
- `orchestration.py` — Orchestration policy rules
- `predictions.py` — PyKEEN link prediction
- `schedules.py` — Cron-style workflow scheduling
- `triggers.py` — Event-driven workflow triggers

## Data Layer

| File | Purpose |
|---|---|
| `db.py` | Database layer — DuckDB (relational) + LanceDB (vectors). Always go through here, never query directly. |
| `app_db.py` | App-level settings DB (separate from per-library DB) |
| `models.py` | Pydantic models shared by API and DB (source of truth for schema) |
| `knowledge_models.py` | Entity, claim, and link models for knowledge graph |
| `research_models.py` | Research agent workflow models |
| `spatial_models.py` | Spatial reasoning models |
| `hermeneutics_models.py` | Interpretation and hermeneutics models |
| `storage.py` | Thumbnails, archives, file path management |
| `migrations.py` | Schema migration runner |

## AI Integration

| File | Purpose |
|---|---|
| `llm.py` | LangChain interface + LiteLLM routing for 100+ providers |
| `providers.py` | Provider definitions (Ollama, LM Studio, OpenAI, Anthropic, Google, etc.) |
| `pykeen_inference.py` | PyKEEN knowledge graph embedding and link prediction |
| `graph_reasoning.py` | NetworkX graph analysis (centrality, communities, clustering) |
| `orchestration_policy.py` | Workflow orchestration rules |

## Workflow System (`src/fichero/workflows/`)

| File | Purpose |
|---|---|
| `registry.py` | Tool definitions with port specs — **single source of truth for ports** |
| `builder.py` | Converts frontend workflow JSON → executable LangGraph |
| `executor.py` | Runs graphs with SSE streaming |
| `types.py` | NodeDef, EdgeDef, WorkflowDef, WorkflowState |
| `store.py` | Workflow persistence (DuckDB) |
| `tasks.py` | Async background task runner |
| `scheduler.py` | Cron-style workflow scheduling |
| `activity.py` | Execution event tracking and SSE streaming |
| `chaining.py` | Sequential and conditional workflow chaining |
| `batch.py` | Bulk workflow execution |
| `resolver.py` | Parameter reference resolution at runtime |
| `state.py` | Workflow state management |
| `file_watcher.py` | File system change triggers |
| `action_library.py` | Pre-built action definitions |
| `action_store.py` | Action persistence |
| `model_comparison.py` | Multi-model response comparison |

## Loaders (`src/fichero/loaders/`)

| File | Purpose |
|---|---|
| `unified.py` | Dispatcher — routes files to the right loader |
| `document_loader.py` | PDF, DOCX, TXT, Markdown extraction |
| `image_loader.py` | JPEG, PNG, HEIC, JPEG-XL with OCR |
| `audio_loader.py` | Audio transcription |
| `video_loader.py` | Video transcription |
| `iiif_loader.py` | IIIF manifest fetching |
| `base.py` | Base loader interface |

## Integrations (`src/fichero/integrations/`)

| File | Purpose |
|---|---|
| `devonthink.py` | DEVONthink import/sync |
| `bookends.py` | Bookends reference manager sync |
| `tinderbox.py` | Tinderbox note export |
| `base.py` | Base integration interface |

## Infrastructure

| File | Purpose |
|---|---|
| `ingest.py` | File ingestion pipeline (37+ types, LINK/COPY modes) |
| `bookmarks.py` | macOS security-scoped bookmark management |
| `keychain.py` | macOS Keychain credential storage |
| `mcp_manager.py` | MCP server lifecycle management |
| `mcp_server.py` | MCP server implementation |
| `logging.py` | Structured logging with request context |
| `multilingual.py` | Language detection, normalisation, transliteration |
| `errors.py` | Centralised error types and retry logic |

## Scripts (`scripts/`)

| Script | Purpose | When to use |
|---|---|---|
| `sync_openapi_schema.sh` | Export Python schema → Swift client | After any API route/model change |
| `start_backend.sh` | Dev server with validation | Local development |
| `validate_model_sync.py` | Check Python/Swift model alignment | Before API changes |
| `build_backend_bundle.sh` | Briefcase bundle build | Release packaging |
| `export_openapi_schema.py` | Raw schema export | Called by sync script |

Dormant scripts (exist, no current callers): `verify_system.py`, `check_dependencies.py`, `check_runtime_deps.py`, `export_api_schemas.py`, `validate_swift_api_calls.py`, `setup_app_icon.py`, `build_dual_backend.sh`, `clean_local_artifacts.sh`
