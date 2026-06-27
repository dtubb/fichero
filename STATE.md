# STATE — 2026-06-27 NIGHT (7-lane tmux worker grind + governance review)

I am /session-start-manager. Workers run as INTERACTIVE `claude --dangerously-skip-permissions` (some `--model opus`) in tmux session `fichero-workers`, each in its OWN external worktree under `~/code/fichero-worktrees/ms-*` on a `lane/*` branch, committing as **Claude** (`git -c user.name=Claude -c user.email=noreply@anthropic.com`), NOT pushing. I review+ponytail+build-gate+verify_all+merge-via-PR+close-issues+re-dispatch on a 15-min loop. Resilient to Escape (separate processes). I keep STATE + RELEASE_NOTES current; main GREEN.

## THE 7 LANES (tmux window → worktree → job)
- **docs** → ms-docs (lane/docs): docs CONTENT — README typos, CHANGELOG→one RELEASE_NOTES, developer→contributor, platform=iOS/iPadOS/macOS only, FAQ (models not Ollama-only; Issues=dev-backlog→Discussions for users; honest how-built), API-in-progress banner, CONTRIBUTING.md, workflow doc in AGENTS, component .md (fichero/ + fichero-engine/) → thin pointers to canonical docs (single source of truth).
- **guardrails** → ms-guardrails (lane/guardrails): WHOLE Programmatic Guardrails milestone (#2287/2286/2285/2270/2269 + #2461/#2393/#2660/#2281/#2271). scripts/check_*.py + verify_all wiring + KNOWN_VIOLATIONS allowlists.
- **uireform** → ms-uireform (lane/uireform): WHOLE UI Reform — Representations milestone (triage stale-done; implement #2264/#2265/#2266 + net-new).
- **backend** → ms-backend (lane/backend): AI Backend Hardening (#2507 silent-fallbacks→raise, #2615 local models) → Workflows & Catalogue Hardening (backend: #2545/#2538/#2529/#2528/#2535) → more backend milestones.
- **tests** → ms-tests (lane/tests): run backend pytest + verify_all health (#2693 machinery); FIX test bugs, FILE issues for real product bugs (don't paper over), strengthen weak coverage.
- **review** (OPUS) → ms-review (lane/review): governance/structure/agent-harness PLAN-GOVERNANCE.md — canonicalize root md (AGENTS canonical, CLAUDE thin pointer, make less-AI-specific), audit agents/skills/ (used/stale/update/delete/bring-from-~/code/fichero-skills), agent-work/ cleanup + harvest issues, rules.json, architecture-folder rename (swiftui→fichero, api→fichero-engine — RECOMMEND name + flag), AND the CANONICAL DOCS DECISION: **mkdocs renders docs/ (docs_dir: docs); merge site/docs/ INTO docs/; clean docs/ (scratch→agent-work); agent-work separate.** Owns docs STRUCTURE; can execute on its branch.
- **archdocs** (OPUS) → ms-archdocs (lane/archdocs): accuracy-vs-code + impl-status + placement of docs/architecture/swiftui/* + api/* (reform_masterplan, observable_data_layer, mac_shell_design_proposal, mac_assed_audit, ios_appkit_audit, appkit_interop, SWIFTUI_PRINCIPLES). CAN move (Daniel: "no" was a question): durable principles→site/contributor (now docs/), dated audits→archive/agent-work; file issues for unimplemented findings.

## MERGE RECONCILIATION
docs/archdocs/review all touch docs/ — expect conflicts; I reconcile at merge with **review-lane structure as canonical** (docs/ = the rendered source), taking content from docs lane. Build-gate Swift (Xcode windowtab1) for uireform; ruff+pytest for backend/tests; mkdocs --strict for docs lanes.

## PARKED (need Daniel)
- Release: signed DMG 2026.06.27-beta ready; notarization blocked on UPLOAD-BANDWIDTH timeout → retry on wired connection, then Daniel's Keychain for GitHub/Sparkle + Mac TestFlight publish. Repo is PRIVATE so GitHub release won't be public.
- review-lane plan + archdocs placement + the "less-AI-specific" reframings + architecture-folder name → Daniel's sign-off.
- #2702 de-personalize; FastAPI version→dated-release; mkdocs serving at 127.0.0.1:8000.

---

# STATE — 2026-06-27 EVE (release cut + UX/docs batch + publicization prep)

main @ `origin/main` `5407de80`+, synced, **green** (Xcode build verified, 644s 0 errors). Manager session driving the **first dated release** + a wide UX/docs/cleanup batch via worktree-isolated workers.

## RELEASE — DMG built + signed, BLOCKED on notarization NETWORK
- `build/releases/Fichero.dmg` (400M) = **2026.06.27-beta** (build 20260627), full build (engine rebuilt, no skips), **Developer ID signed inside-out** (app + engine binary + embedded `.so` all QAPB6CWYR6, `--deep --strict` OK). Version bumped via PR #2685; auto-date-stamping landed (PR #2699 — future releases self-stamp today's date + same-day sub-number).
- **Notarization FAILED twice — `HTTPClientError.deadlineExceeded` uploading the 400MB DMG to Apple's notary.** This is a LOCAL UPLOAD-BANDWIDTH timeout, NOT a DMG problem. **Next: retry on a faster/wired connection**, or add a resumable-upload/longer-timeout to `notarize.sh`. The DMG is runnable as-is on Daniel's own Mac (signed; right-click-Open or `xattr -cr` if Gatekeeper warns) — notarization only matters for clean first-launch on OTHER Macs.
- Repo `dtubb/fichero` is **PRIVATE** → GitHub release won't be public. ⚠️ Sparkle appcast on a private raw-URL can't be auth'd by end users — fine for testers now, real public auto-update needs a public release repo/feed later.
- Run order in `docs/release/RELEASE_READINESS.md` §5. After notarize: `create-github-release.sh --prerelease` (Sparkle sign, Keychain prompt — DANIEL does the last step), then `release-all.sh --skip-dmg --skip-notarize` (Mac TestFlight). iOS/iPad TestFlight = NOT YET (release-all is Mac-only; needs a new iOS archive lane — iOS now compiles per #2098).

## SHIPPED this session (PRs #2685, #2693–#2699; earlier #2674–#2684)
- **UX batch (PR #2698):** #2474 iOS touch targets, #2520 iPad immersive preview, #2574 library local/remote badge, #1371 tooltips. Gated together (ponytail/swiftlint + macOS build).
- **Inspector (earlier):** #2495 artifact text full-height (Daniel-flagged), #2536 autosave trailing edit.
- **Docs voice (PR #2695):** em-dashes + "not-X-but-Y" stripped from 16 public docs; **USER.md reframed for public open-source** (internal agent-safety lines pulled OUT).
- **README (PR #2694):** Daniel's hand-edited user-facing opening preserved; about.md removed.
- **verify_all → issues (PR #2693):** `build/verify_all_report.json` (category per check) + `scripts/verify_to_issues.sh` routes failures to the right MILESTONE, `--file-issues` auto-files + writes `verify_all_needs_fixing.json` + prints `MANAGER-ACTION:` to flag the manager to dispatch fix-workers.
- **Auto-versioning (PR #2699).** **Sparkle feed-URL fix, iOS compile unblock #2098, mkdocs site, hygiene** (prior PRs).

## CLOSED stale (verify-net-new): #2468 #2521 #2522 #1379 #2547 #2487(dup of #2520) #2662. ready-for-test: #2474/#2520/#2574/#1371/#2495/#2536/#2665/#2666/#2661.

## NEW issues filed (Daniel's UX think-through + docs direction)
- **#2696** inspector: use standard SwiftUI List/Table everywhere, retire custom UX (esp. document inspector).
- **#2697** document-inspector Content pane: top attributes default is wrong — surface interesting artefacts (entities/people/places) as added to the page.
- **#2698**(issue, not PR — CHECK number) folder-vs-children ambiguity: inspector mixes a folder's OWN entities/artefacts with its children's; unclear ownership esp. artefacts. Needs design. Extends #2521.
- **Docs Review milestone #108** (#2686–#2691): Daniel reviews every agent-written doc (README/governance/site landing/FAQ/user/dev/API/how-its-built).
- Docs direction on **#1796** (user manual = explain every UI element + screenshots, app-not-backend) + **#1797** (dev docs for developers) + **#2692** (capture screenshots).

## WORKERS still running (land next session)
- **history-cleanup** (ab65...): merge CHANGELOG.md + HISTORY.md → ONE canonical RELEASE_NOTES.md; `git rm` CHANGELOG/HISTORY.md/HISTORY-worker.md/HISTORY//memory/ (archiving constitution-changelog into RELEASE_NOTES first).
- **public-hygiene** (a56..., opus): audit `.claude/.codex/.agents/.ai` (ALL TRACKED → would go public) → KEEP/UNTRACK+gitignore/FLAG table; vendor app-dev skills from `~/code/fichero-skills/` into the repo (session-start-manager, session-end, dispatch-worker, choose-next, shared principles) WITHOUT leaking private vendor config/secrets.

## ⚠️ PUBLICIZATION TODO (before repo goes public)
- `.claude`(9)/`.codex`(1)/`.agents`(11)/`.ai`(16) files are TRACKED — public-hygiene worker is untracking the private ones. REVIEW its decision table.
- Stale GitHub branches to review/delete (UNMERGED — not touched): `feat/lan-tls-listener-2157`, `feat/2020-entity-provenance-table`, `ms/importers`, `ms/mac-shell`, `ms/macos-gating`, `worker/2627b`, `worker/2633`. Keep `ms/kg-hermeneutics` (open PR #1627), `0.0.2`.
- `rules.json` = cozempic agent-guard policy (KEEP unless removing the guard). `memory/` = stale journals (public-hygiene/history handling).

## NEXT
1. Retry notarization on a good connection → finish the release (Daniel does the Keychain last step).
2. Land history-cleanup + public-hygiene; review the decision table; complete publicization.
3. iOS/iPad TestFlight archive lane.
4. Keep grinding UX (verify-net-new first): #2696/#2697 inspector standard-SwiftUI + attribute-default + folder-vs-children design, #2670 toolbars (Daniel's area).

---

# STATE — 2026-06-27 PM (autonomous manager session — site consolidation + iOS unblock + UX, 11 PRs)

Branch `main` @ `origin/main` (`aab6023b`+), synced, **green** (Xcode BuildProject verified through the session). Daniel out running; manager ran a 15-min check-in loop, dispatching worktree-isolated workers (build-gated before every merge) + one codex tmux lane.

## SHIPPED TO origin/main THIS SESSION (PRs #2674–#2683)
- **One unified public site (PR #2675/#2676/#2677):** a single MkDocs-Material portal = marketing + user docs + dev docs + API (Redoc) + "How It's Built" (agent-transparency). **`docs_dir: site/docs`** — the folder IS the source of truth (no `exclude_docs` allowlist, no `docs/` mirror; `docs/` stays the internal agent scratch area). **11ty fully removed**, real `index.md`/`faq.md` salvaged in, app icon = logo/favicon, on-disk cruft cleaned. `site_url` is a placeholder pending the real `fichero.***` domain; landing copy marked `<!-- PLACEHOLDER: Daniel to rewrite -->`.
- **iOS UNBLOCKED (PR #2681 #2098 + PR #2682):** the iOS Simulator target did NOT compile on main (ungated macOS-only APIs — `onDeleteCommand` ×6, `homeDirectoryForCurrentUser`) — almost certainly *why* iPad/iPhone "wasn't working". Gated 7 sites behind `#if os(macOS)`; iOS + macOS both BUILD SUCCEEDED. PR #2682 also guards the macOS engine-embed Run-Script for non-macOS so iOS **Release** builds too. See [[ios-build-gate-via-worktree-worker]] (worktree workers iOS-build without the Xcode build.db lock).
- **Governance docs grounded in code (PR #2675):** README/CONSTITUTION/.claude/CLAUDE.md — LLM layer is **LangChain** not LiteLLM (cost-only), transport is **pinned HTTPS** not HTTP, **MCP server is live** not planned.
- **verify_all failure summary (PR #2674):** failed checks now collect into one consolidated block + count at the end (Daniel's "does it list all the errors?" — now yes).
- **Sparkle feed-URL fix (PR #2678):** pbxproj `SPARKLE_FEED_URL` repointed off the retired `fichero-releases` repo → canonical `dtubb/fichero/main/fichero/appcast.xml` (both configs).
- **Repo hygiene (PR #2679):** #2656 dynamic cron path, #2658 retire 0.0.2 handoff paths, #2659 drop duplicate `Sources/openapi.json`.
- **UX (PR #2680 + #2683):** #2648 percent-encode `X-Fichero-Library-Path` (non-ASCII paths), #2664 no red engine-failure flash during startup, #2607 true full-screen iPhone image viewer, #2495 inspector artifact text fills full height (Daniel-flagged), #2536 autosave no longer drops the trailing edit.
- **RELEASE_NOTES.md + docs/release/RELEASE_READINESS.md (PR #2675):** dated changelog + manager-executable publish checklist.

## STALE-DONE ISSUES CLOSED / READY-FOR-TEST
- Closed (already on main): #2468 (no empty Artifacts tab, 3008814c), #2521 (current-vs-children filter, 94cf11d1).
- `ready-for-test` (fix on main, need Daniel's device/visual verify): #2665 iPad crash, #2666 iPhone reader, #2661 click→inspector, #2648/#2664/#2607/#2495/#2536.
- ⚠️ **Stale-issue rate is high** — several "open" issues were already shipped. **Verify net-new (fix not already on main) BEFORE dispatching a worker.**

## RELEASE — READY, BLOCKED ONLY ON DANIEL'S KEYCHAIN
Every cert/key/profile/tool present (Developer ID, Apple Distribution, notarytool profile, ASC `.p8` `2MGYUR786H`, provisioning, Sparkle EdDSA key, `gh` auth). Run order in `docs/release/RELEASE_READINESS.md`. Remaining = execution only: fresh `build-release-dmg.sh` → `notarize.sh` → `create-github-release.sh` (Sparkle `sign_update` needs Keychain approval) → first `gh release` (no `v*` tags yet) → `release-all.sh --skip-dmg --skip-notarize` (Mac TestFlight, needs Keychain). Compile blockers that previously failed the archive are fixed. `build-release-dmg.sh [2b/6]` inside-out re-sign is load-bearing — never `codesign --deep`.

## WORKERS / OPS
- codex tmux (`fichero-workers:1`) idle after the hygiene batch — prompt-heavy/low-throughput; **prefer background Claude subagents** for the grind. Worktree-isolated subagents build-verify in their own dir (no Xcode lock) and auto-report.
- Build gate = Xcode MCP `BuildProject` (tab `windowtab1`); iOS gate = a worktree worker running `xcodebuild -destination 'generic/platform=iOS Simulator'`. NOT `xcodebuild test`/verify_all on Daniel's desktop.

## NEXT — START HERE
1. **Release publish** (needs Daniel present for Keychain): walk `RELEASE_READINESS.md` §5 run order; rehearse with `--dry-run` first.
2. Pick the real domain → swap `site_url` + add `site/docs/CNAME`; Daniel rewrites the placeholder landing copy.
3. **Keep grinding UX** but VERIFY-NET-NEW first: EPIC #2670 toolbars (Daniel's active area — coordinate), #2455 slide-in attribute browser, #2458 annotation controls, observables (#2278/#2009/#1696). Non-toolbar, build-gate, worktree-isolated.
4. Optional cleanup: delete dead `ArtifactsInspectorPane.swift` (needs pbxproj deregistration via `add-swift-file.rb` reverse).

---

# STATE — 2026-06-27 (Mac/iOS shell batch + Canvas/Space shipped; release lane handed to manager)

Branch `main` @ `origin/main` (`1da7f098`), synced. This session: regression-fix the Mac/iOS shell + Canvas/Space view modes, ship them, then inherit the release lane.

## SHIPPED TO origin/main THIS SESSION
- **iOS/view-mode (PR #2668):** #2665 iPad EXC_BAD_ACCESS stack-overflow (re-gate `.spatial`); **#2667 Canvas/Space merge** — collapsed 3 overlapping spatial modes → **Canvas (2D)** + **Space (3D)** on the shared `canvasLayoutStore` (xpos/ypos), retired duplicate `mapView`/`LibraryMapComponents` (−115 lines); #2666 iPhone reader push (`@State` `.navigationDestination`). See [[canvas-spatial-fold-into-library]].
- **Mac inspector + reader/representation (PR #2668):** #2661 click→inspector, #2468 redundant Artifacts tab, #2521 current-vs-children, #2455 detail slide-in, #2522 focus-aware selection, #2519 multi-select delete, #2467 collapsible reader toolbars, #2481 three-pane split.
- **Build hotfixes (PR #2669 + codex PR #2671):** worker commits were swiftlint-clean but **never compiled** → 4 scope/overload errors reached origin/main (SplittablePane `.frame(maxWidth:height:)`, EntityDigestView `confirmDelete`, EntityDetailView+Claims `provenanceSummary`, ReaderToolbar `splitAxisActions`). All fixed; Xcode BuildProject green. **LESSON → new HARD rule [[workers-on-separate-worktrees-merge-to-main]]: workers in their OWN worktree; manager merges + runs a real Xcode build before push. swiftlint is NOT a compile gate.**
- Consolidated other lanes' WIP (engine KG routes/NER/deps, release scripts, Xcode dated-release versioning, shell view-mode menu/DocumentStore env).

## EPICS FILED
- **#2667** Canvas/Space view-mode merge (frontend done; backend mindpalace-endpoint retirement DEFERRED post-TestFlight).
- **#2670** Unify all mini-toolbars — bottom-anchored, Tahoe liquid-glass, adaptive button count per platform (iPhone fewest / iPad fewer / macOS graceful overflow not extend), for sidebar+library+preview+reader+inspector. (#2495 already tracks the inspector text-editor-height bug.)

## RELEASE LANE (now manager-owned; runbook: docs/release/release-lane.md)
- **DMG:** built, notarized, stapled — `build/releases/Fichero.dmg` (`xcrun stapler validate` ✅; notary submission `3b636277-68bf-4266-9383-dc28f800402a` Accepted). `build-release-dmg.sh [2b/6]` signs every embedded Mach-O individually — DO NOT replace with `codesign --deep`.
- **Mac TestFlight:** archive previously FAILED only on the now-fixed compile errors → **re-run:** `scripts/release-all.sh --skip-dmg --skip-notarize 2>&1 | tee build/releases/testflight-$(date +%Y%m%d-%H%M%S).log`, then parse `error:|ARCHIVE FAILED|EXPORT FAILED|Upload`. Uses Mac App Store Connect profile UUID `fe5c4814-...`, Apple Distribution cert `7CD87BA0...`. MARKETING_VERSION converted to numeric for App Store Connect.
- **GitHub/Sparkle:** DMG ready; `create-github-release` blocks at Sparkle `sign_update` until Daniel approves Keychain access (service `https://sparkle-project.org`, account `ed25519`, tool `~/code/sparkle-tools/bin/sign_update`). GitHub target `dtubb/fichero`, appcast `fichero/appcast.xml`.
- Constraints: build/archive only — NO `xcodebuild test`/`verify_all.sh`; no hand-edit pbxproj/openapi; no print `.p8`/Sparkle key; PR to push (never direct to main).

## GATE NOTE (Daniel's verify_all question)
`scripts/verify_all.sh` prints `FAIL <label>` per failing check and a single trailing `verify_all (<tier>): FAILURES ABOVE` — it does NOT aggregate every error into one final block, so errors scroll past mid-run. Worth adding a final consolidated error summary (file under Test Coverage / DX). Note: verify_all runs `xcodebuild iPhone/iPad Simulator build` — heavy/GUI on Daniel's desktop; prefer Xcode MCP `BuildProject` for the Swift compile gate.

## NEXT SESSION — START HERE
1. **Re-run the TestFlight archive** (compile blockers are fixed): `scripts/release-all.sh --skip-dmg --skip-notarize`; parse the log; report archive/export/upload result.
2. **GitHub/Sparkle release** once Daniel approves the Sparkle Keychain prompt: `scripts/release-all.sh --skip-dmg --skip-notarize --skip-testflight --github --draft`.
3. **Keep grinding UX** (build-verify-before-merge, workers in separate worktrees): EPIC #2670 toolbars, #2495 inspector text-editor height, observables (#2278/#2009/#1696), standard-SwiftUI/emoji→SF-Symbol sweeps. Daniel actively edits toolbar files in Xcode — dispatch workers onto NON-colliding areas.
4. Then: Briefcase engine update → fresh Xcode build → DMG/TestFlight; verify Mac-host + remote-device connect.

GOTCHA: the main checkout is SHARED — Daniel + codex release lane + workers all touch it; the dirty tree moves under you. Build-verify via Xcode MCP `BuildProject` before any push.

---
# STATE — 2026-06-26 (0.0.2 → main MERGED via PR #2652; worktrees purged; TestFlight next)

Branch `main` @ **6437c140** (= `origin/main`, clean). The `0.0.2` working line is merged to `main` via PR #2652 (real merge commit, parents `0f5665ad` + `1ec14343`). **`main` is now the working branch** — `.claude/CLAUDE.md` `WORKING_BRANCH` updated, `CONSTITUTION.md` + `docs/agent-workflow/*` + `scripts/check_unmerged_work.py` swept for `0.0.2` working-branch refs. All 8 stale worktrees purged (`git worktree remove --force`); only the `main` checkout remains.

## DONE THIS SESSION
- **Merge**: PR #2652 → `origin/main` = `6437c140`. Not a fast-forward (main had 2 old PR-merge commits); merged with `--merge` for a real merge commit.
- **Worktree purge**: codex-execpkg, codex-execrunner, codex-multiplat, codex-wf2525, codex-wf2627b, codex-winchrome, integrate-batch5-20260626, integrate-frontend-batch-20260625 — all removed. Branches preserved (held `#2594` work still on codex-execpkg/codex-execrunner).
- **Reference sweep** (`0.0.2` → `main` in active instructions): `.claude/CLAUDE.md`, `CONSTITUTION.md`, `docs/agent-workflow/skills/dispatch-worker.md`, `docs/agent-workflow/parallel-execution.md`, `docs/agent-workflow/github-conventions.md`, `docs/architecture/swiftui/workflow_checklist.md`, `scripts/check_unmerged_work.py`. Historical records (`HISTORY.md`, `MEMORY.md`, dated `docs/design/*`, `docs/archive/*`, release-notes-0.0.2.md, `v0.0.2` release tag) left as-is.
- **Test hangs filed, NOT silently merged past**: #2650 (execute-route blocks in-process at `client.post` — `test_routes_workflow_execution.py` 16th test), #2651 (2nd hang — DuckDB/lancedb connection deadlock mid-suite). Plus #2649 (guardrail allowlist drift).

## GATE STRENGTH (acknowledged debt — fix AFTER release)
Daniel: "verify_all is important, but when there are errors we're not fixing them — our gate isn't strong enough." Accepted. The structural fix is **conftest app-DB isolation + seeding** (the backend suite shares `app.duckdb` with the live engine → contaminated when the engine is up; isolation alone breaks the suite on an empty DB). Deferred to the post-release testing-cleanup pass along with #2649/#2650/#2651. Path B for the release: merge on "no new correctness regressions," don't detour into fixing the gate now.

## NEXT — TESTFLIGHT RELEASE (the goal)
Sequence per Daniel: merge (✅) → TestFlight → GitHub release → then testing cleanup → then backend + issues on `main`.
1. #158 — App Store Connect API key for notarization.
2. #159 — verify Sparkle EdDSA private key matches the public key in Info.plist.
3. #160 — build engine + signed Release app + DMG.
4. #161 — notarize DMG + staple ticket.
5. #162 — Sparkle-sign DMG + GitHub release on `fichero-releases` + tag source.
6. #163 — wire real download URL in site/index.md + deploy site.
7. #164 — smoke test: download fresh DMG on a clean Mac account / after `xattr -cr`.

## POST-RELEASE (deferred)
- Testing-cleanup pass: #2649 (guardrail allowlist), #2650 (execute-route hang root-cause), #2651 (DuckDB/lancedb deadlock — identify the test), + conftest app-DB isolation+seeding (the structural gate fix).
- Then: proceed on backend + issues on `origin/main`.

GOTCHAS: working branch is now `main` — commit work directly to `main` (PR still required to push). Worktrees branch from `main`, live ONLY under `~/code/fichero-worktrees/`. Never `rm -rf` a bare `~/code/fichero-*` sibling. The `0.0.2` branch still exists (preserved for history); do not start new work on it.

---
# STATE — 2026-06-25 (manager takeover from Claude; 0.0.2 cleaned, pushed, workers shut down)

Branch `0.0.2` @ **c8775216** (= `origin/0.0.2`, clean). I took over the manager lane from Claude's rate-limited session, recovered its session history, reconciled the live worktrees/branches, pushed the two held-local `#2594` commits, cleaned the dirty tree, filed the new PDF fan-out efficiency bug, and shut down the stale worker tmux sessions (`f_knowledge`, `f_mindpalace`, `f_runner`).

## LANDED / CONFIRMED
- **#2594 option (a) is fully landed and pushed**: leaf-only `execution/` move, with `runner.py` intentionally left under `api/routes/workflow_execution/` so the SwiftUI wiring contract stays green. Remote `0.0.2` now includes:
  - `df7b41ea` `refactor: move workflow runner into execution (#2594)`
  - `c8775216` `test: update runner source guard for execution move (#2594)`
- **#2593 is resolved as "do not delete those routers"**. The useful part that remains is the additive SSRF coverage migration already on branch (`304abc62` / `test_research_tools_ssrf.py`). No dead-router deletion should be merged.
- **#2621** already tracks the Activity 0%-progress / empty-log live bug. Claude's final finding says the current root cause was a stale Mac app build that still used `URLSession.shared.bytes(...)` instead of the pinned session; fix path is rebuild + relaunch from current `0.0.2`, not a new code change.
- **#2622** newly filed: PDF per-page fan-out currently re-renders the same source PDF once per page instead of rendering once up front, wasting CPU/memory without increasing model tokens.

## HELD / NEEDS REVIEW
1. **#2596** — `knowledge/` package consolidation is still OPEN and unmerged. Big mostly-move diff (~5.5k insertions / ~5.4k deletions) with no manager sign-off yet. Treat it as a supervised repo-hygiene lane, not a drive-by merge.
2. **Swift/OpenAPI follow-ups for #2589/#2590/#2591** — backend fields/routes landed, but the app-side adoption and generated-surface consumption still need a deliberate lane.
3. **Workflow hardening after today's live reports** — `#2622` should probably run under the same milestone as `#2545` (`Workflows & Catalogue Hardening`), because it's the same scale/reliability class.

## NEXT SESSION — START HERE
1. Rebuild and relaunch the Mac app from current `0.0.2` to verify the `#2621` stale-build explanation and confirm Activity progress/log recover on the fresh app binary.
2. Dispatch a backend worker on **#2622**: instrument the PDF fan-out path, switch it to batch-render once via `_batch_render_pdf_pages_to_cgimages()`, add a regression check.
3. Dispatch a review lane on **#2596** before any merge. Require a narrow answer: does the `knowledge/` reorg preserve import compatibility and pass targeted backend gates, or should it stay parked?
4. After the workflow/backend lane returns, decide whether the next manager batch should be **repo hygiene/reorg** (`#2596`, #104, README/docs cleanup) or **workflow reliability** (`#2545` + `#2622`).

GOTCHAS: the dirty worktree at takeover was just leftover schema/client regen plus `EOF` and `scripts/f_director-check.sh`; those are cleaned out and not part of the branch. `codex-execpkg`/`codex-execrunner` are superseded by pushed `0.0.2`; `codex-knowledge` still exists as the parked `#2596` worktree.

---
## (recent context — earlier 2026-06-22 overnight; see HISTORY.md)
Branch `0.0.2` @ **0dc1f276+**. Overnight loop shipped: workflow 100k-hardening, Activity rebuild, shell UX.

## SHIPPED THIS SESSION (all gated + pushed to 0.0.2)
**Workflows & Catalogue Hardening (#91):** untested-flag (display-only trust); #2533 (one save path); #2523 (per-page documents in ALL transcribe presets + builder double-fan-out bug); #2537 (typed nodes/edges boundary + source_port drift); #2538/#1943 (Activity SSE → shared FicheroClient; dev engine HTTPS).
**100k-image reliability (EPIC #2545) — the whole chain is ON:** C2 #2540 (DB/embed off event loop) · C1 #2539 (vision loop bounded-concurrent) · C4 #2542 (batched writes + Lance compaction) · C5 #2543 (provider backoff + circuit breaker) · H1 #2544 (capped folder source) · M1 (API-key cache) · **#2532 FLIPPED — enable_parallel=True on the run path** (memory bounded O(4) by semaphore; 988 workflows pass).
**Activity = live monitor (#2546):** B1 (shared @Observable WorkflowExecutionStore) + B2 (poppable hierarchical run→node→file table; editor inline progress removed) + **the live-stream FIX**: SSE /stream was a single-consumer queue (2nd subscriber starved → 0% + empty log); now a WorkflowEventHub pub/sub + replay buffer; plus overallProgress seeds totalFiles from file events. NEEDS Daniel visual confirm.
**Mac App Shell (shell-reform):** ALL FOUR reported shell issues SHIPPED — #2547 (iPhone inspector full-height) · #2548 (Mac sidebar selection reconcile) · #2549 (iOS reader hide zoom on compact) · #2550 (glass minitoolbars). EPIC #2551 REMAINDER needs Daniel's runtime/visual review (build-gate-only can't verify these safely): NotificationCenter claim-selection → observable; singleton @ObservedObject → @Environment; split ContentView+State.swift(995)/ContentView(859)/PDFPageView(799); swipe-between-modes nav. Overnight loop holding on these — no risky blind refactors.

## DEFERRED / NEEDS DANIEL
- Visual confirm: Activity live progress+log now stream; per-page transcription all presets; B2 table (the ↗ pop-out button); the two shell P0 fixes.
- Backend follow-up: aggregator-barrier retention at huge fan-out (ponytail note in builder.py, bounded by largest single fan-out).
- Release pipeline tasks (#158-165) untouched.

---
# (history) STATE — Session end 2026-06-22 (workflow review + integration + GH hygiene)

Branch `0.0.2` @ **1921aa35** (= origin, clean). Today's project: the **workflow / node-editor** system.

## SHIPPED THIS SESSION (0.0.2, each full-suite baseline-diff 0-new, pushed)
- **#2513** (3b4b4d8b) — save_artifact ValidationError no longer swallowed (fail loud).
- **#2514** (4ee6b3be) — removed redundant DBWriter; single connection+lock is the sole write path → **#90 AI Backend Hardening DONE**.
- **#2523** (1921aa35) — **HTR two-pass saves PER-PAGE** (wired the unwired `documents` port across all 5 transcribe presets + DB-resolve backstop). RE-TEST: run Transcribe HTR on a multi-page PDF or folder of images → each page/image gets its own transcription + review; parent stays empty.

## PARKED — `worker/untested-flag` @ 6d1d7406 (2 commits, NOT landed)
- "Untested" tool badge (ToolDef.tested; only the 4 HTR-chain tools tested) + "(Untested)" on all presets except Transcribe HTR + the existing-library in-place-rename fix (old names → `_DEPRECATED_PRESET_NAMES`).
- **TODO before merge:** dedupe catalogue.json duplicate `config` key, fold #2445 (font), gate (ruff + swiftlint + compile-only Swift build — NOT RunAllTests on Daniel's desktop), full backend baseline-diff, cherry-pick to 0.0.2, push, remove worktree.

## THE WORKFLOW PATHWAY (the project — Workflows & Catalogue Hardening milestone, EPIC #2524)
Grounded in **docs/reviews/workflow-nodes-backend-review.md**. North star: atomic tools the user chains → tests on one folder → copies the chain to another (per-page save is the contract).
1. Land Phase 1 (untested-flag, above).
2. **Structural** (review order): **#2532** P0 parallel-fork (preview graph ≠ run graph) → **#2537** P1 typed Workflow.nodes/edges boundary → **#2533** P1 collapse save-wrappers → **#2534** P2 bundle.
3. **Editor form** (#2524): clickable/editable edges, user-chosen fan-out, native diagram (#2525 drop Pyppeteer), minitoolbar-at-bottom (#2527), import (#2528), compare-as-sidebar (#2526), font (#2445).
4. **Capabilities:** HTR bboxes (#2530), human-in-loop (#2529), auto_detect port (#2531), RAG-in-HTR cleanup, exporter (#2535).

## NEXT SESSION — START HERE
1. `git -C ~/code/fichero status` — 0.0.2 should be 1921aa35 = origin; worktree `untested-flag` @ 6d1d7406 carries parked work.
2. Daniel's call: **land `untested-flag`** (do the TODO above) OR start the workflow **structural** lane #2532.
3. GOTCHA: workers spawned before the overnight run are 50-110 commits STALE — never merge them wholesale (ios-reader-polish would revert ~5000 lines). Verify "closed" issues against actual code (#2445 was closed-but-unfixed).
4. Build gate on Daniel's active desktop = swiftlint + compile-only `BuildProject`, NEVER RunAllTests/verify_all (launches Fichero GUI windows).

---
## (history — overnight 2026-06-22, mostly shipped/superseded this session)
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
