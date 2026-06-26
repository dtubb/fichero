# Endpoints vs UX Audit — through the Node-Model lens

> Issue #2588 · Milestone *Node Model & Endpoint Unification* · Base `0.0.2`
> Status: **proposal / informational** — no code changed. Read-only audit to drive consolidation.

## 2026-06-26 worker refresh

Current pass ran from `worker/2633` on `origin/0.0.2` and rechecked the route
surface against the settled SwiftUI service/store/view layer. The committed
endpoint coverage matrix reports **655 OpenAPI operations**; most mismatches are
already seeded guardrail gaps, which matches the audit finding that the problem is
not one missing wrapper but too many parallel endpoint families around the same
library-node concepts.

Follow-up issues filed from this audit:

- #2636 — add a general `/api/library/links` endpoint for typed node relations.
- #2637 — persist saved searches as smart-folder nodes.
- #2638 — retire or quarantine no-UX route families instead of carrying them in
  the app API.

Related existing follow-ups already covering major collapse areas:

- #2081 — library node-model epic.
- #2446 — research/workspace sidebar modes become library-tree node kinds.
- #2447 — entities live in the library as folder-like nodes.
- #2299 — backend Mind Palace cleanup for dead room routes and CLI/MCP surfaces.

## Why this exists

Daniel's framing: **the Library is ONE graph of typed nodes.** Most of what looks
like a separate "subsystem" in the engine is really a node **type** + **attributes**
+ **relations** + a **view mode**, all of which the library/document endpoints can
serve. Only true **processes** (workflows, actions, providers, auth, import, search
execution, rendering) deserve their own endpoint family.

This document maps the ~80 route modules under
`fichero-engine/src/fichero/api/routes/` against the SwiftUI UX that has actually
emerged (`fichero/fichero/Views/**`, the hand-written `Services/*`, and the
`@Observable`/`ObservableObject` stores in `fichero/fichero/Models/*`), and gives
each family a verdict.

**Method / evidence rule.** The SwiftUI app reaches the engine three ways:
the generated OpenAPI client (`client.api.<operationId>…`), hand-written service
wrappers (`Services/*Generated.swift`, `Services/*Service.swift`), and the
reactive stores. The *generated client contains an operation for every endpoint in
`openapi.json` whether or not the app uses it* — so presence in the generated
package proves nothing. The signal used here is a **hand-written service / store /
view consumer**. "No caller found" = a `search_text` over `fichero/fichero/**/*.swift`
(excluding the generated `FicheroAPIClient` package and stale `.claude/worktrees/`)
returned no wrapper/store/view reference. Where the UX is genuinely unclear I say so.

---

## 1. Inventory — route modules grouped by family

Route modules (symbol counts in parens) grouped into ~25 families:

