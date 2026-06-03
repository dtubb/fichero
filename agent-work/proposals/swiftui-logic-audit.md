# SwiftUI KG-logic audit — move logic to the backend (Phase B)

**Date:** 2026-05-14
**Author:** autonomous loop (Phase B, iteration 2)
**Scope:** the KG / document-inspector SwiftUI surface
**Principle:** the backend owns logic (computation, aggregation, dedup, scoping,
summarization, filtering). SwiftUI only *renders* what the backend returns.
(See MEMORY `feedback_kg_logic_in_backend`.)

---

## Headline finding

The KG entity data reaches the UI through **two different, inconsistent paths**:

| Surface | Endpoint(s) it calls | Client-side work it does |
|---|---|---|
| Library **list view** rows | `getArtifacts(forDocumentId:)` | parses `artifact.data["items"]`, extracts names/keywords/dates → lozenges |
| **KG inspector tab** | `listClaims(sourceDocumentId:)` **+** per-entity `getEntity(id)` (O(n) calls) | dedups by canonical name, detects `mergedIntoId`, groups claims into kind buckets, filters hidden kinds |
| **Ontology browser** | `listEntities(query:)` | filters by kind client-side, counts by kind for charts |

Three surfaces, three data sources, three client-side aggregation paths — so they
**disagree** (#1068) and the inspector is slow (O(n) `getEntity` calls). Every
issue in the cluster traces back to this: there is no single canonical
"knowledge for this document/scope" endpoint.

---

## Findings (file → misplaced logic → issue → backend replacement)

### 1. `KnowledgeGraphInspectorSection` — `DocumentInspectorArtifactsTab.swift:639–837`
- **Misplaced:** dedup by canonical name (`seenKey` set), `mergedIntoId` skip, claim→kind bucketing, hidden-kind filtering (lines 674–729). Load path makes `listClaims(...limit:500)` then **loops `getEntity(id)` per unique entity** (805–837).
- **Issue:** #1068.
- **Backend replacement:** `GET /api/documents/{id}/knowledge-graph?include_children={bool}` → returns `{ entities_by_kind, claims }`, already deduped / merge-resolved / grouped. One call, no per-entity fan-out.

### 2. `ArtifactEntitiesView` — `LibraryView+ColumnConfig.swift:176–372`
- **Misplaced:** `extractNames()` / `extractKeywords()` / `extractDates()` pull structured fields out of raw artifact JSON (329–346). Different data source from the inspector → the two never agree.
- **Issue:** #1068 (both surfaces must consume the *same* canonical endpoint).
- **Backend replacement:** same `GET /api/documents/{id}/knowledge-graph` endpoint, a lightweight projection (`?fields=lozenges`) for the list row.

### 3. `EntityDetailView` — `EntityDetailView.swift:6–582`
- **Misplaced:** two-axis claim filtering (epistemic status + claim type) recomputed every render (44–62); **SVO-triple → prose biography composition** with pronouns + inline citations (102–163); filter-chip value sets derived client-side (507–518).
- **Issue:** #1050 (entity header = claim #1, not a real summary), #1030 (raw verb/object repr).
- **Backend replacement:** `GET /api/entities/{id}` returns a pre-composed `summary` / `biography` field + claims already filtered server-side. Prose synthesis is backend work (ties to #989).

### 4. `OntologyBrowser` — `OntologyBrowser.swift:15–582`
- **Misplaced:** `filterEntities()` applies hidden-kinds client-side (76–91); `listEntities(query:)` has free-text search but **no `?entity_type=` / `?scope=` server param** (481–517).
- **Issue:** #1047 (folder scope), #1071 (scoped aggregation + filter/search).
- **Backend replacement:** `GET /api/entities?kinds=...&query=...&scope={document|folder|library}` — filtering and scoping server-side.

### 5. `EntityKindChartView` / `ForceDirectedGraphView` — `OntologyBrowser.swift:895–1529`
- **Misplaced:** client-side count-by-kind bucketing (1457–1466); `hiddenKinds` filtered locally before the layout engine (1111–1122). (`fetchNeighborhood` traversal is correctly server-side — leave it.)
- **Issue:** #902-adjacent; low priority.
- **Backend replacement:** `count_by_kind` as a field on the entities response; `?exclude_kinds=` param on the neighborhood call.

### 6. `ClaimSummaryCard` — `ClaimSummaryCardView.swift:6–399`
- **Misplaced:** SVO extraction with metadata-dict fallback (26–42, duplicated from EntityDetailView); empty-content heuristic — "is `claim.text` a bare noun fragment?" (51–56).
- **Issue:** #1030 (raw verb/object repr), #1029-adjacent (content quality).
- **Backend replacement:** claims arrive with SVO already resolved + a `content_quality` flag; no client-side heuristic.

---

## Proposed backend endpoints

1. **`GET /api/documents/{id}/knowledge-graph`** — the canonical one. Params:
   `include_children` (PDF/folder aggregation — #1069), optional `fields` projection
   for the lightweight list-row case. Returns deduped, merge-resolved,
   kind-grouped entities + their claims. **Replaces findings 1 + 2.**
2. **`GET /api/entities/{id}`** extended — add a server-composed `summary` and
   filtered-claims support. **Replaces finding 3** (#1050).
3. **`GET /api/entities`** extended — `kinds`, `scope`, `count_by_kind`.
   **Replaces findings 4 + 5** (#1071).
4. Claims responses carry resolved SVO + `content_quality`. **Replaces finding 6** (#1030).

---

## Recommended implementation sequence

1. **#1068 first** — build `GET /api/documents/{id}/knowledge-graph` (with
   `include_children` covering **#1069**). This is the keystone: it kills the
   two-endpoints-disagree problem and the O(n) `getEntity` fan-out. Backend +
   pytest only; the SwiftUI rewiring is a thin follow-up.
2. **#1047** — fold the folder catalogue narrative into the same endpoint's
   response when the target is a folder.
3. **#1050** — extend `GET /api/entities/{id}` with the server-composed summary.
4. **#1030 / #1071 / charts** — claims SVO + `content_quality`, `GET /api/entities`
   scoping params. Lower priority.

Each step is backend-first (pytest-verifiable); SwiftUI changes are render-only
follow-ups (Phase C). ~6 files / ~1500 lines of client-side logic retire as the
endpoints land.

---

# Whole-app broadening (#1072)

**Date:** 2026-06-03 · **Author:** milestone worker (Library & Reading Surface)
**Scope:** the broadening #1072 asks for — sweep the **whole** app
(`Views/`, `Models/`, `Services/`), not just KG/inspector. The KG findings above
(2026-05-14) still stand; the items below add the Library / Sidebar / Search /
Services / Models surfaces and the cross-view *duplicate computations*. Where a
finding overlaps the KG audit it is noted (e.g. artifact-JSON extraction = old
finding 2; biography = old finding 3).

## Findings ranked by severity

| # | Finding | File:line | Sev | Owning endpoint (existing / **NEW**) | Bug |
|---|---|---|---|---|---|
| 27 | Load ALL docs (no limit) to build sidebar tree | `Models/DocumentStore.swift:111` | HIGH | `GET /api/documents?tree=true` (**NEW** mode) | #1047 |
| 19 | Inbox identified by `name == "Inbox"` in tree build | `Models/SidebarItemBuilder.swift:93` | HIGH | sidebar-tree endpoint + `is_inbox` flag (**NEW**) | #1047 |
| 3 | Workflow submenu grouped by `folderPath` in **2 places** | `Views/Library/LibraryView+FilterAndBatch.swift:296` + `SidebarItemRow.swift` | HIGH | `GET /api/workflows?grouped=true` (**NEW**) | — |
| 4 | `runWorkflowOnCollection` scopes by client `.file` filter | `Views/ContentView+WorkflowActions.swift:221` | HIGH | accept `folder_id` workflow input (**NEW**) | #1047 |
| 2 | `pdfDocPages` parent-PDF→page rollup (filter+sort) | `Views/ContentView+ReadingLayout.swift:87` | HIGH | consume `GET /api/documents/{id}/children` directly | #1069 |
| 17/18 | Artifact-JSON entity extraction **duplicated** in 2 structs | `Views/Library/ArtifactEntityViews.swift:188` & `:289` | HIGH | typed `entities` on `GET /api/artifacts/{id}` (= old #2) | #1068 |
| 9 | `RelatedClaimsPanel` N+1 similarity + dedup + top-K | `…/DocumentInspector/DocumentInspectorInfoTab.swift:186` | HIGH | `POST /api/kg/claims/similar-to-document` (**NEW**) | #1050,#1068 |
| 10 | Source-doc name resolved from current-folder cache only | `…/DocumentInspectorInfoTab.swift:239` | HIGH | return `source_document_name` inline | #1055 |
| 11 | `biographyComposedText` prose synth + cache name lookup | `…/OntologyBrowser/EntityDetailView+Biography.swift:34` | HIGH | `GET /api/entities/{id}/biography` (= old #3) | #1050 |
| 6 | `ArtifactsBrowserView` facets/filters/sorts/groups (500 cap) | `Views/Library/ArtifactsBrowserView.swift:26` | HIGH | `GET /api/artifacts` + `groupBy`/`facets`/paging | #1068 |
| 15 | `KGTimelineView.datedClaims` parse+join+filter+sort | `Views/KnowledgeGraph/KGTimelineView.swift:211` | HIGH | `GET /api/documents/{id}/timeline` (**NEW**) | #1069 |
| 25 | Client-side status shadow layer (`applyStatusOverrides`) | `Models/DocumentStore+Helpers.swift:175` | MED | status push via SSE / `/status` | #1055 |
| 1 | `filteredDocuments` filters by truncated `pageContent` | `Views/Library/LibraryView+FilterAndBatch.swift:18` | MED | `GET /api/search` (or scope filter to name) | #1055 |
| 7 | `KGInspectorSection.grouped` context-fallback assembly | `…/DocumentInspectorArtifactsTab.swift:183` | MED | resolved `displayContext` on group items (= old #1) | — |
| 8 | Grouped items confidence-sorted in inspector | `…/DocumentInspectorArtifactsTab.swift:226` | MED | return items pre-ranked | #1068 |
| 12 | Epistemic/claim-type filter applied before curation sheets | `…/OntologyBrowser/EntityDetailView.swift:48` | MED | `GET /api/claims?entity_id&epistemic_status&claim_type` | — |
| 13/14 | `DisplayAttributesStrip` artifact rollup + type dedup | `Views/Library/DocumentInspector.swift:784` & `:542` | MED | artifact `summary[]` (type/count/latest_at) | — |
| 20 | `childOrder` 3-key sibling sort policy in client | `Models/SidebarItemBuilder.swift:54` | MED | children endpoint returns canonical order | — |
| 21 | Folder hierarchy re-derived from `folderPath` (4 types) | `Models/SidebarItemBuilder.swift:191` | MED | include `parent_folder_id` / tree endpoints | — |
| 5 | `hasProcessingDocuments` full-list scan per poll | `Views/Library/LibraryView.swift:165` | LOW | `has_pending` in children response | — |
| 16 | `undatedInScopeCount` re-parses dates | `Views/KnowledgeGraph/KGTimelineView.swift:234` | LOW | `undated_count` in timeline response | — |
| 22 | `collectDescendantIds` client BFS (optimistic delete) | `Models/DocumentStore+CRUD.swift:66` | LOW | (backend cascade already canonical) | — |
| 23 | RealityKit layout sort duplicates `childOrder` | `Views/Library/DocumentKGSurface.swift:249` | LOW | consume pre-sorted children | — |
| 24 | `cachedScope` parent-child filter fallback | `Views/Library/DocumentKGSurface.swift:314` | LOW | children endpoint | — |
| 26 | `matchSourceLabel` parses untyped `metadata` array | `Views/Search/SearchResultRowFromAPI.swift:93` | LOW | `match_source_label` on search schema | — |

(Spot-checked: F27 `loadCollections` "Loading all documents", F2 `pdfDocPages`
filter+sort, F19 Inbox name-match at line 93, F17/18 duplicate `extractNames` at
188 & 289 — all confirmed against current source.)

## Cross-view duplicate computations (fix first — these can silently disagree)

- **Dup A — artifact-JSON entity extraction.** `extractNames/Keywords/Dates`
  line-for-line duplicated in `ArtifactEntitiesView` (`ArtifactEntityViews.swift:188`)
  and `ArtifactEntityCell` (`:289`). (F17/18; old KG-audit #2.)
- **Dup B — workflow submenu grouping.** `LibraryView.workflowSubmenuItems`
  (`LibraryView+FilterAndBatch.swift:296`) + a copy in `SidebarItemRow.swift`; the
  source even comments on the duplication. (F3.)
- **Dup C — child sort policy.** `SidebarItemBuilder.childOrder` (`:54`) re-implemented
  in `FolderRealityKitSurface.nodes` (`DocumentKGSurface.swift:251`). (F20/23.)
- **Dup D — parent-PDF path resolution.** `ContentView.resolvedParentPDFPath`
  (`ContentView+ReadingLayout.swift:46`) + `MailStyleRow.resolvedParentPDFPath`
  (`LibraryViewComponents.swift:134`) — same fallback chain. (F2 area.)

## Root cause

Findings 19/20/21/27 stem from one decision: `DocumentStore.loadCollections()` fetches
*every* document with no limit and `SidebarItemBuilder` builds the whole tree
client-side (incl. the `"Inbox"` name-match). A `GET /api/documents?tree=true` mode
returning navigable containers with pre-built nesting + `is_inbox` collapses four
findings and removes the 50k-doc scalability cliff.

## Recommended migration (split into follow-up issues — backend-first, NOT big-bang)

1. **Sidebar tree endpoint** (F19/20/21/27; Dup C) — `GET /api/documents?tree=true`,
   `is_inbox` + canonical child order. Highest leverage; unblocks scalability.
2. **Artifact entity/facet API** (F6/13/14/17/18; Dup A) — typed `entities` + `summary[]`.
3. **KG derivation endpoints** (F9/10/11/15/16; old audit's keystone) —
   `similar-to-document`, `entities/{id}/biography`, `documents/{id}/timeline`.
4. **Per-page / collection scoping** (F2/4; Dup D) — consume `children` directly;
   add `folder_id` workflow input.
5. **Status & search polish** (F1/5/8/25/26).

Each cluster is its own GitHub issue: backend endpoint (pytest-verifiable) + a thin
SwiftUI render-only follow-up. The audit itself (this doc) is the deliverable of
#1072 step 1; the moves are steps 2–3 and should be tracked as the issues above.

