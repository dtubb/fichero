# STATE — UI REFORM handoff 2026-06-15

Branch `0.0.2`, tracking `origin/0.0.2`. Keep `0.0.2 == origin` (gate before every push). HEAD `84aaa0df`.

## ☀️ START HERE — the UI reform is planned; BEGIN Phase 1
**Master plan:** `docs/architecture/swiftui/reform_masterplan_2026-06.md` (the whole vision + §0 design
brief + §8 RESOLVED decisions + principle 9 "SwiftUI shows, logic is backend"). **Tracking EPIC #2253**
(phased breakdown in its comments). ~36 reform issues, all **phase-labelled** (`gh issue list --label phase:1`…`phase:5`,`phase:continuous`). Worktrees cleaned.

**Role: you are MANAGER — you do NOT implement.** Dispatch workers; gate + integrate. Model policy
(Daniel): **haiku** for minor (3–5 issues), **sonnet** for bigger (5–10), **opus** for complex.

**Swift gating (critical):** Swift workers CANNOT build. For EVERY Swift change YOU gate:
`swiftlint` + Xcode **BuildProject** (tab `windowtab1`) — push only on a clean build. Register every
new `.swift` with `ruby scripts/add-swift-file.rb <path>` (rule #10) or the compiler can't see it.
Backend: full pytest gate (`PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=…_archived`), push only if 0 failed. RunAllTests serial OK (Daniel may not be on the machine — confirm). Keep SwiftUI **folders/files logically organized** (no dumping grounds).

**Target:** latest OS — Tahoe / macOS Golden Gate + iPadOS/iOS latest, **one codebase**, ship **Sept 2026**, newest SwiftUI, no back-deployment.

**PHASE 1 (start here — `gh issue list --label phase:1`, oldest-first):**
- **#2097** platform abstraction shims (`PlatformImage`/`PlatformViewRepresentable`/`PlatformPasteboard`/file-picker) — mirror `Models/MindPalaceTheme.swift`'s `#if canImport` pattern. Additive, foundational.
- **#2098** gate macOS-only code behind `#if os(macOS)` (EmbeddedBackendService engine-spawn, NSWorkspace/NSWindow). Engine is REMOTE-only on iOS.
- **#1455 / #1569** retire Mind Palace → library 2D map (SceneKit/Spatial2DCanvas) + 3D map (RealityKit/SpatialScene3D) view modes; delete the standalone window + `SidebarMode.mindPalace` (compiler-guided ~14 files); KEEP the projector/scene/theme.
- Per Daniel's decision: **build BOTH Mac + iPad/iOS now** (stand up the iOS target) to surface design failures early — this is the riskiest Phase-1 piece (Xcode project change; never hand-edit project.pbxproj — use the ruby script / careful target setup).
Then Phase 2 = shell #2031 + zoned toolbar #2032; Phase 3 inspector/attributes(#2081 full prototypes)/annotation; Phase 4 representations/PDF/maps; Phase 5 table/window/chrome/agents; Continuous = guardrails(#92)/perf/observability/tests/a11y.

**Held (do not touch):** worktrees `entitytable-2020` (#2020), `lan-tls-2157` (#2157), `importers`. #1973
Swift change-stream fix HELD for Daniel (2 build fails; WIP on `ms/ai-backend-harden` branch). Deps #2248 shipped. ICANH libraries are Daniel's.

---
## (historical) overnight backend handoff

## ☀️ MORNING HANDOFF (read first) — as of ~03:20, 2026-06-15
**36 issues shipped to origin/0.0.2 overnight, every one full-suite gated, branch NEVER went red.**
- ✅ **AI Backend Hardening** — DONE (bar #2248 deps, held for you).
- ✅ **AI Infrastructure** — DONE (#2211/#2212/#2213/#2214 — incl the ICANH page-doc page_content fix).
- ✅ **Workflows & Catalogue Hardening** — DONE (per-page across ALL source paths; Auto-Detect/folder/collection/whole-PDF; preset rationalization #2251 + standardization #2252; route_map/classify_script/empty-success; PDF single-open perf #2247; result caches #2224/#2246).
- The gate caught **7 broken "done" claims** (5 pytest reds + 2 Swift build fails) — all bounced, none reached the branch. Workers consistently forget to sweep sibling tests on behavior changes — the full-suite gate is non-negotiable.

**DO IN THE MORNING (your calls, not auto-merged):**
1. **Hard-restart your :8765 backend**, then re-run live ICANH — #2214 + #2247 should make per-page transcription correct AND fast (page children fill in).
2. **#2248 deps upgrade** — committed on `ms/deps-update`, gated in isolated `.venv-deps`. Merge deliberately (upgrades the shared `.venv` your live backend uses).
3. **#1973** (change-stream beachball) — Swift, HELD. 2 blind worker builds failed (Swift-6 actor isolation across 13 stores). Needs a compiler-in-loop pass; both build errors on the issue; WIP on `ms/ai-backend-harden`.

**Next milestones are mostly SwiftUI/iOS** (Remote & Self-Hosting #2096-2101 iOS client; Mac/iOS shell) — backend workers can't build Swift, so those need a manager-gated Swift lane (or you). Overnight the workers are on backend-shaped Developer Experience tooling (#1815 perf benchmarks, #1918 prefetch, #1915/#1953 guardrail scripts). Observable Data Layer: 2 left (#2009 InterpretationStore, #1973-held).

## ⛔ Do NOT touch overnight
- **Port `:8765` and the ICANH libraries** — Daniel is running his OWN backend and testing
  `ICANH-Clean.fichero` himself. No CLI transcribe/import/export, no backend on 8765.
- Mac / SwiftUI / Xcode (no-xcodebuild-on-Daniel's-machine rule — launches GUI windows).
- Held worktrees `entitytable-2020` (#2020), `lan-tls-2157` (#2157); `.claude/worktrees/agent-aaf4fec2eced9c821`.

## ✅ SHIPPED to origin/0.0.2 tonight (each FULL-suite gated, issues closed) — as of 22:55
- #2222 `0dd7e2a6` — vision_base.py `vision_mode != "llm"` text-layer fix. **Daniel: hard-restart backend to load it before live ICANH test.**
- #2226/#2227/#2229/#2230 `d312d625` — quota classification, E5 roles, embed error handling, bg-task tracking.
- #2236 `320d32c9` — Auto-Detect per-page fan-out; #2243 `8a7af1bd` — Apple in vision fallback.
- #2225 `97d5f0e9` — lancedb stamp embedding_model_id; #2244/#2245 `72a7f28f` — empty-output detection.
- #2224 `e0f23367` — vision/LLM result cache (Daniel's caching ask); #2228 `2dba9169` — vision timeout+telemetry;
  #2231 `1387fefc` — ONNX off event loop; #2233 `5b7f6490` — batch-embed RAM; #2234 `0f82e51f` — remote-embed gating.
  (These 5 first went RED — worker repaired in ea911ad1; re-gated 5096 passed.)
- #2250 `6ee1e3b1` per-page regression test; #2241 `805aeebb` blank-page crash; #2232 `78e32104` drift-guard full scan.
- #2239/#2240/#2242 `fd6a5e9b` source-tool fan-out; #2249 `0c80697e` whole-PDF→page children.
- #1587 `63b477d5` multi-window observer inject (Swift — swiftlint+Xcode BuildProject verified); #1935 `9d5b7e83` renderer guardrail script.
- #2239/#2240/#2242 `fd6a5e9b` + #2249 `0c80697e` source-tool fan-out + whole-PDF→page children (re-fixed after a bounce).
- #2212 `9b7fcc68` compare-vision empty/None response = error.
- **HEAD = 9b7fcc68, 0.0.2 == origin. 25 issues closed tonight.**
- **AI Backend Hardening: DONE except #2248 (deps, held).** Per-page principle holds across ALL source paths.
- Open: Workflows & Catalogue ~6 (#2223 #2235 #2237 #2238 #2246 #2247 #2251 #2252), Observable 2 (#2009 #1973), AI Infra ~2 (#2211 #2214).
- **Swift commits from backend workers are NOT compile-checked — always swiftlint + Xcode BuildProject (tab windowtab1) before shipping; pytest doesn't cover Swift.**

## Progress update ~01:40
- **29 issues shipped. AI Infrastructure DONE** (#2211/#2212/#2213/#2214 all shipped; only #2248 deps held).
- #2214 `c8abf5fd`+`0c427fc6` (re-fixed after a skipped bounce); #2237 `0a69b71a`; #2213 `cbaee3f9`; #2211 `c2b6688e`; #2212 `9b7fcc68`.

## 🔴 HELD for Daniel — #1973 (Swift, needs a compiler-in-loop pass)
Two autonomous backend-worker Swift-6 attempts failed to COMPILE (worker has no Xcode):
- c7a679a6 (Task.detached): LibraryChangeStream.swift:245 sending/data-race.
- ac0fa7ee (nonisolated apply): DocumentStore+ChangeStream.swift:35-38 — apply() nonisolated but calls main-actor removeDocuments/pendingPatchIds/schedule synchronously.
Correct fix = compute diff OFF main, do ALL @Published/store mutations ON @MainActor — a threading-contract change across all 13 stores. WIP on ms/ai-backend-harden (c7a679a6, ac0fa7ee). Commented on #1973 with both build errors. ai-backend redirected off it. ALWAYS Xcode BuildProject before shipping ANY Swift — caught both blind failures.

LESSON (kept): a behavior change must sweep ALL existing caller tests (sync→async mocks; folder_tool subfolders; skip-empty guards; SQL-dialect assertions); workers over-report self-testing — ALWAYS full-gate before push. Tonight the gate caught 4 separate red batches the workers called green (5-fail async, 1-fail folder_tool, 4-fail #2214+#2213) — branch never went red.

## 🔴 HELD for Daniel's morning go (do NOT auto-merge)
- #2248 deps upgrade — committed `946217e2` on ms/deps-update, worker-gated in ISOLATED `.venv-deps`.
  Merging means upgrading the SHARED `.venv` his live :8765 backend runs on. Deliberate morning merge only.

## Current Focus — overnight autonomous BACKEND milestone work
Work backend milestones via Claude workers in external worktrees (`~/code/fichero-worktrees/`),
3–10 issues per batch, gate+merge in batches (don't over-verify — it's slow). Priority order:
1. **#2222 (TOP)** — Transcribe *cloud* path saves combined transcript to the PARENT PDF, not
   page children. Fix: cloud/Gemini transcribe must OCR each page image separately and write
   each page's text to its page child (build `per_page_texts` for the single-call path, like
   #2215 did for the Apple/LLM path). Add a unit test asserting per-page page_content. No live
   backend needed to gate (mock vision). Daniel re-tests live in the morning.
2. **Observable Data Layer** (4 open, 77% done) — nearly complete, backend-safe.
3. **AI Infrastructure** (4 open, 82% done) — nearly complete.
4. **Remote & Self-Hosting** (16 open) — engine-remote / storage-HTTP / configurable host (backend).
5. **Developer Experience** (27 open) — docs + tooling (verify_all, sync_openapi, gates, CI).

## In Progress
- tmux lanes `f_importer_fixes` (worktree `importer-fixes`, branch `ms/importer-fixes`) and
  `f_icanh_cli` (stood down). importer-fixes was told to fix #2222 — verify it has the
  CORRECTED diagnosis (cloud path per-page, not "vision never runs").
- Uncommitted OpenAPI surface regen on `0.0.2` (5 files) committed at this session-end.

## Opus reviews COMPLETE — milestones populated
- **AI Backend Hardening**: #2224 (per-page cache), #2225 (lancedb model-stamp migration),
  #2226–#2234 (E5 role mismatch, quota misclassification, vision-path missing timeout/telemetry,
  fire-and-forget embeds, silent batch-embed except, sync-ONNX-blocks-loop, drift-guard-32-row,
  RAM-OOM embeds, remote-embed gating), #2248 (deps upgrade).
- **Workflows & Catalogue Hardening**: #2222 (one-page-at-a-time), #2223 (startup re-run),
  #2235 (msgpack checkpoint), #2236–#2247 + #2249–#2252. KEY VERDICT: one-page-at-a-time is
  honored BY CONSTRUCTION in the default "Transcribe" preset + Catalogue (direct files-source→
  transcribe edge, Send fan-out), but BREAKS silently in Auto-Detect (#2236), folder/collection
  sources (#2239/#2240/#2242), and the whole-PDF fallback (#2249). Highest-leverage: #2236,
  #2243 (Apple not in vision fallback), #2244/#2245 (empty success reported as OK), #2250 (the
  missing per-page regression test).

## Active worker lanes (persistent tmux — feed next batch, don't respawn)
- `f_importer_fixes` (ms/importer-fixes) — #2222 + workflow bugs.
- `f_ai_backend` (ms/ai-backend-harden) — AI Backend Hardening batch.
- `f_deps` (ms/deps-update, opus) — #2248 in ISOLATED .venv-deps; gate/integrate separately.

## Next Session — Start Here
1. `git status`, `git worktree list`, `tmux ls`. You OWN :8765 now (Daniel freed it) — use it to
   verify ICANH live after #2222 lands (restart clean backend on importers-worktree source;
   transcribe ~440s/doc is NOT a hang). Don't destroy ICANH library data.
2. Run the 30-min overnight loop (see the ScheduleWakeup prompt): integrate the 3 lanes, gate,
   cherry-pick to 0.0.2, push green, feed next batch. Drain Workflows & Catalogue Hardening →
   AI Backend Hardening → Observable Data Layer (4) → AI Infra (4) → Remote/DevEx → Mac (code-only).
3. f_deps changes pyproject — gate ALONE in its own venv, integrate carefully, never the shared .venv.
4. Read MEMORY.md "Live transcription gotchas": ~440s/doc, restart backend after merges (reload
   unreliable), tmux multi-line needs a 2nd Enter, verify DB/commits yourself (workers over-report).
