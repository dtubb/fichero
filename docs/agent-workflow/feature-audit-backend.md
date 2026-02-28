# Fichero Backend Audit Report

**Date:** 2026-02-26
**Branch:** `codex/restructure-api-swiftui`
**Auditor:** python-dev (static analysis only)

---

## Overview

The Fichero backend is a FastAPI application serving a macOS SwiftUI frontend. It uses DuckDB + LanceDB for data, LangChain/LangGraph for AI workflows, and exposes 22 route modules with ~170+ endpoints. The codebase totals ~18,777 lines of route code, ~7,144 lines of core modules, and ~11,692 lines of workflow engine code.

**Test framework:** pytest with FastAPI TestClient, anyio/asyncio markers, unittest.mock. No pytest-asyncio installed (custom fallback in conftest.py). No dev-dependency section in pyproject.toml -- test deps are not formally declared.

---

## Route Module Audit

### Actions
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/actions.py`, 403 lines | |
| Endpoints | 16 (GET: 9, POST: 5, PUT: 1, DELETE: 1) | CRUD, search, import/export, from-node, composite |
| Test file | exists (integration) | `test_action_library_integration.py` (573 lines) |
| Dependencies | `db.Database`, `workflows.action_store.ActionStore` | |
| Feature status | complete | Full CRUD with search, categories, import/export |
| M1 recommendation | dev-only | Complex feature, not needed for core document management |

### Activity
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/activity.py`, 374 lines | |
| Endpoints | 7 (GET: 5, DELETE: 1, SSE stream: 1) | List, recent, stats, stream, by-workflow, by-batch, cleanup |
| Test file | exists (unit) | `test_activity.py` (390 lines) |
| Dependencies | `db.Database`, `workflows.activity` | |
| Feature status | complete | Full activity tracking with SSE streaming |
| M1 recommendation | on | Essential for monitoring workflow runs |

### Artifacts
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/artifacts.py`, 196 lines | |
| Endpoints | 5 (GET: 4, DELETE: 1) | By document, by ID, list all, types, delete |
| Test file | none (directly) | Covered partially in `test_api.py` |
| Dependencies | `db.Database`, `models.Artifact`, `models.Document` | |
| Feature status | complete | Read-heavy, artifacts created by workflow tools |
| M1 recommendation | on | Core feature -- workflow outputs stored as artifacts |

### Batch
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/batch.py`, 384 lines | |
| Endpoints | 10 (GET: 3, POST: 5, DELETE: 1) | CRUD, execute, pause/resume/cancel/retry, progress |
| Test file | exists (integration) | `test_batch_execution_integration.py` (547 lines) |
| Dependencies | `app_db`, `workflows.batch`, `workflows.workflow_store` | |
| Feature status | complete | Full batch lifecycle management |
| M1 recommendation | on | Needed for processing multiple documents |

### Chains
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/chains.py`, 468 lines | |
| Endpoints | 8 (GET: 3, POST: 2, PUT: 1, DELETE: 2) | CRUD, execute, execution history |
| Test file | none | No dedicated test file |
| Dependencies | `workflows.chaining`, `workflows.types`, `workflows.workflow_store`, `db.Database` | |
| Feature status | complete | Chain workflows together with execution tracking |
| M1 recommendation | dev-only | Advanced feature, not essential for M1 |

### Chat
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/chat.py`, 617 lines | |
| Endpoints | 9 (GET: 3, POST: 4, PUT: 1, DELETE: 1) | Send message, conversations CRUD, duplicate, reorder, providers, extract-text |
| Test file | none (directly) | Partially covered in `test_api.py` |
| Dependencies | `db.Database`, `app_db.AppDatabase`, `models.*`, `keychain`, `providers` | |
| Feature status | complete | Full conversational AI with multi-provider support |
| M1 recommendation | on | Core user-facing feature |

