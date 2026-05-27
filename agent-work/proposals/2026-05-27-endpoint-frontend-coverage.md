# SwiftUI ↔ Backend Endpoint Coverage Audit

Date: 2026-05-27  
Scope: read-only audit of `fichero-engine/tests/contracts/openapi.json`, `fichero-engine/src/fichero/api/routes/`, and SwiftUI service/view usage under `fichero/fichero/`.

## Summary

The OpenAPI contract currently exposes **430 path templates / 556 operations**. The backend route tiering is split in `fichero-engine/src/fichero/api/main.py`:

- **Release tier:** documents, search, KG, workflows, chains, chat, model comparison, export, annotations, image editing, citations, bibliography, providers, settings, storage, activity, batches, migrations, tasks, MCP tools.
- **Dev tier:** search explain, mind palace, research agents, IIIF, actions, integrations, local models, MCP servers, orchestration/agent-write policy, schedules, triggers.

Important gating detail: backend default is `FICHERO_FEATURE_TIER=release` when the env var is absent, but `EmbeddedBackendService` sets `FICHERO_FEATURE_TIER` to `dev` by default for the Swift-launched backend. That means several dev-tier routes are reachable in the app process, but Swift feature flags still hide their UI by default.

This audit treats an endpoint as **frontend enabled** only when a Swift service/view calls it in an actual reachable surface. Generated client coverage alone is not counted as enabled.

## Priority Enable List

1. **Chat + model comparison:** backend is release-tier and Swift views/services exist, but `FeatureManager.resetToV001()` keeps `chat` off and there is no obvious default navigation path to comparisons. Enable chat, expose `ModelComparisonView`, and wire the already-present compare/history/cost/vision/tool APIs.
2. **Integrations:** backend routes and `IntegrationsView`/`IntegrationsService` exist for DEVONthink, Bookends, and Tinderbox, but the backend router is dev-tier and the Swift `integrations` flag defaults off. This is a strong "turn it on and test" candidate if #1151 agrees it is not agent/thinking-risky.
3. **MCP server management:** backend routes and full Swift screens exist, but they are dev-tier plus `mcp` flag off. Enable only after confirming #1151 policy, because this touches external tool execution.
4. **Automation schedules/triggers:** backend routes and Swift editor/detail views exist, but routes are dev-tier and `automation` defaults off. This is likely enable-able for workflow users once basic schedule/trigger flows are smoke-tested.
5. **Local models settings:** backend routes and settings UI exist, but routes are dev-tier and the Models settings tab defaults off. Enable if local Whisper/embedding management is in 0.0.2 scope.
6. **KG advanced controls already partly wired:** claim search/embed, entity semantic embed, graph neighborhood, predictions, contradictions/evidence chain, entity merge/split/audit, and citation graph are called from Swift. Keep them visible, then bugfix. Remaining KG surfaces below are backend-only and need explicit product decisions.

## Area Tables

### System / Health

| Endpoint family | Backend status | Frontend status | Recommendation |
|---|---|---|---|
| `GET /api/health` | Release; used by backend connection checks | Enabled | Keep. |
| `GET /api/stats` | Release | Backend-only | Dead/uncertain. Either expose in Backend settings/diagnostics or remove from shipped contract. |

### Documents / Library / Folders / Import / Storage

| Endpoint family | Backend status | Frontend status | Recommendation |
|---|---|---|---|
| `/api/documents`, `/roots`, `/collections`, `/{doc_id}`, `/children`, `/ancestors`, `/parent`, `/move`, `/reorder`, `/cleanup-orphans` | Release; `documents.py` | Enabled via `DocumentStore`, `DocumentServiceGenerated`, sidebar, library grid, inspector | Keep. |
| `/api/documents/import`, `/api/ingest/file`, `/api/ingest/folder`, `/api/ingest/status/{task_id}`, `/api/ingest/xlsx` | Release; `ingest.py` | File/folder import enabled; XLSX has backend/CLI path but no clear SwiftUI import affordance | Enable XLSX import in the frontend if the #1237 backend is considered working. |
| `/api/documents/pdfs/backfill-pages` | Release | Backend-only | Backend maintenance action; expose as a repair action only if users need it. |
| `/api/folders/{entity_type}/folders`, `/move` | Release | Mostly backend-only; Swift uses document collections more than generic entity folders | Dead/uncertain. Clarify whether this belongs to sidebar foldering or legacy generalized folders. |
| `/api/storage/thumbnail`, `/display`, `/source` | Release | Enabled via `StorageServiceGenerated`, `LibraryImageView`, quick look | Keep. |
| `/api/storage/stats`, `/debug`, `/snapshots/*` | Release | Backend-only | Enable `stats` in Backend settings; keep `debug`/snapshots as maintenance-only unless Daniel wants visible library backups. |
| `/view/document/{doc_id}` | Release | Enabled via document web/KG panes where needed | Keep. |
| `/api/library`, `/api/registry/*`, `/api/libraries/{lib}/entity-types/*` | Release; CLI/library management support | Mostly backend/CLI-only | Should be enabled only where Swift needs multi-library registry/entity-type editing; otherwise leave as backend infrastructure. |
| `/api/migrations/*` | Release | Backend-only | Intentionally backend/admin. Do not surface in normal UI. |

