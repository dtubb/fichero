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
