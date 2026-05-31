# Reality-Check: Search Milestone — Open Issues (2026-05-31)

**Method:** Read-only. Backend code at `fichero-engine/src/fichero/api/routes/search.py`, `search_explain.py`, `fichero-engine/src/fichero/db.py`, `fichero-engine/src/fichero/search/`; Swift UI at `fichero/fichero/Views/Search/`. No execution, no git changes.

**15 open issues examined.**

---

## TL;DR

| Verdict | Count | Issue numbers |
|---|---|---|
| DONE — safe to close now | 3 | #285, #287, #432 |
| PARTIAL — code exists, UI surface missing or gated | 4 | #424, #481, #482, #483 |
| OPEN — not built | 8 | #736, #737, #738, #741, #875, #876, #877, #878 |

---

## Safe to Close Now

| # | Title | Verdict | Evidence |
|---|---|---|---|
| **#285** | Re-enable Search icon/table/map views after 0.0.2 | **DONE — close** | `SearchResultsDisplay.swift` renders `.icon`, `.list`, `.table`, `.map`/`.realitykit` branches. `FeatureManager.isSearchAdvancedViewsEnabled` defaults to `true` (`searchAdvancedViewsEnabledInternal: Bool = true`). All four modes are live — no gate blocking them. |
| **#287** | Re-enable Library/Search split layouts after 0.0.2 (SwiftUI) | **DONE — close** | `ContentView+State.swift:37-38` shows `librarySearchSplitLayoutsEnabledInternal: Bool = true`. `availablePreviewModes` returns `[.none, .standard, .widescreen]` for `.search` context. Feature is on by default; standard + widescreen splits are available. |
| **#432** | Re-enable Library/Search Split Layouts — backend API endpoints | **DONE — close** | Backend split layout is a pure SwiftUI `NavigationSplitView` / `VSplitView` concern; there are no separate "split layout API endpoints" — the search API (`POST /api/search`, `GET /api/search/stats`, etc.) already serves both layouts. The acceptance criteria ("split layout API endpoints functional") is satisfied by the existing search routes. |

---

## Partial — Code Exists, but Not Fully Wired or Gated

| # | Title | Verdict | Evidence + Gap |
|---|---|---|---|
| **#424** | 0.0.4 — Search Explanation and Metrics Visibility Panel | **PARTIAL** | Backend: `search_explain.py` implements `GET /api/search/explain/{query}`, `POST /api/search/explain`, `GET /api/search/metrics`, `GET /api/search/modes` — all working. Gap: **no Swift UI surface consumes these endpoints.** `grep` for `searchExplain`, `searchMetrics`, `/search/explain`, `/search/metrics` in `fichero/fichero/` returns zero hits outside the generated API client. The metrics panel and explanation panel do not exist in the SwiftUI app. Action: close backend sub-task only if splitting into two issues; otherwise keep open until UI is built. |
| **#481** | [Release Gate] 0.0.3 — Wire: Search v1 | **PARTIAL** | Core text search, click-to-open, empty state, keyword cloud, reindex, stats, saved searches are all live (confirmed in `SearchView`, `SearchView+Helpers`, `SearchResultsDisplay`, `search.py`). Gate checklist items like icon-view (#285 ✓), keyboard shortcuts (#326 — misfile, not search), sidebar right-click (#354 — misfile), magnifier zoom (#355 — misfile) are either done or belong to other milestones. **The gate cannot be called "pass" while its checklist references misfile issues.** Recommend: update gate body to remove misfile items, then close. |
| **#482** | [Release Gate] 0.0.4 — Wire: Search v2 (Filters + Layouts) | **PARTIAL** | Filters panel exists (`SearchFiltersPanel.swift` — doc_type, file_type, status, sort, search-type picker all rendered). Saved search CRUD exists end-to-end. Split layout is live (see #287/#432 above). Gap: **filters panel is not wired into the main SearchView** — `SearchView.swift` does not reference `SearchFiltersPanel`; the panel is implemented but not surfaced via toolbar/button in the live search flow. Table and icon views are live. Action: keep open until filters panel is reachable from SearchView. |
| **#483** | [Release Gate] 0.0.5 — Wire: Search v3 (Semantic Map + Saved) | **PARTIAL** | Saved searches: fully wired (sidebar renders them, `saveCurrentQuery()` persists them, `SearchView` loads them on appear). Reindex from UI: wired (`reindexLibrary()` → polls stats). Stats panel: shows indexed count in result-count header. Gap: **semantic embedding map** (UMAP/t-SNE 2D projection — the "wow-factor" canvas) does not exist anywhere in Python or Swift. The `.map`/`.realitykit` display mode in `SearchResultsDisplay` is a *relevance-score grid layout* (cards positioned by rank), not a 2D embedding projection. `GET /api/search/views/map` returns geographic markers, not embedding coordinates. Action: keep open — semantic map is genuinely unbuilt. |

