# STATE — overnight handoff 2026-06-14 (late)

Branch `0.0.2`, tracking `origin/0.0.2`. Keep `0.0.2 == origin` (gate before every push).

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

## ⚠️ HELD-BROKEN (bounced — do NOT cherry-pick until verified)
- #1973 Swift fix `c7a679a6` (f_ai_backend): moves change-stream apply() off @MainActor across all 13 stores, but BUILD FAILS — LibraryChangeStream.swift:245 Swift-6 'sending'/data-race. swiftlint passed; backend worker can't compile Swift. Worker reworking with off-main compute + MainActor.run for the @Published publish. Its emit() test (Python) was harmless but dropped with it. ALWAYS Xcode BuildProject before shipping ANY Swift.

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
