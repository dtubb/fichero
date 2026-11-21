# Search — Design Spec (#TBD)

> Milestone: search-correct-and-fast (the 2026-11-20 review's fixes, #6780-#6794 and #6867, in this spec's Build order); the older issues sit in milestone `search`
> Manual: TBD — the user manual's Library section needs "Searching your library": one field,
> top right, with Ask/Keyword scopes and a Hybrid/Semantic/Full-Text method in the results
> Options menu; results are ordinary library rows you can sort, filter, and open like any other.

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval.** Legacy milestones "Search View" (#17),
> "Search View - Engine" (#186), and "Search View - Saved Searches" (#129) accumulated 12 open
> issues with no spec anchoring any of them, plus #4236 (a live bug) waiting on this spec from
> the `library-view-modes.md` fold. This is Pass 1: the spec these issues never got, written
> against the code as it stands today. Search here turns out to be one of the more mature,
> heavily tested surfaces in the app — this spec states that plainly rather than assuming the
> milestones' age means the work is undone.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, unproven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts the intent (needs an issue).
>
> **Path and folder**: `ui/search.md`, alongside `library-view-modes.md`, `reader-view.md`,
> `panes-workspaces.md`, `modes-to-panes.md` — search is a Library-surface feature (its own
> field, its own results, its own options), the same shape as those specs, not a separate
> subsystem needing its own top-level folder the way `kg/`, `transport/`, or `harness/` group
> genuinely distinct concerns.
>
> **Territory this spec does NOT own — read first, cited not restated:**
> - `library-view-modes.md` — how search HITS render once they exist: `library.search.spatial-
>   modes-share-one-projection`, `library.search.columns-show-hits-not-browse-root` (search
>   results become the rows in every Library view mode). This spec owns producing the hits and
>   the field/scope/method UI; that spec owns what a view mode does with them.
> - `reader-view.md` — the passage-highlight channel search first built (`reader.passage-
>   channel.has-a-second-producer`): search was the ORIGINAL writer of `ReaderPassageFocus`,
>   later reused by claim-following. This spec owns producing the search hit; that spec owns
>   the Reader's own highlight rendering.
> - `kg-tables.md` — the per-table filter that intersects with search
>   (`kg.tables.filter.combines-with-search`, tested `ClaimsFilterTests`): a KG table's own
>   filter text and the shared search query both narrow the same rows. This spec does not
>   restate that table-level mechanic.
> - `historical-text-normalization.md` — fuzzy/typo-tolerant matching is genuinely implemented
>   there (`histnorm.fuzzy-search`, OK); the normalized-content column and a real full-text
>   index remain that spec's own GAP (`histnorm.dual-field-model-not-built`). Do NOT duplicate
>   either claim here. **#3309** (document date → sortable in search views) also belongs there
>   (`histnorm.dates.jdn-core`, `.search-and-sort`) — redirected, not folded into this spec.
> - **The ratified ruling this spec assumes throughout**: there is no top-level Knowledge Graph
>   browser (`modes-to-panes.md`'s "KG graph/map = Library view modes" ruling) — search results,
>   like KG views, are Library view modes, not a separate surface with its own navigation model.

## Intent (the design)

One search field, always available, in the same place a Mac user expects one — not a bespoke
control that behaves like nothing else in the app. A query can be a person, place, or date
prefix, a phrase, or a question; the app decides whether that's a lookup or something to hand to
chat, and always shows what it actually searched, never a black box. Results are not a separate
screen — they are the Library's own rows, sortable and browsable in every view mode, with
documents, entities, claims, and artifacts as peers, not a document-only search with metadata
bolted on. Every result states honestly how it was found (literal match, semantic neighbor, or
graph inference) and never dresses up a weak guess as a confident answer. A result's job is to
get the user to the exact passage or region that matched, not just the containing document.

## Grounding: what exists today (verified against HEAD, 2026-09-19)

**The field and its scopes are built as the app's ONE native toolbar search** —
`ContentView+ToolbarSearch.swift`'s own comment states the history directly: "The hand-rolled
magnifier+TextField lozenge (#4604) is gone... use the default one." The SYSTEM toolbar search
item (`.searchable` + `.searchToolbarBehavior(.minimize)` on iOS) carries the field, collapsing
to a magnifier and expanding on click (Mail-style); Ask/Keyword survive as native
`.searchScopes`, shown only while the field is presented; the Hybrid/Semantic/Full-Text
retrieval METHOD lives in the results bar's own Options menu, a separate control from the
Ask/Keyword scope. This is the single `.searchable` registration in the window, guarded against
the app's own duplicate-identifier crash class by `ToolbarDuplicateRegistrationGuardTests`.

**The engine's search response is genuinely a four-leg, honesty-first contract**
(`api/routes/search/core.py`'s `enhanced_search`, `SearchResponse`): `results` (documents),
`entity_hits`, `claim_hits` (the exact `SearchClaimHit` type this spec's own brief named,
carrying `provenance_kind`), and `artifact_hits` — four peer legs, not a document search with
sidebars. `legs: dict[str, int]` reports which retrievers ran and how many hits each contributed
("semantic": n, "fulltext": n, "kg": n); `weak_semantic_only` flags when the only evidence is a
weak cosine neighbor with no literal or graph support, specifically so the UI can say "no
literal matches; showing closest pages" instead of dressing a fused rank up as confidence;
`compiled_query`/`compilation_error` return what an LLM-assisted query compilation actually
produced (or why it failed), never hidden — the AI-as-instrument north star applied to search
itself. `rendered_total` vs `total_results` are two deliberately different fields (documented in
the model itself, #4403/#4113) so a UI header can answer "how many things am I looking at?"
without conflating it with pre-pagination counts.

**Search hits become ordinary Library rows** — `LibraryView`, `LibraryToolbarState`, and
`DocumentStore` all treat a "transient search" as the active row set (`documents` under a
transient search IS the hit set, per `LibraryView+Insets.swift`'s own comment), not a separate
results screen. Pinned: `SearchResultsReachEveryViewModeTests`
(`testDatasetRenderersScopeTheirQueryToTheSearchHits`,
`testAnEmptyHitScopeMatchesNothingRatherThanEverything`,
`testTheClientSendsTheHitScopeThrough`, `testSubmittingASearchReleasesAPinnedLibraryScope`).

**Saved searches are a full audited action**, not a bolt-on: `save_search`/`update`/`delete`/
`reorder`/`duplicate` all route through the action registry with undo/redo. Pinned:
`test_routes_savedsearch_actions.py`'s `TestSavedSearchSaveAction` (audit-emit,
undo-then-redo-recreates), `TestSavedSearchUpdateAction` (undo-then-redo-reapplies). Mounted in
the sidebar (`SidebarView.swift` references `SavedSearch`).

**A related-documents endpoint exists**: `GET /documents/{doc_id}/related`
(`api/routes/document/documents.py:1642`), two merged legs (entity co-occurrence + semantic
similarity, `#4120`), each leg degrading independently on failure (logged, never a 500 —
"relatedness is best-effort context"). A `DocumentInspectorRelatedTab.swift` mounts related
documents in the Inspector — a different surface than #4606's own ask (column-view surfacing),
but the underlying capability and an app surface for it both exist.

**Embedding-failure honesty (#4395) is substantially fixed, not merely claimed**: `Database.
embed()`'s exception handler (`db/__init__.py:~4774-4788`) now returns an `EmbedOutcome` object
(`embedded`, `reason`, `document_id`, `error`) instead of a bare bool — the object's own comment
cites #4395 directly: "the bool alone cannot distinguish 'this document has no embeddable text'
... from 'the embedding model could not be loaded'... The outcome now carries its reason so a
caller can count and report causes." The import summary reads `last_embed_outcome` and reports
an `embedded` count (`ingest.py:~843,882`). **Not independently re-verified this pass**: whether
an infrastructure-level failure (the model itself unavailable) actually STOPS the import loudly,
versus continuing to embed-and-count silently document-by-document — the issue's second ask
("fail loudly on infrastructure failure, don't treat it as partial success") needs a closer
read of the calling loop before it can be called fully resolved.

## Behaviors

### A. The field, scopes, and method

- `search.native-toolbar-field` — **[OK]** the app's ONE search field is the system toolbar
  search item, not a hand-rolled control; the old lozenge (the EPIC's own diagnosis) is gone.
  Pinned: `ToolbarSearchRegistrationTests`, `ToolbarDuplicateRegistrationGuardTests`. Escape
  clears the field and exits the transient search presentation, the same gesture every other
  transient state in the app answers to, replacing a dedicated "Done" button — verified by
  direct code read (`ContentView+ToolbarSearch.swift`'s `SearchEscapeDismiss` modifier), no
  dedicated pinning test found for this specific gesture.
- `search.always-visible` — **[GAP]** (#6729; app; owner 2026-11-19) search is always visible in the main window. The right
  inspector has a minimum width that keeps its search field whole, so a narrow inspector never squeezes the field out of
  view; when the inspector is closed or too narrow the same field and menu move to the toolbar, so closing the inspector
  keeps search. Test (UI): narrow the inspector to its minimum and close it; the search field stays visible and focusable
  with ⌘F.
- `search.scope-menu` — **[GAP]** (#6729; app; owner 2026-11-19) search has a scope: This Page, This Document, This Folder,
  This Project, Everywhere (all open projects). It is a third section, Search Scope, of the same menu that already holds
  Search Kind (Ask / Keyword) and Search Type (Full Text / Semantic / Semantic + Graph), with a check on the current scope.
  It defaults to the narrowest sensible scope for the current selection, and the field's placeholder shows it (for example
  "Search this document"). Ties to the search milestone; the always-visible field is its entry point.
- `search.ask-keyword-native-scopes` — **[OK]** (superseded by the #5024 ruling: `search.one-toolbar-button-with-the-kind-menu`) Ask/Keyword are native `.searchScopes`, shown
  only while the field is presented, not a separate always-visible control. Pinned:
  `ToolbarSearchRoutingTests` (`testToolbarSearchRoutesToATransientSearchWithNoSavedSearch`,
  `testRepeatedSearchesRouteIdenticallyPerQuery`, `testBlankQueryProducesNoRoute`,
  `testWhitespacePaddedQueryStillRoutesWithTrimmedQuery`).
- `search.method-lives-in-options-menu` — **[OK]** Hybrid/Semantic/Full-Text is a separate
  control from Ask/Keyword, living in the results bar's Options menu, not a third scope
  crowding the search field itself. Pinned: `SearchScopeAndOptionsMenuTests`
  (`testEveryFormerRowControlLivesInTheMenu`, `testScopeOffersExactlyTwoChoices`).
- `search.scope-carries-the-breadcrumb` — **[OK]** a search launched from inside a browsed
  folder scopes to that folder's whole breadcrumb trail, not just the leaf, and the Library
  root itself is never part of the scope. Pinned: `SearchScopeAndOptionsMenuTests`
  (`testScopeCarriesTheWholeBreadcrumbTrailNotJustTheLeaf`,
  `testTheLibraryRootSegmentIsNotPartOfTheContextScope`).
- `search.query-syntax-prefixes` — **[PARTIAL]** (#4604) `person:`/`place:`/`organization:`/
  `entity:`/`date:` prefix parsing exists (`search/query_parser.py`, cited in the historical-
  text-normalization spec's own grounding); whether ALL five prefixes from #4604's own list are
  wired end-to-end through the toolbar field was not individually re-verified this pass.
- `search.smart-routing-question-vs-keywords` — **[OK]** a question compiles through an LLM into
  a structured query rather than running as a literal keyword match; a failed compilation
  surfaces its error, never silently falling back. Pinned: `test_routes_search.py`'s
  `TestQueryCompilation` and `ToolbarSearchRoutingTests.testCompilationFailureDetailRemainsReadable`.
- `search.query-expansion-related-terms` — **[GAP]** (#4604) the ask that searching "gold"
  should offer/search precious-metals-and-related terms via vector neighbors was not found
  built; the semantic leg finds documents ABOUT related concepts, but no query-expansion step
  rewrites or offers alternate terms before searching.

### B. Retrieval, ranking, and honesty

- `search.zero-results-for-visible-text` — **[PARTIAL]** (#4236 still open pending close) a search can return 0 results
  for a term the Inspector is displaying, on screen at the same moment, for the SAME document —
  a confident, wrong, empty answer, not a stale-index absence. The issue itself named three
  candidates needing different fixes: (1) search silently scopes to an empty/no-selection
  collection and reports a correct zero for that empty scope; (2) case-sensitivity somewhere in
  the match path; (3) the text belongs to a PAGE child, and the index covers parent documents
  but not page children. **Update, 2026-09-19**: the engine lane reproduced all three named
  candidates against a real test library, and NONE of them reproduces the symptom — the cause
  is something else at that layer. **A second hypothesis (the keyword-fallback-scan gate)
  was then TESTED and KILLED**: in a partly-embedded temp library using the real embedder, the
  never-embedded page child was still found — the safety net's gate looks only at the fulltext
  leg's OWN hits for the query term, not at the semantic leg, so an unrelated embedded document
  does not starve it. Nothing at the `Database.search` layer reproduces the bug across two
  separate constructions; that hypothesis is no longer a live candidate. **Next, untested**: the
  route wrapper `enhanced_search` — ACL visibility, phrase/exclude post-filters, and scope
  filters — none of which `Database.search` itself exercises. **Update, 2026-09-19**: the
  route layer was driven end to end in a temp library; six shapes came back clean. Two
  MECHANISMS drop a page-child hit — stated as mechanisms found, not a confirmed cause of the
  maintainer's own repro: (1) a `doc_type=file` filter tests the HIT's own `doc_type` ("page"),
  not its parent document's, so a page-child hit fails a filter meant for the parent; (2) the
  ACL visibility filter, under real multiuser, would also drop a hit the requesting user lacks
  access to — but this is a no-op for a single owner on loopback, so it is a mechanism to know
  about, not a suspect for the maintainer's own single-user repro. **Whether the app ever
  actually SENDS `doc_type` on this query path is UNVERIFIED — the next check.**

  **REPRODUCED, 2026-09-19** (engine lane, temp library, the real route, the real embedder).
  Cause: the keyword fallback that scans raw page text runs only when the index returns
  NOTHING for the query (`db/__init__.py`, the `if not fulltext_results:` gate, about line
  5439). A page that is not indexed yet is found only by that fallback. The moment ANY other
  indexed passage matches the same term, the gate stays shut and the unindexed page vanishes,
  for hybrid and keyword search alike. Shape: a name that appears across many documents, most
  already embedded, one freshly imported page not yet embedded. Exactly the "Inspector shows
  the text, search finds nothing" report.

  Ruled out with evidence: folder scope (the folder walk is an unbounded BFS and is correct,
  the drop is identical with and without `folder_id`, three levels deep), an unrelated
  embedded document (does not shut the gate, which is why an earlier test of this same idea
  came back clean), the doc_type filter (the app never sends it), the visibility filter (a
  no-op for a single owner on loopback). A stale comment above the folder filter still
  describes a one-hop walk.

  Not the same defect as #4885's three recursion switches.

  **FIXED, 2026-09-19 (0ca50eb55).** The fallback now covers exactly the documents the index does
  not cover, unioned with the index hits — an embedded document is never a fallback candidate, so
  no duplicates, and the fallback's own scoring and the shared filter loop are unchanged. The
  folder filter's stale "one hop" comment is corrected in the same commit: the walk is a full
  subtree BFS, as the earlier ruled-out evidence above already found. Cost is bounded and
  measured, not assumed: which documents are embedded is cached per library for the process and
  invalidated at the three embedding write sites, so a hit is a dict lookup — cold, at 200k
  embedding rows, 0.27s once after a write; a fully embedded library scans nothing. A
  table-version-check alternative was measured and rejected (opening the table costs most of the
  scan, and a held handle doesn't see another handle's writes). Tests executed: the 14 new cases
  in `test_search_without_embeddings.py` (subfolder nesting, an unrelated embedded document, and
  rows embedded after an earlier keyword query all ruled out and kept as regression tests) plus
  the pre-existing 71 route tests, all passing. **PARTIAL, not OK, because #4236 stays open**:
  needs an engine restart to pick up the fix, and the maintainer has not yet confirmed it against
  his own library — built and tested, not yet seen working.
- `search.four-leg-response` — **[OK]** `SearchResponse` carries documents, entities, claims,
  and artifacts as four peer legs (`entity_hits`, `claim_hits: list[SearchClaimHit]`,
  `artifact_hits`), not a document search with metadata bolted on — the exact shape the unified-
  object-search ask (below) wants, for these three object types. Pinned:
  `test_routes_search.py::TestEnhancedSearch`,
  `TestHonestCounts` (`rendered_total` vs `total_results` do not drift from the body).
- `search.leg-visibility-not-fake-confidence` — **[OK]** `legs: dict[str, int]` reports which
  retrievers ran and how much each contributed; `weak_semantic_only` flags a result set with no
  literal or graph evidence, letting the UI say "no literal matches" instead of dressing up a
  fused rank as confidence. Pinned: `test_routes_search.py::TestGraphLeg`,
  `SearchHonestySummaryTests`, `SearchSourceHonestyTests`.
- `search.images-artifacts-as-first-class-results` — **[PARTIAL]** (#4118) artifacts are a first-
  class leg (built, see above); whether IMAGE captions/OCR specifically surface as their own
  typed result (the issue's other named object type) was not confirmed this pass — `artifact_hits`
  may already cover this if an image's OCR text is stored as an artifact, but that mapping
  wasn't traced end to end.
- `search.real-relevance-signal-exists` — **[PARTIAL]** (#4119) `best_semantic_similarity` (raw
  cosine) and the leg-count/weak-flag infrastructure above give a REAL signal to build an honest
  display from — this is not the fake-71%-everywhere state the issue describes. Not built: the
  issue's own "graphical, not a percentage" display requirement — no DEVONthink-style heat
  bar/dots UI was found; today's UI still likely shows a number where one exists.
- `search.exact-match-boost` — **[PARTIAL, unverified against the original repro]** (#1782) hybrid
  RRF fusion across semantic + fulltext exists (cited in `historical-text-normalization.md`'s own
  grounding of `_fold_for_search`/BM25); whether it specifically fixes the issue's own repro
  ("andagueda" surfacing "Andagoya," a different place, as the #1 semantic-only hit) was not
  re-run this pass — the infrastructure to fix it (leg weighting, `_lexical_evidence_strength`)
  exists, but the specific regression case is unconfirmed either way.
- `search.embedding-failure-honesty` — **[PARTIAL]** (#4395) `embed()` returns its `EmbedOutcome`
  (truthy only when vectors were written) and every call site reads it: "no embeddable text" and
  "excluded" are skips; "no passages produced" is logged as a malfunction; "embedding failed" (the
  model cannot load) is an error in the import log, and a re-embed after a correction fails its
  job so Activity shows it. Pinned by `tests/unit/db/test_embed_outcome_contract.py` and the
  discarded-result seam. Not built: an import does not stop at the first infrastructure failure;
  it carries on and counts each document.
- `search.embedding-model-only-while-needed` — **[OK]** (→ #5283, ruled 2026-10-01) the
  embedding model (bge-m3, about 1.5 GB of the engine's 1.8 GB, measured 2026-09-30) is loaded
  when something needs it — an embed or a semantic search — and **released once nothing has
  used it for a while**, so a session that never embeds or searches never holds it. It is
  **not loaded at launch**: the post-ready prewarm no longer loads it (the workflow tool-stack
  warm-up stays). An embed that is running holds it; the release waits for it. The first
  semantic search after a release pays the load again (seconds), which the ruling accepts.
  Built as `db.embeddings.leased_embedder` (every embed leases the shared model; a Database
  keeps only which model) and `release_idle_embedders`, run by a daemon thread while a model is
  loaded (`FICHERO_EMBEDDER_IDLE_SECONDS`, default 600). Pinned by
  `fichero-server/tests/unit/db/test_embedding_model_only_while_needed.py` (released means
  collected; an embed in progress holds it; a Database keeps no reference),
  `tests/unit/api/test_warm_up_after_ready.py` (launch loads no model) and
  `tests/unit/api/test_prefetch.py::test_prefetch_loads_no_embedding_model`. Not yet measured on
  a running engine (the footprint after the idle spell).
  The idle spell is `FICHERO_EMBEDDER_IDLE_SECONDS` (600 by default); the embedder's own process ends with the release and its memory goes back with it, checked against the real model where it is installed (skipped where it is not): `fichero-server/tests/unit/db/test_idle_embedder_returns_its_memory_6129.py` (#6129).
- `search.unify-retrieval-as-one-index` — **[PARTIAL, north-star]** (#1824) the four-leg response
  plus leg visibility is real, meaningful movement toward "one queryable index, many lenses" —
  but the issue's own full list (graph + RAG + vector + full-text + hermeneutics + ontology +
  interpretations + chat, as one COMPOSED index) is a much larger unification than four legs in
  one HTTP response; hermeneutics/ontology/interpretations/chat are not additional legs of this
  same query today. Recorded as directional progress, not completion.
- `search.passage-chunking-kg-fusion-ranking` — **[GAP, unverified]** (#1833) whether page
  content is embedded as passage-level chunks (vs. one vector per whole page, averaging the
  signal) was not confirmed this pass; the per-passage `char_start`/`char_end`/`passage_id`
  fields cited elsewhere in this codebase (search result metadata, `db_embeddings.py`) suggest
  SOME passage-level structure exists, but whether it resolves this issue's specific "a
  page-mean vector competes against a one-line query" complaint needs a closer read than this
  pass gave it.

### C. Corpus tools and the north-star EPIC

- `search.corpus-linguistics-tools` — **[GAP]** (#1812) no KWIC concordance, collocation,
  frequency/n-gram, or keyness tooling exists; a large, standalone feature request, not started.
- `search.results-render-as-library-nodes` — **[OK]** search hits render as ordinary Library
  rows across every view mode, not a separate results screen with disclosure sections — the
  EPIC's own biggest RESULTS-section ask, built. Pinned: `SearchResultsReachEveryViewModeTests`
  (`testDatasetRenderersScopeTheirQueryToTheSearchHits`); see also
  `library-view-modes.md`'s own `library.search.*` behaviors above.
- `search.click-result-to-highlighted-region` — **[GAP, the EPIC's own "big missing feature"]**
  (#4604) clicking a result lands in the Reader with the matched PASSAGE highlighted (built, see
  `reader-view.md`'s `reader.passage-channel.has-a-second-producer`) — but the PREVIEW-pane
  bounding-box highlight and the multi-passage HEAT MAP over a page (the issue's own explicit
  "big missing feature" framing) were not found built anywhere under `Views/Preview/`. The
  passage-level channel exists; the page-region/heat-map visualization does not.
- `search.vector-space-visualization` — **[GAP]** (#878, #4604) no 2D/3D embedding-space view
  mode exists; #4604 itself calls this a "needs a feasibility spike" item, not a committed
  build — recorded as GAP, not urgent.
- `search.smart-folders-as-sidebar-folders` — **[PARTIAL]** (#4114) saved searches ARE first-
  class, audited, sidebar-mounted objects (see `search.*` above) — the foundation this issue
  needs. Not confirmed: drag-into-any-folder behavior, alias support (reusing → #2591's existing
  alias machinery), or the one-click "all mentions of `<entity>`" creation from an entity's
  context menu.
- `search.find-related-documents` — **[PARTIAL]** (#4606) the engine endpoint exists
  (`GET /documents/{doc_id}/related`, two merged legs, degrade-not-500 on either leg failing)
  and a UI surface exists (`DocumentInspectorRelatedTab.swift`) — but not in the COLUMN VIEW the
  issue specifically asks for; today's surface is the Inspector, a different location with the
  same underlying data.
- `search.reader-graph-view-restored` — **[GAP, unverified]** (#4604's own "RESTORE" line) a
  reader graph view with subject-verb-object statements laid out is described as "hidden in
  some reorg" by the issue itself, filed separately — not independently checked this pass
  whether it has since resurfaced.

### D. Naming (placed here, not `panes-workspaces.md`)

- `search.built-in-library-has-one-name` — **[GAP, DESIGN]** (#4891) seen live 2026-09-19: the
  built-in library is called "Global" in the sidebar and "Local" in breadcrumbs — two names
  for the same thing. Placed in THIS spec rather than `panes-workspaces.md` (owned by a
  different lane on this same findings pass) because `search.scope-carries-the-breadcrumb`
  above is this spec's own behavior that displays the inconsistent name today; the sidebar-row
  naming itself may also need a matching fix in that other spec, cross-referenced, not
  restated. **Candidate names, none recommended** — the maintainer decides: "Home" (short,
  familiar from other apps, but implies a single default rather than a specific library kind);
  "This Mac" / "On My Mac" (Apple's own convention for the local, non-iCloud store — precise,
  but wordy in a breadcrumb); "Built-In" (accurate and neutral, but sounds like a settings
  category, not a place); "Default" (matches how the code already treats it internally, but
  reads as "the one nothing else overrode," not a place with things in it); "Global" (already
  used in the sidebar today — keeping it and fixing only the breadcrumb's "Local" would be the
  smallest change, at the cost of not addressing whichever name the maintainer actually
  dislikes).

## Review 2026-11-20: what the code does, measured

> A review of search end to end, against the code and against runs on scratch projects (never a real
> one). `→ #NEW-Sn` marks an issue the manager is asked to file; each such line also cites the open issue
> nearest to it. Where a line here and an older line above disagree, this one is the later reading of the
> code: `search.scope-menu` (two of its five scopes are built), `search.query-syntax-prefixes` (wired, see
> F), `search.passage-chunking-kg-fusion-ranking` (passages are built, see E), and the Grounding paragraph
> on embeddings.
>
> **How it was measured.** (1) Real text: 18 pages of real transcriptions (12 English diary and account
> pages, 1 early-modern Spanish notarial page with abbreviation markup, 2 Arabic, 2 Hebrew, 1 polytonic
> Greek), embedded with the shipped model (bge-m3) on a 16 GB M1 laptop; 24 hand-made queries; three
> statements and two names added by hand for the graph and Ask runs; the on-device text model for Ask.
> (2) Scale: synthetic pages of about 1,800 characters (about 6 passages each), one name and three
> statements per page, random unit vectors in place of the model, at 5,000, 20,000 and 50,000 pages on a
> 24 GB M4 desktop. (3) The 346 search, retrieval, saved-search and embedder unit tests: all pass.

### E. What search is made of (as built)

- `search.store.passages-in-one-table` — **[OK]** a page's text is cut into passages of up to 512
  characters with 80 of overlap, each with its page and character offsets
  (`fichero-server/src/fichero_server/db/embeddings.py`, `split_text_passages`); each passage is one row,
  text and a 1,024-number vector normalised to length 1, in one table in the project's own `vectors`
  folder. Full text is an index on that same text column (lower-cased, Latin accents folded, no stemming,
  no stop words; `fichero-server/src/fichero_server/db/__init__.py`, `_ensure_text_search_index`); meaning
  is a scan of every vector (no approximate index). Names and statements have their own two vector tables.
  Pinned: `fichero-server/tests/unit/db/test_embedding_passages.py`.
- `search.store.one-fused-list` — **[OK]** hybrid search ranks each leg alone, keeps a page's best
  passage, and fuses the lists by reciprocal rank (k = 60); the graph joins as a third list only when
  Semantic + Graph is chosen. Pinned: `fichero-server/tests/unit/search/test_search_scoring.py`.
- `search.embedding.never-beside-kraken` — **[OK]** the search model and Kraken are never loaded
  together: loading either frees the other first, and a search that would need to unload a running Kraken
  says the search model is busy instead (`fichero-server/src/fichero_server/llm/kraken_runtime.py`,
  `release_for_the_embedder`). Pinned:
  `fichero-server/tests/unit/llm/test_kraken_and_embedder_never_resident_together_perf1.py`. The model
  (about 1.5 GB loaded) runs in its own process and is released after ten idle minutes
  (`search.embedding-model-only-while-needed`). Measured: the first semantic search after a release took
  7.5 s on the M1, later ones 0.1 to 0.3 s on 18 pages.
- `search.scale.passages-end-cleanly` — **[PARTIAL]** (#1833, → #6780) a page whose text ends in a space
  or a line break was cut into its real passages and then about 70 more, each one character shorter than
  the last (80, 79, 78 … characters of the page's tail): the cutter steps one character at a time once
  the remaining text is all inside the overlap. Measured on real diary pages of about 1,000 characters:
  67 to 73 rows a page where 3 are right; 786 of the 861 rows of the 18-page project were such tails.
  It costs twenty times the embedding work (40 to 79 s a page on the M1 where the six-passage Spanish page
  took 6 s), twenty times the disk and scan, repeated rows for one page in full-text results, and tail
  scraps at the top of semantic results (a three-letter query scored 0.91 against a scrap). Should: a
  page's passages never number more than its length divided by the step, plus one; the tail is one
  passage. Built: the cutter leaves trailing whitespace out of the length, so a page is cut into the
  same passages with or without it; pinned:
  `fichero-server/tests/unit/db/test_passages_of_text_ending_in_whitespace.py`. Rows already written:
  `Database.tail_passage_scan` counts the pages and tail rows without writing, and
  `Database.remove_tail_passages(confirm=True)` deletes only those rows, leaving the passages the cutter
  makes now, so nothing is embedded again; pinned:
  `fichero-server/tests/unit/db/test_tail_passage_rows_are_found_then_removed.py`. Not built: a route or
  menu item that runs the scan and offers the removal on an existing project.
- `search.embedding.estimate-is-measured` — **[BROKEN]** (#4302, → #6792) the time estimate for
  embedding a project assumes 6 passages a second for bge-m3. Measured on the M1 at the engine's
  background priority: 0.6 to 1.6 a second (18 Greek passages in 29 s, 6 Spanish in 6 s). The figure should be the machine's own measured rate
  (kept from its last run), said as an estimate. Test to write: test_embed_estimate_uses_measured_rate.py
  in `fichero-server/tests/unit/db/`.

### F. Speed and truth at 5,000 to 50,000 pages

Measured, M4 desktop, warm, best of three, model time left out (the query vector is given):

| pages | passage rows | keyword, common word | keyword, rare word | word with no index hit | fuzzy | semantic | hybrid | the vector scan alone | the text index alone | peak memory |
|---|---|---|---|---|---|---|---|---|---|---|
| 5,000 | 29,665 | 0.77 s | 0.62 s | 3.8 s | 9.8 s | 0.78 s | 0.95 s | 18 ms | 7 ms | 1.4 GB |
| 20,000 | 118,609 | 2.6 s | 2.3 s | 17 s | 42 s | 2.6 s | 2.7 s | 54 ms | 9 ms | 3.6 GB |
| 50,000 | 296,458 | 6.0 s | 5.5 s | 43 s | 111 s | 6.9 s | 7.4 s | 214 ms | 24 ms | 7.7 GB |

The two indexes are fast; nearly all of the time is what is done around them.

- `search.scale.budget` — **[BROKEN]** (#4604, → #6782) at 50,000 pages a keyword search answers in
  under 0.3 s and a semantic or hybrid one in under 1 s once the model is loaded, and a search adds no
  more than 300 MB of memory. Measured: 5.5 to 7.4 s, and 7.7 GB. The perf test that should hold this
  (`fichero-server/tests/perf/test_search_workload_perf.py`) seeds 200 pages with no text, no vectors and
  no graph, so it cannot see any of it. Test to write: the same file seeds 5,000 pages with passages,
  given vectors, names and statements, and holds a budget scaled from this one. Ruling P4 (owner
  2026-11-21): the budget is held on the 8 GB M1.
- `search.scale.cost-does-not-grow-with-the-graph` — **[BROKEN]** (#1833, → #6782) every search, of any
  type, reads every name in the project to widen the query with aliases, then every statement and every
  name again to mark which hits they touch (`_expand_query_with_entity_aliases`,
  `enrich_search_results_with_kg`). Measured: reading all statements alone takes 0.46 s, 1.6 s and 4.8 s
  at the three sizes, and it is done on each search. Should: aliases are looked up by folded name in an
  index, and statements are fetched for the pages on the result page only. Test to write:
  test_search_reads_only_the_rows_it_needs.py in `fichero-server/tests/unit/search/` (counts rows read).
- `search.scale.no-whole-table-read` — **[BROKEN]** (#3321, → #6783) when the text index finds nothing
  for a word (a typing slip, the start of a word, a word inside a longer token), and for every fuzzy
  search, the whole passage table, vectors included, is read into memory and scanned. Measured: 43 s and
  about 3.5 GB more memory at 50,000 pages for one mistyped word; fuzzy 111 s. On a 16 GB laptop that is
  the engine being killed. Should: the scan never reads vectors, and the cases it serves move into the
  index (`search.match.same-with-or-without-other-hits`). Test to write:
  test_zero_hit_query_reads_no_vectors.py in `fichero-server/tests/unit/search/`.
- `search.scope.narrows-before-ranking` — **[BROKEN]** (#4236, → #6781) a search in This Folder ranks
  the whole project, keeps the best 200 passages, and only then drops what is outside the folder. A
  folder of 50 pages that all hold the word returned 30 to 43 of them in a 300-page project, 3 in a
  20,000-page one, and none at 5,000 and 50,000 pages: the header says 0 results for a word the folder is
  full of. Date and type filters are applied the same way. Should: the scope (folder and its subfolders,
  one document, one page, a selection, a date range) is given to both indexes as a filter, so a scoped
  search searches only the scope and its count is the scope's count. This is also the engine half of the
  Page, Document and Selection scopes of `search.scope-menu`. Test to write:
  test_scoped_search_finds_everything_in_scope.py in `fichero-server/tests/unit/search/`.
- `search.results.one-row-per-page` — **[BROKEN]** (#4604, → #6784) Full Text returns a page once for
  each passage that matched (hybrid and semantic keep one). Measured: 9 repeats in 22 rows at 50,000
  pages; on real text one page three times in the first three rows. Should: one row a page, carrying its
  best passage and how many passages matched. Test to write: test_fulltext_one_row_per_page.py in
  `fichero-server/tests/unit/search/`.
- `search.results.total-is-true` — **[BROKEN]** (#4604, → #6784) the total a search reports is the
  number of candidates kept, which is never more than four times the page size: a word on thousands of
  pages says 200. Should: the true count of matching pages when it is cheap (keyword), else "more than
  N", never a ceiling shown as a count. Test: the same file as above.
- `search.scale.vector-index-when-large` — **[GAP]** (#1833, → #6793) scanning every vector is right
  at these sizes (214 ms for 296,458 rows) and exact. Past about 500,000 rows the table gets an
  approximate index, rebuilt when a tenth of the rows are new, and vectors are kept at half or quarter
  size (the int8 switch exists and is off). Not needed before the fixes above. Test to write:
  test_vector_index_built_past_threshold.py in `fichero-server/tests/unit/db/`.

### G. Matching: languages, scripts, old spelling

Measured on the real pages (rank of the right page; 18 pages, default settings):

| query | Full Text | Semantic | Hybrid (default floor) |
|---|---|---|---|
| exact phrase, two words, a surname | 1 | 1 to 4 | 1 |
| paraphrase in the page's language (5 queries) | 1 to 2 | 1 to 2 | 1 to 2 |
| accented name typed with or without the accent | 1 | 5 | 1 |
| start of a word (a stem) | 1 (by the slow scan) | 2 | 1 |
| Spanish word typed without accent; abbreviation as written | 1 | not found; 10 | 1 |
| Spanish paraphrase, in Spanish | 1 | 1 | 1 |
| the same idea asked in English | not found | 2 | not found |
| Arabic, Hebrew word as written; Greek with and without accents | 1 | 2 to 7 | 1 |
| a question in words | 1 | 1 | 1 |
| nonsense | none | 7 pages at 0.68 to 0.69 | none |

- `search.match.same-with-or-without-other-hits` — **[BROKEN]** (#3321, → #6783) the start of a word,
  a word inside a longer token (a line in a script written without spaces is one token), and a pointed
  Hebrew or Arabic word typed without points are found only by the slow scan, and the scan runs only
  when the index found nothing at all for the query. So the same word is found or not depending on
  whether some other page holds the query as a whole word. Should: one stored, folded copy of the text
  (case, accents, points, compatibility forms: the fold of `histnorm.accent-insensitive-search`) indexed
  by word and by short character runs, so starts of words, unspaced scripts and unpointed typing are
  index hits, always. Ruling P3 (owner 2026-11-21): the folded copy is stored for each page and the
  database's own index is built over it. Test to write: test_prefix_and_unpointed_hits_survive_other_hits.py in
  `fichero-server/tests/unit/search/`.
- `search.match.reading-levels` — **[GAP]** (#3312, #3321) the index holds one text a page (the page's
  standing text). A search cannot be told to match the letters as written, the normalised reading, or
  the expanded abbreviations, and a page is found by an expansion only if the expansion was written into
  that one text (as on the notarial page measured, whose markup carries both). Should: each standing
  level of a page's reading is indexed; a search matches all of them by default and the row says which
  level matched; a menu narrows to one. Owned with `histnorm.dual-field-model-not-built`.
- `search.match.old-spellings` — **[GAP]** (#3313) spelling habits of a period (u and v, i and j, ç and
  z, long s, doubled letters) are not folded; the fuzzy switch is the only help and it is the slow scan.
  Should: a per-language table of equal spellings applied to the folded copy and to the query, on by
  default, off with one switch, never changing the text kept.
- `search.match.scripts-measured` — **[PARTIAL]** (#3321) Arabic and Hebrew words as written, polytonic
  Greek with and without accents, and Spanish without accents are found first by Full Text and by
  Hybrid on the real pages. Not measured: pointed text typed unpointed, right-to-left snippets on
  screen, scripts written without spaces. Pinned in part:
  `fichero-server/tests/unit/search/test_search_fold_unicode.py`.
- `search.hybrid.meaning-survives-a-weak-keyword-hit` — **[BROKEN]** (#1782, → #6787) when any page
  matches a query word, hybrid shows only the keyword pages and drops pages found by meaning alone.
  Measured: an English question about a Spanish deed ranked the deed second by meaning (0.85) and hybrid
  returned one English page that shared two common words, and not the deed. Should: a page found by
  meaning alone stays, under the keyword pages, when its score stands clear of the project's own floor
  (below). Test to write: test_hybrid_keeps_clear_semantic_hits.py in `fichero-server/tests/unit/search/`.
- `search.hybrid.floor-is-the-projects-own` — **[BROKEN]** (#4119, → #6787) the default floor of 0.55
  does nothing with this model: nonsense scores 0.68 to 0.69 and right answers 0.79 to 0.85, a band
  0.15 wide. Should: the floor is measured for the project (the scores of a few random passages against
  the query, or kept from the last searches), and a hit is shown as found by meaning only when it stands
  above it. The fused score is not shown as a percentage: three rows read 100% in one result. Two words
  instead, as `search.adopt.two-bands`.

### H. Searching the graph: who, what, where, when

What a person can do today (run through the real route, with names and statements added by hand):
type `people:` (or `person:`), `places:`, `organizations:`, `events:` before a name; pick Semantic +
Graph so statements and names help rank pages; and, by reading the app's code, start such a search from a name's own row. There
is no way to ask who did what, where or when; no date range anywhere in search; and the graph's own
search route is not called by the app.

- `search.graph.scopes-read-the-record` — **[OK]** `people:Name` finds the pages where a name or one of
  its aliases is written, accent-blind, through merges, never a rejected name, with the segments its
  mentions sit on; singular and plural prefixes are the same. Measured: both pages returned for a
  surname, one for a place typed without its accent. Pinned:
  `fichero-server/tests/unit/search/test_search_reads_the_record.py`,
  `fichero-server/tests/unit/search/test_search_query_parser.py`.
- `search.graph.scope-with-words-means-both` — **[BROKEN]** (#4604, → #6788) a name prefix with other
  words (`person:"A B" contract`) is not "pages where A B is written that are about a contract": the
  prefix is taken out and the words are searched alone. Measured: a page with no mention of the person
  came back. Should: prefixes narrow (which pages), words and meaning rank (in what order).
- `search.graph.dates-read-the-record` — **[GAP]** (#5597, #5008) `dates:1935` matches only inside
  extraction artifacts, as letters. Measured: nothing found in a project with two statements dated in
  1935 on pages headed with 1935 dates.
- `search.graph.date-range` — **[PARTIAL]** (#3322, → #6785) the engine can keep only pages whose
  written date span overlaps a range (day numbers, so any calendar; a page dated to a year overlaps any
  range touching that year; undated pages are left out), `date_jdn_from` and `date_jdn_to`. Nothing in
  the app sends it, it is applied after the candidate cut (`search.scope.narrows-before-ranking`), no
  test names it, and a statement's own dates (`time_start`, `time_end`, `time_precision`) cannot be
  searched at all. Test to write: test_search_date_range_overlap.py in
  `fichero-server/tests/unit/search/`.
- `search.graph.who-what-where-when` — **[GAP]** (#4604, → #6788) one question in four parts, any of
  them empty: who (a name or alias, or a kind of name), did what (the verb or the words of the
  statement, folded, by meaning if nothing matches as written), where (a place, and the places inside
  it), when (a date or a range). The answer is statements, each with its page and the segment it stands
  on, grouped by page; typed as `who: what: where: when:` in the one field, or filled in from a row of
  four boxes under it; kept as a saved search like any other. It reads the statement and name tables
  through indexes, never the whole graph (`search.scale.cost-does-not-grow-with-the-graph`). Tests to
  write: test_statement_search_four_parts.py in `fichero-server/tests/unit/search/`.
- `search.graph.a-date-is-a-span` — **[GAP]** (#5008, → #6788) every date searched or matched is a
  span with a precision: "1935" is the whole year, "March 1935" the month, "about 1930" a span with a
  stated margin, "before 1940" open at one end. A match is an overlap; closer and tighter spans rank
  first; a date that is inferred or disputed says so on the row; undated statements and pages are never
  silently dropped: they are counted and offered apart ("212 undated"). The same rule as
  `explore.time.a-date-is-a-span`.
- `search.graph.with-words-and-meaning` — **[GAP]** (#1824, → #6788) how the three combine, in one
  rule: the graph parts and the scope NARROW (which pages and statements may be shown); words and
  meaning RANK inside what is left; when no graph part is given, the graph only helps rank (today's
  Semantic + Graph). A row says each way it was found (word, meaning, name, statement), as it does now.
- `search.graph.names-lead-to-their-pages` — **[BROKEN]** (#1833, → #6786) the step that follows the
  names nearest a query to the pages of their statements, so a page is found though its text never has
  the word, never runs: it reads the name hits as objects and they are plain records, so each one fails
  and is skipped, with one warning in the log per search
  (`fichero-server/src/fichero_server/api/routes/search/core.py`, `enhanced_search`, the graph leg). Its
  test passes because it only checks the hit if the hit is there. Test to write: the existing graph-leg
  test asserts the page is found by the graph, with no condition.
- `search.graph.own-route` — **[PARTIAL]** (#2571, → #6788) `GET /api/kg/search` looks for letters in
  every name, statement, note and annotation by reading them all, lower-cased but not folded (an
  accented name is missed unless an alias is plain); it is off below the beta tier and nothing in the
  app calls it. It becomes the statement search above or goes.

### I. Ask

Two different things are called Ask. In the search field, Ask is the same search with the question first
turned into a search by a model; no answer is written. Chat is where a question gets an answer with
sources; it is a dev-tier feature, off in a release build, and the search field does not lead to it.

- `search.ask.turns-a-question-into-a-search` — **[PARTIAL]** (#5029) built and shown ("Searched: …");
  measured with the on-device model: 3.1 s, and 7.0 s the first time, on the M1; the right page first
  for both questions tried. The defects are the next three lines.
- `search.ask.invents-no-filter` — **[BROKEN]** (#5029, → #6785) a question with no date in it came
  back with the date range of the example in the model's instructions (a month in 1948), and with
  "entities" that are just the question's nouns. Should: a filter is kept only if its words are in the
  question (checked in code, not asked of the model); the instructions carry no copyable example date.
  Test to write: test_compiled_filters_come_from_the_question.py in
  `fichero-server/tests/unit/retrieval/`.
- `search.ask.a-date-means-the-date-written` — **[BROKEN]** (#3322, → #6785) a date range taken from a
  question is compared with the day the page was imported, and passage hits carry no such day, so the
  filter does nothing: "in January 1935" narrows nothing and says it did. Should: it becomes the
  written-date range of `search.graph.date-range`, shown as a part of the search that can be removed.
- `search.ask.uses-the-chosen-text-model` — **[BROKEN]** (#5368, → #6791) the model that turns the
  question into a search is looked up among provider rows in the project's database, where there are
  none, so it is always the on-device model whatever Settings says (chat reads the app's default
  correctly). In an engine run from source the on-device bridge is also looked for one folder too high
  and reported missing. Test to write: test_compile_uses_the_app_text_default.py in
  `fichero-server/tests/unit/retrieval/`.
- `search.ask.answers-with-cited-pages` — **[GAP]** (#1828, → #6789) Ask in the search field gives a
  short answer above the result rows: written from the passages that matched (and the statements on
  those pages), each sentence followed by the page it rests on, which opens at that passage; "not found
  in these pages" and no sources when nothing stands above the floor; the model that answered is named;
  on this Mac unless the person chose otherwise. The rows under it are the same search. The chat
  behaviours it rests on are `research.chat.*` in `research.md`.

### J. The app, as built

Read from the Swift code, 2026-11-20; not run. One field: the toolbar's search field on the Mac
(`ToolbarSearchField`), the system search field on iPad and iPhone. Its menu holds Interpretation (Ask,
Keyword), Search Type (Full Text; Semantic, which sends hybrid and is the default; Semantic + Graph,
offered once names have been reviewed), and Search Scope (This Project, This Folder). Return runs it;
Escape clears it. Results replace the Library's rows, 50 at a time with a Load 50 more button; a row
shows how it was found (exact, entity, claim, graph), a percentage, and a snippet with the words lit;
the bar above says how many, from which legs, what was really searched, and when nothing matched as
written. Selecting a row opens the page in the Reader at the passage (by character offsets) and lights
the same words on the image; there is no region box and no page heat map. Save Search puts the search in
the sidebar; clicking it runs it again.

- `search.scope.two-of-five` — **[PARTIAL]** (#6729) This Project and This Folder are built
  (`fichero/Tests/Unit/general/Views/Library/SearchScopeAndOptionsMenuTests.swift`); This Page, This
  Document, a selection and Everywhere are not, and wait on `search.scope.narrows-before-ranking` and
  `search.all-libraries-fanout`.
- `search.saved.rename-keeps-the-query` — **[BROKEN]** (#4114, → #6790) renaming a saved search
  replaces its query with the new name (`SavedSearchService.renameSavedSearch`): a saved search has no
  name of its own. Should: a name and a query, two fields. Test to write: a case in
  SavedSearchRenameTests.swift under `fichero/Tests/Unit/general/`.
- `search.saved.keeps-scope-and-filters` — **[GAP]** (#4114, → #6790) a saved search keeps its
  words, type and sort, not its scope or filters (the engine has the field; the app sends none), and it
  is always run as Ask whatever it was saved as. Should: it runs as it was saved.
- `search.keyboard.command-f-finds` — **[PARTIAL]** (#6729) one comment says ⌘F is the search field and
  another that it is the Library's filter bar; by reading, the filter bar wins. The owner's rule
  (`search.always-visible`) is that ⌘F reaches search.

### K. Set beside the system's own semantic index

What Apple's on-device search does that is public: text given to the system index is embedded on the
device, in the background, when the machine is idle or on power; a query runs a word index and the
embedding index together and returns one ranked list; an app asks for ranked results and gets them in
bands of confidence rather than raw scores; changed items are re-indexed one at a time; the models are
the system's, shared by every app, so an app holds no model in memory.

- `search.adopt.two-bands` — **[GAP]** (#4119, → #6787) adopt: results come in two named bands,
  matches (the words, a name, or a statement were found) and related (found by meaning, above the
  project's floor), with no percentage on a row; the raw score stays in Why this result.
- `search.adopt.index-when-idle` — **[PARTIAL]** (#5820) already the design: a page is embedded after
  it is read, a changed page after a quiet spell, at background priority
  (`fichero-server/tests/unit/jobs/test_reembed_waits_for_a_quiet_period_5360.py`). Adopt the rest: bulk
  embedding goes faster when the Mac is idle and on power, and waits on battery.
- `search.adopt.keyword-now-meaning-when-ready` — **[GAP]** (#4302, → #6794) adopt: keyword results
  are shown at once and the pages found by meaning join when the model has loaded (7.5 s after an idle
  spell on the M1), instead of the whole search waiting; and a search never unloads a running reader.
- `search.adopt.system-embedder-as-small-tier` — **[GAP]** (#4302, → #6794) to try, not yet to build:
  the system's own sentence-embedding model as a second, small choice of search model for iPad, iPhone
  and 8 GB Macs. It costs no memory of the app's and no download, and it could stay loaded beside
  Kraken. Against it: it is weaker on old spelling and has one model per script family, where bge-m3
  has one space for every script. A measurement on the multilingual test pages decides.
Not adopted: the project's pages are not given to system Spotlight (#4167, closed as not planned);
research data stays in the project, and the project's own index is the only one.

### L. Chat: asking the project a question (moved from `research.md`, 2026-11-21)

> Run through the real chat route on a scratch project of 18 real transcribed pages (never a real
> project), with the on-device text model and the shipped search model, on a 16 GB M1 laptop; three
> statements and two names were added by hand. `→ #N` names the issue filed from the search review.
> What Ask means in the search field is `search.ask.*` above.

Four questions were asked. The page that holds the answer was the first source for all three questions
that have one (score 1.0, the next page at about 0.5). One answer was right and short (a hotel's name,
with the day's heading, 2.9 s). Two were the page copied out rather than an answer (8.3 s and 9.9 s),
and one of those left out the half of the question that asked when. The question with no answer in the
pages got "no mention" five times over, with five sources listed (6.0 s).

- `research.chat.finds-the-page` — **[PARTIAL]** (#1828) a chat turn searches the project (hybrid, no
  floor, five pages), adds the statements on those pages and one step further through their names, and
  refuses to answer if the search itself fails. Measured: the right page first, three times of three.
  Not built: it is reachable only in a dev build (`/api/chat` is a dev-tier route).
- `research.chat.answers-from-the-passage` — **[BROKEN]** (#1828, → #6789) the model is given the
  first 1,000 characters of each page found, not the passage that matched, so an answer further down a
  long page is never seen; the source's excerpt is likewise the page's first 200 characters. Should: the
  matched passages, with a little either side. Test to write: test_chat_context_is_the_matched_passage.py
  in `fichero-server/tests/unit/api/`.
- `research.chat.a-citation-opens-its-passage` — **[BROKEN]** (#4723, → #6789) the model is told to
  cite "Document 1, Document 2 …" by the order of what it was given, pages and statements in one
  numbering; the reply's sources list holds pages only, so "Document 5" in an answer was a statement and
  matched nothing in the list. A source carries the page's id, name, excerpt and score, and no passage
  offsets, segment or statement id. Should: each cited thing in an answer is a link to the page at the
  passage, or to the statement, and the reply carries what the link needs.
- `research.chat.says-not-found-once` — **[BROKEN]** (#1828, → #6789) when nothing in the project
  answers, the reply repeats "no mention" for each page it was handed and lists those pages as sources.
  Should: one sentence, and no sources, when no page stands above the project's floor
  (`search.hybrid.floor-is-the-projects-own`).
- `research.chat.names-the-model-that-answered` — **[BROKEN]** (#5368, → #6789) the reply says the
  model was "auto/auto" when none was named in the request. Should: the provider and model that ran.
- `research.chat.answers-the-question` — **[GAP]** (#1828, → #6789) an answer is a few sentences in
  the question's language that answer each part asked, or say which part the pages do not answer; it is
  not the page copied out. Held by a small set of questions with known answers over the test pages, run
  against the on-device model when it is present. Test to write: test_chat_answers_known_questions.py
  in `fichero-server/tests/integration/`.

### Open questions (for the owner)

1. Should the start of a word always match (typing "dredg" finds "dredges"), or only with a star?
   Proposed: always.
2. A name prefix with other words: both must hold (proposed), or either?
3. Ask in the search field: an answer above the rows (proposed), or stays a search and answers live
   only in chat?
4. Undated pages in a date search: left out and counted (proposed), or shown last?
5. Is the system's small embedding model worth a measured trial for iPad and 8 GB Macs?

## Build order

Stage 1 is the search review's ranked fixes (section 5 of the 2026-11-20 review), in rank order; a fix
with more than five behaviours is two steps. Stage 2 holds the older issues of milestone `search` that a
line here still cites. Engine tests sit under `fichero-server/tests/`, Swift tests under
`fichero/Tests/Unit/general/`.

### Stage 1 — The review's fixes: correct, then fast, then honest

#### Step 1.1 — A page's passages end where its text ends (#6780)
- Behaviours: `search.scale.passages-end-cleanly`
- Tests: `test_passages_of_text_ending_in_whitespace.py` in fichero-server/tests/unit/db/ (to write)
- Size: S

#### Step 1.2 — The scope narrows before ranking; the 5,000-page scoped test runs in time (#6781, #6867, #4236)
- Behaviours: `search.scope.narrows-before-ranking`, `search.zero-results-for-visible-text`, `search.scope-menu`, `search.scope.two-of-five`
- Tests: `test_scoped_search_finds_everything_in_scope.py` in fichero-server/tests/unit/search/ (to write), `test_embed_many_deletes_rows_in_one_call.py` in fichero-server/tests/unit/db/ (to write)
- Size: M

#### Step 1.3 — Search stops reading the whole graph; a real 5,000-page perf test (#6782)
- Behaviours: `search.scale.budget`, `search.scale.cost-does-not-grow-with-the-graph`
- Tests: `test_search_reads_only_the_rows_it_needs.py` in fichero-server/tests/unit/search/ (to write), fichero-server/tests/perf/test_search_workload_perf.py
- Size: M

#### Step 1.4 — No whole-table read; one folded copy with the database's index (#6783, #3321)
- Behaviours: `search.scale.no-whole-table-read`, `search.match.same-with-or-without-other-hits`, `search.match.scripts-measured`
- Tests: `test_zero_hit_query_reads_no_vectors.py` in fichero-server/tests/unit/search/ (to write), `test_prefix_and_unpointed_hits_survive_other_hits.py` in fichero-server/tests/unit/search/ (to write)
- Size: M

#### Step 1.5 — Ask tells the truth: its filters come from the question, its model from Settings, its graph leg runs (#6785, #6786, #6791)
- Behaviours: `search.ask.invents-no-filter`, `search.ask.a-date-means-the-date-written`, `search.graph.date-range`, `search.ask.uses-the-chosen-text-model`, `search.graph.names-lead-to-their-pages`
- Tests: `test_compiled_filters_come_from_the_question.py` in fichero-server/tests/unit/search/ (to write), `test_compile_uses_the_app_text_default.py` in fichero-server/tests/unit/search/ (to write), `test_search_date_range_overlap.py` in fichero-server/tests/unit/search/ (to write)
- Size: M

#### Step 1.6 — One row per page and a true total (#6784)
- Behaviours: `search.results.one-row-per-page`, `search.results.total-is-true`
- Tests: `test_fulltext_one_row_per_page.py` in fichero-server/tests/unit/search/ (to write)
- Size: S

#### Step 1.7 — Hybrid keeps clear meaning hits above the project's own floor, in two bands (#6787, #1782, #4119)
- Behaviours: `search.hybrid.meaning-survives-a-weak-keyword-hit`, `search.hybrid.floor-is-the-projects-own`, `search.adopt.two-bands`, `search.exact-match-boost`, `search.real-relevance-signal-exists`
- Tests: `test_hybrid_keeps_clear_semantic_hits.py` in fichero-server/tests/unit/search/ (to write), `SearchResultBandRowTests.swift` in fichero/Tests/Unit/general/Views/ (to write)
- Size: M

#### Step 1.8 — Chat answers from the matched passages with citations that map to sources (#6789, #4723, #1828)
- Behaviours: `research.chat.answers-from-the-passage`, `research.chat.a-citation-opens-its-passage`, `research.chat.says-not-found-once`, `research.chat.names-the-model-that-answered`, `research.chat.answers-the-question`
- Tests: `test_chat_context_is_the_matched_passage.py` in fichero-server/tests/unit/api/ (to write), `test_chat_citations_map_to_sources.py` in fichero-server/tests/unit/api/ (to write), `test_chat_answers_known_questions.py` in fichero-server/tests/integration/ (to write)
- Size: M

#### Step 1.9 — Ask in the search field answers above the rows, from the chat route (#6789, #5029)
- Behaviours: `search.ask.answers-with-cited-pages`, `search.ask.turns-a-question-into-a-search`, `research.chat.finds-the-page`
- Tests: `test_chat_route_is_not_dev_only.py` in fichero-server/tests/unit/api/ (to write), `AskAnswerAboveRowsTests.swift` in fichero/Tests/Unit/general/Views/ (to write)
- Depends on: 1.8
- Size: M

#### Step 1.10 — Statement search in the engine: who, what, where, when; a date is a span (#6788)
- Behaviours: `search.graph.who-what-where-when`, `search.graph.a-date-is-a-span`, `search.graph.scope-with-words-means-both`, `search.graph.with-words-and-meaning`, `search.graph.own-route`
- Tests: `test_statement_search_four_parts.py` in fichero-server/tests/unit/search/ (to write)
- Size: M

#### Step 1.11 — Statement search in the app: the four-part row and the prefixes; `dates:` reads the record (#6788, #5597)
- Behaviours: `search.query-syntax-prefixes`, `search.graph.dates-read-the-record`
- Tests: `StatementSearchRowTests.swift` in fichero/Tests/Unit/general/Views/ (to write), `test_dates_prefix_reads_the_record.py` in fichero-server/tests/unit/search/ (to write)
- Depends on: 1.10
- Size: M

#### Step 1.12 — A saved search has a name and keeps its scope and filters (#6790, #4114)
- Behaviours: `search.saved.rename-keeps-the-query`, `search.saved.keeps-scope-and-filters`, `search.smart-folders-as-sidebar-folders`
- Tests: `SavedSearchRenameKeepsTheQueryTests.swift` in fichero/Tests/Unit/general/Views/ (to write)
- Depends on: 1.2
- Size: M

#### Step 1.13 — The embedding time estimate is the measured rate (#6792, #4302)
- Behaviours: `search.embedding.estimate-is-measured`
- Tests: `test_embed_estimate_is_measured.py` in fichero-server/tests/unit/search/ (to write)
- Size: S

#### Step 1.14 — A vector index and smaller vectors past about 500,000 rows (#6793)
- Behaviours: `search.scale.vector-index-when-large`
- Tests: `test_vector_index_when_large.py` in fichero-server/tests/perf/ (to write)
- Depends on: 1.4
- Size: M

#### Step 1.15 — Keyword results first, meaning when ready; a measured trial of the system embedder (#6794)
- Behaviours: `search.adopt.keyword-now-meaning-when-ready`, `search.adopt.system-embedder-as-small-tier`
- Tests: `KeywordFirstResultsTests.swift` in fichero/Tests/Unit/general/Views/ (to write)
- Depends on: 1.7
- Size: M

### Stage 2 — The older issues of milestone `search`

#### Step 2.1 — The search field is always visible and ⌘F finds (#6729)
- Behaviours: `search.always-visible`, `search.keyboard.command-f-finds`
- Tests: `SearchFieldAlwaysVisibleTests.swift` in fichero/Tests/Unit/general/Views/ (to write)
- Depends on: 1.2
- Size: S

#### Step 2.2 — A hit opens its page at the passage, with the region lit (#5744, #4604)
- Behaviours: `search.anchor-carries-page-id`, `search.click-result-to-highlighted-region`
- Tests: `test_search_anchor_page_id.py` in fichero-server/tests/unit/search/ (to write), `SearchHitLightsTheRegionTests.swift` in fichero/Tests/Unit/general/Views/ (to write)
- Size: M

#### Step 2.3 — Old spellings and reading levels in the folded copy (#3313, #3312)
- Behaviours: `search.match.old-spellings`, `search.match.reading-levels`
- Tests: `test_old_spellings_fold_alike.py` in fichero-server/tests/unit/search/ (to write)
- Depends on: 1.4
- Size: M

#### Step 2.4 — Results load as you scroll under one toolbar button; images are results (#5028, #5024, #4118)
- Behaviours: `search.results-load-as-you-scroll`, `search.one-toolbar-button-with-the-kind-menu`, `search.images-artifacts-as-first-class-results`
- Tests: `SearchResultsLoadAsYouScrollTests.swift` in fichero/Tests/Unit/general/Views/ (to write), `test_artifacts_are_search_results.py` in fichero-server/tests/unit/search/ (to write)
- Size: M

#### Step 2.5 — The search model: chosen at the Search step, changed by a re-embed run, failing out loud, built when idle (#6249, #6144, #6122, #4395, #5820)
- Behaviours: `search.embedding.chosen-at-project-creation`, `search.embedding.choices-come-from-the-engine`, `search.embedding.change-is-a-re-embed-run`, `search.embedding-failure-honesty`, `search.adopt.index-when-idle`
- Tests: fichero/Tests/Unit/general/Models/EmbeddingChangeStoreTests.swift, fichero-server/tests/unit/db/test_embedding_chosen_per_project_6122.py
- Size: M

#### Step 2.6 — A failed index build is a failed job; the built-in library has one name (#5315, #4891)
- Behaviours: `search.index-build-failure-is-a-failed-job`, `search.built-in-library-has-one-name`
- Tests: `test_index_build_failure_is_a_failed_job.py` in fichero-server/tests/unit/search/ (to write)
- Size: S

#### Step 2.7 — Related terms and related documents (#4604, #4606)
- Behaviours: `search.query-expansion-related-terms`, `search.find-related-documents`
- Tests: `test_related_terms_and_documents.py` in fichero-server/tests/unit/search/ (to write)
- Size: M

#### Step 2.8 — Passages and the graph in one ranking (#1833, #1824)
- Behaviours: `search.passage-chunking-kg-fusion-ranking`, `search.unify-retrieval-as-one-index`
- Tests: `test_one_ranking_over_passages_and_graph.py` in fichero-server/tests/unit/search/ (to write)
- Depends on: 1.10
- Size: M

#### Step 2.9 — One search across the open libraries (#4110)
- Behaviours: `search.all-libraries-fanout`
- Tests: `test_all_libraries_fanout.py` in fichero-server/tests/unit/search/ (to write)
- Size: M

#### Step 2.10 — Reading tools: concordance, the vector-space view, the Reader's graph view (#1812, #878)
- Behaviours: `search.corpus-linguistics-tools`, `search.vector-space-visualization`, `search.reader-graph-view-restored`
- Tests: `test_kwic_concordance.py` in fichero-server/tests/unit/search/ (to write), `VectorSpaceViewTests.swift` in fichero/Tests/Unit/general/Views/ (to write)
- Size: M

#### Step 2.11 — A real archive search seen in the app closes the residue issues (#4604, #4236, #4118, #4119, #4114)
- Behaviours: `search.residue-issues-stay-open`
- Tests: fichero-server/tests/unit/api/test_routes_search.py
- Depends on: 2.10
- Size: S

## Behavior counts

76 behaviors (recounted 2026-11-20): **13 OK, 21 PARTIAL, 25 GAP, 17 BROKEN.**

## Redirect, not folded here

- **#3309** (document date attribute + extraction → sort library & search by date) —
  **redirected to `source/historical-text-normalization.md`**, which already owns this exact ground
  (`histnorm.dates.jdn-core`, `histnorm.dates.wired-at-import`, `histnorm.dates.search-and-
  sort`, citing #3309 itself). Not re-litigated here; this spec's own search-view sort control
  reads whatever that spec's JDN columns provide.

## Fold record for the 12 + 1 issues (Pass 2 — executed 2026-09-19)

All by NUMBER, re-pulled fresh before executing: #17 held exactly the same 9 issues, #186 the
same 2, #129 the same 1 — no drift since Pass 1. 11 issues moved onto #319, plus #4236 (which
had been waiting on this spec since the `library-view-modes` fold); #3309 stayed on #129,
redirected elsewhere per above. **#17 ("Search View") and #186 ("Search View - Engine") both
reached zero open issues and were closed.** #129 ("Search View - Saved Searches") retains 1
open issue (#3309) and was not closed. No issue was closed by this pass — every "already built"
finding was posted as GitHub-comment evidence with "Left OPEN; not closing myself."

**Moved onto #319, each now backing a named behavior above:**
- #878 → `search.vector-space-visualization`
- #1782 → `search.exact-match-boost`
- #1812 → `search.corpus-linguistics-tools`
- #1824 → `search.unify-retrieval-as-one-index`
- #1833 → `search.passage-chunking-kg-fusion-ranking`
- #4114 → `search.smart-folders-as-sidebar-folders`
- #4118 → `search.four-leg-response` (OK half) + `search.images-artifacts-as-first-class-
  results` (PARTIAL half). **Verify-close comment posted**, naming `TestEnhancedSearch`/
  `TestHonestCounts`; stays OPEN — the images-as-first-class mapping specifically was not
  independently confirmed.
- #4119 → `search.real-relevance-signal-exists`
- #4236 → `search.zero-results-for-visible-text` — the ONE new behavior this pass adds,
  tagged BROKEN, stating only what is known: a search can return 0 results for text the
  Inspector shows for the same document; the cause is undiagnosed; the issue's own three
  candidates (scope, case sensitivity, page-child text not indexed) need different fixes and
  none is picked here. Diagnosis is separate, follow-up work against a real test library.
- #4395 → `search.embedding-failure-honesty`. **Verify-close comment posted**, naming the
  `EmbedOutcome` fix and its own code comment citing this issue; stays OPEN — the
  "fail loudly on infrastructure failure" and recoverable-re-embed (#4302) asks were not
  independently re-verified.
- #4604 → `search.native-toolbar-field`, `.query-syntax-prefixes`, `.query-expansion-related-
  terms`, `.results-render-as-library-nodes`, `.click-result-to-highlighted-region`,
  `.vector-space-visualization`, `.smart-folders-as-sidebar-folders`, `.reader-graph-view-
  restored`. **Verify-close comment posted**, naming the FIELD & SCOPES and RESULTS sections as
  built (with test classes) and the NAVIGATION section's own "big missing feature" framing as
  still not built; stays OPEN.
- #4606 → `search.find-related-documents`. **Scope-narrowing comment posted** (not a
  verify-close): the engine endpoint and an Inspector-tab UI both exist, but not the
  COLUMN-VIEW surfacing this issue specifically asked for — a different surface, same data.

**Redirected, not moved:**
- #3309 → `source/historical-text-normalization.md` (see above); left on #129.

**Milestones closed**: #17 ("Search View", 61 closed / 0 open), #186 ("Search View - Engine",
6 closed / 0 open).

## Rulings

- **2026-10-04 (#5315):** a failed full-text index build is never only a log line: it shows as a
  failed job in Activity and in the project's health, each with Retry
  (`search.index-build-failure-is-a-failed-job`).

## Future (ideas, not scheduled)
- (#4167, closed as not planned) Index documents, entities and notes into system Spotlight via App Intents and CoreSpotlight with deep links; depends on view URLs (#4171). What is taken from the system's index instead is in section K.

## Triaged from the backlog (2026-10-04)
- `search.all-libraries-fanout` — **[GAP]** (#4110) an engine endpoint fans a search out across open libraries with normalised scores and library_path provenance per result, enabling the All Libraries scope.
- `search.one-toolbar-button-with-the-kind-menu` **[PARTIAL]** (#5024; built 12c8096f8, OneToolbarSearchItemTests; not yet seen in the app): the toolbar has one search button; its menu holds Ask and Keyword with a checkmark and whatever the second button offered, and the Ask/Keyword bar under the toolbar is gone (this replaces `search.ask-keyword-native-scopes`).
- `search.results-load-as-you-scroll` **[GAP]** (#5028): search results have no 'Load 50 more' button; the next page loads as the end of the list comes into view, with a quiet Loading row, and the header gives the total.
- `search.index-build-failure-is-a-failed-job` **[GAP]** (#5315): when building a project's full-text index fails, the build shows as a failed job in Activity, with its reason and Retry, and the project's health shows the index as failed with the same Retry; a failure is never only written to the log. (Ruled 2026-10-04.)

## Triaged from the August search plan (2026-10-17)
Built: KG fusion (#1833), min_score and streaming (#4236, #4604), batch regions. The residue is below.
- `search.anchor-carries-page-id` — **[GAP]** (#5744, #4604) `SearchAnchor` (`db/__init__.py`) has no `page_id`, so a hit cannot open its page or draw the passage heat map; passage vectors already carry page_id and character offsets. Test: a new test_search_anchor_page_id.py in `fichero-server/tests/unit/search/` (to write).
- `search.embedding.choices-come-from-the-engine` — **[PARTIAL]** (#6144) the search models a project may be made with, and the line saying what each is good for, are the engine's: `GET /api/search/embedding/models` lists every supported model, the recommended one first, with its short name and blurb, and needs no project (it answers before one exists), so the menu on Your project and the Change embedding model sheet read the same list; the app keeps a built-in list only as a fallback for an engine it cannot reach (`db.embeddings.embedding_model_choices`, `fichero-server/tests/unit/db/test_embedding_chosen_per_project_6122.py::test_the_models_route_lists_every_supported_model_with_its_blurb_before_any_project_exists`). Owed: the app reading it (Swift, in this change).
- `search.embedding.chosen-at-project-creation` — **[PARTIAL]** (#6249, APPROVED 2026-10-28 by the maintainer, who found the Search step offers no embedder choice; #6122 built the engine side, tested: `fichero-server/tests/unit/db/test_embedding_chosen_per_project_6122.py`) a project's embedding model is chosen **once, at the Search step of Set Up**, and kept for the project: the Search stage's page ("Make vectors for search", `source.onboard.search-stage-says-what-is-embedded`) carries the one "Search model" menu, bge-m3 preselected and the other model beside it (multilingual-e5-large), each with one line of what it is, read from the engine (`search.embedding.choices-come-from-the-engine`), and a line saying that changing it later means embedding every page again. The choice is written to the project when the stage is saved (`PUT /api/search/embedding`, the audited `search.set_embedding_model`, which refuses a project that already holds vectors: `search.embedding.change-is-a-re-embed-run`); the engine keeps it in the package (`embedding.json`) and every embed and search of that project uses it; `GET /api/search/embedding` says which model the project uses, the models it may choose, and how many vectors it holds (documents, entities and claims: all three are stamped with the model); the Start plan's Search step and the model download use the project's model, not the engine's. **Set Up's first screen (Your project) asks nothing about search**, and a project whose recipe has no Search step is never asked; the engine's default (`FICHERO_EMBED_MODEL`, else bge-m3) applies only to a project that embeds with no choice made (one made before this, or one whose Search step was added later without choosing). `POST /api/library` no longer needs `embedding_model` for the app's path; the field stays for the CLI and for an existing project (which keeps its own choice). *Built, uncompiled (2026-10-28):* the Your project step's menu is gone and `NewProjectStore` sends no `embedding_model`; the Search stage page carries `SetupSearchModelField` (`fichero/fichero/Views/Onboarding/InspectorProjectEmbedding.swift`): while the project holds no vectors a pick is saved at once (`EmbeddingChangeStore.choose`, `PUT /api/search/embedding`), after that the model is said with Change… (the re-embed run's sheet) (`fichero/Tests/Unit/general/Models/EmbeddingChangeStoreTests.swift` theSearchStepSavesThePick; `NewProjectStore` has no `embeddingModel` left to send). *Left:* the engine test that a project with no Search step carries no choice; a real run. **Ruling 2026-10-28** (updates the owner ruling of 2026-10-25, "embedder at creation"): still chosen once and kept, but at the Search step of setup, not on the first screen. Tests to write: a Swift test that the Your project step has no Search model control and the Search stage page has one, and an engine test that a new project with a Search step saved carries the saved model while one without a Search step carries no choice.
- `search.embedding.change-is-a-re-embed-run` — **[PARTIAL]** (#6122; owner ruling 2026-10-25; engine built and tested: `fichero-server/tests/unit/db/test_changing_the_embedding_model_is_a_re_embed_run_6122.py` and `test_vector_swap_is_crash_safe_6122.py`; the app's action is built 2026-10-25 (Swift, needs compile: builder): the Inspector's project section says which search model the project uses and how many vectors it holds, and 'Change embedding model…' opens a sheet that shows the plan (pages, time estimate, cost, and that search keeps the old vectors until it finishes) before 'Embed every page again' starts the run and says where its progress shows; `EmbeddingChangeStore`, `InspectorProjectEmbedding`, `fichero/Tests/Unit/general/Models/EmbeddingChangeStoreTests.swift`) changing a project's embedding model after it holds vectors is never a silent switch and never mixes vectors. `GET /api/search/embedding/change-plan?model=` says first what it would do: the pages, passages, entities and claims to embed again, a time estimate (said as an estimate), the cost (none: it runs on this Mac) and that search keeps the old vectors until the run finishes. `POST /api/search/embedding/change` with `confirm: true` (the audited action `search.change_embedding_model`) queues the one `reindex` job (its progress, pages embedded of all, shows in Activity), which is `Database.migrate_embedding_space(to_model=...)` (the `search.reindex` action's migration, #4962; the same model is still its in-place rebuild): the new vectors are built in a shadow folder (`vectors-next`) in the new space while search reads the old ones, then swapped in whole under the vector lock as one crash-safe step (`db/vector_swap.py`: a begun-swap marker, the live folder moved to `-old`, the shadow moved in, the project's choice written atomically, the marker removed, and only then `-old` deleted; a failure puts the old vectors and the old model back at once, and a library opened after a crash finishes or undoes the swap before anything reads it), so every open connection sees the new model (the choice is keyed on `embedding.json`'s time). A page whose new vector is already written is never embedded again: a run stopped part-way is carried on from its shadow, and the pages that arrived during the run are caught up after the swap. A run that fails leaves the old vectors and the old model as they were, and says why on its row. `PUT /api/search/embedding` still refuses a project that holds vectors and points to this run.
- `search.residue-issues-stay-open` — **[PARTIAL]** (#4604, #4236, #4118, #4119, #4114) each is cited by its own entry above; none closes until a real archive search (a regional archive) is seen in the app. Test: `fichero-server/tests/unit/api/test_routes_search.py`.

## Triaged from the render review (2026-11-20)

- `search.name-and-statement-hits-are-their-own-rows` — **[GAP]** (#4604) see `kg/kg-rendering.md`, `kg.render.search-results-group-by-kind`: today a name or statement hit is folded into a document row, only when that document had no text hit (`ContentView.rowHits`), and opening it lights nothing (`openHitDocument`).
