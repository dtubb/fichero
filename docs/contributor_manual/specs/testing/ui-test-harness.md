# UI-Test Harness — Design Spec (#TBD)

> Milestone: ui-test-harness
> Manual: docs/contributor_manual/guide/11-testing.md
>
> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: APPROVED — 2026-09-09.** Rulings recorded below; tests-first, then
> code, then run individually via Xcode MCP.
> Tags: [OK] built · [MISSING] not built · [PARTIAL] exists / not wired.

## Why this spec exists

XCUITests have **never actually driven the app against real data.** The functional suites
(e.g. `InspectorFlowsUITests.testDocumentInspectorLoadsSeededEntities`) either **skip** (no
venv) or **bounce on the empty new/open-library screen** while `waitForLibraryReady()` grinds
to a 120 s timeout. The click-around leg — the Testing Constitution's weakest — has been
unproven the whole time.

Root-causing it surfaced a second, deeper problem: **the Xcode config had drifted from its own
documentation.** A harness comment asserted "Dev Local is sandboxed"; the actual build config
says the opposite. That stale assumption is what sent the socket into the real app container.
The config-invariants guardrail that prevents that drift is its own spec —
[`xcode-build-configs.md`](xcode-build-configs.md) — so this one stays focused on the harness.
The transport contract the harness depends on is [`transport-http-uds.md`](../transport/transport-http-uds.md).

## Evidence gathered (2026-09-09, before any code)

- **The Python side is healthy.** `test_engine_harness.py --seed-mode full` standalone seeds a
  full library (21 docs / 3 entities / 3 claims / 5 workflows), spawns the engine, binds a real
  world-RW socket, answers `/api/health`, prints the ready line — ~15 s, clean stderr. → the
  seeder/engine is NOT the problem.
- **Dev Local is UNSANDBOXED.** Verified chain: `Fichero (Dev Local)` scheme →
  `buildConfiguration = "Debug"` → `Debug` config has `ENABLE_APP_SANDBOX = NO` (pbxproj).
  `Dev Embedded` is sandboxed; Dev Local (the scheme that runs the UI tests) is not. The
  `UITestEngineHarness.swift:260` comment ("SANDBOXED including Dev Local") is **stale/wrong**;
  `:256` ("non-sandboxed Dev schemes") is right.
- **Consequence:** the #4194 relocation of the socket into the real container
  (`~/Library/Containers/app.fichero.fichero/Data/tmp`) was done to satisfy a sandbox that
  isn't there. It is the ONLY test artifact touching the real container — everything else
  (library, app-home) already lives in a disposable per-run temp dir. That relocation is exactly
  the "test stuff in my real container" ruling #1 rejects.

**CONFIRMED root cause (2026-09-10, ran the harness via CLI with the screen unlocked) — a
two-layer ENGINE-PROVISIONING failure, NOT the app-side bounce first hypothesized:**
1. **Engine wouldn't start.** The engine is spawned as a CHILD of the XCUITest *runner*, so it
   can only `bind()` its UDS socket in the runner's own container temp. The 2026-07-29 relocation
   put the socket in the *app's* container → cross-container `bind()` failed → "engine exited
   (status 1) before becoming ready, no output captured". FIX: bind in `NSTemporaryDirectory`
   (`UITestEngineHarness.shortSocketPath`). Dev Local is UNSANDBOXED, so the app connects fine.
   VERIFIED: the app then received the engine's own 403 — proof the UDS connection works.
2. **Engine refused the seeded library.** Its library-open policy (`security/path_security.py`)
   rejected `Seed.fichero` as "outside every location this engine may open (allowed roots and
   security-scoped grants)" — because the engine's HOME is the disposable app-home, so the temp
   dir is outside its home-derived roots. FIX: the harness sets `FICHERO_LIBRARY_ALLOWED_ROOTS`
   to the per-run temp dir (`test_engine_harness.py`). (commit 497469f15)