| Family | Route modules |
|---|---|
| **Documents / Library tree** | `documents` (108), `document_inspector` (18), `folders` (22), `library` (1), `library_registry` (5), `library_entity_types` (5), `registries` (13) |
| **Storage / rendering** | `storage` (21), `iiif` (14) |
| **Artifacts** | `artifacts` (13), `image_editing` (57) |
| **Classifications (node types)** | `classifications` (23) |
| **Citations / bibliography / sources** | `citations` (8), `citation_rendering` (6), `citation_usages` (3), `bibliography` (22), `sources` (24), `references` (23) |
| **Annotations** | `annotations` (42) |
| **Notes** | `notes` (30) |
| **Knowledge Graph (entities + claims)** | `entities` (40), `entity_inspector` (6), `kg_entity_curation` (30), `claims` (43), `claim_curation` (53), `claim_links` (24), `kg_graph` (30), `kg_review` (17), `kg_curation_rules` (22), `kg_claim_search` (8), `kg_claim_analysis` (5), `kg_search` (6), `kg_render` (4), `kg_rebuild` (5), `kg_inclusion` (3), `kg_mutations` (5) |
| **KG — experimental ML** | `kg_pykeen` (12), `kg_predictions` (12), `kg_triangulation` (5), `kg_sparql` (9) |
| **Hermeneutics / interpretations** | `hermeneutics` (61), `multilingual` (20) |
| **Search** | `search` (78), `search_explain` (20) |
| **Workflows** | `workflows` (74), `workflow_execution/*` (~56), `chains` (35), `orchestration` (23) |
| **Actions** | `actions` (34), `actions_registry` (13) |
| **Chat / model comparison** | `chat` (42), `model_comparison` (49) |
| **Providers / models** | `providers` (56), `provider_keys` (15), `provider_models` (18), `models` (12), `local_models` (4), `local_inference` (20) |
| **MCP** | `mcp_servers` (19), `mcp_tools` (22) |
| **Activity** | `activity` (30), `changes` (3) |
| **Automation** | `schedules` (18), `triggers` (17) |
| **Batch / ingest** | `batch` (57), `ingest` (19) |
| **Research workspace** | `research_crud` (29), `research_notes` (14), `research_tools` (13), `research_agents` (0) |
| **Tasks / projects (standalone)** | `tasks` (25), `projects` (13) |
| **Mind Palace / canvas** | `mind_palace` (70), `mindpalace_render` (4) |
| **Saved views** | `views` (8) |
| **Integrations** | `integrations` (32) |
| **Auth / devices** | `auth_accounts` (36), `pairing` (32) |
| **Infra / settings** | `settings` (17), `migrations` (20), `export` (10), `agent_memory` (24), `triggers`/`schedules` above |

---

## 2. Family-by-family verdicts

Legend: **KEEP** · **COLLAPSE-INTO-LIBRARY** · **REDUNDANT/LEGACY** · **MISSING**

