# STATE.md — Fichero

## Next Session — Start Here (2026-05-13 late autonomous)

**Latest commit on 0.0.2: `2e8ae135`.** Eleven commits today. Five GitHub
issues closed: #902, #885, #927, #959, plus citation-graph wiring for
#974. Test suite: **2392 passing, 14 failing** (was 1704 / 755 at start
of day — `/.session-end-complete` is way out of date because of that).

### What landed today

1. **`a7aa8a33` — #902 KG force-directed graph.** SwiftUI Canvas-based
   graph as a List/Graph picker in OntologyBrowser. Closed.
2. **`df629970` — #885 Kreuzberg extractor outputs.** Tables, slide
   text, transcripts, image OCR, keywords, annotations all persist as
   Artifact rows. 10 new tests. Closed.
3. **`c7d30be7` — STATE.md mid-day update.**
4. **`b967fa7d` — Citation graph service methods** (`inboundCitations` /
   `outboundCitations` on `EntityServiceGenerated`) for #974.
5. **`045460d5` — #927 PDF page-child thumbnails.** Aligned
   `DocumentThumbnailView` + `MapCard` with `MailStyleRow.resolvedParentPDFPath`
   so page children render the correct page when viewing a parent
   PDF's children. Closed.
6. **`a8f1aefd` — #959 KG-RAG Related Claims panel.** Inspector Info-tab
   section: for each of the doc's claims (up to 20), fetch top-3
   similar from `/api/kg/claim-search/{id}/similar`, dedup, rank, show.
   Closed.
7. **`ad053195` — Citations section on Info tab.** Renders inbound +
   outbound citations using the methods from #5. UI for #974 prep.
8. **`bf37e38d` — Test infra: disable auth in conftest + ruff F823.**
   Set `FICHERO_DISABLE_AUTH=1` before app import — recovered ~688
   previously-broken tests that the post-#742 loopback check was
   silently rejecting. Also fixed the F823 shadow-import in
   `workflows/tools/catalogue.py:481`.