### Documents
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/documents.py`, 313 lines | |
| Endpoints | 12 (GET: 5, POST: 3, PUT: 2, DELETE: 1) | List, collections, roots, get, children, ancestors, create, update, delete, reorder, import, move |
| Test file | exists (unit) | `test_api.py` (747 lines, shared), `test_new_data_layer.py` |
| Dependencies | `db.Database`, `models.Document`, `models.DocType/FileType/Status` | |
| Feature status | complete | Full document hierarchy management |
| M1 recommendation | on | Core feature -- the primary data model |

### Folders
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/folders.py`, 262 lines | |
| Endpoints | 5 (GET: 1, POST: 1, PUT: 2, DELETE: 1) | List, create, rename, move items, delete |
| Test file | none | No dedicated test file |
| Dependencies | `db.Database`, `models.Workflow/SavedSearch/Conversation` | |
| Feature status | complete | Generic folder management for multiple entity types |
| M1 recommendation | on | Needed for sidebar organization |

### Ingest
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/ingest.py`, 198 lines | |
| Endpoints | 3 (GET: 1, POST: 2) | File upload, folder scan, status check |
| Test file | exists (unit + integration) | `test_ingest_module.py` (1396 lines), `test_ingest_pipeline.py` (566 lines) |
| Dependencies | `models.Document`, `db.Database` | |
| Feature status | complete | Core pipeline with background processing |
| M1 recommendation | on | Essential -- primary data ingestion path |

### Integrations
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/integrations.py`, 485 lines | |
| Endpoints | 15 (GET: 9, POST: 4, PUT: 1) | List, available, per-app, refresh, items, import/export, open, DEVONthink/Bookends/Tinderbox specific |
| Test file | exists (unit) | `test_integrations.py` (295 lines) |
| Dependencies | `integrations.base` (registry), `integrations.devonthink/bookends/tinderbox` | |
| Feature status | complete | macOS app integrations via AppleScript/pyobjc |
| M1 recommendation | dev-only | Nice-to-have, not blocking core functionality |

### Local Models
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/local_models.py`, 94 lines | |
| Endpoints | 4 (GET: 2, POST: 1, DELETE: 1) | List, disk usage, download, delete |
| Test file | none | No dedicated test file |
| Dependencies | `local_models` (core module) | |
| Feature status | partial | Basic local model management (Ollama/fastembed) |
| M1 recommendation | dev-only | Only relevant if shipping local model support |

### MCP Servers
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/mcp_servers.py`, 444 lines | |
| Endpoints | 9 (GET: 3, POST: 4, PUT: 1, DELETE: 1) | CRUD, list tools, load into registry, reload registry |
| Test file | exists (unit + integration) | `test_mcp_manager.py` (557), `test_mcp_server.py` (369), `test_mcp_workflow_integration.py` (414) |
| Dependencies | `app_db`, `models.MCPServer`, `mcp_manager` | |
| Feature status | complete | Full MCP server management with tool loading |
| M1 recommendation | dev-only | Advanced power-user feature |

### Model Comparison
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/model_comparison.py`, 343 lines | |
| Endpoints | 10 (GET: 5, POST: 4) | Compare, history, presets, models, estimate cost, vision/tool compare |
| Test file | exists (unit) | `test_model_comparison.py` (330 lines) |
| Dependencies | `workflows.model_comparison` | |
| Feature status | complete | Side-by-side model comparison with cost estimation |
| M1 recommendation | off | Nice-to-have feature, not essential |

### Models (HuggingFace)
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/models.py`, 230 lines | |
| Endpoints | 3 (GET: 3) | HuggingFace tasks, search, model details |
| Test file | none | No dedicated test file |
| Dependencies | `httpx` (external API calls to HuggingFace) | |
| Feature status | complete | HuggingFace model browser |
| M1 recommendation | off | Discovery feature, not essential |