| Route family | SwiftUI UX surface(s) that consume it | Verdict |
|---|---|---|
| **documents / document_inspector** | `DocumentStore` (+ `+CRUD/+ChangeStream/+Helpers`), `LibraryView`, `DocumentInspector*`, `DocumentServiceGenerated`. The spine. | **KEEP** — this *is* the node endpoint. It becomes the consolidation target (see §3). |
| **folders** | `FolderService` (`/folders/{id}/views`), sidebar tree (`SidebarItemBuilder`, `SidebarView+UnifiedLibrarySections`). | **KEEP** — the node *tree*. Fold `views` into it (already reads `/folders/{id}/views`). |
| **storage** | `StorageService(Generated)`, `LibraryImageView`, PDF/Image viewers. Serves bytes via HTTP (per "no local paths" rule). | **KEEP** (infra). |
| **classifications** | `ArtifactServiceGenerated` — `/api/classifications?dimension=node_class` and `?dimension=document_prototype`; `NodeClassPicker`, `DocumentInspectorInfoTab+Prototype`. | **KEEP** — **this is already the node-type system.** It is the attribute layer the COLLAPSE rows fold onto. |
| **artifacts / image_editing** | `ArtifactServiceGenerated`, `ArtifactStore`, `ArtifactPanel`/`ArtifactsBrowserView`; `ImageEditingServiceGenerated`, `ImageEditor*`. | **KEEP** — artifacts are node children; image-editing is a process. |
| **annotations** | `AnnotationService`, `AnnotationStore`, `AnnotationListView`/`AnnotationsInspectorPane`. | **KEEP** — node child of a document (data could later fold into the node tree, but it is a clean live surface). |
| **notes** | `NoteService`, `NoteStore`, `Notes/*` views. | **KEEP** — canonical note surface. *Absorbs* `research_notes` (see below). |
| **citations / bibliography / citation_usages / citation_rendering / sources / references** | `ArtifactServiceGenerated` (`/api/bibliography/*`, `/api/citations/*`, `/api/citation-usages`, `/api/sources`), `CitationStore`, `ReferenceStore`, `DocumentInspectorInfoTab+Bibliography/+Citations`, `Citations/References` inspector panes. | **KEEP** — node attributes/children of documents. Candidate to merge the *six* modules into one `bibliography` family later, but all are live. |
| **entities + claims + kg_graph + kg_entity_curation + kg_review + kg_curation_rules + kg_claim_search + kg_claim_analysis + claim_curation + claim_links** | `ClaimStore`, `EntityServiceGenerated`, `OntologyBrowser*`, `EntityDetailView*`, `KGMapView`, `ForceDirectedGraphView`, `ClaimReviewQueueSheet`, `ContradictionTriageSheet`, `DocumentInspectorArtifactsTab+KGSection`. | **KEEP** — the KG *is* the node graph; large, live surface. `claim_links` is the one real relations endpoint that exists. |
| **kg_render / kg_search / kg_rebuild / kg_inclusion / kg_mutations** | Mixed. `DocumentKGWebPane`/`DocumentKGSurface` render KG; some are internal rebuild/inclusion ops with no direct wrapper. | **KEEP** (render/search) / **verify** (rebuild/inclusion/mutations may be backend-internal — fold into `kg_graph`). |
| **kg_pykeen / kg_predictions / kg_triangulation / kg_sparql** | **No caller found** in app Swift. Experimental ML (embeddings, link prediction, SPARQL). | **REDUNDANT/LEGACY** — backend-only experiments; no UX. Candidates to delete or move behind a research flag. |
| **hermeneutics** | `InterpretationStore` consumes `EntityServiceGenerated.listDocumentInterpretations`; `DocumentInspectorArtifactsTab+Interpretations`, `DocumentNotesTab`. The `interpretation.*` change events drive the inspector. | **KEEP** (data: interpretations are a document-scoped node child) **+ COLLAPSE** the *decompose pipeline* stays a process; the interpretation records belong on the node. |
| **multilingual** | **No caller found.** | **REDUNDANT/LEGACY** — verify; likely backend pipeline only. |
| **search / search_explain** | `SearchServiceGenerated`, `SearchStore`, `Search/*` views, `SearchResultRowFromAPI`. | **KEEP** (process) — query execution. **But `search/saved` data → COLLAPSE** (below). |
| **search/saved (subset of `search`)** | `SavedSearchServiceGenerated`, rendered as `SidebarItem.savedSearch` virtual folders (`SidebarItemBuilder.buildSearchHierarchy`). | **COLLAPSE-INTO-LIBRARY** — a saved search is a **smart-folder node**. The *query execution* stays in `search`; the *persisted saved search* should be a library node type, so it lives in the same tree/sidebar as folders. |
| **workflows + workflow_execution + chains** | `WorkflowServiceGenerated`, `WorkflowExecutionStore`/`Service`/`Observer`, `WorkflowStreamService`, `ChainService`, the entire `Views/Workflow/*` canvas. | **KEEP** — core process. |
| **orchestration** | **No caller found** (execution goes through `workflow_execution`). | **REDUNDANT/LEGACY** — verify; fold into `workflow_execution` or delete. |
| **actions / actions_registry** | `ActionStore`, `ActionInvokeService`, `ActionLibraryService`, `ActionsService`, `Actions/*` views. The audited action layer (EPIC #1848). | **KEEP** — the one audited mutation layer; stays separate by design. |
| **chat / model_comparison** | `ChatService(Generated)`, `ConversationServiceGenerated`, `Chat/*`; `ModelComparisonService`, `ModelComparison/*`, `ComparisonDetailView`. | **KEEP** — processes. (Conversations *could* later be node-typed, but live + distinct.) |
| **providers / provider_keys / provider_models / models / local_models / local_inference** | `ProviderServiceGenerated`, `ModelServiceGenerated`, `AIProviders/*`, `LocalModelsSettingsView`. | **KEEP** — infra/process. Candidate to merge the 6 modules into one `providers` family, but all live. |
| **mcp_servers / mcp_tools** | `MCPService`, `MCPServers/*`. | **KEEP** — infra/process. |
| **activity / changes** | `ActivityServiceGenerated`, `Activity/*`, SSE `/activity/stream`; `LibraryChangeStream` (the reactive change feed). | **KEEP** — infra. `changes` is the backbone of the observable data layer (#1863). |
| **schedules / triggers** | `AutomationService(Generated)`, `Automation/*` views. | **KEEP** — processes. |
| **batch / ingest** | `BatchServiceGenerated`, `ImportService(Generated)`, batch UI in `LibraryView+FilterAndBatch`, `DocumentPickerSheet`. | **KEEP** — import/batch processes. |
| **integrations** | `IntegrationsService` (`/api/integrations/*`), `IntegrationsView`. | **KEEP**. |
| **auth_accounts / pairing** | `RemoteClientPairing`, `BackendConnectionView`, multi-user (#2021/#2022, behind `FICHERO_MULTIUSER`). | **KEEP** — process/infra. |
| **settings / migrations / export** | `Settings/*`, `BackupsView`, `BackendSettingsView`. `export` mostly workflow-export (`WorkflowExporter`). | **KEEP** (settings/migrations) / **verify** standalone `export`. |
| **research_crud (projects/plans/tasks/steps/checklists)** | `ResearchService` + `ResearchStore`, `Research/*` (`ResearchProjectListView`, `ResearchTasksPane`, `ResearchWorkspaceView`). **`ResearchProject` already carries `libraryDestinationFolderId`.** | **COLLAPSE-INTO-LIBRARY** — research project/plan/task/step/checklist are a **parallel node tree** that already points back into a library folder. They should be library node *types* under a research-project root node, not a separate CRUD store. |
| **research_notes** | `ResearchService.createNote/updateNote/loadNotes`. Duplicates the Notes surface. | **COLLAPSE** — fold into `notes` (a research note is just a note with a project scope). |
| **research_tools** | `ResearchService.webSearch` (`/api/research/tools/web-search`), `browserSave` (`/api/research/tools/browser-save`). | **KEEP** — these are *processes* (web search, save-from-browser). Stay separate when research data collapses. |
| **research_agents** | **0 symbols — empty module.** No caller. | **REDUNDANT/LEGACY** — delete. |
| **tasks (standalone) / projects (standalone)** | **No caller found.** App's tasks/projects go through `…ApiResearch…` operations (research_crud), not `/api/tasks` or `/api/projects`. | **COLLAPSE or REDUNDANT** — if these are a legacy parallel project/task store, delete or fold into the research node types. **Verify** they are not the in-app Agent task system (#2067) before removing. |
| **mind_palace / mindpalace_render** | `CanvasItemStore` + `CanvasLayoutStore` consume `/api/mind-palace/folders/{id}/canvas-items` and `/canvas-layout`; `SpatialView`/`SpatialScene3D` render it. **But `MindPalaceLibraryProjector` already builds the spatial scene *client-side* from `/api/entities`** — its own comment calls it "the temporary" projector pending a real `/api/mind-palace/library/scene` (which does not exist). | **COLLAPSE-INTO-LIBRARY** — the spatial scene is a **view mode** over library nodes; canvas position/layout are node **attributes**; node-to-node lines are a **links relation**. This is the single biggest win (see §3). |
| **views (standalone)** | **No caller of `/api/views`**; the app reads view config via `/folders/{id}/views`. | **COLLAPSE-INTO-LIBRARY** — saved view config = folder/node attribute; fold into folders. |
| **library / library_registry / library_entity_types / registries** | **No direct app caller found** (`library.py` has 1 symbol — a router include). | **COLLAPSE-INTO-LIBRARY (seed)** — these are the node-type/registry seams. They are the natural home of the unified node-type endpoint (§3), not standalone routers. |
| **agent_memory** | **No caller found** (the `Agents/*` views are configuration, not memory). | **REDUNDANT/LEGACY** — backend/agent-internal; verify against the in-app Agent EPIC (#2067) before deleting. |
| **iiif** | **No caller found** (images served via `storage`). | **REDUNDANT / FUTURE** — archival IIIF is a stated future direction (interchange/static-site), not a live UX. Keep dormant or move out of the app's hot path. |

---

## 3. The consolidated target — one library/node endpoint family

The COLLAPSE rows all fold onto **one node spine** that already mostly exists in
`documents` + `folders` + `classifications`:

```
/api/library/nodes                     ← the unified node endpoint
  GET    /nodes?node_class=…&parent=…   list/filter (folders, documents, research
                                         projects/plans/tasks, saved searches, …)
  POST   /nodes                          create a node of any node_class
  GET    /nodes/{id}                      one node + attributes
  PATCH  /nodes/{id}                      edit attributes (incl. canvas x/y/z,
                                          layout, view-mode state, status)
  DELETE /nodes/{id}
  POST   /nodes/{id}/move                 reparent (the tree)

/api/library/links                      ← the ONE relations endpoint (generalises
                                          claim_links + MindPalaceLink)
  GET/POST/DELETE  typed edges between any two nodes

/api/library/node-types                 ← from library_entity_types + registries +
                                          classifications(dimension=node_class)
```

- **`node_class`** already exists as a classifications dimension and a SwiftUI
  `NodeClassPicker`/`MindPalaceNodeType` — it is the discriminator for *what kind*
  of node (document, folder, research-project, task, saved-search, interpretation).
- **Attributes** (canvas position/layout, view-mode, prototype, status) live on the
  node — folding in `mind_palace/canvas-*`, `views`, research `status`.
- **Relations** (`/links`) generalise the existing `claim_links` and the
  client-only `MindPalaceLink`/`MindPalaceConnection`.
- **View modes** (list/table/map/spatial/reading) are a *client* concern over the
  same node feed — the spatial Mind Palace becomes a renderer, not an endpoint.

**Folds into the spine:** mind_palace + mindpalace_render, views, research_crud
(projects/plans/tasks/steps/checklists), research_notes→notes, search/saved,
library_registry/library_entity_types/registries, tasks/projects (standalone),
interpretation records (from hermeneutics).

### Stays separate — true processes / infra

These do *not* fold; they act on nodes but are verbs/infrastructure:

`workflows` + `workflow_execution` + `chains` · `actions`/`actions_registry` ·
`search`/`search_explain` (query *execution*) · `providers`(+keys/models/local) ·
`chat` + `model_comparison` · `mcp_servers`/`mcp_tools` · `activity` + `changes`
(the reactive stream) · `storage` (bytes) · `image_editing` · `ingest` + `batch` ·
`schedules` + `triggers` · `integrations` · `auth_accounts` + `pairing` ·
`research_tools` (web-search/browser-save) · `settings` + `migrations`.

### MISSING

- **`/api/library/links` (general node-to-node relations).** Only `claim_links`
  exists; Mind Palace edges are faked client-side in `MindPalaceLibraryProjector`.
- **`/api/mind-palace/library/scene`** — referenced by name in the projector's own
  comment but does not exist; the app reconstructs the scene from `/api/entities`
  client-side. Either build it as a *view-mode projection of `/nodes`*, or keep the
  client projector and drop the half-built `mind_palace` CRUD.
- **A single `node_class`-typed list endpoint** — today documents, folders,
  entities, research nodes, and mind-palace nodes are five separate trees.

---

## 4. Staged, low-risk sequence

Pre-release: schema can change directly in `db.py` `_ensure_table` per rule #9 —
**except** anything touching real library data (Marshall Diaries), which needs an
idempotent migration in `db_migrations.py` (policy update 2026-06-12). Flags below.

1. **Delete the dead, zero-consumer modules (no data risk).**
   `research_agents` (empty), and after a quick confirm, `kg_pykeen`,
   `kg_predictions`, `kg_triangulation`, `kg_sparql`, `multilingual`,
   `orchestration`. Pure router removals — no UX, no tables touched.
   *Risk: low. No migration.*

2. **Confirm-then-retire the standalone parallel stores.**
   Verify `tasks`/`projects`/`views`/`agent_memory` have no live caller (and are
   not reserved for the in-app Agent EPIC #2067). Fold `views` reads onto the
   already-used `/folders/{id}/views`. *Risk: low; flag if any backing table holds
   real rows → migration.*

3. **Unify notes.** Point `research_notes` at the `notes` store (a research note =
   note + project scope). Collapse `ResearchService.*Note*` onto `NoteService`.
   *Risk: low–medium; if research_notes has its own table with real rows, backfill
   into notes via `db_migrations.py` (FLAG: touches data).*

4. **Introduce `/api/library/links`.** Generalise `claim_links`; back the
   client-only `MindPalaceLink` with it. Additive endpoint — nothing removed yet.
   *Risk: low (additive).* 

5. **Mind Palace → view mode (biggest win).** Add canvas x/y/z + layout as node
   **attributes** on the node/folder model; expose the scene as a projection of
   `/nodes` (+ `/links`). Migrate `mind_palace` canvas-items/canvas-layout rows onto
   node attributes, then retire `mind_palace`/`mindpalace_render` CRUD. Keep the
   SwiftUI `SpatialView` as a renderer over the unified feed. *Risk: medium; **FLAG**
   — canvas layout rows are real data → idempotent migration required.*

6. **Research tree → library node types.** Promote research project/plan/task/step/
   checklist to `node_class` values under a research-project root node (it already
   has `libraryDestinationFolderId`). Keep `research_tools` as processes. Migrate
   existing research rows into the node tree. *Risk: medium–high; **FLAG** — real
   data; phased migration + keep `ResearchService` API shape stable for the UI.*

7. **Saved search → smart-folder node.** Persist saved searches as a `node_class`;
   `search` keeps executing queries. *Risk: low–medium; **FLAG** if saved-search
   rows exist.*

8. **Collapse the node-type registries.** Merge `library_entity_types` +
   `registries` + `classifications(node_class)` behind `/api/library/node-types`.
   *Risk: low (mostly read paths).* 

Throughout: every retirement is **collapse onto the canonical node spine**, never a
fresh parallel replacement (constitution "Iterate, never replace"). Ship one stage,
verify the full backend suite + the SwiftUI build, then take the next.

---

## Headline numbers

Counting the ~25 grouped families:

- **KEEP: ~16 families** — documents/library-tree spine, storage, classifications,
  artifacts/image-editing, annotations, notes, citations/bibliography, the KG,
  search execution, workflows, actions, chat/model-comparison, providers, MCP,
  activity/changes, automation, batch/ingest, integrations, auth/devices, settings.
  (These are the live UX surfaces + true processes/infra.)
- **COLLAPSE-INTO-LIBRARY: ~6 families** — mind_palace/canvas, research_crud
  (+research_notes), standalone tasks/projects, saved-searches, standalone views,
  library_registry/entity_types/registries (the node-type seed). Plus the
  *data* half of hermeneutics interpretations.
- **REDUNDANT/LEGACY: ~4–6 families** — `research_agents` (empty), the experimental
  KG-ML cluster (`kg_pykeen/predictions/triangulation/sparql`), `multilingual`,
  `orchestration`, `agent_memory`, `iiif` (future-dormant). All "no caller found".
- **MISSING: 3** — a general `/links` relations endpoint, the
  `/mind-palace/library/scene` projection it references but never built, and a
  single `node_class`-typed `/nodes` list.

**Single biggest consolidation win:** **Mind Palace → a view mode over the unified
node feed.** The engine has a 70-symbol `mind_palace` CRUD, yet the SwiftUI
`MindPalaceLibraryProjector` *already* rebuilds the spatial scene client-side from
`/api/entities` and admits in its own header comment that it is "temporary" pending
consolidation. Promoting canvas position/layout to node attributes and node-lines to
`/links` lets the spatial scene become a pure renderer of `/nodes` — deleting a whole
parallel endpoint family, removing the client-side fake, and proving out the node
model (attributes + relations + view mode) that every other COLLAPSE row then reuses.