Both fixes are committed; the final GREEN run is pending an UNLOCKED screen (XCUITest "enabling
automation mode" times out while the screen is locked — it only runs unlocked). No app-side
bounce fix was needed — the app was never the problem; the engine provisioning was.

## Creative-director rulings (2026-09-09)

1. **Testing container = the disposable per-run temp dir, NOT the real app container.** Move the
   socket back out of `~/Library/Containers/app.fichero.fichero/…` into the harness temp dir with
   the library + app-home. No app-group entitlement needed (Dev Local is unsandboxed). Delete the
   container-path code that the false sandbox assumption spawned. ("drop useless code")
2. **No-library → the main interface.** Remove the empty new/open-library screen entirely; when
   no library is current, render the main library shell (the same rail that already renders during
   `.starting`/`.unreachable`/`.failed` — BackendRootGate `content()`), not a takeover screen.
3. **Python seeder stays** (fix the path, don't rewrite to CLI now). CLI-seeding is a later step
   only if it earns its keep.
4. **Fail-fast, whole run.** On app-side non-connection, abort the run once with one clear
   "harness connection broken — fix this first" signal; never N × 120 s, never silent `XCTSkip`
   for a present-but-broken harness. A genuinely-absent venv/seeder stays a legitimate skip.
5. **Design-led testing for the Xcode configs too** — a guardrail that asserts the config matrix
   (scheme → config → sandbox/arch/deployment/test-plan), so config drift is a red test.

## Behaviors (the four provisioning layers — each a named regression guard)

Found by running the harness end-to-end (report: `reports/ui-test-harness-findings-2026-09-12.md`).
The seeded library/socket/app-home live in the **xctrunner container tmp** (the containerized
runner's `tempfile.gettempdir()`), NOT `/var/folders` as the Evidence section first assumed.

- `harness.runner-gui` [ENV] — XCUITest needs an UNLOCKED GUI session; "Timed out enabling
  automation mode" = locked screen, not a test failure. The runner/report must distinguish it.
- `harness.engine-binds` — **[PARTIAL]** (#4808) fixed in code — `UITestEngineHarness.shortSocketPath`
  (`fichero/Tests/UI/general/UITestEngineHarness.swift:279`) binds the socket under
  `NSTemporaryDirectory()`, the RUNNER's own container, not the app's — but no Swift test exercises
  `shortSocketPath` directly; it's a helper in a UI-test support file, not itself under test. Retagged
  2026-09-18 (re-check, no test read that pins it).
- `harness.library-allowed` [OK] — the harness sets `FICHERO_LIBRARY_ALLOWED_ROOTS` to the
  per-run temp so the engine's `path_security` policy permits opening the seeded library. Pinned:
  `test_configured_library_allowed_roots.py::test_harness_script_sets_library_allowed_roots_to_the_per_run_temp_dir`
  (the harness sets the env var to `self.temp_dir`),
  `::test_configured_library_allowed_roots_permits_a_library_under_it` (the engine's
  `configured_library_allowed_roots()` + `path_within_any_root()` then actually permit a library
  under that dir while rejecting one under the disposable app-home).
- `harness.content-renders` [OK] — **the open layer.** The EntityService transport fix
  (commit c6f8a589c, "route EntityService off raw URLSession onto the centralized transport")
  plus the shared-session harness wiring landed the flow this spec was blocked on:
  `InspectorFlowsUITests.testDocumentInspectorLoadsSeededEntities` (added in ae938e8b0) drives the
  seeded document's inspector Knowledge ▸ Entities facet end-to-end and asserts the seeded rows
  render. Issue #4661 tracked this and is closed with the same evidence.
- `harness.persist-engine-stderr` [PARTIAL] (#4662) — the Python engine harness script (`_stderr_tail`, in `fichero-server/scripts/`) persists stdout+stderr to a stable path (`FICHERO_UITEST_LOG` or
  `/tmp/fichero-uitest-engine.log`) for pre-ready failures, pinned by
  `test_spawn_per_run_harness.py::test_unready_engine_fails_loudly_not_green`. But the Swift-side
  post-ready path (`UITestEngineHarness.stop()`) only prints its stderr tail to
  `FileHandle.standardError` — no stable file, no spawn command, no errno — and nothing pins it.
  See #4662 (same behavior also tracked under `ui-testing.evidence-on-failure` as → #4777 —
  cross-milestone pointer, not this spec's own tracking issue).
- `harness.testing-container` [OK] — confirmed by reading the source: the engine harness script
  in `fichero-server/scripts/` uses tempfile.mkdtemp(prefix="fichero-harness-")
  / tempfile.gettempdir() for socket, library, and app-home, never the real app container; the
  Swift-side `UITestEngineHarness.shortSocketPath` binds in the RUNNER's own NSTemporaryDirectory
  (commit 497469f15). Pinned: `test_spawn_per_run_harness.py::test_stop_leaves_no_orphan_engine_no_socket`
  (asserts socket + app-home are gone after teardown). Corrected citation, 2026-09-18 — this spec
  previously cited a Swift test file that never existed for this claim; that mistake is what
  the "Test matrix" section's own gap row now tracks (see below), separately from this behavior's
  already-real Python pin.
- `harness.app-connects` [PARTIAL] (#4780) — the connection itself now works (see
  `harness.content-renders`), but the ≤15 s target bound from this spec was never enforced:
  `FicheroUISession.swift`'s `readyTimeout` and `ColdLaunchReachesLibraryUITests`'s
  `launchDeadline` are both still 120 s, and nothing measures/asserts actual connect time.
- `harness.fail-fast-loud` [PARTIAL] (#4781) — engine-bind failure is loud and pinned
  (`test_unready_engine_fails_loudly_not_green`). App-side is not: `FicheroUISessionTests.setUp`
  turns ANY provisioning error — including a present-but-broken harness — into `XCTSkip`, and
  `waitForLibraryReady()` has no class-level memoization, so a broken app connection can still cost
  N × 120 s across a run.
- `harness.ios-sim-same-socket` [MISSING] (#4782) — no iOS/iPad UI test target constructs a
  `UITestEngineHarness` or dials `FICHERO_FORCE_UDS_PATH` on a Simulator destination; nothing
  verifies a Simulator process can `connect()` the Mac runner's socket.
- `empty-library-screen.removed` [OK] (#4783) — removed, not just mitigated: `noLibraryView` and
  its mount branch are deleted from `LibraryWindow.swift`; every window/tab resolution goes through
  `LibraryWindow.resolvedLibraryID` (`LibraryWindow+Actions.swift`), whose final fallback is the
  Global library — always real, loaded synchronously by `LibraryManager.shared.init` before any
  window can read it. Pinned by `LaunchWindowSeedTests.testTheCreateOrOpenPromptIsGoneNotJustUnreachable`
  (source-level: neither `noLibraryView` nor its prompt text exist) and
  `testResolvedLibraryIDAlwaysResolves` (the resolution table: nil/stale/closed/valid/restored ids
  all land on a real library).

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | fail-fast classifier (absent-vs-broken); `shortSocketPath`'s path builder | **none — #4701, #4808: `UITestHarnessTests.swift` never existed; no Swift test covers this today** |
| Snapshot/Preview (Swift) | y | the main interface renders with no library current | `fichero/Tests/Unit/**/…SnapshotTests.swift` |
| Backend (pytest) | y | harness seeds + binds + ready-line into a passed-in dir | `fichero-server/tests/integration/test_spawn_per_run_harness.py` |
| Click-around (XCUITest) | y | app connects → seeded rows drive (InspectorFlows goes GREEN) | `fichero/Tests/UI/**` |
| iPad/iOS | y | sim dials the temp-dir socket | `fichero/Tests/UI/ios`, `…/ipad` |

Hard-gate: `harness.app-connects`, `harness.fail-fast-loud`.

## Accessibility identifiers

- `library.content.ready` — keep; ensure it means *library open*, not merely *phase ≠ setupNeeded*.
- The main-interface no-library state gets a stable id for the snapshot/click test.

## Open questions

All four original questions resolved by the rulings above. Remaining unknown: the exact app-side
reason the seeded library isn't current at window-resolve time — pinned by one instrumented MCP
run before the fix, per systematic-debugging.
