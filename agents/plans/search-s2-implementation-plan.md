# S2 Implementation Plan — Search results render INTO the Library view (#4106)

Written 2026-07-26 ~23:15 by the integrator session, after S1 (#4105 already
done via #4086), S5 (#4109 engine half, commit 90a55b885), S9 (#4113 engine
half, commit 488e70551). Blocked only on xcodebuild being busy with the
2026.07.26 release; implement as soon as it frees.

## Verified seams (all read this session)

- `ToolbarSearchRouter.route(for:)` — ContentView+ActionsImport.swift:188.
  Currently returns `(sidebarMode: .search, viewMode: .search(nil))`.
- `.search` render case — ContentView+Navigation.swift:123-131 → `SearchView(...)`.
- `.library` render case — ContentView+Navigation.swift:~60-122 → LibraryView
  with `folderId:`, `selection:`, `displayMode:` etc. LibraryView filters/sorts
  whatever document array it receives (`recomputeFiltered`,
  LibraryView+FilterAndBatch.swift:19).
- `SearchStore` — one per library (LibraryManager.swift:188), @Observable,
  `performSearch` + `results: [SearchResult]` + `changeToken`.
- Engine now returns honest `total_results`/`has_more` (#4113) and 500s on
  failure (#4109) — UI must render `searchError` + a load-more affordance.

## Design (minimal, iterate-never-replace)

1. **Transient search state on ContentView**: `@State var activeSearchQuery:
   String?`. `runToolbarSearch` sets it (+ keeps `sidebarMode`/`viewMode` at
   `.library`), calls the library's `searchStore.performSearch(query)`.
   Clearing the toolbar field (or Escape) nils it. Do NOT touch
   `viewMode = .search` — that case dies at the end.
2. **Result resolution**: map `searchStore.results` → `[Document]` by id
   against `documentStore.currentDocuments` + `documentStore.collections`;
   fetch misses via `documentService.getDocument(id:)` (check how
   SearchView/SearchResultsDisplay resolved docs — reuse that helper if it
   exists rather than writing a new one).
3. **LibraryView input swap**: in the `.library` case, when
   `activeSearchQuery != nil`, hand LibraryView the resolved hit array
   (relevance order) instead of the folder listing, `folderId: nil`. All view
   modes (icons/list/columns/table) come free. Consider a small "N results
   for 'q' — total_results/has_more" header + Load More button (S9 UI half).
4. **Saved-search selection** routes through the SAME path: selecting a saved
   search sets `activeSearchQuery = saved.query` (+ its stored
   searchType/sort when S8 lands). Then `.search` viewMode case, SearchView,
   SearchResultsDisplay, and `SidebarMode.search` are deleted.
5. **Search error**: render `searchStore.error` (engine 500 detail) as an
   inline banner in the results header — never an empty grid.
6. **Guards**: ContentView keeps the ONE `.searchable`
   (ToolbarSearchableModifier) — never add a second (#3163). The
   changeToken observer must move from SearchView:179 into the new results
   pipeline (re-verify per closed #3249).

## Test plan

- ToolbarSearchRoutingTests: update — route now keeps `.library` and sets the
  transient query (the no-SavedSearch regression guard stays).
- New: resolving hits → Document array preserves relevance order; misses are
  fetched; error surfaces; clearing the query restores the folder listing.
- Source-contract updates: tests referencing SearchView/SearchResultsDisplay
  (SearchResultsDisplayTests, SceneStorageUsageTests scene keys, AdaptiveShell
  file lists) must be repointed or retired WITH the deletion, like the
  breadcrumb removal was (commit 058af97ac shows the pattern).
- Full FicheroTests suite + `scripts/verify_all.sh --standard` before commit.

## After S2

S3 (#4107 location scope: folder = existing folder_id filter), S4 (#4108
Settings default scope), S8 (#4112 real params through the mini-toolbar),
S7 (#4111 delete SearchFiltersPanel + /api/search/views*).
