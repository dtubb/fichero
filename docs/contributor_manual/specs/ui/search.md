# Search — Design Spec (#TBD)

> Milestone: search
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
- `search.ask-keyword-native-scopes` — **[OK]** Ask/Keyword are native `.searchScopes`, shown
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
- `search.embedding-failure-honesty` — **[PARTIAL]** (#4395) `EmbedOutcome` now distinguishes
  "no embeddable text" from "the embedding model failed to load," and the import summary reports
  an embedded count — two of the issue's four asks are clearly built. Not independently
  re-verified: whether an infrastructure-level embedding failure actually STOPS an import loudly
  (vs. continuing silently, document by document, each individually counted) — the calling loop
  at the ingest call site was not traced closely enough to say either way.
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

## Behavior counts

23 behaviors: **8 OK, 8 PARTIAL, 6 GAP, 1 BROKEN.**

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
