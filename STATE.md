# STATE — Overnight autonomous run (2026-06-22 ~01:25, Daniel asleep, "work all night")

Branch `0.0.2` @ c703c06e (= origin, clean). Daniel: "it builds, going to bed, keep working."

## SHIPPED OVERNIGHT 2026-06-22 (after Daniel slept) — 0.0.2 @ 151d52c9, all baseline-diff 0-new + pushed
- **#2518 — live results fixed** (5ddb380c): emit gap, NOT transport. complete_run_documents + kg_persist_finalize
  now emit document/entity/claim.updated → UI refreshes live on completion. + permanent emit-coverage guardrail
  + key canonicalization + Swift surfaces connect failures (liveUpdatesUnavailable). Activity-progress was a SEPARATE
  already-working stream (thread_id-keyed) — if Activity still looks frozen, the new surfacing flags it = new ticket.
- **#2430 — per-page transcription fixed** (151d52c9): multi-page PDFs were processed whole-doc → combined blob on
  parent because the import page-split SILENTLY FAILED (Kreuzberg). 3 fixes: split-fail-loud + fitz fallback + stamp;
  on-the-spot split in sources (AUTO-BACKFILLS existing PDFs next run); process_vision guard raises not combined-blob.
  Sequential fan-out (500-page safe). Catalogue = rollup. RE-TEST: import/re-run a multi-page PDF → per-page artifacts.
- STILL RUNNING: `backend-hardening-finish` (Opus) #2513 (ValidationError swallow) + #2514 (remove DBWriter) → finishes #90.
- NEXT (panes free): UI bug batch — #2515 toolbar-overlap, #2517 library-toolbar=reader, #2496-#2504, #2506; #2516 annotation
  palette (design=floating-right decided); #2507 silent-fallback sweep. iOS branch worker/ios-reader-polish: I build-gate+merge.

## SHIPPED TODAY (0.0.2, baseline-diff-verified 0-new-failures, pushed)
- **#2508 KEYSTONE — single DuckDB connection + lock per package** (was per-thread → root of #2430/#2462).
  P0-P4 + permanent guardrail (bans get_ident keying). Read-after-write now deterministic. c703c06e.
- #2509 (cross-thread conn) · #2510 (false-success partial write) · #2511 (cache-miss swallow) · #2512 (silent re-embed).
- Earlier: #2430 DB-race half, #2486 accents, #2490 chat, #2494 editor P0, unified reader toolbar (#2421/#2423/#2488).

## RUNNING NOW (lanes, ~/code/fichero-worktrees/, commit-not-push, manager baseline-diff-gates before merge)
- `backend-hardening-finish` (Opus) — #2513 (ValidationError swallow) + #2514 (remove redundant DBWriter). Finishes #90.
- `changestream-probe` (Opus) — #2518 FIX: the live-results bug = an EMIT GAP (complete_run_documents + kg_persist_finalize
  save terminal state but never emit document/entity/claim.updated to the change-stream → UI never refreshes; reload shows all).
  Fix = 2 best-effort emits + add terminal nodes to check_emit_change_coverage.py + tests. (NOT transport/HTTPS.)
- QUEUED (tmux full): `transcribe-per-page` — #2430 granularity. PDFs aren't split into page-children (split silently
  fails at import) → whole-PDF→parent. Folder-of-images works (per-item). Fix: split-on-import fail-loud + per-page guard
  + bounded fan-out (docs up to 500 pages, ONE page/call). Worktree ready, dispatch when a pane frees.

