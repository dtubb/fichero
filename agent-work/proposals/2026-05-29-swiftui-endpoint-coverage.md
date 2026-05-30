# SwiftUI Endpoint Coverage Audit

Date: 2026-05-29  
Scope: routers registered from `fichero-engine/src/fichero/api/main.py` on `origin/0.0.2`; Swift wrappers under `fichero/fichero/Services/`; view use checked with `rg` across `fichero/fichero/Views/` and `fichero/fichero/Models/`.

## Covered Endpoints

These backend surfaces have Swift wrapper methods and at least one current SwiftUI caller.

| Backend surface | Swift wrapper | View/model callers |
| --- | --- | --- |
| `/api/documents/*` | `DocumentServiceGenerated`, `DocumentStore`, `APIEndpoints.Documents` | Library/sidebar/grid, inspector, preview/source navigation, chat document picker |
| `/api/artifacts/*` | `ArtifactServiceGenerated` | `DocumentInspectorArtifactsTab`, artifact refresh/list surfaces |
| `/api/entities`, `/api/entities/{id}`, `/api/entities/claim-counts`, `/api/entities/{id}/inspector` | `ArtifactServiceGenerated` entity methods | `OntologyBrowser`, `EntityDetailView`, `DocumentInspectorArtifactsTab` |
| `/api/claims`, `/api/claims/{id}` | `ArtifactServiceGenerated` claim methods | KG inspector, ontology details, claim cards |
| `/api/documents/{id}/knowledge-graph` | `ArtifactServiceGenerated.documentKnowledgeGraph` | Inspector KG tab, document KG surface |
| `/api/kg/claim-analysis/*`, `/api/kg/claim-search/*`, `/api/kg/entity-curation/*`, `/api/kg/predictions/heuristic`, `/api/kg/graph/neighborhood/{id}` | `ArtifactServiceGenerated` KG methods | Ontology browser tools, entity detail related-claims panels, WebKit/native KG focus surfaces |
| `/api/citations/graph/document/{id}/inbound`, `/api/citations/graph/document/{id}/outbound` | `ArtifactServiceGenerated` citation graph methods | citation graph affordances in KG/document surfaces |
| `/api/bibliography/document/{id}`, `/api/bibliography/document/{id}/extract` | `ArtifactServiceGenerated` bibliography methods | bibliography metadata/extraction affordances |
| `/api/workflows/*` | `WorkflowServiceGenerated`, `WorkflowStore` | Workflow sidebar/editor/run controls |
| `/api/workflow-execution/*` | `ActivityServiceGenerated`, `WorkflowExecutionObserver` | Activity view, live workflow execution status |
| `/api/activity`, `/api/activity/recent`, `/api/activity/stats`, `/api/activity/workflow/{id}`, `/api/activity/batch/{id}`, `/api/activity/cleanup` | `ActivityServiceGenerated` | Activity browser/detail panes |
| `/api/search`, `/api/search/stats`, `/api/search/reindex`, `/api/search/embed/{id}`, `/api/search/saved/*` | `SearchServiceGenerated`, `SavedSearchServiceGenerated` | Search view, saved-search sidebar |
| `/api/chat`, `/api/chat/conversations/*`, `/api/chat/providers`, `/api/chat/extract-text` | `ChatServiceGenerated`, `ConversationServiceGenerated` | Chat view, chat inspector |
| `/api/providers/*`, `/api/providers/models/{type}`, `/api/providers/{id}/models`, `/api/providers/refs/*`, `/api/providers/{type}/api-key*`, `/api/providers/{type}/test` | `ProviderServiceGenerated` | Settings/providers UI |
| `/api/models/huggingface/*` | `ModelServiceGenerated` | Model search/settings surfaces |
| `/api/batches/*` | `BatchServiceGenerated` | Batch/activity surfaces |
| `/api/images/{id}/*` | `ImageEditingServiceGenerated` | Image editing preview/operation UI |
| `/api/mind-palace/*` | `MindPalaceService` | Mind Palace room/node/scene surfaces |
| `/api/research/*` | `ResearchService` | Research browser and researcher tools |
| `/api/storage/thumbnail/{id}`, `/api/storage/display/{id}`, `/api/storage/source/{id}`, `/api/storage/stats` | `StorageServiceGenerated` | thumbnails, previews, storage stats |
| `/view/document/{id}` | `DocumentKGPaneRoute` | WebKit document KG/transcript surface |

## Wrapped But Unused

These have Swift service coverage but no clear live view caller in the current tree. They are useful for upcoming or hidden surfaces, but should not be treated as complete UI coverage.

