# UI-Test Harness — Design Spec (#TBD)

> Milestone: ui-test-harness
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
The transport contract the harness depends on is [`transport-http-uds.md`](transport-http-uds.md).

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

**Corrected root-cause direction:** filesystem reach is NOT the blocker (unsandboxed app reaches
`/var/folders` fine). The empty-state bounce is an **app-side launch/open behavior** — the
seeded library isn't becoming *current* before the window resolves, so the root switch shows the
empty new/open-library surface instead of the library shell. To be pinned by ONE instrumented
app run (Xcode MCP) before the fix — do not fix ahead of that.

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

## Behaviors

- `harness.testing-container` [MISSING] — socket + library + app-home all live in the disposable
  per-run temp dir; nothing is written to the real app container.
- `harness.app-connects` [MISSING] — the app reaches `library.content.ready` with the seeded
  library OPEN within a short bound (target ≤ 15 s), not 120 s.
- `harness.fail-fast-loud` [PARTIAL] — engine-bind failure is already loud; app-side connect
  failure aborts the whole run once with a clear signal.
- `harness.ios-sim-same-socket` [MISSING] — a simulator build dials the same temp-dir socket;
  verify a sim can `connect()` it (sim shares the Mac filesystem).
- `empty-library-screen.removed` [MISSING] — the empty new/open-library screen is gone; no-library
  renders the main interface.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | fail-fast classifier (absent-vs-broken); testing-container path builder | `fichero/Tests/UI/general/UITestHarnessTests.swift` |
| Snapshot/Preview (Swift) | y | the main interface renders with no library current | `fichero/Tests/Unit/**/…SnapshotTests.swift` |
| Backend (pytest) | y | harness seeds + binds + ready-line into a passed-in dir | `fichero-server/tests/test_engine_harness_*.py` |
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