## DANIEL'S DECISIONS (this session) — fold into the work
- Annotation tools (#2516) = floating right-side palette, annotate mode. PDFs auto-split into page docs (#2430).
- worker/ios-reader-polish (3 unmerged iOS commits) = I build-gate (Mac MCP) + merge; he builds iPhone later.
- Red baseline (~1218 env-dependent pytest fails + 13 arch-checks): triage soon (real-bug vs needs-deps).
- Page-level FIRST for everything; catalogue = later rollup reading per-page records. NO silent fallbacks.

## OPEN UI BUGS FILED (frontend, not yet laned): #2515 toolbar overlaps library · #2517 library toolbar=reader toolbar
  · #2496-#2504 (list-click, merge dest #2499, iPhone merge #2500, mirror libs #2498, iPhone space #2497, RTF-in-list #2502,
  iOS view 2-tap #2503, 3D-circle #2504) · #2506 editor fast-nav lost-edit.

## NEXT (morning / as panes free): integrate the 2 running lanes (baseline-diff) → dispatch transcribe-per-page (#2430)
  → then the UI bug batch. #2514 finishes #90 hardening. Follow-up #2513-style: silent-fallback sweep #2507.

---
## (history below) STATE — Overnight autonomous run (2026-06-20 ~21:45, Daniel asleep)

Branch `0.0.2`. Daniel is asleep; **work autonomously all night** fixing the filed bug backlog.
Manager (Claude) dispatches Opus/Sonnet lanes (1–4 at a time, disjoint files), integrates,
build-gates, and runs verify_all at checkpoints.

## CADENCE (Daniel's rules, this session)
- **1–4 lanes at a time**, disjoint files, claim issues (status:in-progress). Opus for important
  UX/structural; sonnet for medium; backend lanes fine on sonnet. NO kimi (it 429-rate-limited).
- Each lane: own worktree under ~/code/fichero-worktrees/<name>, commit (don't push), report.
- Manager integrates: review diff, swiftlint/ruff, register new .swift (add-swift-file.rb — now
  UTF-8-safe), cherry-pick to 0.0.2, BUILD-GATE via Xcode MCP BuildProject(windowtab5)=0 errors
  (Daniel asleep → no conflict now), push only if green, close issue, remove worktree+branch,
  shut down the agent. **Run full verify_all.sh at batch checkpoints** (it's slow).
- `.buttonStyle(.glass)`/`.glassProminent` do NOT compile — bounce. `.glassEffect()` OK.
- SwiftUI type-checker: large view bodies tip "unable to type-check in reasonable time" — split props.
- All networking via generated OpenAPI client; no hand-rolled URLSession. App never uses local paths.
- Do NOT touch the TLS/auth perimeter (cert SAN -9807 = #2382, Daniel's call).

## DONE TONIGHT (all on 0.0.2, build-green, pushed) — through ad0a5530
- Inspector-editor reliability: #2476 #2477 #2478 (store-owned save, flush-on-nav, self-echo filter).
- #2480 legacy-embeddings warning de-noise (backend, fires once/process).
- Reader: #2428 (pin keeps page) #2424 (focus ring) #2427 (full-res image zoom).
- #2482 entity garbage-name filter ("12:10"): LibraryView filter + EntityRow fallback + 422 manual-create guard.
- #2469 image spinner + ±3 neighbor preload + bounded display cache.
- #2438 (silent save, removed "Saved" flash) + #2445 (node help-text font) — done by manager directly.
- **#2453 KEYSTONE — editor unification**: deleted AppKit AttributedTextEditor (531 lines), unified on
  SwiftUI 26 AttributedString TextEditor across Mac/iPad/iPhone; ArtifactRichTextCodec RTF boundary;
  Document made @unchecked Sendable for the cross-actor save. ⚠️ NEEDS DANIEL TESTING (rich-text + RTF round-trip).
- #2439 (run output → Activity, removed editor bottom panel) + #2437 (node/edge spacing).
- #2429 artifact relative-timestamp in inspector list.
- #2475 sidebar bottom toolbar — 44pt touch tier (reused MiniToolbarMetricPolicy) + Liquid Glass.
- #2472 iPhone sidebar empty-on-launch — root-caused (compact .task runs before loadCollections);
  fixed via @Published librariesLoadVersion + SidebarView.onChange (no withObservationTracking race).
- #2430 HTR per-page artifacts — already fixed (stale build); added 7 adversarial regression tests as guard.
- #2459 image-editor save — root-caused (the #2469 display cache had ZERO callers); wired
  onEditApplied→invalidateImageCache on success only (+3 tests). NOTE: other image-mutating paths may need invalidation too.
- #2434 inspector workflow-history — improved existing panel: status badge + newest-first sort + STABLE
  ForEach id (fixes duplicate-workflowId crash) + 5 tests.
- **~21 issues closed**, all build-gated green (Xcode BuildProject; verify_all NOT run — GUI-window rule).
  HEAD = 6063ac43. Several worker lanes stalled or erred mid-run (workflow-polish, editor-unify, + a bad
  pbxproj test registration) and were salvaged/fixed/reviewed by the manager — build-gate every lane.

## LESSON (add to worker briefs)
- NEVER run add-swift-file.rb on fichero-tests/* — the test target is a SYNCED group; manual registration
  creates a duplicate PBXGroup with a doubled path → build fails ("input file cannot be found"). #2434 hit this.

## MAINTENANCE (overnight, no code change)
- BACKEND HEALTH CHECK (overnight): full unit suite as one process = 4133 passed / 1218 failed, BUT the
  failures are ENVIRONMENTAL (sampled failing files pass in isolation; suite isn't built to run as one 5k-test
  process against the live engine). HEAD is healthy. EXCEPTION — found ONE real bug hiding in the noise:
  filed #2483 (default workflow 'Capture OCR + Transcribe' fails to build in LangGraph — builder names nodes
  by label vs id inconsistently; 38/39 presets build fine, only this one fails, in isolation). Backend lane.
- #2461 swiftlint: posted a scoping plan as an issue comment — 46 warnings, 0 serious; Batch 1 ~15
  mechanical (swiftlint --fix safe), Batch 2 ~30 structural (file/type/function length — manual splits,
  type-check-timeout risk, do file-by-file). Did NOT run --fix (would conflict with in-flight #2098 lane).
- #2474 triaged: NOT a dup of the fixed #2475. It's a real SIBLING — `libraryBottomActionBar`
  (LibraryView.swift:470), a 2nd bottom bar with small (.controlSize(.small)) buttons + no glass.
  Exact fix scoped on the issue (mirror #2475: iOS 44pt touch tier + glassEffect, Mac stays native).
  DEFERRED (not done blind): LibraryView.swift is at file-length limit + the in-flight #2098 lane edits
  it — do after #2098 lands to avoid conflict. New issues check (last 24h): nothing newly actionable+small.
- Stale LOCAL branches needing Daniel's call (NOT deleted — not in --merged):
  - `worker/ios-reader-polish` — DIFF SUMMARY (vs 0.0.2): 3 commits (#2331/#2332/#2100). Adds a NET-NEW
    compact iOS PDF reader — `iOSPDFReaderView.swift` (+48, not on 0.0.2, not superseded) doing swipe-pages +
    pinch-zoom via PDFPageView, wired by a 12-line `EditorView.swift` edit, plus `CompactReaderPolicyTests`
    (+44) and a junk FINDINGS.md. 0.0.2 has NO iOSPDFReader/CompactReader wiring today, so it's real added
    functionality. BUT the branch base is ~1000 commits stale → a direct cherry-pick conflicts on pbxproj
    (iOSPDFReaderView registration vs the diverged project file) + FINDINGS.md, and its EditorView edit predates
    the #2453 editor-unification + reader-zoom changes. DECISION (recommend): do NOT cherry-pick the stale branch.
    Either (a) DROP it if the shipped reader-zoom (#2417 pinch) + iOS-shell reading already cover iOS PDF reading
    well enough, or (b) if you still want a dedicated swipe-pages compact reader, RE-IMPLEMENT the ~100-line delta
    fresh on current 0.0.2 (re-add iOSPDFReaderView via add-swift-file.rb, re-wire EditorView) — cleaner than
    untangling the stale merge. Your product call on whether (a) or (b).
  - `worktree-agent-a6f4aac6c892361cf` — DELETED (was 451bd643, reflog-recoverable). Confirmed superseded:
    all 4 of its files exist on 0.0.2 + 22 #2376/#2399/#2401 onboarding/pairing commits merged since its base;
    it was just an early snapshot 0.0.2 evolved past.
  - BRANCH-CRUFT TRIAGE (merge-status scan done): NONE are in `--merged`, but two tiers:
    * SAFE-PRUNE SET (unique=1, ~3wk stale, reference CLOSED issues — superseded throwaway/model-bakeoffs):
      tmp-1306/1307/1306v2/1307v2, gpt*, codex53-*, issue-1359, issue-1156-graph-rag-chat, feat/*, fix/*,
      ms/activity-255/importers/macos-gating, work/real-data-processing-1594. Spot-confirmed tmp-1318
      (issue #1318 CLOSED) → DELETED it as proof. The rest can be bulk-pruned after a quick "issue closed?"
      confirm each (all reflog-recoverable). Low priority.
    * REVIEW SET (real divergent work, higher unique counts): opus=28, haiku=22, sonnet=9, backend/1382=13,
      ms/ai-backend-harden=8, ms/importer-fixes=3, gptmini-*=2, ms/kg-hermeneutics=2. Don't delete — verify content first.

## DONE (borderline-design, post-drain) — through 2dae7aab
- #2405 column/list view: real navigable page+artifact rows instead of count badges (→ reader focus #1463).
- #2404 sidebar: PDF is now a LEAF (stop expanding pages in the tree) — coherent pair with #2405.
- #2471 iOS image viewer: inline glass MiniToolbar (zoom/fit/actual-size) — assessed clean drop-in, no #2423/#2467 touch.
- **~24 issues closed total this run.**

## RUNNING NOW
- Nothing. Isolated AND the three borderline-design items are now DONE. Everything remaining is
  one of: (a) HELD design clusters, (b) device/data-specific (can't verify overnight), (c) perimeter
  (Daniel's call). Categorized below — needs Daniel's direction to proceed well.

## REMAINING OPEN — CATEGORIZED (for Daniel to direct)
- **Held design clusters**: toolbar #2431/#2432/#2436/#2423/#2467/#2433; inspector redesign
  #2468/#2470/#2455; workflow-node editor #2440/#2441/#2442/#2443/#2444; node model #2446/#2447;
  splits #2422/#2481. → unified design + Opus, not piecemeal.
- **Device/data-specific (can't verify overnight)**: #2464 (ICANH no PDFs — needs the real lib),
  #2407/#2408/#2409 (iPad auth-race/perf/WebKit — needs iPad profiling), #2479 (cross-device sync — needs 2 devices).
- **Perimeter (Daniel's call)**: #2400/#2403/#2435 (tailnet host / user-auth / KG-on-remote), #2382 cert SAN.
- **Editor-area (hold until #2453 tested)**: #2416 (Mac RTF save bug) #2418 (cross-platform editor parity).
- **Borderline-design (could do with a nudge)**: #2405 (list shows counts not items), #2404 (sidebar
  expansion consistency), #2471 (iOS image-viewer toolbar overlay, low-pri).
- **Backlog**: #2410-2414 (OpenAPI conversion EPIC), #2461 (~112 swiftlint — careful, no blanket font sweep).

## MORNING — DANIEL, START HERE
1. ⚠️ **TEST #2453** (editor unification): rich-text editing (bold/italic/headings) + RTF round-trip
   (no formatting loss) + save persists, on Mac AND iPad AND iPhone. It deleted the AppKit editor.
2. Quick-test the other UI changes: image zoom/preload + edit-then-view, reader focus ring, entity list
   (no "12:10"), iPhone sidebar populates on launch, sidebar bottom toolbar tap targets, workflow spacing,
   inspector workflow-history.
3. Pick the next milestone/cluster to direct (see categorized list) — the held clusters need your call.
4. `worker/ios-reader-polish` branch: integrate (resolve EditorView conflict) or confirm superseded.

## HELD FOR DANIEL (don't piecemeal overnight)
- **Toolbar-rationalization cluster #2431/#2432/#2436/#2423** — design-coupled (one consistent
  view/mode-switch gesture, not per-view icon rows). Needs a unified design + Daniel's "frame-first"
  direction; do with Opus, not piecemeal workers. #2481 (3-way panel split) + node model #2446/#2447
  are likewise structural.
- **worker/ios-reader-polish** branch (3 commits, net-new compact iOS PDF reader) — EditorView.swift
  conflicts with merged reader-zoom; decide integrate-vs-superseded.

## PRIORITY BANDS for the night (after inspector-editor lands)
1. **Inspector/reader reliability** (the editor cluster above) — landing.
2. **Reader/toolbar UX**: #2467 (glass + collapsible reader toolbars; absorbs the bright-blue
   prev/next + #2419 magnifier + #2421 edit/annot toggle + #2432), #2423 (unified reader mini-toolbar
   one code path), #2427 (full-res image zoom), #2428 (pin resets page), #2424 (focus ring),
   #2475/#2474 (sidebar bottom toolbar touch size+glass), #2420 done.
3. **Workflows editor**: #2443 umbrella — #2437 edges, #2438 saved-flash, #2439 output→Activity,
   #2440 hidden tools, #2441 editable nodes, #2442 fan-out, #2444 DeepL tool, #2445 help font.
4. **Mac shell**: #2431 toolbar control, #2450 activity status widget + Inbox header line,
   #2408 rotation perf, #2409 WKWebView perf, #2436 KG toolbar icons.
5. **Backend/quiet**: #2480 (embeddings stamp/de-noise), #2469 (image preload spinner),
   #2470 (KG layers ontology/hermeneutic/interpretation), #2429 (artifact timestamps), #2430 (HTR per-page).
6. **Node model / research-workspace**: #2446 (research/workspace into library tree), #2447
   (entities into library), #2081.
GATED ON DANIEL (perimeter): #2382 cert SAN, #2407 403 race, #2435 KG-pane remote, #2479 transport side.

## DEFERRED BRANCH: worker/ios-reader-polish (3 commits, compact iOS PDF reader #2331/#2332) —
conflicts with merged reader-zoom on EditorView; resolve + fold into a reader lane, or it's covered.

## DONE THIS SESSION (all pushed to 0.0.2, build-gated where noted)
Connection: #2448 Activity live-refresh, #2457 iPhone libs, #2465 connect-order, #2466 save -999,
#2462 doc 404, #2473 workflow-diagram 500, #2451 chat-with-doc (was breaking ALL chat), #2452
search→pages, #2463 pylance/FTS, OpenAPI conversions (#2410-2414), resumePendingUploads, SpatialView
split+access fix, swift-file-script UTF-8. ~30 issues closed. Branch cleanup: 139 local branches deleted.
# STATE — Manager cycle (2026-06-20 ~20:15) — integration done, 3 workers running

**Priority (Daniel, explicit): CONNECTION → MAC SHELL → filed bugs.** Manager delegates
(haiku/sonnet/kimi; opus only if structural), integrates + build-gates (Xcode BuildProject
windowtab5), pushes only if green. Workers in their OWN worktrees; disjoint files; claim issues.

## ✅ This cycle — integrated to 0.0.2, build-green, pushed
- **7 OpenAPI conversions** (import/storage/activity/apiclient/engineconfig/appstate/applescript)
  — killed hand-rolled URLSession (#2410–2414, #2406, #2392 partial). Fixed kimi's bogus
  `.unprocessableContent` cases in PairingService. Closed #2401/#2399/#2417/#2420/#2411/#2412/#2413/#2414/#2406.
- **4 feature lanes**: connected-capture (#2401), pairing-link (#2399), reader-zoom-nav
  (#2417 pinch / #2420 folder nav). ios-reader-polish DEFERRED (overlapped reader-zoom on EditorView;
  branch worker/ios-reader-polish kept).
- **Shell fixes**: SpatialView Spatial2DCanvas split for SwiftLint; ContentView pane-width consts
  `nonisolated` (#LayoutMode actor error); RemoteClientPairing.defaultDeviceName() `@MainActor`.
- shell-mockups docs. All worktrees cleaned; single tree at HEAD.

## 🔄 WORKERS RUNNING (background agents, own worktrees — manager integrates + build-gates)
- **conn-activity** (sonnet) → #2448 Activity live updates over change-stream (CONNECTION band)
- **shell-breadcrumb** (haiku) → #2425 window-title breadcrumb Library›Folder›File›page (SHELL)
- **shell-glass** (sonnet) → #2041 Tahoe glass mini-toolbar + #2415 workflows toolbar button (SHELL)
Issues #2448/#2425/#2041/#2415 carry status:in-progress. `.buttonStyle(.glass)` does NOT compile — bounce it.

## NEXT after these land: Mac shell FRAME (zones sidebar|content|inspector, tabs inside content
column #1968, native .inspector() #2033, zoned toolbar #2032) — the structural lane (opus/manager).
Then remaining connection bugs (#2451 chat-with-doc, #2452 search→pages, #2435 KG remote) + filed UX.

## ⚠️ Daniel's: TLS cert SAN loopback-only (-9807) for remote iPad = perimeter #2382 (his call).
Backend running fine (non-loopback bind warning is expected/harmless).

---
# (prior hand-off below)
# STATE — SESSION-END hand-off (2026-06-20 ~18:00, manager out of tokens ~1h)

Branch `0.0.2`, synced with origin. Autonomous manager session for the iPhone/iPad demo
(Ann tonight via **tailnet sharing** — she joins Daniel's Tailscale). Manager is token-limited;
**kimi/codex workers keep grinding on a wakeup loop until ~19:30. NO verify/integrate by the
manager — Daniel integrates + build-gates later.**

## ✅ FIXED + PUSHED this session (build-green via Xcode MCP `BuildProject` tab windowtab5)
- iPad **crash fix** `f3b8cdd2` — removed macOS-only `drawsBackground` KVC that crashed iOS
  WKWebView (the "can't click / feels crashed"). **→ DANIEL: rebuild the iPad app to get it.**
- **Per-page transcription** `849777af` (#2303/#2395/#2396) — HTR text saves per-page, not parent. 17 tests pass.
- **iOS shell** `3e5431c7` — multiple libraries (registry picker) + phone launches on sidebar +
  compact swipe nav (#2329/#2334/#2394).
- **Liquid Glass bar** + button fix — `.glassEffect()` on MiniToolbar (`.buttonStyle(.glass)` NOT in SDK).
- Mac deploy target → **macOS 26**; mini-toolbar glyphs scale w/ Dynamic Type; worktrees 23→1.

## 🔄 LANES RUNNING (Daniel: integrate + build-gate these later, manager will NOT)
KIMI (cheap, `codex exec --oss --local-provider ollama -m kimi-k2.7-code:cloud`):
- `f_kimi_import` → #2412/#2406 ImportServiceGenerated → OpenAPI client (likely fixes iPad import 400)
- `f_kimi_openapi-storage` → #2411 StorageServiceGenerated → OpenAPI
- `f_kimi_openapi-activity` → #2413/#2392 ActivityServiceGenerated → OpenAPI (likely fixes empty Activity)
CLAUDE (finishing, will not relaunch):
- `f_lane_capture` #2401 capture-while-connected · `f_lane_link` #2399 pairing-link ·
  `f_lane_mockups` HTML shell mockups · `f_lane_reader` DONE (~/code/fichero-worktrees/ios-reader-polish, integrate)
Worktrees under ~/code/fichero-worktrees/. **Kimi may EDIT but NOT COMMIT — check git status.**

## 📋 Issues filed this session (#2391–#2414) + milestone
- iPad/UX: #2391 spatial zoom/xy · #2404 sidebar stop-expanding-pages · #2405 list show pages+artifacts
  · #2406 import 400 · #2407 403 auth race · #2408 slow rotate · #2409 WKWebView slow/unresponsive
- Connect/capture: #2392 Activity empty · #2393 URLSession guardrail · #2394 iOS↔Mac libs ·
  #2397 cross-lib DnD · #2399 pairing-link · #2400 tailnet host (DECIDED: tailnet) · #2401 capture-while-connected
- Multi-user: #2403 connect login-gate (no auto-owner) · #2083 add/manage users · #2084 multi-user toggle
- Build/dist: #2402 notarized standalone build + embedded engine + Sparkle (needs Daniel's Apple creds)
- AR: #2398 immersive Spaces (walls/floor)
- **MILESTONE "Networking — OpenAPI-only (kill hand-rolled URLSession)"**: EPIC #2410 +
  #2411/#2412/#2413/#2414. Guardrail #2393 enforces going forward.

## ⚠️ DANIEL DECISIONS / TODO (manager will not auto-do — perimeter/credentials)
1. **Rebuild iPad app** for the crash fix (f3b8cdd2).
2. **TLS for the demo (#2382/#2400):** `remote_access_tls.py:182` builds the cert SAN for ONE host
   (loopback) → iPad to `macbook-pro-m1.local` fails `-9807` → change-stream/images drop. For tailnet:
   advertise the `*.ts.net` host (+ `tailscale serve` valid cert, or self-signed SAN incl. tailnet name).
   This is the ONE thing blocking remote data load.
3. **Integrate the worker lanes** (build-gate each via Xcode MCP, push if green).
4. Multi-user slice (#2084 toggle → #2083 users → #2403 login-gate) when ready.

## Shell design (Daniel, from the Safari mockups) — KEEP current Mac UX, same code adapts
- Mac = all zones (sidebar·library·preview·reader·inspector), no redesign.
- iPad LANDSCAPE = 2 views in pairs: Library¼+Preview¾ / Preview¾+Reader¼ / Reader¾+Inspector¼.
- iPad PORTRAIT = 1 view + slideovers. iPhone = 1 view + swipe. visionOS = each zone its own window.
- Mockups in docs/design/shell-mockups/ (mac.html, ipad.html ready; phone/tv/vision generating).

## Operating model now
Manager token-limited → **kimi/codex workers only**, light wakeup loop to keep them fed until ~19:30,
**no manager verify/integrate/build**. All work is GitHub-issue-tracked.

## Kimi worker output (2026-06-20 ~19:37) — UNINTEGRATED, for Daniel to build-gate + cherry-pick
The bash/ollama dispatcher (f_dispatcher) ran kimi workers until 19:30 (no Claude). Committed work waiting
in ~/code/fichero-worktrees/ (NOT built/verified/pushed by manager):
- **OpenAPI-only conversions** (1 commit each): openapi-import (#2412/#2406), openapi-storage (#2411),
  openapi-activity (#2413/#2392 — has 1 UNCOMMITTED file, commit it before integrating), openapi-apiclient,
  openapi-engineconfig, openapi-appstate, openapi-applescript (all #2414).
- **Feature lanes**: connected-capture (#2401, 3 commits), pairing-link (#2399, 4 commits),
  reader-zoom-nav (#2417/#2420, 3 commits), ios-reader-polish (#2331/#2332, 3 commits).
- **shell-mockups** (2 commits + uncommitted refinements): the per-device HTML mockups incl. the iPhone
  reader/buttons + iPad orientation-pair + visionOS-windows refinements in docs/design/shell-mockups/.
- ios-shell-nav: already integrated earlier (0 commits remaining).
Integration order suggestion: build-gate each via Xcode MCP (windowtab5), backend conversions need pytest,
push only if green. ~60 issues filed today (#2391–#2449) — all current-release; the workflow-editor cluster
(#2437–#2445), node-model consolidation (#2446/#2447), chat redesign (#2449), and the change-stream/TLS
remote bugs (#2382/#2407/#2435/#2448) are the big themes. Manager stopped (token budget); resume integration
or dispatch more kimi via f_dispatcher pattern when ready.

## ===== OVERNIGHT AUTONOMOUS OPERATING MODEL (Daniel, 2026-06-20 ~19:45) =====
Work STEADILY and AUTONOMOUSLY overnight. Manager (Claude) integrates + tests, but judiciously.

### PRIORITY ORDER (work top-down; finish a band before the next)
1. **CONNECTION** — the remote/transport layer must actually work. Activity view live updates (#2448),
   change-stream/SSE over remote, cert SAN / TLS (#2382/#2400), 403 auth race (#2407), KG-pane-on-remote
   (#2435), OpenAPI-only conversions (#2410–2414, kill hand-rolled URLSession #2393). Get data flowing
   reliably on Mac AND iPad/remote.
2. **READER** — reading is the core. Pinch-zoom #2417, folder/page left-right #2420, full-res image #2427,
   PDF magnifier #2419, unified reader mini-toolbar #2423 (absorbs #2419/#2421/#2432), per-pane split docs
   #2422, pin-resets-page #2428, focus ring #2424.
3. **UX SHELL — make every platform the best**: iOS/iPhone/iPad/tvOS/visionOS/macOS adaptive shell. Keep
   Mac UX, same code adapts (mockups in docs/design/shell-mockups/). iPad portrait=1/landscape=2-pairs +
   sidebar overlay; iPhone 1-swipe; visionOS windows-per-zone. Toolbar control #2431/#2450, window-title
   breadcrumb #2425, Tahoe Liquid Glass #2041, rotation perf #2408, WKWebView perf #2409.
4. **UX odds & ends** — sidebar/list (#2404/#2405/#2429), RTF/text save (#2416), editor parity #2418,
   workflows toolbar button #2415, the toolbar-rationalization cluster, misc filed bugs.
5. **WORKFLOWS** — node-editor parity #2443 (umbrella: #2437 edges, #2440 hidden tools, #2441 editable
   nodes, #2442 fan-out, #2444 DeepL, #2445 help font, #2438 saved-flash, #2439 output→Activity).
6. **CHAT** — Xcode-style chat redesign #2449 (paperclip-attach context drives mode).
7. **RESEARCH/WORKSPACE + node-model** — #2446 (research/workspace into library tree), #2447 (entities into
   library), then deeper node model #2081.

### WORKER POLICY
- Default to **ollama/kimi** workers (cheap) for most lanes — `codex exec --oss --local-provider ollama
  -m kimi-k2.7-code:cloud --dangerously-bypass-approvals-and-sandbox` in tmux + external worktree. The
  `f_dispatcher` bash-loop pattern can keep them fed without Claude.
- Use **haiku/sonnet** (`claude --model …`) for medium frontend lanes; **opus** ONLY for complex/structural
  (adaptive shell, node-model, chat redesign).
- Multiple lanes at once (≤ ~4 active). Disjoint files to avoid collisions; claim issues.
### MANAGER (Claude) DUTIES — judiciously, NOT every commit (slow)
- Integrate landed lanes: review diff + real tests, swiftlint/ruff, register new .swift (add-swift-file.rb),
  cherry-pick to 0.0.2. BUILD-GATE Swift via Xcode MCP BuildProject(tab windowtab5)=0 errors; backend via
  pytest. Run full `verify_all.sh` only at batch checkpoints (it's slow). Push ONLY if green.
- Liquid Glass SDK gotcha: `.glassEffect()`/`GlassEffectContainer` OK; `.buttonStyle(.glass)/.glassProminent`
  do NOT compile — bounce reintroduction.
- DO NOT auto-change the TLS/auth perimeter beyond what Daniel decided (tailnet); cert SAN work is OK to
  IMPLEMENT carefully but flag perimeter assertions.
- Conserve tokens: prefer kimi for the work; spend Claude on integration/build-gating + the hard lanes.