### Search

| Endpoint family | Backend status | Frontend status | Recommendation |
|---|---|---|---|
| `POST /api/search`, `/stats`, `/reindex`, `/embed/{doc_id}`, `/keywords` | Release | Search and stats/reindex are enabled; per-document embed and keywords are only lightly/unclearly surfaced | Keep search enabled. Consider surfacing keyword cloud and per-document embed repair in advanced diagnostics. |
| `/api/search/saved/*` | Release | Enabled via `SavedSearchServiceGenerated`, sidebar, Search view | Keep. |
| `/api/search/views/{table,map,grid}` | Release | Backend-only; Swift has local result modes | Dead/uncertain. If backend view shaping works, switch Swift result modes to display backend-provided views per #1072. |
| `/api/search/explain*`, `/api/search/modes`, `/metrics` | Dev tier for explain; release for modes/metrics | Backend-only | Good enable candidate for a "Why these results?" search inspector, but keep gated until the UX is defined. |

### Knowledge Graph / Claims / Entities / Artifacts

| Endpoint family | Backend status | Frontend status | Recommendation |
|---|---|---|---|
| `/api/entities`, `/api/entities/{id}`, `/documents`, `/claim-counts`, `/digest`, `/aliases`, `/resolve`, `/top` | Release | Enabled in Ontology browser, entity detail, digest, document inspector | Keep. |
| `/api/claims`, `/api/claims/{id}`, `/transition`, `/queues/*`, `/claim-links/*`, `/claims/{id}/related` | Release | Claims list/detail enabled; curation queues/transitions only partly visible | Enable review queues as a visible curation workflow if Daniel wants "get it all up" for KG. |
| `/api/artifacts/*` | Release | Enabled in inspector artifacts and artifacts browser | Keep. |
| `/api/kg/graph/*` | Release | Neighborhood is enabled; centrality/cooccurrence/metrics/traverse/path/pagerank/communities/components/triangles/clustering are backend-only | Enable next in KG visualization panels if the goal is full graph exploration. |
| `/api/kg/triangulation*` | Release | Backend-only | Enable as an entity detail tool if it produces stable, useful claims. |
| `/api/kg/render/paragraph` | Release | Backend-only | Enable as a claim/entity "draft paragraph" action, or leave to workflows. |
| `/api/kg/pykeen/*` | Release | Backend-only | Intentionally uncertain. This is ML training/prediction infrastructure; keep out of default UI until a human decides. |
| `/api/kg/predictions*` | Release | Heuristic predictions called from Ontology tools; apply flow unclear | Partly enabled. Finish the prediction review/apply UI if backend output is stable. |
| `/api/kg/review/*` | Release | Backend-only | Enable if entity-pair review is part of 0.0.2 KG cleanup; otherwise keep as backlog. |
| `/api/kg/mutations/*` | Release | Backend-only | Enable undo/audit affordance in KG tools; this is useful once merge/split is visible. |
| `/api/kg/claim-search*`, `/api/kg/claim-analysis/*` | Release | Enabled in document inspector / claim summary details | Keep. |
| `/api/kg/entity-curation/*` | Release | Merge/split/audit enabled in Ontology browser | Keep. |
| `/api/kg/sparql`, `/api/kg/inclusion` | Release | Backend-only | Advanced/uncertain. SPARQL can stay hidden; inclusion may belong in project/library scope if it is working. |
| `/api/hermeneutics/*`, `/api/kg/interpretations/*` | Release | Backend-only | Should be enabled if #1124/hermeneutics is in scope; otherwise classify as uncertain rather than dead. |
| `/api/multilingual/*` | Release | Backend-only | Enable if multilingual entity normalization/search is reliable; otherwise keep hidden. |