| Backend surface | Swift wrapper | Notes |
| --- | --- | --- |
| `/api/folders/{folder_id}/views` | `FolderService.availableViews` | Added in this pass for workspace/folder lenses. No live Swift view consumes it yet. |
| `/api/providers/apple-intelligence/probe` | generated OpenAPI operation only | Useful diagnostics; no Settings button calls it directly. |
| `/api/activity/feed`, `/api/activity/trends`, `/api/activity/top`, `/api/activity/entity-types`, `/api/activity/metrics/summary` | generated OpenAPI operations only | Analytics/dashboard endpoints; Activity view currently uses list/recent/stats/detail paths. |
| `/api/claims/{id}/links`, `/api/claim-links/*`, `/api/claims/{id}/related` | `ArtifactServiceGenerated` link helpers | KG link editing is partly wired; not all link CRUD paths have visible controls. |
| `/api/bibliography/import`, `/api/bibliography/export.bib`, `/api/bibliography/resolve` | generated OpenAPI operations only | Bibliography import/export UI is not visible in SwiftUI yet. |
| `/api/model-comparison/*` | generated OpenAPI operations plus comparison models | Comparison feature shell exists, but not every estimate/preset/tool comparison path has a visible command. |

## Uncovered Endpoints

These registered routes have no dedicated Swift service wrapper in `fichero/fichero/Services/`.

| Backend surface | User impact / recommendation |
| --- | --- |
| `/api/annotations/*` | No annotation service wrapper for backend annotations. Add before shipping annotation editing/crop/promote-to-claim UI. |
| `/api/notes/*` and `/api/sources/*` | Backend note/source CRUD exists. Swift research notes use `/api/research/*` instead; keep uncovered unless the generic note/source model becomes user-facing. |
| `/api/projects/*` | Generic projects/inclusion endpoints are distinct from the Research UI. Add wrappers only if project membership becomes visible outside Research. |
| `/api/classifications/*`, `/api/registries/*`, `/api/libraries/{lib}/entity-types/*` | Vocabulary/customization endpoints. Important for curation settings, but no current Swift settings pane consumes them. |
| `/api/export/*` | Export-to-Markdown/Word backend exists with no Swift command wrapper. Add before exposing export menu items. |
| `/api/ingest/file`, `/api/ingest/folder`, `/api/ingest/xlsx`, `/api/ingest/status/{id}` | Swift import uses document/import services rather than this ingest router. Avoid duplicate UI paths unless import is consolidated. |
| `/api/library`, `/api/registry/*` | CLI/library bootstrap and known-library registry endpoints. Swift library management currently uses document/package flows. |
| `/api/mcp/tools/*`, `/api/mcp-servers/*` | MCP management endpoints are backend-ready; Swift has no MCP settings UI yet. |
| `/api/migrations/*` | Operational/admin endpoints; should stay out of the main UI unless an advanced diagnostics pane is added. |
| `/api/multilingual/*` | Language normalization/search endpoints. No Swift multilingual curation/search UI yet. |
| `/api/actions/*` | Action catalog/custom action endpoints. No Swift action library UI yet. |
| `/api/integrations/*` | DEVONthink/Bookends/Tinderbox integrations exist server-side; no Swift integration browser/settings wrapper yet. |
| `/api/local-models/*` | Local model download/disk endpoints. Settings has provider/model surfaces but no local-model manager wrapper. |
| `/api/tasks/*` | Background task monitor endpoints. Activity covers workflow runs but not generic task jobs. |
| `/api/schedules/*`, `/api/triggers/*` | Automation endpoints are registered; Swift automation UI currently lacks dedicated generated services in `Services/`. |
| `/api/chains/*` | Workflow chains model/UI exists, but there is no generated `ChainService` wrapper. Add before enabling chain CRUD/execution controls. |
| `/api/kg/reset`, `/api/kg/rebuild`, `/api/kg/triangulation/*`, `/api/kg/render/paragraph`, `/api/kg/review/*`, `/api/kg/mutations/*`, `/api/kg/pykeen/*`, `/api/kg/sparql`, `/api/kg/inclusion`, `/api/kg/graph/*` except neighborhood | Advanced KG analytics/rebuild/review endpoints are mostly backend-only. Add wrappers incrementally as each curation/analytics tool gets a Swift surface. |
| `/api/hermeneutics/*` and `/api/kg/interpretations/*` | Interpretation layer is backend-ready; no Swift hermeneutics UI wrapper yet. |
| `/api/iiif/*` | IIIF image/manifest endpoints are Web/interop surfaces; no native Swift caller. |
| `/api/policies/orchestration/*`, `/api/agents/write/*` | Agent/orchestration policy endpoints are backend/admin surfaces without Swift wrappers. |
| `/api/search/views*`, `/api/search/explain*`, `/api/search/modes`, `/api/search/metrics` | Search explanation/view endpoints are backend-ready. Existing Search UI covers core search and saved searches only. |
| `/api/citation-usages` and `/api/citations/graph` collection CRUD | Citation graph read paths for document inbound/outbound are wrapped; full citation graph CRUD/list remains uncovered. |

## Changes Made

- Added `FolderService` with typed `FolderViewInfo` and `FolderViewsResponse`.
- Wrapped `GET /api/folders/{folder_id}/views` as `availableViews(folderId:)` because folder/workspace lenses are a current user feature surface.

## Follow-Up

Highest-value wrapper gaps for SwiftUI parity are automation (`schedules`, `triggers`), workflow chains (`chains`), export (`export`), annotations (`annotations`), and local model management (`local-models`). The rest are backend/admin, integration, or future advanced KG surfaces and should get wrappers only with a concrete UI entry point.