9. **`dd0f5a34` — Removed 3 stale KG test files.** `/api/knowledge-graph/*`
   was deleted in 1587a1b6 (#832); test files for that namespace
   couldn't be salvaged (~1238 LOC).
10. **`4a5d0c22` — Updated `test_feature_tier_routing` +
    `test_routes_graph_exploration`** for the post-consolidation `/api/kg/*`
    shape: flat metrics response, `/path?source=&target=` not
    `/paths/{a}/{b}`.
11. **`8b97b80f` + `2e8ae135` — Empty/whitespace search query returns
    200 ("browse the index"), not 400.** Two test files updated to
    match the deliberate route behavior in `enhanced_search`.

### Open candidates (next session)

**Bounded:**
- Citation graph UI is in but the **inspector still shows "Citations" as
  an empty section** until citations are recorded for a doc. Nothing
  to fix — just confirm by adding a citation via the workflow.
- **#928** PDF loupe / magnifier — blocked on #783 (loupe fix first).
- **14 remaining test failures** clustered in:
  - `test_routes_settings` (6) — duckdb lock conflicts with running
    backend (the test fixture doesn't isolate `app.duckdb`).
  - `test_providers` + `test_api_providers` (4) — same duckdb lock.
  - `test_routes_entities_kg_integration` (3) — post-consolidation
    response shape drift (likely fixable in 20 min).
  - `test_chat_structured` (1) — Apple Intelligence error-hierarchy
    expectation; needs Apple Vision env.

**Blocked / decision-dependent:**
- **#963** first-person claims — blocked on #924 (author identity in
  extractor).
- **#886** search ranking — blocked on richer corpus.
- **#961** console hygiene — needs running app to verify.
- **#943** view stickiness — needs Daniel's call on scope.
- **#958** structured artifact editors — multi-day rewrite.

**Backend wiring follow-ups** (unwired-endpoint audit at
`agent-work/2026-05-13-unwired-endpoint-audit.md`):
- BibliographyService wrapper (5 endpoints).
- AnnotationService wrapper (4 endpoints).
- NotesService / TasksService / ProjectsService / SourcesService.

### Don't break

- `RelatedClaimsPanel` and `CitationGraphPanel` use `.task(id: documentId)`
  to re-fetch on selection change. Don't switch the parent to a
  value-copy view body that drops the task.
- `FICHERO_DISABLE_AUTH=1` is set in conftest before app import —
  moving the env-set after the import re-breaks ~688 tests.
- `OntologyBrowser.viewMode` is persisted via `@SceneStorage` —
  switching to `@AppStorage` would lose the per-window scope.

---

## Earlier next-session entry (2026-05-13 mid-day autonomous)

**Latest commit on 0.0.2: `df629970`.** Two streams shipped in a parallel
agent run (KG force-directed graph + extractor-artifact preservation).
Stream B (KG-RAG Related Claims inspector panel) drafted by an agent in
worktree but not landed — see "Stream B port — finish next session" below.

### What landed today
1. **#902 (partial #889) — KG force-directed graph view.** Adds SwiftUI
   Canvas-based force-directed layout as a second detail-pane mode in
   OntologyBrowser. Nodes are entities (filtered by the existing
   `hiddenKinds` set), edges derive from "appears together in a claim"
   with weight = co-occurrence count. Coulomb/Hooke physics over ~4s
   then freezes (no continued CPU). New segmented List/Graph picker
   in the toolbar, persisted via @SceneStorage. Folded into
   OntologyBrowser.swift because KnowledgeGraph is a plain PBXGroup
   not a synchronized one (per MEMORY [[feedback_swift_file_sync]]).
   Commit `a7aa8a33`.
2. **#885 — Preserve Kreuzberg extractor outputs as artifacts.** Tables,
   slide text, image OCR/descriptions, audio/video transcripts,
   keywords, and PDF annotations are now persisted as Artifact rows
   tied to the parent document (or, for PDF pages, to the page
   Document). New artifact kinds: kreuzberg_table, kreuzberg_transcript,
   kreuzberg_slide_text, kreuzberg_image_description, kreuzberg_keywords,
   kreuzberg_annotations. 10 new tests pass. Strictly additive — no
   schema or OpenAPI changes. Commit `df629970`.
3. **Unwired-endpoint audit** at
   `agent-work/2026-05-13-unwired-endpoint-audit.md` — 51 backend
   endpoints across 9 unwired groups (annotations, bibliography,
   citations, classifications, multilingual, notes, projects, tasks,
   sources). Citations + Bibliography are highest leverage next.

### Stream B port — finish next session

A parallel agent drafted `RelatedClaimsPanel.swift` (KG-RAG "Related
Claims" inspector section, #959 + claim-search hookup). It's preserved
at `.claude/worktrees/agent-a2fb80b6decdb56e0/fichero-swiftui/fichero-swiftui/Views/Library/DocumentInspector/RelatedClaimsPanel.swift`.

Port to current paths needs:
- Update `listClaimsApiKnowledgeGraphClaimsGet` →
  `library.entityService.listClaims(sourceDocumentId:limit:)`
- Update `findSimilarClaimsApiKnowledgeGraphClaimsClaimIdSimilarGet` →
  `client.api.findSimilarClaimsApiKgClaimSearchClaimIdSimilarGet(...)`
- DocumentInspector subdir is a plain PBXGroup; either inline the panel
  in DocumentInspector.swift (1005 lines, risky) or edit pbxproj.
- The agent's structure (DisclosureGroup with count badge, per-row
  claim text + italic source-doc + 0.00–1.00 score, tap → posts
  NotificationCenter for cross-pane nav) is solid; just retarget
  API surfaces.

### Agent-worktree base mismatch — root cause

All three agent worktrees were seeded off commit `5cebddf6` (PR #638
merge state, 560 commits behind `0.0.2` HEAD). That predated the
`fichero-swiftui/` → `fichero/` and `fichero-api/` → `fichero-engine/`
rename. So agent diffs cannot be merged directly — they need porting.
For future autonomous runs, either pin the worktree base explicitly
to `origin/0.0.2` or do the work directly without isolation.
See MEMORY note (to write): worktree-base-mismatch caveat.

### Don't break

- The graph view shares `selectedEntityId` with the entity list — both
  modes update each other. Don't break that binding.
- `_pending_artifacts` / `_kreuzberg_artifacts` metadata keys must be
  popped (not just read) so they never persist into the Document row.
- `_save_pending_artifacts` is called AFTER `db.save(doc)` so doc.id
  exists; same for `_save_pdf_page_artifacts` after `db.save(page_doc)`.
- Three agent worktrees still locked at `.claude/worktrees/agent-*` —
  can be `git worktree remove --force` after Stream B is ported.

### Pre-existing failures (not new)

- `test_activity.py::test_list_activities` fails on origin/0.0.2 in
  0.13s — unrelated to today's work.
- `ruff` F823 in `workflows/tools/catalogue.py:481` — pre-existing.

---

## Current Focus

**Branch:** `0.0.2` — latest commit `23fdd6a3` (2026-05-11 evening
autonomous: KG epistemology + ontology + verbatim source_text layer,
7 commits, #882 closed, #893 mostly shipped, #894 filed).

**Test suite:** 683 passing, 0 failing. Coverage 10.78% (was 9.20%
this morning — +1.58pp on the day).

**Headline (2026-05-11 / 2026-05-12 overnight — KG surface lit up):**
- #919 5c backend consolidation: /api/knowledge-graph deleted; 5
  new kg_* modules under /api/kg/*.
- EntityServiceGenerated rewired to new schema (no more dead service stubs).
- OntologyBrowser: Tools menu, '+' New Entity, Edit/Delete context
  menu, Curation History section, expandable claim cards with
  contradictions + evidence-chain, Heuristic Predictions Review
  Sheet (accept/reject writes KnowledgeClaimLink).
- DocumentInspector: verbatim source_text per claim — italicised
  tappable citation (#893 closed).
- Library + KG filter unified via @AppStorage (#887).
- save_claim within-page dedup (defense-in-depth for #896).
- Closed: #832, #888, #895, #887, #893, #729, #896, #891 (eight
  issues). Updated: #889 with rebuild blueprint pointing at
  OntologyBrowser as the new shell; #901 with shipped (entity
  PATCH/DELETE, claim DELETE) and pending (claim PATCH inline
  editing) status.
- **#896 root cause** found: shared cache key across page children
  collapsed pages 2-6 to page-1's cached result. Fix:
  compute_cache_key gains document_id parameter (2f58a4f8).
- **#891 architecture** verified in place: per-page fan-out +
  per-page extract_all + cache-key-by-page-id + within-page dedup.


- Backend KG namespace consolidation (1587a1b6); `kg` bucket = 45
  endpoints, old `knowledge-graph` bucket deleted.
- Swift API client regenerated against new schema. Build clean.
- `EntityServiceGenerated` extended with contradictions, evidence-chain,
  entity merge/split/audit, claim+entity embedding, heuristic
  predictions (66c8320a).
- `OntologyBrowser` gained a Tools menu (wrench icon): embed claims,
  embed entities, generate suggested links. Transient status string
  in the toolbar (bce81165).
- `EntityDetailView` gained a Curation History section — driven by
  `/api/kg/entity-curation/audit`, renders nothing when empty (bce81165).
- `ClaimSummaryCard` is now expandable: chevron toggle fetches
  contradictions + evidence-chain in parallel and shows inline (96a13e74).
- Dead Swift removed: `KnowledgeGraphServiceGenerated.swift`,
  `HermeneuticsServiceGenerated.swift`, and the orphan
  `ClaimInspector` / `EpistemologyGraph` / `PredictionReview` view
  dirs (2360 LOC of unbuildable cruft).
- GitHub issues closed: #832 (duplicate routers), #895 (toolbar
  accumulation), #888 (service-layer cleanup). #889 updated with
  rebuild blueprint pointing at OntologyBrowser as the new shell.

**Headline (2026-05-11 — late autonomous: KG namespace consolidation):**
- **#832 closed.** `/api/knowledge-graph/*` sub-package deleted; the
  five unique surfaces ported into focused single-purpose modules
  under `/api/kg/*`:
  - `kg_claim_search` — semantic claim search (embed + ?q= + similar)
  - `kg_claim_analysis` — contradictions + evidence-chain
  - `kg_entity_curation` — merge/split/audit/undo + semantic entity search
  - `kg_predictions` — heuristic predictions + run listing + apply
  - `kg_inclusion` — declarative library/folder/document scope rules
- Also deleted: `routes/interpretations.py` (CRUD + taxonomy already
  in `kg_interpretations.py`). Net ~8200 LOC removed.
- OpenAPI: `kg` bucket now 45 endpoints (was 29 + 33 split). Old
  `knowledge-graph` bucket gone.
- Kept (per Daniel): `graph_exploration.py`, `graph_traversal.py`,
  `graph_reasoning.py`, `hermeneutics.py`, `mind_palace.py`,
  `research_*.py` — unique features, not duplicates.

**Headline (2026-05-11 — autonomous day):**
- **OntologyBrowser wired (#498)** — Knowledge Graph sidebar entry
  per library, peer to Workflows + Activity. Two-pane content view:
  searchable entity list (left, with type-filter chips) + entity
  detail with claims (right). Uses canonical
  `library.entityService: EntityServiceGenerated` (`/api/entities` +
  `/api/claims`).
- **#884 fixed** — Transcribe node text-passthrough so `.md`/`.txt`
  files don't crash Catalogue with "cannot identify image file".
- **#882 shipped** — KG inspector entity names (People/Places/Orgs/
  Events) tap-to-search like keyword lozenges.
- **#883 partial** — Sidebar breathing room 8→12pt, MiniToolbar
  `.background(.bar)` + height 36→44pt to match NSToolbar, filter
  menu re-styled to actually appear in the toolbar.
- **240+ new frontend tests** across 14 files; coverage 9.20% → 9.94%
  (this session) → 12.37% (post-OntologyBrowser).

**KG follow-up filed:**
- **#888** KG service-layer cleanup (KnowledgeGraphServiceGenerated +
  HermeneuticsServiceGenerated need regenerating against current
  OpenAPI; method signatures + type names drifted significantly).
- **#889** KG view rewrites (ClaimInspector / EpistemologyGraph /
  PredictionReview / Hermeneutics targeted older schema; rewrite per
  current types after #888).
- **#729 partial** — `person:X` syntax already works end-to-end (Phase
  3 backend parser + #882 lozenge wire). Cross-doc detail page +
  graph viz remain.

**Other 0.0.2 bugs filed today:**
- **#881** Markdown ingest content missing (test once #884 fix verified)
- **#885** Preserve all extractor outputs as artifacts (Kreuzberg
  tables, A/V transcripts, slide text — tracking issue)
- **#886** Search filename-match ranking (verify with richer corpus)
- **#887** Unify KG-tab kind-filter and library-toolbar entity-filter

**Headline (2026-05-10):**
- **Search is real now.** L2-normalised cosine + RRF + accent-insensitive
  fold + query parser (phrases / scopes / NOT) + did-you-mean + per-folder
  filter + lozenge entity-scoped search + library-mode toolbar field +
  sidebar reorder.
- **5 new KG endpoints** pull #729 backend forward: `/entities/top`,
  `/entities/{id}/documents`, `/entities/{id}/co-occurrence`,
  `/entities/{id}/drill-down`, `/documents/{id}/related`.
- **NER per-page (local)** preset for folders of `.md` / `.txt` files —
  Apple Intelligence via `$small`, no transcribe step.
- **PDF backfill** route fixes old libraries with missing page children.
- **Test coverage:** 91 backend tests (unit + integration) + 31 frontend
  tests (unit). The integration test `TestRouteLevelEnhancedSearch`
  caught a real bug — single-phrase queries weren't enforcing the phrase.

**Goal:** Daniel bug-tests tomorrow (2026-05-11). After verifying the
search + KG flow on his field-notes library, we move toward release
packaging (#658–#660).

## Open Issues (0.0.2 milestone)

**Release pipeline (Daniel-blocked):**
| # | Title | Status |
|---|---|---|
| #658 | Set up fichero-releases GitHub repo | Needs Daniel to create repo |
| #659 | Build, sign, notarize 0.0.2 DMG | Blocked on #658 + Apple notarytool creds |
| #660 | Dry-run install 0.0.2 on Daniel's machine | Blocked on #659 |
| #661 | Add Fichero download page to tubb.ca | Content writing |
| #662 | Update tubb.ca/fichero with release notes | Content writing |

**Engineering — open or deferred:**
| # | Title | Status |
|---|---|---|
| #178/#803 | Phase C: page_cleanup tool | ✅ Shipped 2026-05-04 |
| #179/#804 | Phase D: folder_cleanup tool | ✅ Shipped 2026-05-04 |
| #180/#805 | Phase E: multi-output catalogue | ✅ Shipped 2026-05-04 |
| #806 | Duplicate Apple Intelligence in model picker | ✅ Closed (dedup at startup) |
| #807 | Phantom SourceKit "Self has no member" errors | ✅ Closed (3 real lint fixes) |
| #720 | Catalogue (composable) doesn't emit combined artifact | Resolved by Phase E (multi-output) |
| #721 | Inspector shows parent's container artifacts on child page | Inspector V2 ships per-doc strict scope |
| #702 | Drag-drop folder onto PDF row | Validation matrix, not started |
| #598 | Sidebar drop routes to selected row, not cursor target | Pending |

## In Progress

- Inspector V2 Phase 2 (#156): RTF-editable panels ✓, delete ✓, AI
  display attributes (deferred), per-type artifact payloads (deferred).

## Blocked

Nothing right now. Daniel needs to test the new pipeline end to end on
a real folder before the release packaging path opens up.

## In Progress

- **LLM-stack overhaul (#872 master plan)** — 15 issues closed overnight; archive in HISTORY.md.
- Inspector V2 Phase 2 (#156) — RTF panels shipped; AI display attributes + payload types still pending.

## Blocked

- #854 Apple Intelligence proactive token budgeting — waiting on macOS SDK 26.4 release.

**Decisions logged (Daniel approved):**
- Theme C: stay on fm-bridge as canonical Apple integration.
- Theme A: do the LLMProvider Protocol refactor — long-hall worth it.

## Branch reconciliation — DECISION (2026-05-08)

**Stay on 0.0.2. Re-implement the 0.0.3 features here.** Merging the
two branches surfaced 16 real conflicts (mostly across the directory
rename + file-splitting refactors that happened independently).
Re-implementing the 10 features from 0.0.3 directly on 0.0.2's path
structure is cleaner: each feature is a clean commit, every test
passes deterministically, no merge metadata noise.

The 0.0.3 worktree (`~/code/fichero-0.0.3`) stays as a frozen reference —
read its commits to see the implementation that needs porting. The
0.0.3 *branch* is effectively orphaned; its commits get re-derived on
0.0.2.

### Features to port from 0.0.3 (reference commits)

Read the diff at each commit in `~/code/fichero-0.0.3` then re-implement
on 0.0.2 paths. Path mapping: `fichero-swiftui/` → `fichero/`,
`fichero-api/` → `fichero-engine/` (Python isn't touched in any of
these — they're all Swift UI).

| Issue | 0.0.3 commit | What |
|---|---|---|
| #517 | `e80f00c6` | Library list/table/map re-enable + Finder-style search criteria strip |
| #518/#519 | `57981ec6` | Processing poll + Artifacts column |
| — | `4c51202e` | Resolve pre-existing OpenAPI schema migration build errors |
| #326 | `15786e4a` | Wire left/right pane navigation for list/table/map modes |
| #618 | `8c4cce4c` | Flatten sidebar row indentation to NNW-style near-flush |
| #602 | `a6b27e4e` | Sidebar sibling reorder via `.onMove` + shadow @State |
| #617 | `3487786b` | Per-column NNW-style toolbars (sidebar/content/inspector strips) |
| #593 | `e6c30600` | Swipe-to-navigate sibling documents in preview pane |
| #675 | `9af7994c` | `convertToSendable` preserves Date/URL/NSNumber types |
| #354 | `eaf1f99d` | Bound inspector close button hit area to its icon |

### Audit (2026-05-08): most are already on 0.0.2

After 0.0.3 shipped (Apr 23), 0.0.2 had ~2 weeks of work that
independently re-implemented most of these features under the new path
structure. Verified by grep on 0.0.2's tree:

| Issue | 0.0.3 commit | Status on 0.0.2 |
|---|---|---|
| #354 | `eaf1f99d` | **N/A** — bug doesn't apply; 0.0.2 uses standard SwiftUI ToolbarItem, not the InspectorColumnHeader HStack the fix targeted |
| #675 | `9af7994c` | **N/A** — `convertToSendable` lives in different file structure on 0.0.2; not the same code path |
| #602 | `a6b27e4e` | **✅ Done** — `.onMove` wired in `SidebarItemRow.swift:545` and `SidebarView+ViewComponents.swift:271`; MEMORY.md `feedback_onmove_shadow_state.md` documents the pattern |
| #326 | `15786e4a` | **✅ Done** — `cyclePaneFocus` in `ContentView+Actions.swift:15`; navigation wires through `onRequestPreviousPaneFocus` / `onRequestNextPaneFocus` |
| #617 | `3487786b` | **✅ Done** — `MiniToolbar.swift` exists in `Views/Toolbars/`; per-column toolbar pattern in place |
| #618 | `8c4cce4c` | **TBD** — verify sidebar indentation matches NNW-style |
| — | `4c51202e` | **TBD** — backend schema build errors; check if they apply to current llm.py / OpenAPI shape |

### Truly missing — port these (in suggested order)

| Issue | 0.0.3 commit | What | Notes |
|---|---|---|---|
| #519 | `57981ec6` | Artifacts column on document list | Half of the processing-poll / Artifacts commit; the column is the visible piece |
| #518 | `57981ec6` | Processing-status poll | Background poller updates document status; pairs with #519 |
| #593 | `e6c30600` | Swipe-to-navigate sibling docs in preview | Trackpad swipe → next/prev sibling; MEMORY.md `feedback_nsswipe_gesture_missing.md` notes NSSwipeGestureRecognizer doesn't exist on Swift macOS — must use `NSEvent.addLocalMonitorForEvents(matching: .swipe)` |
| #517 | `e80f00c6` | Library list/table/map view modes wired + Finder-style search criteria strip | **Highest-value piece for Search v1.** SearchCriteriaStrip.swift is the one new file. List/table view modes have skeleton on 0.0.2 (`ViewDisplayMode.table` enum case exists) but may need to be actually wired to render. |

### Then for Search v1 (#481)

After the criteria strip lands, add the actual `.searchable(text: $queryText, prompt: ...)` to SearchView so users can type queries (this is the original "input not wired" gap). 30-60min, all in `fichero/fichero/Views/Search/SearchView.swift`.

## Morning push (2026-05-12) — 12 fixes + 8 dedups

12 fixes shipped + pushed today:
- **#931** wf list description no longer truncates
- **#932** first-run AI Defaults auto-populated with Apple Intelligence
- **#935** three Apple model rows seeded (apple-intelligence / -vision / -speech)
- **#937** save_model idempotent on (provider_id, model_id) — no more duplicate adds
- **#946** PDF thumbnails show multi-page badge (paper-stack + count)
- **#952** mermaid 500 → graceful 204 with mermaid source in header
- **#957** Apple Vision OCR skipped when PDF has embedded text layer
- **#962** Apple Intelligence Generable failures promoted to AppleUnavailableError → \$large fallback
- **#962 follow-up** asyncio.Semaphore(3) throttle on concurrent fm-bridge calls
- **#964** OntologyBrowser toolbar moved inside entity list pane only
- **#965** \`.task(id: entityId)\` re-fires claim fetch on selection change
- **#966** /api/kg/* promoted from dev-tier to core (13 routers)

8 duplicates folded: #941+#942 → #943, #945 → #946, #950 → #952,
#953 → #957, #954 → #958, #955 → #959, #956 → #960.

26 unique open bugs remain in the morning queue.
20 new regression tests across pdf-text-layer, Apple-Intelligence
decode errors, save_model dedup. Three-leg green throughout.

## Next Session — Start Here (2026-05-12 afternoon hand-off)

**Latest commit on 0.0.2: `d41b178c`.** Four fixes shipped this afternoon
(#948 page checkmarks, #960 inspector heights, #967 backend offline,
ingest file types). Closed #948, #960, #967. Filed #975 (structured
transcript ingest — future milestone). Backlog: 17 open in 0.0.2.

### Start here

1. **Pull + Xcode rebuild.** Four Swift files touched in #948
   (DocumentStore + 4 SSE callsites) — clean build picks up the new
   helpers.
2. **Smoke-test #948**: run Catalogue on a multi-page PDF; spinner
   should now persist through extract_all NER and only flip green
   when workflow.complete fires.
3. **Smoke-test #967**: kill the engine mid-session (`lsof -ti:8765 |
   xargs kill -9`) and watch the app flip to the "Backend Not
   Running" full-screen state within ~10s. Restart engine — should
   auto-recover.
4. **Smoke-test #960**: inspector → Artifacts tab on a doc with many
   artifacts. Panels should size to content; long artifacts grow,
   short ones don't pad to 120pt.
5. **Pick next from backlog.** Best small candidates: #963 (blocked
   on #924), #959 KG claim quote rendering, #885 preserve extractor
   outputs. Bigger: #943 view stickiness (needs architectural call
   first: global vs per-item vs hybrid), #958 structured artifact
   editors (multi-day).

### Don't break

- DocumentStore.pendingFanoutCompletionPaths is the new in-memory Set
  for #948; flushPendingFanoutCompletions(status:) must be called on
  workflow.complete / .error / .systemicError or pages stay stuck on
  spinner forever.
- AppState heartbeat (#967) is 5s loop. If you change health URL or
  add a global timeout, mirror it in both checkBackendHealth() and
  pingBackendOnce().
- AttributedTextEditor.sizeThatFits depends on layoutManager.ensureLayout
  — don't remove the container-width set, or layout reports the
  previous width's height.

---

## Earlier next-session entry (2026-05-12 morning hand-off)

**Latest commit on 0.0.2: `340ff58f`.** 26 commits pushed overnight.
8 GitHub issues closed: #832, #887, #888, #891, #893, #895, #896, #729.
Three-leg check green throughout (116 KG-adjacent tests pass, swiftlint
clean, xcodebuild SUCCEEDED).

### What landed
1. **Backend KG namespace consolidation (#919 5c).** `/api/knowledge-graph/*`
   sub-package deleted (~8200 LOC dupes); five focused modules under
   `/api/kg/*`: `kg_claim_search`, `kg_claim_analysis`, `kg_entity_curation`,
   `kg_predictions`, `kg_inclusion`. `kg` bucket = 45 endpoints.
2. **#896 Davidson ×6 — ROOT CAUSE.** `compute_cache_key` was keyed
   on `file_path` only, so all six page children of a PDF (which share
   the parent's on-disk path) collided on cache → page-1 result returned
   for pages 2-6 → six near-identical claims. Fix threads `document_id`
   into the key (2f58a4f8). Belt-and-braces: `save_claim` dedups
   within-page near-duplicates (4a3cc728). Regression tests at both
   layers (ffc46a81, 3a3dadc9).
3. **OntologyBrowser as the KG shell.** Tools menu (embed claims /
   entities / generate suggested links), '+' New Entity sheet,
   right-click Edit/Delete entity with confirmationDialog, right-click
   Delete claim, Curation History section, expandable claim cards
   (contradictions + evidence-chain), Heuristic Predictions Review
   Sheet (accept writes KnowledgeClaimLink).
4. **DocumentInspector KG tab** renders verbatim source_excerpt as
   italicised tappable citation (#893).
5. **Library toolbar entity filter unified** with KG @AppStorage CSV (#887).
6. **Dead-code purge.** Removed `KnowledgeGraphServiceGenerated.swift`,
   `HermeneuticsServiceGenerated.swift`, and 2360 LOC of orphan view
   dirs that referenced removed endpoints.

### Suggested morning order
1. **Pull + Xcode rebuild.** OpenAPI client was regenerated at the
   start of the night, so the build picks up all the new methods.
2. **Smoke-test the KG bug fix.** Re-catalogue `tubb2020shift` —
   Davidson should now produce **one** KnowledgeClaim per page, not
   six. Verify by opening Knowledge Graph → Davidson → claim count.
3. **Try the new UI.** Right-click an entity for Edit/Delete. Click
   the wrench in the OntologyBrowser toolbar for the Tools menu.
   Expand a claim card to see contradictions + evidence-chain inline.
4. **Filed for follow-up:** claim PATCH inline editor (#901 remaining
   stroke), force-directed graph viz (#902).

### Tonight's count
- 15 concept tickets closed (#903–#915, #917, #918) + #919 master plan
- 18 concept-issue tickets added + closed since last session
- 448 active backend routes (down from 532 after consolidation — old
  dark routers unregistered, best ideas ported)

### What's ready for Swift work

| You want | Hit this endpoint |
|---|---|
| Right-side inspector for a document | `GET /api/documents/{id}/inspector` |
| Right-side inspector for an entity | `GET /api/entities/{id}/inspector` |
| Force-directed graph data | `GET /api/kg/graph/traverse/{entity_id}` |
| Library overview / counts | `GET /api/kg/graph/metrics` |
| Mixed search bar | `GET /api/kg/search?q=` |
| Triangulation badges | `GET /api/kg/triangulation` |
| Citation export (BibTeX) | `POST /api/bibliography/export.bib` |
| Citation render (Chicago/APA/MLA) | `GET /api/citations/document/{id}?style=…` |
| Curation queue | `GET /api/kg/review/pairs` |
| PyKEEN predictions | `GET /api/kg/pykeen/predict/{id}` |
| Annotation crop for vision input | `GET /api/annotations/{id}/crop` |
| Classification pickers | `GET /api/classifications?dimension=…` |
| Edit any entity / claim | `PATCH` / `DELETE` on `/api/entities/{id}` + `/api/claims/{id}` |
| Undo any edit | `POST /api/kg/mutations/{id}/undo` |

Full reference: `docs/architecture/api/KG_ENDPOINTS.md`.

### Suggested morning order

1. **Pull + Xcode rebuild** — OpenAPI client just refreshed in `0c5ce607`; first build picks up all 62 KG endpoints.
2. **#902 visualisation** — Swift Charts panels (triangulation strength, claim_type donut, epistemic distribution), then force-directed Canvas using `/api/kg/graph/traverse`. MapKit place layer when ready.
3. **Wire the curation surface** — review queue UI, edit/delete buttons, undo button. All backend done.
4. **Re-catalogue tubb2020shift** to see the Toulmin + temporal data flowing through. Most claims won't be analytic so Toulmin slots will be sparse; dates will populate freely.

### Don't break
- Use the canonical KG namespace `/api/kg/*` for new Swift calls, not the deprecated routers (`/api/interpretations`, `/api/graph/*`, `/api/hermeneutics`, `/api/mind-palace`, `/api/research/*`). Old code stays in tree but isn't mounted.
- `docs/architecture/api/KG_ENDPOINTS.md` is the single source of truth.
- Pattern: every `_DEV_ROUTE_SPECS` entry passes tags as the third tuple element — APIRouter constructors should NOT also set tags, or the OpenAPI export double-counts.

---

## Earlier next-session entry (2026-05-12 overnight autonomous run)

**Latest commit on 0.0.2: `4ed74389`** — cross-source triangulation. Total
night's work: ~15 commits implementing the #899 KG library rollup
(rdflib, sentence-transformers, spaCy) + #900 triangulation + #894 fix
(Apple Intelligence now emits real epistemic_status / source_text) +
the earlier #895 / #896 / #897 dedup fixes.

### What's now wired

1. **#896 / #897 dedup** — Davidson should appear once on p.1 with
   variants in aliases; the 6 narrator-monologue events should
   consolidate to 1-2.
2. **#899 Phase A — rdflib substrate**. `fichero.kg.triples` materializes
   KnowledgeEntity + KnowledgeClaim as RDF using FOAF / schema.org /
   SKOS / fichero: namespaces. SPARQL queries work over the in-memory
   graph.
3. **#899 Phase B — sentence-transformer entity vectors**.
   `fichero.kg.entity_vectors` encodes canonical_name + description
   into LanceDB. `upsert_entity` is now a 4-stage pipeline (exact →
   cosine ≥0.92 auto-merge → 0.75-0.92 review-gate log → SequenceMatcher
   floor → create + index). Semantic-divergence dedup works.
4. **#899 Phase C — spaCy NER pre-pass**.
   `fichero.kg.spacy_ner` loads `en_core_web_sm` + `es_core_news_sm`,
   `detect_language()` picks per chunk. Wired into the catalogue extractor
   for people/places/orgs/events — spaCy spans land in the LLM prompt
   as "use these as canonical entities."
5. **#900 triangulation** — `fichero.kg.triangulation` computes
   support_count per (subject, predicate, object) triple across the
   corpus. New axis distinct from per-claim `epistemic_status`. Two
   dev-tier endpoints: `GET /api/kg/triangulation/entity/{id}` and
   `GET /api/kg/triangulation?threshold=3`.
6. **#894 closed** — Apple Intelligence now emits `epistemic_status`
   (confirmed/tentative/rejected) and `source_text` (verbatim quote)
   instead of falling through to defaults. Pydantic v2 schema-required
   + before-validator pattern.
7. **#895 closed** — KG sidebar click no longer leaves the library
   icons/list/table/map mode rail visible.

### Test for visible wins on next launch

1. Pull `0.0.2`, restart engine, rebuild Xcode.
2. Nuke library (or use a fresh one), import `tubb2020shift - Preface.pdf`.
3. Run Catalogue.
4. Open Knowledge Graph → check:
   - **Davidson**: 1 entity, claims show parenthetical variants in aliases.
   - **Events**: 1-2 entities for the recurring monologue (not 6).
   - **Claim cards**: epistemic_status badges show "Confirmed" / "Tentative"
     based on the LLM's read, NOT all "Tentative" defaults. Source quote
     italics under each claim shows real text, not empty.
   - **KG sidebar**: only the KG MiniToolbar appears, no mode-strip.
5. Hit the rebuild endpoint to populate the RDF graph + backfill any
   missing vectors:
   ```bash
   TOKEN=$(cat ~/Library/Application\ Support/Fichero/.api-key)
   LIB="$HOME/Library/Application Support/com.fichero.fichero/global.fichero"
   curl -X POST http://localhost:8765/api/kg/rebuild \
     -H "Authorization: Bearer $TOKEN" \
     -H "X-Fichero-Library-Path: $LIB"
   # → {"entities": N, "claims": M, "vector_indexed": N, "triples_written": K}
   ```
6. Inspect the RDF graph file:
   ```bash
   ls "$LIB" | grep kg.nt   # → kg.nt
   head -20 "$LIB/kg.nt"
   ```
7. Triangulation query (after multiple PDFs catalogued):
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     -H "X-Fichero-Library-Path: $LIB" \
     http://localhost:8765/api/kg/triangulation?threshold=2
   ```

### Pending / next slices

- **#899 Phase D (splink)** — probabilistic record linkage. Needs
  labelled pairs from Phase B's 0.75-0.92 review-gate region. Deferred
  until the curation UI from #377 lands (or until Daniel labels a few
  pairs manually).
- **#900 slice 3** — materialize support counts to DuckDB for cached
  reads. Defer until inspector hits perf issues (~100k claims is the
  trigger).
- **#900 slice 5** — Swift UI corroboration badge + source-list
  popover next to existing epistemic_status badge.
- **#893** — true PDFKit findString integration (open parent PDF + jump
  to highlight) — current "tap excerpt → library search" is a graceful
  fallback.
- **#887** — unify KG inspector kind-filter with library-toolbar entity
  filter (six SceneStorage booleans → single AppStorage CSV).

### Don't break

- **Pydantic schema-required + before-validator pattern** — see new
  MEMORY entry. The naive `Field(default=..., json_schema_extra=
  {"required": True})` approach does NOT work; only the no-default +
  before-validator combination forces grammar emission.
- **`ClaimType` (ontological) ≠ `EpistemicStatus` (epistemic)**. Two
  axes, both on `KnowledgeClaim`. And now **`support_count`** is a
  third axis (cross-source corroboration, derived). Three distinct
  signals — don't conflate.
- spaCy + fastembed models are bundled, but first-run downloads.
  Engine cold start stays fast because both are lazy-loaded.

---

## Earlier next-session entry (2026-05-11 late hand-off)

**Latest commit on 0.0.2: `23fdd6a3`** — KG epistemology + ontology +
source_text layer (7 commits pushed today). Build green; 41 extractor
tests + 2 live Apple Intelligence tests passing.

### Test on next launch

1. **Pull + restart engine + rebuild app.** New backend fields land
   only on freshly catalogued docs; existing claims won't have them.
2. **Catalogue a fresh PDF** (Daniel's earlier suggestion was
   `tubb2020shift — Chapter 1.pdf` + `Preface.pdf`). Expect:
   - KG inspector entities now have **two filter strips** above the
     claims list — Status (confirmed/tentative/rejected) and Kind
     (fact/analysis/interpretation/argument/historiography/theory).
   - Each claim card shows the **LLM-quoted source excerpt** in italics.
   - **Tap the excerpt** → library search for that exact passage.
   - **Tap entity name in the header** (`Eugenio Córdoba`, etc.) →
     scoped library search (`people:"Eugenio Córdoba"`).
3. **Expected gap (already filed at #894):** Apple Intelligence will
   probably leave source_text empty + epistemic="tentative" + kind
   ="fact" on every claim because Pydantic defaults aren't required in
   the JSON schema. Decide whether to (a) drop defaults so grammar
   forces emission, or (b) `json_schema_extra={"required": True}` per
   field for the same effect with graceful Pydantic parsing.

### Visual queue carried over (not done — needs your screenshots)

- Sidebar background shade vs. content area
- Margin/divider between sidebar top and window toolbar
- Toolbar background coherence with MiniToolbar pane headers

### Open KG follow-ups

- **#893** stays open for PDFKit `findString` integration so tapping
  an excerpt navigates into the parent PDF preview and highlights
  the matching span (currently only routes via library search).
- **#894** prompt-vs-defaults — implement option 2 if you agree.
- **#887** unify KG inspector kind-filter with library-toolbar entity
  filter — 6× `@SceneStorage` + 1× `@AppStorage` need to converge.
- **#888 / #889** regen KG service stubs + rewrite ClaimInspector /
  EpistemologyGraph / PredictionReview / Hermeneutics views.

### Don't break

- `ClaimType` (ontological) ≠ `EpistemicStatus` (epistemic) — two
  distinct axes, both already on `KnowledgeClaim`. Don't merge them.
- `CurationStateBadge` uses `unreviewed/shortlisted/curated/rejected`
  — NOT `approved/pending` (those were renamed in an earlier regen and
  the broken switch hid behind incremental builds for weeks).
- The on-device model's grammar-constrained decoding lets Pydantic
  defaults silently win — only required fields are forced.

---

## Earlier next-session entry (2026-05-10 late-night hand-off)

**Latest commit on 0.0.2: `8065f96e`** — frontend test coverage sweep
(Phase 28→34). Coverage on Fichero.app: 9.20% → 9.94% (+0.74pp).
**472 tests passing, 0 failing.**

### Phase 28–34 — test coverage push (Models + DTOs)

Test files added this evening (10 new files, ~210 new tests):

- `ItemTypeRegistryTests` (10) — Add-menu handler injection contract
- `ModelComparisonTypesTests` (19) — Compare-Models DTOs; locks the
  `<provider>/<model>` Identifiable formula and snake_case decoders.
  Note: `ComparisonResult` clashes with `Foundation.ComparisonResult`;
  qualify as `Fichero.ComparisonResult` in tests.
- `WorkflowResponseTypesTests` (12) — workflow API + SSE event DTOs,
  `NodeExecutionState.progressText`/`isParallelProcessing` rules
- `MCPServerTests` (19) — per-transport validation (stdio→command,
  net→url), status icon/color, snake_case Codable
- `BackendDTOTests` (20) — CheckpointTypes + BatchTypes; locks
  `CheckpointValue.stringValue` per-branch render + Batch status maps
- `WorkflowChainTests` (18) — full chain-execution DTO surface

(Plus 9 fixed pre-existing test failures: EndpointValidationTests
path-resolution via `Bundle(for:)` anchor, InspectorTab cases bumped
from 2→4, RichTextController weak-binding contract test, etc.)

### Earlier today (Phase 22+ Search v1)

Score-correctness rewrite, query parser, KG endpoints, library
toolbar search — see commit history `git log --oneline 0.0.2`.

### What's deployed and waiting for bug-test

1. **Score-correctness rewrite** (Phase 1–11): un-normalised
   embeddings → cosine; RRF combiner; accent-insensitive fold;
   marker-only embed fix (`[sin texto]` no longer dominates).
2. **Query parser** (Phase 3): phrases / `field:value` / `-exclude`.
3. **Lozenge tap-to-search** with entity scope (Phase 11).
4. **NER per-page (local)** preset for `.md` folders (Phase 12).
5. **Library toolbar search field** always visible (Phase 13).
6. **PDF page backfill** route (Phase 14).
7. **5 KG endpoints** (Phase 15, 18, 19, 21) — `/entities/top`,
   `/entities/{id}/documents`, `/entities/{id}/co-occurrence`,
   `/entities/{id}/drill-down`, `/documents/{id}/related`.
8. **Sidebar reorder** — Saved Searches below Workflows + Activity (Phase 16).
9. **Reindex live progress count** (Phase 8).
10. **27+4 frontend Swift unit tests** (Phase 22) + 91 backend tests.

### Restart procedure (engine + app)

```bash
# 1. Pull
git pull origin 0.0.2

# 2. Restart engine cleanly (avoids the 401 token-rotation issue
#    flagged in #879 — old worker holds stale token-in-memory while
#    file got rewritten)
pkill -f "uvicorn fichero.api.main"
./scripts/start_backend.sh

# 3. Re-index (old un-normalised embeddings need refresh)
TOKEN=$(cat ~/Library/Application\ Support/Fichero/.api-key)
LIB="$HOME/Library/Application Support/com.fichero.fichero/global.fichero"
curl -X POST http://localhost:8765/api/search/reindex \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Fichero-Library-Path: $LIB"

# 4. Rebuild Xcode + run
```

### Test scripts (run anytime, no restart needed)

```bash
# Backend (91 tests)
PYTHONPATH=fichero-engine/src .venv/bin/pytest \
  fichero-engine/tests/unit/test_search_scoring.py \
  fichero-engine/tests/unit/test_search_query_parser.py \
  fichero-engine/tests/integration/test_search_end_to_end.py \
  fichero-engine/tests/unit/workflows/test_default_workflows.py

# Frontend (31 tests)
xcodebuild test -project fichero/fichero.xcodeproj -scheme Fichero \
  -configuration Debug -destination 'platform=macOS' \
  -derivedDataPath /tmp/fichero-build -skipPackagePluginValidation \
  -only-testing:FicheroTests/RecentSearchesStoreTests \
  -only-testing:FicheroTests/SearchResultRowFromAPITests \
  -only-testing:FicheroTests/EntityTypeMappingTests \
  -only-testing:FicheroTests/SearchResultsDisplayTests
```

### Known issues for tomorrow's test session

- **#879 — 401 token rotation**: Daniel saw repeated 401s while my
  edits triggered uvicorn `--reload` rotations. Workaround: start the
  engine without `--reload`, or restart engine+app after each backend
  change.
- **Per-folder scope toggle UI** (#11 in handoff list): backend works
  (filters['folder_id']), UI not wired.
- **Frontend KG hookups** for the new endpoints — not yet wired into
  inspector / search empty state. Backend ready.

---

## Next Session — Start Here (2026-05-09 evening hand-off)

**Latest commit on 0.0.2: `af1f30ff`** (clear-filter escape, lozenge
middle-truncation, single-click no longer hijacks filter). xcodebuild
verified clean on every commit pushed today.

### Visual bugs flagged from morning test (priority for next pass)

1. **Sidebar window background too dark** — visibly different shade
   from the rest of the window. Needs lighter material to match the
   content area. (Screenshot 2026-05-09 8:40 AM.)
2. **Margin between sidebar and toolbar** — no visible separation
   between sidebar's top edge and the window toolbar; needs a touch of
   padding or a divider.
3. **Toolbar background is off** (Daniel's last 2026-05-09 message)
   — full visual treatment audit across sidebar / window toolbar /
   pane mini-toolbars so they feel coherent.

### Functional queue (started, not finished)

4. **Filter button → top-right TOOLBAR for all library views** (icon /
   list / table / map), not just an overlay on list. Already removed
   the list-only overlay in `LibraryView+DisplayModes.swift`; needs a
   `ToolbarItem(placement: .primaryAction)` wired in the parent that
   calls `entityFilterMenu`. (Half-shipped.)
5. **Per-folder view-mode persistence verification.** Plumbing exists
   (`folderViewDisplayModesJSON` @SceneStorage on ContentView,
   `displayMode(for:)`/`saveDisplayMode(_:for:)` in
   `ContentView+Persistence.swift`). Daniel reports view mode isn't
   sticking per folder — either save isn't called on folder change or
   load isn't being applied.
6. **Sidebar layout for macOS Tahoe** — needs a screenshot to fix.

### Don't break

- Single click on a MailStyleRow selects only — do NOT re-add tag-tap
  `onTapGesture` to badges. Daniel hit a stuck-filter bug.
- "Clear Filter" button must be visible whenever `!searchText.isEmpty` —
  it's the user's only escape from a bad filter state.
- `Table` builder caps at 10 columns — don't add an 11th without
  computed-property column-groups refactor.
- `WindowState.libraryId` is non-optional UUID — don't `if let` it.
- Run `xcodebuild` before every Swift push, not just `swiftlint`.

### Architectural follow-ups (for 0.0.3+)

- **#874** User-extensible entity types — registry-driven backend +
  frontend re-architecture. The 6 types are baked into the Pydantic
  `_Extraction` class AND into 6+ frontend call sites. 0.0.4 scope.
- **#868** LLMProvider Protocol refactor — foundation laid. 0.0.3.
- **#481/#482/#483** — Search v1 / v2 / v3 release gates. v1 is in this
  0.0.2; v2 + v3 are 0.0.4 / 0.0.5.

### Read for context

- `docs/architecture/api/development_standards.md` — 6 LLM-stack contracts
- `MEMORY.md` 2026-05-07/08/09 — durable patterns
- `HISTORY.md` — session-by-session log
- GitHub `#874` — user-extensible entity types brief

---

## Earlier next-session entry (kept for continuity)

**Latest commit on 0.0.2: `3d50df04`** (10 integration tests for the LLM
fallback chain, mocked at the network boundary, no internet calls).

### 0.0.2 milestone state

Open: 9 (was 16). Closed: 265+. Ratio 96%.

The remaining 9 are: #659–#665 (release packaging, all Daniel-blocked),
#821 (Apple Intelligence Tool calls — bigger feature, deferrable), #868
+ #872 + #873 (LLM-stack follow-ups — all doable now), #854 moved to
0.0.3 (genuinely blocked on macOS SDK 26.4).

### Highest-value next thing: #868 LLMProvider Protocol refactor

**Read first:** the implementation brief I wrote inside the issue
(GitHub comment dated 2026-05-07). It has the exact 5-commit sequence
+ file paths + risk analysis. Don't re-derive — execute.

**Quick orientation:** the foundation is already in `llm.py`:
- `AppleUnavailableError` hierarchy (~line 145)
- `_compute_timeout(config, kind, *, schema_chars=None)` (~line 1308)
- `collect_usage()` + `_record_usage()` (~line 70)
- Reasoning routing in `get_langchain_model` (~line 1850)

The refactor wraps these into provider classes; dispatchers replace the
in-line `if config.provider == "apple": ... else: ...` branches.

### Other paths

- **#873 next slice:** the 10 fallback-chain tests are scoped piece 1.
  Pieces 2/3 would be (a) a workflow-execution-runner test with mocked
  tools, (b) an end-to-end test driving the FastAPI route. Both need
  fixture-infra design choices first.
- **Live verification still pending:** restart backend on a recent commit
  and re-run Catalogue (Mixed) on Legal Case to confirm the Spanish
  locale fix works in production.
- **Cellphone-aware rule for autonomous loop:** mock all LLM calls in
  tests; never write a test that hits real provider APIs without an env
  flag (`FICHERO_INTEGRATION=1`) and `pytest.skipif` guard.

### Don't break

- AppleUnavailableError fallback works because `chat_with_fallback` /
  `chat_structured_with_fallback` catch the base class. Don't catch
  `GuardrailViolationError` specifically anywhere.
- Don't add a fourth timeout formula somewhere. Use `_compute_timeout`.
- Don't `logger.info("LLM usage ...")` directly. Use `_record_usage` so
  the contextvar collector picks it up.
- Don't add a second Apple path. fm-bridge is canonical.

### Read for context

- `docs/architecture/api/development_standards.md` — 6 contracts under
  "LLM Stack Architecture (post-#872)"
- `MEMORY.md` 2026-05-07 entries (7 durable lessons)
- HISTORY.md 2026-05-07 session summary
- GitHub issue #868 comment "Implementation brief — for fresh-context resumption"
2. **If per-file works**: move on to release pipeline #658–#660 (DMG
   build / notarize / dry-run install).
3. **If per-file doesn't land**: check engine.log for
   `page_cleanup(<key>): wrote <key>_clean on N/M descendant docs` —
   N>0 means it's working. If N=0, the records flow lost doc_ids
   again; verify catalogue.json has both `transcribe.texts → aggregate.text`
   AND `files-source.documents → aggregate.documents` (force-reseed
   defaults via Settings if not).
4. Iterate on the inspector via plain Xcode: `BuildProject` (~1.5s) +
   `open .../Fichero.app` (~5s end-to-end). Don't try SwiftUI
   previews of the Inspector — they hit the 30s app-launch timeout
   and the SPM workaround isn't worth the duplication cost.
5. New bugs Daniel files via `/bug` go to milestone 0.0.2.

## Architecture Reminders

- **Engine**: external (`./fichero-engine/scripts/start_backend.sh` or
  briefcase dev) — Debug Embed phase no longer copies the briefcase
  bundle; the Swift app probes `:8765` for 5s and uses whatever's there.
- **Auth**: token at `~/Library/Application Support/Fichero/.api-key`,
  written by `initialize_token()` on every engine start regardless of
  launch path.
- **Test 2 folder**: `7dbba674ae204be9b08dc8df5a00f6fa` (Asprilla,
  15 files); Catalogue workflow id changes per reseed — query
  `/api/workflows/` to find current.