### Providers
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/providers.py`, 1329 lines | |
| Endpoints | 18 (GET: 7, POST: 5, PATCH: 2, DELETE: 3) | Catalog, CRUD, refs, API key management, test connection, models per provider |
| Test file | exists (unit) | `test_api_providers.py` (334), `test_providers.py` (719) |
| Dependencies | `db.Database`, `app_db`, `models.Provider/Model/ProviderType`, `providers`, `keychain` | |
| Feature status | complete | Full multi-provider management with keychain integration |
| M1 recommendation | on | Essential -- manages all AI provider configs |

### Schedules
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/schedules.py`, 384 lines | |
| Endpoints | 9 (GET: 3, POST: 3, PUT: 1, DELETE: 1) | CRUD, pause/resume, trigger, run history |
| Test file | none (directly) | Partially in `test_phase8_integration.py` |
| Dependencies | `db.Database`, `workflows.scheduler`, `workflows.workflow_store` | |
| Feature status | complete | Cron-based workflow scheduling via APScheduler |
| M1 recommendation | dev-only | Advanced automation, not blocking core |

### Search
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/search.py`, 369 lines | |
| Endpoints | 10 (GET: 2, POST: 5, DELETE: 1, PUT: 1) | Hybrid search, stats, reindex, embed doc, saved searches CRUD, reorder |
| Test file | exists (indirectly) | Covered in `test_api.py`, `test_new_data_layer.py` |
| Dependencies | `db.Database`, `db.SearchResult` | |
| Feature status | complete | Hybrid vector + full-text search with saved searches |
| M1 recommendation | on | Core feature -- primary document discovery |

### Settings
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/settings.py`, 88 lines | |
| Endpoints | 3 (GET: 1, PUT: 1, DELETE: 1) | AI defaults get/set/reset |
| Test file | none | No dedicated test file |
| Dependencies | `app_db` | |
| Feature status | complete | Simple key-value settings for AI defaults |
| M1 recommendation | on | Needed for default model configuration |

### Storage
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/storage.py`, 217 lines | |
| Endpoints | 5 (GET: 5) | Thumbnail, display image, source file, stats, debug |
| Test file | exists (unit) | `test_storage.py` (461 lines) |
| Dependencies | `db.Database`, `models.Document` | |
| Feature status | complete | File serving from .fichero package structure |
| M1 recommendation | on | Essential -- serves document previews/files to SwiftUI |

### Triggers
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/triggers.py`, 380 lines | |
| Endpoints | 8 (GET: 3, POST: 2, PUT: 1, DELETE: 1) | CRUD, pause/resume, execution history |
| Test file | none (directly) | Partially in `test_phase8_integration.py` |
| Dependencies | `db.Database`, `workflows.file_watcher`, `workflows.workflow_store` | |
| Feature status | complete | File system event triggers via watchdog |
| M1 recommendation | dev-only | Advanced automation feature |

### Workflow Execution
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/workflow_execution.py`, 2343 lines | |
| Endpoints | 16 (GET: 10, POST: 3, DELETE: 3) | Execute, stream SSE, resume, status, history, threads, visualization, code gen, cache management |
| Test file | exists (unit) | `test_workflow_executor.py` (836), `test_workflow_api_direct.py` (156), `test_workflow_api_verification.py` (147) |
| Dependencies | `db.Database`, `models.Workflow`, `workflows.checkpointer`, `workflows.workflow_store`, `workflows.builder` | |
| Feature status | complete | Full LangGraph execution engine with SSE streaming, checkpointing, visualization |
| M1 recommendation | on | Core feature -- runs all AI workflows |

### Workflows
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/api/routes/workflows.py`, 721 lines | |
| Endpoints | 15 (GET: 5, POST: 5, PUT: 1, PATCH: 1, DELETE: 1) | Tools list/grouped/detail/prompt/create-node, CRUD, import/export, duplicate, reorder |
| Test file | exists (unit) | `test_workflows.py` (532), `test_workflow_crud_operations.py` (320), `test_workflow_import_export.py` (388), `test_workflow_rename_duplicate.py` (467), `test_workflow_tools.py` (1071) |
| Dependencies | `db.Database`, `workflows.types`, `workflows.registry` | |
| Feature status | complete | Full workflow CRUD with tool registry integration |
| M1 recommendation | on | Core feature -- workflow builder/management |

---

## Core Module Audit

