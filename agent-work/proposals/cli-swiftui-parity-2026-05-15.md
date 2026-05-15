# CLI ↔ SwiftUI Endpoint Parity Audit — 2026-05-15

Branch: `0.0.2`. Working dir: `/Users/danieltubb/code/fichero-0.0.2`.

**Scope.** Cross-references every endpoint the SwiftUI app calls (via the
hand-written `fichero/fichero/Services/*Generated.swift` wrappers built on top
of the OpenAPI-generated `Components.Schemas.*`) against every method exposed
by the typed CLI (`fichero-engine/src/fichero/cli/client.py`), and against the
backend's declared `response_model=` (the source of truth Pydantic types in
`fichero-engine/src/fichero/api/routes/`).

**Status legend.**

- `parity` — both surfaces hit it; CLI uses a real `fichero.models` /
  route-module Pydantic class.
- `cli-untyped` — CLI hits it but returns `Any` (raw dict).
- `cli-missing` — SwiftUI calls it; CLI has no method.
- `swift-only` — view-state / native-only (image rendering, drag-and-drop
  glue, multipart import, SSE stream consumed by SwiftUI's stream parser).

**Priority legend.**

- `high` — needed for engine-quality comparison (workflow status, document
  inspector, KG queries, search, activity).
- `medium` — admin / library management.
- `low` — genuinely view-state.

## Matrix

| Endpoint (METHOD path) | SwiftUI caller | CLI method | Typed response model | Status | Priority |
|---|---|---|---|---|---|
| GET /api/health | (none — engine status checks happen elsewhere) | `health()` | `Any` | cli-untyped | low |
| GET /api/documents | DocumentService (indirect via list/roots/children) | `list_documents()` | `list[Document]` | parity | high |
| GET /api/documents/{doc_id} | `DocumentServiceGenerated.getDocument` | `get_document()` | `Document` | parity | high |
| POST /api/documents | `DocumentServiceGenerated.createDocument`, `createCollection` | — | `Document` | cli-missing | medium |
| PUT /api/documents/{doc_id} | `DocumentServiceGenerated.updateDocument` | — | `Document` | cli-missing | medium |
| DELETE /api/documents/{doc_id} | `DocumentServiceGenerated.deleteDocument` | — | 204 | cli-missing | medium |
| GET /api/documents/{doc_id}/children | `DocumentServiceGenerated.getChildren` | — | `list[Document]` | cli-missing | medium |
| GET /api/documents/{doc_id}/ancestors | `DocumentServiceGenerated.getAncestors` | — | `list[Document]` | cli-missing | medium |
| GET /api/documents/roots | `DocumentServiceGenerated.getRoots` | — | `list[Document]` | cli-missing | medium |
| GET /api/documents/collections | `DocumentServiceGenerated.getCollections` | — | `list[Document]` | cli-missing | medium |
| PUT /api/documents/{doc_id}/move | `DocumentServiceGenerated.moveDocument` | — | `Document` | cli-missing | medium |
| POST /api/documents/reorder | `DocumentServiceGenerated.reorderDocuments` | — | 204/dict | cli-missing | low |
| POST /api/documents/import | `ImportServiceGenerated.importFile` (multipart) | `import_file()` | `Any` (dict) | cli-untyped | medium |
| GET /api/documents/{doc_id}/inspector | (used by inspector views via `APIClient`) | `document_inspector()` | `Any` (should be `DocumentInspectorResponse`) | cli-untyped | **high** |
| GET /api/documents/{doc_id}/knowledge-graph | (filed for #1068; consumed by KG inspector) | — | `DocumentKnowledgeGraphResponse` | cli-missing | **high** |
| GET /api/documents/{doc_id}/related | (related-docs inspector) | — | `list[RelatedDocumentsResponse]` | cli-missing | medium |
| POST /api/ingest/file | `ImportServiceGenerated.importFiles` | — | dict | cli-missing | medium |
| POST /api/ingest/folder | `ImportServiceGenerated.startFolderImport` | — | dict | cli-missing | medium |
| GET /api/ingest/status/{task_id} | `ImportServiceGenerated.getIngestStatus` | — | `IngestTaskStatus` | cli-missing | medium |
| GET /api/artifacts/document/{doc_id} | `ArtifactServiceGenerated.getArtifacts` | `list_artifacts()` | `list[Artifact]` (envelope) | parity | high |
| GET /api/artifacts/{artifact_id} | `ArtifactServiceGenerated.getArtifact` | — | `Artifact` | cli-missing | medium |
| PUT /api/artifacts/{artifact_id} | `ArtifactServiceGenerated.updateArtifact` | — | `Artifact` | cli-missing | medium |
| DELETE /api/artifacts/{artifact_id} | `ArtifactServiceGenerated.deleteArtifact` | — | 204 | cli-missing | low |
| GET /api/artifacts/types | `ArtifactServiceGenerated.getArtifactTypes` | — | `list[str]` | cli-missing | low |
| GET /api/artifacts | `ArtifactServiceGenerated.getAllArtifacts` | — | `list[Artifact]` (envelope) | cli-missing | medium |
| GET /api/workflows | `WorkflowServiceGenerated.listWorkflows` | `list_workflows()` | `list[Workflow]` | parity | high |
| GET /api/workflows/{workflow_id} | `WorkflowServiceGenerated.getWorkflow` | — | `Workflow` | cli-missing | medium |
| POST /api/workflows | `WorkflowServiceGenerated.createWorkflow` | — | `WorkflowResponse` | cli-missing | medium |
| PUT /api/workflows/{workflow_id} | `WorkflowServiceGenerated.updateWorkflow` | — | `WorkflowResponse` | cli-missing | medium |
| PATCH /api/workflows/{workflow_id} | `WorkflowServiceGenerated.updateWorkflowProperties`, `renameWorkflow`, `moveToFolder` | — | `WorkflowResponse` | cli-missing | medium |
| DELETE /api/workflows/{workflow_id} | `WorkflowServiceGenerated.deleteWorkflow` | — | 204 | cli-missing | medium |
| POST /api/workflows/{workflow_id}/duplicate | `WorkflowServiceGenerated.duplicateWorkflow` | — | `WorkflowResponse` | cli-missing | low |
| POST /api/workflows/reorder | `WorkflowServiceGenerated.reorderWorkflows` | — | dict | cli-missing | low |
| GET /api/workflows/{workflow_id}/export | `WorkflowServiceGenerated.exportWorkflow` | — | dict | cli-missing | low |
| POST /api/workflows/import | `WorkflowServiceGenerated.importWorkflow` | — | `WorkflowResponse` | cli-missing | low |
| POST /api/workflows/reinstall-defaults | `WorkflowServiceGenerated.reinstallDefaults` | — | dict | cli-missing | low |
| GET /api/workflows/tools | `WorkflowServiceGenerated.listTools` | — | `list[ToolResponse]` | cli-missing | medium |
| GET /api/workflows/tools/grouped | `WorkflowServiceGenerated.listToolsGrouped` | — | `ToolsGroupedResponse` | cli-missing | medium |
| GET /api/workflows/tools/{tool_name} | `WorkflowServiceGenerated.getTool` | — | `ToolResponse` | cli-missing | low |
| POST /api/workflows/tools/{tool_name}/prompt | `WorkflowServiceGenerated.getToolPrompt` | — | dict | cli-missing | low |
| POST /api/workflows/tools/{tool_name}/create-node | `WorkflowServiceGenerated.createNode` | — | dict | cli-missing | low |
| POST /api/workflow-execution/execute | `WorkflowExecutionService` | `run_workflow()` | `Any` (should be `ExecuteAcceptedResponse`) | cli-untyped | **high** |
| GET /api/workflow-execution/threads/{thread_id}/status | `WorkflowExecutionService.status` | `execution_status()` | `Any` (should be `ExecutionStatusResponse`) | cli-untyped | **high** |
| GET /api/workflow-execution/threads/{thread_id}/history | `ActivityServiceGenerated.getThreadActivities` (via threads) | — | `CheckpointHistoryResponse` | cli-missing | high |
| GET /api/workflow-execution/threads/{thread_id}/run | `ActivityServiceGenerated.getWorkflowRun` | — | `WorkflowRunResponse` | cli-missing | high |
| GET /api/workflow-execution/threads | (thread browser) | — | `ThreadListResponse` | cli-missing | medium |
| DELETE /api/workflow-execution/threads/{thread_id} | (thread cleanup) | — | `ThreadDeletedResponse` | cli-missing | low |
| POST /api/workflow-execution/threads/{thread_id}/resume | `WorkflowExecutionService` (interrupt resume) | — | dict | cli-missing | medium |
| GET /api/workflow-execution/stream/{thread_id} | `WorkflowStreamService` (SSE) | — | text/event-stream | swift-only | low (CLI could subscribe; not view-state per se but stream consumption is non-typed by design — ship a `--follow` flag later) |
| GET /api/workflow-execution/threads/{thread_id}/diagram.png | (visualization image) | — | image/png | swift-only | low |
| GET /api/workflow-execution/workflows/{wf}/visualization | (visualization JSON) | — | `WorkflowVisualizationResponse` | cli-missing | low |
| GET /api/workflow-execution/workflows/{wf}/visualization.png | (visualization image) | — | image/png | swift-only | low |
| GET /api/workflow-execution/workflows/{wf}/code | (codegen view) | — | `WorkflowCodeExportResponse` | cli-missing | low |
| GET /api/workflow-execution/workflows/{wf}/cache/stats | (cache UI) | — | `CacheStatsResponse` | cli-missing | low |
| DELETE /api/workflow-execution/workflows/{wf}/cache | (cache clear) | — | `CacheClearResponse` | cli-missing | low |
| GET /api/workflow-execution/cache/stats | (global cache stats) | — | `CacheStatsResponse` | cli-missing | low |
| DELETE /api/workflow-execution/cache | (global cache clear) | — | `CacheClearResponse` | cli-missing | low |
| GET /api/activity/recent | `ActivityServiceGenerated.getRecentActivities` | `recent_activity()` | `Any` (should be `list[ActivityResponse]`) | cli-untyped | **high** |
| GET /api/activity | `ActivityServiceGenerated.queryActivities` | — | `list[ActivityResponse]` | cli-missing | **high** |
| GET /api/activity/stats | `ActivityServiceGenerated.getActivityStats` | — | `ActivityStatsResponse` | cli-missing | medium |
| GET /api/activity/workflow/{workflow_id} | `ActivityServiceGenerated.getWorkflowActivities` | — | `list[ActivityResponse]` | cli-missing | medium |
| GET /api/activity/batch/{batch_id} | `ActivityServiceGenerated.getBatchActivities` | — | `list[ActivityResponse]` | cli-missing | medium |
| GET /api/activity/feed | (Activity feed view) | — | `ActivityFeedResponse` | cli-missing | medium |
| GET /api/activity/trends | (Activity trends view) | — | `ActivityTrendsResponse` | cli-missing | low |
| GET /api/activity/top | (top entities) | — | `TopEntitiesResponse` | cli-missing | low |
| GET /api/activity/entity-types | (entity-types facet) | — | `EntityTypesResponse` | cli-missing | low |
| GET /api/activity/metrics/summary | (summary widget) | — | `ActivityMetricsSummary` | cli-missing | low |
| GET /api/activity/stream | (live tail) | — | text/event-stream | swift-only | low |
| DELETE /api/activity/cleanup | `ActivityServiceGenerated.cleanupOldActivities` | — | `CleanupResponse` | cli-missing | low |
| POST /api/search | `SearchServiceGenerated.search` (compat path: `/api/search/`) | `search()` | `Any` (should be `SearchResponse`) | cli-untyped | **high** |
| GET /api/search/stats | `SearchServiceGenerated.stats` | — | dict | cli-missing | medium |
| GET /api/search/keywords | `SearchServiceGenerated.keywordCloud` | — | dict | cli-missing | low |
| POST /api/search/reindex | `SearchServiceGenerated.reindexAll` | — | `ReindexStartedResponse` | cli-missing | medium |
| POST /api/search/embed/{doc_id} | `SearchServiceGenerated.embedDocument` | — | `EmbedDocumentResponse` | cli-missing | medium |
| POST /api/search/saved | `SavedSearchServiceGenerated.saveSearch` / `SearchServiceGenerated.saveSearch` | — | `SavedSearchResponse` | cli-missing | medium |
| GET /api/search/saved | `SavedSearchServiceGenerated.listSavedSearches` | — | `list[SavedSearchResponse]` | cli-missing | medium |
| PUT /api/search/saved/{id} | `SavedSearchServiceGenerated.updateSavedSearch` | — | `SavedSearchResponse` | cli-missing | medium |
| POST /api/search/saved/{id}/duplicate | `SavedSearchServiceGenerated.duplicateSavedSearch` | — | `SavedSearchResponse` | cli-missing | low |
| DELETE /api/search/saved/{id} | `SavedSearchServiceGenerated.deleteSavedSearch` | — | `DeletedResponse` | cli-missing | low |
| POST /api/search/saved/reorder | `SavedSearchServiceGenerated.reorderSavedSearches` | — | `ReorderResponse` | cli-missing | low |
| GET /api/search/views | (search results table/map/grid) | — | `SearchViewsResponse` | cli-missing | low |
| GET /api/search/views/{table\|map\|grid} | (view-specific renderers) | — | `Table/Map/GridViewData` | cli-missing | low |
| GET /api/entities | `ArtifactServiceGenerated.listEntities` | `list_entities()` | `Any` (should be `list[KnowledgeEntity]`) | cli-untyped | **high** |
| GET /api/entities/{id} | `ArtifactServiceGenerated.getEntity` | — | `KnowledgeEntity` | cli-missing | high |
| POST /api/entities | `ArtifactServiceGenerated.upsertEntity` | — | `KnowledgeEntity` | cli-missing | medium |
| PATCH /api/entities/{id} | `ArtifactServiceGenerated.patchEntity` | — | `KnowledgeEntity` | cli-missing | medium |
| DELETE /api/entities/{id} | `ArtifactServiceGenerated.deleteEntity` | — | 204 | cli-missing | low |
| GET /api/claims | `ArtifactServiceGenerated.listClaims` | `list_claims()` | `Any` (should be `list[KnowledgeClaim]`) | cli-untyped | **high** |
| PATCH /api/claims/{id} | `ArtifactServiceGenerated.patchClaim` | — | `KnowledgeClaim` | cli-missing | medium |
| DELETE /api/claims/{id} | `ArtifactServiceGenerated.deleteClaim` | — | 204 | cli-missing | low |
| POST /api/claims/{id}/links | `ArtifactServiceGenerated.createClaimLink` | — | dict | cli-missing | medium |
| GET /api/kg/search | (KG global search) | `kg_search()` | `Any` (should be `KGSearchResponse`) | cli-untyped | **high** |
| GET /api/kg-claim-analysis/{id}/contradictions | `ArtifactServiceGenerated.contradictions` | — | dict | cli-missing | medium |
| GET /api/kg-claim-analysis/{id}/evidence-chain | `ArtifactServiceGenerated.evidenceChain` | — | dict | cli-missing | medium |
| GET /api/kg-claim-search/{id}/similar | `ArtifactServiceGenerated.findSimilarClaims` | — | dict | cli-missing | medium |
| POST /api/kg-claim-search/embed | `ArtifactServiceGenerated.embedClaims` | — | dict | cli-missing | low |
| POST /api/kg-entity-curation/merge | `ArtifactServiceGenerated.mergeEntities` | — | dict | cli-missing | low |
| POST /api/kg-entity-curation/split | `ArtifactServiceGenerated.splitEntity` | — | dict | cli-missing | low |
| POST /api/kg-entity-curation/semantic-embed | `ArtifactServiceGenerated.embedEntities` | — | dict | cli-missing | low |
| GET /api/kg-entity-curation/audit | `ArtifactServiceGenerated.listEntityAudits` | — | dict | cli-missing | low |
| POST /api/kg-predictions/heuristic | `ArtifactServiceGenerated.generateHeuristicPredictions` | — | dict | cli-missing | low |
| GET /api/kg-graph/neighborhood/{entity_id} | `ArtifactServiceGenerated.fetchNeighborhood` | — | `NeighborhoodResponse` | cli-missing | high |
| GET /api/kg-graph/centrality | (KG analysis views) | — | `list[CentralityRow]` | cli-missing | medium |
| GET /api/kg-graph/page-rank | (KG analysis views) | — | `list[PageRankRow]` | cli-missing | medium |
| GET /api/kg-graph/communities | (KG analysis views) | — | `list[CommunityRow]` | cli-missing | medium |
| GET /api/kg-graph/similar-entities | (KG analysis views) | — | `list[SimilarEntityRow]` | cli-missing | medium |
| GET /api/kg-graph/components | (KG analysis views) | — | `list[ComponentRow]` | cli-missing | low |
| GET /api/kg-graph/triangles | (KG analysis views) | — | `TriangleRow` | cli-missing | low |
| GET /api/kg-graph/clustering | (KG analysis views) | — | `list[ClusteringRow]` | cli-missing | low |
| GET /api/kg-graph/co-occurrence | (KG analysis views) | — | `list[CooccurrenceNeighbour]` | cli-missing | low |
| GET /api/kg-graph/metrics | (KG analysis views) | — | `GraphMetricsResponse` | cli-missing | low |
| GET /api/kg-graph/traverse | (KG traversal view) | — | `TraverseResponse` | cli-missing | low |
| GET /api/kg-graph/path | (KG path view) | — | `PathResponse` | cli-missing | low |
| GET /api/citations-graph/document/{id}/inbound | `ArtifactServiceGenerated.inboundCitations` | — | dict | cli-missing | medium |
| GET /api/citations-graph/document/{id}/outbound | `ArtifactServiceGenerated.outboundCitations` | — | dict | cli-missing | medium |
| GET /api/bibliography/document/{id} | `ArtifactServiceGenerated.bibliographyMetadata` | — | dict | cli-missing | medium |
| PATCH /api/bibliography/document/{id} | `ArtifactServiceGenerated.patchBibliographyMetadata` | — | dict | cli-missing | medium |
| POST /api/bibliography/document/{id}/extract | `ArtifactServiceGenerated.runBibliographyExtractor` | — | dict | cli-missing | medium |
| POST /api/chat | `ChatServiceGenerated.chat` | — | `ChatResponse` | cli-missing | medium |
| POST /api/chat/extract-text | `ChatServiceGenerated.extractText` | — | `ExtractTextResponse` | cli-missing | medium |
| GET /api/chat/providers | `ChatServiceGenerated.listProviders` | — | `list[ProviderInfo]` | cli-missing | low |
| GET /api/chat/conversations | `ConversationServiceGenerated.listConversations` | — | dict envelope | cli-missing | medium |
| GET /api/chat/conversations/{id} | `ConversationServiceGenerated.getConversation` | — | `ConversationHistory` | cli-missing | medium |
| PUT /api/chat/conversations/{id} | `ConversationServiceGenerated.updateConversation`, `moveToFolder`, `renameConversation` | — | dict | cli-missing | medium |
| DELETE /api/chat/conversations/{id} | `ConversationServiceGenerated.deleteConversation` | — | 204 | cli-missing | low |
| POST /api/chat/conversations/{id}/duplicate | `ConversationServiceGenerated.duplicateConversation` | — | dict | cli-missing | low |
| POST /api/chat/conversations/reorder | `ConversationServiceGenerated.reorderConversations` | — | dict | cli-missing | low |
| GET /api/batches | `BatchServiceGenerated.listBatches` | — | `list[BatchResponse]` | cli-missing | medium |
| POST /api/batches | `BatchServiceGenerated.createBatch` | — | `BatchResponse` | cli-missing | medium |
| GET /api/batches/{id} | `BatchServiceGenerated.getBatch` | — | `BatchResponse` | cli-missing | medium |
| GET /api/batches/{id}/progress | `BatchServiceGenerated.getBatchProgress` | — | `BatchProgressResponse` | cli-missing | medium |
| DELETE /api/batches/{id} | `BatchServiceGenerated.deleteBatch` | — | 204 | cli-missing | low |
| POST /api/batches/{id}/{pause\|resume\|cancel\|retry} | `BatchServiceGenerated.*Batch` | — | `BatchResponse`/204 | cli-missing | low |
| GET /api/providers | `ProviderServiceGenerated.listProviders` | — | `list[ProviderResponse]` | cli-missing | medium |
| POST /api/providers | `ProviderServiceGenerated.createProvider` | — | `ProviderResponse` | cli-missing | medium |
| GET/PATCH/DELETE /api/providers/{id} | Provider CRUD | — | `ProviderResponse` | cli-missing | medium |
| GET /api/providers/catalog | `ProviderServiceGenerated.listCatalog` | — | `list[ProviderCatalogResponse]` | cli-missing | low |
| GET /api/providers/catalog/{type} | `ProviderServiceGenerated.getCatalogEntry` | — | `ProviderCatalogResponse` | cli-missing | low |
| {GET,POST,DELETE} /api/providers/{type}/api-key{,/status} | API key mgmt | — | `APIKeyStatusResponse` | cli-missing | medium |
| GET /api/providers/models/{type} | `ProviderServiceGenerated.listAvailableModels` | — | `list[ModelResponse]` | cli-missing | low |
| GET/POST /api/providers/{id}/models | provider model mgmt | — | `list[UserModelResponse]` | cli-missing | low |
| DELETE /api/providers/{pid}/models/{mid} | `removeModel` | — | 204 | cli-missing | low |
| POST /api/providers/{type}/test | `testConnection` | — | `ConnectionTestResponse` | cli-missing | low |
| GET/POST/PATCH/DELETE /api/providers/refs[/...] | provider-ref CRUD | — | `ProviderRefResponse` | cli-missing | low |
| GET /api/models/huggingface/tasks | `ModelServiceGenerated.listHuggingFaceTasks` | — | `list[HFTaskCategory]` | cli-missing | low |
| GET /api/models/huggingface | `ModelServiceGenerated.searchHuggingFaceModels` | — | `ModelSearchResponse` | cli-missing | low |
| GET /api/models/huggingface/{id} | `ModelServiceGenerated.getHuggingFaceModel` | — | `HFModelInfo` | cli-missing | low |
| GET /api/storage/stats | `StorageServiceGenerated.getStats` | — | dict | cli-missing | medium |
| GET /api/storage/.../thumbnail|display|source | `StorageServiceGenerated.getThumbnail/Display/sourceURL/downloadSourceFile` | — | image/binary | swift-only | low |
| GET /api/automation/schedules, /triggers (+CRUD) | `AutomationServiceGenerated.*` | — | dict | cli-missing | medium |

## Summary stats

- **Distinct endpoints catalogued**: ~115
- **`parity` (typed both sides)**: 4 (`GET /api/documents`, `GET /api/documents/{id}`, `GET /api/workflows`, `GET /api/artifacts/document/{id}`)
- **`cli-untyped`**: 8 (`health`, `import_file`, `document_inspector`, `run_workflow`, `execution_status`, `recent_activity`, `search`, `list_entities`, `list_claims`, `kg_search`) — note 9 if you count `import_file`; 7 of these are the marquee high-priority ones STATE.md called out
- **`cli-missing`**: ~95
- **`swift-only`** (image/PNG/SSE — won't be typed): ~6
- **Effective parity rate**: ~3.5% typed both sides; ~10% even reachable from CLI

## Recommended typing order

Drives the "engine-quality comparison" use case fastest — every step lets the
CLI surface (or refute) a class of bugs Daniel keeps hitting in the SwiftUI
inspector / activity / KG panes.

### Wave 1 — type the methods CLI already exposes (no new commands)

Each item here is a one-line edit in `cli/client.py`: replace the `Any` with
the existing route-module Pydantic class, and import it.

1. **`document_inspector(doc_id)` → `DocumentInspectorResponse`**
   (`fichero/api/routes/document_inspector.py:37`). Already used by SwiftUI's
   inspector (#1068 cluster). Untyped today — typing it makes shape drift in
   the inspector aggregate loud at the CLI boundary.
2. **`recent_activity()` → `list[ActivityResponse]`**
   (`fichero/api/routes/activity.py:50`). Re-exported model.
3. **`run_workflow()` → `ExecuteAcceptedResponse`** + **`execution_status()`
   → `ExecutionStatusResponse`** (`workflow_execution/schemas.py:28,58`).
   Workflow status is the #1 thing engine-quality work depends on.
4. **`search()` → `SearchResponse`** (`fichero/api/routes/search.py:331`).
5. **`kg_search()` → `KGSearchResponse`** (`kg_search.py:43`).
6. **`list_entities()` → `list[KnowledgeEntity]`**, **`list_claims()` →
   `list[KnowledgeClaim]`** (already declared in `entities.py` /
   `claims.py`). These are the KG primitives every drill-down view depends on.

### Wave 2 — add the missing methods STATE.md called out

7. **`document_knowledge_graph(doc_id)` → `DocumentKnowledgeGraphResponse`**
   — net-new method for the #1068 endpoint
   (`document_inspector.py:205`). Pairs with the inspector typing above.
8. **`thread_history(thread_id)` → `CheckpointHistoryResponse`** and
   **`workflow_run(thread_id)` → `WorkflowRunResponse`**
   (`workflow_execution/threads.py:44,58`). Lets the CLI replay what the
   activity pane is showing — needed to debug workflow event drift.
9. **`activity(...)` → `list[ActivityResponse]`** (filtered) and
   **`activity_stats()` → `ActivityStatsResponse`**.
10. **`entity(id)` / `claim(id)` getters → `KnowledgeEntity` /
    `KnowledgeClaim`**. Singletons unlock per-row drill-down parity.

### Wave 3 — graph analysis surface (high engine value, low CLI footprint)

11. `kg_neighborhood(entity_id)` → `NeighborhoodResponse` (the
    SwiftUI graph view's data source).
12. `kg_centrality / page_rank / communities / similar_entities` — all
    already typed on the backend; one CLI method each, ~3 lines apiece.

### Wave 4 — admin / library mgmt (commit-and-forget)

13. Document CRUD (create / update / move / delete / children / ancestors /
    roots / collections), workflow CRUD, artifact CRUD, batch CRUD, provider
    CRUD. Lower-priority because Daniel uses the GUI for these and they're
    single-shape `Document` / `Workflow` / `Artifact` round-trips.

### Out of scope (deliberately)

- SSE streams (`/workflow-execution/stream/{id}`,
  `/activity/stream`) — typing-by-shape doesn't apply; they're a sequence of
  `SSEEvent`s and SwiftUI has its own parser. A `--follow` CLI flag would
  consume them line-by-line; ship after Wave 1.
- PNG / image endpoints (thumbnails, display, diagrams) — `swift-only` by
  design; the CLI has no use for raw image bytes.
- Multipart upload (`POST /api/documents/import`) — typed input shape doesn't
  buy much; the response is already small.

## Caveats

- The matrix is built from the operationIds the SwiftUI client invokes
  (decoded from `client.api.<verbCamelCasePath>` calls). A handful of
  endpoints declared by the backend (e.g. `/api/notes`, `/api/sources`,
  `/api/projects`, MCP tools, research agents, mind palace, hermeneutics,
  IIIF, classifications) are not currently called from any
  `*Generated.swift` file — they're omitted from this audit because neither
  surface uses them yet. Re-run this audit if any of those wire up in 0.0.3.
- "Typed response model" lists the **declared** `response_model=` on the
  backend route. A handful of routes (e.g. several KG endpoints, chat,
  bibliography) use `dict` returns even though a `BaseModel` exists for the
  shape — those would need a backend-side `response_model=` first before the
  CLI can import a real type. They are listed as `dict` here to flag that.
