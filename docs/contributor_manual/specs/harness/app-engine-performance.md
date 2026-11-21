# App and engine speed: budgets, scenarios and where to profile — Design Spec (#6600)

> Milestone: Performance - Engine (engine and boundary behaviours); the app behaviours' issues go in
> `Performance - SwiftUI` and `Sidebar & Launch Performance`, as each line says.
> Manual: TBD — contributor-facing. What a user is told is one sentence per surface ("a folder of 50,000 pages opens as
> fast as a folder of 50"), and it waits for the budgets below to be met.
> Spec: companion to `building-fichero-locally.md` § "From `performance-sweep.md`". That spec owns HOW a figure is
> measured, stored, ratcheted and filed (the row shape, the workloads table, the noise band, the filing rule). This spec
> owns WHAT the product must do: the scenario, the budget figure, the place to profile and the test that pins it.

> Design-led (Testing Constitution). **Status: DRAFT — awaiting approval.** Written from the profiling review of
> 2026-11-21 (the owner asked for it). Every figure marked *measured* was taken that day on an M4 with 24 GB, against
> the engine's own test app in one process (`TestClient`, so no socket), on generated rows only; nothing was read from
> a real library. A figure with no *measured* beside it is a budget, not a finding.
> Tags: **[OK]** built and pinned by a test · **[PARTIAL]** built, not pinned or not wired · **[GAP]** not built.
> `→ #NEW-n` names an issue the review asks the manager to file; the number beside it is the tracked parent until then.

## Intent

The app should feel the same at 50,000 pages as at 50. The canvas speed-up of 2026-11-17 showed the method that works
here, and this spec makes it the rule for every surface: **measure the stutter, name the cause, fix it, pin it with a
test.** That work measured 49 hitches in 40 s of zooming, found that 27 of the 35 long ones lined up with the sidebar
re-drawing about once a second, changed each sidebar row to observe only its own activity, and left a test
(`SidebarRowActivityChurnTests`) that fails if a store change re-draws a row it did not change.

Three things were missing for the rest of the product, and this spec adds them:

1. **Scale.** No perf test ran above 200 documents (`fichero-server/tests/perf/`: 50, 100 and 200 documents; one page of
   20,000 shapes). The costs that hurt are the ones that grow with the library, and they do not show at 200.
2. **Budgets per surface.** `scripts/perf_baseline.json` holds tolerances and no figures. A ratchet with no budget
   keeps a slow thing exactly as slow as it is.
3. **Timers on every surface.** The app has six timed interactions (`InteractionProfile.Phase`: sidebar selection
   commit, selection to content, content data load, sidebar expand, preview swipe to image, preview region press) and
   a full launch timeline (`LaunchProfile`). The Items list, the Reader, the segment editor, the Activity pane, the
   inspector and search have none. The engine times five call sites (`perf_span`); the other routes log nothing.

## Prior art

- Apple's own tools, used as they come: `os_signpost` intervals on the Points of Interest track, `xctrace` with the
  Time Profiler, SwiftUI, Hangs and Allocations templates, `XCTOSSignpostMetric` and `XCTApplicationLaunchMetric` with
  `.xcbaseline` files. Nothing here invents a timer where one of these exists.
- The response-time limits every desktop toolkit is designed to (Nielsen; Apple's Human Interface Guidelines):
  **16 ms** for a frame while something moves under the pointer, **100 ms** for a press to show its result,
  **1 s** before a person's attention leaves. The budgets below are these three figures, applied per surface.
- Paged listings with a lean row and a cursor (Mail, Finder, every database client): the list asks for what is on
  screen. `#5260` already asks for this.
- DuckDB's own aggregation and `LIMIT`, and its full-text search extension, instead of reading every row into Python.
- `pyinstrument` and `py-spy` for the engine (`perf-sweep.source.engine-profiles`). py-spy needs root on macOS; it is
  used only where the owner allowed it (2026-11-15).

## Scenarios

One table, so a budget always names its scenario. The engine scenarios extend the sweep's workload set
(`perf-sweep.workload.set`, W1–W10) as W11–W14; the app scenarios extend it as W15–W19. All run on generated rows
(`speed.engine.scale-workloads`).

| Id | Scenario | Corpus |
|----|----------|--------|
| W11 | List one folder: the first 200 rows, then the whole folder | one folder of 5,000 pages; one of 50,000 (1.5 KB of text a page) |
| W12 | Full-text search, three queries, on pages with no vectors yet | the same two |
| W13 | List the shapes of one dense page | a page of 5,000 shapes; one of 20,000 |
| W14 | Save 1,000 Activity events while housekeeping runs | a library with 10,000 past runs and 100,000 events |
| W6 | Launch, cold, to the front library listed (exists) | the 5,000-page library |
| W7 | Sidebar: click five rows, expand three folders (exists) | 500 folders (50 boxes of 10) |
| W9 | Items list and grid: select the folder, scroll to the end (exists, extended) | 5,000 and 50,000 |
| W10 | Activity pane open while a run streams 200 updates (exists) | W14's library |
| W15 | Reader: open a long text, type ten characters, select a line | one text of 100,000 characters |
| W16 | Segment editor: open the page, drag one handle for two seconds | W13's 5,000-shape page |
| W17 | Inspector: step through 20 items with the arrow keys, 10 a second | the 5,000-page folder |
| W18 | Search: type a six-letter word at five characters a second, press Return | the 5,000-page library |
| W19 | Live window resize for two seconds with a 5,000-row list showing | the 5,000-page folder |

## Behaviors

### Engine

- `speed.engine.scale-workloads` **[GAP]** (#5261, #6600 → #NEW-1) — W11–W14 exist as pytest drivers under
  `fichero-server/tests/perf/` and as rows of `harness.toml [perf.workloads]`, on a corpus generated by seed
  (`scripts/perf_fixture.py` gains `library(pages, folders, text_bytes)`; `scripts/perf_corpus.json` names
  `perf-scale-5k` and `perf-scale-50k`). Each driver seeds through the engine's own bulk writer (`Database.save_many`:
  *measured* 5,860 rows a second, so 50,000 pages seed in 8.5 s) and prints one `[perf]` line per route with p50,
  payload bytes and peak RSS. Today nothing above 200 documents is measured. Acceptance: the four drivers run on the
  build machine in under 4 minutes in total at 5,000 and under 12 at 50,000; a driver whose corpus hash differs is
  refused. Test (to write): the new test_scale_listing_perf file in fichero-server/tests/perf, `test_scale_search_perf`,
  `test_scale_segments_perf`, `test_scale_event_writes_perf`.
- `speed.engine.listing-is-paged` **[GAP]** (#5260) — the cost of listing a folder is the cost of the page asked for,
  not of the folder. Budget: the first 200 rows in **50 ms** at 5,000 and at 50,000 pages. *Measured:* `GET
  /api/documents/{id}/children?limit=200` 100 ms at 5,000 and **1,181 ms at 50,000**; `GET /api/documents?limit=200`
  the same. Cause: `limit` is applied to a Python list after every row of the folder has been read and built into a
  model (`fichero-server/src/fichero_server/api/routes/document/documents.py`: `get_children` slices `children[:limit]` after `_list_documents`;
  `list_documents` slices `docs[offset : offset + limit]`); about 80% of the time is `Database._hydrate_row` parsing each
  row's JSON columns. The order (`sort_order`, then the natural name order) must move into the query, or be stored as a
  sort key, for `LIMIT` to mean anything. Test (to write): the new test_scale_listing_perf file in fichero-server/tests/perf, case test_first_page_costs_the_same_at_5k_and_50k.
- `speed.engine.listing-row-is-lean` **[GAP]** (#5260) — a listing sends a row, not a document: no page text, no run
  history, no long metadata. Budget: **300 bytes a row**; 200 rows under 100 KB. *Measured:* 2.7 KB a row on generated
  pages with 1.5 KB of text (536 KB for 200 rows); the whole folder is **13.4 MB at 5,000 and 134 MB at 50,000**, and
  the app asks for the whole folder (`speed.boundary.listing-asks-for-a-page`). `summary=true` exists for agents and
  still sends 0.46 KB a row and takes longer (161 ms against 137 ms at 5,000), because it builds the full models first.
  Test (to write): the new test_scale_listing_perf file in fichero-server/tests/perf, case test_a_list_row_is_under_300_bytes.
- `speed.engine.search-without-vectors-is-indexed` **[GAP]** (#6600 → #NEW-2) — a full-text query answers in
  **200 ms at 5,000 pages and 500 ms at 50,000**, whether or not the pages have vectors. *Measured:* **6.0 s at 5,000
  and 62.5 s at 50,000** for each of three queries when no page has a vector yet (a fresh import, a library whose search
  model is missing or broken, or search turned off). Cause (`fichero-server/src/fichero_server/db/__init__.py::Database.search`, the "uncovered ids"
  branch): every page with no vector is fetched with its whole text and folded for accents one character at a time in
  Python (`_fold_for_search` and `_script_preserves_marks`: 66% of the time), on every query. The fix is one of: a
  stored folded-text column written when the text is written (`#3321` asks for it) with DuckDB's full-text index over
  it; or, as a first step, a SQL prefilter (`lower(page_content) LIKE`) so only matching rows are folded. Test (to
  write): the new test_scale_search_perf file in fichero-server/tests/perf, case test_a_query_over_unembedded_pages_meets_its_budget.
- `speed.engine.search-checks-hits-in-one-query` **[GAP]** (#6600 → #NEW-3) — whether a candidate is live, excluded or
  superseded by its pages is asked once for the whole candidate set. *Measured:* `_is_active_document_id` and
  `_has_indexed_page_children` run two or three single-row reads **per candidate** (`Database.get`, then `query` by
  parent): 3.8 s of a 12 s profiled query at 5,000 pages. Test (to write): the new test_scale_search_perf file in fichero-server/tests/perf, case test_statements_per_query_do_not_grow_with_hits.
- `speed.engine.folder-figures-come-from-sql` **[GAP]** (#6600 → #NEW-4) — a folder's rollup, outline and inspector
  cost the same in a library of 5,000 and of 50,000. Budget: **50 ms** each. *Measured:* rollup 165 ms and
  **1,740 ms**; outline 164 ms and **1,764 ms**; inspector on a folder 92 ms and **912 ms**. Cause
  (`fichero-server/src/fichero_server/api/routes/document/inspector.py::document_rollup` and `document_outline`): each reads every row of the documents,
  artifacts, claims and notes tables into models (`db.query(Document)` with no filter) and counts in Python; the
  inspector's share is `knowledge_entity_ids_scoped_to_documents` over every descendant id. The rollup is called once
  per row a person expands in the table (`LibraryOutlineModel.loadRollup`). Test (to write):
  the new test_scale_listing_perf file in fichero-server/tests/perf, case test_folder_rollup_outline_and_inspector_do_not_grow_with_the_library.
- `speed.engine.columns-read-only-what-was-asked` **[GAP]** (#6600 → #NEW-5) — `POST /api/library-items/columns` for 60
  rows reads those rows. *Measured:* 95 ms at 5,000 and **1,043 ms at 50,000**, for the same 60 ids and an 8.7 KB
  answer. Cause: `fichero-server/src/fichero_server/api/routes/library/items.py::library_item_columns` starts with `db.all(Document)`. Budget: **30 ms**.
  Test (to write): the new test_scale_listing_perf file in fichero-server/tests/perf, case test_columns_for_60_rows_do_not_grow_with_the_library.
- `speed.engine.segments-list-asks-once` **[GAP]** (#6600 → #NEW-6) — the shapes of a page come back with a fixed
  number of statements. Budget: **150 ms at 5,000 shapes, 600 ms at 20,000**, and under 400 bytes a shape. *Measured:*
  584 ms and 5.2 MB at 5,000; 2,283 ms and 20.6 MB at 20,000 (1.0 KB a shape). Cause
  (`fichero-server/src/fichero_server/api/routes/document/segment_readings.py::retired_readings_of`): one `db.get(Segment, id)` per word to find its
  line, 45% of the time; the rows are already in memory in the caller. Test (to write):
  the new test_scale_segments_perf file in fichero-server/tests/perf, case test_statements_do_not_grow_with_shapes.
- `speed.engine.writes-do-not-wait-on-housekeeping` **[GAP]** (#6178 → #NEW-7) — a job's small write (an Activity
  event, a job's detail) is never held more than **10 ms at p95** by background tidying. *Measured:* with 10,000 past
  runs, saving one event took 83 to 128 ms on average (the existing W5 driver: 46.6 s for 1,000), against 7 ms with
  200 runs; 723 of 724 samples of the writing thread were waiting at the transaction gate
  (`fichero-server/src/fichero_server/db/__init__.py::Database._execute`), held by `fichero-server/src/fichero_server/workflows/run_log_tidy.py::run`, the one-time tidy of old run logs (#5711), which moves 50
  runs per transaction. It steps aside for work on its lane that someone waits for; a job's own small write is not
  that. The insert itself is 2% of the time. The cost lasts until the old runs are moved (200 transactions for 10,000
  runs). The tidy must take smaller chunks and step aside while any job is running. Test (to write): the new test_scale_event_writes_perf file in fichero-server/tests/perf, case test_an_event_saves_within_budget_while_the_tidy_runs.
- `speed.engine.every-route-logs-its-duration` **[GAP]** (#6549) — every request writes one line with its route
  template, status, duration and answer bytes, in the `PERF` shape the sweep already reads
  (`perf-sweep.source.engine-perf-lines`). Today five call sites use `perf_span` (the two listings, the document view,
  the thumbnail and its route); search, segments, the inspector routes, columns and Activity log no time at all, so the
  hotspot table cannot rank them. Test (to write): the new test_request_duration_line file in fichero-server/tests/unit/api.
- `speed.engine.reads-do-not-grow-memory` **[GAP]** (#6316 → #NEW-8) — reading the listing routes once does not leave
  the engine holding the rows. Budget: **under 50 MB** added by W11. *Measured* (the test process, peak RSS): 639 →
  828 MB at 5,000 (+189 MB) and 1,066 → **1,920 MB at 50,000 (+855 MB)**. The paged listing removes most of it; the
  figure is held so it cannot return. Test (to write): the new test_scale_listing_perf file in fichero-server/tests/perf, case test_peak_rss_added_by_the_read_set.
- `speed.engine.thumbnail-hit-is-a-file-read` **[PARTIAL]** (#6600 → #NEW-9) — a thumbnail that exists is served in
  **10 ms**; one that must be made, in **300 ms** for a 12-megapixel JPEG, off the event loop. *Measured* (20 generated
  12 MP pages): made 215 ms p50 (587 ms the first), served 5.7 ms; the display image
  8 ms. Built and inside budget; no perf test holds it. Test (to write): the new test_thumbnail_perf file in fichero-server/tests/perf.
- `speed.engine.cold-start` **[OK]** — the engine answers `/api/health` within **3 s** of its process starting.
  *Measured:* 2.49 s (import of `api.main` 1.1 s of it). Test:
  `fichero-server/tests/perf/test_engine_cold_start_perf.py` (the ratchet holds its best time).

### The boundary between app and engine

- `speed.boundary.calls-per-action-are-held` **[GAP]** (#6600 → #NEW-10) — the number of requests and the bytes
  received for one user action are counted by a test and may only fall. Budgets: select a folder, **2 requests and
  150 KB**; select an item, **3 requests**; one typed character in search, **no request**; Return, **2 requests**; the Activity pane, **1 request per update and none when nothing changed**; launch to the front library
  listed, **12 requests**. A mock URL protocol that records every request (the pattern of `EntityServiceTransportTests`) is enough, so
  this needs no engine. Test (to write): the new RequestsPerActionTests file in fichero/Tests/Unit/general/Perf.
- `speed.boundary.listing-asks-for-a-page` **[GAP]** (#5260 → #NEW-11) — the app asks for the rows on screen and the
  next page as it scrolls. Today `DocumentService.getChildren` sends no `limit`
  (`fichero/fichero/Services/DocumentService.swift`), every caller takes the whole folder as whole documents, the conversion
  to the app's model runs on the main actor (`DocumentService` is `@MainActor`), and
  `DocumentStore.refreshPendingStatusesOnly` fetches the whole folder again after each burst of activity to update the
  rows that were pending. At 5,000 pages that is 13.4 MB per fetch; at 50,000, 134 MB. Depends on
  `speed.engine.listing-is-paged`. Test (to write): `RequestsPerActionTests` (a folder of 5,000 is listed in pages of
  200) and the new PendingStatusRefreshTests file in fichero/Tests/Unit/general/Models (the refresh asks by `ids`, which the
  route already supports: *measured* 5.4 ms for 50 ids).

### App

- `speed.app.every-surface-has-a-timer` **[GAP]** (#6370 → #NEW-12) — each surface below has a named
  `InteractionProfile` phase, so Instruments, the log reader and `XCTOSSignpostMetric` all see the same interval. New
  phases: `library first screen` (selection commit to the first rows drawn), `library scroll` (per page fetched),
  `reader open`, `reader keystroke`, `segment editor open`, `segment drag tick`, `activity update`, `inspector load`,
  `search keystroke → results`, `window resize frame` (#6548 timed it once by hand). The six existing phases keep
  their names. Test (to write): the new InteractionPhaseCoverageTests file in fichero/Tests/Unit/general/Perf (every case has a
  signpost name and a call site).
- `speed.app.launch-meets-its-budget` **[GAP]** (#6371) — on a release build, cold, W6: first frame within **1.5 s**,
  engine bound within **4 s**, the front library listed within **6 s**, and the sidebar built **at most 3 times**.
  The only timings are from a debug build under load (#6371: 11.0 s, 26.9 s, 28.3 s, about 25 builds). The milestones
  exist (`LaunchProfile`); the perf plan and its baseline do not (`perf-sweep.source.xctest-metrics`). Test:
  `fichero/Tests/UI/general/Launch/LaunchPerformanceUITests.swift` gains the three milestone budgets;
  `fichero/Tests/Unit/general/Models/LaunchLoadOrderTests.swift` gains the build count.
- `speed.app.sidebar-with-500-folders` **[GAP]** (#4544, #4545, #4573 → #NEW-13) — W7 on 500 folders: selection commit
  within **16 ms**, expand within **100 ms**, expand-all within **1 s**, and a store change re-runs only the rows whose
  own values changed (the rule `SidebarRowActivityChurnTests` proved for activity, applied to every value a row
  reads). Test (to write): the new SidebarRowBodyCountTests file in fichero/Tests/Unit/general/Views/Sidebar.
- `speed.app.items-list-at-5k-and-50k` **[GAP]** (#5260 → #NEW-14) — W9: the first rows are drawn within **200 ms** of
  the click at 5,000 and at 50,000; scrolling to the end has **no hitch over 100 ms**; sorting and filtering never run
  over the whole folder on the main actor during a render; a thumbnail is decoded off the main actor at the size it is
  drawn. Test (to write): the new ListAtScaleTests file in fichero/Tests/Unit/general/Views/Library and the perf plan's W9.
- `speed.app.reader-with-a-long-text` **[GAP]** (#6600 → #NEW-15) — W15: a text of 100,000 characters opens within
  **300 ms**; a keystroke and a selection change each cost under **16 ms** on the main actor, whatever the length.
  Test (to write): the new ReaderLongTextTests file in fichero/Tests/Unit/general/Views/Reader.
- `speed.app.segment-editor-with-5000-shapes` **[GAP]** (#6600 → #NEW-16) — W16: the page draws within **500 ms** of
  its shapes arriving; a drag tick costs under **16 ms** and re-draws only the shape being dragged. Test (to write):
  the new SegmentEditorScaleTests file in fichero/Tests/Unit/general/Views/Segments.
- `speed.app.activity-updates-only-what-changed` **[PARTIAL]** (#6178 → #NEW-17) — W10: 200 streamed updates re-run
  only the rows that changed, and an update that changes nothing writes nothing to the store. Built: the store
  compares before it writes (`fichero/fichero/Models/ActivityStore.swift`, `if backgroundJobs != snapshot.jobs`), and
  the jobs read runs every 2 s, or every 30 s when no window can be seen. Not built: one changed job replaces the whole
  `backgroundJobs` array, so every row that reads it re-runs every 2 s during a run; no test counts it. Test (to
  write): the new ActivityUpdateChurnTests file in fichero/Tests/Unit/general/Models.
- `speed.app.inspector-follows-the-selection` **[PARTIAL]** (#6600 → #NEW-18) — W17: the inspector shows the last
  item within **150 ms** of the last key; a fetch for an item no longer selected is cancelled; one selection sends
  at most **3 requests**. Built: each section loads in a `.task(id:)`, which cancels when the selection moves. Not
  built: every section asks for itself (51 `.task(id:)` sites under `Views/Inspector`; a selected segment starts one
  load each for its making, signs, editorial, hands, statements and groups sections), so one click is many requests,
  and nothing counts them. Test (to write): the new RequestsPerActionTests file in fichero/Tests/Unit/general/Perf
  (the W17 case).
- `speed.app.search-keeps-up-with-typing` **[GAP]** (#6600 → #NEW-19) — W18: a typed character re-runs only the
  search field and sends nothing; Return sends one search and at most one batch for the hits not already loaded; a
  newer query's results replace an older one's; results appear within **300 ms** of Return at 5,000 pages (it needs
  `speed.engine.search-without-vectors-is-indexed`). Built: the search runs on Return, a superseded query is dropped
  and the hits are fetched in one batch (`fichero/fichero/Views/Shell/ContentView/ContentView+SearchResults.swift`).
  Not built: the field's text is `@State` on the root view (`fichero/fichero/Views/Shell/ContentView/ContentView.swift`,
  `toolbarSearchText`), so each key re-runs `ContentView`'s body; and nothing times Return to results. Test (to write):
  the new SearchTypingTests file in fichero/Tests/Unit/general/Models.
- `speed.app.window-resizes-smoothly` **[GAP]** (#6548) — W19: no frame over **33 ms** during a live resize with
  5,000 rows listed. *Measured* before (#6548): frames averaging 88 to 371 ms. Test: named in #6548.

### The rung

- `speed.rung.every-batch-is-profiled` **[GAP]** (#6600 → #NEW-20) — what "profile every batch" runs, by itself:
  1. **Every batch that touches `fichero-server/`:** W11–W14 at 5,000 on the build machine (about 4 minutes), plus the
     existing engine perf tests; each figure against its budget above (a budget is a ceiling: red when over) and
     against its ratchet (`perf-sweep.ratchet.*`: red when slower than the held median by more than the band).
     pyinstrument output is kept for the reviewer; nothing needs root.
  2. **Every batch that touches `fichero/`:** the unit tests of this spec (body counts, churn, requests per action),
     which need no GUI and run with the batch's Swift tests; then, on the build machine's GUI session, W6, W7 and W9
     through the perf test plan with `XCTOSSignpostMetric` on this spec's phases.
  3. **Nightly, not per batch:** the 50,000 corpus, W15–W19 under `xctrace` (Time Profiler, SwiftUI, Hangs,
     Allocations), memray on W11, and py-spy on the one machine where the owner allowed it.
  A scenario that did not run is `not-run` with its reason, never green (`perf-sweep.rung.not-run-is-visible`). Never
  on the manager's Mac. Test: a new case in the builder's test_perf_rung file, test_the_batch_rung_picks_scenarios_by_the_paths_a_batch_touches.

## Budgets in one table

| Surface | Scenario | Budget | Measured 2026-11-21 (5,000 / 50,000) | Tool that shows the cause | Pinned by |
|---------|----------|--------|---------------------------------------|---------------------------|-----------|
| Folder listing, first 200 rows | W11 | 50 ms, 100 KB | 100 ms / 1,181 ms; 536 KB | pyinstrument on `_list_documents` | `test_scale_listing_perf` |
| Folder listing, whole folder (as the app asks today) | W11 | not asked for | 137 ms, 13.4 MB / 1,609 ms, 134 MB | the same | `RequestsPerActionTests` |
| Full-text search, no vectors | W12 | 200 ms / 500 ms | 6,002 ms / 62,462 ms | pyinstrument on `Database.search` | `test_scale_search_perf` |
| Folder rollup, outline, inspector | W11 | 50 ms each | 165, 164, 92 ms / 1,740, 1,764, 912 ms | pyinstrument | `test_scale_listing_perf` |
| Columns for 60 rows | W11 | 30 ms | 95 ms / 1,043 ms | pyinstrument | `test_scale_listing_perf` |
| Shapes of a page (5,000 / 20,000 shapes) | W13 | 150 ms / 600 ms | 584 ms, 5.2 MB / 2,283 ms, 20.6 MB | pyinstrument; statement count | `test_scale_segments_perf` |
| One event saved during housekeeping | W14 | 10 ms p95 | 83–128 ms mean (10,000 runs) | a sampler over every thread; py-spy `dump` where allowed | `test_scale_event_writes_perf` |
| One page, its inspector, its KG | W11 | 20 ms each | 2.7, 4.0, 3.3 ms (met) | — | existing `test_entity_detail_perf.py` |
| Engine memory added by the read set | W11 | 50 MB | +189 MB / +855 MB | memray | `test_scale_listing_perf` |
| Thumbnail made / served | — | 300 ms / 10 ms | 215 ms / 5.7 ms (met) | `PERF library.thumbnail.ensure` | `test_thumbnail_perf.py` |
| Engine cold start | — | 3 s | 2.49 s (met) | `python -X importtime` | `test_engine_cold_start_perf.py` |
| Launch | W6 | 1.5 s / 4 s / 6 s | not measured on a release build | App Launch template; `LaunchProfile` | `LaunchPerformanceUITests` |
| Sidebar | W7 | 16 ms commit, 100 ms expand | not measured | SwiftUI template (body counts) | `SidebarRowBodyCountTests` |
| Items list and grid | W9 | 200 ms first rows; no hitch over 100 ms | not measured | Time Profiler + Hangs; SwiftUI | `ListAtScaleTests` |
| Reader | W15 | 300 ms open; 16 ms a key | not measured | Time Profiler | `ReaderLongTextTests` |
| Segment editor | W16 | 500 ms draw; 16 ms a tick | not measured | Time Profiler; SwiftUI | `SegmentEditorScaleTests` |
| Activity pane | W10 | only changed rows re-run | not measured | SwiftUI template | `ActivityUpdateChurnTests` |
| Inspector | W17 | 150 ms after the last key | not measured | signpost `inspector load` | `RequestsPerActionTests` |
| Search typing | W18 | a key re-runs only the field; 300 ms from Return | not measured | signpost `search keystroke → results` | `SearchTypingTests` |
| Window resize | W19 | 33 ms a frame | 88–371 ms (#6548) | Time Profiler + Hangs | #6548's test |

## Build order

### Stage 1 — Engine: measure at scale, then fix what grows with the library

#### Step 1.1 — The scale workloads and a duration line on every route
- Behaviours: `speed.engine.scale-workloads`, `speed.engine.every-route-logs-its-duration`
- Tests: fichero-server/tests/perf/test_scale_listing_perf (new), fichero-server/tests/perf/test_scale_search_perf (new), fichero-server/tests/perf/test_scale_segments_perf (new), fichero-server/tests/perf/test_scale_event_writes_perf (new), fichero-server/tests/unit/api/test_request_duration_line (new)
- Size: M

#### Step 1.2 — Search without vectors
- Behaviours: `speed.engine.search-without-vectors-is-indexed`, `speed.engine.search-checks-hits-in-one-query`
- Tests: fichero-server/tests/perf/test_scale_search_perf (new)
- Depends on: 1.1
- Size: M

#### Step 1.3 — The paged, lean listing
- Behaviours: `speed.engine.listing-is-paged`, `speed.engine.listing-row-is-lean`, `speed.engine.reads-do-not-grow-memory`
- Tests: fichero-server/tests/perf/test_scale_listing_perf (new)
- Depends on: 1.1
- Size: M

#### Step 1.4 — Folder figures and columns from SQL
- Behaviours: `speed.engine.folder-figures-come-from-sql`, `speed.engine.columns-read-only-what-was-asked`
- Tests: fichero-server/tests/perf/test_scale_listing_perf (new)
- Depends on: 1.1
- Size: S

#### Step 1.5 — Shapes of a page, and the thumbnail figure held
- Behaviours: `speed.engine.segments-list-asks-once`, `speed.engine.thumbnail-hit-is-a-file-read`
- Tests: fichero-server/tests/perf/test_scale_segments_perf (new), fichero-server/tests/perf/test_thumbnail_perf (new)
- Depends on: 1.1
- Size: S

#### Step 1.6 — Writes do not wait on housekeeping
- Behaviours: `speed.engine.writes-do-not-wait-on-housekeeping`
- Tests: fichero-server/tests/perf/test_scale_event_writes_perf (new)
- Depends on: 1.1
- Size: S

### Stage 2 — The boundary: count the calls, then ask for less

#### Step 2.1 — Requests per action, held by a test
- Behaviours: `speed.boundary.calls-per-action-are-held`
- Tests: fichero/Tests/Unit/general/Perf/RequestsPerActionTests (new)
- Size: S

#### Step 2.2 — The app lists in pages
- Behaviours: `speed.boundary.listing-asks-for-a-page`, `speed.app.items-list-at-5k-and-50k`
- Tests: fichero/Tests/Unit/general/Perf/RequestsPerActionTests (new), fichero/Tests/Unit/general/Models/PendingStatusRefreshTests (new), fichero/Tests/Unit/general/Views/Library/ListAtScaleTests (new)
- Depends on: 1.3, 2.1
- Size: M

### Stage 3 — App: a timer on every surface, then each surface to its budget

#### Step 3.1 — Timers on every surface, and the launch budget
- Behaviours: `speed.app.every-surface-has-a-timer`, `speed.app.launch-meets-its-budget`
- Tests: fichero/Tests/Unit/general/Perf/InteractionPhaseCoverageTests (new), fichero/Tests/UI/general/Launch/LaunchPerformanceUITests.swift, fichero/Tests/Unit/general/Models/LaunchLoadOrderTests.swift
- Size: M

#### Step 3.2 — Sidebar and Activity: only what changed re-runs
- Behaviours: `speed.app.sidebar-with-500-folders`, `speed.app.activity-updates-only-what-changed`, `speed.app.window-resizes-smoothly`
- Tests: fichero/Tests/Unit/general/Views/Sidebar/SidebarRowBodyCountTests (new), fichero/Tests/Unit/general/Models/ActivityUpdateChurnTests (new)
- Depends on: 3.1
- Size: M

#### Step 3.3 — Inspector and search follow the person
- Behaviours: `speed.app.inspector-follows-the-selection`, `speed.app.search-keeps-up-with-typing`
- Tests: fichero/Tests/Unit/general/Perf/RequestsPerActionTests (new), fichero/Tests/Unit/general/Models/SearchTypingTests (new)
- Depends on: 2.1, 3.1, 1.2
- Size: S

#### Step 3.4 — Reader and segment editor at size
- Behaviours: `speed.app.reader-with-a-long-text`, `speed.app.segment-editor-with-5000-shapes`
- Tests: fichero/Tests/Unit/general/Views/Reader/ReaderLongTextTests (new), fichero/Tests/Unit/general/Views/Segments/SegmentEditorScaleTests (new)
- Depends on: 3.1, 1.5
- Size: M

### Stage 4 — The rung

#### Step 4.1 — Profile every batch
- Behaviours: `speed.rung.every-batch-is-profiled`
- Tests: fichero-builder/tests/test_perf_rung.py
- Depends on: 1.1, 3.1
- Size: M

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | body counts, churn, requests per action, phase coverage | `fichero/Tests/Unit/general/Perf/…` and the files named per behaviour |
| Availability (Swift) | n | — | — |
| Backend (pytest) | y | the duration line | the new test_request_duration_line file in fichero-server/tests/unit/api |
| MCP | n | — | — |
| CLI | n | — | — |
| Click-around (XCUITest, Mac) | y | launch milestones; W7 and W9 through the perf plan | `fichero/Tests/UI/general/Launch/LaunchPerformanceUITests.swift` |
| iPhone (iOS) | n (simulator timings are recorded, never held: `perf-sweep.workload.set`) | — | — |
| iPad | n | — | — |
| Load (#4634) | y | W11–W14 budgets and ratchets | `fichero-server/tests/perf/test_scale_*_perf.py` |

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual | n (until the budgets are met) | — |
| Contributor | developer docs | y | this spec; `building-fichero-locally.md` for the method |
| AI / agent | MCP tool description | n | — |
| Scripter | CLI `--help` | n | — |
| Reference | capability reference | n | — |

## Open questions for the creative director

1. Is 50,000 pages in ONE folder a case to design for, or is 50,000 across many folders with at most about 5,000 in one
   the real shape? The budgets above hold for both; the order of the fixes changes (paging first, or folder figures
   first).
2. May a listing change its order rule so the database can page it? Today the order is `sort_order`, then a natural
   name order computed in Python. Paging needs either a stored sort key written when a name changes, or the
   database's own collation, which orders `Page 10` before `Page 9`.
3. Full-text search on pages with no vectors: is a stored, accent-folded copy of each page's text acceptable (about the
   size of the text again in the database), with DuckDB's index over it? The other choice keeps the size and stays
   slow for scripts where a plain SQL match cannot stand in for the fold.
4. The app budgets are for a release build on an M4. Should the 8 GB M1 be the machine the budgets are held on
   instead, with the M4 figures as report-only? It is the slower machine people will have.
5. Should the per-batch rung run the app scenarios (about 5 minutes on the GUI session) on every batch that touches
   `fichero/`, or only the unit tests per batch and the scenarios nightly?