### db.py (Database Layer)
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/db.py`, 1366 lines | |
| Test file | `test_db.py` (827 lines), `test_new_data_layer.py` (302 lines) | |
| Role | DuckDB + LanceDB wrapper, CRUD, hybrid search, embedding management | |
| Feature status | complete | Multi-library support via `DatabaseManager`, `X-Fichero-Library-Path` header |
| M1 recommendation | on | Foundation of entire backend |

### models.py (Data Models)
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/models.py`, 844 lines | |
| Test file | `test_contract_models.py` (302 lines) | |
| Role | Pydantic models: Document, Artifact, Workflow, Provider, Model, Conversation, MCPServer, SavedSearch, etc. | |
| Feature status | complete | Shared with Swift via OpenAPI schema validation |
| M1 recommendation | on | Core data definitions |

### ingest.py (Document Processing)
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/ingest.py`, 669 lines | |
| Test file | `test_ingest_module.py` (1396 lines), `test_ingest_pipeline.py` (566 lines) | |
| Role | PDF/image/text extraction, thumbnail generation, OCR via Vision framework | |
| Feature status | complete | Multi-format pipeline with macOS native OCR |
| M1 recommendation | on | Essential data pipeline |

### llm.py (LLM Interface)
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/llm.py`, 1007 lines | |
| Test file | `test_llm.py` (253 lines) | |
| Role | Multi-provider LLM abstraction via LangChain, tool calling, streaming | |
| Feature status | complete | Supports OpenAI, Anthropic, Google, AWS, Ollama, Cohere, Mistral, DashScope |
| M1 recommendation | on | Core AI infrastructure |

### providers.py (Provider Catalog)
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/providers.py`, 430 lines | |
| Test file | `test_providers.py` (719 lines) | |
| Role | Static provider catalog, model listings, capability flags | |
| Feature status | complete | Comprehensive provider metadata |
| M1 recommendation | on | Required by providers route and llm.py |

### bookmarks.py
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/bookmarks.py`, 314 lines | |
| Test file | `test_bookmarks.py` (334 lines) | |
| Role | macOS security-scoped bookmark management for file access | |
| Feature status | complete | Essential for sandbox file access persistence |
| M1 recommendation | on | Required for macOS sandbox compliance |

### app_db.py (App-Level Database)
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/app_db.py`, 516 lines | |
| Test file | none (directly) | Covered through route tests |
| Role | Global settings, provider configs, MCP server configs (not per-library) | |
| Feature status | complete | Singleton app-level DuckDB |
| M1 recommendation | on | Required for settings/providers |

### storage.py (File Storage)
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/storage.py`, 641 lines | |
| Test file | `test_storage.py` (461 lines) | |
| Role | .fichero package structure management, file copying, thumbnail paths | |
| Feature status | complete | macOS package-based storage |
| M1 recommendation | on | Core file management |

### keychain.py
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/keychain.py`, 241 lines | |
| Test file | none | No dedicated test file |
| Role | macOS Keychain access for API key storage via `security` CLI | |
| Feature status | complete | Secure credential storage |
| M1 recommendation | on | Required for provider API keys |

### errors.py
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/errors.py`, 371 lines | |
| Test file | none | No dedicated test file |
| Role | Custom exception hierarchy, error codes | |
| Feature status | complete | Structured error handling |
| M1 recommendation | on | Used across all modules |

### logging.py
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/logging.py`, 475 lines | |
| Test file | none | No dedicated test file |
| Role | Structured logging configuration | |
| Feature status | complete | |
| M1 recommendation | on | Infrastructure |

### mcp_manager.py / mcp_server.py
| Aspect | Status | Details |
|--------|--------|---------|
| File | `mcp_manager.py` (325 lines), `mcp_server.py` (582 lines) | |
| Test file | `test_mcp_manager.py` (557), `test_mcp_server.py` (369) | |
| Role | MCP server lifecycle management; Fichero-as-MCP-server | |
| Feature status | complete | Both client and server MCP support |
| M1 recommendation | dev-only | Advanced feature |

### local_models.py (Core)
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/local_models.py`, 343 lines | |
| Test file | none | No dedicated test file |
| Role | Local model management (Ollama, fastembed) | |
| Feature status | partial | Download/delete but limited model registry |
| M1 recommendation | dev-only | Only if shipping local model support |

