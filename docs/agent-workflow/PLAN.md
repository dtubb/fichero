# Fichero Milestone Plan (M0-M4)

**Created:** 2026-02-26
**Branch:** `codex/restructure-api-swiftui` (173 commits ahead of main)
**Status:** Phase 0 -- Planning. No coding until plan is approved.

---

## Table of Contents

1. [Milestone Overview](#milestone-overview)
2. [Feature Flag State by Milestone](#feature-flag-state-by-milestone)
3. [Milestone 0 -- Foundation](#milestone-0--foundation)
4. [Milestone 1 -- MVP](#milestone-1--mvp)
5. [Milestone 2 -- AI Layer](#milestone-2--ai-layer)
6. [Milestone 3 -- Polish](#milestone-3--polish)
7. [Milestone 4 -- Ship](#milestone-4--ship)
8. [Dependency Graph](#dependency-graph)
9. [Team Assignment Matrix](#team-assignment-matrix)

---

## Milestone Overview

| Milestone | Goal | Key Deliverable | Est. Duration |
|-----------|------|-----------------|---------------|
| **M0** | Foundation | Build passes, tests pass, flags infra in place | 1-2 weeks |
| **M1** | MVP | Core doc management + search + basic workflows working | 2-3 weeks |
| **M2** | AI Layer | Chat, workflow execution, batch, activity fully tested | 2-3 weeks |
| **M3** | Polish | Full feature set, automation, chains, integrations, docs | 3-4 weeks |
| **M4** | Ship | Release-ready, all flags ON, distribution prep | 1-2 weeks |

---

## Feature Flag State by Milestone

### Frontend Flags (Swift)

| Flag | M0 | M1 | M2 | M3 | M4 |
|------|----|----|----|----|-----|
| `featureLibrary` | ON | ON | ON | ON | ON |
| `featureDocuments` | ON | ON | ON | ON | ON |
| `featureIngest` | ON | ON | ON | ON | ON |
| `featureStorage` | ON | ON | ON | ON | ON |
| `featureSearch` | ON | ON | ON | ON | ON |
| `featureSettings` | ON | ON | ON | ON | ON |
| `featureSidebar` | ON | ON | ON | ON | ON |
| `featureToolbars` | ON | ON | ON | ON | ON |
| `featureMenu` | ON | ON | ON | ON | ON |
| `featureComponents` | ON | ON | ON | ON | ON |
| `featureSheets` | ON | ON | ON | ON | ON |
| `featureFolders` | ON | ON | ON | ON | ON |
| `featureProviders` | OFF | ON | ON | ON | ON |
| `featureAIProviders` | OFF | ON | ON | ON | ON |
| `featureChat` | OFF | OFF | ON | ON | ON |
| `featureWorkflow` | OFF | OFF | ON | ON | ON |
| `featureWorkflowExecution` | OFF | OFF | ON | ON | ON |
| `featureActivity` | OFF | OFF | ON | ON | ON |
| `featureBatch` | OFF | OFF | ON | ON | ON |
| `featureActions` | OFF | OFF | DEV | ON | ON |
| `featureAgents` | OFF | OFF | DEV | ON | ON |
| `featureAutomation` | OFF | OFF | OFF | ON | ON |
| `featureIntegrations` | OFF | OFF | OFF | ON | ON |
| `featureMCPServers` | OFF | OFF | DEV | ON | ON |
| `featureChains` | OFF | OFF | OFF | ON | ON |
| `featureSchedules` | OFF | OFF | OFF | ON | ON |
| `featureTriggers` | OFF | OFF | OFF | ON | ON |
| `featureLocalModels` | OFF | OFF | OFF | DEV | ON |
| `featureModelComparison` | OFF | OFF | OFF | DEV | ON |
| `featureModels` | OFF | OFF | OFF | OFF | ON |

### Backend Flags (Python)

| Flag | M0 | M1 | M2 | M3 | M4 |
|------|----|----|----|----|-----|
| `FEATURE_DOCUMENTS` | ON | ON | ON | ON | ON |
| `FEATURE_SEARCH` | ON | ON | ON | ON | ON |
| `FEATURE_INGEST` | ON | ON | ON | ON | ON |
| `FEATURE_STORAGE` | ON | ON | ON | ON | ON |
| `FEATURE_FOLDERS` | ON | ON | ON | ON | ON |
| `FEATURE_SETTINGS` | ON | ON | ON | ON | ON |
| `FEATURE_PROVIDERS` | OFF | ON | ON | ON | ON |
| `FEATURE_CHAT` | OFF | OFF | ON | ON | ON |
| `FEATURE_WORKFLOWS` | OFF | OFF | ON | ON | ON |
| `FEATURE_WORKFLOW_EXECUTION` | OFF | OFF | ON | ON | ON |
| `FEATURE_ACTIVITY` | OFF | OFF | ON | ON | ON |
| `FEATURE_BATCH` | OFF | OFF | ON | ON | ON |
| `FEATURE_ARTIFACTS` | OFF | OFF | ON | ON | ON |
| `FEATURE_ACTIONS` | OFF | OFF | DEV | ON | ON |
| `FEATURE_MCP_SERVERS` | OFF | OFF | DEV | ON | ON |
| `FEATURE_INTEGRATIONS` | OFF | OFF | OFF | ON | ON |
| `FEATURE_CHAINS` | OFF | OFF | OFF | ON | ON |
| `FEATURE_SCHEDULES` | OFF | OFF | OFF | ON | ON |
| `FEATURE_TRIGGERS` | OFF | OFF | OFF | ON | ON |
| `FEATURE_LOCAL_MODELS` | OFF | OFF | OFF | DEV | ON |
| `FEATURE_MODEL_COMPARISON` | OFF | OFF | OFF | DEV | ON |
| `FEATURE_MODELS` | OFF | OFF | OFF | OFF | ON |

**Key:** ON = enabled for all users. DEV = enabled only when `FICHERO_DEV_MODE=1`. OFF = disabled.

---

## Milestone 0 -- Foundation

**Goal:** The project builds, tests pass, lint is clean, and the feature flag infrastructure exists. No new features. Pure stability.

### Features Included

| Feature | Swift Flag | Python Flag | State |
|---------|-----------|-------------|-------|
| Library (view only) | `featureLibrary` ON | `FEATURE_DOCUMENTS` ON | Existing |
| Document CRUD | `featureDocuments` ON | `FEATURE_DOCUMENTS` ON | Existing |
| Ingest pipeline | `featureIngest` ON | `FEATURE_INGEST` ON | Existing |
| Storage layer | `featureStorage` ON | `FEATURE_STORAGE` ON | Existing |
| Search | `featureSearch` ON | `FEATURE_SEARCH` ON | Existing |
| Settings | `featureSettings` ON | `FEATURE_SETTINGS` ON | Existing |
| Sidebar nav | `featureSidebar` ON | -- | Existing |
| Folders | `featureFolders` ON | `FEATURE_FOLDERS` ON | Existing |
| Toolbars / Menu / Components / Sheets | All ON | -- | Existing |
| Feature flags infra | -- | -- | **New** |

All AI-dependent features (chat, workflows, providers, batch, activity) are OFF. The app launches and shows the document library with search but no AI capabilities.

### Acceptance Criteria

1. `xcodebuild -scheme fichero -destination 'platform=macOS' build` exits 0
2. `cd fichero-engine && PYTHONPATH=src python -m pytest tests/ -x` passes with 0 failures
3. `swiftlint lint --reporter json fichero/` produces 0 errors (warnings acceptable)
4. `pylint fichero-engine/src/fichero/ --disable=all --enable=E` produces 0 errors
5. `FeatureFlags.swift` exists at `fichero/fichero/App/FeatureFlags.swift` and compiles
6. `feature_flags.py` exists at `fichero-engine/src/fichero/feature_flags.py` and passes import test
7. `GET /api/feature-flags` returns valid JSON with all expected keys
8. OpenAPI schema at `fichero-engine/openapi.json` validates (no dangling refs, all M0-ON routes present)
9. `ContractTests.swift` and `EndpointValidationTests.swift` pass
10. A `CONTRIBUTING.md` or equivalent doc describes how to set up the dev environment from scratch

### Task List

| # | Task | Team | Size | Depends On |
|---|------|------|------|------------|
| M0-1 | Fix all xcodebuild errors (get build to green) | swift-dev | L | -- |
| M0-2 | Fix all pytest failures (get test suite to green) | python-dev | L | -- |
| M0-3 | Create `feature_flags.py` with all flags and `as_dict()` | python-dev | S | -- |
| M0-4 | Add `/api/feature-flags` endpoint to `main.py` | python-dev | S | M0-3 |
| M0-5 | Gate backend route registration with flag checks in `main.py` | python-dev | M | M0-3, M0-4 |
| M0-6 | Create `FeatureFlags.swift` singleton with all flags | swift-dev | S | -- |
| M0-7 | Add `syncFromBackend()` and `mergeFromBackend()` to FeatureFlags.swift | swift-dev | S | M0-6 |
| M0-8 | Wire flag sync into `FicheroApp.swift` startup flow | swift-dev | S | M0-7 |
| M0-9 | Gate sidebar modes with feature flag checks | swift-dev | S | M0-6 |
| M0-10 | Gate menu items with feature flag checks | swift-dev | S | M0-6 |
| M0-11 | Gate ContentView navigation routing with flag checks | swift-dev | M | M0-6 |
| M0-12 | Run swiftlint, fix all errors (not warnings) | swift-dev | M | M0-1 |
| M0-13 | Run pylint error-level check, fix all errors | python-dev | M | M0-2 |
| M0-14 | Validate OpenAPI schema; fix any dangling refs | python-dev | S | M0-5 |
| M0-15 | Verify ContractTests and EndpointValidationTests pass | swift-dev | S | M0-1, M0-14 |
| M0-16 | Formalize test dependencies in `pyproject.toml` `[project.optional-dependencies]` | python-dev | S | -- |
| M0-17 | Add Xcode scheme env var `FICHERO_DEV_MODE=1` to Debug scheme | swift-dev | S | M0-6 |
| M0-18 | Write dev environment setup doc (build steps, env vars, test commands) | docs | M | M0-1, M0-2 |

### Critical Path

```
M0-1 (build green) --> M0-12 (swiftlint) --> M0-15 (contract tests)
M0-2 (pytest green) --> M0-13 (pylint) --> M0-14 (OpenAPI validate)
M0-3 (feature_flags.py) --> M0-4 (/api/feature-flags) --> M0-5 (gate routes)
M0-6 (FeatureFlags.swift) --> M0-7 (sync) --> M0-8 (wire startup)
```

### Parallel Tracks

| Track | Tasks | Team |
|-------|-------|------|
| Swift build stabilization | M0-1, M0-6, M0-7, M0-8, M0-9, M0-10, M0-11, M0-12, M0-15, M0-17 | swift-dev |
| Python build stabilization | M0-2, M0-3, M0-4, M0-5, M0-13, M0-14, M0-16 | python-dev |
| Documentation | M0-18 | docs |

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| xcodebuild fails with many errors due to 173-commit divergence | High -- blocks all Swift work | Prioritize M0-1; may need to stub out broken imports behind `#if` temporarily |
| pytest failures cascade (database setup issues) | Medium | Isolate test fixtures; fix conftest.py first |
| OpenAPI schema drift between backend routes and generated Swift client | High -- contract tests fail | Regenerate OpenAPI schema from running backend, then regenerate Swift client |
| Feature flag gating accidentally breaks existing navigation flow | Medium | Test the M0 flag configuration manually before moving on |

---

## Milestone 1 -- MVP

**Goal:** Core document management features fully working and tested. User can: launch app, create a library, ingest documents, browse them, search, configure AI providers, and view settings. No AI execution yet.

### Features Included

| Feature | Swift Flag | Python Flag | State | Change from M0 |
|---------|-----------|-------------|-------|-----------------|
| Library | ON | ON | Tested | Unchanged |
| Documents | ON | ON | Tested | Unchanged |
| Ingest | ON | ON | Tested | Unchanged |
| Storage | ON | ON | Tested | Unchanged |
| Search | ON | ON | Tested | Unchanged |
| Settings | ON | ON | Tested | Unchanged |
| Sidebar | ON | -- | Tested | Unchanged |
| Folders | ON | ON | Tested | Unchanged |
| **Providers** | **ON** | **ON** | **Tested** | **OFF -> ON** |
| **AI Providers UI** | **ON** | -- | **Tested** | **OFF -> ON** |
| Feature flags | ON | ON | Tested | Unchanged |

### Acceptance Criteria

1. All M0 acceptance criteria still pass (non-regression)
2. User can create a new .fichero library package from the app
3. User can ingest a PDF, JPEG, and plain text file; all appear in Library view
4. User can search by filename and by content (full-text)
5. User can add an AI provider (e.g., OpenAI) with an API key and see its models listed
6. All M1-ON backend routes have at least one passing unit test per endpoint
7. All M1-ON frontend views have at least one basic test (render test or model test)
8. `xcodebuild test` passes for the fichero-tests target
9. `pytest fichero-engine/tests/` passes with 0 failures, coverage report generated
10. Sidebar shows only: Library, Search (other modes hidden by flags)

### Task List

| # | Task | Team | Size | Depends On |
|---|------|------|------|------------|
| M1-1 | Enable `FEATURE_PROVIDERS` flag; verify providers routes load | python-dev | S | M0 complete |
| M1-2 | Enable `featureProviders` + `featureAIProviders` flags | swift-dev | S | M0 complete |
| M1-3 | Write unit tests for `routes/documents.py` (all 12 endpoints) | python-dev | M | M0 complete |
| M1-4 | Write unit tests for `routes/folders.py` (all 5 endpoints) | python-dev | S | M0 complete |
| M1-5 | Write unit tests for `routes/search.py` (saved searches CRUD) | python-dev | M | M0 complete |
| M1-6 | Write unit tests for `routes/settings.py` (3 endpoints) | python-dev | S | M0 complete |
| M1-7 | Write unit tests for `routes/providers.py` -- fill gaps in existing coverage | python-dev | M | M1-1 |
| M1-8 | Write unit tests for `keychain.py` (mock macOS keychain calls) | python-dev | M | M0 complete |
| M1-9 | Write basic render/snapshot tests for LibraryView | swift-dev | M | M0 complete |
| M1-10 | Write basic tests for SearchView | swift-dev | S | M0 complete |
| M1-11 | Write basic tests for SettingsView | swift-dev | S | M0 complete |
| M1-12 | Write basic tests for ProvidersView / AddProviderSheet | swift-dev | M | M1-2 |
| M1-13 | End-to-end test: ingest a document, verify it appears in search | python-dev | M | M1-3, M1-5 |
| M1-14 | Verify sidebar only shows Library + Search when non-M1 flags are OFF | swift-dev | S | M0-9 |
| M1-15 | Generate pytest coverage report; verify M1-ON routes are >= 60% covered | python-dev | S | M1-3 through M1-8 |
| M1-16 | Fix any remaining swiftlint warnings (not just errors) for M1-ON view areas | swift-dev | M | M1-9 through M1-12 |
| M1-17 | Verify OpenAPI contract tests still pass after provider routes are enabled | swift-dev | S | M1-1, M1-2 |
| M1-18 | Manual QA pass: library creation, ingest, search, provider setup flow | docs | M | All M1 tasks |

### Critical Path

```
M0 complete --> M1-1 (enable providers backend) --> M1-7 (provider tests)
M0 complete --> M1-3 (document tests) --> M1-13 (E2E ingest+search)
M0 complete --> M1-9 (library view tests) --> M1-16 (swiftlint cleanup)
```

### Parallel Tracks

| Track | Tasks | Team |
|-------|-------|------|
| Backend test coverage | M1-1, M1-3, M1-4, M1-5, M1-6, M1-7, M1-8, M1-13, M1-15 | python-dev |
| Frontend test coverage + flags | M1-2, M1-9, M1-10, M1-11, M1-12, M1-14, M1-16, M1-17 | swift-dev |
| QA | M1-18 | docs |

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Provider API key storage via keychain fails in test environment | Medium | Use mock keychain for tests; real keychain only in integration |
| Search requires LanceDB embeddings which need a model provider | High -- search may not work without providers | Ensure full-text search works standalone; semantic search requires M2 providers |
| Generated Swift client types drift from backend models | Medium | Re-run openapi-generator if contract tests fail |

---

## Milestone 2 -- AI Layer

**Goal:** All AI-powered features are working: chat, workflow editor, workflow execution, batch processing, and activity monitoring. Users can build and run AI workflows against their documents.

### Features Included

| Feature | Swift Flag | Python Flag | State | Change from M1 |
|---------|-----------|-------------|-------|-----------------|
| All M1 features | ON | ON | Tested | Unchanged |
| **Chat** | **ON** | **ON** | **Tested** | **OFF -> ON** |
| **Workflows** | **ON** | **ON** | **Tested** | **OFF -> ON** |
| **Workflow Execution** | **ON** | **ON** | **Tested** | **OFF -> ON** |
| **Activity** | **ON** | **ON** | **Tested** | **OFF -> ON** |
| **Batch** | **ON** | **ON** | **Tested** | **OFF -> ON** |
| **Artifacts** | -- | **ON** | **Tested** | **OFF -> ON** |
| **Actions** | DEV | DEV | Dev-tested | **OFF -> DEV** |
| **Agents** | DEV | -- | Dev-tested | **OFF -> DEV** |
| **MCP Servers** | DEV | DEV | Dev-tested | **OFF -> DEV** |

### Acceptance Criteria

1. All M1 acceptance criteria still pass
2. User can open a chat conversation, select a provider/model, and get a response
3. User can create a workflow in the canvas editor with at least 2 nodes
4. User can execute a workflow and see SSE-streamed results in the output log
5. User can run a batch job on multiple documents and monitor progress
6. Activity view shows execution history with status, duration, and error details
7. Workflow artifacts are created and viewable in the document inspector
8. All M2-ON backend routes have unit tests with >= 60% line coverage
9. `WorkflowCanvasTests` and `WorkflowStreamParsingTests` pass
10. SSE streaming works end-to-end (backend sends events, frontend receives and displays them)
11. Sidebar shows: Library, Search, Chat, Workflows, Batches, Activity
12. DEV-only features (Actions, Agents, MCP) accessible when `FICHERO_DEV_MODE=1`

### Task List

| # | Task | Team | Size | Depends On |
|---|------|------|------|------------|
| M2-1 | Enable chat flags (frontend + backend); verify chat routes load | python-dev | S | M1 complete |
| M2-2 | Enable workflow + execution flags (frontend + backend) | python-dev | S | M1 complete |
| M2-3 | Enable batch + activity + artifacts flags | python-dev | S | M1 complete |
| M2-4 | Write unit tests for `routes/chat.py` (9 endpoints) | python-dev | L | M2-1 |
| M2-5 | Write unit tests for `routes/workflows.py` -- fill gaps | python-dev | M | M2-2 |
| M2-6 | Write unit tests for `routes/workflow_execution.py` -- SSE streaming tests | python-dev | L | M2-2 |
| M2-7 | Write unit tests for `routes/batch.py` -- fill gaps in integration tests | python-dev | M | M2-3 |
| M2-8 | Write unit tests for `routes/activity.py` -- fill gaps | python-dev | S | M2-3 |
| M2-9 | Write unit tests for `routes/artifacts.py` | python-dev | S | M2-3 |
| M2-10 | Write tests for `workflows/resolver.py` (530 lines, 0 tests) | python-dev | M | M2-2 |
| M2-11 | Write tests for `workflows/validation.py` (179 lines, 0 tests) | python-dev | S | M2-2 |
| M2-12 | Write basic tests for ChatView | swift-dev | M | M2-1 |
| M2-13 | Write basic tests for WorkflowEditor / WorkflowCanvasView | swift-dev | M | M2-2 |
| M2-14 | Write basic tests for BatchDetailView | swift-dev | S | M2-3 |
| M2-15 | Write basic tests for ActivityDetailView | swift-dev | S | M2-3 |
| M2-16 | Fix the Activity data loading TODO (pending backend schema update) | python-dev | M | M2-3, M2-8 |
| M2-17 | End-to-end test: create workflow, execute on document, verify artifact created | python-dev | L | M2-5, M2-6, M2-9 |
| M2-18 | SSE streaming integration test (backend sends events, verify format) | python-dev | M | M2-6 |
| M2-19 | Enable DEV-only flags (actions, MCP); verify routes load under dev mode | python-dev | S | M2-1 |
| M2-20 | Verify sidebar shows correct modes for M2 flag configuration | swift-dev | S | M2-1, M2-2, M2-3 |
| M2-21 | Generate coverage report; verify M2-ON routes >= 60% covered | python-dev | S | M2-4 through M2-11 |
| M2-22 | Manual QA: full chat session, workflow build + run, batch execution | docs | L | All M2 tasks |

### Critical Path

```
M1 complete --> M2-2 (enable workflows) --> M2-6 (execution tests) --> M2-17 (E2E workflow)
M1 complete --> M2-1 (enable chat) --> M2-4 (chat tests) --> M2-22 (QA)
M2-3 (enable batch/activity) --> M2-16 (fix activity data loading)
```

### Parallel Tracks

| Track | Tasks | Team |
|-------|-------|------|
| Backend: chat + providers | M2-1, M2-4, M2-19 | python-dev |
| Backend: workflows + execution | M2-2, M2-5, M2-6, M2-10, M2-11, M2-17, M2-18 | python-dev |
| Backend: batch + activity + artifacts | M2-3, M2-7, M2-8, M2-9, M2-16 | python-dev |
| Frontend: AI views | M2-12, M2-13, M2-14, M2-15, M2-20 | swift-dev |
| QA | M2-22 | docs |

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| LangGraph execution requires valid provider credentials in tests | High | Use mock LLM responses for unit tests; real provider only in manual QA |
| SSE streaming parsing differs between backend output and Swift client expectations | High | M2-18 validates format; WorkflowStreamParsingTests validates Swift side |
| Workflow canvas has complex gesture handling that is hard to unit test | Medium | Focus on data model tests (WorkflowCanvasTests); manual QA for gesture UX |
| Activity data loading TODO may require schema migration | Medium | M2-16 addresses this; if blocked, skip and track for M3 |
| 39 workflow tools may have inconsistent interfaces | Medium | M2-10 (resolver tests) and M2-11 (validation tests) catch mismatches |

---

## Milestone 3 -- Polish

**Goal:** Full feature set enabled. Automation (schedules, triggers), chains, MCP integration, third-party app integrations. Documentation complete. Error handling audited. Performance acceptable.

### Features Included

| Feature | Swift Flag | Python Flag | State | Change from M2 |
|---------|-----------|-------------|-------|-----------------|
| All M2 features | ON | ON | Tested | Unchanged |
| **Actions** | **ON** | **ON** | **Tested** | **DEV -> ON** |
| **Agents** | **ON** | -- | **Tested** | **DEV -> ON** |
| **MCP Servers** | **ON** | **ON** | **Tested** | **DEV -> ON** |
| **Automation UI** | **ON** | -- | **Tested** | **OFF -> ON** |
| **Schedules** | **ON** | **ON** | **Tested** | **OFF -> ON** |
| **Triggers** | **ON** | **ON** | **Tested** | **OFF -> ON** |
| **Chains** | **ON** | **ON** | **Tested** | **OFF -> ON** |
| **Integrations** | **ON** | **ON** | **Tested** | **OFF -> ON** |
| Local Models | DEV | DEV | Dev-tested | **OFF -> DEV** |
| Model Comparison | DEV | DEV | Dev-tested | **OFF -> DEV** |

### Acceptance Criteria

1. All M2 acceptance criteria still pass
2. User can create a schedule (cron-based) that triggers a workflow automatically
3. User can create a file system trigger that fires when files are added to a watched folder
4. User can chain two workflows together and execute the chain
5. MCP servers can be added, tools loaded, and used in workflow nodes
6. Integrations panel shows available macOS apps; items can be imported from DEVONthink/Bookends
7. All M3-ON backend routes have unit tests with >= 70% line coverage
8. `workflows/chaining.py` has tests (was 0 coverage)
9. `workflows/scheduler.py` has tests (was 0 coverage)
10. `workflows/file_watcher.py` has tests (was 0 coverage)
11. All 7 frontend TODOs from the audit are resolved or explicitly deferred with tracking issues
12. Error handling audit: all routes return proper HTTP status codes and structured error responses
13. User guide draft exists covering: library setup, document ingest, workflow creation, chat usage
14. Developer guide exists covering: architecture overview, adding a new workflow tool, adding a new route
15. App responds to document ingest of 100 files in under 60 seconds (performance baseline)

### Task List

| # | Task | Team | Size | Depends On |
|---|------|------|------|------------|
| M3-1 | Promote Actions, Agents, MCP flags from DEV to ON | swift-dev + python-dev | S | M2 complete |
| M3-2 | Enable Automation, Schedules, Triggers flags (frontend + backend) | swift-dev + python-dev | S | M2 complete |
| M3-3 | Enable Chains flag (frontend + backend) | python-dev | S | M2 complete |
| M3-4 | Enable Integrations flag (frontend + backend) | python-dev | S | M2 complete |
| M3-5 | Write unit tests for `routes/chains.py` (8 endpoints) | python-dev | M | M3-3 |
| M3-6 | Write unit tests for `routes/schedules.py` (9 endpoints) | python-dev | M | M3-2 |
| M3-7 | Write unit tests for `routes/triggers.py` (8 endpoints) | python-dev | M | M3-2 |
| M3-8 | Write unit tests for `routes/mcp_servers.py` -- fill gaps | python-dev | S | M3-1 |
| M3-9 | Write unit tests for `routes/actions.py` -- fill gaps | python-dev | S | M3-1 |
| M3-10 | Write tests for `workflows/chaining.py` (887 lines, 0 tests) | python-dev | L | M3-3 |
| M3-11 | Write tests for `workflows/scheduler.py` (844 lines, 0 tests) | python-dev | L | M3-2 |
| M3-12 | Write tests for `workflows/file_watcher.py` (926 lines, 0 tests) | python-dev | L | M3-2 |
| M3-13 | Write basic tests for AutomationView (ScheduleEditor, TriggerEditor) | swift-dev | M | M3-2 |
| M3-14 | Write basic tests for MCPServersView | swift-dev | S | M3-1 |
| M3-15 | Write basic tests for IntegrationsView | swift-dev | S | M3-4 |
| M3-16 | Write basic tests for ChainEditorView | swift-dev | S | M3-3 |
| M3-17 | Resolve TODO: Activity data loading (schema update) if not done in M2 | python-dev | M | M3-1 |
| M3-18 | Resolve TODO: Batch SSE streaming navigation (Library + DocumentPickerSheet) | swift-dev | M | M3-1 |
| M3-19 | Resolve TODO: Library-scoped filtering for batches/automation in sidebar | swift-dev | M | M3-2 |
| M3-20 | Resolve TODO: Activity view navigation from workflow execution | swift-dev | S | M3-1 |
| M3-21 | Error handling audit: verify all routes use structured error responses | python-dev | M | M3-5 through M3-9 |
| M3-22 | Performance test: ingest 100 files, measure time, identify bottlenecks | python-dev | M | M2 complete |
| M3-23 | Performance optimization: fix any bottleneck identified in M3-22 | python-dev | L | M3-22 |
| M3-24 | Write user guide (library, ingest, workflows, chat, search) | docs | L | M2 complete |
| M3-25 | Write developer guide (architecture, adding tools, adding routes) | docs | L | M2 complete |
| M3-26 | Enable Local Models and Model Comparison as DEV-only | python-dev | S | M3-1 |
| M3-27 | Generate coverage report; verify overall backend coverage >= 70% | python-dev | S | M3-5 through M3-12 |
| M3-28 | Manual QA: automation (schedule + trigger), chain execution, MCP tools, integrations | docs | L | All M3 tasks |

### Critical Path

```
M2 complete --> M3-2 (enable automation) --> M3-11 (scheduler tests) --> M3-12 (watcher tests)
M2 complete --> M3-3 (enable chains) --> M3-10 (chaining tests) --> M3-5 (chain route tests)
M3-22 (perf test) --> M3-23 (perf fix)
All tests --> M3-27 (coverage report) --> M3-28 (QA)
```

### Parallel Tracks

| Track | Tasks | Team |
|-------|-------|------|
| Backend: automation engine | M3-2, M3-6, M3-7, M3-11, M3-12 | python-dev |
| Backend: chains + actions + MCP | M3-1, M3-3, M3-5, M3-8, M3-9, M3-10 | python-dev |
| Backend: quality | M3-21, M3-22, M3-23, M3-27 | python-dev |
| Frontend: automation + advanced views | M3-13, M3-14, M3-15, M3-16, M3-17, M3-18, M3-19, M3-20 | swift-dev |
| Documentation | M3-24, M3-25 | docs |
| QA | M3-28 | docs |

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| APScheduler (scheduler.py) may have thread-safety issues in async context | High | M3-11 tests should exercise concurrent scheduling; add asyncio-safe guards |
| File watcher (watchdog) may behave differently in macOS sandbox | High | Test in sandboxed environment; may need to use FSEvents directly |
| Integration with DEVONthink/Bookends requires those apps to be installed | Medium | Mock AppleScript calls in tests; manual QA on machines with the apps |
| chaining.py is 887 lines with zero tests -- high defect probability | High | M3-10 is large but essential; budget extra time |
| Performance optimization may require architectural changes to ingest pipeline | Medium | M3-23 is sized L; if changes are too large, defer to M4 |

---

## Milestone 4 -- Ship

**Goal:** Release-ready. All flags ON. Final QA. Distribution preparation. Blog published.

### Features Included

| Feature | Swift Flag | Python Flag | State | Change from M3 |
|---------|-----------|-------------|-------|-----------------|
| All M3 features | ON | ON | Tested | Unchanged |
| **Local Models** | **ON** | **ON** | **Tested** | **DEV -> ON** |
| **Model Comparison** | **ON** | **ON** | **Tested** | **DEV -> ON** |
| **Models (HuggingFace)** | **ON** | **ON** | **Tested** | **OFF -> ON** |

### Acceptance Criteria

1. All M3 acceptance criteria still pass
2. All feature flags are ON (no DEV-only or OFF features remain)
3. `xcodebuild -scheme fichero -configuration Release build` succeeds
4. Full test suite (Swift + Python) passes in CI-like environment
5. Backend coverage >= 75% overall
6. Zero pylint errors, zero swiftlint errors
7. App runs for 30 minutes under normal usage without crash or memory leak > 500MB
8. User guide and developer guide reviewed and finalized
9. App icon, About screen, and version number are set
10. Blog post draft completed covering: what Fichero is, architecture, AI workflow system
11. Distribution method decided and prepared (DMG, TestFlight, or direct download)
12. Release notes document exists

### Task List

| # | Task | Team | Size | Depends On |
|---|------|------|------|------------|
| M4-1 | Promote all remaining flags to ON (local models, model comparison, HF models) | swift-dev + python-dev | S | M3 complete |
| M4-2 | Write unit tests for `routes/local_models.py` (4 endpoints) | python-dev | S | M4-1 |
| M4-3 | Write unit tests for `routes/model_comparison.py` -- fill gaps | python-dev | S | M4-1 |
| M4-4 | Write unit tests for `routes/models.py` (3 endpoints, mock HF API) | python-dev | S | M4-1 |
| M4-5 | Write basic tests for ModelComparisonView | swift-dev | S | M4-1 |
| M4-6 | Write basic tests for LocalModelsSettingsView | swift-dev | S | M4-1 |
| M4-7 | Final swiftlint pass: zero errors across entire project | swift-dev | M | M4-1 |
| M4-8 | Final pylint pass: zero errors across entire project | python-dev | M | M4-1 |
| M4-9 | Memory profiling: run app for 30 min with Instruments, fix leaks | swift-dev | L | M4-1 |
| M4-10 | Set app version, build number, About screen content | swift-dev | S | M3 complete |
| M4-11 | Create app icon (if not done) | docs | M | -- |
| M4-12 | Review and finalize user guide | docs | M | M3-24 |
| M4-13 | Review and finalize developer guide | docs | M | M3-25 |
| M4-14 | Write blog post: Fichero overview, architecture, AI workflow system | docs | L | M3 complete |
| M4-15 | Prepare distribution: create DMG or notarized .app archive | swift-dev | M | M4-7, M4-9, M4-10 |
| M4-16 | Write release notes | docs | S | M4-15 |
| M4-17 | Final QA: exercise every feature, every sidebar mode, every settings tab | docs | L | All M4 tasks |
| M4-18 | Remove or archive feature flag infrastructure (optional -- may keep for future) | swift-dev + python-dev | M | M4-17 |

### Critical Path

```
M3 complete --> M4-1 (all flags ON) --> M4-7 (swiftlint) + M4-9 (memory) --> M4-15 (distribution) --> M4-17 (final QA)
```

### Parallel Tracks

| Track | Tasks | Team |
|-------|-------|------|
| Backend finalization | M4-1 (partial), M4-2, M4-3, M4-4, M4-8 | python-dev |
| Frontend finalization | M4-1 (partial), M4-5, M4-6, M4-7, M4-9, M4-10, M4-15 | swift-dev |
| Documentation + marketing | M4-11, M4-12, M4-13, M4-14, M4-16 | docs |
| QA | M4-17 | docs |

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Memory leaks from long-running LangGraph execution or SSE streams | High | M4-9 specifically targets this; use Instruments Allocations + Leaks |
| Code signing / notarization issues for macOS distribution | High | Test notarization early; budget time for Apple Developer account setup |
| HuggingFace model browser depends on external API availability | Low | Graceful degradation if HF API is unreachable |
| Blog post requires screenshots/demos which depend on working app | Medium | Take screenshots as features stabilize in M3 |

---

## Dependency Graph

```
M0 Foundation
|
|-- M0-1: xcodebuild green ---------> M0-12: swiftlint ------> M0-15: contract tests
|-- M0-2: pytest green -------------> M0-13: pylint ---------> M0-14: OpenAPI validate
|-- M0-3: feature_flags.py ---------> M0-4: /api/feature-flags -> M0-5: gate routes
|-- M0-6: FeatureFlags.swift -------> M0-7: sync ------------> M0-8: wire startup
|                                                                --> M0-9: gate sidebar
|                                                                --> M0-10: gate menus
|                                                                --> M0-11: gate navigation
|
v
M1 MVP (requires all M0 complete)
|
|-- M1-1: providers backend --------> M1-7: provider tests
|-- M1-3: document tests -----------> M1-13: E2E ingest+search
|-- M1-9: library view tests -------> M1-16: swiftlint cleanup
|
v
M2 AI Layer (requires all M1 complete)
|
|-- M2-1: enable chat --------------> M2-4: chat tests
|-- M2-2: enable workflows ---------> M2-6: execution tests --> M2-17: E2E workflow
|-- M2-3: enable batch/activity ----> M2-16: fix activity TODO
|
v
M3 Polish (requires all M2 complete)
|
|-- M3-2: enable automation --------> M3-11: scheduler tests -> M3-12: watcher tests
|-- M3-3: enable chains ------------> M3-10: chaining tests --> M3-5: chain route tests
|-- M3-22: perf test ---------------> M3-23: perf fix
|-- M3-24 + M3-25: docs (can start during M2)
|
v
M4 Ship (requires all M3 complete)
|
|-- M4-1: all flags ON -------------> M4-7: swiftlint final -> M4-15: distribution
|                                 --> M4-9: memory profiling -> M4-15
|-- M4-14: blog post
|-- M4-17: final QA (last task)
```

### Cross-Milestone Dependencies

- **M3-24 (user guide) and M3-25 (developer guide)** can begin during M2 once features are stabilizing.
- **M4-14 (blog post)** can begin drafting during M3.
- **M4-11 (app icon)** has no code dependency and can happen at any time.

---

## Team Assignment Matrix

### Team Definitions

| Team | Role | Capabilities |
|------|------|-------------|
| **swift-dev** | SwiftUI frontend development | Xcode, Swift, SwiftUI, swiftlint, XCTest |
| **python-dev** | Python backend development | FastAPI, pytest, DuckDB, LangChain, LangGraph |
| **docs** | Documentation, QA, marketing | Markdown, manual testing, blog writing |

### Ownership by Feature Area

| Feature Area | Primary Owner | Secondary |
|-------------|---------------|-----------|
| FeatureFlags.swift | swift-dev | -- |
| feature_flags.py | python-dev | -- |
| Sidebar gating | swift-dev | -- |
| Route gating | python-dev | -- |
| Library / Documents | swift-dev (views) + python-dev (routes) | -- |
| Search | swift-dev (views) + python-dev (routes) | -- |
| Ingest | python-dev | -- |
| Storage | python-dev | -- |
| Providers | swift-dev (views) + python-dev (routes) | -- |
| Chat | swift-dev (views) + python-dev (routes) | -- |
| Workflows | swift-dev (canvas/editor) + python-dev (engine/executor) | -- |
| Batch / Activity | swift-dev (views) + python-dev (routes + engine) | -- |
| Automation (schedules/triggers) | swift-dev (views) + python-dev (engine) | -- |
| Chains | swift-dev (views) + python-dev (engine) | -- |
| MCP | swift-dev (views) + python-dev (manager) | -- |
| Integrations | swift-dev (views) + python-dev (AppleScript bridge) | -- |
| OpenAPI / contract tests | swift-dev | python-dev |
| User guide | docs | swift-dev (screenshots) |
| Developer guide | docs | python-dev (architecture details) |
| Blog post | docs | -- |
| Distribution / signing | swift-dev | -- |
| Performance | python-dev (backend) | swift-dev (frontend profiling) |

### Task Count by Team per Milestone

| Team | M0 | M1 | M2 | M3 | M4 | Total |
|------|----|----|----|----|-----|-------|
| swift-dev | 10 | 8 | 5 | 8 | 8 | 39 |
| python-dev | 7 | 9 | 13 | 14 | 6 | 49 |
| docs | 1 | 1 | 1 | 4 | 5 | 12 |

---

## Appendix: Size Estimates

| Size | Meaning | Approximate Effort |
|------|---------|-------------------|
| **S** | Small, well-scoped, single-file change | 1-2 hours / 1 agent session |
| **M** | Medium, multi-file, some investigation needed | 3-6 hours / 1-2 agent sessions |
| **L** | Large, complex, may require iteration | 6-12 hours / 2-4 agent sessions |

### Total Estimated Effort

| Milestone | S tasks | M tasks | L tasks | Est. agent-sessions |
|-----------|---------|---------|---------|---------------------|
| M0 | 9 | 5 | 2 | 15-25 |
| M1 | 6 | 8 | 0 | 12-22 |
| M2 | 6 | 8 | 3 | 18-32 |
| M3 | 5 | 10 | 5 | 25-45 |
| M4 | 5 | 6 | 3 | 16-28 |
| **Total** | **31** | **37** | **13** | **86-152** |