### Citations / References / Bibliography

| Endpoint family | Backend status | Frontend status | Recommendation |
|---|---|---|---|
| `/api/citations/graph*` | Release | Inbound/outbound document citation graph enabled in Document Inspector; graph CRUD mostly backend-only | Keep existing read UI; enable create/edit/delete only if users need manual citation curation. |
| `/api/citations/document/{document_id}`, `.bib`, `/api/citations/export` | Release | Backend-only | Enable export/download from document and library menus. |
| `/api/bibliography/document/{document_id}`, `/extract` | Release | Service wrappers exist; no clear active UI usage | Enable in Document Inspector metadata tab if extraction works. |
| `/api/bibliography/import`, `/export.bib`, `/resolve` | Release | Backend-only | Enable import/export in library/document menus if bibliography workflows are in 0.0.2 scope. |
| `/api/references*`, `/api/sources*` | Release | Backend-only | Dead/uncertain. Decide whether these are superseded by citations/bibliography or should become a references browser. |

### Notes / Annotations / Image Editing

| Endpoint family | Backend status | Frontend status | Recommendation |
|---|---|---|---|
| `/api/annotations`, `/{id}`, `/crop`, `/promote-to-claim` | Release | List/create/delete/update enabled in inspector and image editor; crop/promote-to-claim not clearly surfaced | Keep annotations. Enable crop/promote actions after annotations UI smoke test. |
| `/api/images/{document_id}/edits`, `/preview`, `/operations/{crop,rotate,enhance,remove-background,segment}` | Release | Enabled via `ImageEditorModel` and image editor UI | Keep and test. |
| `/api/notes`, `/links`, `/backlinks`, `/forward-links` | Release | Backend-only except annotation notes are separate | Should be enabled: this is a high-value gap for per-document/project notes and backlinks. |
| `/api/projects`, `/include`, `/items`, `/membership` | Release | Backend-only | Should be enabled if projects are intended to group documents/notes/research outputs. |

### Workflows / Chains / Batches / Activity

| Endpoint family | Backend status | Frontend status | Recommendation |
|---|---|---|---|
| `/api/workflows`, `/tools`, `/tools/grouped`, `/create-node`, `/prompt`, import/export/reorder/duplicate | Release | Enabled; import/export and advanced editor affordances are feature-flagged | Keep workflows on. Consider enabling import/export by default if #1151 approves. |
| `/api/workflow-execution/*` | Release | Enabled via `WorkflowStreamService`, `WorkflowExecutionService`, workflow detail/run UI | Keep. |
| `/api/chains/*` | Release; promoted by #1151 | Enabled if `workflow_chains` flag is on; default reset enables chains | Keep. |
| `/api/batches/*` | Release | Generated service exists; UI surface unclear and `batches` flag defaults off | Backend-only but likely enable-able. Add a batch queue/monitor UI if batch processing is working. |
| `/api/activity/*`, `/api/tasks/tasks/*` | Release | Activity is enabled by default; task endpoints mostly backend-only | Keep activity. Expose task health/progress only in diagnostics or Activity detail. |

### Chat / Model Comparison

| Endpoint family | Backend status | Frontend status | Recommendation |
|---|---|---|---|
| `/api/chat`, `/conversations/*`, `/providers`, `/extract-text` | Release | Swift services/views exist, but `chat` feature flag defaults off | **Enable next.** Backend works enough to ship behind existing UI; then test and bugfix. |
| `/api/model-comparison/{compare,history,comparison,models,estimate-cost,presets}` | Release; explicitly promoted from dev tier | Swift `ModelComparisonView` and service exist; reachable path is unclear and tied to chat/navigation | **Enable next with chat.** Add sidebar/menu entry and load history/cost in the UI. |
| `/api/model-comparison/{models-by-tier,compare-vision,compare-tool,compare-node,tools}` | Release | Service methods exist for vision/tool/tier/tools; no clear UI affordance | Enable after base comparison, especially tool/node comparison for workflow debugging. |