---

## Workflow System Audit

### Registry
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/workflows/registry.py`, 869 lines | |
| Registered tools | 39 tools across 36 tool files | via `@register_tool` decorator |
| Test file | `test_tool_registry.py` (521 lines) | |
| Tool categories | Vision (caption, describe, faces, objects, scene, layout, quality, colors, style, safety), Text (classify, entities, keywords, sentiment, summarize, rewrite, questions, tags, timeline, key_people), Document (analyze, extract, table_extract, sources, handwriting, transcribe, catalogue), Media (audio_transcribe, video_describe, convert, diagram), AI (agent, multi_agent, compare, similarity), MCP (mcp) | |

### Executor
| Aspect | Status | Details |
|--------|--------|---------|
| File | `fichero-api/src/fichero/workflows/executor.py`, 760 lines | |
| Test file | `test_workflow_executor.py` (836 lines) | |
| Role | LangGraph-based workflow execution with checkpointing, streaming, human-in-the-loop | |

### Other Workflow Modules
| Module | Lines | Role | Test Coverage |
|--------|-------|------|---------------|
| `action_library.py` | 458 | Reusable action definitions | `test_action_store.py` (88), integration (573) |
| `action_store.py` | 331 | DuckDB-backed action persistence | `test_action_store.py` (88) |
| `activity.py` | 1074 | Workflow execution activity tracking | `test_activity.py` (390) |
| `batch.py` | 700 | Batch execution engine | integration (547) |
| `builder.py` | 923 | LangGraph graph construction from workflow definitions | Covered in executor tests |
| `cache.py` | 364 | Node-level result caching | `test_node_cache.py` (512) |
| `chaining.py` | 887 | Multi-workflow chain execution | none |
| `checkpointer.py` | 446 | Async DuckDB checkpointer for LangGraph | Covered in executor tests |
| `file_watcher.py` | 926 | File system trigger engine via watchdog | none |
| `model_comparison.py` | 891 | Side-by-side model comparison engine | `test_model_comparison.py` (330) |
| `resolver.py` | 530 | Dynamic model/provider resolution | none |
| `scheduler.py` | 844 | APScheduler-based workflow scheduling | none |
| `state.py` | 476 | Workflow state management | Covered in executor tests |
| `types.py` | 505 | Workflow type definitions (WorkflowDef, NodeDef, etc.) | Covered in workflow tests |
| `validation.py` | 179 | Workflow definition validation | none |
| `workflow_store.py` | 474 | DuckDB-backed workflow persistence | Covered in CRUD tests |

---

## Test Coverage Gaps

The following modules have **no dedicated test files**:

| Module | Priority | Recommendation |
|--------|----------|----------------|
| `routes/chains.py` | Medium | Add unit tests for chain CRUD and execution |
| `routes/chat.py` | High | Add unit tests -- core user feature |
| `routes/folders.py` | Medium | Add unit tests for folder operations |
| `routes/local_models.py` | Low | Stub tests sufficient |
| `routes/models.py` | Low | External API, mock tests |
| `routes/schedules.py` | Low | Covered partially in phase8 integration |
| `routes/settings.py` | Low | Simple CRUD, low risk |
| `routes/triggers.py` | Low | Covered partially in phase8 integration |
| `keychain.py` | Medium | Security-sensitive, needs mocking tests |
| `errors.py` | Low | Utility module |
| `logging.py` | Low | Infrastructure |
| `local_models.py` (core) | Low | Dev-only feature |
| `workflows/chaining.py` | Medium | 887 lines with no tests |
| `workflows/file_watcher.py` | Medium | 926 lines with no tests |
| `workflows/resolver.py` | Medium | 530 lines with no tests |
| `workflows/scheduler.py` | Medium | 844 lines with no tests |
| `workflows/validation.py` | Low | Small module (179 lines) |

**Notable:** No formal dev/test dependency declaration in `pyproject.toml`. Test dependencies (pytest, anyio, etc.) are assumed to be installed manually.

---

## M1 Summary Table

| Module | Type | Lines | Endpoints | Test Coverage | M1 Recommendation |
|--------|------|-------|-----------|---------------|-------------------|
| **documents** | route | 313 | 12 | partial | ON |
| **search** | route | 369 | 10 | partial | ON |
| **ingest** | route | 198 | 3 | strong | ON |
| **storage** | route | 217 | 5 | strong | ON |
| **chat** | route | 617 | 9 | weak | ON |
| **providers** | route | 1329 | 18 | strong | ON |
| **workflows** | route | 721 | 15 | strong | ON |
| **workflow_execution** | route | 2343 | 16 | moderate | ON |
| **artifacts** | route | 196 | 5 | weak | ON |
| **batch** | route | 384 | 10 | moderate | ON |
| **activity** | route | 374 | 7 | moderate | ON |
| **folders** | route | 262 | 5 | none | ON |
| **settings** | route | 88 | 3 | none | ON |
| **actions** | route | 403 | 16 | moderate | DEV-ONLY |
| **integrations** | route | 485 | 15 | weak | DEV-ONLY |
| **mcp_servers** | route | 444 | 9 | strong | DEV-ONLY |
| **schedules** | route | 384 | 9 | weak | DEV-ONLY |
| **triggers** | route | 380 | 8 | weak | DEV-ONLY |
| **chains** | route | 468 | 8 | none | DEV-ONLY |
| **local_models** | route | 94 | 4 | none | DEV-ONLY |
| **model_comparison** | route | 343 | 10 | moderate | OFF |
| **models** (HF) | route | 230 | 3 | none | OFF |
| **db.py** | core | 1366 | -- | strong | ON |
| **models.py** | core | 844 | -- | moderate | ON |
| **ingest.py** | core | 669 | -- | strong | ON |
| **llm.py** | core | 1007 | -- | weak | ON |
| **providers.py** | core | 430 | -- | strong | ON |
| **bookmarks.py** | core | 314 | -- | moderate | ON |
| **app_db.py** | core | 516 | -- | weak | ON |
| **storage.py** | core | 641 | -- | strong | ON |
| **keychain.py** | core | 241 | -- | none | ON |
| **errors.py** | core | 371 | -- | none | ON |
| **logging.py** | core | 475 | -- | none | ON |
| **mcp_manager.py** | core | 325 | -- | strong | DEV-ONLY |
| **mcp_server.py** | core | 582 | -- | moderate | DEV-ONLY |
| **local_models.py** | core | 343 | -- | none | DEV-ONLY |
| **workflow registry** | workflow | 869 | -- | strong | ON |
| **workflow executor** | workflow | 760 | -- | strong | ON |
| **workflow builder** | workflow | 923 | -- | moderate | ON |
| **workflow tools (39)** | workflow | ~6000 | -- | moderate | ON |

---

## Key Findings

1. **Scale:** 22 route modules, ~170 endpoints, 39 workflow tools. This is a substantial backend for an M1.

2. **Architecture:** Clean separation -- routes are thin controllers, core modules handle business logic, workflow system is self-contained with registry pattern.

3. **Largest files by risk:**
   - `workflow_execution.py` (2343 lines) -- largest route file, handles SSE streaming + LangGraph execution. Refactor candidate.
   - `providers.py` (1329 lines) -- manages 8+ AI providers with keychain integration. Complex but well-tested.
   - `db.py` (1366 lines) -- dual-database engine. Well-tested.

4. **Test coverage:** 29 unit test files (10,444 lines) + 11 integration test files (4,873 lines) = ~15,300 lines of tests for ~37,600 lines of source. ~40% test-to-code ratio. Key gaps in chat, folders, chains, and several workflow engine modules.

5. **Missing `[project.optional-dependencies]`:** No `dev` or `test` extras declared. Test dependencies should be formalized.

6. **M1 scope recommendation:** 14 route modules ON, 6 DEV-ONLY, 2 OFF. This keeps the core document/search/chat/workflow pipeline active while deferring advanced automation (schedules, triggers, chains) and exploratory features (model comparison, HuggingFace browser).
