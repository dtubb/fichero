# Fabel Review — Search Surface

**Date:** 2026-07-25
**Branch:** `integration`
**Scope:** milestones 17 "Search View" (24 open), 186 "Search View - Engine" (0 open / 2 closed), 129 "Search View - Saved Searches" (7 open) — 31 open issues total.
**Status:** READ-ONLY review. No source edited, no issue state changed. Deliverable is this plan.

---

## 0. Executive summary

Search is **substantially built** — a real hybrid engine (LanceDB vector + FTS, RRF fusion), a full saved-search CRUD stack, a working SwiftUI search view. The problem is not missing capability. The problem is that the shipped design is the **opposite** of Daniel's stated intent on two of the four points, and silently absent on the other two:

| Intent | Reality | Verdict |
|---|---|---|
| 1. Search results NOT saved by default | **Every Return in the toolbar field mints a persisted SavedSearch** | ❌ Directly contradicted |
| 2. Results render INTO the Library view | Search is a **separate sidebar destination** that replaces the library column | ❌ Directly contradicted |
| 3. Scope selector: folder / library / all libraries | Only a **content-type** scope (documents/entities/claims). No location scope at all | ❌ Missing |
| 4. Default scope is a Settings preference | No search-scope preference exists anywhere in Settings | ❌ Missing |

And the load-bearing sequencing fact: **"all libraries" is not possible today.** The engine is physically partitioned one-DuckDB-and-one-Lance-index per `.fichero` package, and every search request is pinned to a single library by a required HTTP header. Scope option 3 of 3 is blocked on real engine work in milestone 218.