---

## Genuinely Open — Not Built

| # | Title | Verdict | Evidence |
|---|---|---|---|
| **#736** | Search v2: hybrid BM25 + BGE-M3 retrieval (RRF) | **OPEN** | The current "hybrid" in `db.py` uses LanceDB cosine similarity + pandas substring scan fused by RRF — not DuckDB FTS + BGE-M3. No `fts` DuckDB extension, no `fastembed`/BGE-M3 model, no `/api/search/hybrid` endpoint. The issue acceptance criteria ("DuckDB FTS index built incrementally on ingest", "BGE-M3 embeddings", "eval harness") are unmet. Note: #875 is a newer restatement of the same scope — see duplicate flag in the earlier audit. |
| **#737** | Search v2.1: alias-aware entity query expansion | **OPEN** | `db.py` `enrich_search_results_with_kg` looks up entity aliases *post-retrieval* for chip display, but does **not** expand the query itself before retrieval. No OR-set expansion, no alias lookup at query time, no entity-scope boost on RRF score. The acceptance criteria ("searching 'Bolívar' returns hits for 'El Libertador'") is unmet. |
| **#738** | Search index: int8 quantization for LanceDB at 100K-doc scale | **OPEN** | LanceDB table uses default float vectors. No SQ8 index, no quantization, no migration script. Older duplicate of #876. |
| **#741** | Search v2.5: local RAG Q&A workflow (Apple Intelligence + hybrid retrieval) | **OPEN** | No `LocalRAGQATool`, no `qa_local.json` workflow, no "Ask" UI surface exists anywhere. Older duplicate of #877. |
| **#875** | Hybrid BM25 + BGE-M3 retrieval (RRF beyond cosine) | **OPEN** | Same as #736 (newer restatement). Not built. |
| **#876** | Int8 quantization for LanceDB embeddings (100K+ doc scale) | **OPEN** | Same as #738 (newer restatement). Not built. |
| **#877** | RAG Q&A workflow (Apple Intelligence + hybrid retrieval) | **OPEN** | Same as #741 (newer restatement). Not built. |
| **#878** | Semantic embedding map visualisation (2D projection of doc cloud) | **OPEN** | No UMAP/t-SNE projection, no 2D canvas, no embedding coordinate endpoint. The existing map-mode in `SearchResultsDisplay` is a static relevance-rank grid. Not built. |

---

## Duplicate Pairs (flag only — no action taken here)

The earlier audit already flagged these. Both pairs are genuinely unbuilt; the newer issue has cleaner scope:

| Older (lower priority) | Newer (canonical) |
|---|---|
| #736 | #875 |
| #738 | #876 |
| #741 | #877 |

Recommendation: when work begins on Search v2/v3, close #736, #738, #741 as "superseded by" #875, #876, #877.

---

## Action Summary

**Close now (3):**
- #285 — search icon/table/map views already enabled by default
- #287 — split layouts already enabled by default
- #432 — no separate backend API needed; existing search routes cover both layouts

**Keep open (12):**
- #424 — backend done, SwiftUI metrics/explanation panel not built
- #481 — most of gate done; update checklist to remove misfile issues, then close
- #482 — filters panel exists but not reachable from SearchView toolbar
- #483 — saved searches + reindex wired; semantic embedding map not built
- #736, #737, #738, #741, #875, #876, #877, #878 — all genuinely unbuilt

---

*Read-only analysis. No code was run, no tests executed, no git changes made.*
