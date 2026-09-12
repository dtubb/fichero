# UI-Test Harness — problem report & test findings (2026-09-12)

Companion to the spec `docs/contributor/specs/ui-test-harness.md`. This is the record of what
was actually wrong — found by running the harness end-to-end via CLI — so the last layer can be
closed without re-deriving the first four.

## Summary

XCUITests had **never** driven the app against real data. The failure was NOT the "app bounces
to the empty new-library screen" the spec first hypothesized. It was a **stack of four distinct
layers**, each hiding the next, all in engine *provisioning* — the app was never the problem.
Peeling them (each fixed, then the next appeared):

| # | Layer | Symptom | Root cause | Fix | Status |
|---|-------|---------|-----------|-----|--------|
| 1 | Can't run tests | "Timed out enabling automation mode" | XCUITest needs an **unlocked GUI session** | (operational — unlock the screen) | env, not code |
| 2 | Engine won't start | "engine exited (status 1), no output captured" | engine is a **child of the sandboxed XCUITest runner**; the socket was bound in the *app's* container (`app.fichero.fichero/Data/tmp`) — cross-container `bind()` fails | bind in the runner's own `NSTemporaryDirectory` (`UITestEngineHarness.shortSocketPath`) | **FIXED**, verified (app then connected) |
| 3 | App connects, engine refuses library | on-screen **"No Access to Seed"** (403) | engine's library-open policy (`security/path_security.py`) rejects `Seed.fichero`: it's in the **xctrunner container tmp**, outside the engine's home-derived allowed roots (engine HOME = disposable app-home) | harness sets `FICHERO_LIBRARY_ALLOWED_ROOTS` = per-run temp (`test_engine_harness.py`) | **FIXED** (library now opens) |
| 4 | Library opens, nothing renders | "a library seems to open… but nothing happens in the app" | **OPEN** — seeded content/entities don't drive the UI once the library is current. App-side (change-stream/observation, or the seeded library is empty as the app sees it). | — | **TODO** (next session) |

Commits: `497469f15` (layers 2+3), spec updated in the same range.

## Why it took four passes (the testing lesson)

- **The spec's evidence was wrong on one fact.** It assumed the seeded library lives in
  `/var/folders` (which the engine auto-allows, `api/main.py:1090`). It actually lives in the
  **xctrunner container tmp**, because the containerized runner's `tempfile.gettempdir()` resolves
  to its container, not `/var/folders`. Fix the spec's "Evidence" section to say this.
- **The harness discards the evidence you need.** On failure the engine's stderr came back
  `<no engine output captured>` and the persisted engine log was empty — so each layer had to be
  inferred rather than read. **Recommendation:** the harness must persist the engine's real
  stderr + the exact spawn command + errno to a stable, always-readable path on every failure.
- **`test-without-building` hides the app console;** only `xcodebuild test` streams it. Debugging
  needed the app's own log lines, which the faster invocation dropped.
- **Automation mode needs an unlocked screen** — every locked run wasted ~2 min on a timeout that
  looks like a real failure. The harness/report should distinguish "runner never initialized"
  (operational) from "test ran and failed" (real).

## Recommended spec/code follow-ups

1. Close layer 4: instrument the app's library-open→content path under `--uitesting`; confirm
   whether the seeded library the app opens actually contains the seeded rows (the engine serves
   them, but does the app's current-library observation fire?).
2. Harness: **persist real engine stderr on failure** (the single biggest debugging accelerator).
3. Spec: correct the library-location assumption; add the four-layer table above as the
   root-cause record; add a **behavior** for each layer so a future regression in any one is a
   named red test.
4. Consider the fail-fast ruling (#4 in the spec): a present-but-broken harness should abort the
   whole run once, loudly — not `XCTSkip` per test (which reads as green).