### Providers / Settings / Models

| Endpoint family | Backend status | Frontend status | Recommendation |
|---|---|---|---|
| `/api/providers`, `/catalog`, `/api-key`, `/models`, `/refs` | Release | Provider settings and model selection are wired; some settings tabs gated | Keep; make sure tabs needed for provider setup are visible in 0.0.2. |
| `/api/settings/ai-defaults` | Release | Enabled via app state/workflow drop handling/settings | Keep. |
| `/api/models/huggingface/*` | Release | Enabled in AI model catalog | Keep if provider/model browsing is in scope. |
| `/api/local-models/*` | Dev tier | Swift `LocalModelsSettingsView` exists, but Models settings tab defaults off | Enable if local model download/delete is ready; otherwise keep gated as a settings-only advanced surface. |

### Integrations / Sync / External Apps

| Endpoint family | Backend status | Frontend status | Recommendation |
|---|---|---|---|
| `/api/integrations`, `/available`, `/{app}/refresh`, `/{app}/items`, import/export/open | Dev tier | `IntegrationsView` and service exist, but `integrations` flag defaults off | **Enable candidate.** This is not agent/thinking; turn on if app-specific adapters are stable enough to test. |
| `/api/integrations/devonthink/*`, `/bookends/*`, `/tinderbox/*` | Dev tier | Service extensions exist for Bookends/Tinderbox; UI mostly generic list/detail | Enable alongside integrations if Daniel wants sync/import workflows surfaced. |
| `/api/iiif/*` | Dev tier | Backend-only | Keep gated unless image/document interoperability is a near-term product surface. |

### Automation / Actions / MCP / Agents

| Endpoint family | Backend status | Frontend status | Recommendation |
|---|---|---|---|
| `/api/actions/*` | Dev tier | Swift action library/picker views and services exist; no default navigation | Should be enabled only if actions are user-facing now. Otherwise leave gated. |
| `/api/schedules/*`, `/api/triggers/*` | Dev tier | Swift automation views/editors exist; `automation` flag defaults off | Enable after workflow smoke tests if scheduled workflows are desired in 0.0.2. |
| `/api/mcp-servers/*` | Dev tier | Swift MCP server views/services exist; `mcp` flag defaults off | Keep gated per #1151 unless the decision is to expose external tool servers now. |
| `/api/mcp/tools/knowledge/*` | Release | Backend-only tool endpoints | Intentionally not a normal SwiftUI surface; keep for MCP/tooling. |
| `/api/policies/orchestration/*`, `/api/agents/write/*` | Dev tier | Backend-only | Intentionally gated per #1151. These are agent-write/approval surfaces. |

### Research / Mind Palace / Experimental Reading Surfaces

| Endpoint family | Backend status | Frontend status | Recommendation |
|---|---|---|---|
| `/api/research/*` | Dev tier | Backend-only | Intentionally gated/uncertain. Do not enable until research-agent UX is reviewed. |
| `/api/mind-palace/*` | Dev tier | Backend-only | Intentionally gated/uncertain. Needs product decision before surfacing. |

## Classification Totals By Route Family

- **Enabled in frontend:** documents/library, file/folder import, storage image display, search/saved search, workflows/execution/chains, activity, provider/settings/model catalog, annotations, image editing, core KG entity/claim/artifact/citation panels, entity merge/split/audit, claim search/analysis, chat/model-comparison services/views but hidden by feature flags.
- **Backend-only but should be enabled:** chat/model comparison, integrations, local models settings, notes/backlinks, projects, bibliography import/export/extract, XLSX import, batches, KG review/prediction/mutation/graph tools, workflow import/export, automation schedules/triggers if workflow scheduling is in scope.
- **Intentionally gated:** MCP servers/tools, orchestration/agent-write policy, research agents, mind palace, IIIF, SPARQL/PyKEEN unless Daniel explicitly wants them visible.
- **Dead/uncertain:** `/api/stats`, generic `/api/folders/{entity_type}`, references/sources duplication, migrations UI, storage debug/snapshots, search backend view endpoints, multilingual, hermeneutics if #1124 is not active.

## GitHub Follow-Up

Filed tracking issue: [#1288](https://github.com/dtubb/fichero/issues/1288). Related: #1151 and #1072.