Separately, **~15 of the 24 issues in milestone 17 are not search-UI issues at all** — they are the Historical Text program (#3311–#3326), a coherent 6-step normalization/paleography/calendar plan that was filed into the Search milestone because it touches indexing. It should be split out, or milestone 17 can never be assessed as done.

---

## 1. What exists now

Every claim below is cited to a real symbol.

### 1.1 Engine — the query path

Router mounted at `/api/search` (`fichero-engine/src/fichero/api/main.py:1476`). Explain router mounted separately (`main.py:1538`, `api/routes/search/explain.py:25`).

- **`POST /api/search`** → `api/routes/search/core.py:798 enhanced_search`. (Note: there is no `/api/search/enhanced` path — only the *function* is named that.) An empty query short-circuits to `db.recent_content_document_rows`, i.e. a "recent" browse mode.
- Execution: `core.py:538 _run_content_search_sync` → `db/__init__.py:3944 Database.search`.
- **Hybrid is real**: semantic leg `db/__init__.py:4004 search_vectors` (LanceDB, cosine from L2) + full-text leg `db/__init__.py:4056+` (Lance-native FTS, BM25 corpus-scan fallback).
- **Fusion is Reciprocal Rank Fusion, k=60** — inline `_rrf_add` at `db/__init__.py:4204`, normalised by `rrf_max = 2/(k+1)` at `4238`, plus a `+0.1 * _lexical_score` nudge at `4241`.
- Post-fusion: entity bonus, filters, sort, pagination, highlighting, `enrich_search_results_with_kg`.
- Route-layer post-processing is substantial: `_apply_phrase_and_exclude_filters` (`core.py:313`), `_entity_match_results` (`core.py:571`), `_apply_filename_boost` (`core.py:250`), `_project_pdf_file_hits_to_pages` (`core.py:348`), `_suggest_for_no_results` (`core.py:158`). Query syntax parsed by `fichero/search/query_parser.py parse_query`.

**Request model** — `core.py:707 SearchRequest`: `query, limit(10), include[content|entities|claims], min_score(0.55), search_type(hybrid), filters, sort_by(relevance), sort_direction(desc), offset(0), use_fuzzy_match, highlight_results`.
Implemented filters: `folder_id / doc_type / file_type / date_from / date_to` (`db/__init__.py:~4265-4330`). **`folder_id` already works** — this matters for intent 3.
Accepted-and-ignored: `sort_by="size"` is validated at `core.py:855` but `db/__init__.py:4334-4348` only branches on `relevance`/`date`/`name`. Unknown `filters` keys are silently dropped.

### 1.2 Engine — saved searches

- Model `fichero/models/__init__.py:1297 SavedSearch` (query, is_smart_search, filters, search_type, sort_by, sort_direction, created_by, folder_path, sort_order, timestamps).
- Table `saved_searches`, migrated by `fichero/db/migrations/schema.py:213 migrate_saved_search_table`.
- Rows are **also mirrored into the document tree as smart folders** — `db/__init__.py:2476 _save_saved_search_document`, hydrated at `db/__init__.py:1368`. Saved searches are therefore first-class library nodes, not a side table.
- Full CRUD: `POST/GET/PUT/DELETE /api/search/saved`, plus `/duplicate` and `/reorder` (`core.py:1280–1526`), each wrapped by the audited action layer (`core.py:1989+`).

### 1.3 Engine — the `/api/search/views*` endpoints

`GET /api/search/views`, `/views/table`, `/views/map`, `/views/grid` (`core.py:1652–1885`). **These do not call the search engine at all** — they `db.all(Document)`, substring-filter on name, and hardcode `relevance_score: 1.0` (`core.py:1712`). They are stubs.

### 1.4 SwiftUI — where search lives

- **One global input**: `.searchable(text:placement:.automatic, prompt:"Search")` in `ToolbarSearchableModifier.body` — `fichero/Views/Shell/ContentView/Layout/ContentView+RootLayout.swift:345`, applied to the `NavigationSplitView`. ContentView owns the *only* `.searchable`; LibraryView (`LibraryView.swift:511`), SearchView (`SearchView.swift:67`) and others deliberately refuse to add a second one (duplicate `com.apple.SwiftUI.search` NSToolbar crash, #3163).
- **On submit** — `runToolbarSearch` (`fichero/Views/Shell/ContentView/Actions/ContentView+ActionsImport.swift:35-65`) sets `sidebarMode = .search` and `viewMode = .search(search)`. `ContentView+Navigation.swift:123-131` renders `SearchView`, which **fully replaces the library content column**.
- Unrelated but easily confused: LibraryView's ⌘F is a **client-side filter** over already-loaded rows (`LibraryView.swift:385-394`), never touching the search API.
- `SearchStore` (`fichero/Models/SearchStore.swift`) is `@Observable`, one per library (`LibraryManager.swift:188`).
- Scope selector exists but is **content-type only**: `scopeSelectorBar` (`SearchView.swift:198-243`), `SearchScope = .content/.entities/.claims` (`SearchView+Helpers.swift:7-65`) → API `include[]`. Not persisted (plain `@State`, `SearchView.swift:16`).

### 1.5 SwiftUI — saved searches are the default flow

This is the finding that most directly contradicts intent.

`runToolbarSearch` (`ContentView+ActionsImport.swift:42-48`) calls `savedSearchService.saveSearch(...)` on **every toolbar search submit**, then navigates to the newly created object. Every Return in the global search field mints a persisted SavedSearch row in the sidebar.

There are then **two further** creation paths: an explicit "Save Search" toolbar button (`SearchView.swift:78-90` → `SearchView+Helpers.swift:113-134 saveCurrentQuery()`), and a `"New Search"` placeholder (`SidebarCreationHandlers.swift:11-44`). Sidebar rendering: `SidebarView+UnifiedLibrarySections.swift:37`, rows/reorder `SidebarView+UnifiedRows.swift:126-154`, selection `SidebarView+SelectionHandling.swift:118-121`.

The explicit Save button is redundant *because* saving is already implicit — which is exactly backwards from the intent.

### 1.6 Known defects, confirmed

- **Hardcoded params** — `SearchStore.swift:68-80` passes literal `minScore: 0.0`, `filters: nil`, `offset: 0`, `useFuzzyMatch: false`. Neither `minScore` nor `filters` is even a parameter of `performSearch`, so no caller can supply them. `searchType` comes only from `@SceneStorage("searchType")` (`SearchView.swift:34`, default `"hybrid"`) with **no UI control** — the toolbar menu (`SearchView.swift:94-113`) offers only sortBy/sortDirection. Passing `minScore: 0.0` defeats the backend's 0.55 noise floor.
- **Silent failure** — `db/__init__.py:4408-4412` catches `Exception`, logs a warning, returns `[], 0, {"error": str(e)}`. `enhanced_search` never inspects `search_stats["error"]`, so **a failed search is HTTP 200 with zero results**. Only `EmbeddingSpaceMismatchError` re-raises. The empty-query path has a bare `except: rows = []` at `core.py:815`.
- **Pagination is misleading** — the semantic leg fetches only `limit * 2` candidates and **ignores offset** (`db/__init__.py:4006`) while the FTS leg uses `max(limit*4, offset + limit*2)` (`4061`), so deep pages degrade toward fulltext-only ordering. Worse, `core.py:557` **discards** the db's `total_count` (`results, _total_count, ...`), so `SearchResponse.total_results` is merely the page size; the entity bridge then appends hits *after* pagination (`core.py:914`). No UI pagination exists either — `hasMore` is decoded (`SearchResponse.swift:13,73`) and read by nothing.
- **Dead UI** — `SearchFiltersPanel.swift:4` is 188 lines of complete filter UI (searchType picker, sort, `SearchFilters` bindings). A grep across `fichero/` and `fichero-tests/` returns **exactly one hit: its own declaration.** No instantiation, no preview, no test.
- **Dead endpoints** — `listSearchViews / getTableViewData / getMapViewData / getGridViewData` appear only in generated client code (`fichero-api-client/.build/.../Client.swift:28873, 28937, 29059, 29166`). Zero callers in app or tests.

---

## 2. Multi-library reality check — **NO**

**The engine cannot query across multiple libraries today.**

- **Physical partitioning, not logical.** `db/manager.py:23 DatabaseManager` keys `self._databases: dict[str, Database]` by package path; `get_database()` opens `package_path / "fichero.duckdb"`. Vectors live per-library at `db/__init__.py:585` `self._lance_path = path.parent / "vectors"`. FTS is LanceDB-native and therefore also per-library. **There is no `library_id` column anywhere.**
- **Every request is pinned to one library.** `core.py:797 enhanced_search` depends on `require_library_path` (`api/library_header.py:22`), which returns 400 if `X-Fichero-Library-Path` is absent. `Database.search` (`db/__init__.py:3944`) is an instance method on one connection and **has no library or scope parameter in its signature**.
- **The registry is a list of paths, not a queryable union.** `api/routes/library/registry.py:858 get_global_database` → `global.fichero` holds `KnownLibrary` rows (paths only). `registry.py:892 list_open_libraries` proves N connections *can* be live simultaneously — nothing consumes that set for querying.
- **The Swift side is further along than the engine.** `Models/LibraryManager.swift:67 LibraryReference` already carries `let host: BackendHost` (`Models/BackendHost.swift:10`), and `openLibraries: [LibraryReference]` holds many at once, each with its own `apiClient` / `searchService`. So the per-library-host half of #2573 is effectively done. But `Services/SearchService.swift:39` pins `libraryPath` to `client.currentLibraryPath`, one client per service.
- The `LibraryManager.globalLibraryId` "Global library" is documented as being for cross-library search but is in practice just another ordinary `.fichero` package with its own DB. It is not a union view.

**What "all libraries" actually requires** (this is engine work, not a query tweak):
1. A fan-out endpoint (e.g. `POST /api/search/all`) that takes no single-library header, enumerates open/known library paths, and calls `Database.search` per package concurrently.
2. **Score normalisation across corpora.** Each Lance FTS index has its own BM25 corpus statistics, and RRF ranks are computed per-corpus — raw scores from different libraries are *not* comparable. Naive merge will systematically favour whichever library is smallest. This is the hard part.
3. `library_id` / `library_path` provenance stamped on every `SearchResult` so the UI can attribute and route each hit.
4. Per-path authorization: `_is_allowed_library_path` and security-scoped grants (`libraryIdsAwaitingGrant`) must be validated for each fanned-out package, not once for the request.
5. Swift: a search coordinator not bound to a single `FicheroClient`, routing remote libraries through `BackendHost`.

**Sequencing consequence:** ship scope options 1 and 2 (current folder / current library) now — `folder_id` filtering already works in the engine. Ship option 3 disabled-with-reason, or omit it from the picker, until milestone 218 lands the fan-out.

---

## 3. Gap analysis against the four intents

### Intent 1 — results are not saved by default
**Contradicted at `ContentView+ActionsImport.swift:42-48`.** Searching is currently an artifact-creating act: every Return persists a row, mirrored into the document tree as a smart folder (`db/__init__.py:2476`). The user cannot search without littering the sidebar. This also cuts against `CONSTITUTION.md:64` — "the researcher stays in charge" — since the app is deciding, on the user's behalf, that a throwaway lookup deserves to become a permanent library object. The explicit "Save Search" button is dead weight given implicit save, and three separate creation paths exist.

The fix is small in code and large in consequence: `runToolbarSearch` should navigate to a *transient* result state, and saving should happen only via the explicit button. Note the engine needs no change — the CRUD is fine, it is simply being called too eagerly. Also note the sidebar is the *right* home for genuinely saved searches, so this is a call-site change, not a teardown.

### Intent 2 — results render into the Library view
**Contradicted at `ContentView+ActionsImport.swift:35-65` + `ContentView+Navigation.swift:123-131`.** Search sets `sidebarMode = .search` and swaps in `SearchView`, a parallel presentation stack (`SearchResultsDisplay.swift`) that duplicates what Library already does — and does it *worse*, since it has no icon/list/column/table modes.

This aligns with the existing "Views IA" memory (search = Library) and with #3534's "adopt shared chrome". The target is: the global field drives the Library view's contents; results are library nodes rendered by the existing Library view modes; the scope/filter controls live in the shared bottom mini-toolbar. That deletes `SearchView` as a destination and probably deletes `SearchResultsDisplay` too.

Caveat to design around: entity and claim results are not documents, so the Library view needs a result-kind concept (documents / entities / claims) — #3534 already anticipates this as optional tabs.

### Intent 3 — scope selector (folder / library / all libraries)
**Missing.** The existing `scopeSelectorBar` is content-type, not location, and the two concepts will collide in the UI if not carefully separated. Location scope needs a new control. Engine support: "current folder" = existing `folder_id` filter ✅; "current library" = today's default behaviour ✅; "all libraries" = blocked ❌.

### Intent 4 — default scope as a Settings preference
**Missing.** The only search-adjacent Settings row is `Toggle("Auto-create search embeddings")` (`Views/Settings/General/GeneralSettingsView.swift:78`). Finder's model is a single popup under a "When performing a search" label; Fichero should mirror that exactly — one preference, not a per-search toggle pile, consistent with the ON-or-OFF UX rule. The per-search selector then *starts* from the preference and can be overridden for the current search without persisting.

---

## 4. Triage of the 31 open issues

### Milestone 17 — Search View (24 open)

**The Historical Text cluster — 14 issues that do not belong in this milestone.**

| # | Title | Verdict |
|---|---|---|
| 3311 | 📋 Historical Text — strategy + open questions | **REWRITE** → move to a new "Historical Text" milestone. Not a search-UI issue. |
| 3319 | 📋 Fabel Deep Review — Historical Text (grounded plan) | **REWRITE** → same move. This is a good, verified plan; it just isn't Search View. |
| 3312 | diplomatic_text + normalized_text dual-field model | **REWRITE** → move. |
| 3313 | Fuzzy search + entity variant merging | **KEEP but move** → genuinely search-relevant (`use_fuzzy_match` is a no-op today, see #3321), but belongs with its cluster. |
| 3314 | Historical calendars: raw string + JDN | **REWRITE** → move. Overlaps #3309 (document date). |
| 3315 | Unicode/paleography rendering: fonts | **REWRITE** → move. Rendering, not search. |
| 3316 | Translation of entities/artifacts/documents | **REWRITE** → move. |
| 3320 | textnorm foundation: NFC + ftfy (1/6) | **REWRITE** → move. Currently `status:blocked`. |
| 3321 | normalized_content column + implement no-op use_fuzzy_match (2/6) | **KEEP but move** → this one *does* fix a real accepted-and-ignored search param. |
| 3322 | histdate core: JDN columns + sort/filter (3/6) | **REWRITE** → move; merge-check against #3309. |
| 3323 | cross-script entity variant candidates (4/6) | **REWRITE** → move. |
| 3324 | paleography fonts + diplomatic render (5/6) | **REWRITE** → move. |
| 3325 | translation: embed with scope, artifact.translate (6/6) | **REWRITE** → move. |
| 3326 | Transliteration / romanization across scripts | **REWRITE** → move. |

Recommendation: create milestone **"Historical Text"** and move all 14. Milestone 17 cannot be reasoned about while 58% of it is a different program. No content change to the issues themselves is needed — they are well-grounded.

**Stale release gates.**

| # | Title | Verdict |
|---|---|---|
| 481 | [Release Gate] 0.0.3 — Wire: Search v1 | **CLOSE-AS-WRONG** — 0.0.x gate scheme is retired (releases are now dated, per the dated-releases policy). Its commands reference `fichero-api/src` and `fichero-swiftui/`, directories that no longer exist (now `fichero-engine/` and `fichero/`). The functionality it gates (type → results → click → open) works today. |
| 482 | [Release Gate] 0.0.4 — Wire: Search v2 (Filters + Layouts) | **CLOSE-AS-WRONG** — same stale scheme. Its actual content (filters panel wired up) is better tracked by #3245/#3255 and the new filters issue below. |
| 483 | [Release Gate] 0.0.5 — Wire: Search v3 (Semantic Map + Saved) | **CLOSE-AS-WRONG** — same. "Saved" half is now *contra*-intent; map half survives as #878. |

**Real search issues.**

| # | Title | Verdict |
|---|---|---|
| 424 | 0.0.4 — Search Explanation and Metrics Visibility Panel | **ALREADY-DONE (backend).** All four acceptance endpoints exist: `POST /api/search/explain`, `GET /api/search/explain/{query}`, `GET /api/search/modes`, `GET /api/search/metrics` — `api/routes/search/explain.py:291, 360, 383, 397`. The body scopes it to "Backend Work" only. Verify the test suite, then close; file a separate UI issue if the *panel* is still wanted. |
| 878 | Semantic embedding map visualisation (2D projection) | **KEEP.** Not done. `GET /api/search/views/map` (`core.py:1735`) is a stub that returns all documents with `relevance_score: 1.0` and has zero FE callers. Body itself flags it "wow-factor, not core search" — keep, deprioritise below the intent work. |
| 1782 | Hybrid ranking — boost exact/keyword above semantic | **KEEP, partially addressed.** RRF + a `+0.1 * _lexical_score` nudge (`db/__init__.py:4241`) and `_apply_filename_boost` (`core.py:250`) now exist. Re-test the original repro ('andagueda' → 'Andagoya') and either close or retune. Cheap to resolve. |
| 1812 | Corpus-linguistics features (KWIC, collocations, n-grams, keyness) | **KEEP.** Genuine unbuilt feature, independent of the IA work. Large. |
| 1824 | Unify retrieval as ONE semantic index (8 modes) | **KEEP as EPIC.** North-star vision issue, correctly labelled as such in its own body. Should not block anything. |
| 1833 | Improve embedding quality: passage chunking + KG-fusion | **KEEP.** Real and high-value — whole-page embedding averages signal, which is a root cause of #1782-class complaints. Its step 1 (e5 prefixes, #1795) should be checked for completion. |
| 3534 | Search adopts shared chrome; filters → bottom mini-toolbar | **REWRITE.** Closest existing issue to intent 2, but it still assumes Search remains its own surface with its own chrome. Rewrite as "Search results render into the Library view" (see proposed issue S2). Keep the mini-toolbar/result-kind-tabs detail. |

### Milestone 129 — Saved Searches (7 open)

| # | Title | Verdict |
|---|---|---|
| 3245 | App hardcodes minScore=0.0 / searchType=hybrid / filters=nil | **KEEP — CONFIRMED.** `SearchStore.swift:68-80`. `minScore: 0.0` defeats the backend's 0.55 noise floor (#1054 regression). Highest-value small fix in the set. |
| 3246 | Failures silent end-to-end; sort_by=size unimplemented | **KEEP — CONFIRMED.** `db/__init__.py:4408-4412` returns 200+empty on exception; `core.py:815` has a bare `except`. Directly violates the prefer-raise-over-silent-fallback and check-the-result-of-every-op rules. Should be split: (a) surface errors, (b) implement-or-reject `sort_by=size`. |
| 3247 | Saved-search settings don't round-trip | **REWRITE — CONFIRMED but now the wrong frame.** Both construction sites (`ContentView+ActionsImport.swift:51-58`, `SidebarCreationHandlers.swift:31-38`) omit searchType/sortBy/sortDirection/filters; `SearchView.swift:115-145` restores three of them but never `filters`; scopes are never persisted. All true — but the *first* fix is to stop auto-saving at all (proposed S1). Rewrite as "saved searches round-trip their full settings" scoped to the surviving explicit-save path, and add scope to the payload. |
| 3249 | changeToken is dead plumbing | **ALREADY-DONE.** Observed at `SearchView.swift:179` (`.onChange(of: searchStore.changeToken) { performSearch() }`). One observer, but live. Close — but re-verify after S2 moves results into Library, since that observer lives on the view being deleted. |
| 3250 | No pagination in UI; semantic leg caps at limit*2 | **KEEP — CONFIRMED and worse than described.** Beyond the `limit*2` cap that ignores offset (`db/__init__.py:4006`), `core.py:557` discards the db's `total_count`, so `total_results` is just the page size, and the entity bridge appends hits after pagination (`core.py:914`). |
| 3255 | Dead/duplicated surface (FiltersPanel, /views*, dup CRUD) | **REWRITE — one-third fixed.** The duplicated saved-search CRUD was Swift-side and was removed in commit `6dd5dd9b3`; the engine never had two services. Still true: `SearchFiltersPanel.swift` has exactly one reference (its own declaration), and `/api/search/views*` have zero FE callers. Rewrite as a scoped deletion issue (S7). |
| 3309 | Document date attribute + date extraction → sort by date | **KEEP, but move to Library milestone.** This is a Document-model and library-sort concern that happens to also affect search sort. Cross-check against #3314/#3322 (historical calendars / JDN) — there is real overlap and these three should be reconciled before any is worked. |

**Milestone 186 (Search View - Engine)** has 0 open issues; both closed items (#3718 Lance FTS schema drift, #3768 stale route contracts) are real fixes. The milestone is a reasonable home for the new engine-side issues below.

---

## 5. Proposed issue set

Do **not** file these yet — listed for the manager.

**S1 — Search does not create a saved search; saving becomes explicit**
*Milestone 17.* `runToolbarSearch` (`ContentView+ActionsImport.swift:42-48`) calls `savedSearchService.saveSearch(...)` on every submit, so each Return in the global field mints a persisted SavedSearch mirrored into the document tree as a smart folder. Change submit to drive a transient result state with no persistence. Saving becomes the explicit toolbar action only (`SearchView+Helpers.swift:113-134`), which stops being redundant once implicit save is gone. Reconcile the third creation path (`SidebarCreationHandlers.swift:11-44 createNewSearch`) — a "New Search" placeholder is defensible only if it is an explicitly-authored smart folder. No engine change; the CRUD is correct, it is merely called too eagerly. Add a regression test asserting that N searches create zero SavedSearch rows.

**S2 — Search results render into the Library view; retire SearchView as a destination**
*Milestone 17. Supersedes #3534.* Today submit sets `sidebarMode = .search` / `viewMode = .search(search)` (`ContentView+ActionsImport.swift:35-65`) and `ContentView+Navigation.swift:123-131` swaps in `SearchView`, a parallel stack that duplicates the Library view with fewer capabilities (no icon/list/column/table modes). Make the global field drive the Library view's contents so results are library nodes rendered by existing view modes, with scope/filter controls in the shared bottom mini-toolbar. Needs a result-kind concept for entity/claim hits, which are not documents (#3534's optional tabs). Expect `SearchView` and `SearchResultsDisplay` to be deleted; re-verify the `changeToken` observer (`SearchView.swift:179`) survives the move. Keep the single `.searchable` in ContentView — do not add a second (#3163).

**S3 — Location scope selector: current folder / current library**
*Milestone 17. Depends on S2.* Add a location scope control, distinct from the existing content-type scope (`SearchView.swift:198-243`, `.content/.entities/.claims`) which must not be conflated with it. "Current library" is today's behaviour; "current folder" maps to the already-implemented `folder_id` filter (`db/__init__.py:~4265`), so no engine work is required. Ship "All libraries" only when S6 lands — until then omit it rather than showing a disabled control.

**S4 — Settings preference: default search scope**
*Milestone 17 (or Settings milestone). Depends on S3.* Add a single "When performing a search" popup in Settings, mirroring Finder, beside the existing `Toggle("Auto-create search embeddings")` (`Views/Settings/General/GeneralSettingsView.swift:78`). One preference, not a toggle pile. The per-search selector initialises from it and may be overridden for the current search without persisting the override.

**S5 — Search failures surface as errors instead of empty results**
*Milestone 186.* `db/__init__.py:4408-4412` catches `Exception`, logs a warning and returns `[], 0, {"error": ...}`; `enhanced_search` never inspects `search_stats["error"]`, so a failed search is HTTP 200 with zero results — indistinguishable from a genuine miss. `core.py:815` has the same bare-`except` shape on the empty-query path. Raise a typed error and surface it; render `searchError` in the UI. Split `sort_by="size"` out: it is validated at `core.py:855` but unimplemented at `db/__init__.py:4334-4348` — either implement it or reject it at the schema. Covers #3246.

**S6 — Engine: cross-library search fan-out**
*Milestone 218.* Prerequisite for "all libraries" scope. Add an endpoint that takes no single-library header, enumerates known/open library paths (`registry.py:858/892`), and fans out `Database.search` concurrently. The hard part is score normalisation: each Lance FTS index has its own BM25 corpus statistics and RRF ranks are per-corpus, so raw scores are not comparable and a naive merge favours the smallest library. Also required: `library_path` provenance on every `SearchResult`, and per-path authorization (`_is_allowed_library_path` + security-scoped grants) validated per fanned-out package rather than once per request. Swift needs a coordinator over `LibraryManager.openLibraries` rather than one `SearchService` per client (`SearchService.swift:39`). Note the per-library-host half of #2573 is already done (`LibraryManager.swift:67`).

**S7 — Delete the dead search surface**
*Milestone 129.* Scoped deletion, replacing the still-valid two-thirds of #3255. Remove `SearchFiltersPanel.swift` (188 lines; grep across `fichero/` and `fichero-tests/` returns only its own declaration) — its function is superseded by the S2 mini-toolbar. Remove or implement `/api/search/views`, `/views/table`, `/views/map`, `/views/grid` (`core.py:1652-1885`): they never call the search engine, they `db.all(Document)` and hardcode `relevance_score: 1.0`, and they have zero FE callers. If #878's map is wanted, `/views/map` should be rebuilt properly rather than left as a stub. The duplicated Swift CRUD half of #3255 is already fixed (`6dd5dd9b3`).

**S8 — Wire real search parameters through the app**
*Milestone 129.* `SearchStore.swift:68-80` hardcodes `minScore: 0.0`, `filters: nil`, `offset: 0`, `useFuzzyMatch: false`; `minScore` and `filters` are not even parameters of `performSearch`. `minScore: 0.0` defeats the backend's 0.55 noise floor (#1054 regression). `searchType` is reachable only via `@SceneStorage("searchType")` with no UI control. Land after S2 so filters arrive through the shared mini-toolbar rather than reviving the dead panel. Covers #3245.

**S9 — Honest pagination and result counts**
*Milestone 186.* The semantic leg fetches `limit * 2` candidates and ignores offset (`db/__init__.py:4006`) while FTS uses `max(limit*4, offset + limit*2)` (`4061`), so deep pages silently degrade to fulltext-only ordering. `core.py:557` discards the db's `total_count`, making `total_results` merely the page size, and the entity bridge appends hits after pagination (`core.py:914`). Fix the counts, make the semantic leg offset-aware, then add load-more in the Library results view — `hasMore` is already decoded (`SearchResponse.swift:13,73`) and read by nothing. Covers #3250.

---

## 6. Sequencing

**Phase 0 — stop contradicting the intent (small, unblocks everything).**
S1 (no implicit save). One call site. Do this first: it is the largest intent violation and the cheapest fix, and it prevents S2 from being designed around a persistence model that is going away.

**Phase 1 — correctness, in parallel with Phase 0.**
S5 (surface errors) and S9 (honest counts) are engine-side and independent of the IA work. They also make Phase 2 debuggable — right now a broken search and an empty search look identical.

**Phase 2 — the structural move.**
S2 (results into Library). This is the big one and everything else in the UI waits on it. It deletes a surface rather than adding one. Milestone-17 issues that assume a standalone Search surface (#3534) must be rewritten before this starts, not during.

**Phase 3 — scope, on top of S2.**
S3 (folder / library selector) then S4 (Settings default). Both cheap once S2 lands; both engine-complete already via `folder_id`.

**Phase 4 — cleanup and quality, unordered.**
S7 (delete dead surface), S8 (real parameters — after S2 so filters land in the right chrome), #1782 re-test, #1833 (chunking + KG fusion), #1812 (corpus linguistics).

**Blocked on multi-library.**
S6, and therefore the "all libraries" option in S3. Do not put "All libraries" in the picker before S6 lands. S6 is a genuine engine project — the score-normalisation problem is not incidental — and belongs to milestone 218, sequenced against the rest of the sharing work rather than against the search UI.

**Milestone hygiene, do before anything else.**
Move the 14 Historical Text issues (#3311–#3326) out of milestone 17 into their own milestone, and close the three stale 0.0.x release gates (#481/#482/#483). Verify and close #424 (backend already done) and #3249 (already fixed). That takes milestone 17 from 24 open to 5 real search issues and makes the milestone assessable.

---

## 7. Vision additions (2026-07-27, Daniel — V-series #4114–#4120)

Status when these landed: S1/S5/S9/S7 done; S2 fully landed (slices A+B+C,
ed2fbd8c1 + e73231265) — search is ONE surface, the toolbar field rendering
into the Library view, saved searches run transient. These additions build on
that unification; none of them reintroduce a separate search mode.

**V1 #4114 — Smart folders.** Saved searches behave like Finder smart
folders: drag into sidebar folders, alias them, one-click "all mentions of
<entity>" searches from an entity's context menu. Pure organization on top of
the stored query — the transient pipeline stays the only executor.

**V2 #4115 — Graph leg + chat tooling.** Add KG traversal (entity →
statements → documents) as a retrieval leg beside vector+FTS, and expose the
whole search as ONE audited action-layer tool the chat/agent system calls
(chat_tools.py exists unwired; #1848). Search is chat's retrieval backbone —
one implementation, two front doors.

**V3 #4116 — LLM query compilation.** Sentence/question-like queries drop
down to an LLM (langchain, local-first MLX) that constructs the advanced
search: entities, date ranges, field filters, semantic query. Keyword queries
keep the fast path. The compiled query is always visible and editable
(AI = instrument: show what was searched).

**V4 #4117 — AI-first field + chat-the-search.** The search field is
plain-language by DEFAULT with a drop-down to switch to keyword/advanced
(one control, not a pile of toggles). Running a search can also open a chat
pane scoped to that search — conversational refinement over the same result
context. Depends on V2 (tool) + V3 (compilation).

**V5 #4118 — Unified object search.** Results span documents, images,
artifacts, entities, and KVO/hermeneutic/ontological statements. Engine:
extend the include= legs with honest per-type counts. UI: typed rows/cards in
the existing Library view modes; type filtering; sortable. Presentations are
view modes, never new surfaces.

**V6 #4119 — Real, graphical relevance.** Fix score calibration (the
everything-is-71% problem; same normalisation work as S6 #4110) and render
relevance as a DEVONthink-style graphic, not a percentage number.

**V7 #4120 — Related Documents inspector.** Automatic see-also for the open
document (embedding neighbors + entity-overlap boost) as a new Inspector tab
or a toggleable bottom-right section. Needs a related-documents endpoint;
honest empty state when unindexed.

**Sequencing against the S-series.** S3/S4 (scope + default) stay next — they
are cheap and V4's drop-down will sit beside the scope control, so land the
control chrome once. Then S8 (real params through the mini-toolbar) which V3
extends. V7 is independent of everything and can interleave. V2→V3→V4 is the
dependency chain for the AI path; V6 rides with S6's normalisation work.
V1 and V5 are independent engine+UI slices.

### Status update 2026-07-27 (later)

DONE: S1–S5, S7–S9 all landed; #4106/#4107/#4108/#4111/#4112/#4120 closed.
V7 (#4120) shipped as the Related inspector facet. V2's tool half shipped:
`search.query` is the registry's FIRST read_only action (5d1e673a2) — the
chat tool loop previously had ZERO tools. Endpoint cleanup: 19 dead paths
deleted, /api/migrations stutter fixed (1a79445bf).

**V2 graph-leg design (next engine slice).** `GraphAwareRetriever._augment_with_kg`
already does claim-seeded, hop-limited entity↔claim expansion for chat/researcher
context. The search-grid leg reuses those seams, direction REVERSED:

1. Entity leg of /api/search already returns entity hits (include=entities).
2. New: for the top-N entity hits (N≈5), pull
   `db.knowledge_claim_source_document_ids_for_entity(eid)` (the seam #4120's
   related-docs uses), score each doc as
   `entity_similarity × 0.8^hop` (1 hop only to start), and merge into the
   content results via the SAME RRF fusion, tagged `via: "graph"` so the UI
   can badge graph-found hits with provenance.
3. Honest counts: graph-leg hits join BEFORE pagination (the S9 lesson —
   never append after the page is cut).
4. Exposed through the same one pipeline: /api/search, search.query,
   and therefore chat, all get it at once.

**V3 (#4116) design sketch.** Compiler in the engine
(`fichero/retrieval/query_compiler.py`): heuristic gate (≥5 words OR
question-mark OR question-word start) → langchain structured-output call
(local-first MLX per llm-routing policy) emitting a
`CompiledQuery{semantic_query, entities[], date_from/to, doc_types[],
filters}` → mapped onto SearchRequest. The compiled query is RETURNED in
SearchResponse (new optional `compiled_query` field) so the UI shows and
lets the user edit what was actually searched (AI = instrument). Keyword-ish
queries skip the LLM entirely — no latency tax on 'cacao'.

**Held for Daniel:** the 7 /api/agents/write* + /api/policies/orchestration*
endpoints (real logic, process-memory state, overlaps #1848) — delete or
DB-back before wiring.

### Status update 2026-07-27 (end of day)

CLOSED today: #4105–#4109, #4111, #4112, #4115, #4116, #4120, #4122, #4125
(+ legacy #3245/#3246/#3249/#3250/#3255/#3534/#424/#481–#483). V4116 is
fully done: engine compiler + UI (compile=true on explicit submits, compiled
query + failures always rendered in the results bar).

PARTIAL: #4114 (entity → 'Save Mentions as Smart Search' one-click landed
e8441c3aa; remaining: verify/fix saved-search drag-into-folder + aliases).
#4123 (sidebar + grid drag out = real file + RTF landed; remaining:
single-page PDF export, markdown flavor). #4124 (sidebar classifier +
grid/list per-cell drop targets landed; remaining: Table-view cells).
#4121 (badges → glyphs #4122 done; View-menu first cut + nested folder
creation + row New Folder landed; the PARITY UNIFICATION + Go menu +
Settings migration await Daniel's sign-off — full audit in the issue).

REMAINING search queue: #4117 (AI-first drop-down + chat-the-search pane —
next big design-led slice), #4118 (unified object results), #4119
(score calibration — rides S6), S6 #4110 (cross-library, engine project).

Non-search bug queue for next session: #4121 unification (post sign-off),
#4123/#4124 leftovers, more sidebar/DnD bugs from Daniel.
