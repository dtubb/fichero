# SwiftUI whole-app logic audit — logic that belongs in the backend (#1072)

**Date:** 2026-05-14
**Author:** autonomous loop (Phase B extension — #1072)
**Scope:** the *whole* SwiftUI app — `Views/`, `Models/`, `Services/` — **excluding**
the KG/document-inspector surface, which is already covered by the companion
doc `swiftui-logic-audit.md` (findings #1068/#1069/#1047/#1050, all shipped).
**Principle:** the backend owns logic (computation, aggregation, dedup, scoping,
summarization, filtering, cross-record reconciliation). SwiftUI only *renders*
what the backend hands it. (MEMORY `feedback_kg_logic_in_backend`.)

**Method:** three parallel sweeps read every `.swift` file in scope (235 view
files, 41 models, 49 services). Sweep A — Library/Search/Components. Sweep B —
Workflow/Activity/Toolbars/Menu. Sweep C — Services/Models/Settings/AIProviders.

---

## Headline finding

The KG audit found *one* surface (KG entities) reaching the UI through
inconsistent client-side paths. The whole-app sweep finds the **same anti-pattern
in three more places**, each with the same failure mode — *two or more SwiftUI
views independently compute the "same" thing from raw rows, and they disagree*:

| Cluster | Surfaces that re-implement it | What's missing on the backend |
|---|---|---|
| **Artifacts** | `ArtifactsBrowserView`, `DocumentInspectorArtifactsTab` (`CatalogueArtifactPreviews`), `DocumentInspectorContentV2`, `ArtifactEntitiesView`/`ArtifactEntityCell` | a typed, server-composed artifacts response (typed `items`, `is_canonical`/`superseded_by`, `display_name`) |
| **Workflow runs** | `WorkflowExecutionObserver+Events` (SSE reducer), every `Activity*` view, `WorkflowEditor+Actions` | a backend "workflow run" resource — one composed run aggregate, same shape for live and historical |
| **Model/provider capability** | `AISettingsView` (`TierCapability`), `AIModelSelectionView` (`filteredModels`), `ProvidersView` (`sortOrder`) | tier eligibility + cost-sort + recommended rank as server fields; resolved AI defaults |

Toolbars, Menu, Components, Search, and the domain Models are **clean** — they
are legitimate presentation. The problem is concentrated in artifacts, workflow
runs, and provider/model resolution.

---

## Cluster 1 — Artifacts (HIGH)

Four views each fetch raw `Artifact` rows and re-implement filtering, raw
`data["items"]` JSON parsing, type grouping, and raw/`_clean` reconciliation.

- **`ArtifactsBrowserView.swift:26–68`** — downloads up to 500 raw artifacts,
  then client-side derives the type facet list, free-text filters, 4-way sorts,
  groups by type. O(library) download + filter.
- **`DocumentInspectorArtifactsTab.swift:19–29`** — raw/`_clean` supersession:
  strips the `_clean` suffix, hides any raw artifact whose `_clean` sibling
  exists. **`DocumentInspector.swift:895–917`** (`DocumentInspectorContentV2.sortedArtifacts`)
  is a *second, independent* implementation of the same canonical-vs-raw rule.
- **`DocumentInspectorArtifactsTab.swift:413–526`** (`CatalogueArtifactPreviews`)
  — parses `artifact.data["items"]` reaching into raw keys with **bilingual
  Spanish/English fallbacks** (`nombre`/`name`, `fecha_normalizada`/`date_normalized`).
  Schema knowledge — including locale logic — living in the view.
- **`LibraryView+ColumnConfig.swift:313–372` + `:416–469`** — `extractNames` /
  `extractKeywords` / `extractDates` are **duplicated verbatim** between
  `ArtifactEntitiesView` and `ArtifactEntityCell`, and overlap
  `CatalogueArtifactPreviews` — *three copies* of the same `items` parser, one
  of them run once per visible table cell.
- Type→icon/color/**label** maps are hardcoded in **three** places
  (`ArtifactsBrowserView:359–396`, `DocumentInspectorArtifactsTab.iconByType`,
  `DocumentInspector.swift:641–722` `ArtifactPanel`) and **already disagree**
  (`summary_file` → "File Summary" vs "Summary").
- Filtering business rules — `shouldHideArtifactType` (`DocumentInspectorArtifactsTab.swift:364–371`)
  and `hiddenMetadataKeys` (`DocumentInspectorMetadataTab.swift:47–53`) — hardcode
  "which artifact types / metadata keys are internal substrate" in views.

**Backend replacement:** a typed, server-composed artifacts response. Extend
`artifacts.py` (`list_all_artifacts`, `list_document_artifacts`) or fold into the
existing `/{document_id}/inspector` aggregate, returning: typed `items` (a
`CatalogueItem` schema with normalized `name`/`context`/`date` — bilingual key
reconciliation moves server-side), an `is_canonical`/`superseded_by` flag, a
`display_name`, a `user_visible` flag, and optional `search`/`sort_by`/`group_by`
query params + a type-facet list.

---

## Cluster 2 — Workflow runs (HIGH)

**Root cause: there is no backend "workflow run" resource the frontend can
render.** The client subscribes to raw SSE events, runs its own reducer to build
a `WorkflowExecution` aggregate, then every Activity view re-derives progress,
status, and error rollups from it — disagreeing with each other and with the
historical (server-fetched) path.

- **`WorkflowExecutionObserver+Events.swift:12–187`** — a full client-side SSE
  reducer: per-node state, per-file step matrix, running totals, **and terminal
  workflow status derivation** (`:148–162` — "completed vs failed", synthesizes
  the `"N file(s) failed"` string).
- **`WorkflowExecutionTypes.swift:29–38`** — `overallProgress` computed two
  incompatible ways (file-based vs node-mean); the historical path has no
  equivalent at all, so a completed run shows no progress.
- **`WorkflowEditor+Actions.swift:149–162`** — re-derives `finalStatus` a
  *second* time in the view layer, duplicating the reducer's `:148–162`.
- **Per-document status rollup** — duplicated in
  `ActivityProgressView+LiveProgress.swift:96–136` and
  `ActivityOverviewView.swift:131–157` with **different rules** (Overview adds an
  "empty stepStatuses ⇒ grey" branch the other lacks).
- **`ActivityDetailView.swift:27–33`** — `errorCount` computed two
  non-equivalent ways for live vs historical; the same filter is repeated at
  `:202–205` to feed `ActivityErrorsView`.
- **`ActivityErrorsView.swift:16–35`** — error list reconciled from two
  independent client-side collections (`nodeStates` + per-file `stepStatuses`).
- **`ActivityProgressView+DataLoading.swift:7–31`** — *the smoking gun*: the
  frontend models (`ProgressTimeline`, `NodeProgressStats`, `ExecutionStep`)
  exist for a backend `progress_timeline` that **was never shipped**; the body is
  commented out with `TODO: Re-enable when backend schema is updated`.
- **Node-name filtering** — `activityHumanNodeName` is used as a hide-predicate
  in 6+ Activity sites; MEMORY `feedback_langgraph_node_display` records the
  backend *already* has `_is_internal_langchain_node()` in `runner.py` (#1002).
  Two divergent filters, two languages. A *third* hardcoded "what's internal"
  list lives in `ActivityGraphView.swift:206–214` (`isInternalKey`) and a
  *fourth* in `+Events.swift:32–33`.
- **`ActivityViewHelpers.swift:125–188`** — `ActivityBrowserView.loadRuns()`
  merges live + historical runs, dedups by thread ID, sorts — aggregation +
  dedup + scoping across sources, done client-side (and again, slightly
  differently, in `Views/Sidebar/ActivityDataProcessing.swift`).
- **Lower severity, same root cause:** `ActivityLogView.messageColor` (`:166–176`,
  log severity guessed by English substring match), `WorkflowOutputLog+ErrorCell.swift:79–99`
  (`simplifyError` — error category by HTTP-code/substring match),
  `WorkflowOutputLog.swift:30–36` (`sourceTools` hardcoded set — should read the
  `ToolInfo` capability registry).

**Backend replacement:** a `GET /workflow-execution/threads/{threadId}/state`
endpoint returning one composed run aggregate — `overall_progress`, per-node
states, per-file step matrix with a server-computed `status` enum +
`served_from_cache`, totals, `phase`/terminal status, `error_count`. The SSE
stream should carry *already-reduced* snapshots of the same shape so the client
appends rather than reduces. A `GET .../threads/{id}/errors` for a uniform error
list. Structured (non-string) log rows with a `level` field. The backend is the
*only* node-name filter — emit `display_name`, never emit internal nodes; delete
`activityHumanNodeName` and the three other hardcoded lists. `GET /activity/runs`
returns the unified, deduped, sorted run list.

---

## Cluster 3 — Model / provider capability resolution (HIGH — ties #1057/#1059)

Model-tier classification, "first available model" default-picking, model-list
sort/filter, and first-run defaulting are computed client-side in **three views
that each classify capabilities differently**.

- **`AISettingsView.swift:280–302`** — `TierCapability.matches` hand-classifies
  a model into text/vision/audio tiers, including a hardcoded
  `modelId == "apple-intelligence"` special-case.
- **`AIModelSelectionView.swift:51–99`** — `filteredModels` is a full
  client-side search + 10-filter + 4-sort pipeline, including a `cheapest`
  composite-cost metric and a `recommended` rank. Its "audio-capable" definition
  (`supportsAudioInput || supportsAudioOutput`) **already diverges** from
  AISettingsView's (`supportsAudioInput` only).
- **`AISettingsView.swift:339–405, 484–494`** — picks `list.first` as the default
  model on provider change, and on first run *guesses* `apple` defaults and
  **persists them from the client** — the default depends on which client opened
  the sheet first.
- **`AISettingsView.swift:257–263`** — dedups the provider list by
  `providerType` because the backend returns duplicate provider rows.
- **`ProvidersView.swift:83–103`** — a hardcoded provider sort-priority table
  that ignores the `sort_order` field `ProviderCatalogResponse` already carries.
- **`ActivityTypes.swift:132–181`** — `ActivityItem.status` re-derives status
  from event-type strings with a `default` fallthrough that produces
  silently-wrong status.
- **`ActivityTypes.swift:96–130`** — `parsedTimestamp` tries 6 date formats and
  guesses timezone because the backend emits inconsistent timestamps.

**Backend replacement:** the model-listing endpoint
(`/api/providers/models/{providerType}`) returns `tier_eligibility`, a cost-sort
key, and a `recommended` rank as server fields, and accepts `search`/`filter`/`sort`
params (the HuggingFace search endpoint already proves this pattern).
`GET /api/settings/ai-defaults` returns *resolved* non-empty defaults instead of
`""`. `GET /api/providers` stops returning duplicate `providerType` rows. The
`/api/activity` rows carry a `status` field directly. The backend emits
timezone-aware ISO8601 timestamps in one format.

---

## Smaller / cross-cutting findings (MEDIUM–LOW)

- **`fileSizeInBytes` metadata probing** — `LibraryView+ColumnConfig.swift:137–162`
  probes `File_Size`/`file_size`/`size` keys with type coercion; partially and
  *inconsistently* repeated in `DocumentInspectorInfoTab` and
  `DocumentInspectorMetadataTab.formatMetadataValue`. Fix: a typed
  `Document.fileSize: Int?` populated at ingest. (MEDIUM)
- **`SearchView+Helpers.swift:72–108`** — `reindexLibrary()` infers "indexing
  done" by polling `/stats` for a count that's stable across two polls. Fragile
  heuristic; the backend should expose an explicit reindex-complete signal.
  (MEDIUM)
- **`SearchResultRowFromAPI.swift:82–92`** — `matchSourceLabel` reconciles
  `match_sources`/`match_source` from raw metadata; needs a typed
  `SearchResult.matchSources: [String]` (schema bump). (LOW)
- **`LibraryView+FilterAndBatch.swift:18–28`** — `filteredDocuments` is a second,
  weaker client-side search path that disagrees with the real Search view.
  Acceptable while folders are small; fold into a folder-documents query if they
  grow. (LOW)
- **`AddProviderSheet+Helpers.swift:7–13`** — `defaultServerUrl` hardcodes
  `ollama`/`lmstudio` localhost URLs; belongs as `default_api_base` on
  `ProviderCatalogResponse`. (LOW)
- **Dead-code cleanup:** duplicated `swiftUIColor` color-maps between
  `ProviderServiceTypes.swift` and `GeneratedTypeExtensions.swift`
  (`ProviderCatalogEntry` looks like a dead legacy type);
  `workflowSubmenuItems` grouping duplicated between
  `LibraryView+FilterAndBatch.swift` and `SidebarItemRow.swift` (a shared Swift
  helper, not a backend move); `Document.ingestMode`'s legacy `bookmark`
  heuristic fallback can be deleted once old docs are migrated. (LOW)

---

## Proposed backend endpoints (whole-app)

1. **Artifacts** — typed server-composed artifacts response (typed `items`,
   `is_canonical`/`superseded_by`, `display_name`, `user_visible`, optional
   `search`/`sort`/`group_by`). Extends `artifacts.py` or the `/{id}/inspector`
   aggregate. **Retires Cluster 1.**
2. **Workflow run state** — `GET /workflow-execution/threads/{threadId}/state`
   (one composed aggregate) + `.../errors` + structured log rows + SSE carrying
   reduced snapshots. **Retires Cluster 2** (the single highest-leverage fix —
   collapses the SSE reducer, every Activity rollup, and the node-name filters).
3. **Model/provider listing** — `tier_eligibility` + cost-sort + `recommended`
   as server fields, `search`/`filter`/`sort` params; resolved AI defaults;
   de-duplicated `/api/providers`. **Retires Cluster 3** (ties #1057/#1059).
4. Typed `Document.fileSize`; explicit reindex-complete signal; typed
   `SearchResult.matchSources`; `default_api_base` on the provider catalog.

---

## Recommended sequence

The KG cluster (companion doc) is done. For the rest:

1. **Artifacts response (Cluster 1)** — self-contained, pytest-verifiable,
   retires the most duplicated parser in the app (3 copies of the `items`
   parser, 3 type-label maps). Good next 0.0.2 backend target.
2. **Workflow run-state endpoint (Cluster 2)** — highest leverage but largest:
   it needs a real `workflow_run` aggregate + SSE shape change. Likely splits —
   the read endpoint can land in 0.0.2, the SSE-snapshot rework in 0.0.3.
3. **Model/provider listing (Cluster 3)** — overlaps the open product decisions
   #1057 (model defaults) and #1059 (consolidate pickers); do the server-fields
   part once those are decided.
4. Smaller typed-field fixes (`Document.fileSize`, `matchSources`,
   `default_api_base`) — cheap, batchable.

Each backend step is pytest-verifiable; the SwiftUI changes are render-only
follow-ups (Phase C). Per the audit's own exclusions, the ~50 Workflow
canvas/editor files, Toolbars, Menu, Components, and the domain Models are
legitimate presentation and need no change.
